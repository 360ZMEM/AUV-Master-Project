#!/usr/bin/env python3
"""Independent ROS2 node that swaps the stable cable facade for v2."""

from __future__ import annotations

from dataclasses import fields
import math
import json
import time
from types import SimpleNamespace
from typing import Any

import numpy as np
import rclpy
from rclpy.executors import ExternalShutdownException
from nav_msgs.msg import Odometry
from sensor_msgs.msg import Imu
from std_msgs.msg import Bool, Float32, Float32MultiArray, String
from auv_interfaces.msg import PerceptionQuality, Setpoint, SonarCableObservation

from auv_decision_ros.cable_guidance_limits import ZigzagProbeConfig
from auv_decision_ros.cable_prior_adapter import load_cable_map_from_config
from auv_decision_ros.cable_tracking_node import CableTrackingNode, PROJECT_ROOT
from .field_identity_calibration import validate_field_identity_calibration
from .runtime_target_anchor import validate_runtime_target_anchor
from .hold_budget import HoldBudgetConfig, HoldBudgetMonitor
from .identity_cue import SonarIdentityPolicy, sonar_identity_cue
from .static_target_prior import validate_static_target_prior
from auv_mag_tracking.v2 import SurveyCurrentEvidence


def _dataclass_kwargs(cls, mapping: dict[str, Any]) -> dict[str, Any]:
    names = {item.name for item in fields(cls)}
    values = {key: value for key, value in mapping.items() if key in names}
    if cls.__name__ == "CrossScanConfig" and "half_span_levels_m" in values:
        values["half_span_levels_m"] = tuple(float(item) for item in values["half_span_levels_m"])
    return values


def _navigation_uncertainty_from_covariance(payload) -> tuple[float, float, float] | None:
    """Extract horizontal position/velocity and yaw 1-sigma from ES-EKF P15."""
    try:
        matrix = np.asarray(payload, dtype=float).reshape(15, 15)
        if not np.isfinite(matrix).all():
            return None
        def horizontal_sigma(indices):
            block = matrix[np.ix_(indices, indices)]
            eigenvalues = np.linalg.eigvalsh(.5 * (block + block.T))
            return math.sqrt(float(max(eigenvalues[-1], 0.))) if eigenvalues[0] >= -1e-6 else None
        position_sigma = horizontal_sigma((0, 1))
        velocity_sigma = horizontal_sigma((3, 4))
        yaw_variance = float(matrix[8, 8])
        if (position_sigma is None or velocity_sigma is None or yaw_variance <= 0.
                or position_sigma <= 0. or velocity_sigma <= 0.):
            return None
        return position_sigma, math.degrees(math.sqrt(yaw_variance)), velocity_sigma
    except (TypeError, ValueError, OverflowError):
        return None


def _matched_imu_heading_sigma_deg(imu: Imu | None, odom: Odometry | None,
                                   *, receipt_age_s: float,
                                   maximum_age_s: float) -> float | None:
    """Use a declared orientation uncertainty only for the matching odometry pose.

    ROS IMU all-zero covariance means unknown and first-element -1 means no
    orientation estimate. A direct quaternion replacement in localization is
    not a covariance update to its ES-EKF P15; the independently supplied
    orientation covariance must be checked instead.
    """
    if imu is None or odom is None or not 0. <= receipt_age_s <= maximum_age_s:
        return None
    imu_stamp = imu.header.stamp.sec + imu.header.stamp.nanosec * 1e-9
    odom_stamp = odom.header.stamp.sec + odom.header.stamp.nanosec * 1e-9
    if (not math.isfinite(imu_stamp) or imu_stamp <= 0.
            or abs(imu_stamp - odom_stamp) > .15):
        return None
    try:
        covariance = np.asarray(imu.orientation_covariance, dtype=float).reshape(3, 3)
        if not np.isfinite(covariance).all() or covariance[0, 0] == -1.:
            return None
        eigenvalues = np.linalg.eigvalsh(.5 * (covariance + covariance.T))
        if eigenvalues[0] < -1e-9 or covariance[2, 2] <= 0.:
            return None
        q_imu = np.array([imu.orientation.w, imu.orientation.x,
                          imu.orientation.y, imu.orientation.z], dtype=float)
        q_nav = np.array([odom.pose.pose.orientation.w, odom.pose.pose.orientation.x,
                          odom.pose.pose.orientation.y, odom.pose.pose.orientation.z], dtype=float)
        if not np.isfinite(q_imu).all() or not np.isfinite(q_nav).all():
            return None
        n_imu = float(np.linalg.norm(q_imu))
        n_nav = float(np.linalg.norm(q_nav))
        if n_imu < 1e-6 or n_nav < 1e-6:
            return None
        angular_difference = 2. * math.acos(min(1., abs(float(np.dot(q_imu, q_nav) / (n_imu * n_nav)))))
        if angular_difference > math.radians(2.):
            return None
        return math.degrees(math.sqrt(float(eigenvalues[-1])))
    except (TypeError, ValueError, OverflowError):
        return None


class _RosV2PipelineAdapter:
    """Keep configured Search/Confirm speeds despite the legacy node speed argument."""

    def __init__(self, core, *, altitude_provider=None) -> None:
        self.core = core
        self._altitude_provider = altitude_provider

    def reset(self) -> None:
        self.core.reset()

    def export_state(self):
        return self.core.export_state()

    def step(self, *args, **kwargs):
        return self.core.step(*args, **kwargs)

    def step_with_guidance(self, navigation, magnetic, sonar=None, *, target_depth_m=None, speed_mps=None):
        if sonar is None and self._altitude_provider is not None:
            altitude_m = self._altitude_provider()
            if altitude_m is not None:
                sonar = SimpleNamespace(
                    time_s=float(navigation.time_s),
                    valid=True,
                    altitude_m=float(altitude_m),
                )
        tracking, guidance = self.core.step_with_guidance(
            navigation,
            magnetic,
            sonar,
            target_depth_m=target_depth_m,
            speed_mps=None,
        )
        if (
            tracking.mode == "track"
            and speed_mps is not None
            and guidance.guidance_source != "v2_endpoint_hold"
            and not getattr(guidance, "safe_lock_active", False)
        ):
            policy = getattr(getattr(self.core, "v2_config", None), "inspection", None)
            if policy is not None and policy.enabled:
                requested = float(speed_mps)
                guidance.speed_mps = min(guidance.speed_mps, max(0.0, requested)) if math.isfinite(requested) else 0.0
            else:
                guidance.speed_mps = float(speed_mps)
        return tracking, guidance


class CableTrackingV2Node(CableTrackingNode):
    """Reuse stable ROS I/O while replacing only the algorithm facade."""

    def __init__(self) -> None:
        super().__init__()
        self.declare_parameter("inspection_latest_navigation_qos", False)
        self._inspection_latest_navigation_qos = bool(
            self.get_parameter("inspection_latest_navigation_qos").value)
        if self._inspection_latest_navigation_qos:
            inspection_mapping = dict(self.config.get("v2", {}).get("inspection", {}) or {})
            if inspection_mapping.get("enabled") is not True:
                raise ValueError("latest navigation QoS requires v2 inspection.enabled")
            for subscription in tuple(self._subscriptions):
                if subscription.topic_name == "/auv/state/filtered":
                    if not self.destroy_subscription(subscription):
                        raise RuntimeError("failed to replace inspection navigation subscription")
                    break
            else:
                raise RuntimeError("inspection navigation subscription unavailable")
            self.create_subscription(Odometry, "/auv/state/filtered", self._on_odom, 1)
        self.declare_parameter("inspection_snapshot_freshness", False)
        self._inspection_snapshot_freshness = bool(
            self.get_parameter("inspection_snapshot_freshness").value)
        if self._inspection_snapshot_freshness:
            inspection_mapping = dict(self.config.get("v2", {}).get("inspection", {}) or {})
            if inspection_mapping.get("enabled") is not True:
                raise ValueError("snapshot freshness requires v2 inspection.enabled")
        self.declare_parameter("inspection_recoverable_input_stale", False)
        self._inspection_recoverable_input_stale = bool(
            self.get_parameter("inspection_recoverable_input_stale").value)
        self._tick_snapshot_wall_s = None
        self._tick_snapshot_nav_wall_s = None
        self._tick_snapshot_cov_wall_s = None
        self._tick_snapshot_nav_uncertainty = None
        self._tick_snapshot_nav_msg = None
        self.declare_parameter("inspection_decision_period_s", .1)
        decision_period_s = float(self.get_parameter("inspection_decision_period_s").value)
        if not math.isfinite(decision_period_s) or not .1 <= decision_period_s <= 2.:
            raise ValueError("inspection decision period must be finite in [0.1, 2.0] s")
        if decision_period_s != .1:
            inspection_mapping = dict(self.config.get("v2", {}).get("inspection", {}) or {})
            if inspection_mapping.get("enabled") is not True:
                raise ValueError("nondefault decision period requires v2 inspection.enabled")
            self.destroy_timer(self.timer)
            self.timer = self.create_timer(decision_period_s, self._on_tick)
        # The legacy constructor replaces Node._subscriptions with its own
        # list, dropping the pre-existing /clock subscription under sim time.
        # Restore it only in this adapter, without altering the v1 node.
        clock_subscription = getattr(self._time_source, "_clock_sub", None)
        if clock_subscription is not None and clock_subscription not in self._subscriptions:
            self._subscriptions.append(clock_subscription)
        from auv_mag_tracking.api import DeploymentPerceptionConfig
        from auv_mag_tracking.config import build_default_scenarios
        from auv_mag_tracking.v2 import (
            AuvMagTrackingPipelineV2,
            CrossScanConfig,
            DetectionConfig,
            FwhmConfig,
            FlythroughConfig,
            FlythroughInspectionPipelineV2,
            InspectionConfig,
            SearchConfig,
            ShallowSurveyInspectionPipelineV2,
            ShallowSurveyMissionConfig,
            TrackingConfig,
            V2Config,
        )

        cable_map = load_cable_map_from_config(self.config, project_root=PROJECT_ROOT)
        scenarios = build_default_scenarios()
        scenario_name = str(self.config.get("scenario_name", "case1"))
        scenario = scenarios.get(scenario_name, next(iter(scenarios.values())))
        self._apply_scenario_overrides(scenario, self.config.get("scenario_overrides", {}) or {})
        v2_mapping = dict(self.config.get("v2", {}) or {})
        self.declare_parameter("navigation_heading_uncertainty_source", "ekf")
        self._navigation_heading_uncertainty_source = str(
            self.get_parameter("navigation_heading_uncertainty_source").value).strip().lower()
        if self._navigation_heading_uncertainty_source not in {"ekf", "imu_orientation_covariance"}:
            raise ValueError("navigation heading uncertainty source must be ekf or imu_orientation_covariance")
        v2_config = V2Config(
            search=SearchConfig(**_dataclass_kwargs(SearchConfig, dict(v2_mapping.get("search", {}) or {}))),
            detection=DetectionConfig(
                **_dataclass_kwargs(DetectionConfig, dict(v2_mapping.get("detection", {}) or {}))
            ),
            cross_scan=CrossScanConfig(
                **_dataclass_kwargs(CrossScanConfig, dict(v2_mapping.get("cross_scan", {}) or {}))
            ),
            fwhm=FwhmConfig(**_dataclass_kwargs(FwhmConfig, dict(v2_mapping.get("fwhm", {}) or {}))),
            tracking=TrackingConfig(
                **_dataclass_kwargs(TrackingConfig, dict(v2_mapping.get("tracking", {}) or {}))
            ),
            inspection=InspectionConfig(
                **_dataclass_kwargs(InspectionConfig, dict(v2_mapping.get("inspection", {}) or {}))
            ),
        )
        if (v2_config.inspection.enabled and v2_config.inspection.allow_uncalibrated_depth
                and not bool(self.get_parameter("use_sim_time").value)):
            raise ValueError("non-sim inspection cannot publish uncalibrated FWHM depth")
        boundary_payload = v2_mapping.get("search_boundary_xy_m")
        boundary = None if boundary_payload in (None, []) else np.asarray(boundary_payload, dtype=float)
        mission_geometry = str(v2_mapping.get("mission_geometry", "cross_scan"))
        if mission_geometry not in {"cross_scan", "flythrough", "shallow_survey"}:
            raise ValueError(f"unsupported v2 mission geometry: {mission_geometry}")
        self._navigation_ground_velocity_frame = str(
            v2_mapping.get("navigation_ground_velocity_frame", "unconfigured")
        )
        if self._navigation_ground_velocity_frame not in {"unconfigured", "world_ned"}:
            raise ValueError("navigation_ground_velocity_frame must be unconfigured or world_ned")
        self._navigation_world_frame_id = str(v2_mapping.get("navigation_world_frame_id", "world")).strip()
        if self._navigation_ground_velocity_frame == "world_ned" and not self._navigation_world_frame_id:
            raise ValueError("navigation_world_frame_id is required for world_ned velocity")
        pipeline_type = ({
            "cross_scan": AuvMagTrackingPipelineV2,
            "flythrough": FlythroughInspectionPipelineV2,
            "shallow_survey": ShallowSurveyInspectionPipelineV2,
        })[mission_geometry]
        flythrough_kwargs = _dataclass_kwargs(
            FlythroughConfig, dict(v2_mapping.get("flythrough", {}) or {}),
        ) if mission_geometry == "flythrough" else {}
        self._runtime_identity_policy = None
        self._runtime_target_anchor_evidence = None
        self._static_target_prior_evidence = None
        self._survey_current_topic = None
        if mission_geometry == "flythrough":
            flythrough_kwargs["side_hint_required"] = True
            runtime_identity_enabled = bool(flythrough_kwargs.get("require_runtime_identity_cue", False))
            if runtime_identity_enabled:
                identity_mapping = dict(v2_mapping.get("runtime_identity", {}) or {})
                required = ("sonar_frame_id", "world_frame_id", "calibration_id",
                            "lever_arm_body_xy_m", "yaw_sonar_in_body_deg",
                            "extrinsic_position_sigma_m", "extrinsic_yaw_sigma_deg")
                missing = [key for key in required if key not in identity_mapping]
                if missing:
                    raise ValueError("runtime identity requires explicit " + ", ".join(missing))
                policy_kwargs = _dataclass_kwargs(SonarIdentityPolicy, identity_mapping)
                policy_kwargs["lever_arm_body_xy_m"] = tuple(policy_kwargs["lever_arm_body_xy_m"])
                self._runtime_identity_policy = SonarIdentityPolicy(**policy_kwargs)
                self._runtime_identity_policy.validate()
                if self._runtime_identity_policy.world_frame_id != self._navigation_world_frame_id:
                    raise ValueError("runtime identity world frame must match navigation world frame")
                if (self._runtime_identity_policy.maximum_age_s
                        > float(flythrough_kwargs.get("maximum_runtime_identity_age_s", 0.5))):
                    raise ValueError("sonar identity age may not exceed flythrough cue age")
            simulated_clock = bool(self.get_parameter("use_sim_time").value)
            flythrough_kwargs["allow_synthetic_side_hint"] = simulated_clock
            if (not simulated_clock and self._runtime_identity_policy is not None
                    and self._runtime_identity_policy.calibration_id.lower().startswith("synthetic")):
                raise ValueError("synthetic sonar calibration cannot enable non-sim identity gate")
            if not simulated_clock and self._runtime_identity_policy is not None:
                # A renamed simulation ID is not physical evidence. Pin the
                # approved field artifact before accepting any ROS quality flag.
                validate_field_identity_calibration(
                    identity_mapping, self._runtime_identity_policy.calibration_id,
                    PROJECT_ROOT,
                )
                if any(key in flythrough_kwargs for key in
                       ("runtime_target_anchor_min_m", "runtime_target_anchor_max_m",
                        "runtime_target_exclusive_min_m", "runtime_target_exclusive_max_m")):
                    raise ValueError("non-sim runtime target anchor and exclusive corridor must come from reviewed evidence")
                self._runtime_target_anchor_evidence = validate_runtime_target_anchor(
                    dict(v2_mapping.get("runtime_target_anchor", {}) or {}),
                    flythrough_kwargs, dict(self.config.get("prior", {}) or {}),
                    PROJECT_ROOT, mission_config=self.config,
                )
                flythrough_kwargs["runtime_target_anchor_min_m"] = (
                    self._runtime_target_anchor_evidence.lateral_min_m)
                flythrough_kwargs["runtime_target_anchor_max_m"] = (
                    self._runtime_target_anchor_evidence.lateral_max_m)
                flythrough_kwargs["runtime_target_exclusive_min_m"] = (
                    self._runtime_target_anchor_evidence.exclusive_lateral_min_m)
                flythrough_kwargs["runtime_target_exclusive_max_m"] = (
                    self._runtime_target_anchor_evidence.exclusive_lateral_max_m)
            if not simulated_clock and not runtime_identity_enabled:
                # Candidate field stopgate: a broad map label is not evidence
                # that the selected magnetic anomaly is the target cable.
                # Widening this bound requires a new multi-source acceptance
                # case, rather than a YAML-only change.
                supplied_width = flythrough_kwargs.get("maximum_side_hint_width_m")
                if supplied_width is not None and float(supplied_width) > 1.0:
                    raise ValueError("non-sim flythrough side hint width cannot exceed 1.0 m")
                flythrough_kwargs["maximum_side_hint_width_m"] = (
                    1.0 if supplied_width is None else supplied_width
                )
                if flythrough_kwargs.get("side_hint_source") != "synthetic_test_fixture":
                    self._static_target_prior_evidence = validate_static_target_prior(
                        dict(v2_mapping.get("static_target_prior", {}) or {}),
                        flythrough_kwargs,
                        dict(self.config.get("prior", {}) or {}),
                        PROJECT_ROOT,
                        mission_config=self.config,
                    )
            if (flythrough_kwargs.get("rejoin_opposed_runin_m") is not None
                    and self._navigation_ground_velocity_frame != "world_ned"):
                raise ValueError("adaptive rejoin requires world_ned navigation ground velocity")
        survey_kwargs = {}
        if mission_geometry == "shallow_survey":
            # This route is an experimental software-chain mode. A physical
            # current sensor and independent target identity source have not
            # been accepted, so a non-sim launch must fail before motion.
            if not bool(self.get_parameter("use_sim_time").value):
                raise ValueError("shallow_survey is simulation-only pending physical evidence acceptance")
            survey_mapping = dict(v2_mapping.get("shallow_survey", {}) or {})
            self._survey_current_topic = str(survey_mapping.pop(
                "current_evidence_topic", "/auv/state/cross_current_evidence"))
            if not self._survey_current_topic.startswith("/"):
                raise ValueError("shallow survey current evidence topic must be absolute")
            survey_kwargs = _dataclass_kwargs(ShallowSurveyMissionConfig, survey_mapping)
            identity_mapping = dict(v2_mapping.get("runtime_identity", {}) or {})
            required = ("sonar_frame_id", "world_frame_id", "calibration_id",
                        "lever_arm_body_xy_m", "yaw_sonar_in_body_deg",
                        "extrinsic_position_sigma_m", "extrinsic_yaw_sigma_deg")
            missing = [key for key in required if key not in identity_mapping]
            if missing:
                raise ValueError("shallow survey identity requires explicit " + ", ".join(missing))
            policy_kwargs = _dataclass_kwargs(SonarIdentityPolicy, identity_mapping)
            policy_kwargs["lever_arm_body_xy_m"] = tuple(policy_kwargs["lever_arm_body_xy_m"])
            self._runtime_identity_policy = SonarIdentityPolicy(**policy_kwargs)
            self._runtime_identity_policy.validate()
            if self._runtime_identity_policy.world_frame_id != self._navigation_world_frame_id:
                raise ValueError("shallow survey identity world frame must match navigation world frame")
            if (self._runtime_identity_policy.maximum_age_s
                    > float(survey_kwargs.get("maximum_identity_age_s", .5))):
                raise ValueError("sonar identity age may not exceed shallow survey cue age")
        extra = (
            {"flythrough_config": FlythroughConfig(**flythrough_kwargs)}
            if mission_geometry == "flythrough" else
            {"survey_config": ShallowSurveyMissionConfig(**survey_kwargs)}
            if mission_geometry == "shallow_survey" else {}
        )
        core = pipeline_type(
            scenario,
            cable_map,
            deployment_config=self._build_deployment_config(DeploymentPerceptionConfig),
            v2_config=v2_config,
            search_boundary_xy_m=boundary,
            initial_position_uncertainty_m=float(v2_mapping.get("initial_position_uncertainty_m", 0.0)),
            **extra,
        )
        hold_budget_mapping = v2_mapping.get("hold_budget")
        hold_budget_config = (None if hold_budget_mapping is None else
                              HoldBudgetConfig.from_mapping(dict(hold_budget_mapping)))
        self._hold_budget = HoldBudgetMonitor(hold_budget_config, boundary)
        route_admission_mapping = dict(v2_mapping.get("route_hold_admission", {}) or {})
        enabled = route_admission_mapping.get("enabled", False)
        if not isinstance(enabled, bool):
            raise ValueError("route_hold_admission.enabled must be boolean")
        self._route_hold_admission_enabled = enabled
        self._route_hold_deviation_bound_m = float(route_admission_mapping.get("route_deviation_bound_m", 0.))
        if (not math.isfinite(self._route_hold_deviation_bound_m)
                or self._route_hold_deviation_bound_m < 0.):
            raise ValueError("route deviation bound must be finite and nonnegative")
        if enabled and (mission_geometry not in {"flythrough", "shallow_survey"}
                        or hold_budget_config is None or boundary is None):
            raise ValueError("route Hold admission requires inspection geometry, hold budget and boundary")
        if mission_geometry == "shallow_survey" and not enabled:
            raise ValueError("shallow survey requires route Hold admission")
        if self._inspection_recoverable_input_stale:
            if (not self._inspection_snapshot_freshness or not enabled
                    or self.pub_setpoint.topic_name != "/auv/control/setpoint_candidate"):
                raise ValueError("recoverable input stale requires snapshot freshness, "
                                 "route Hold admission and candidate-only Setpoint remap")
            self._hold_budget.defer_navigation_unavailable = True
        self._route_hold_admission_result: dict[str, Any] | None = None
        self._rejected_rearm_count = 0
        self._latest_altitude_m: float | None = None
        self._latest_sonar_observation = None
        self._latest_sonar_quality = None
        self._latest_identity_reason = "runtime_identity_cue_unavailable"
        self._latest_nav_uncertainty: tuple[float, float, float] | None = None
        self._latest_nav_uncertainty_wall_time_s = 0.
        self._latest_imu_heading_msg: Imu | None = None
        self._latest_imu_heading_wall_time_s = 0.
        self.pub_lateral_valid = self.create_publisher(Bool, "/auv/cable/lateral_valid", 10)
        self.pub_depth_valid = self.create_publisher(Bool, "/auv/cable/depth_valid", 10)
        self.pub_inspection_status = self.create_publisher(String, "/auv/cable/inspection_status", 10)
        self.pub_recovery_required = self.create_publisher(Bool, "/auv/cable/recovery_required", 10)
        self.pub_hold_budget = self.create_publisher(String, "/auv/cable/hold_budget", 10)
        self._latest_altitude_wall_time_s = 0.0
        self._altitude_timeout_s = float(self.sensor_policy_cfg.get("altitude_timeout_s", 1.5))
        self.pipeline = _RosV2PipelineAdapter(
            core,
            altitude_provider=self._fresh_altitude_m,
        )
        # rclpy's Node.create_subscription() already registers the returned
        # subscription in self._subscriptions. Appending it a second time makes
        # destroy_node() attempt to remove the same waitable twice.
        self.create_subscription(
            Float32,
            str(self.sensor_policy_cfg.get("altitude_topic", "/auv/sensors/altitude")),
            self._on_altitude,
            20,
        )
        self.create_subscription(
            Float32MultiArray, "/auv/state/covariance", self._on_covariance,
            1 if self._inspection_latest_navigation_qos else 10,
        )
        if self._navigation_heading_uncertainty_source == "imu_orientation_covariance":
            self.create_subscription(Imu, "/auv/sensors/imu", self._on_imu_heading, 10)
        if self._runtime_identity_policy is not None:
            identity_mapping = dict(v2_mapping.get("runtime_identity", {}) or {})
            self.create_subscription(
                SonarCableObservation,
                str(identity_mapping.get("observation_topic", "/auv/sensors/cable_sonar_observation")),
                self._on_sonar_observation, 10,
            )
            self.create_subscription(
                PerceptionQuality,
                str(identity_mapping.get("quality_topic", "/auv/perception/quality/sonar")),
                self._on_sonar_quality, 10,
            )
        if self._survey_current_topic is not None:
            self.create_subscription(String, self._survey_current_topic,
                                     self._on_survey_current_evidence, 10)

        # The v2 cross-scan already emits waypoint headings.  Disable the legacy
        # sine overlay so the two trajectory generators cannot be superimposed.
        self.probe_cfg = ZigzagProbeConfig(enabled=False)
        self.recovery_cfg["enabled"] = False
        self.get_logger().info(
            f"cable tracking v2 active: {mission_geometry} Search/Confirm/FWHM/Track pipeline; "
            "legacy sine probe disabled"
        )

    def _on_altitude(self, msg: Float32) -> None:
        value = float(msg.data)
        if math.isfinite(value) and value > 0.01:
            self._latest_altitude_m = value
            self._latest_altitude_wall_time_s = time.monotonic()
        else:
            self._latest_altitude_m = None

    def _on_covariance(self, msg: Float32MultiArray) -> None:
        self._latest_nav_uncertainty = _navigation_uncertainty_from_covariance(msg.data)
        self._latest_nav_uncertainty_wall_time_s = time.monotonic()

    def _on_imu_heading(self, msg: Imu) -> None:
        self._latest_imu_heading_msg = msg
        self._latest_imu_heading_wall_time_s = time.monotonic()

    def _on_sonar_observation(self, msg: SonarCableObservation) -> None:
        self._latest_sonar_observation = msg

    def _on_sonar_quality(self, msg: PerceptionQuality) -> None:
        self._latest_sonar_quality = msg

    def _on_survey_current_evidence(self, msg: String) -> None:
        core = self.pipeline.core
        try:
            payload = json.loads(msg.data)
            if not isinstance(payload, dict) or payload.get("source") != "synthetic_current_fixture":
                raise ValueError("simulation current evidence source required")
            velocity = tuple(float(value) for value in payload["velocity_xy_mps"])
            if len(velocity) != 2:
                raise ValueError("two current components required")
            evidence = SurveyCurrentEvidence(
                time_s=float(payload["time_s"]), velocity_xy_mps=velocity,
                sigma_mps=float(payload["sigma_mps"]),
                source=str(payload["source"]), frame=str(payload.get("frame", "")),
            )
            core.set_current_evidence(evidence)
        except (TypeError, ValueError, KeyError, OverflowError):
            core.set_current_evidence(None)

    def _build_inputs(self):
        navigation, magnetic = super()._build_inputs()
        if navigation is not None and self._navigation_ground_velocity_frame == "world_ned":
            twist = self.latest_odom.twist.twist.linear
            # The localization publisher writes world-NED ground velocity to
            # Odometry.twist. Keep this explicit because generic Odometry
            # publishers may instead use the child/body frame.
            navigation.ground_velocity_frame_valid = (
                self.latest_odom.header.frame_id == self._navigation_world_frame_id
            )
            navigation.ground_velocity_ned_mps = np.array(
                [float(twist.x), float(twist.y), float(twist.z)], dtype=float,
            )
        if (navigation is not None and self._inspection_enabled()
                and (not self.get_parameter("use_sim_time").value
                     or self._runtime_identity_policy is not None)):
            policy = self.pipeline.core.v2_config.inspection
            if (self._latest_nav_uncertainty is None
                    or time.monotonic() - self._latest_nav_uncertainty_wall_time_s > policy.maximum_input_age_s):
                navigation.position_std_m = policy.maximum_navigation_sigma_m + 1.
            else:
                navigation.position_std_m, navigation.heading_std_deg, velocity_sigma = self._latest_nav_uncertainty
                navigation.ground_velocity_std_mps = velocity_sigma
            if self._navigation_heading_uncertainty_source == "imu_orientation_covariance":
                heading_sigma = _matched_imu_heading_sigma_deg(
                    self._latest_imu_heading_msg, self.latest_odom,
                    receipt_age_s=time.monotonic() - self._latest_imu_heading_wall_time_s,
                    maximum_age_s=policy.maximum_input_age_s,
                )
                navigation.heading_std_deg = 180. if heading_sigma is None else heading_sigma
        if self._runtime_identity_policy is not None:
            core = self.pipeline.core
            cue = None
            reason = "runtime_identity_cue_unavailable"
            if (navigation is not None and self.latest_odom is not None
                    and self._latest_sonar_observation is not None
                    and self._latest_sonar_quality is not None):
                cue, reason = sonar_identity_cue(
                    self._latest_sonar_observation, self._latest_sonar_quality,
                    navigation, self.latest_odom,
                    core._survey_origin if self._survey_current_topic is not None else core._fly_origin,
                    core._survey_tangent if self._survey_current_topic is not None else core._fly_tangent,
                    self._runtime_identity_policy,
                )
            core.set_runtime_identity_cue(cue)
            self._latest_identity_reason = reason
        return navigation, magnetic

    def _inspection_enabled(self) -> bool:
        core = getattr(getattr(self, "pipeline", None), "core", None)
        return bool(core is not None and core.v2_config.inspection.enabled)

    def _on_tick(self) -> None:
        if self._inspection_snapshot_freshness and self._inspection_enabled():
            self._tick_snapshot_wall_s = time.monotonic()
            self._tick_snapshot_nav_wall_s = self.latest_odom_wall_time_s
            self._tick_snapshot_cov_wall_s = self._latest_nav_uncertainty_wall_time_s
            self._tick_snapshot_nav_uncertainty = self._latest_nav_uncertainty
            self._tick_snapshot_nav_msg = self.latest_odom
        try:
            return super()._on_tick()
        finally:
            self._tick_snapshot_wall_s = None
            self._tick_snapshot_nav_wall_s = None
            self._tick_snapshot_cov_wall_s = None
            self._tick_snapshot_nav_uncertainty = None
            self._tick_snapshot_nav_msg = None

    def _on_mission_command(self, msg: String) -> None:
        if not self._inspection_enabled():
            return super()._on_mission_command(msg)
        try:
            payload = json.loads(msg.data)
            if not isinstance(payload, dict):
                raise ValueError("mission must be an object")
            for key, default in (("target_depth", 12.0), ("target_speed_mps", 0.8)):
                value = float(payload.get(key, default))
                if not math.isfinite(value) or value < 0:
                    raise ValueError(f"invalid {key}")
        except (ValueError, TypeError, OverflowError) as exc:
            self.get_logger().warning(f"rejected malformed inspection mission: {exc}")
            return
        if str(payload.get("mission_type", "")).upper() not in self.mission_types:
            return super()._on_mission_command(msg)
        if (self._static_target_prior_evidence is not None
                or self._runtime_target_anchor_evidence is not None):
            is_static = self._static_target_prior_evidence is not None
            expected = (self._static_target_prior_evidence if is_static
                        else self._runtime_target_anchor_evidence)
            status_prefix = "STATIC_TARGET_PRIOR" if is_static else "RUNTIME_TARGET_ANCHOR"
            if (str(payload.get("mission_id", "")).strip() != expected.mission_id
                    or str(payload.get("target_id", "")).strip() != expected.target_id):
                self.get_logger().warning(f"inspection mission rejected: {status_prefix} ID mismatch")
                self.pub_inspection_status.publish(String(data=f"{status_prefix}_ID_MISMATCH"))
                return
            controls = dict(self.config.get("control", {}) or {})
            try:
                if any(isinstance(payload[key], bool) or isinstance(controls[config_key], bool)
                       for key, config_key in (("target_depth", "default_depth_m"),
                                               ("target_speed_mps", "default_speed_mps"))):
                    raise ValueError("boolean mission command value")
                depth_m = float(payload["target_depth"])
                speed_mps = float(payload["target_speed_mps"])
                reviewed_depth_m = float(controls["default_depth_m"])
                reviewed_speed_mps = float(controls["default_speed_mps"])
                if (not all(math.isfinite(value) for value in
                            (depth_m, speed_mps, reviewed_depth_m, reviewed_speed_mps))
                        or abs(depth_m - reviewed_depth_m) > 1e-6
                        or abs(speed_mps - reviewed_speed_mps) > 1e-6):
                    raise ValueError("mission command differs from reviewed control defaults")
            except (KeyError, TypeError, ValueError, OverflowError):
                self.get_logger().warning(f"inspection mission rejected: {status_prefix} command mismatch")
                self.pub_inspection_status.publish(String(data=f"{status_prefix}_COMMAND_MISMATCH"))
                return
            if self.latest_mission is None:
                try:
                    validator = (validate_static_target_prior if is_static
                                 else validate_runtime_target_anchor)
                    mapping_key = ("static_target_prior" if is_static
                                   else "runtime_target_anchor")
                    verified = validator(
                        dict(self.config.get("v2", {}).get(mapping_key, {}) or {}),
                        dict(self.config.get("v2", {}).get("flythrough", {}) or {}),
                        dict(self.config.get("prior", {}) or {}), PROJECT_ROOT,
                        mission_config=self.config,
                    )
                except ValueError as exc:
                    self.get_logger().warning(f"inspection mission rejected: {status_prefix} changed or expired: {exc}")
                    self.pub_inspection_status.publish(String(data=f"{status_prefix}_INVALID"))
                    return
                if verified != expected:
                    self.get_logger().warning(f"inspection mission rejected: {status_prefix} changed after startup")
                    self.pub_inspection_status.publish(String(data=f"{status_prefix}_INVALID"))
                    return
        # The autostart injector deliberately repeats the same command on two
        # topics. A retransmission (or a changed speed) must never re-arm a
        # latched safety disposition or a failed flythrough state machine.
        if (self._hold_budget.recovery_required
                or getattr(self.pipeline.core, "_fly_failed", False)
                or getattr(self.pipeline.core, "_survey_failed", False)):
            self._rejected_rearm_count += 1
            self.get_logger().warning("inspection mission rejected: safety disposition requires external review")
            return
        if (self._route_hold_admission_enabled and self.latest_mission is None
                and self._survey_current_topic is None):
            core = self.pipeline.core
            result = self._hold_budget.admit_convex_route(
                [core._fly_start, core._fly_end],
                deviation_bound_m=self._route_hold_deviation_bound_m,
            )
            self._route_hold_admission_result = result
            if not result["admitted"]:
                self._hold_budget.latch(str(result["reason"]))
                self.pub_recovery_required.publish(Bool(data=True))
                self.pub_hold_budget.publish(String(data=json.dumps({
                    **result, "state": "RECOVERY_REQUIRED", "recovery_required": True,
                }, allow_nan=False)))
                self.pub_inspection_status.publish(String(data="RECOVERY_REQUIRED"))
                self.get_logger().warning(f"inspection mission rejected: {result['reason']}")
                return
        super()._on_mission_command(msg)

    def _hold_budget_snapshot(self, mode: str) -> dict[str, Any]:
        position = None
        navigation_age = None
        navigation_sigma = None
        covariance_age = None
        snapshot_active = getattr(self, "_tick_snapshot_wall_s", None) is not None
        reference_wall_s = (self._tick_snapshot_wall_s if snapshot_active else time.monotonic())
        nav_msg = self._tick_snapshot_nav_msg if snapshot_active else self.latest_odom
        nav_wall_s = self._tick_snapshot_nav_wall_s if snapshot_active else self.latest_odom_wall_time_s
        cov_wall_s = self._tick_snapshot_cov_wall_s if snapshot_active else self._latest_nav_uncertainty_wall_time_s
        if nav_msg is not None:
            odom_position = nav_msg.pose.pose.position
            position = (float(odom_position.x), float(odom_position.y))
            navigation_age = max(0., reference_wall_s - nav_wall_s)
        uncertainty = (self._tick_snapshot_nav_uncertainty if snapshot_active
                       else self._latest_nav_uncertainty)
        if uncertainty is not None:
            navigation_sigma = float(uncertainty[0])
            covariance_age = max(0., reference_wall_s - cov_wall_s)
        if self._route_hold_admission_enabled and mode.lower() in ("search", "confirm", "track", "reacquire"):
            inspection_sim_clock = bool(self.get_parameter("use_sim_time").value)
            wall_now_s = time.monotonic()
            return self._hold_budget.evaluate_motion(
                position_xy_m=position, navigation_age_s=navigation_age,
                navigation_sigma_m=navigation_sigma, covariance_age_s=covariance_age,
                now_s=(self.get_clock().now().nanoseconds * 1e-9
                       if inspection_sim_clock else wall_now_s),
                fallback_now_s=wall_now_s if inspection_sim_clock else None,
            )
        wall_now_s = time.monotonic()
        # Every accelerated inspection simulation can move farther than wall
        # time suggests. Count plant time against the Hold budget, and retain
        # wall time as a fallback if /clock stops advancing.
        inspection_sim_clock = bool(self.get_parameter("use_sim_time").value)
        return self._hold_budget.evaluate(
            hold=mode.lower() in ("hold", "sensor_degraded"),
            now_s=(self.get_clock().now().nanoseconds * 1e-9
                   if inspection_sim_clock else wall_now_s),
            fallback_now_s=wall_now_s if inspection_sim_clock else None,
            position_xy_m=position,
            navigation_age_s=navigation_age,
            navigation_sigma_m=navigation_sigma,
            covariance_age_s=covariance_age,
        )

    def _publish_setpoint(self, tracking, guidance, limited, target_depth: float) -> None:
        if not self._inspection_enabled():
            return super()._publish_setpoint(tracking, guidance, limited, target_depth)
        self._check_target_evidence_lifetime()
        if (self._survey_current_topic is not None
                and self._route_hold_admission_enabled
                and self._route_hold_admission_result is None
                and not guidance.safe_lock_active):
            route = self.pipeline.core.declared_route_envelope_points_xy_m()
            result = self._hold_budget.admit_convex_route(
                route, deviation_bound_m=self._route_hold_deviation_bound_m)
            self._route_hold_admission_result = result
            if not result["admitted"]:
                self._hold_budget.latch(str(result["reason"]))
        budget_snapshot = None
        if self._route_hold_admission_enabled:
            budget_snapshot = self._hold_budget_snapshot(str(getattr(tracking, "mode", "")))
        msg = Setpoint()
        msg.header.stamp = self.get_clock().now().to_msg()
        values = [limited.desired_heading_deg, guidance.target_depth_m, limited.speed_mps,
                  *tracking.estimated_cable_xy_m]
        if not np.isfinite(values).all():
            self._publish_degraded_hold_setpoint("nonfinite_command")
            return
        hold = bool(guidance.safe_lock_active or self._hold_budget.recovery_required
                    or (budget_snapshot is not None
                        and budget_snapshot["state"] == "INPUT_STALE_HOLD"))
        if not hold and self._inspection_snapshot_freshness and self._tick_snapshot_nav_msg is not None:
            # In the opt-in two-process path the candidate header identifies
            # the navigation snapshot, not the end of expensive computation.
            msg.header.stamp = self._tick_snapshot_nav_msg.header.stamp
        if hold and self.pipeline.core._last_navigation is None:
            self.get_logger().warning("inspection command withheld: no validated navigation")
            return
        msg.mode = "CABLE_TRACKING_DEGRADED_HOLD" if hold else "CABLE_TRACKING"
        msg.bridge_backend = str(self.control_cfg.get("bridge_backend", "protocol_udp"))
        msg.control_mode_byte = int(self.control_cfg.get("control_mode_byte", 0xEE))
        msg.target_depth_m = float(guidance.target_depth_m)
        msg.target_heading_rad = math.radians(float(guidance.desired_heading_deg if hold else limited.desired_heading_deg))
        msg.target_speed_mps = 0.0 if hold else max(0.0, min(
            float(limited.speed_mps), float(guidance.speed_mps),
            self.pipeline.core.v2_config.inspection.maximum_guidance_speed_mps,
        ))
        msg.track_cable = not hold
        # Explicit waypoint guidance must not become a second sine trajectory.
        msg.sine_amplitude = 0.0
        msg.sine_period_s = 0.0
        msg.high_priority = hold or bool(self.control_cfg.get("high_priority", False))
        msg.note = ("v2_hold_budget:" + str(self._hold_budget.reason)
                    if self._hold_budget.recovery_required else str(guidance.guidance_source))
        msg.target_x_m, msg.target_y_m = map(float, tracking.estimated_cable_xy_m)
        self.pub_setpoint.publish(msg)
        self._publish_count += 1

    def _publish_degraded_hold_setpoint(self, reason: str) -> None:
        if not self._inspection_enabled():
            return super()._publish_degraded_hold_setpoint(reason)
        core = self.pipeline.core
        nav = core._last_navigation
        if nav is None:
            # No trustworthy pose exists yet. Do not manufacture a depth or
            # heading command; the controller's input watchdog owns this case.
            self.get_logger().warning("inspection hold awaits first valid navigation: " + reason)
            return
        tracking = core._hold_output(reason)
        guidance = SimpleNamespace(safe_lock_active=True, target_depth_m=abs(float(nav.position_ned_m[2])),
                                   desired_heading_deg=float(nav.heading_deg), speed_mps=0.0,
                                   guidance_source="v2_sensor_hold:" + reason)
        self._publish_setpoint(tracking, guidance, guidance, guidance.target_depth_m)

    def _publish_tracking(self, tracking, guidance, limited) -> None:
        if self._inspection_enabled():
            self._check_target_evidence_lifetime()
            tracking.diagnostics["hold_budget"] = self._hold_budget_snapshot(tracking.mode)
            if self._route_hold_admission_result is not None:
                tracking.diagnostics["route_hold_admission"] = self._route_hold_admission_result
        if self._runtime_identity_policy is not None:
            cue = self.pipeline.core._runtime_identity_cue
            tracking.diagnostics["runtime_identity_reason"] = self._latest_identity_reason
            tracking.diagnostics["runtime_identity_center_m"] = (
                None if cue is None else cue.lateral_center_m
            )
            tracking.diagnostics["runtime_identity_half_width_m"] = (
                None if cue is None else cue.half_width_m
            )
        super()._publish_tracking(tracking, guidance, limited)

    def _check_target_evidence_lifetime(self) -> None:
        evidence = self._static_target_prior_evidence
        if evidence is not None and not evidence.currently_valid():
            self._hold_budget.latch("static_target_prior_expired")
        anchor = self._runtime_target_anchor_evidence
        if anchor is not None and not anchor.currently_valid():
            self._hold_budget.latch("runtime_target_anchor_expired")

    def _acceptance_flags(self, tracking) -> list[str]:
        flags = super()._acceptance_flags(tracking)
        if self._hold_budget.recovery_required:
            flags.append("hold_budget_recovery_required")
        return flags

    def _publish_cable_monitor_topics(self, payload) -> None:
        super()._publish_cable_monitor_topics(payload)
        if self._inspection_enabled():
            budget = self._hold_budget_snapshot(str(payload.get("mode", "")))
            self.pub_recovery_required.publish(Bool(data=budget["recovery_required"]))
            self.pub_hold_budget.publish(String(data=json.dumps(budget, allow_nan=False)))
        diagnostics = payload.get("diagnostics") or {}
        lateral = bool(diagnostics.get("lateral_valid", False))
        depth = bool(diagnostics.get("depth_valid", False))
        self.pub_lateral_valid.publish(Bool(data=lateral))
        self.pub_depth_valid.publish(Bool(data=depth))
        status = "LOCALIZED_WITH_DEPTH" if lateral and depth else (
            "LOCALIZED_DEPTH_PENDING" if lateral else "LOCALIZATION_PENDING"
        )
        if self._inspection_enabled():
            if self._hold_budget.recovery_required:
                status = "RECOVERY_REQUIRED"
            elif str(payload.get("mode", "")).lower() == "hold":
                status = "HOLD"
            elif str(payload.get("mode", "")).lower() == "sensor_degraded":
                status = "SENSOR_DEGRADED"
        self.pub_inspection_status.publish(String(data=status))

    def _fresh_altitude_m(self) -> float | None:
        if self._latest_altitude_m is None:
            return None
        if time.monotonic() - self._latest_altitude_wall_time_s > self._altitude_timeout_s:
            return None
        return self._latest_altitude_m


def main() -> None:
    rclpy.init()
    node = CableTrackingV2Node()
    try:
        rclpy.spin(node)
    except ExternalShutdownException:
        pass
    except Exception:
        if rclpy.ok():
            raise
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()

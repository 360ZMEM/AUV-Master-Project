#!/usr/bin/env python3
"""ROS2 adapter that calls AUV-Master-Mag and publishes cable-tracking setpoints."""

from __future__ import annotations

from collections import deque
import json
import math
import os
from pathlib import Path
from typing import Any

import numpy as np
from nav_msgs.msg import Odometry
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import MagneticField
from std_msgs.msg import Bool, Float32, String
import yaml

from auv_interfaces.msg import ArbiterStatus, Setpoint

from .cable_guidance_limits import GuidanceLimitConfig, ZigzagProbeConfig, apply_zigzag_probe, limit_guidance, wrap_deg
from .cable_prior_adapter import ensure_auv_master_mag_on_path, load_cable_map_from_config


def _find_project_root() -> Path:
    candidates = []
    env_root = os.environ.get("AUV_PROJECT_ROOT")
    if env_root:
        candidates.append(Path(env_root))
    candidates.append(Path.cwd())
    candidates.extend(Path(__file__).resolve().parents)
    for candidate in candidates:
        if (candidate / "AUV-Master-Mag").exists() and (candidate / "brain_linux").exists():
            return candidate
    return Path.cwd()


PROJECT_ROOT = _find_project_root()


def _json_safe(value):
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, np.floating):
        numeric = float(value)
        return numeric if math.isfinite(numeric) else None
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.ndarray):
        return [_json_safe(item) for item in value.tolist()]
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def _yaw_from_odom(msg: Odometry) -> float:
    q = msg.pose.pose.orientation
    return math.atan2(
        2.0 * (q.w * q.z + q.x * q.y),
        1.0 - 2.0 * (q.y * q.y + q.z * q.z),
    )


class CableTrackingNode(Node):
    def __init__(self) -> None:
        super().__init__("auv_cable_tracking_node")
        self.declare_parameter("config_file", str(PROJECT_ROOT / "brain_linux/config/cable_tracking.yaml"))
        self.declare_parameter("enabled", True)

        self.config = self._load_config()
        self.enabled = bool(self.get_parameter("enabled").value) and bool(self.config.get("enabled", True))
        ensure_auv_master_mag_on_path(PROJECT_ROOT, self.config.get("auv_master_mag_root", "AUV-Master-Mag"))
        from auv_mag_tracking.api import (
            AuvMagTrackingPipeline,
            DeploymentPerceptionConfig,
            MagneticInput,
            NavigationInput,
            SonarInput,
        )
        from auv_mag_tracking.config import build_default_scenarios

        self._magnetic_input_cls = MagneticInput
        self._navigation_input_cls = NavigationInput
        self._sonar_input_cls = SonarInput

        cable_map = load_cable_map_from_config(self.config, project_root=PROJECT_ROOT)
        scenarios = build_default_scenarios()
        scenario_name = str(self.config.get("scenario_name", "case1"))
        scenario = scenarios.get(scenario_name, next(iter(scenarios.values())))
        self._apply_scenario_overrides(scenario, self.config.get("scenario_overrides", {}) or {})
        self.quality_cfg = dict(self.config.get("quality", {}) or {})
        self.acceptance_cfg = dict(self.config.get("acceptance", {}) or {})
        self.pipeline = AuvMagTrackingPipeline(
            scenario,
            cable_map,
            deployment_config=self._build_deployment_config(DeploymentPerceptionConfig),
        )

        self.mission_types = set(self.config.get("mission_types", ["CABLE_TRACKING", "CABLE_INSPECTION"]))
        self.control_cfg = dict(self.config.get("control", {}) or {})
        self.recovery_cfg = dict(self.config.get("recovery_guidance", {}) or {})
        self.mag_cfg = dict(self.config.get("magnetic", {}) or {})
        self.limit_cfg = GuidanceLimitConfig.from_mapping(self.config.get("zigzag_limits", {}) or {})
        self.probe_cfg = ZigzagProbeConfig.from_mapping(self.config.get("zigzag_probe", {}) or {})
        self.mag_block: deque[list[float]] = deque(maxlen=max(1, int(self.mag_cfg.get("block_size", 8))))
        self.latest_odom: Odometry | None = None
        self.latest_mission: dict[str, Any] | None = None
        self.latest_arbiter: ArbiterStatus | None = None
        self._missing_input_logged = False
        self._publish_count = 0
        self._recovery_guidance_active = False
        self._recovery_guidance_streak = 0
        self._inspection_hold_active = False
        self._inspection_hold_streak = 0

        self.pub_setpoint = self.create_publisher(Setpoint, "/auv/control/setpoint", 10)
        self.pub_tracking = self.create_publisher(String, "/auv/cable/tracking", 10)
        self.pub_diagnostics = self.create_publisher(String, "/auv/cable/diagnostics", 10)
        self.pub_cable_industrial_ready = self.create_publisher(Bool, "/auv/cable/industrial_ready", 10)
        self.pub_cable_mode = self.create_publisher(String, "/auv/cable/mode", 10)
        self.pub_cable_acceptance_flags = self.create_publisher(String, "/auv/cable/acceptance_flags", 10)
        self.pub_cable_status_text = self.create_publisher(String, "/auv/cable/status_text", 10)
        self.pub_cable_cross_track = self.create_publisher(Float32, "/auv/cable/cross_track_m", 10)
        self.pub_cable_route_progress = self.create_publisher(Float32, "/auv/cable/route_progress_m", 10)
        self.pub_cable_burial_depth = self.create_publisher(Float32, "/auv/cable/burial_depth_m", 10)
        self.pub_cable_burial_sigma = self.create_publisher(Float32, "/auv/cable/burial_sigma_m", 10)
        self.pub_cable_confidence = self.create_publisher(Float32, "/auv/cable/confidence", 10)
        self.pub_cable_magnetic_snr = self.create_publisher(Float32, "/auv/cable/magnetic_snr_db", 10)
        self.pub_cable_magnetic_confidence = self.create_publisher(Float32, "/auv/cable/magnetic_confidence", 10)
        self.pub_cable_dlt1278_summary = self.create_publisher(String, "/auv/cable/dlt1278_summary", 10)
        self.pub_cable_dlt1278_state = self.create_publisher(String, "/auv/cable/dlt1278_state", 10)
        self.pub_cable_dlt1278_score = self.create_publisher(Float32, "/auv/cable/dlt1278_total_score", 10)
        self.pub_cable_industrial_acceptance_pass = self.create_publisher(
            Bool, "/auv/cable/industrial_acceptance_pass", 10
        )

        self._subscriptions = [
            self.create_subscription(Odometry, "/auv/state/filtered", self._on_odom, 10),
            self.create_subscription(MagneticField, "/auv/sensors/magnetic", self._on_magnetic, 50),
            self.create_subscription(String, "/auv/mission_command", self._on_mission_command, 10),
            self.create_subscription(String, "/auv/cable/mission_command", self._on_mission_command, 10),
            self.create_subscription(ArbiterStatus, "/auv/arbiter/status", self._on_arbiter_status, 10),
        ]
        self.timer = self.create_timer(0.1, self._on_tick)
        self.get_logger().info(
            f"cable tracking node ready: enabled={self.enabled} mission_types={sorted(self.mission_types)}"
        )
        self.get_logger().info(
            "cable tracking quality config "
            f"confidence_min_ready={self.quality_cfg.get('confidence_min_ready', 0.65)} "
            f"route_offset_ready_m={self.quality_cfg.get('route_offset_ready_m', 2.0)}"
        )
        self.get_logger().info(
            "cable zigzag probe config "
            f"enabled={self.probe_cfg.enabled} amplitude_m={self.probe_cfg.lateral_amplitude_m:.2f} "
            f"wavelength_m={self.probe_cfg.wavelength_m:.2f}"
        )
        if bool(self.recovery_cfg.get("enabled", False)):
            self.get_logger().info(
                "cable recovery guidance enabled "
                f"enter_abs_cross_track_m={self.recovery_cfg.get('enter_abs_cross_track_m', 3.0)} "
                f"exit_abs_cross_track_m={self.recovery_cfg.get('exit_abs_cross_track_m', 1.0)} "
                f"max_correction_deg={self.recovery_cfg.get('max_correction_deg', 55.0)}"
            )

    def _build_deployment_config(self, config_cls):
        fields = getattr(config_cls, "__dataclass_fields__", {})
        kwargs = {name: self.quality_cfg[name] for name in fields if name in self.quality_cfg}
        return config_cls(**kwargs)

    def _load_config(self) -> dict[str, Any]:
        config_file = Path(str(self.get_parameter("config_file").value))
        if not config_file.is_absolute():
            config_file = PROJECT_ROOT / config_file
        if not config_file.exists():
            self.get_logger().warning(f"cable tracking config not found, using defaults: {config_file}")
            return {}
        payload = yaml.safe_load(config_file.read_text(encoding="utf-8")) or {}
        return dict(payload.get("cable_tracking", payload) or {})

    def _apply_scenario_overrides(self, scenario, overrides: dict[str, Any]) -> None:
        """Apply explicit experiment-only overrides to AUV-Master-Mag scenario config."""
        if not isinstance(overrides, dict):
            return
        for section_name in ("tracking", "vehicle"):
            section = getattr(scenario, section_name, None)
            values = overrides.get(section_name, {}) or {}
            if section is None or not isinstance(values, dict):
                continue
            for key, value in values.items():
                if hasattr(section, str(key)):
                    setattr(section, str(key), value)

    def _on_odom(self, msg: Odometry) -> None:
        self.latest_odom = msg

    def _on_magnetic(self, msg: MagneticField) -> None:
        self.mag_block.append([
            float(msg.magnetic_field.x) * 1.0e9,
            float(msg.magnetic_field.y) * 1.0e9,
            float(msg.magnetic_field.z) * 1.0e9,
        ])

    def _on_mission_command(self, msg: String) -> None:
        try:
            payload = json.loads(msg.data)
        except json.JSONDecodeError as exc:
            self.get_logger().warning(f"invalid mission command JSON: {exc}")
            return
        if str(payload.get("mission_type", "")).upper() in self.mission_types:
            self.latest_mission = payload
            self.get_logger().info(f"cable mission accepted: {payload.get('mission_type')}")
        else:
            self.get_logger().warning(f"ignored non-cable mission command: {payload.get('mission_type')}")

    def _on_arbiter_status(self, msg: ArbiterStatus) -> None:
        self.latest_arbiter = msg

    def _build_inputs(self):
        if self.latest_odom is None or not self.mag_block:
            return None, None
        odom = self.latest_odom
        pos = odom.pose.pose.position
        yaw_rad = _yaw_from_odom(odom)
        speed = math.sqrt(
            float(odom.twist.twist.linear.x) ** 2
            + float(odom.twist.twist.linear.y) ** 2
            + float(odom.twist.twist.linear.z) ** 2
        )
        nav = self._navigation_input_cls(
            time_s=float(self.get_clock().now().nanoseconds) * 1.0e-9,
            position_ned_m=np.array([float(pos.x), float(pos.y), float(pos.z)], dtype=float),
            heading_deg=math.degrees(yaw_rad),
            speed_mps=speed,
            source="ros2_state_filtered",
        )
        mag = self._magnetic_input_cls(
            time_s=nav.time_s,
            sample_block_nt=np.asarray(self.mag_block, dtype=float),
            sample_rate_hz=float(self.mag_cfg.get("sample_rate_hz", 50.0)),
            sensor_frame=str(self.mag_cfg.get("sensor_frame", "mag_link")),
        )
        return nav, mag

    def _on_tick(self) -> None:
        if not self.enabled or self.latest_mission is None:
            return
        nav, mag = self._build_inputs()
        if nav is None or mag is None:
            if not self._missing_input_logged:
                self.get_logger().warning(
                    "cable tracking waiting for inputs "
                    f"has_odom={self.latest_odom is not None} mag_samples={len(self.mag_block)}"
                )
                self._missing_input_logged = True
            self._publish_diag({"ready": False, "reason": "missing_navigation_or_magnetic"})
            return
        self._missing_input_logged = False

        target_depth = float(self.latest_mission.get("target_depth", self.control_cfg.get("default_depth_m", 12.0)))
        requested_speed = float(self.latest_mission.get("target_speed_mps", self.control_cfg.get("default_speed_mps", 0.8)))
        requested_speed = float(np.clip(
            requested_speed,
            float(self.control_cfg.get("min_speed_mps", 0.3)),
            float(self.control_cfg.get("max_speed_mps", 1.1)),
        ))
        tracking, guidance = self.pipeline.step_with_guidance(
            nav,
            mag,
            target_depth_m=target_depth,
            speed_mps=requested_speed,
        )
        recovery_active = self._apply_recovery_guidance(tracking, guidance)
        inspection_hold_active = self._update_inspection_hold(tracking)
        if (
            (recovery_active and bool(self.recovery_cfg.get("disable_zigzag", True)))
            or inspection_hold_active
        ):
            guidance.zigzag_width_m = 0.0
            guidance.diagnostics.update(
                {
                    "zigzag_probe_active": False,
                    "zigzag_probe_suppressed_by_recovery": recovery_active,
                    "zigzag_probe_suppressed_by_inspection_hold": inspection_hold_active,
                    "zigzag_probe_lateral_amplitude_m": 0.0,
                    "zigzag_probe_wavelength_m": self.probe_cfg.wavelength_m,
                    "zigzag_probe_phase_rad": 0.0,
                    "zigzag_probe_heading_bias_deg": 0.0,
                    "zigzag_probe_required_peak_heading_deg": 0.0,
                    "zigzag_probe_required_min_turn_radius_m": float("inf"),
                    "zigzag_probe_required_peak_lateral_speed_mps": 0.0,
                    "zigzag_probe_dynamics_feasible": True,
                    "zigzag_probe_feasibility_reasons": [],
                }
            )
        else:
            probe = apply_zigzag_probe(
                base_heading_deg=guidance.desired_heading_deg,
                route_progress_m=tracking.route_progress_m,
                speed_mps=guidance.speed_mps,
                probe_config=self.probe_cfg,
                limit_config=self.limit_cfg,
            )
            guidance.desired_heading_deg = probe.desired_heading_deg
            guidance.zigzag_width_m = probe.requested_lateral_amplitude_m
            guidance.diagnostics.update(
                {
                    "zigzag_probe_active": probe.active,
                    "zigzag_probe_suppressed_by_recovery": False,
                    "zigzag_probe_suppressed_by_inspection_hold": False,
                    "zigzag_probe_lateral_amplitude_m": probe.requested_lateral_amplitude_m,
                    "zigzag_probe_wavelength_m": probe.wavelength_m,
                    "zigzag_probe_phase_rad": probe.phase_rad,
                    "zigzag_probe_heading_bias_deg": probe.heading_bias_deg,
                    "zigzag_probe_required_peak_heading_deg": probe.required_peak_heading_deg,
                    "zigzag_probe_required_min_turn_radius_m": probe.required_min_turn_radius_m,
                    "zigzag_probe_required_peak_lateral_speed_mps": probe.required_peak_lateral_speed_mps,
                    "zigzag_probe_dynamics_feasible": probe.dynamics_feasible,
                    "zigzag_probe_feasibility_reasons": list(probe.feasibility_reasons),
                }
            )
        limited = limit_guidance(
            desired_heading_deg=guidance.desired_heading_deg,
            current_heading_deg=nav.heading_deg,
            speed_mps=guidance.speed_mps,
            config=self.limit_cfg,
        )
        if bool(self.control_cfg.get("publish_setpoint", True)):
            self._publish_setpoint(tracking, guidance, limited, target_depth)
        self._publish_tracking(tracking, guidance, limited)

    def _publish_setpoint(self, tracking, guidance, limited, target_depth: float) -> None:
        msg = Setpoint()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.mode = "CABLE_TRACKING"
        msg.bridge_backend = "protocol_udp"
        msg.control_mode_byte = int(self.control_cfg.get("control_mode_byte", 0xEE))
        msg.target_depth_m = float(target_depth)
        msg.target_heading_rad = math.radians(float(limited.desired_heading_deg))
        msg.target_speed_mps = float(limited.speed_mps)
        msg.track_cable = True
        msg.sine_amplitude = float(guidance.zigzag_width_m)
        msg.sine_period_s = float(self.control_cfg.get("sine_period_s", 0.0))
        msg.high_priority = bool(self.control_cfg.get("high_priority", False))
        msg.note = "AUV-Master-Mag cable tracking"
        msg.target_x_m = float(tracking.estimated_cable_xy_m[0])
        msg.target_y_m = float(tracking.estimated_cable_xy_m[1])
        self.pub_setpoint.publish(msg)
        self._publish_count += 1
        if self._publish_count == 1 or self._publish_count % 50 == 0:
            self.get_logger().info(
                "published cable tracking setpoint "
                f"count={self._publish_count} heading_deg={limited.desired_heading_deg:.2f} "
                f"depth_m={target_depth:.2f} speed_mps={limited.speed_mps:.2f}"
            )

    def _publish_tracking(self, tracking, guidance, limited) -> None:
        quality_flags = list(tracking.diagnostics.get("quality_flags", []) or [])
        acceptance_flags = self._acceptance_flags(tracking)
        industrial_ready = bool(tracking.diagnostics.get("industrial_ready", False)) and not acceptance_flags
        dlt1278 = self._build_dlt1278_runtime_summary(
            tracking=tracking,
            acceptance_flags=acceptance_flags,
            quality_flags=quality_flags,
            industrial_ready=industrial_ready,
        )
        payload = {
            "time_s": tracking.time_s,
            "estimated_cable_xy_m": tracking.estimated_cable_xy_m.tolist(),
            "cross_track_m": tracking.cross_track_m,
            "route_progress_m": tracking.route_progress_m,
            "cable_heading_deg": tracking.cable_heading_deg,
            "burial_depth_m": tracking.burial_depth_m,
            "burial_sigma_m": tracking.burial_sigma_m,
            "confidence": tracking.confidence,
            "mode": tracking.mode,
            "magnetic_strength_nt": tracking.diagnostics.get("magnetic_strength_nt"),
            "magnetic_snr_db": tracking.diagnostics.get("magnetic_snr_db"),
            "magnetic_confidence": tracking.diagnostics.get("magnetic_confidence"),
            "fit_residual_m": tracking.diagnostics.get("fit_residual_m"),
            "prior_alignment_residual_m": tracking.diagnostics.get("prior_alignment_residual_m"),
            "burial_fit_quality": tracking.diagnostics.get("burial_fit_quality"),
            "burial_sample_count": tracking.diagnostics.get("burial_sample_count"),
            "quality_flags": quality_flags,
            "acceptance_flags": acceptance_flags,
            "industrial_ready": industrial_ready,
            "industrial_acceptance_pass": industrial_ready,
            "dlt1278": dlt1278,
            "guidance": {
                "desired_heading_deg": limited.desired_heading_deg,
                "raw_desired_heading_deg": guidance.desired_heading_deg,
                "speed_mps": limited.speed_mps,
                "yaw_rate_deg_s": limited.yaw_rate_deg_s,
                "commanded_turn_radius_m": limited.commanded_turn_radius_m,
            },
            "diagnostics": {
                **tracking.diagnostics,
                **guidance.diagnostics,
                "zigzag_limited": limited.zigzag_limited,
                "limit_reason": ",".join(limited.limit_reasons),
                "acceptance_flags": acceptance_flags,
                "industrial_ready": industrial_ready,
                "industrial_acceptance_pass": industrial_ready,
                "dlt1278_state": dlt1278["state"],
                "dlt1278_total_score": dlt1278["total_score"],
            },
        }
        text = json.dumps(_json_safe(payload), ensure_ascii=False, allow_nan=False)
        self.pub_tracking.publish(String(data=text))
        self._publish_cable_monitor_topics(payload)
        self._publish_diag(payload["diagnostics"])

    def _publish_cable_monitor_topics(self, payload: dict[str, Any]) -> None:
        """Publish short typed fields for Foxglove and console monitoring.

        The raw /auv/cable/tracking message stays as a long JSON string for
        full-fidelity logging. These derived topics expose the high-value
        acceptance fields as std_msgs types so Foxglove can plot/indicator them
        without parsing String.data.
        """
        acceptance_flags = list(payload.get("acceptance_flags", []) or [])
        self.pub_cable_industrial_ready.publish(Bool(data=bool(payload.get("industrial_ready", False))))
        self.pub_cable_industrial_acceptance_pass.publish(
            Bool(data=bool(payload.get("industrial_acceptance_pass", False)))
        )
        self.pub_cable_mode.publish(String(data=str(payload.get("mode", "--"))))
        self.pub_cable_acceptance_flags.publish(String(data="none" if not acceptance_flags else ",".join(acceptance_flags)))

        numeric_publishers = {
            "cross_track_m": self.pub_cable_cross_track,
            "route_progress_m": self.pub_cable_route_progress,
            "burial_depth_m": self.pub_cable_burial_depth,
            "burial_sigma_m": self.pub_cable_burial_sigma,
            "confidence": self.pub_cable_confidence,
            "magnetic_snr_db": self.pub_cable_magnetic_snr,
            "magnetic_confidence": self.pub_cable_magnetic_confidence,
        }
        for key, publisher in numeric_publishers.items():
            value = payload.get(key)
            if value is None:
                continue
            try:
                numeric = float(value)
            except (TypeError, ValueError):
                continue
            if math.isfinite(numeric):
                publisher.publish(Float32(data=numeric))

        status_text = self._build_cable_status_text(payload, acceptance_flags)
        self.pub_cable_status_text.publish(String(data=status_text))
        dlt1278 = payload.get("dlt1278")
        if isinstance(dlt1278, dict):
            self.pub_cable_dlt1278_state.publish(String(data=str(dlt1278.get("state", "无效数据"))))
            self.pub_cable_dlt1278_score.publish(Float32(data=float(dlt1278.get("total_score", 0.0) or 0.0)))
            self.pub_cable_dlt1278_summary.publish(String(data=self._build_dlt1278_summary_text(dlt1278)))

    def _build_cable_status_text(self, payload: dict[str, Any], acceptance_flags: list[str]) -> str:
        def _fmt(value: Any, digits: int = 2) -> str:
            if value is None:
                return "--"
            try:
                numeric = float(value)
            except (TypeError, ValueError):
                return str(value)
            if not math.isfinite(numeric):
                return "--"
            return f"{numeric:.{digits}f}"

        ready = "READY" if bool(payload.get("industrial_ready", False)) else "NOT READY"
        flags = "none" if not acceptance_flags else ",".join(acceptance_flags)
        return (
            f"{ready} | mode={payload.get('mode', '--')} | flags={flags}\n"
            f"cross={_fmt(payload.get('cross_track_m'))} m | progress={_fmt(payload.get('route_progress_m'), 1)} m\n"
            f"burial={_fmt(payload.get('burial_depth_m'))} m | sigma={_fmt(payload.get('burial_sigma_m'), 3)} m\n"
            f"conf={_fmt(payload.get('confidence'), 3)} | "
            f"snr={_fmt(payload.get('magnetic_snr_db'), 1)} dB | "
            f"mag_conf={_fmt(payload.get('magnetic_confidence'), 3)}"
        )

    def _build_dlt1278_runtime_summary(
        self,
        *,
        tracking,
        acceptance_flags: list[str],
        quality_flags: list[str],
        industrial_ready: bool,
    ) -> dict[str, Any]:
        """Build a lightweight DL/T 1278-style runtime status summary.

        The full scoring/report generator still owns final experiment artifacts.
        Runtime scoring mirrors the currently implemented report items so
        Foxglove and the console can show the same interpretation while running.
        """
        burial_target = float(self.acceptance_cfg.get("burial_target_m", 1.5))
        route_target = float(self.acceptance_cfg.get("max_route_offset_m", 2.0))
        accuracy_target = float(self.acceptance_cfg.get("max_burial_sigma_m", 0.15))

        score_items: list[dict[str, Any]] = []
        if abs(float(tracking.cross_track_m)) > route_target:
            score_items.append({"item": "海缆位移", "level": "II", "base_score": 4, "weight": 2, "score": 8})
        if tracking.burial_depth_m is not None and float(tracking.burial_depth_m) < burial_target:
            score_items.append({"item": "海缆埋深不足", "level": "III", "base_score": 8, "weight": 2, "score": 16})
        if tracking.burial_sigma_m is not None and float(tracking.burial_sigma_m) > accuracy_target:
            score_items.append({"item": f"埋深估计精度未达 {accuracy_target:.2f}m", "level": "II", "base_score": 4, "weight": 2, "score": 8})

        total_score = sum(int(item["score"]) for item in score_items)
        worst_single = max([int(item["score"]) for item in score_items], default=0)
        if worst_single >= 30:
            state = "严重状态"
        elif worst_single >= 20:
            state = "异常状态"
        elif total_score > 30 or worst_single >= 12:
            state = "注意状态"
        else:
            state = "正常状态"

        output_products = [
            "tracking.jsonl",
            "inspection_summary.json",
            "dlt1278_report.md",
            "cable_ops_points.csv",
            "burial_profile.csv",
            "route_deviation.csv",
            "figures/*.png",
            "operator_view/*.png",
        ]
        return {
            "standard": "DL/T 1278-style",
            "runtime_scope": "实时样本摘要；最终结论以离线报告为准",
            "state": state,
            "total_score": total_score,
            "worst_single_score": worst_single,
            "score_items": score_items,
            "industrial_conclusion_readiness": "ready" if industrial_ready else "limited",
            "industrial_acceptance_pass": bool(industrial_ready),
            "acceptance_flags": list(acceptance_flags),
            "quality_flags": list(quality_flags),
            "thresholds": {
                "burial_target_m": burial_target,
                "route_offset_target_m": route_target,
                "burial_accuracy_target_m": accuracy_target,
            },
            "output_products": output_products,
        }

    def _build_dlt1278_summary_text(self, summary: dict[str, Any]) -> str:
        items = summary.get("score_items") or []
        if items:
            item_text = "；".join(
                f"{item.get('item', '--')}({item.get('level', '--')}, {item.get('score', 0)}分)"
                for item in items
            )
        else:
            item_text = "无实时扣分项"
        flags = summary.get("acceptance_flags") or []
        flag_text = "none" if not flags else ",".join(str(item) for item in flags)
        products = ", ".join(str(item) for item in (summary.get("output_products") or [])[:4])
        return (
            f"DL/T 1278风格状态: {summary.get('state', '无效数据')} | "
            f"总分: {int(summary.get('total_score', 0) or 0)} | "
            f"ready: {summary.get('industrial_conclusion_readiness', '--')} | "
            f"pass: {bool(summary.get('industrial_acceptance_pass', False))}\n"
            f"扣分项: {item_text}\n"
            f"验收标志: {flag_text}\n"
            f"产物链: {products} ..."
        )

    def _acceptance_flags(self, tracking) -> list[str]:
        flags = []
        max_offset = float(self.acceptance_cfg.get("max_route_offset_m", 2.0))
        min_confidence = float(self.acceptance_cfg.get("min_confidence", 0.65))
        max_burial_sigma = float(self.acceptance_cfg.get("max_burial_sigma_m", 0.15))
        if abs(float(tracking.cross_track_m)) > max_offset:
            flags.append("route_offset_over_limit")
        if float(tracking.confidence) < min_confidence:
            flags.append("confidence_below_limit")
        if tracking.burial_sigma_m is None:
            flags.append("burial_uncertainty_missing")
        elif float(tracking.burial_sigma_m) > max_burial_sigma:
            flags.append("burial_uncertainty_over_limit")
        return flags

    def _publish_diag(self, payload: dict[str, Any]) -> None:
        self.pub_diagnostics.publish(String(data=json.dumps(_json_safe(payload), ensure_ascii=False, allow_nan=False)))

    def _update_inspection_hold(self, tracking) -> bool:
        cfg = dict(self.config.get("inspection_hold", {}) or {})
        if not bool(cfg.get("enabled", False)):
            self._inspection_hold_active = False
            self._inspection_hold_streak = 0
            return False
        enter_cross_track = float(cfg.get("enter_abs_cross_track_m", 2.0))
        consecutive_required = max(1, int(cfg.get("enter_consecutive_samples", 20)))
        abs_cross_track = abs(float(tracking.cross_track_m))
        burial_ready = tracking.burial_sigma_m is not None
        if abs_cross_track <= enter_cross_track and burial_ready:
            self._inspection_hold_streak += 1
        else:
            self._inspection_hold_streak = 0
        if self._inspection_hold_streak >= consecutive_required:
            self._inspection_hold_active = True
        tracking.diagnostics.update(
            {
                "inspection_hold_enabled": True,
                "inspection_hold_active": self._inspection_hold_active,
                "inspection_hold_streak": self._inspection_hold_streak,
                "inspection_hold_enter_abs_cross_track_m": enter_cross_track,
                "inspection_hold_enter_consecutive_samples": consecutive_required,
            }
        )
        return self._inspection_hold_active

    def _apply_recovery_guidance(self, tracking, guidance) -> bool:
        """Temporarily prioritize line reacquisition before DL/T inspection."""
        if not bool(self.recovery_cfg.get("enabled", False)):
            self._recovery_guidance_active = False
            self._recovery_guidance_streak = 0
            guidance.diagnostics.update(
                {
                    "recovery_guidance_enabled": False,
                    "recovery_guidance_active": False,
                    "recovery_guidance_streak": 0,
                }
            )
            return False

        signed_cross_track = tracking.diagnostics.get("signed_cross_track_m")
        if signed_cross_track is None:
            signed_cross_track = tracking.diagnostics.get("prior_alignment_prior_cross_track_m")
        try:
            signed_cross_track = float(signed_cross_track)
        except (TypeError, ValueError):
            signed_cross_track = float(tracking.cross_track_m)
        abs_cross_track = abs(signed_cross_track)

        enter = float(self.recovery_cfg.get("enter_abs_cross_track_m", 3.0))
        exit_threshold = float(self.recovery_cfg.get("exit_abs_cross_track_m", 1.0))
        exit_streak_required = max(1, int(self.recovery_cfg.get("exit_consecutive_samples", 30)))
        if abs_cross_track <= exit_threshold:
            self._recovery_guidance_streak += 1
        else:
            self._recovery_guidance_streak = 0

        if self._recovery_guidance_active:
            if self._recovery_guidance_streak >= exit_streak_required:
                self._recovery_guidance_active = False
        elif abs_cross_track >= enter:
            self._recovery_guidance_active = True
            self._recovery_guidance_streak = 0

        raw_heading_correction = float(guidance.diagnostics.get("heading_correction_deg", 0.0) or 0.0)
        cable_heading_deg = wrap_deg(float(guidance.desired_heading_deg) - raw_heading_correction)
        applied_correction = raw_heading_correction
        if self._recovery_guidance_active:
            gain = float(self.recovery_cfg.get("gain_deg_per_m", 6.0))
            max_correction = float(self.recovery_cfg.get("max_correction_deg", 55.0))
            applied_correction = float(np.clip(-gain * signed_cross_track, -max_correction, max_correction))
            guidance.desired_heading_deg = wrap_deg(cable_heading_deg + applied_correction)
            if "speed_mps" in self.recovery_cfg:
                guidance.speed_mps = float(
                    np.clip(
                        float(self.recovery_cfg["speed_mps"]),
                        float(self.control_cfg.get("min_speed_mps", 0.3)),
                        float(self.control_cfg.get("max_speed_mps", 1.1)),
                    )
                )

        guidance.diagnostics.update(
            {
                "recovery_guidance_enabled": True,
                "recovery_guidance_active": self._recovery_guidance_active,
                "recovery_guidance_streak": self._recovery_guidance_streak,
                "recovery_guidance_enter_abs_cross_track_m": enter,
                "recovery_guidance_exit_abs_cross_track_m": exit_threshold,
                "recovery_guidance_exit_consecutive_samples": exit_streak_required,
                "recovery_guidance_abs_cross_track_m": abs_cross_track,
                "recovery_guidance_signed_cross_track_m": signed_cross_track,
                "recovery_guidance_cable_heading_deg": cable_heading_deg,
                "recovery_guidance_heading_correction_deg": applied_correction,
            }
        )
        return self._recovery_guidance_active


def main() -> None:
    rclpy.init()
    node = CableTrackingNode()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()

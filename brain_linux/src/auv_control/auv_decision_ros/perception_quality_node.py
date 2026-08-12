#!/usr/bin/env python3
"""Shadow ROS adapter for source-specific cable perception quality."""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from std_msgs.msg import String

from auv_interfaces.msg import (
    MagneticSampleBlock,
    PerceptionQuality,
    SonarCableObservation,
)

from .perception_quality import (
    MagneticQualityEstimator,
    QualityEstimate,
    SonarQualityEstimator,
    SourceCalibration,
)


def _stamp_seconds(stamp) -> float:
    return float(stamp.sec) + float(stamp.nanosec) * 1.0e-9


def _json_safe(value):
    """Recursively map non-finite diagnostics to JSON null."""
    if isinstance(value, np.ndarray):
        return [_json_safe(item) for item in value.tolist()]
    if isinstance(value, np.generic):
        return _json_safe(value.item())
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


class PerceptionQualityNode(Node):
    def __init__(self) -> None:
        super().__init__("perception_quality_node")
        self.declare_parameter(
            "magnetic_block_topic",
            "/auv/sensors/magnetic_block",
        )
        self.declare_parameter(
            "sonar_observation_topic",
            "/auv/sensors/cable_sonar_observation",
        )
        self.declare_parameter("target_frequency_hz", 45.0)
        self.declare_parameter("minimum_target_cycles", 8.0)
        self.declare_parameter("maximum_age_s", 0.5)
        self.declare_parameter("cross_track_tolerance_m", 2.0)
        self.declare_parameter("magnetic_calibration_file", "")
        self.declare_parameter("sonar_calibration_file", "")
        self.declare_parameter("calibration_domain", "physical")
        self.declare_parameter("magnetic_geometry_context_enabled", False)
        self.declare_parameter("cable_heading_rad", 0.0)
        self.declare_parameter("vertical_separation_m", 0.0)

        max_age_s = float(self.get_parameter("maximum_age_s").value)
        tolerance_m = float(self.get_parameter("cross_track_tolerance_m").value)
        self.calibration_domain = str(
            self.get_parameter("calibration_domain").value
        ).strip()
        self.magnetic_estimator = MagneticQualityEstimator(
            target_frequency_hz=float(
                self.get_parameter("target_frequency_hz").value
            ),
            min_cycles=float(
                self.get_parameter("minimum_target_cycles").value
            ),
            max_age_s=max_age_s,
            cross_track_tolerance_m=tolerance_m,
            calibration=self._load_calibration("magnetic_calibration_file"),
        )
        self.sonar_estimator = SonarQualityEstimator(
            max_age_s=max_age_s,
            cross_track_tolerance_m=tolerance_m,
            calibration=self._load_calibration("sonar_calibration_file"),
        )
        self.cable_heading_rad = float(
            self.get_parameter("cable_heading_rad").value
        )
        self.vertical_separation_m = float(
            self.get_parameter("vertical_separation_m").value
        )
        self.magnetic_geometry_context_enabled = bool(
            self.get_parameter("magnetic_geometry_context_enabled").value
        )
        self.mag_quality_pub = self.create_publisher(
            PerceptionQuality,
            "/auv/perception/quality/magnetic",
            10,
        )
        self.sonar_quality_pub = self.create_publisher(
            PerceptionQuality,
            "/auv/perception/quality/sonar",
            10,
        )
        self.diagnostics_pub = self.create_publisher(
            String,
            "/auv/perception/quality/diagnostics",
            10,
        )
        self.create_subscription(
            MagneticSampleBlock,
            str(self.get_parameter("magnetic_block_topic").value),
            self._on_magnetic_block,
            5,
        )
        self.create_subscription(
            SonarCableObservation,
            str(self.get_parameter("sonar_observation_topic").value),
            self._on_sonar_observation,
            10,
        )
        self.get_logger().info(
            "perception quality shadow node ready; outputs do not drive BT or MPC"
        )

    def _load_calibration(self, parameter_name: str) -> SourceCalibration | None:
        value = str(self.get_parameter(parameter_name).value).strip()
        if not value:
            return None
        path = Path(value).expanduser()
        if not path.is_absolute() and not path.exists():
            try:
                from ament_index_python.packages import (
                    get_package_share_directory,
                )

                path = (
                    Path(get_package_share_directory("auv_decision_ros"))
                    / "config"
                    / path
                )
            except Exception:
                pass
        try:
            calibration = SourceCalibration.from_json(path)
        except Exception as exc:
            self.get_logger().error(
                f"failed to load {parameter_name}={path}: {exc}"
            )
            return None
        self.get_logger().info(
            f"loaded {parameter_name}: {calibration.calibration_id} "
            f"domain={calibration.calibration_domain}"
        )
        if calibration.calibration_domain != self.calibration_domain:
            self.get_logger().error(
                f"{parameter_name} domain mismatch: "
                f"expected={self.calibration_domain} "
                f"actual={calibration.calibration_domain}; disabled"
            )
            return None
        if not calibration.deployment_approved:
            self.get_logger().warning(
                f"{parameter_name} is fit-only; probabilities remain disabled"
            )
        return calibration

    def _on_magnetic_block(self, msg: MagneticSampleBlock) -> None:
        count = min(
            int(msg.sample_count),
            len(msg.time_offset_s),
            len(msg.x_nt),
            len(msg.y_nt),
            len(msg.z_nt),
        )
        stamp_s = _stamp_seconds(msg.header.stamp)
        now_s = float(self.get_clock().now().nanoseconds) * 1.0e-9
        times = stamp_s + np.asarray(msg.time_offset_s[:count], dtype=float)
        samples = np.column_stack(
            (
                np.asarray(msg.x_nt[:count], dtype=float),
                np.asarray(msg.y_nt[:count], dtype=float),
                np.asarray(msg.z_nt[:count], dtype=float),
            )
        )
        heading = (
            self.cable_heading_rad
            if self.magnetic_geometry_context_enabled
            else None
        )
        separation = (
            self.vertical_separation_m
            if self.magnetic_geometry_context_enabled
            else None
        )
        reasons = []
        if count != int(msg.sample_count):
            reasons.append("array_length_mismatch")
        if msg.status and msg.status not in {"采集中", "acquiring"}:
            reasons.append("device_status_not_acquiring")
        if not msg.sample_clock_verified:
            reasons.append("sample_clock_unverified")
        estimate = self.magnetic_estimator.evaluate(
            samples_nt=samples,
            time_s=times,
            age_s=max(now_s - stamp_s, 0.0),
            data_completeness=float(msg.data_completeness),
            clipping_ratio=float(msg.clipping_ratio),
            calibration_valid=bool(msg.calibration_valid),
            cable_heading_rad=heading,
            vertical_separation_m=separation,
            external_reasons=reasons,
        )
        self._publish(
            estimate,
            msg.header,
            self.mag_quality_pub,
        )

    def _on_sonar_observation(self, msg: SonarCableObservation) -> None:
        count = min(len(msg.point_x_m), len(msg.point_y_m))
        points = np.column_stack(
            (
                np.asarray(msg.point_x_m[:count], dtype=float),
                np.asarray(msg.point_y_m[:count], dtype=float),
            )
        )
        weights = None
        reasons = list(msg.quality_flags)
        if msg.point_weight:
            weights = np.asarray(msg.point_weight, dtype=float)
            if weights.size != count:
                reasons.append("array_length_mismatch")
        if not msg.valid:
            reasons.append("detector_invalid")
        stamp_s = _stamp_seconds(msg.header.stamp)
        now_s = float(self.get_clock().now().nanoseconds) * 1.0e-9
        estimate = self.sonar_estimator.evaluate(
            points_body_m=points,
            point_weight=weights,
            detector_score=float(msg.detector_score),
            contrast_to_noise_ratio=float(msg.contrast_to_noise_ratio),
            visible_length_m=float(msg.visible_length_m),
            ambiguity_margin=float(msg.ambiguity_margin),
            field_of_view_truncated=bool(msg.field_of_view_truncated),
            age_s=max(now_s - stamp_s, 0.0),
            external_reasons=reasons,
        )
        self._publish(
            estimate,
            msg.header,
            self.sonar_quality_pub,
        )

    def _publish(self, estimate: QualityEstimate, header, publisher) -> None:
        msg = PerceptionQuality()
        msg.header = header
        msg.source = estimate.source
        msg.validity = int(estimate.validity)
        msg.reason_codes = list(estimate.reason_codes)
        msg.detection_score = float(estimate.detection_score)
        msg.p_detect = float(estimate.p_detect)
        msg.p_track = float(estimate.p_track)
        msg.detection_probability_calibrated = bool(
            estimate.detection_probability_calibrated
        )
        msg.track_probability_calibrated = bool(
            estimate.track_probability_calibrated
        )
        msg.estimate = np.asarray(estimate.estimate, dtype=float).tolist()
        msg.covariance = np.asarray(
            estimate.covariance,
            dtype=float,
        ).reshape(-1).tolist()
        msg.age_s = float(estimate.age_s)
        msg.sample_count = int(estimate.sample_count)
        msg.data_completeness = float(estimate.data_completeness)
        msg.calibration_id = str(estimate.calibration_id)
        publisher.publish(msg)
        payload = {
            "source": estimate.source,
            "validity": estimate.validity,
            "reason_codes": list(estimate.reason_codes),
            "detection_score": estimate.detection_score,
            "p_detect": estimate.p_detect
            if math.isfinite(estimate.p_detect)
            else None,
            "p_track": estimate.p_track
            if math.isfinite(estimate.p_track)
            else None,
            "detection_probability_calibrated": (
                estimate.detection_probability_calibrated
            ),
            "track_probability_calibrated": (
                estimate.track_probability_calibrated
            ),
            "estimate": [
                value if math.isfinite(value) else None
                for value in np.asarray(estimate.estimate, dtype=float)
            ],
            "diagnostics": _json_safe(estimate.diagnostics),
        }
        self.diagnostics_pub.publish(
            String(data=json.dumps(payload, allow_nan=False))
        )


def main(args: list[str] | None = None) -> None:
    rclpy.init(args=args)
    node = PerceptionQualityNode()
    try:
        rclpy.spin(node)
    except ExternalShutdownException:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()

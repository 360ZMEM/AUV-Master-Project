#!/usr/bin/env python3
"""P5 cable tracking authority publisher, hard-wired to shadow mode."""

from __future__ import annotations

import json
import time

import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from std_msgs.msg import String

from auv_interfaces.msg import CableTrackingAuthority, PerceptionQuality

from .sensor_runtime import capability_available
from .tracking_authority import QualitySignal, TrackingAuthorityMachine


class TrackingAuthorityNode(Node):
    def __init__(self) -> None:
        super().__init__("tracking_authority_shadow_node")
        self.declare_parameter("maximum_age_s", 0.75)
        self.declare_parameter("track_enter_probability", 0.75)
        self.declare_parameter("track_exit_probability", 0.55)
        self.declare_parameter("search_enter_probability", 0.55)
        self.declare_parameter("search_exit_probability", 0.35)
        self.declare_parameter("enter_debounce_count", 3)
        self.declare_parameter("exit_debounce_count", 5)
        self.declare_parameter("publish_rate_hz", 5.0)
        self.declare_parameter("runtime_status_topic", "/auv/sensors/runtime_status")
        self.declare_parameter("required_capability", "")
        self.declare_parameter("calibration_domain", "physical")
        self.declare_parameter(
            "output_topic",
            "/auv/perception/cable_tracking_authority_shadow",
        )

        self.machine = TrackingAuthorityMachine(
            maximum_age_s=float(
                self.get_parameter("maximum_age_s").value
            ),
            track_enter_probability=float(
                self.get_parameter("track_enter_probability").value
            ),
            track_exit_probability=float(
                self.get_parameter("track_exit_probability").value
            ),
            search_enter_probability=float(
                self.get_parameter("search_enter_probability").value
            ),
            search_exit_probability=float(
                self.get_parameter("search_exit_probability").value
            ),
            enter_debounce_count=int(
                self.get_parameter("enter_debounce_count").value
            ),
            exit_debounce_count=int(
                self.get_parameter("exit_debounce_count").value
            ),
        )
        self.required_capability = str(
            self.get_parameter("required_capability").value
        ).strip()
        self.calibration_domain = str(
            self.get_parameter("calibration_domain").value
        ).strip()
        self._quality: dict[str, tuple[PerceptionQuality, float]] = {}
        self._runtime_status: dict | None = None
        self.publisher = self.create_publisher(
            CableTrackingAuthority,
            str(self.get_parameter("output_topic").value),
            10,
        )
        self.create_subscription(
            PerceptionQuality,
            "/auv/perception/quality/magnetic",
            self._on_quality,
            10,
        )
        self.create_subscription(
            PerceptionQuality,
            "/auv/perception/quality/sonar",
            self._on_quality,
            10,
        )
        self.create_subscription(
            String,
            str(self.get_parameter("runtime_status_topic").value),
            self._on_runtime_status,
            10,
        )
        publish_rate_hz = max(
            float(self.get_parameter("publish_rate_hz").value),
            0.2,
        )
        self.create_timer(1.0 / publish_rate_hz, self._on_timer)
        self.get_logger().info(
            "P5 tracking authority ready in mandatory shadow mode "
            f"domain={self.calibration_domain}"
        )

    def _on_quality(self, msg: PerceptionQuality) -> None:
        self._quality[str(msg.source)] = (msg, time.monotonic())

    def _on_runtime_status(self, msg: String) -> None:
        try:
            payload = json.loads(msg.data)
        except json.JSONDecodeError:
            return
        if isinstance(payload, dict):
            self._runtime_status = payload

    def _on_timer(self) -> None:
        now_s = time.monotonic()
        signals = []
        for source, (msg, received_s) in self._quality.items():
            signals.append(
                QualitySignal(
                    source=source,
                    validity=int(msg.validity),
                    p_detect=float(msg.p_detect),
                    p_track=float(msg.p_track),
                    detection_calibrated=bool(
                        msg.detection_probability_calibrated
                    ),
                    track_calibrated=bool(
                        msg.track_probability_calibrated
                    ),
                    age_s=max(
                        float(msg.age_s) + now_s - received_s,
                        0.0,
                    ),
                )
            )
        runtime_ok = capability_available(
            self._runtime_status,
            self.required_capability,
        )
        decision = self.machine.update(
            signals,
            runtime_sensor_health_ok=runtime_ok,
        )
        msg = CableTrackingAuthority()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = "auv/base_link"
        msg.mode = int(decision.mode)
        msg.sensor_health_ok = bool(decision.sensor_health_ok)
        msg.detection_authorized = bool(decision.detection_authorized)
        msg.tracking_authorized = bool(decision.tracking_authorized)
        msg.p_detect = float(decision.p_detect)
        msg.p_track = float(decision.p_track)
        msg.contributing_sources = list(decision.contributing_sources)
        msg.reason_codes = list(decision.reason_codes)
        msg.calibration_domain = self.calibration_domain
        msg.shadow_only = True
        self.publisher.publish(msg)


def main(args: list[str] | None = None) -> None:
    rclpy.init(args=args)
    node = TrackingAuthorityNode()
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

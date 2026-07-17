#!/usr/bin/env python3
"""Jetson-side forward sonar wrapper skeleton.

Current terrain-following control consumes /auv/sensors/forward_sonar_slope, so
this wrapper normalizes vendor output to that contract. Raw range publication is
optional and can be extended per device.
"""

from __future__ import annotations

import math
from typing import Any

import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from std_msgs.msg import Float32


class ForwardSonarWrapperNode(Node):
    def __init__(self) -> None:
        super().__init__("forward_sonar_wrapper_node")
        self.declare_parameter("slope_topic", "/auv/sensors/forward_sonar_slope")
        self.declare_parameter("range_topic", "/auv/sensors/forward_sonar_range_m")
        self.declare_parameter("publish_rate_hz", 20.0)
        self.declare_parameter("device_uri", "TODO://configure-device-uri")
        self.declare_parameter("publish_range", True)
        self.declare_parameter("mock_mode", False)
        self.declare_parameter("mock_slope", 0.05)
        self.declare_parameter("mock_range_m", 8.0)

        self.slope_topic = str(self.get_parameter("slope_topic").value)
        self.range_topic = str(self.get_parameter("range_topic").value)
        self.publish_rate_hz = float(self.get_parameter("publish_rate_hz").value)
        self.device_uri = str(self.get_parameter("device_uri").value)
        self.publish_range = bool(self.get_parameter("publish_range").value)
        self.mock_mode = bool(self.get_parameter("mock_mode").value)
        self.mock_slope = float(self.get_parameter("mock_slope").value)
        self.mock_range_m = float(self.get_parameter("mock_range_m").value)

        self.slope_pub = self.create_publisher(Float32, self.slope_topic, 10)
        self.range_pub = self.create_publisher(Float32, self.range_topic, 10) if self.publish_range else None
        self.timer = self.create_timer(1.0 / max(self.publish_rate_hz, 1.0e-3), self._on_timer)
        self._warn_count = 0
        self.get_logger().info(
            f"forward sonar wrapper skeleton ready slope_topic={self.slope_topic} device_uri={self.device_uri}"
        )

    def _on_timer(self) -> None:
        if not rclpy.ok():
            return

        sample = self.read_device_sample()
        if sample is None:
            self._warn_count += 1
            if self._warn_count == 1 or self._warn_count % 100 == 0:
                self.get_logger().warning(
                    "forward sonar wrapper skeleton is running without device samples; "
                    "implement read_device_sample()/decode_device_sample() for the target sensor"
                )
            return

        decoded = self.decode_device_sample(sample)
        if decoded is None:
            return

        try:
            slope = float(decoded["slope"])
        except (KeyError, TypeError, ValueError):
            self.get_logger().warning("forward sonar wrapper dropped sample without numeric slope field")
            return
        if not math.isfinite(slope):
            self.get_logger().warning("forward sonar wrapper dropped non-finite slope")
            return
        try:
            self.slope_pub.publish(Float32(data=slope))
        except Exception:
            if not rclpy.ok():
                return
            raise

        if self.range_pub is not None and "range_m" in decoded:
            try:
                range_m = float(decoded["range_m"])
            except (TypeError, ValueError):
                return
            if math.isfinite(range_m):
                try:
                    self.range_pub.publish(Float32(data=range_m))
                except Exception:
                    if not rclpy.ok():
                        return
                    raise

    def read_device_sample(self) -> Any | None:
        """Read a raw vendor packet.

        Override for the concrete sonar transport (UDP/serial/SDK).
        """
        if self.mock_mode:
            return {"slope": self.mock_slope, "range_m": self.mock_range_m}
        return None

    def decode_device_sample(self, raw: Any) -> dict[str, Any] | None:
        """Decode the vendor packet.

        Expected output:
            {"slope": <float>, "range_m": <optional float>}
        """
        if isinstance(raw, dict):
            return raw
        return None

##
# @brief Run the forward sonar wrapper node until the ROS context stops.
# @param args Optional ROS CLI arguments.
def main(args: list[str] | None = None) -> None:
    rclpy.init(args=args)
    node = ForwardSonarWrapperNode()
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

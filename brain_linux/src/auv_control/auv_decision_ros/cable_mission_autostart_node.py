#!/usr/bin/env python3
"""Publish a cable-tracking mission command for reproducible full-flow runs."""

from __future__ import annotations

import json

import rclpy
from rclpy.node import Node
from std_msgs.msg import String


class CableMissionAutostartNode(Node):
    """Timed mission injector for cable tracking experiments.

    The node is intentionally small and launch-gated.  It does not own mission
    state; it only publishes the same JSON payload that operators previously
    sent manually to ``/auv/mission_command``.
    """

    def __init__(self) -> None:
        super().__init__("auv_cable_mission_autostart_node")
        self.declare_parameter("mission_type", "CABLE_TRACKING")
        self.declare_parameter("target_depth", 12.0)
        self.declare_parameter("target_speed_mps", 0.8)
        self.declare_parameter("start_delay_s", 8.0)
        self.declare_parameter("publish_duration_s", 30.0)
        self.declare_parameter("publish_rate_hz", 2.0)
        self.declare_parameter("publish_general_mission", True)
        self.declare_parameter("publish_cable_mission", True)

        self.mission_type = str(self.get_parameter("mission_type").value).upper()
        self.target_depth = float(self.get_parameter("target_depth").value)
        self.target_speed_mps = float(self.get_parameter("target_speed_mps").value)
        self.start_delay_s = max(0.0, float(self.get_parameter("start_delay_s").value))
        self.publish_duration_s = max(0.0, float(self.get_parameter("publish_duration_s").value))
        self.publish_rate_hz = max(0.1, float(self.get_parameter("publish_rate_hz").value))
        self.publish_general_mission = bool(self.get_parameter("publish_general_mission").value)
        self.publish_cable_mission = bool(self.get_parameter("publish_cable_mission").value)

        self.publisher = self.create_publisher(String, "/auv/mission_command", 10)
        self.cable_publisher = self.create_publisher(String, "/auv/cable/mission_command", 10)
        self.start_time_s = float(self.get_clock().now().nanoseconds) * 1.0e-9
        self.sent_count = 0
        self._done_logged = False
        self.timer = self.create_timer(1.0 / self.publish_rate_hz, self._on_timer)
        self.get_logger().info(
            "cable mission autostart ready "
            f"type={self.mission_type} depth={self.target_depth:.2f}m "
            f"speed={self.target_speed_mps:.2f}m/s delay={self.start_delay_s:.1f}s "
            f"duration={self.publish_duration_s:.1f}s rate={self.publish_rate_hz:.1f}Hz "
            f"general={self.publish_general_mission} cable={self.publish_cable_mission}"
        )

    def _on_timer(self) -> None:
        now_s = float(self.get_clock().now().nanoseconds) * 1.0e-9
        elapsed_s = now_s - self.start_time_s
        if elapsed_s < self.start_delay_s:
            return
        if elapsed_s > self.start_delay_s + self.publish_duration_s:
            if not self._done_logged:
                self.get_logger().info(f"cable mission autostart complete sent={self.sent_count}")
                self._done_logged = True
            return

        payload = {
            "mission_type": self.mission_type,
            "target_depth": self.target_depth,
            "target_speed_mps": self.target_speed_mps,
            "source": "cable_mission_autostart_node",
        }
        msg = String(data=json.dumps(payload, ensure_ascii=False))
        if self.publish_general_mission:
            self.publisher.publish(msg)
        if self.publish_cable_mission:
            self.cable_publisher.publish(msg)
        self.sent_count += 1
        if self.sent_count == 1 or self.sent_count % max(1, int(self.publish_rate_hz * 5.0)) == 0:
            self.get_logger().info(
                "published cable mission autostart "
                f"count={self.sent_count} type={self.mission_type}"
            )


def main() -> None:
    rclpy.init()
    node = CableMissionAutostartNode()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()

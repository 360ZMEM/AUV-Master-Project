#!/usr/bin/env python3
"""Jetson-side sensor supervisor.

The supervisor watches topic freshness for multiple sensors and derives
mission-level capabilities. A single sensor loss should only degrade the
capabilities that depend on it instead of collapsing the whole stack.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import time
from typing import Any, Callable

from geometry_msgs.msg import TwistStamped
from nav_msgs.msg import Odometry
import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from sensor_msgs.msg import Imu, MagneticField
from std_msgs.msg import Float32, String
import yaml

from .sensor_runtime import SensorWatch, build_runtime_status_snapshot


def _find_project_root() -> Path:
    candidates = []
    env_root = os.environ.get("AUV_PROJECT_ROOT")
    if env_root:
        candidates.append(Path(env_root))
    candidates.append(Path.cwd())
    candidates.extend(Path(__file__).resolve().parents)
    for candidate in candidates:
        if (candidate / "brain_linux").exists():
            return candidate
    return Path.cwd()


PROJECT_ROOT = _find_project_root()


SUPPORTED_MSG_TYPES: dict[str, type] = {
    "nav_msgs/msg/Odometry": Odometry,
    "sensor_msgs/msg/MagneticField": MagneticField,
    "sensor_msgs/msg/Imu": Imu,
    "geometry_msgs/msg/TwistStamped": TwistStamped,
    "std_msgs/msg/Float32": Float32,
    "std_msgs/msg/String": String,
}


class SensorSupervisorNode(Node):
    def __init__(self) -> None:
        super().__init__("sensor_supervisor_node")
        self.declare_parameter(
            "config_file",
            str(PROJECT_ROOT / "brain_linux/config/sensor_supervisor.yaml"),
        )
        self.declare_parameter("enabled", True)

        self.enabled = bool(self.get_parameter("enabled").value)
        self.config = self._load_config()
        self.publish_rate_hz = float(self.config.get("publish_rate_hz", 2.0))
        self.status_topic = str(self.config.get("status_topic", "/auv/sensors/runtime_status"))
        self.capability_requirements = {
            str(key): [str(item) for item in value]
            for key, value in dict(self.config.get("capabilities", {}) or {}).items()
        }
        self.watches = self._build_watches(self.config.get("sensors", []) or [])
        self.status_pub = self.create_publisher(String, self.status_topic, 10)
        self._last_sensor_health: dict[str, bool] = {}
        self._last_capability_health: dict[str, bool] = {}

        for watch in self.watches.values():
            msg_type = SUPPORTED_MSG_TYPES.get(watch.msg_type)
            if msg_type is None:
                watch.last_error = f"unsupported_msg_type:{watch.msg_type}"
                self.get_logger().warning(
                    f"sensor supervisor skipped {watch.name}: unsupported msg_type={watch.msg_type}"
                )
                continue
            self.create_subscription(msg_type, watch.topic, self._make_rx_callback(watch.name), 20)

        self.timer = self.create_timer(1.0 / max(self.publish_rate_hz, 1.0e-3), self._on_timer)
        self.get_logger().info(
            "sensor supervisor ready "
            f"enabled={self.enabled} watches={sorted(self.watches.keys())} status_topic={self.status_topic}"
        )

    def _load_config(self) -> dict[str, Any]:
        config_file = Path(str(self.get_parameter("config_file").value))
        if not config_file.is_absolute():
            config_file = PROJECT_ROOT / config_file
        if not config_file.exists():
            self.get_logger().warning(f"sensor supervisor config not found, using defaults: {config_file}")
            return {}
        payload = yaml.safe_load(config_file.read_text(encoding="utf-8")) or {}
        return dict(payload.get("sensor_supervisor", payload) or {})

    def _build_watches(self, items: list[dict[str, Any]]) -> dict[str, SensorWatch]:
        watches: dict[str, SensorWatch] = {}
        for raw in items:
            if not isinstance(raw, dict):
                continue
            name = str(raw.get("name", "")).strip()
            if not name:
                continue
            watches[name] = SensorWatch(
                name=name,
                topic=str(raw.get("topic", "")),
                msg_type=str(raw.get("msg_type", "")),
                timeout_s=float(raw.get("timeout_s", 0.5)),
                capabilities=[str(item) for item in (raw.get("capabilities", []) or [])],
                required=bool(raw.get("required", False)),
                description=str(raw.get("description", "")),
            )
        return watches

    def _make_rx_callback(self, watch_name: str) -> Callable[[Any], None]:
        def _callback(msg: Any) -> None:
            del msg
            watch = self.watches[watch_name]
            watch.last_rx_monotonic_s = time.monotonic()
            watch.message_count += 1
            watch.last_error = None

        return _callback

    def _on_timer(self) -> None:
        if not self.enabled:
            return
        now_s = time.monotonic()
        payload = build_runtime_status_snapshot(
            self.watches,
            self.capability_requirements,
            now_s=now_s,
        )
        payload["time_s"] = time.time()
        self._log_transitions(payload)
        self.status_pub.publish(String(data=json.dumps(payload, ensure_ascii=False, allow_nan=False)))

    def _log_transitions(self, payload: dict[str, Any]) -> None:
        sensors = dict(payload.get("sensors", {}) or {})
        for name, data in sensors.items():
            healthy = bool(data.get("healthy", False))
            previous = self._last_sensor_health.get(name)
            if previous is None or previous == healthy:
                self._last_sensor_health[name] = healthy
                continue
            self._last_sensor_health[name] = healthy
            level = "info" if healthy else "warning"
            getattr(self.get_logger(), level)(
                f"sensor {name} health changed -> {healthy} "
                f"topic={data.get('topic')} age_s={data.get('age_s')} timeout_s={data.get('timeout_s')}"
            )

        capabilities = dict(payload.get("capabilities", {}) or {})
        for name, data in capabilities.items():
            available = bool(data.get("available", False))
            previous = self._last_capability_health.get(name)
            if previous is None or previous == available:
                self._last_capability_health[name] = available
                continue
            self._last_capability_health[name] = available
            level = "info" if available else "warning"
            getattr(self.get_logger(), level)(
                f"capability {name} changed -> {available} missing={data.get('missing_sensors', [])}"
            )

##
# @brief Run the sensor supervisor node until the ROS context stops.
# @param args Optional ROS CLI arguments.
def main(args: list[str] | None = None) -> None:
    rclpy.init(args=args)
    node = SensorSupervisorNode()
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

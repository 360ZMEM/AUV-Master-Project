#!/usr/bin/env python3
"""Standalone kinematics and magnetic-field source for cable-tracking closure.

This node intentionally stays outside the PVS/HoloOcean backends.  It consumes
the production cable-tracking setpoint, integrates a small unicycle model, and
publishes the same deployment-facing ROS topics a real vehicle would provide:
filtered odometry, raw magnetic field, and mission command.
"""

from __future__ import annotations

from collections import deque
import json
import math
import os
from pathlib import Path
import sys
from typing import Any

import numpy as np
from geometry_msgs.msg import Point, Quaternion
from nav_msgs.msg import Odometry
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import MagneticField
from std_msgs.msg import String
from visualization_msgs.msg import Marker
import yaml

from auv_interfaces.msg import Setpoint

from .cable_prior_adapter import ensure_auv_master_mag_on_path, load_cable_map_from_config


def _find_project_root() -> Path:
    candidates: list[Path] = []
    env_root = os.environ.get("AUV_PROJECT_ROOT")
    if env_root:
        candidates.append(Path(env_root))
    candidates.append(Path.cwd())
    candidates.extend(Path(__file__).resolve().parents)
    for candidate in candidates:
        if (candidate / "AUV-Master-Mag").exists() and (candidate / "sim_holoocean").exists():
            return candidate
    return Path.cwd()


PROJECT_ROOT = _find_project_root()
SIM_INTERFACES = PROJECT_ROOT / "sim_holoocean" / "interfaces"
if str(SIM_INTERFACES) not in sys.path:
    sys.path.insert(0, str(SIM_INTERFACES))

from perception_engine import CablePath, compute_biot_savart_hvdc  # noqa: E402


def _wrap_angle_rad(angle: float) -> float:
    return (float(angle) + math.pi) % (2.0 * math.pi) - math.pi


def _yaw_quaternion(yaw_rad: float) -> Quaternion:
    q = Quaternion()
    q.w = math.cos(0.5 * yaw_rad)
    q.z = math.sin(0.5 * yaw_rad)
    return q


def _load_tracking_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return dict(payload.get("cable_tracking", payload) or {})


class DecoupledCableSimNode(Node):
    """Close the ROS cable-tracking loop without a PVS/HoloOcean dynamics backend."""

    def __init__(self) -> None:
        super().__init__("auv_decoupled_cable_sim_node")
        self.declare_parameter(
            "tracking_config_file",
            str(PROJECT_ROOT / "brain_linux/config/cable_tracking_direction_a.yaml"),
        )
        self.declare_parameter("frame_id", "local_ned")
        self.declare_parameter("base_link_frame_id", "base_link")
        self.declare_parameter("mag_frame_id", "mag_link")
        self.declare_parameter("initial_x_m", 0.0)
        self.declare_parameter("initial_y_m", 7.5)
        self.declare_parameter("initial_depth_m", 12.0)
        self.declare_parameter("initial_heading_deg", 0.0)
        self.declare_parameter("default_speed_mps", 0.0)
        self.declare_parameter("max_yaw_rate_deg_s", 12.0)
        self.declare_parameter("depth_time_constant_s", 4.0)
        self.declare_parameter("state_rate_hz", 50.0)
        self.declare_parameter("mag_rate_hz", 50.0)
        self.declare_parameter("marker_rate_hz", 2.0)
        self.declare_parameter("mission_rate_hz", 1.0)
        self.declare_parameter("mission_type", "CABLE_TRACKING")
        self.declare_parameter("target_depth_m", 12.0)
        self.declare_parameter("target_speed_mps", 0.8)
        self.declare_parameter("publish_general_mission", True)
        self.declare_parameter("publish_cable_mission", True)
        self.declare_parameter("true_cable_y_m", 0.0)
        self.declare_parameter("true_cable_start_x_m", -80.0)
        self.declare_parameter("true_cable_end_x_m", 180.0)
        self.declare_parameter("true_cable_segment_m", 5.0)
        self.declare_parameter("vertical_separation_m", 7.5)
        self.declare_parameter("current_amp_a", 600.0)
        self.declare_parameter("trail_max_points", 1200)

        tracking_config_file = Path(str(self.get_parameter("tracking_config_file").value))
        if not tracking_config_file.is_absolute():
            tracking_config_file = PROJECT_ROOT / tracking_config_file
        self.tracking_config_file = tracking_config_file
        self.tracking_config = _load_tracking_config(tracking_config_file)
        ensure_auv_master_mag_on_path(
            PROJECT_ROOT,
            self.tracking_config.get("auv_master_mag_root", "AUV-Master-Mag"),
        )

        self.frame_id = str(self.get_parameter("frame_id").value)
        self.base_link_frame_id = str(self.get_parameter("base_link_frame_id").value)
        self.mag_frame_id = str(self.get_parameter("mag_frame_id").value)
        self.target_depth_m = float(self.get_parameter("target_depth_m").value)
        self.target_speed_mps = float(self.get_parameter("target_speed_mps").value)
        self.max_yaw_rate_rad_s = math.radians(float(self.get_parameter("max_yaw_rate_deg_s").value))
        self.depth_time_constant_s = max(0.05, float(self.get_parameter("depth_time_constant_s").value))
        self.current_amp_a = float(self.get_parameter("current_amp_a").value)
        self.trail: deque[np.ndarray] = deque(maxlen=max(2, int(self.get_parameter("trail_max_points").value)))

        self.position_ned = np.array(
            [
                float(self.get_parameter("initial_x_m").value),
                float(self.get_parameter("initial_y_m").value),
                float(self.get_parameter("initial_depth_m").value),
            ],
            dtype=float,
        )
        self.heading_rad = math.radians(float(self.get_parameter("initial_heading_deg").value))
        self.speed_mps = float(self.get_parameter("default_speed_mps").value)
        self.latest_setpoint: Setpoint | None = None
        self.last_step_time_s = self._now_s()

        self.true_cable = self._build_true_cable()
        self.prior_points_ned = self._load_prior_points_ned()

        self.pub_odom = self.create_publisher(Odometry, "/auv/state/filtered", 10)
        self.pub_magnetic = self.create_publisher(MagneticField, "/auv/sensors/magnetic", 50)
        self.pub_mission = self.create_publisher(String, "/auv/mission_command", 10)
        self.pub_cable_mission = self.create_publisher(String, "/auv/cable/mission_command", 10)
        self.pub_true_cable = self.create_publisher(Marker, "/auv/visual/decoupled_true_cable", 10)
        self.pub_prior_cable = self.create_publisher(Marker, "/auv/visual/decoupled_prior_cable", 10)
        self.pub_trail = self.create_publisher(Marker, "/auv/visual/decoupled_vehicle_trail", 10)
        self.pub_auv = self.create_publisher(Marker, "/auv/visual/decoupled_vehicle", 10)
        self.sub_setpoint = self.create_subscription(Setpoint, "/auv/control/setpoint", self._on_setpoint, 10)

        state_rate_hz = max(1.0, float(self.get_parameter("state_rate_hz").value))
        mag_rate_hz = max(1.0, float(self.get_parameter("mag_rate_hz").value))
        marker_rate_hz = max(0.2, float(self.get_parameter("marker_rate_hz").value))
        mission_rate_hz = max(0.1, float(self.get_parameter("mission_rate_hz").value))
        self.state_timer = self.create_timer(1.0 / state_rate_hz, self._on_state_timer)
        self.mag_timer = self.create_timer(1.0 / mag_rate_hz, self._publish_magnetic)
        self.marker_timer = self.create_timer(1.0 / marker_rate_hz, self._publish_markers)
        self.mission_timer = self.create_timer(1.0 / mission_rate_hz, self._publish_mission)

        self.get_logger().info(
            "decoupled cable sim ready "
            f"config={self.tracking_config_file} initial=({self.position_ned[0]:.1f},"
            f"{self.position_ned[1]:.1f},{self.position_ned[2]:.1f}) "
            f"true_cable_y={float(self.get_parameter('true_cable_y_m').value):.1f} "
            f"vertical_sep={float(self.get_parameter('vertical_separation_m').value):.1f} "
            f"current={self.current_amp_a:.1f}A"
        )

    def _now_s(self) -> float:
        return float(self.get_clock().now().nanoseconds) * 1.0e-9

    def _build_true_cable(self) -> CablePath:
        x0 = float(self.get_parameter("true_cable_start_x_m").value)
        x1 = float(self.get_parameter("true_cable_end_x_m").value)
        spacing = max(0.5, float(self.get_parameter("true_cable_segment_m").value))
        y = float(self.get_parameter("true_cable_y_m").value)
        depth = self.target_depth_m + float(self.get_parameter("vertical_separation_m").value)
        count = max(2, int(math.ceil(abs(x1 - x0) / spacing)) + 1)
        xs = np.linspace(x0, x1, count)
        points = np.column_stack([xs, np.full(count, y), np.full(count, depth)])
        return CablePath(points)

    def _load_prior_points_ned(self) -> np.ndarray:
        try:
            cable_map = load_cable_map_from_config(self.tracking_config, project_root=PROJECT_ROOT)
            xy = np.asarray(cable_map.points_xy_m, dtype=float).reshape(-1, 2)
        except Exception as exc:
            self.get_logger().warning(f"failed to load distorted prior marker geometry: {exc}")
            xy = np.asarray([[0.0, 7.5], [120.0, 7.5]], dtype=float)
        z = self.target_depth_m + float(self.get_parameter("vertical_separation_m").value)
        return np.column_stack([xy[:, 0], xy[:, 1], np.full(xy.shape[0], z)])

    def _on_setpoint(self, msg: Setpoint) -> None:
        self.latest_setpoint = msg

    def _on_state_timer(self) -> None:
        now_s = self._now_s()
        dt_s = max(0.0, min(now_s - self.last_step_time_s, 0.2))
        self.last_step_time_s = now_s
        self._integrate(dt_s)
        self._publish_odom()

    def _integrate(self, dt_s: float) -> None:
        if dt_s <= 0.0:
            return
        target_heading = self.heading_rad
        target_speed = self.speed_mps
        target_depth = self.target_depth_m
        if self.latest_setpoint is not None:
            target_heading = float(self.latest_setpoint.target_heading_rad)
            target_speed = max(0.0, float(self.latest_setpoint.target_speed_mps))
            if float(self.latest_setpoint.target_depth_m) > 0.0:
                target_depth = float(self.latest_setpoint.target_depth_m)

        heading_error = _wrap_angle_rad(target_heading - self.heading_rad)
        yaw_step = float(np.clip(heading_error, -self.max_yaw_rate_rad_s * dt_s, self.max_yaw_rate_rad_s * dt_s))
        self.heading_rad = _wrap_angle_rad(self.heading_rad + yaw_step)
        self.speed_mps = target_speed
        self.position_ned[0] += math.cos(self.heading_rad) * self.speed_mps * dt_s
        self.position_ned[1] += math.sin(self.heading_rad) * self.speed_mps * dt_s
        alpha = min(1.0, dt_s / self.depth_time_constant_s)
        self.position_ned[2] += (target_depth - self.position_ned[2]) * alpha
        self.trail.append(self.position_ned.copy())

    def _publish_odom(self) -> None:
        msg = Odometry()
        stamp = self.get_clock().now().to_msg()
        msg.header.stamp = stamp
        msg.header.frame_id = self.frame_id
        msg.child_frame_id = self.base_link_frame_id
        msg.pose.pose.position.x = float(self.position_ned[0])
        msg.pose.pose.position.y = float(self.position_ned[1])
        msg.pose.pose.position.z = float(self.position_ned[2])
        msg.pose.pose.orientation = _yaw_quaternion(self.heading_rad)
        msg.twist.twist.linear.x = math.cos(self.heading_rad) * self.speed_mps
        msg.twist.twist.linear.y = math.sin(self.heading_rad) * self.speed_mps
        self.pub_odom.publish(msg)

    def _publish_magnetic(self) -> None:
        b_ned_t = compute_biot_savart_hvdc(
            auv_pos_ned=self.position_ned,
            cable=self.true_cable,
            current_amp=self.current_amp_a,
        )
        msg = MagneticField()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = self.mag_frame_id
        msg.magnetic_field.x = float(b_ned_t[0])
        msg.magnetic_field.y = float(b_ned_t[1])
        msg.magnetic_field.z = float(b_ned_t[2])
        self.pub_magnetic.publish(msg)

    def _publish_mission(self) -> None:
        payload = {
            "mission_type": str(self.get_parameter("mission_type").value).upper(),
            "target_depth": self.target_depth_m,
            "target_speed_mps": self.target_speed_mps,
            "source": "decoupled_cable_sim_node",
            "tracking_config_file": str(self.tracking_config_file),
        }
        msg = String(data=json.dumps(payload, ensure_ascii=False))
        if bool(self.get_parameter("publish_general_mission").value):
            self.pub_mission.publish(msg)
        if bool(self.get_parameter("publish_cable_mission").value):
            self.pub_cable_mission.publish(msg)

    def _publish_markers(self) -> None:
        stamp = self.get_clock().now().to_msg()
        self.pub_true_cable.publish(
            self._line_marker(
                self.true_cable.points,
                stamp=stamp,
                ns="direction_a_true_cable",
                marker_id=1,
                color=(0.0, 0.85, 0.2, 1.0),
                width=0.18,
            )
        )
        self.pub_prior_cable.publish(
            self._line_marker(
                self.prior_points_ned,
                stamp=stamp,
                ns="direction_a_distorted_prior",
                marker_id=2,
                color=(1.0, 0.55, 0.0, 1.0),
                width=0.12,
            )
        )
        if len(self.trail) >= 2:
            self.pub_trail.publish(
                self._line_marker(
                    np.asarray(self.trail, dtype=float),
                    stamp=stamp,
                    ns="direction_a_vehicle_trail",
                    marker_id=3,
                    color=(0.2, 0.55, 1.0, 1.0),
                    width=0.08,
                )
            )
        self.pub_auv.publish(self._vehicle_marker(stamp))

    def _line_marker(
        self,
        points_ned: np.ndarray,
        *,
        stamp,
        ns: str,
        marker_id: int,
        color: tuple[float, float, float, float],
        width: float,
    ) -> Marker:
        marker = Marker()
        marker.header.stamp = stamp
        marker.header.frame_id = self.frame_id
        marker.ns = ns
        marker.id = marker_id
        marker.type = Marker.LINE_STRIP
        marker.action = Marker.ADD
        marker.scale.x = float(width)
        marker.color.r, marker.color.g, marker.color.b, marker.color.a = color
        marker.points = [Point(x=float(p[0]), y=float(p[1]), z=float(p[2])) for p in np.asarray(points_ned)]
        return marker

    def _vehicle_marker(self, stamp) -> Marker:
        marker = Marker()
        marker.header.stamp = stamp
        marker.header.frame_id = self.frame_id
        marker.ns = "direction_a_vehicle"
        marker.id = 4
        marker.type = Marker.ARROW
        marker.action = Marker.ADD
        marker.pose.position.x = float(self.position_ned[0])
        marker.pose.position.y = float(self.position_ned[1])
        marker.pose.position.z = float(self.position_ned[2])
        marker.pose.orientation = _yaw_quaternion(self.heading_rad)
        marker.scale.x = 2.0
        marker.scale.y = 0.35
        marker.scale.z = 0.35
        marker.color.r = 0.15
        marker.color.g = 0.45
        marker.color.b = 1.0
        marker.color.a = 1.0
        return marker


def main() -> None:
    rclpy.init()
    node = DecoupledCableSimNode()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()

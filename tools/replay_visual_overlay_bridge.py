#!/usr/bin/env python3
"""Reconstruct Foxglove visual overlay topics during rosbag replay.

This sidecar is for recorded 3f runs whose MCAP only contains state and cable
tracking topics but not the older /auv/visual/* marker topics. It republishes a
minimal visualization set:
  - /auv/visual/auv_body
  - /auv/visual/history_trail
  - /auv/visual/cable_marker
  - /auv/visual/view_range
  - /auv/visual/seabed_mesh
  - /auv/visual/scale_bar
"""

from __future__ import annotations

from collections import deque
import math
import sys
from pathlib import Path
from typing import Any

from geometry_msgs.msg import Point, Pose, Quaternion, Vector3
import numpy as np
import rclpy
from nav_msgs.msg import Odometry
from rclpy.node import Node
from std_msgs.msg import ColorRGBA, String
import yaml
from visualization_msgs.msg import Marker


PROJECT_ROOT = Path(__file__).resolve().parents[1]
for extra in [
    PROJECT_ROOT / "brain_linux" / "src" / "auv_viz_bridge",
    PROJECT_ROOT / "brain_linux" / "src" / "auv_control",
]:
    extra_str = str(extra)
    if extra_str not in sys.path:
        sys.path.insert(0, extra_str)

from auv_decision_ros.cable_prior_adapter import load_cable_map_from_config  # noqa: E402
from auv_viz_bridge.zenoh_viz_bridge_node import _multiply_quaternions, _normalize_quaternion  # noqa: E402


def _quaternion_to_rpy(x: float, y: float, z: float, w: float) -> tuple[float, float, float]:
    """Convert quaternion to roll, pitch, yaw."""
    sinr_cosp = 2.0 * (w * x + y * z)
    cosr_cosp = 1.0 - 2.0 * (x * x + y * y)
    roll = math.atan2(sinr_cosp, cosr_cosp)

    sinp = 2.0 * (w * y - z * x)
    if abs(sinp) >= 1.0:
        pitch = math.copysign(math.pi / 2.0, sinp)
    else:
        pitch = math.asin(sinp)

    siny_cosp = 2.0 * (w * z + x * y)
    cosy_cosp = 1.0 - 2.0 * (y * y + z * z)
    yaw = math.atan2(siny_cosp, cosy_cosp)
    return roll, pitch, yaw


def _load_tracking_config(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"invalid config payload: {path}")
    return dict(payload.get("cable_tracking", {}) or {})


def _load_tracking_root_config(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"invalid config payload: {path}")
    return payload


def _cable_map_to_points_xyz(cable_map) -> np.ndarray:
    points_xy = np.asarray(cable_map.points_xy_m, dtype=float)
    burial = getattr(cable_map, "burial_depth_m", None)
    if burial is None:
        z_values = np.zeros(points_xy.shape[0], dtype=float)
    else:
        burial_arr = np.asarray(burial, dtype=float).reshape(-1)
        if burial_arr.size == 1:
            burial_arr = np.repeat(burial_arr, points_xy.shape[0])
        z_values = -np.abs(burial_arr[: points_xy.shape[0]])
    return np.column_stack((points_xy[:, 0], points_xy[:, 1], z_values))


def _terrain_depth_from_tracking_cfg(x_value: float, y_value: float, tracking_cfg: dict[str, Any]) -> float:
    prior = dict(tracking_cfg.get("prior", {}) or {})
    default_depth = 15.0
    points = prior.get("yaml_points_ned") or []
    if points:
        z_values = [-float(point[2]) for point in points if len(point) >= 3]
        if z_values:
            default_depth = float(sum(z_values) / len(z_values))

    curvature = 0.015 * math.sin(x_value / 18.0) + 0.01 * math.cos(y_value / 10.0)
    slope = 0.0035 * max(0.0, x_value - 20.0)
    cross = 0.002 * y_value
    return -(default_depth + slope + curvature + cross)


def _make_triangle_list_display(
    points_xyz: list[list[float]],
    *,
    frame_id: str,
    stamp,
    ns: str,
    marker_id: int,
    color: tuple[float, float, float, float],
) -> Marker:
    marker = _make_marker_base(marker_id, ns, Marker.TRIANGLE_LIST, frame_id, stamp)
    marker.color = ColorRGBA(r=float(color[0]), g=float(color[1]), b=float(color[2]), a=float(color[3]))
    marker.points = [_display_point(point) for point in points_xyz]
    return marker


def _make_marker_base(marker_id: int, ns: str, marker_type: int, frame_id: str, stamp) -> Marker:
    marker = Marker()
    marker.header.stamp = stamp
    marker.header.frame_id = frame_id
    marker.ns = ns
    marker.id = marker_id
    marker.type = marker_type
    marker.action = Marker.ADD
    marker.pose.orientation.w = 1.0
    marker.lifetime.sec = 0
    marker.lifetime.nanosec = 0
    return marker


def _display_point(value: list[float] | tuple[float, float, float]) -> Point:
    return Point(x=float(value[0]), y=float(value[1]), z=float(value[2]))


def _make_line_strip_display(
    points_xyz: list[list[float]],
    *,
    frame_id: str,
    stamp,
    ns: str,
    marker_id: int,
    color: tuple[float, float, float, float],
    width: float = 0.1,
) -> Marker:
    marker = _make_marker_base(marker_id, ns, Marker.LINE_STRIP, frame_id, stamp)
    marker.scale.x = float(width)
    marker.color = ColorRGBA(r=float(color[0]), g=float(color[1]), b=float(color[2]), a=float(color[3]))
    marker.points = [_display_point(point) for point in points_xyz]
    return marker


def _make_auv_body_marker_display(
    position_xyz: list[float],
    rpy: list[float],
    *,
    frame_id: str,
    stamp,
    ns: str,
    marker_id: int,
) -> Marker:
    marker = _make_marker_base(marker_id, ns, Marker.ARROW, frame_id, stamp)
    qx, qy, qz, qw = _normalize_quaternion(*_quaternion_from_rpy(*rpy))
    marker.pose = Pose(
        position=_display_point(position_xyz),
        orientation=Quaternion(x=qx, y=qy, z=qz, w=qw),
    )
    marker.scale = Vector3(x=3.8, y=0.7, z=0.7)
    marker.color = ColorRGBA(r=0.2, g=0.95, b=1.0, a=1.0)
    return marker


def _make_range_ring_display(
    center_xyz: list[float],
    radius_m: float,
    *,
    frame_id: str,
    stamp,
    ns: str,
    marker_id: int,
    samples: int = 48,
) -> Marker:
    marker = _make_marker_base(marker_id, ns, Marker.LINE_STRIP, frame_id, stamp)
    marker.scale.x = 0.08
    marker.color = ColorRGBA(r=1.0, g=0.25, b=0.25, a=0.55)
    points: list[list[float]] = []
    for index in range(samples + 1):
        theta = 2.0 * math.pi * index / samples
        points.append(
            [
                float(center_xyz[0]) + radius_m * math.cos(theta),
                float(center_xyz[1]) + radius_m * math.sin(theta),
                float(center_xyz[2]) + 0.02,
            ]
        )
    marker.points = [_display_point(point) for point in points]
    return marker


def _make_scale_bar_display(
    *,
    origin_xyz: list[float],
    length_m: float,
    label_height_m: float,
    frame_id: str,
    stamp,
    ns: str,
    marker_id: int,
) -> Marker:
    marker = _make_marker_base(marker_id, ns, Marker.LINE_LIST, frame_id, stamp)
    marker.scale.x = 0.18
    marker.color = ColorRGBA(r=1.0, g=1.0, b=1.0, a=0.95)
    x0, y0, z0 = origin_xyz
    x1 = x0 + length_m
    tick = 0.8
    points = [
        [x0, y0, z0],
        [x1, y0, z0],
        [x0, y0 - tick, z0],
        [x0, y0 + tick, z0],
        [x1, y0 - tick, z0],
        [x1, y0 + tick, z0],
    ]
    marker.points = [_display_point(point) for point in points]
    marker.text = f"{length_m:.0f} m"
    return marker


def _make_scale_label_display(
    *,
    origin_xyz: list[float],
    text: str,
    frame_id: str,
    stamp,
    ns: str,
    marker_id: int,
) -> Marker:
    marker = _make_marker_base(marker_id, ns, Marker.TEXT_VIEW_FACING, frame_id, stamp)
    marker.pose.position = _display_point(origin_xyz)
    marker.scale.z = 1.5
    marker.color = ColorRGBA(r=1.0, g=1.0, b=1.0, a=0.98)
    marker.text = text
    return marker


def _quaternion_from_rpy(roll: float, pitch: float, yaw: float) -> tuple[float, float, float, float]:
    cy = math.cos(yaw * 0.5)
    sy = math.sin(yaw * 0.5)
    cp = math.cos(pitch * 0.5)
    sp = math.sin(pitch * 0.5)
    cr = math.cos(roll * 0.5)
    sr = math.sin(roll * 0.5)
    return (
        sr * cp * cy - cr * sp * sy,
        cr * sp * cy + sr * cp * sy,
        cr * cp * sy - sr * sp * cy,
        cr * cp * cy + sr * sp * sy,
    )


def _rewrite_dlt_summary_text(text: str) -> str:
    rewritten = text.replace("总分:", "扣分合计:").replace("总分：", "扣分合计：")
    rewritten = rewritten.replace("总分 ", "扣分合计 ").replace("总分|", "扣分合计|")
    return rewritten.replace("DL/T 风格总分", "DL/T 风格扣分合计").replace("DL/T 1278风格总分", "DL/T 1278风格扣分合计")


class ReplayVisualOverlayBridge(Node):
    def __init__(self) -> None:
        super().__init__("replay_visual_overlay_bridge")
        default_cfg = PROJECT_ROOT / "results" / "cable_ops_report" / "replay_e2e" / "_configs" / "heavy.yaml"
        self.declare_parameter("tracking_config", str(default_cfg))
        self.declare_parameter("frame_id", "world")
        self.declare_parameter("trail_length", 300)
        self.declare_parameter("view_radius_m", 4.0)

        self.frame_id = str(self.get_parameter("frame_id").value)
        self.trail_length = int(self.get_parameter("trail_length").value)
        self.view_radius_m = float(self.get_parameter("view_radius_m").value)

        config_path = Path(str(self.get_parameter("tracking_config").value)).expanduser()
        tracking_root_cfg = _load_tracking_root_config(config_path)
        tracking_cfg = dict(tracking_root_cfg.get("cable_tracking", {}) or {})
        cable_map = load_cable_map_from_config(tracking_cfg, project_root=PROJECT_ROOT)
        self.prior_points_xyz = _cable_map_to_points_xyz(cable_map)
        self.seabed_mesh_points_xyz = self._build_seabed_mesh_points(tracking_cfg)

        self.trail: deque[list[float]] = deque(maxlen=max(2, self.trail_length))

        self.cable_pub = self.create_publisher(Marker, "/auv/visual/cable_marker", 10)
        self.body_pub = self.create_publisher(Marker, "/auv/visual/auv_body", 10)
        self.trail_pub = self.create_publisher(Marker, "/auv/visual/history_trail", 10)
        self.range_pub = self.create_publisher(Marker, "/auv/visual/view_range", 10)
        self.mesh_pub = self.create_publisher(Marker, "/auv/visual/seabed_mesh", 10)
        self.scale_bar_pub = self.create_publisher(Marker, "/auv/visual/scale_bar", 10)
        self.dlt_summary_pub = self.create_publisher(String, "/auv/cable/dlt1278_summary_rewritten", 10)
        self.latest_dlt_summary_rewritten: str | None = None

        self.create_subscription(Odometry, "/auv/state/filtered", self._on_odom, 20)
        self.create_subscription(String, "/auv/cable/dlt1278_summary", self._on_dlt_summary, 10)
        self.get_logger().info(
            f"replay_visual_overlay_bridge started: frame_id={self.frame_id}, prior_points={len(self.prior_points_xyz)}"
        )

    def _build_seabed_mesh_points(self, tracking_cfg: dict[str, Any]) -> list[list[float]]:
        xs = np.linspace(-10.0, 110.0, 13)
        ys = np.linspace(-10.0, 30.0, 9)
        vertices: list[list[float]] = []
        grid: dict[tuple[int, int], list[float]] = {}
        for ix, x_value in enumerate(xs):
            for iy, y_value in enumerate(ys):
                grid[(ix, iy)] = [float(x_value), float(y_value), _terrain_depth_from_tracking_cfg(float(x_value), float(y_value), tracking_cfg)]
        for ix in range(len(xs) - 1):
            for iy in range(len(ys) - 1):
                p00 = grid[(ix, iy)]
                p10 = grid[(ix + 1, iy)]
                p01 = grid[(ix, iy + 1)]
                p11 = grid[(ix + 1, iy + 1)]
                vertices.extend([p00, p10, p11, p00, p11, p01])
        return vertices

    def _on_dlt_summary(self, msg: String) -> None:
        raw_text = str(msg.data or "")
        rewritten = _rewrite_dlt_summary_text(raw_text)
        self.latest_dlt_summary_rewritten = rewritten
        self.dlt_summary_pub.publish(String(data=rewritten))

    def _on_odom(self, msg: Odometry) -> None:
        stamp = msg.header.stamp
        position = msg.pose.pose.position
        orientation = msg.pose.pose.orientation
        rpy = _quaternion_to_rpy(orientation.x, orientation.y, orientation.z, orientation.w)
        position_xyz = [float(position.x), float(position.y), float(position.z)]
        self.trail.append(position_xyz)

        self.cable_pub.publish(
            _make_line_strip_display(
                self.prior_points_xyz.tolist(),
                frame_id=self.frame_id,
                stamp=stamp,
                ns="replay_prior_cable",
                marker_id=1,
                color=(1.0, 0.84, 0.18, 1.0),
                width=0.18,
            )
        )
        self.mesh_pub.publish(
            _make_triangle_list_display(
                self.seabed_mesh_points_xyz,
                frame_id=self.frame_id,
                stamp=stamp,
                ns="replay_seabed_mesh",
                marker_id=10,
                color=(0.68, 0.54, 0.34, 0.35),
            )
        )
        self.body_pub.publish(
            _make_auv_body_marker_display(
                position_xyz,
                list(rpy),
                frame_id=self.frame_id,
                stamp=stamp,
                ns="replay_auv_body",
                marker_id=2,
            )
        )
        if len(self.trail) >= 2:
            trail_marker = _make_line_strip_display(
                list(self.trail),
                frame_id=self.frame_id,
                stamp=stamp,
                ns="replay_history_trail",
                marker_id=3,
                color=(0.2, 0.55, 1.0, 1.0),
                width=0.08,
            )
            self.trail_pub.publish(trail_marker)

        self.range_pub.publish(
            _make_range_ring_display(
                position_xyz,
                self.view_radius_m,
                frame_id=self.frame_id,
                stamp=stamp,
                ns="replay_view_range",
                marker_id=4,
            )
        )
        scale_origin = [position_xyz[0] - 8.0, position_xyz[1] - 7.0, position_xyz[2] + 0.15]
        self.scale_bar_pub.publish(
            _make_scale_bar_display(
                origin_xyz=scale_origin,
                length_m=10.0,
                label_height_m=1.5,
                frame_id=self.frame_id,
                stamp=stamp,
                ns="replay_scale_bar",
                marker_id=20,
            )
        )
        self.scale_bar_pub.publish(
            _make_scale_label_display(
                origin_xyz=[scale_origin[0] + 5.0, scale_origin[1] - 1.8, scale_origin[2] + 0.2],
                text="10 m",
                frame_id=self.frame_id,
                stamp=stamp,
                ns="replay_scale_bar",
                marker_id=21,
            )
        )
        if self.latest_dlt_summary_rewritten:
            self.dlt_summary_pub.publish(String(data=self.latest_dlt_summary_rewritten))


def main() -> None:
    rclpy.init()
    node = ReplayVisualOverlayBridge()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Zenoh -> ROS2 digital twin visualization bridge.

The node consumes synthetic scene payloads from Zenoh and converts them into
Foxglove-friendly ROS2 visualization topics.
"""

from __future__ import annotations

import json
from dataclasses import asdict
import math
import os
import struct
import time
from pathlib import Path
import sys
from typing import Any

def _resolve_project_root() -> Path:
    env_root = Path(str(os.environ.get('AUV_PROJECT_ROOT', ''))).expanduser() if os.environ.get('AUV_PROJECT_ROOT') else None
    if env_root and (env_root / 'common').exists() and (env_root / 'brain_linux').exists():
        return env_root

    cur = Path(__file__).resolve()
    for parent in cur.parents:
        if (parent / 'common').exists() and (parent / 'sim_holoocean').exists() and (parent / 'brain_linux').exists():
            return parent

    return cur.parents[4]


PROJECT_ROOT = _resolve_project_root()
for folder in [PROJECT_ROOT, PROJECT_ROOT / 'common', PROJECT_ROOT / 'sim_holoocean', PROJECT_ROOT / 'sim_holoocean' / 'interfaces']:
    folder_str = str(folder)
    if folder_str not in sys.path:
        sys.path.insert(0, folder_str)

import rclpy
from geometry_msgs.msg import Point, Pose, PoseStamped, Quaternion, TransformStamped, Vector3
from rclpy.node import Node
from sensor_msgs.msg import PointCloud2, PointField
from std_msgs.msg import ColorRGBA
from std_msgs.msg import String
from tf2_ros import TransformBroadcaster
from visualization_msgs.msg import Marker
import yaml

from common.protocol import (
    KEY_CENTER_NED,
    KEY_HEIGHT_M,
    KEY_POINTS_NED,
    KEY_POSITION_NED,
    KEY_RADIUS_M,
    KEY_RPY_NED,
    KEY_TRAIL_NED,
    Z_PATH_CABLE_MARKER,
    Z_PATH_HISTORY_TRAIL,
    Z_PATH_SEABED_CLOUD,
    Z_PATH_TRUTH_POSE,
    Z_PATH_VIEW_RANGE,
)
from foxglove_layout_project.generator.mock_topics import build_mock_topics_snapshot
from synthetic_sensors import VirtualEnvironment, euler_to_quaternion


def _normalize_quaternion(qx: float, qy: float, qz: float, qw: float) -> tuple[float, float, float, float]:
    norm = math.sqrt(qx * qx + qy * qy + qz * qz + qw * qw)
    if norm <= 1e-12:
        return 0.0, 0.0, 0.0, 1.0
    return qx / norm, qy / norm, qz / norm, qw / norm


def _multiply_quaternions(
    first: tuple[float, float, float, float],
    second: tuple[float, float, float, float],
) -> tuple[float, float, float, float]:
    x1, y1, z1, w1 = first
    x2, y2, z2, w2 = second
    return (
        w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
        w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2,
        w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2,
        w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2,
    )


def _rpy_to_quaternion(rpy_ned: list[float] | tuple[float, float, float]) -> Quaternion:
    qx, qy, qz, qw = euler_to_quaternion(float(rpy_ned[0]), float(rpy_ned[1]), float(rpy_ned[2]))
    qx, qy, qz, qw = _normalize_quaternion(qx, qy, qz, qw)
    return Quaternion(x=qx, y=qy, z=qz, w=qw)


def _rpy_to_quaternion_tuple(rpy_ned: list[float] | tuple[float, float, float]) -> tuple[float, float, float, float]:
    quat = _rpy_to_quaternion(rpy_ned)
    return quat.x, quat.y, quat.z, quat.w


def _ned_to_display_xyz(value: list[float] | tuple[float, float, float]) -> tuple[float, float, float]:
    return float(value[0]), float(value[1]), float(-value[2])


def _as_point(value: list[float] | tuple[float, float, float]) -> Point:
    x_value, y_value, z_value = _ned_to_display_xyz(value)
    return Point(x=x_value, y=y_value, z=z_value)


def _pointcloud2_from_points(points: list[list[float]], frame_id: str, stamp) -> PointCloud2:
    msg = PointCloud2()
    msg.header.stamp = stamp
    msg.header.frame_id = frame_id
    msg.height = 1
    msg.width = len(points)
    msg.is_bigendian = False
    msg.is_dense = True
    msg.fields = [
        PointField(name='x', offset=0, datatype=PointField.FLOAT32, count=1),
        PointField(name='y', offset=4, datatype=PointField.FLOAT32, count=1),
        PointField(name='z', offset=8, datatype=PointField.FLOAT32, count=1),
    ]
    msg.point_step = 12
    msg.row_step = msg.point_step * msg.width
    msg.data = b''.join(struct.pack('<fff', *_ned_to_display_xyz(p)) for p in points)
    return msg


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


def _make_line_strip(points: list[list[float]], *, frame_id: str, stamp, ns: str, marker_id: int, color: tuple[float, float, float, float], width: float = 0.1) -> Marker:
    marker = _make_marker_base(marker_id, ns, Marker.LINE_STRIP, frame_id, stamp)
    marker.scale.x = float(width)
    marker.color = ColorRGBA(r=float(color[0]), g=float(color[1]), b=float(color[2]), a=float(color[3]))
    marker.points = [_as_point(point) for point in points]
    return marker


def _make_terrain_mesh(points: list[list[float]], *, frame_id: str, stamp, ns: str, marker_id: int) -> Marker:
    marker = _make_marker_base(marker_id, ns, Marker.TRIANGLE_LIST, frame_id, stamp)
    marker.scale = Vector3(x=1.0, y=1.0, z=1.0)
    marker.color = ColorRGBA(r=0.82, g=0.71, b=0.55, a=0.34)

    if len(points) < 4:
        return marker

    unique_x = sorted({round(float(point[0]), 6) for point in points})
    unique_y = sorted({round(float(point[1]), 6) for point in points})
    if len(unique_x) < 2 or len(unique_y) < 2:
        return marker

    width = len(unique_y)
    height = len(unique_x)
    if width * height != len(points):
        return marker

    display_points = [_as_point(point) for point in points]
    triangles: list[Point] = []
    for ix in range(height - 1):
        for iy in range(width - 1):
            p00 = display_points[ix * width + iy]
            p01 = display_points[ix * width + iy + 1]
            p10 = display_points[(ix + 1) * width + iy]
            p11 = display_points[(ix + 1) * width + iy + 1]
            triangles.extend([p00, p10, p11, p00, p11, p01])

    marker.points = triangles
    return marker


def _make_arrow_marker(position_ned: list[float], rpy_ned: list[float], *, frame_id: str, stamp, ns: str, marker_id: int) -> Marker:
    marker = _make_marker_base(marker_id, ns, Marker.ARROW, frame_id, stamp)
    marker.pose = Pose(position=_as_point(position_ned), orientation=_rpy_to_quaternion(rpy_ned))
    marker.scale = Vector3(x=2.8, y=0.18, z=0.18)
    marker.color = ColorRGBA(r=0.1, g=0.7, b=1.0, a=1.0)
    return marker


def _make_auv_body_marker(position_ned: list[float], rpy_ned: list[float], *, frame_id: str, stamp, ns: str, marker_id: int) -> Marker:
    marker = _make_marker_base(marker_id, ns, Marker.CYLINDER, frame_id, stamp)
    body_quat = _rpy_to_quaternion_tuple(rpy_ned)
    offset_quat = _rpy_to_quaternion_tuple((0.0, math.pi / 2.0, 0.0))
    qx, qy, qz, qw = _normalize_quaternion(*_multiply_quaternions(body_quat, offset_quat))
    marker.pose = Pose(
        position=_as_point(position_ned),
        orientation=Quaternion(x=qx, y=qy, z=qz, w=qw),
    )
    marker.scale = Vector3(x=0.45, y=0.45, z=2.4)
    marker.color = ColorRGBA(r=0.35, g=0.65, b=1.0, a=0.92)
    return marker


def _make_range_ring(center_ned: list[float], radius_m: float, *, frame_id: str, stamp, ns: str, marker_id: int, samples: int = 48) -> Marker:
    marker = _make_marker_base(marker_id, ns, Marker.LINE_STRIP, frame_id, stamp)
    marker.scale.x = 0.06
    marker.color = ColorRGBA(r=1.0, g=0.25, b=0.25, a=0.55)
    z_value = float(center_ned[2]) + 0.02
    points: list[list[float]] = []
    for index in range(samples + 1):
        theta = 2.0 * math.pi * index / samples
        points.append(
            [
                float(center_ned[0]) + radius_m * math.cos(theta),
                float(center_ned[1]) + radius_m * math.sin(theta),
                z_value,
            ]
        )
    marker.points = [_as_point(point) for point in points]
    return marker


class ZenohVizBridgeNode(Node):
    def __init__(self) -> None:
        super().__init__('zenoh_viz_bridge_node')

        default_params = str(PROJECT_ROOT / 'brain_linux' / 'config' / 'params.yaml')
        self.declare_parameter('params_file', default_params)
        self.declare_parameter('mock_mode', False)
        self.declare_parameter('mock_fallback_timeout_s', 3.0)
        self.declare_parameter('frame_id', 'map')
        self.declare_parameter('truth_frame_id', 'truth_link')
        self.declare_parameter('terrain_key', Z_PATH_SEABED_CLOUD)
        self.declare_parameter('cable_key', Z_PATH_CABLE_MARKER)
        self.declare_parameter('truth_key', Z_PATH_TRUTH_POSE)
        self.declare_parameter('trail_key', Z_PATH_HISTORY_TRAIL)
        self.declare_parameter('range_key', Z_PATH_VIEW_RANGE)

        self.params_file = str(self.get_parameter('params_file').value)
        self.mock_mode = bool(self.get_parameter('mock_mode').value)
        self.mock_fallback_timeout_s = float(self.get_parameter('mock_fallback_timeout_s').value)
        self.frame_id = str(self.get_parameter('frame_id').value)
        self.truth_frame_id = str(self.get_parameter('truth_frame_id').value)

        cfg = self._load_config(self.params_file).get('digital_twin', {})
        self.terrain_key = str(cfg.get('terrain_topic_key', self.get_parameter('terrain_key').value))
        self.cable_key = str(cfg.get('cable_topic_key', self.get_parameter('cable_key').value))
        self.truth_key = str(cfg.get('truth_topic_key', self.get_parameter('truth_key').value))
        self.trail_key = str(cfg.get('history_topic_key', self.get_parameter('trail_key').value))
        self.range_key = str(cfg.get('view_topic_key', self.get_parameter('range_key').value))

        self.virtual_env = VirtualEnvironment(cfg)
        self._session = None
        self._subscribers = []
        self._last_live_rx_ns = 0
        self._live_terrain: dict[str, Any] | None = None
        self._live_cable: dict[str, Any] | None = None
        self._live_truth: dict[str, Any] | None = None
        self._live_trail: dict[str, Any] | None = None
        self._live_range: dict[str, Any] | None = None
        self._mock_tick = 0

        self.cloud_pub = self.create_publisher(PointCloud2, '/auv/visual/seabed_cloud', 10)
        self.mesh_pub = self.create_publisher(Marker, '/auv/visual/seabed_mesh', 10)
        self.cable_pub = self.create_publisher(Marker, '/auv/visual/cable_marker', 10)
        self.body_pub = self.create_publisher(Marker, '/auv/visual/auv_body', 10)
        self.truth_pub = self.create_publisher(Marker, '/auv/visual/truth_marker', 10)
        self.trail_pub = self.create_publisher(Marker, '/auv/visual/history_trail', 10)
        self.range_pub = self.create_publisher(Marker, '/auv/visual/view_range', 10)
        self.mock_scene_pub = self.create_publisher(String, '/auv/mock/scene', 10)
        self.tf_broadcaster = TransformBroadcaster(self)

        self._open_zenoh()
        self.create_timer(0.1, self._on_timer)
        self.get_logger().info('zenoh_viz_bridge_node started')

    @staticmethod
    def _load_config(path: str) -> dict:
        p = Path(path)
        if not p.exists():
            return {}
        with p.open('r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
        return data if isinstance(data, dict) else {}

    def _open_zenoh(self) -> None:
        try:
            import zenoh  # type: ignore
        except Exception:
            self.get_logger().warning('zenoh package not available, running in mock fallback mode')
            return

        try:
            zcfg = zenoh.Config()
            self._session = zenoh.open(zcfg)
        except Exception as exc:
            self.get_logger().warning(f'zenoh session unavailable, running in mock fallback mode: {exc}')
            self._session = None
            return

        def _sub(key: str, handler):
            self._subscribers.append(self._session.declare_subscriber(key, self._make_cb(handler)))

        _sub(self.terrain_key, self._on_terrain)
        _sub(self.cable_key, self._on_cable)
        _sub(self.truth_key, self._on_truth)
        _sub(self.trail_key, self._on_trail)
        _sub(self.range_key, self._on_range)

    def _make_cb(self, handler):
        def _cb(sample):
            payload = sample.payload.to_bytes() if hasattr(sample.payload, 'to_bytes') else bytes(sample.payload)
            try:
                data = json.loads(payload.decode('utf-8'))
            except Exception:
                return
            self._last_live_rx_ns = self.get_clock().now().nanoseconds
            handler(data)

        return _cb

    def _on_terrain(self, data: dict[str, Any]) -> None:
        self._live_terrain = data

    def _on_cable(self, data: dict[str, Any]) -> None:
        self._live_cable = data

    def _on_truth(self, data: dict[str, Any]) -> None:
        self._live_truth = data

    def _on_trail(self, data: dict[str, Any]) -> None:
        self._live_trail = data

    def _on_range(self, data: dict[str, Any]) -> None:
        self._live_range = data

    def _publish_scene(self, terrain: dict[str, Any], cable: dict[str, Any], truth: dict[str, Any], trail: dict[str, Any], view_range: dict[str, Any]) -> None:
        now = self.get_clock().now().to_msg()
        frame_id = self.frame_id

        if KEY_POINTS_NED in terrain:
            points = terrain[KEY_POINTS_NED]
            if isinstance(points, list) and points:
                self.cloud_pub.publish(_pointcloud2_from_points(points, frame_id, now))
                self.mesh_pub.publish(_make_terrain_mesh(points, frame_id=frame_id, stamp=now, ns='seabed_mesh', marker_id=10))

        if KEY_POINTS_NED in cable:
            points = cable[KEY_POINTS_NED]
            if isinstance(points, list) and points:
                marker = _make_line_strip(points, frame_id=frame_id, stamp=now, ns='cable', marker_id=1, color=(1.0, 0.95, 0.1, 1.0), width=0.12)
                self.cable_pub.publish(marker)

        position = truth.get(KEY_POSITION_NED, [0.0, 0.0, 0.0])
        rpy = truth.get(KEY_RPY_NED, [0.0, 0.0, 0.0])
        if isinstance(position, list) and isinstance(rpy, list):
            self.body_pub.publish(_make_auv_body_marker(position, rpy, frame_id=frame_id, stamp=now, ns='auv_body', marker_id=20))
            truth_marker = _make_arrow_marker(position, rpy, frame_id=frame_id, stamp=now, ns='truth', marker_id=2)
            self.truth_pub.publish(truth_marker)

            transform = TransformStamped()
            transform.header.stamp = now
            transform.header.frame_id = frame_id
            transform.child_frame_id = self.truth_frame_id
            transform.transform.translation.x = float(position[0])
            transform.transform.translation.y = float(position[1])
            transform.transform.translation.z = float(-position[2])
            quat = _rpy_to_quaternion(rpy)
            transform.transform.rotation = quat
            self.tf_broadcaster.sendTransform(transform)

        trail_points = trail.get(KEY_TRAIL_NED, [])
        if isinstance(trail_points, list) and trail_points:
            colors: list[tuple[float, float, float, float]] = []
            count = max(1, len(trail_points) - 1)
            for index, _ in enumerate(trail_points):
                ratio = index / count
                colors.append((0.2, 0.5 + 0.5 * ratio, 1.0 - 0.4 * ratio, 1.0))
            marker = _make_line_strip(trail_points, frame_id=frame_id, stamp=now, ns='trail', marker_id=3, color=(0.2, 0.7, 1.0, 1.0), width=0.08)
            marker.colors = [ColorRGBA(r=c[0], g=c[1], b=c[2], a=c[3]) for c in colors]
            self.trail_pub.publish(marker)

        center = view_range.get(KEY_CENTER_NED, [0.0, 0.0, 0.0])
        radius = float(view_range.get(KEY_RADIUS_M, 3.0))
        if isinstance(center, list):
            self.range_pub.publish(_make_range_ring(center, radius, frame_id=frame_id, stamp=now, ns='view_range', marker_id=4))

    def _publish_mock_scene_summary(self, *, sample_index: int, position_ned: list[float], rpy_ned: list[float], mode: str) -> None:
        snapshot = build_mock_topics_snapshot(
            sample_index=sample_index,
            digital_twin_config=asdict(self.virtual_env.config),
        )
        payload = {
            "mode": mode,
            "sample_index": int(sample_index),
            "position_ned": [float(v) for v in position_ned],
            "rpy_ned": [float(v) for v in rpy_ned],
            "scene_config": snapshot["summary"].get("sceneConfig", {}),
            "visible_layers": snapshot["summary"]["visibleLayers"],
            "payload_sizes": snapshot["summary"]["payloadSizes"],
        }
        self.mock_scene_pub.publish(String(data=json.dumps(payload, ensure_ascii=False)))

    def _on_timer(self) -> None:
        now_ns = self.get_clock().now().nanoseconds
        have_live = self._last_live_rx_ns > 0 and (now_ns - self._last_live_rx_ns) < int(self.mock_fallback_timeout_s * 1e9)

        if self.mock_mode or not have_live:
            position, rpy = self.virtual_env.sample_mock_pose(self._mock_tick)
            payloads = self.virtual_env.build_visual_payloads(position_ned=position, rpy_ned=rpy, publish_terrain=True)
            self._publish_scene(
                payloads[Z_PATH_SEABED_CLOUD],
                payloads[Z_PATH_CABLE_MARKER],
                payloads[Z_PATH_TRUTH_POSE],
                payloads[Z_PATH_HISTORY_TRAIL],
                payloads[Z_PATH_VIEW_RANGE],
            )
            self._publish_mock_scene_summary(sample_index=self._mock_tick, position_ned=position, rpy_ned=rpy, mode='mock')
            self._mock_tick += 1
            return

        if self._live_truth is None:
            return

        terrain = self._live_terrain or {KEY_POINTS_NED: self.virtual_env.sample_seabed_points([0.0, 0.0, self.virtual_env.config.seabed_z_m])}
        cable = self._live_cable or {KEY_POINTS_NED: self.virtual_env.cable_points()}
        trail = self._live_trail or {KEY_TRAIL_NED: []}
        view_range = self._live_range or {
            KEY_CENTER_NED: self._live_truth.get(KEY_POSITION_NED, [0.0, 0.0, 0.0]),
            KEY_RADIUS_M: self.virtual_env.config.view_radius_m,
            KEY_HEIGHT_M: self.virtual_env.config.view_height_m,
        }
        self._publish_scene(terrain, cable, self._live_truth, trail, view_range)
        self._publish_mock_scene_summary(
            sample_index=self._mock_tick,
            position_ned=self._live_truth.get(KEY_POSITION_NED, [0.0, 0.0, 0.0]),
            rpy_ned=self._live_truth.get(KEY_RPY_NED, [0.0, 0.0, 0.0]),
            mode='live',
        )

    def destroy_node(self):
        for sub in self._subscribers:
            try:
                sub.undeclare()
            except Exception:
                pass
        self._subscribers = []

        if self._session is not None:
            try:
                self._session.close()
            except Exception:
                pass
            self._session = None

        return super().destroy_node()


def main(args=None) -> None:
    rclpy.init(args=args)
    node = ZenohVizBridgeNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()

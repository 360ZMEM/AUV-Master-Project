#!/usr/bin/env python3
"""Zenoh -> ROS2 数字孪生可视化桥接节点。

核心功能：
  1. 从Zenoh订阅合成场景有效载荷（海底地形、电缆路径、真值位姿等）
  2. 转换为Foxglove友好的ROS2可视化话题
  3. 发布PointCloud2（点云）、Marker（标记）、TransformStamped（坐标树）
  4. 支持模式切换：实时/模拟/降级失败转移

发布话题：
  - /auv/visual/seabed_cloud: 海底点云
  - /auv/visual/seabed_mesh: 海底网格三角形
  - /auv/visual/cable_marker: 电缆路径线条
  - /auv/visual/auv_body: AUV本体圆柱体
  - /auv/visual/truth_marker: 真值位姿箭头
  - /auv/visual/history_trail: 历史轨迹线条
  - /auv/visual/view_range: 搜索范围环
  - /auv/mock/scene: 模拟场景元数据摘要
  
坐标系约定：
  - NED（北东地）输入 -> 显示坐标系转换（深度反号）
  - 所有位置/速度保持NED标准
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

from .inspection_geometry import inspection_geometry
from .inspection_status import InspectionStatus

import rclpy
from rclpy.executors import ExternalShutdownException

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

from geometry_msgs.msg import Point, Pose, PoseStamped, Quaternion, TransformStamped, Vector3
from rclpy.node import Node
from sensor_msgs.msg import MagneticField, PointCloud2, PointField
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
    Z_PATH_GROUND_TRUTH,
    Z_PATH_HISTORY_TRAIL,
    Z_PATH_PC_CMD_RAW,
    Z_PATH_SEABED_CLOUD,
    Z_PATH_TRUTH_POSE,
    Z_PATH_VIEW_RANGE,
)
from foxglove_layout_project.generator.mock_topics import build_mock_topics_snapshot
from synthetic_sensors import VirtualEnvironment, euler_to_quaternion


def _normalize_quaternion(qx: float, qy: float, qz: float, qw: float) -> tuple[float, float, float, float]:
    """归一化四元数。
    
    Args:
        qx, qy, qz, qw: 四元数分量
        
    Returns:
        tuple[float, float, float, float]: 归一化后的四元数
        
    说明：
        若范数过小（< 1e-12）则返回单位四元数(0, 0, 0, 1)，
        避免数值不稳定。
    """
    norm = math.sqrt(qx * qx + qy * qy + qz * qz + qw * qw)
    if norm <= 1e-12:
        return 0.0, 0.0, 0.0, 1.0
    return qx / norm, qy / norm, qz / norm, qw / norm


def _multiply_quaternions(
    first: tuple[float, float, float, float],
    second: tuple[float, float, float, float],
) -> tuple[float, float, float, float]:
    """四元数乘法（四元数旋转复合）。
    
    Args:
        first: 第一个四元数
        second: 第二个四元数
        
    Returns:
        tuple[float, float, float, float]: 复合旋转后的四元数
        
    说明：
        用于坐标系变换复合，例如body->NED旋转与pitch偏移的组合。
    """
    x1, y1, z1, w1 = first
    x2, y2, z2, w2 = second
    return (
        w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
        w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2,
        w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2,
        w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2,
    )


def _rpy_to_quaternion(rpy_ned: list[float] | tuple[float, float, float]) -> Quaternion:
    """将欧拉角（RPY）转换为四元数对象。
    
    Args:
        rpy_ned: NED坐标系下的欧拉角 [roll, pitch, yaw]（弧度）
        
    Returns:
        Quaternion: ROS2 Quaternion 消息对象
        
    说明：
        - 自动归一化，防止数值误差
        - 用于可视化标记的方向设置
    """
    qx, qy, qz, qw = euler_to_quaternion(float(rpy_ned[0]), float(rpy_ned[1]), float(rpy_ned[2]))
    qx, qy, qz, qw = _normalize_quaternion(qx, qy, qz, qw)
    return Quaternion(x=qx, y=qy, z=qz, w=qw)


def _rpy_to_quaternion_tuple(rpy_ned: list[float] | tuple[float, float, float]) -> tuple[float, float, float, float]:
    """将欧拉角转换为四元数元组。
    
    Args:
        rpy_ned: NED坐标系下的欧拉角
        
    Returns:
        tuple[float, float, float, float]: 四元数元组 (x, y, z, w)
    """
    quat = _rpy_to_quaternion(rpy_ned)
    return quat.x, quat.y, quat.z, quat.w


def _ned_to_display_xyz(value: list[float] | tuple[float, float, float]) -> tuple[float, float, float]:
    """将NED坐标转换为显示坐标系（深度反号）。
    
    Args:
        value: NED坐标 [north, east, down]
        
    Returns:
        tuple[float, float, float]: 显示坐标 (x, y, z)，其中z = -down
        
    说明：
        Foxglove使用Z向上的坐标系，NED中"向下"为正，
        因此需要反号以正确显示深度。
    """
    return float(value[0]), float(value[1]), float(-value[2])


def _as_point(value: list[float] | tuple[float, float, float]) -> Point:
    """将NED坐标转换为ROS2 Point 消息。
    
    Args:
        value: NED坐标
        
    Returns:
        Point: ROS2 Point 对象
    """
    x_value, y_value, z_value = _ned_to_display_xyz(value)
    return Point(x=x_value, y=y_value, z=z_value)


def _pointcloud2_from_points(points: list[list[float]], frame_id: str, stamp) -> PointCloud2:
    """将点列表转换为 PointCloud2 消息。
    
    Args:
        points: 点坐标列表（NED格式）
        frame_id: 参考坐标系ID
        stamp: 时间戳
        
    Returns:
        PointCloud2: 点云消息，用于Foxglove在线显示
        
    说明：
        - 每个点为 float32 x 3（12字节）
        - 使用小端序二进制编码
        - 自动将NED转换为显示坐标
    """
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
    """创建基础 Marker 对象。
    
    Args:
        marker_id: 标记ID（命名空间内唯一）
        ns: 标记命名空间
        marker_type: 标记类型（ARROW、CYLINDER、LINE_STRIP等）
        frame_id: 参考坐标系ID
        stamp: 时间戳
        
    Returns:
        Marker: 基础标记对象，可进一步设置颜色、尺度等
        
    说明：
        - 默认添加模式（Marker.ADD）
        - 无生命周期限制（持久显示）
    """
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
    """创建线条标记（用于电缆、轨迹等）。
    
    Args:
        points: 点坐标列表（NED格式）
        frame_id: 参考坐标系ID
        stamp: 时间戳
        ns: 命名空间
        marker_id: 标记ID
        color: RGBA颜色元组 (r, g, b, a)，范围[0, 1]
        width: 线条宽度（默认0.1m）
        
    Returns:
        Marker: LINE_STRIP类型标记
        
    说明：
        按点的连接顺序形成线段，常用于电缆路径和历史轨迹。
    """
    marker = _make_marker_base(marker_id, ns, Marker.LINE_STRIP, frame_id, stamp)
    marker.scale.x = float(width)
    marker.color = ColorRGBA(r=float(color[0]), g=float(color[1]), b=float(color[2]), a=float(color[3]))
    marker.points = [_as_point(point) for point in points]
    return marker


def _mission_geometry(
    cable_points: list[list[float]],
    corridor_half_width_m: float = 5.0,
    *,
    pattern_mode: str = "sine",
    lateral_amplitude_m: float = 1.5,
    wavelength_m: float = 24.0,
    lane_spacing_m: float = 6.0,
) -> tuple[list[list[float]], list[list[float]]]:
    """Return a corridor outline and an algorithm-aligned reference path.

    ``sine`` mirrors the stable v1 probe parameters. ``lawnmower`` mirrors the
    v2 prior-guided SEARCH geometry. The layer is a reference generated from
    published/configured parameters, never mislabeled as executed waypoints.
    """
    valid = [point for point in cable_points if isinstance(point, list) and len(point) >= 3]
    if len(valid) < 2:
        return [], []
    start, end = valid[0], valid[-1]
    dx = float(end[0]) - float(start[0])
    dy = float(end[1]) - float(start[1])
    length = math.hypot(dx, dy)
    if length < 1.0e-6:
        return [], []
    nx, ny = -dy / length, dx / length
    z = sum(float(point[2]) for point in valid) / len(valid) - 0.08

    def offset(point: list[float], distance: float) -> list[float]:
        return [float(point[0]) + nx * distance, float(point[1]) + ny * distance, z]

    corridor = [
        offset(start, corridor_half_width_m),
        offset(end, corridor_half_width_m),
        offset(end, -corridor_half_width_m),
        offset(start, -corridor_half_width_m),
        offset(start, corridor_half_width_m),
    ]

    pattern: list[list[float]] = []
    if pattern_mode == "lawnmower":
        lane_count = max(2, int(math.floor(2.0 * corridor_half_width_m / max(lane_spacing_m, 0.1))) + 1)
        offsets = [
            -corridor_half_width_m + 2.0 * corridor_half_width_m * index / max(1, lane_count - 1)
            for index in range(lane_count)
        ]
        for index, lateral in enumerate(offsets):
            first, second = (start, end) if index % 2 == 0 else (end, start)
            pattern.extend([offset(first, lateral), offset(second, lateral)])
    else:
        samples = max(40, min(240, int(length / 0.5) + 1))
        tangent_x, tangent_y = dx / length, dy / length
        for index in range(samples):
            progress = length * index / max(1, samples - 1)
            lateral = lateral_amplitude_m * math.sin(2.0 * math.pi * progress / max(wavelength_m, 0.1))
            pattern.append([
                float(start[0]) + tangent_x * progress + nx * lateral,
                float(start[1]) + tangent_y * progress + ny * lateral,
                z - 0.04,
            ])
    return corridor, pattern


def _nearest_cable_point(position: list[float], cable_points: list[list[float]]) -> list[float] | None:
    """Find the nearest sampled cable point in the horizontal plane."""
    valid = [point for point in cable_points if isinstance(point, list) and len(point) >= 3]
    if not valid or len(position) < 2:
        return None
    return min(
        valid,
        key=lambda point: (float(point[0]) - float(position[0])) ** 2 + (float(point[1]) - float(position[1])) ** 2,
    )


def _make_sphere_marker(position_ned: list[float], *, frame_id: str, stamp, ns: str, marker_id: int,
                        color: tuple[float, float, float, float], diameter: float) -> Marker:
    marker = _make_marker_base(marker_id, ns, Marker.SPHERE, frame_id, stamp)
    marker.pose.position = _as_point(position_ned)
    marker.scale = Vector3(x=diameter, y=diameter, z=diameter)
    marker.color = ColorRGBA(r=color[0], g=color[1], b=color[2], a=color[3])
    return marker


def _make_text_marker(position_ned: list[float], text: str, *, frame_id: str, stamp, ns: str, marker_id: int) -> Marker:
    marker = _make_marker_base(marker_id, ns, Marker.TEXT_VIEW_FACING, frame_id, stamp)
    label_position = list(position_ned)
    label_position[2] = float(label_position[2]) - 1.6  # NED up before display conversion.
    marker.pose.position = _as_point(label_position)
    marker.scale.z = 0.9
    marker.color = ColorRGBA(r=0.9, g=0.97, b=1.0, a=1.0)
    marker.text = text
    return marker


def _make_arrow_between(start_ned: list[float], end_ned: list[float], *, frame_id: str, stamp,
                        ns: str, marker_id: int, color: tuple[float, float, float, float]) -> Marker:
    marker = _make_marker_base(marker_id, ns, Marker.ARROW, frame_id, stamp)
    marker.points = [_as_point(start_ned), _as_point(end_ned)]
    marker.scale = Vector3(x=0.08, y=0.18, z=0.28)
    marker.color = ColorRGBA(r=color[0], g=color[1], b=color[2], a=color[3])
    return marker


def _make_uncertainty_ring(position_ned: list[float], sigma_m: float, *, frame_id: str, stamp,
                           ns: str, marker_id: int, samples: int = 64) -> Marker:
    radius = max(0.08, 2.0 * float(sigma_m))
    points = []
    for index in range(samples + 1):
        angle = 2.0 * math.pi * index / samples
        points.append([
            float(position_ned[0]) + radius * math.cos(angle),
            float(position_ned[1]) + radius * math.sin(angle),
            float(position_ned[2]),
        ])
    return _make_line_strip(
        points,
        frame_id=frame_id,
        stamp=stamp,
        ns=ns,
        marker_id=marker_id,
        color=(0.85, 0.35, 1.0, 0.85),
        width=0.055,
    )


def _make_terrain_mesh(points: list[list[float]], *, frame_id: str, stamp, ns: str, marker_id: int) -> Marker:
    """创建海底地形网格标记。
    
    Args:
        points: 点坐标列表（按行优先顺序排列的矩形网格）
        frame_id: 参考坐标系ID
        stamp: 时间戳
        ns: 命名空间
        marker_id: 标记ID
        
    Returns:
        Marker: TRIANGLE_LIST 类型标记
        
    说明：
        - 期望输入为矩形网格的点（width x height 排列）
        - 自动生成三角形面片进行渲染
        - 使用棕色（0.82, 0.71, 0.55）和半透明度(0.34)
    """
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
    """创建箭头标记（用于真值位姿）。
    
    Args:
        position_ned: 箭头原点（NED坐标）
        rpy_ned: 箭头方向（RPY欧拉角）
        frame_id: 参考坐标系ID
        stamp: 时间戳
        ns: 命名空间
        marker_id: 标记ID
        
    Returns:
        Marker: ARROW 类型标记
        
    说明：
        - 长度 2.8m，宽/高 0.18m
        - 青蓝色(0.1, 0.7, 1.0)，完全不透明
        - 常用于显示AUV当前姿态
    """
    marker = _make_marker_base(marker_id, ns, Marker.ARROW, frame_id, stamp)
    marker.pose = Pose(position=_as_point(position_ned), orientation=_rpy_to_quaternion(rpy_ned))
    marker.scale = Vector3(x=2.8, y=0.18, z=0.18)
    marker.color = ColorRGBA(r=0.1, g=0.7, b=1.0, a=1.0)
    return marker


def _make_auv_body_marker(position_ned: list[float], rpy_ned: list[float], *, frame_id: str, stamp, ns: str, marker_id: int) -> Marker:
    """创建AUV本体圆柱形标记。
    
    Args:
        position_ned: AUV质心位置（NED坐标）
        rpy_ned: AUV姿态（RPY欧拉角）
        frame_id: 参考坐标系ID
        stamp: 时间戳
        ns: 命名空间
        marker_id: 标记ID
        
    Returns:
        Marker: CYLINDER 类型标记
        
    说明：
        - 圆柱体长 2.4m（纵轴），直径 0.45m
        - 应用 pitch +90° 偏移使圆柱沿前进方向
        - 浅青蓝色(0.35, 0.65, 1.0)，透明度 0.92
    """
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
    """创建搜索范围环标记。
    
    Args:
        center_ned: 环心位置（NED坐标）
        radius_m: 环半径（米）
        frame_id: 参考坐标系ID
        stamp: 时间戳
        ns: 命名空间
        marker_id: 标记ID
        samples: 圆周采样点数（默认48，高精度圆形）
        
    Returns:
        Marker: LINE_STRIP 类型闭合环
        
    说明：
        - 红色（1.0, 0.25, 0.25），半透明(0.55)
        - 线宽 0.06m
        - 高度略高于中心(+0.02m)，视觉上浮于地面
    """
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
    """Zenoh -> ROS2 可视化桥接节点。
    
    订阅Zenoh话题并将合成场景（海底、电缆、真值）转换为
    Foxglove可视化的ROS2消息流，同时支持模拟和实时两种模式。
    
    订阅话题（Zenoh）：
      - Z_PATH_SEABED_CLOUD: 海底点云JSON
      - Z_PATH_CABLE_MARKER: 电缆路径JSON
      - Z_PATH_TRUTH_POSE: 真值位姿JSON
      - Z_PATH_HISTORY_TRAIL: 历史轨迹JSON
      - Z_PATH_VIEW_RANGE: 搜索范围JSON
      
    发布话题（ROS2）：
      - /auv/visual/seabed_cloud: PointCloud2
      - /auv/visual/seabed_mesh: Marker (TRIANGLE_LIST)
      - /auv/visual/cable_marker: Marker (LINE_STRIP)
      - /auv/visual/auv_body: Marker (CYLINDER)
      - /auv/visual/truth_marker: Marker (ARROW)
      - /auv/visual/history_trail: Marker (LINE_STRIP with colors)
      - /auv/visual/view_range: Marker (LINE_STRIP 环)
      - /tf: TransformStamped (真值坐标系)
      - /auv/mock/scene: String (场景元数据摘要)
      
    模式：
      - mock_mode=true: 使用VirtualEnvironment模拟轨迹
      - mock_mode=false + Zenoh活跃: 实时来自仿真的数据
      - Zenoh超时: 自动降低为模拟模式
    """
    
    def __init__(self) -> None:
        super().__init__('zenoh_viz_bridge_node')

        default_params = str(PROJECT_ROOT / 'brain_linux' / 'config' / 'params.yaml')
        self.declare_parameter('params_file', default_params)
        self.declare_parameter('mock_mode', False)
        self.declare_parameter('allow_synthetic_scene_fallback', True)
        self.declare_parameter('publish_sim_ground_truth', True)
        self.declare_parameter('mock_fallback_timeout_s', 3.0)
        self.declare_parameter('frame_id', 'world')
        self.declare_parameter('truth_frame_id', 'truth_link')
        self.declare_parameter('terrain_key', Z_PATH_SEABED_CLOUD)
        self.declare_parameter('cable_key', Z_PATH_CABLE_MARKER)
        self.declare_parameter('truth_key', Z_PATH_TRUTH_POSE)
        self.declare_parameter('trail_key', Z_PATH_HISTORY_TRAIL)
        self.declare_parameter('range_key', Z_PATH_VIEW_RANGE)
        self.declare_parameter('ground_truth_key', Z_PATH_GROUND_TRUTH)
        self.declare_parameter('pc_cmd_raw_key', Z_PATH_PC_CMD_RAW)

        self.params_file = str(self.get_parameter('params_file').value)
        self.mock_mode = bool(self.get_parameter('mock_mode').value)
        self.allow_synthetic_scene_fallback = bool(
            self.get_parameter('allow_synthetic_scene_fallback').value)
        self.publish_sim_ground_truth = bool(self.get_parameter('publish_sim_ground_truth').value)
        self.mock_fallback_timeout_s = float(self.get_parameter('mock_fallback_timeout_s').value)
        self.frame_id = str(self.get_parameter('frame_id').value)
        self.truth_frame_id = str(self.get_parameter('truth_frame_id').value)

        cfg = self._load_config(self.params_file).get('digital_twin', {})
        self.terrain_key = str(cfg.get('terrain_topic_key', self.get_parameter('terrain_key').value))
        self.cable_key = str(cfg.get('cable_topic_key', self.get_parameter('cable_key').value))
        self.truth_key = str(cfg.get('truth_topic_key', self.get_parameter('truth_key').value))
        self.trail_key = str(cfg.get('history_topic_key', self.get_parameter('trail_key').value))
        self.range_key = str(cfg.get('view_topic_key', self.get_parameter('range_key').value))
        self.gt_key = str(cfg.get('ground_truth_topic_key', self.get_parameter('ground_truth_key').value))
        self.pc_cmd_raw_key = str(self.get_parameter('pc_cmd_raw_key').value)

        self.virtual_env = VirtualEnvironment(cfg)
        self._session = None
        self._subscribers = []
        self._last_live_rx_ns = 0
        self._live_terrain: dict[str, Any] | None = None
        self._live_cable: dict[str, Any] | None = None
        self._live_truth: dict[str, Any] | None = None
        self._live_trail: dict[str, Any] | None = None
        self._live_range: dict[str, Any] | None = None
        self._live_layer_monotonic_s: dict[str, float] = {}
        self._scene_live_signature: tuple[str, ...] | None = None
        self._tracking: dict[str, Any] = {}
        self._inspection_status = InspectionStatus()
        self._magnetic_ned_t: list[float] | None = None
        self._emergency_active = False
        self._emergency_status: dict[str, Any] = {}
        self._mock_tick = 0

        self.cloud_pub = self.create_publisher(PointCloud2, '/auv/visual/seabed_cloud', 10)
        self.mesh_pub = self.create_publisher(Marker, '/auv/visual/seabed_mesh', 10)
        self.cable_pub = self.create_publisher(Marker, '/auv/visual/cable_marker', 10)
        self.body_pub = self.create_publisher(Marker, '/auv/visual/auv_body', 10)
        self.truth_pub = self.create_publisher(Marker, '/auv/visual/truth_marker', 10)
        self.trail_pub = self.create_publisher(Marker, '/auv/visual/history_trail', 10)
        self.range_pub = self.create_publisher(Marker, '/auv/visual/view_range', 10)
        self.search_corridor_pub = self.create_publisher(Marker, '/auv/visual/search_corridor', 10)
        self.search_pattern_pub = self.create_publisher(Marker, '/auv/visual/search_pattern', 10)
        self.detection_link_pub = self.create_publisher(Marker, '/auv/visual/detection_link', 10)
        self.cable_target_pub = self.create_publisher(Marker, '/auv/visual/cable_target', 10)
        self.mission_label_pub = self.create_publisher(Marker, '/auv/visual/mission_label', 10)
        self.cable_estimate_pub = self.create_publisher(Marker, '/auv/visual/cable_estimate', 10)
        self.burial_estimate_pub = self.create_publisher(Marker, '/auv/visual/burial_estimate', 10)
        self.position_uncertainty_pub = self.create_publisher(Marker, '/auv/visual/position_uncertainty', 10)
        self.magnetic_vector_pub = self.create_publisher(Marker, '/auv/visual/magnetic_vector', 10)
        self.fwhm_span_pub = self.create_publisher(Marker, '/auv/visual/fwhm_span', 10)
        self.perception_label_pub = self.create_publisher(Marker, '/auv/visual/perception_label', 10)
        self.perception_text_pub = self.create_publisher(String, '/auv/visual/perception_text', 10)
        self.mission_display_state_pub = self.create_publisher(String, '/auv/visual/mission_state', 10)
        self.emergency_command_pub = self.create_publisher(String, '/auv/emergency/command', 10)
        self.mock_scene_pub = self.create_publisher(String, '/auv/mock/scene', 10)
        self.gt_pub = self.create_publisher(PoseStamped, '/auv/sensors/ground_truth', 50)
        self.create_subscription(String, '/auv/cable/tracking', self._on_tracking, 10)
        self.create_subscription(String, '/auv/cable/operational_status', self._on_inspection_status, 10)
        self.create_subscription(MagneticField, '/auv/sensors/magnetic', self._on_magnetic, 20)
        self.create_subscription(String, '/auv/emergency/status', self._on_emergency_status, 10)
        self.tf_broadcaster = TransformBroadcaster(self)

        self._open_zenoh()
        self.create_timer(0.1, self._on_timer)
        self.get_logger().info('zenoh_viz_bridge_node started')

    @staticmethod
    def _load_config(path: str) -> dict:
        """从YAML文件加载配置。
        
        Args:
            path: 配置文件路径
            
        Returns:
            dict: 解析后的配置字典，若文件不存在返回空字典
        """
        p = Path(path)
        if not p.exists():
            return {}
        with p.open('r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
        return data if isinstance(data, dict) else {}

    def _open_zenoh(self) -> None:
        """初始化 Zenoh 会话并订阅所有场景话题。
        
        若Zenoh不可用或连接失败，节点自动降级为模拟模式。
        """
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
        _sub(self.gt_key, self._on_ground_truth)
        # Console commands are control-plane traffic.  They must not refresh
        # the scene-data watchdog, otherwise the periodic ESTOP heartbeat can
        # suppress the terrain/cable fallback for the whole emergency ascent.
        self._subscribers.append(
            self._session.declare_subscriber(
                self.pc_cmd_raw_key,
                self._make_cb(self._on_pc_command, mark_live=False),
            )
        )

    def _on_pc_command(self, data: dict[str, Any]) -> None:
        """Forward only explicit console emergency semantics into ROS 2."""
        event = str(data.get('event', '')).strip().upper()
        action = str(data.get('emergency_action', '')).strip().upper()
        if event not in {'ESTOP', 'ESTOP_RESET'} and action not in {'SURFACE', 'CLEAR'}:
            return
        active = bool(data.get('emergency_latched', action == 'SURFACE')) and action != 'CLEAR'
        payload = {
            'state': 'EMERGENCY_SURFACE' if active else 'CLEAR',
            'active': active,
            'surface_depth_m': float(data.get('surface_depth_m', 0.5)),
            'source': str(data.get('source', 'console_zenoh')),
            'event': event,
            'ts': float(data.get('ts', time.time())),
        }
        self._emergency_active = active
        self.emergency_command_pub.publish(
            String(data=json.dumps(payload, ensure_ascii=False, allow_nan=False))
        )

    def _on_emergency_status(self, message: String) -> None:
        try:
            payload = json.loads(message.data)
        except (TypeError, ValueError, json.JSONDecodeError):
            return
        if not isinstance(payload, dict):
            return
        self._emergency_status = payload
        self._emergency_active = bool(payload.get('active', False))

    def _publish_mission_display_state(self) -> None:
        if self._emergency_active:
            state = str(self._emergency_status.get('state', 'EMERGENCY_SURFACE')).upper()
        elif (getattr(self, '_inspection_geometry_enabled', False)
              and self._inspection_status.status is not None):
            state = self._inspection_status.phase(time.monotonic())
        elif (not self.allow_synthetic_scene_fallback and self._tracking
              and time.monotonic() - getattr(
                  self, '_tracking_received_monotonic_s', float('-inf'))
              >= self.mock_fallback_timeout_s):
            state = 'STATUS_STALE'
        else:
            diagnostics = self._tracking.get('diagnostics')
            diagnostics = diagnostics if isinstance(diagnostics, dict) else {}
            state = str(diagnostics.get('mission_phase', self._tracking.get('mode', 'WAITING'))).upper()
        self.mission_display_state_pub.publish(String(data=state))

    def _on_inspection_status(self, message: String) -> None:
        try:
            payload = json.loads(message.data)
        except (TypeError, ValueError):
            return
        self._inspection_status.accept(payload, time.monotonic())

    def _make_cb(self, handler, *, mark_live: bool = True):
        """创建Zenoh订阅回调（JSON解析包装）。
        
        Args:
            handler: 处理解析后JSON数据的函数
            
        Returns:
            callable: Zenoh订阅回调函数
            
        说明：
            自动记录接收时间戳用于超时检测，若JSON解析失败则静默忽略。
        """
        def _cb(sample):
            payload = sample.payload.to_bytes() if hasattr(sample.payload, 'to_bytes') else bytes(sample.payload)
            try:
                data = json.loads(payload.decode('utf-8'))
            except Exception:
                return
            if mark_live:
                self._last_live_rx_ns = self.get_clock().now().nanoseconds
            handler(data)

        return _cb

    def _on_terrain(self, data: dict[str, Any]) -> None:
        """接收海底地形点云数据。"""
        self._live_terrain = data
        self._live_layer_monotonic_s['terrain'] = time.monotonic()

    def _on_cable(self, data: dict[str, Any]) -> None:
        """接收电缆路径点列数据。"""
        self._live_cable = data
        self._live_layer_monotonic_s['cable'] = time.monotonic()

    def _on_truth(self, data: dict[str, Any]) -> None:
        """接收真值位姿数据（位置+RPY）。"""
        self._live_truth = data
        self._live_layer_monotonic_s['truth'] = time.monotonic()

    def _on_trail(self, data: dict[str, Any]) -> None:
        """接收历史轨迹点列数据。"""
        self._live_trail = data
        self._live_layer_monotonic_s['trail'] = time.monotonic()

    def _on_range(self, data: dict[str, Any]) -> None:
        """接收搜索范围配置（中心+半径）。"""
        self._live_range = data
        self._live_layer_monotonic_s['range'] = time.monotonic()

    def _on_tracking(self, message: String) -> None:
        """Cache cable-tracking evidence used by presentation markers."""
        try:
            payload = json.loads(message.data)
        except (TypeError, ValueError, json.JSONDecodeError):
            return
        if isinstance(payload, dict):
            self._tracking = payload
            self._tracking_received_monotonic_s = time.monotonic()
            diagnostics = payload.get('diagnostics')
            if isinstance(diagnostics, dict) and 'inspection_enabled' in diagnostics:
                self._inspection_geometry_enabled = bool(diagnostics['inspection_enabled'])

    def _on_magnetic(self, message: MagneticField) -> None:
        """Cache the NED magnetic vector (ROS SI units) for the 3D field glyph."""
        self._magnetic_ned_t = [
            float(message.magnetic_field.x),
            float(message.magnetic_field.y),
            float(message.magnetic_field.z),
        ]

    def _on_ground_truth(self, data: dict[str, Any]) -> None:
        """转发 sim 端 ground_truth payload 到 ROS /auv/sensors/ground_truth。

        与 _on_truth (Z_PATH_TRUTH_POSE) 不同：此回调消费 Z_PATH_GROUND_TRUTH，
        不依赖 mock fallback，直接桥接 sim → ROS PoseStamped 供 benchmark 消费。
        """
        if not self.publish_sim_ground_truth or not rclpy.ok():
            return

        position = data.get(KEY_POSITION_NED)
        rpy = data.get(KEY_RPY_NED)
        if not isinstance(position, list) or not isinstance(rpy, list):
            return
        msg = PoseStamped()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = self.frame_id
        # NED z is positive-down; ROS world frame is z-up. Flip to match
        # /auv/state/filtered and downstream RViz/Foxglove conventions.
        msg.pose.position.x = float(position[0])
        msg.pose.position.y = float(position[1])
        msg.pose.position.z = float(-position[2])
        msg.pose.orientation = _rpy_to_quaternion(rpy)
        try:
            self.gt_pub.publish(msg)
        except Exception:
            if not rclpy.ok():
                return
            raise

        # Backfill _live_truth so the visualization marker tracks the real pose
        # if Z_PATH_TRUTH_POSE delivery is broken (avoids silent mock fallback).
        self._live_truth = {KEY_POSITION_NED: list(position), KEY_RPY_NED: list(rpy)}
        self._live_layer_monotonic_s['truth'] = time.monotonic()

    def _publish_scene(self, terrain: dict[str, Any], cable: dict[str, Any], truth: dict[str, Any], trail: dict[str, Any], view_range: dict[str, Any]) -> None:
        """将场景数据转换为ROS2 Marker/PointCloud2并发布。
        
        Args:
            terrain: 海底地形数据
            cable: 电缆路径数据
            truth: 真值位姿数据
            trail: 历史轨迹数据
            view_range: 搜索范围数据
            
        说明：
            - 地形以点云+网格三角形形式渲染
            - 电缆以线条形式渲染
            - 真值以AUV圆柱体+方向箭头形式渲染
            - 轨迹以彩色线条渲染（按时间渐变）
            - 搜索范围以环形渲染
        """
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
                self._publish_mission_geometry(points, truth, frame_id=frame_id, stamp=now)

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

        center = view_range.get(KEY_CENTER_NED)
        radius = float(view_range.get(KEY_RADIUS_M, 3.0))
        if isinstance(center, list):
            self.range_pub.publish(_make_range_ring(center, radius, frame_id=frame_id, stamp=now, ns='view_range', marker_id=4))

    def _clear_untrusted_scene_markers(self) -> None:
        """Remove previously published scene markers when live evidence expires."""
        marker = Marker()
        marker.header.frame_id = self.frame_id
        marker.header.stamp = self.get_clock().now().to_msg()
        self.cloud_pub.publish(_pointcloud2_from_points(
            [], self.frame_id, marker.header.stamp))
        marker.action = Marker.DELETEALL
        for publisher in (
            self.mesh_pub, self.cable_pub, self.body_pub, self.truth_pub,
            self.trail_pub, self.range_pub, self.search_corridor_pub,
            self.search_pattern_pub, self.detection_link_pub,
            self.cable_target_pub, self.mission_label_pub,
        ):
            publisher.publish(marker)

    def _publish_mission_geometry(self, cable_points: list[list[float]], truth: dict[str, Any], *, frame_id: str, stamp) -> None:
        """Publish presentation layers that explain the cable-inspection task."""
        diagnostics = self._tracking.get('diagnostics')
        diagnostics = diagnostics if isinstance(diagnostics, dict) else {}
        algorithm_version = str(diagnostics.get('algorithm_version', 'v1')).lower()
        mission_phase = str(diagnostics.get('mission_phase', self._tracking.get('mode', ''))).lower()
        pattern_mode = 'lawnmower' if algorithm_version == 'v2' and mission_phase in ('search', 'reacquire') else 'sine'
        try:
            amplitude = float(diagnostics.get('zigzag_probe_lateral_amplitude_m', 1.5))
            wavelength = float(diagnostics.get('zigzag_probe_wavelength_m', 24.0))
        except (TypeError, ValueError):
            amplitude, wavelength = 1.5, 24.0
        corridor_half_width = 15.0 if pattern_mode == 'lawnmower' else 5.0
        corridor, pattern = _mission_geometry(
            cable_points,
            corridor_half_width,
            pattern_mode=pattern_mode,
            lateral_amplitude_m=amplitude,
            wavelength_m=wavelength,
            lane_spacing_m=6.0,
        )
        active_plan = diagnostics.get('active_plan_waypoints_xy_m')
        if isinstance(active_plan, list) and len(active_plan) >= 2:
            actual_plan: list[list[float]] = []
            plan_z = float(self.virtual_env.config.seabed_z_m) - 0.35
            for point in active_plan:
                if not isinstance(point, (list, tuple)) or len(point) < 2:
                    continue
                try:
                    x_m, y_m = float(point[0]), float(point[1])
                except (TypeError, ValueError):
                    continue
                if math.isfinite(x_m) and math.isfinite(y_m):
                    actual_plan.append([x_m, y_m, plan_z])
            if len(actual_plan) >= 2:
                pattern = actual_plan
        if corridor:
            self.search_corridor_pub.publish(
                _make_line_strip(
                    corridor,
                    frame_id=frame_id,
                    stamp=stamp,
                    ns='search_corridor',
                    marker_id=30,
                    color=(0.15, 0.8, 0.95, 0.72),
                    width=0.08,
                )
            )
        if pattern:
            self.search_pattern_pub.publish(
                _make_line_strip(
                    pattern,
                    frame_id=frame_id,
                    stamp=stamp,
                    ns='algorithm_reference_path',
                    marker_id=31,
                    color=(0.95, 0.55, 0.12, 0.85),
                    width=0.07,
                )
            )

        position = truth.get(KEY_POSITION_NED, [0.0, 0.0, 0.0])
        if not isinstance(position, list) or len(position) < 3:
            return
        if getattr(self, '_inspection_geometry_enabled', False):
            self._publish_inspection_mission_target(position, frame_id=frame_id, stamp=stamp)
            return
        target = _nearest_cable_point(position, cable_points)
        if target is None:
            return

        mode = str(self._tracking.get('mode', '')).strip().upper()
        confidence = self._tracking.get('confidence')
        try:
            confidence_value = float(confidence)
        except (TypeError, ValueError):
            confidence_value = min(0.96, 0.28 + self._mock_tick / 260.0)

        if not mode:
            cycle_tick = self._mock_tick % 540
            if cycle_tick < 35:
                mode = 'LAUNCH'
            elif cycle_tick < 150:
                mode = 'SEARCH'
            elif cycle_tick < 205:
                mode = 'DETECT'
            elif cycle_tick < 480:
                mode = 'TRACK'
            else:
                mode = 'COMPLETE'

        cross_track = self._tracking.get('cross_track_m')
        if cross_track is None:
            cross_track = math.hypot(float(position[0]) - float(target[0]), float(position[1]) - float(target[1]))
        try:
            cross_track_text = f'{float(cross_track):.2f} m'
        except (TypeError, ValueError):
            cross_track_text = '--'

        target_color = (0.2, 1.0, 0.45, 0.95) if confidence_value >= 0.65 else (1.0, 0.65, 0.1, 0.95)
        self.cable_target_pub.publish(
            _make_sphere_marker(
                target,
                frame_id=frame_id,
                stamp=stamp,
                ns='cable_target',
                marker_id=32,
                color=target_color,
                diameter=0.55,
            )
        )
        self.detection_link_pub.publish(
            _make_line_strip(
                [position, target],
                frame_id=frame_id,
                stamp=stamp,
                ns='detection_link',
                marker_id=33,
                color=target_color,
                width=0.045,
            )
        )
        if self._emergency_active:
            emergency_state = str(
                self._emergency_status.get('state', 'EMERGENCY_SURFACE')
            ).upper()
            depth = self._finite_number(self._emergency_status.get('current_depth_m'))
            depth_text = '--' if depth is None else f'{depth:.2f} m'
            label = f'ESTOP  |  {emergency_state}  |  depth {depth_text}'
        else:
            label = f'{mode}  |  cable {cross_track_text}  |  confidence {confidence_value:.2f}'
        self.mission_label_pub.publish(
            _make_text_marker(position, label, frame_id=frame_id, stamp=stamp, ns='mission_label', marker_id=34)
        )
        self._publish_perception_geometry(
            cable_points,
            position,
            target,
            diagnostics,
            frame_id=frame_id,
            stamp=stamp,
        )

    def _publish_inspection_mission_target(self, position, *, frame_id, stamp):
        """Draw the estimated target only; scene cable truth is a reference layer."""
        geometry = inspection_geometry(
            self._tracking, float(self.virtual_env.config.seabed_z_m),
            time.monotonic() - getattr(self, '_tracking_received_monotonic_s', float('-inf')))
        target = geometry.position_ned
        if target is None:
            for publisher, namespace, marker_id in (
                    (self.cable_target_pub, 'cable_target', 32),
                    (self.detection_link_pub, 'detection_link', 33)):
                marker = Marker()
                marker.header.frame_id, marker.header.stamp = frame_id, stamp
                marker.ns, marker.id, marker.action = namespace, marker_id, Marker.DELETE
                publisher.publish(marker)
        else:
            marker = _make_sphere_marker(list(target), frame_id=frame_id, stamp=stamp,
                                        ns='cable_target', marker_id=32,
                                        color=(.9,.25,1.,.95), diameter=.55)
            if geometry.burial_m is None:
                marker.scale.z = .06
            marker.lifetime.sec = 2
            self.cable_target_pub.publish(marker)
            marker = _make_line_strip([position, list(target)], frame_id=frame_id, stamp=stamp,
                                     ns='detection_link', marker_id=33,
                                     color=(.9,.25,1.,.95), width=.045)
            marker.lifetime.sec = 2
            self.detection_link_pub.publish(marker)
        phase = self._inspection_status.phase(time.monotonic())
        if self._emergency_active:
            phase = str(self._emergency_status.get('state', 'EMERGENCY_SURFACE'))
        marker = _make_text_marker(position, phase + ' | ESTIMATED TARGET / REFERENCE PLANE',
                                  frame_id=frame_id, stamp=stamp, ns='mission_label', marker_id=34)
        marker.lifetime.sec = 2
        self.mission_label_pub.publish(marker)

    @staticmethod
    def _finite_number(value: Any) -> float | None:
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return None
        return numeric if math.isfinite(numeric) else None

    def _publish_perception_geometry(
        self,
        cable_points: list[list[float]],
        auv_position: list[float],
        nearest_truth: list[float],
        diagnostics: dict[str, Any],
        *,
        frame_id: str,
        stamp,
    ) -> None:
        """Render estimator, burial, magnetic and FWHM evidence without hiding truth."""
        if (getattr(self, '_inspection_geometry_enabled', False) or not self._tracking
                or self._tracking.get('mode') == 'SENSOR_DEGRADED'):
            self._publish_inspection_geometry(frame_id=frame_id, stamp=stamp)
            return
        estimate_xy = self._tracking.get('estimated_cable_xy_m')
        if not isinstance(estimate_xy, list) or len(estimate_xy) < 2:
            estimate_xy = [float(nearest_truth[0]), float(nearest_truth[1])]

        burial = self._finite_number(self._tracking.get('burial_depth_m'))
        burial_sigma = self._finite_number(self._tracking.get('burial_sigma_m'))
        seabed_z = float(self.virtual_env.config.seabed_z_m)
        estimate_z = seabed_z + burial if burial is not None and burial >= 0.0 else float(nearest_truth[2])
        estimate_position = [float(estimate_xy[0]), float(estimate_xy[1]), estimate_z]

        self.cable_estimate_pub.publish(
            _make_sphere_marker(
                estimate_position,
                frame_id=frame_id,
                stamp=stamp,
                ns='estimated_cable_position',
                marker_id=40,
                color=(0.9, 0.25, 1.0, 0.95),
                diameter=0.48,
            )
        )
        if burial is not None and burial >= 0.0:
            self.burial_estimate_pub.publish(
                _make_arrow_between(
                    [estimate_position[0], estimate_position[1], seabed_z],
                    estimate_position,
                    frame_id=frame_id,
                    stamp=stamp,
                    ns='estimated_burial_depth',
                    marker_id=41,
                    color=(0.95, 0.35, 0.9, 0.95),
                )
            )

        position_sigma = self._finite_number(diagnostics.get('observation_line_sigma_m'))
        if position_sigma is None:
            width_sigma = self._finite_number(diagnostics.get('fwhm_width_sigma_m'))
            position_sigma = None if width_sigma is None else 0.5 * width_sigma
        if position_sigma is None:
            # A burial-depth uncertainty is not a lateral covariance, but while
            # confirming a cable it gives a conservative visible uncertainty
            # radius instead of implying an exact position.
            position_sigma = self._finite_number(diagnostics.get('fwhm_burial_depth_sigma_m'))
        if position_sigma is not None:
            self.position_uncertainty_pub.publish(
                _make_uncertainty_ring(
                    estimate_position,
                    position_sigma,
                    frame_id=frame_id,
                    stamp=stamp,
                    ns='estimated_position_2sigma',
                    marker_id=42,
                )
            )

        magnetic_strength = self._finite_number(self._tracking.get('magnetic_strength_nt'))
        magnetic_snr = self._finite_number(self._tracking.get('magnetic_snr_db'))
        magnetic_confidence = self._finite_number(self._tracking.get('magnetic_confidence'))
        if self._magnetic_ned_t is not None:
            bx, by, bz = (component * 1.0e9 for component in self._magnetic_ned_t)
            magnitude = math.sqrt(bx * bx + by * by + bz * bz)
            if magnitude > 1.0e-9:
                scale = 3.0 / magnitude
                endpoint = [
                    float(auv_position[0]) + bx * scale,
                    float(auv_position[1]) + by * scale,
                    float(auv_position[2]) + bz * scale,
                ]
                self.magnetic_vector_pub.publish(
                    _make_arrow_between(
                        auv_position,
                        endpoint,
                        frame_id=frame_id,
                        stamp=stamp,
                        ns='magnetic_vector_ned',
                        marker_id=43,
                        color=(1.0, 0.45, 0.12, 0.95),
                    )
                )
                if magnetic_strength is None:
                    magnetic_strength = magnitude

        fwhm_left = self._finite_number(diagnostics.get('fwhm_left_x_m'))
        fwhm_right = self._finite_number(diagnostics.get('fwhm_right_x_m'))
        fwhm_peak = self._finite_number(diagnostics.get('fwhm_peak_x_m'))
        fwhm_width = self._finite_number(diagnostics.get('fwhm_width_m'))
        heading_deg = self._finite_number(self._tracking.get('cable_heading_deg')) or 0.0
        heading_rad = math.radians(heading_deg)
        normal = [-math.sin(heading_rad), math.cos(heading_rad)]
        if fwhm_left is not None and fwhm_right is not None:
            # FWHM crossings are expressed in scan-centred coordinates while
            # the rendered estimate sits at the fitted peak.
            peak_x = 0.0 if fwhm_peak is None else fwhm_peak
            left_offset = fwhm_left - peak_x
            right_offset = fwhm_right - peak_x
            span_z = seabed_z - 0.12
            span = [
                [estimate_position[0] + normal[0] * left_offset, estimate_position[1] + normal[1] * left_offset, span_z],
                [estimate_position[0] + normal[0] * right_offset, estimate_position[1] + normal[1] * right_offset, span_z],
            ]
            self.fwhm_span_pub.publish(
                _make_line_strip(
                    span,
                    frame_id=frame_id,
                    stamp=stamp,
                    ns='fwhm_half_max_span',
                    marker_id=44,
                    color=(1.0, 0.2, 0.65, 0.95),
                    width=0.12,
                )
            )

        fwhm_valid = diagnostics.get('fwhm_valid')
        source = str(diagnostics.get('source', 'legacy_amplitude_inversion'))
        burial_text = '--' if burial is None else f'{burial:.2f} m'
        sigma_text = '--' if burial_sigma is None else f'{burial_sigma:.2f} m'
        mag_text = '--' if magnetic_strength is None else f'{magnetic_strength:.0f} nT'
        snr_text = '--' if magnetic_snr is None else f'{magnetic_snr:.1f} dB'
        fwhm_text = '--' if fwhm_width is None else f'{fwhm_width:.2f} m'
        perception_label = (
            f'EST cable=({estimate_position[0]:.1f}, {estimate_position[1]:.1f}) m\n'
            f'burial={burial_text}  sigma={sigma_text}\n'
            f'|B|={mag_text}  SNR={snr_text}  FWHM={fwhm_text}'
        )
        label_anchor = [estimate_position[0], estimate_position[1], seabed_z - 1.0]
        self.perception_label_pub.publish(
            _make_text_marker(label_anchor, perception_label, frame_id=frame_id, stamp=stamp, ns='perception_label', marker_id=45)
        )
        self.perception_text_pub.publish(String(data=(
            f'ESTIMATOR: {source}\n'
            f'cable position: x={estimate_position[0]:.2f} m, y={estimate_position[1]:.2f} m\n'
            f'burial: {burial_text}, sigma: {sigma_text}\n'
            f'magnetic: {mag_text}, SNR: {snr_text}, confidence: '
            f'{"--" if magnetic_confidence is None else f"{magnetic_confidence:.3f}"}\n'
            f'FWHM: {fwhm_text}, valid: {fwhm_valid if fwhm_valid is not None else "not active"}'
        )))

    def _publish_inspection_geometry(self, *, frame_id: str, stamp) -> None:
        reference_z = float(self.virtual_env.config.seabed_z_m)
        state = inspection_geometry(
            self._tracking, reference_z,
            time.monotonic() - getattr(self, '_tracking_received_monotonic_s', float('-inf')),
        )
        def remove(publisher, namespace, marker_id):
            marker = Marker()
            marker.header.frame_id, marker.header.stamp = frame_id, stamp
            marker.ns, marker.id, marker.action = namespace, marker_id, Marker.DELETE
            publisher.publish(marker)

        remove(self.magnetic_vector_pub, 'magnetic_vector_ned', 43)

        def emit(publisher, marker):
            marker.lifetime.sec = 2
            publisher.publish(marker)

        position = state.position_ned
        if position is None:
            remove(self.cable_estimate_pub, 'estimated_cable_position', 40)
            remove(self.perception_label_pub, 'perception_label', 45)
        else:
            marker = _make_sphere_marker(list(position), frame_id=frame_id, stamp=stamp,
                ns='estimated_cable_position', marker_id=40, color=(0.9,0.25,1.0,0.95), diameter=0.48)
            if state.burial_m is None:
                marker.scale.z = 0.06  # A flat projection, not a resolved 3D point.
            emit(self.cable_estimate_pub, marker)
            emit(self.perception_label_pub, _make_text_marker(
                [position[0],position[1],reference_z-1.0], state.label,
                frame_id=frame_id, stamp=stamp, ns='perception_label', marker_id=45))
        if position is not None and state.burial_m is not None:
            emit(self.burial_estimate_pub, _make_arrow_between(
                [position[0],position[1],reference_z], list(position), frame_id=frame_id,
                stamp=stamp, ns='estimated_burial_depth', marker_id=41, color=(.95,.35,.9,.95)))
        else:
            remove(self.burial_estimate_pub, 'estimated_burial_depth', 41)
        if position is not None and state.lateral_sigma_m is not None:
            emit(self.position_uncertainty_pub, _make_uncertainty_ring(
                list(position), state.lateral_sigma_m, frame_id=frame_id, stamp=stamp,
                ns='estimated_position_2sigma', marker_id=42))
        else:
            remove(self.position_uncertainty_pub, 'estimated_position_2sigma', 42)
        if position is not None and state.width_m is not None and state.heading_deg is not None:
            angle = math.radians(state.heading_deg)
            points = [[position[0]-math.sin(angle)*side*state.width_m/2,
                       position[1]+math.cos(angle)*side*state.width_m/2, reference_z-.12] for side in (-1,1)]
            emit(self.fwhm_span_pub, _make_line_strip(points, frame_id=frame_id, stamp=stamp,
                ns='fwhm_half_max_span', marker_id=44, color=(1.,.2,.65,.95), width=.12))
        else:
            remove(self.fwhm_span_pub, 'fwhm_half_max_span', 44)
        self.perception_text_pub.publish(String(data=self._inspection_status.text(state, time.monotonic())))

    def _publish_mock_scene_summary(self, *, sample_index: int, position_ned: list[float], rpy_ned: list[float], mode: str) -> None:
        """发布场景元数据摘要（用于Foxglove仪表板）。
        
        Args:
            sample_index: 采样索引（用于追踪回放进度）
            position_ned: 当前位置（NED坐标）
            rpy_ned: 当前姿态（欧拉角）
            mode: 模式标签（"mock"或"live"）
            
        说明：
            发布JSON格式的场景摘要到/auv/mock/scene话题，
            包括可见图层、有效载荷大小等可视化统计信息。
        """
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
        """定时发布场景（100ms周期）。
        
        逻辑：
          1. 若在模拟模式或Zenoh超时，使用VirtualEnvironment模拟
          2. 否则从_live_*缓存读取最新Zenoh数据并发布
          3. 若Zenoh无真值数据，不发布任何内容
        """
        if not rclpy.ok():
            return

        self._publish_mission_display_state()
        # Status must keep expiring even if the live scene/pose stops arriving.
        if getattr(self, '_inspection_geometry_enabled', False):
            self._publish_inspection_geometry(
                frame_id=self.frame_id, stamp=self.get_clock().now().to_msg())

        if not self.allow_synthetic_scene_fallback:
            now_mono = time.monotonic()
            def fresh(name: str) -> bool:
                stamp = self._live_layer_monotonic_s.get(name)
                return (stamp is not None and 0. <= now_mono - stamp
                        < self.mock_fallback_timeout_s)

            live = tuple(name for name in ('truth', 'terrain', 'cable', 'trail', 'range')
                         if fresh(name) and getattr(self, f'_live_{name}') is not None)
            if live != self._scene_live_signature:
                self._clear_untrusted_scene_markers()
                self._scene_live_signature = live
            if 'truth' not in live:
                return
            terrain = self._live_terrain if 'terrain' in live else {}
            cable = self._live_cable if 'cable' in live else {}
            trail = self._live_trail if 'trail' in live else {}
            view_range = self._live_range if 'range' in live else {}
            self._publish_scene(terrain, cable, self._live_truth, trail, view_range)
            return

        now_ns = self.get_clock().now().nanoseconds
        have_live = self._last_live_rx_ns > 0 and (now_ns - self._last_live_rx_ns) < int(self.mock_fallback_timeout_s * 1e9)

        if self.mock_mode or not have_live:
            position, rpy = self.virtual_env.sample_mock_pose(self._mock_tick)
            payloads = self.virtual_env.build_visual_payloads(position_ned=position, rpy_ned=rpy, publish_terrain=True)
            try:
                self._publish_scene(
                    payloads[Z_PATH_SEABED_CLOUD],
                    payloads[Z_PATH_CABLE_MARKER],
                    payloads[Z_PATH_TRUTH_POSE],
                    payloads[Z_PATH_HISTORY_TRAIL],
                    payloads[Z_PATH_VIEW_RANGE],
                )
                self._publish_mock_scene_summary(sample_index=self._mock_tick, position_ned=position, rpy_ned=rpy, mode='mock')
            except Exception:
                if not rclpy.ok():
                    return
                raise
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
        try:
            self._publish_scene(terrain, cable, self._live_truth, trail, view_range)
            self._publish_mock_scene_summary(
                sample_index=self._mock_tick,
                position_ned=self._live_truth.get(KEY_POSITION_NED, [0.0, 0.0, 0.0]),
                rpy_ned=self._live_truth.get(KEY_RPY_NED, [0.0, 0.0, 0.0]),
                mode='live',
            )
        except Exception:
            if not rclpy.ok():
                return
            raise

    def destroy_node(self):
        """清理资源：关闭Zenoh会话和订阅。"""
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

##
# @brief Run the visualization bridge node until the ROS context stops.
# @param args Optional ROS CLI arguments.
def main(args=None) -> None:
    """Zenoh可视化桥接节点入口点。"""
    rclpy.init(args=args)
    node = ZenohVizBridgeNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    except ExternalShutdownException:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()

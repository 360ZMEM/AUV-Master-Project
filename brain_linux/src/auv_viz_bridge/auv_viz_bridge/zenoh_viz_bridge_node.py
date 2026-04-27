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

    def _make_cb(self, handler):
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
            self._last_live_rx_ns = self.get_clock().now().nanoseconds
            handler(data)

        return _cb

    def _on_terrain(self, data: dict[str, Any]) -> None:
        """接收海底地形点云数据。"""
        self._live_terrain = data

    def _on_cable(self, data: dict[str, Any]) -> None:
        """接收电缆路径点列数据。"""
        self._live_cable = data

    def _on_truth(self, data: dict[str, Any]) -> None:
        """接收真值位姿数据（位置+RPY）。"""
        self._live_truth = data

    def _on_trail(self, data: dict[str, Any]) -> None:
        """接收历史轨迹点列数据。"""
        self._live_trail = data

    def _on_range(self, data: dict[str, Any]) -> None:
        """接收搜索范围配置（中心+半径）。"""
        self._live_range = data

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


def main(args=None) -> None:
    """Zenoh可视化桥接节点入口点。"""
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

#!/usr/bin/env python3
"""AUV 本地化节点。

该节点负责融合 IMU、DVL、深度等传感器数据，输出滤波后的位姿与速度
估计，供控制与决策模块消费。

ES-EKF localization node.

Inputs:
- /auv/sensors/imu (sensor_msgs/Imu)
- /auv/sensors/dvl (geometry_msgs/TwistStamped)
- /auv/sensors/depth (std_msgs/Float32)

Outputs:
- /auv/state/filtered (nav_msgs/Odometry)
- /auv/state/covariance (std_msgs/Float32MultiArray)
- /tf (world -> auv/base_link)
- /tf_static (auv/base_link -> sensor links)

增强特性：
- 自动位置对齐：首次收到 DVL 或深度观测时，自动初始化滤波器位置
- 动态初始化日志：记录初始化时间和对齐位置
- 兼容原有行为：如已配置 init_pos，则按原配置初始化
"""

from __future__ import annotations

import time
from pathlib import Path
import sys
import importlib.util
import os

import numpy as np
import rclpy
from geometry_msgs.msg import TwistStamped
from geometry_msgs.msg import TransformStamped
from nav_msgs.msg import Odometry
from rcl_interfaces.msg import SetParametersResult
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from sensor_msgs.msg import Imu
from std_msgs.msg import Float32, Float32MultiArray, String
from tf2_ros import StaticTransformBroadcaster, TransformBroadcaster
from auv_interfaces.msg import SensorStatus, Setpoint
import yaml


def _format_confidence_markdown(confidence: float) -> str:
    return f'## {confidence:.2f}'


def _format_power_markdown(voltage_v: float, threshold_v: float) -> str:
    if voltage_v < threshold_v:
        return f'## LOW POWER: {voltage_v:.2f}V'
    return f'## POWER: {voltage_v:.2f}V'

def _resolve_project_root() -> Path:
    env_root = Path(str(os.environ.get('AUV_PROJECT_ROOT', ''))).expanduser() if os.environ.get('AUV_PROJECT_ROOT') else None
    if env_root and (env_root / 'algorithm').exists():
        return env_root

    try:
        from ament_index_python.packages import get_package_share_directory

        share_dir = Path(get_package_share_directory('auv_localization')).resolve()
        candidate = share_dir.parents[3]
        if (candidate / 'algorithm').exists():
            return candidate
    except Exception:
        pass

    cur = Path(__file__).resolve()
    for parent in cur.parents:
        if (parent / 'algorithm').exists():
            return parent

    raise RuntimeError('cannot resolve project root containing algorithm directory')


PROJECT_ROOT = _resolve_project_root()
ALGO_DIR = PROJECT_ROOT / 'algorithm'
def _load_es_ekf_class():
    module_path = ALGO_DIR / 'es_ekf.py'
    spec = importlib.util.spec_from_file_location('auv_algorithm_es_ekf', str(module_path))
    if spec is None or spec.loader is None:
        raise RuntimeError(f'failed to load ES-EKF module: {module_path}')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.ES_EKF


ES_EKF = _load_es_ekf_class()


def _parse_xyz(value: object) -> tuple[float, float, float]:
    """Parse a 3D offset parameter from a string or sequence."""
    if isinstance(value, (list, tuple)) and len(value) >= 3:
        return float(value[0]), float(value[1]), float(value[2])
    if isinstance(value, str):
        parts = [part.strip() for part in value.split(',') if part.strip()]
        if len(parts) >= 3:
            return float(parts[0]), float(parts[1]), float(parts[2])
    return 0.0, 0.0, 0.0


class AUVLocalizationNode(Node):
    """AUV 本地化节点。

    该节点融合 IMU、DVL、深度和控制目标信息，维护 ES-EKF 状态并发布
    /auv/state/filtered、/auv/state/covariance、/auv/sensors/status 以及相关 TF。
    """

    def __init__(self) -> None:
        """初始化本地化参数、滤波器、话题订阅和输出发布器。"""
        super().__init__('auv_localization_node')

        default_params = str(PROJECT_ROOT / 'brain_linux' / 'config' / 'params.yaml')
        self.declare_parameter('params_file', default_params)
        self.declare_parameter('filter_rate_hz', 20.0)
        self.declare_parameter('world_frame_id', 'world')
        self.declare_parameter('base_frame_id', 'auv/base_link')
        self.declare_parameter('imu_frame_id', 'auv/imu_link')
        self.declare_parameter('dvl_frame_id', 'auv/dvl_link')
        self.declare_parameter('depth_frame_id', 'auv/depth_link')
        self.declare_parameter('camera_frame_id', 'auv/camera_link')
        self.declare_parameter('sonar_frame_id', 'auv/sonar_link')
        self.declare_parameter('imu_frame_offset_xyz', '0.0,0.0,0.0')
        self.declare_parameter('dvl_frame_offset_xyz', '0.0,0.0,0.0')
        self.declare_parameter('depth_frame_offset_xyz', '0.0,0.0,0.0')
        self.declare_parameter('camera_frame_offset_xyz', '0.0,0.0,0.0')
        self.declare_parameter('sonar_frame_offset_xyz', '0.0,0.0,0.0')
        self.declare_parameter('publish_imu_tf', True)
        self.declare_parameter('publish_dvl_tf', True)
        self.declare_parameter('publish_depth_tf', True)
        self.declare_parameter('publish_camera_tf', False)
        self.declare_parameter('publish_sonar_tf', False)
        self.declare_parameter('publish_tf', True)
        self.declare_parameter('publish_static_tf', True)
        self.declare_parameter('publish_sensor_status', True)
        self.declare_parameter('publish_raw_state', False)
        self.declare_parameter('raw_state_topic', '/auv/state/raw_dr')
        self.declare_parameter('seabed_depth_m', 15.0)
        self.declare_parameter('seabed_proximity_margin_m', 1.5)
        self.declare_parameter('battery_low_voltage_threshold', 44.8)
        self.declare_parameter('nominal_voltage_v', 48.0)

        self.params_file = str(self.get_parameter('params_file').value)
        self.filter_rate_hz = float(self.get_parameter('filter_rate_hz').value)
        self.world_frame_id = str(self.get_parameter('world_frame_id').value)
        self.base_frame_id = str(self.get_parameter('base_frame_id').value)
        self.imu_frame_id = str(self.get_parameter('imu_frame_id').value)
        self.dvl_frame_id = str(self.get_parameter('dvl_frame_id').value)
        self.depth_frame_id = str(self.get_parameter('depth_frame_id').value)
        self.camera_frame_id = str(self.get_parameter('camera_frame_id').value)
        self.sonar_frame_id = str(self.get_parameter('sonar_frame_id').value)
        self.imu_frame_offset_xyz = _parse_xyz(self.get_parameter('imu_frame_offset_xyz').value)
        self.dvl_frame_offset_xyz = _parse_xyz(self.get_parameter('dvl_frame_offset_xyz').value)
        self.depth_frame_offset_xyz = _parse_xyz(self.get_parameter('depth_frame_offset_xyz').value)
        self.camera_frame_offset_xyz = _parse_xyz(self.get_parameter('camera_frame_offset_xyz').value)
        self.sonar_frame_offset_xyz = _parse_xyz(self.get_parameter('sonar_frame_offset_xyz').value)
        self.publish_imu_tf = bool(self.get_parameter('publish_imu_tf').value)
        self.publish_dvl_tf = bool(self.get_parameter('publish_dvl_tf').value)
        self.publish_depth_tf = bool(self.get_parameter('publish_depth_tf').value)
        self.publish_camera_tf = bool(self.get_parameter('publish_camera_tf').value)
        self.publish_sonar_tf = bool(self.get_parameter('publish_sonar_tf').value)
        self.publish_tf = bool(self.get_parameter('publish_tf').value)
        self.publish_static_tf = bool(self.get_parameter('publish_static_tf').value)
        self.publish_sensor_status = bool(self.get_parameter('publish_sensor_status').value)
        self.publish_raw_state = bool(self.get_parameter('publish_raw_state').value)
        self.raw_state_topic = str(self.get_parameter('raw_state_topic').value or '/auv/state/raw_dr')
        self.seabed_depth_m = float(self.get_parameter('seabed_depth_m').value)
        self.seabed_proximity_margin_m = float(self.get_parameter('seabed_proximity_margin_m').value)
        self.battery_low_voltage_threshold = float(self.get_parameter('battery_low_voltage_threshold').value)
        self.nominal_voltage_v = float(self.get_parameter('nominal_voltage_v').value)

        cfg = self._load_config(self.params_file)
        ekf_cfg = cfg.get('ekf', {})
        localization_cfg = dict(cfg.get('localization', {}) or {})
        self.use_imu_orientation_measurement = bool(
            localization_cfg.get('use_imu_orientation_measurement', False)
        )

        self.filter = ES_EKF(ekf_cfg)

        self._last_imu = np.zeros(3, dtype=float)
        self._last_gyro = np.zeros(3, dtype=float)
        self._last_imu_orientation = None
        self._last_dvl = None
        self._last_depth = None
        self._last_imu_ts = 0.0
        self._last_dvl_ts = 0.0
        self._last_depth_ts = 0.0
        self._last_imu_header_stamp = None  # 新增：保存IMU消息的Header Stamp
        self._last_dvl_header_stamp = None  # 新增：保存DVL消息的Header Stamp
        self._last_depth_header_stamp = None  # 新增：保存深度消息的Header Stamp
        self._last_loop_ts = time.time()
        self._last_predict_imu_ts = 0.0
        self._last_corrected_dvl_ts = 0.0
        self._last_corrected_depth_ts = 0.0
        self._latest_setpoint_depth_m: float | None = None
        self._filter_initialized_logged = False

        self.odom_pub = self.create_publisher(Odometry, '/auv/state/filtered', 10)
        self.raw_odom_pub = self.create_publisher(Odometry, self.raw_state_topic, 10)
        self.cov_pub = self.create_publisher(Float32MultiArray, '/auv/state/covariance', 10)
        self.status_pub = self.create_publisher(SensorStatus, '/auv/sensors/status', 10)
        self.depth_error_pub = self.create_publisher(Float32, '/auv/metrics/depth_error', 10)
        self.lateral_error_pub = self.create_publisher(Float32, '/auv/metrics/lateral_error', 10)
        self.confidence_text_pub = self.create_publisher(String, '/auv/display/confidence_text', 10)
        self.power_text_pub = self.create_publisher(String, '/auv/display/power_text', 10)
        self.tf_broadcaster = TransformBroadcaster(self)
        self.static_tf_broadcaster = StaticTransformBroadcaster(self)

        # QoS 降级：队列深度强制改为1，消除队列积压导致的时间戳滑移
        # 宁可丢弃旧包（Drop），也绝不能让旧包在队列里排队
        self.create_subscription(Imu, '/auv/sensors/imu', self._on_imu, 1)
        self.create_subscription(TwistStamped, '/auv/sensors/dvl', self._on_dvl, 1)
        self.create_subscription(Float32, '/auv/sensors/depth', self._on_depth, 1)
        self.create_subscription(Setpoint, '/auv/control/setpoint', self._on_setpoint, 10)

        if self.publish_static_tf:
            self._publish_static_transforms()

        self._filter_timer = self.create_timer(1.0 / max(self.filter_rate_hz, 1e-3), self._on_timer)
        self._param_callback = self.add_on_set_parameters_callback(self._on_parameters_changed)

        self._lat_count = 0
        self._lat_sum = 0.0
        self.create_timer(2.0, self._log_latency)

        self.get_logger().info('auv_localization_node started')
        self.get_logger().info(
            'TF config: '
            f'world_frame_id={self.world_frame_id}, '
            f'base_frame_id={self.base_frame_id}, '
            f'imu_frame_id={self.imu_frame_id}, '
            f'dvl_frame_id={self.dvl_frame_id}, '
            f'depth_frame_id={self.depth_frame_id}, '
            f'camera_frame_id={self.camera_frame_id}, '
            f'sonar_frame_id={self.sonar_frame_id}, '
            f'publish_tf={self.publish_tf}, '
            f'publish_static_tf={self.publish_static_tf}, '
            f'publish_imu_tf={self.publish_imu_tf}, '
            f'publish_dvl_tf={self.publish_dvl_tf}, '
            f'publish_depth_tf={self.publish_depth_tf}, '
            f'publish_camera_tf={self.publish_camera_tf}, '
            f'publish_sonar_tf={self.publish_sonar_tf}, '
            f'publish_sensor_status={self.publish_sensor_status}, '
            f'publish_raw_state={self.publish_raw_state}, '
            f'raw_state_topic={self.raw_state_topic}, '
            f'use_imu_orientation_measurement={self.use_imu_orientation_measurement}, '
            f'seabed_depth_m={self.seabed_depth_m}, '
            f'seabed_proximity_margin_m={self.seabed_proximity_margin_m}, '
            f'battery_low_voltage_threshold={self.battery_low_voltage_threshold}, '
            f'nominal_voltage_v={self.nominal_voltage_v}'
        )

    @staticmethod
    def _load_config(path: str) -> dict:
        """加载本地化参数 YAML，若不存在则返回空配置。"""
        p = Path(path)
        if not p.exists():
            return {}
        with p.open('r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
        return data if isinstance(data, dict) else {}

    def _on_imu(self, msg: Imu) -> None:
        """缓存最新 IMU 加速度和角速度。"""
        self._last_imu = np.array([
            msg.linear_acceleration.x,
            msg.linear_acceleration.y,
            msg.linear_acceleration.z,
        ], dtype=float)
        self._last_gyro = np.array([
            msg.angular_velocity.x,
            msg.angular_velocity.y,
            msg.angular_velocity.z,
        ], dtype=float)
        quat = np.array(
            [
                msg.orientation.w,
                msg.orientation.x,
                msg.orientation.y,
                msg.orientation.z,
            ],
            dtype=float,
        )
        quat_norm = float(np.linalg.norm(quat))
        if quat_norm > 1.0e-6:
            self._last_imu_orientation = quat / quat_norm
        # 严格保存消息的 Header Stamp，用于后续状态发布
        self._last_imu_header_stamp = msg.header.stamp
        self._last_imu_ts = float(msg.header.stamp.sec) + float(msg.header.stamp.nanosec) * 1e-9

    def _on_dvl(self, msg: TwistStamped) -> None:
        """缓存最新 DVL 速度测量。"""
        self._last_dvl = np.array([
            msg.twist.linear.x,
            msg.twist.linear.y,
            msg.twist.linear.z,
        ], dtype=float)
        # 严格保存消息的 Header Stamp
        self._last_dvl_header_stamp = msg.header.stamp
        self._last_dvl_ts = float(msg.header.stamp.sec) + float(msg.header.stamp.nanosec) * 1e-9

    def _on_depth(self, msg: Float32) -> None:
        """缓存最新深度测量。"""
        self._last_depth = float(msg.data)
        # Float32 没有 header，但我们可以从节点时钟获取时间戳（深度传感器通常没有独立时间源）
        # 这里使用IMU时间戳作为参考，因为深度更新通常与IMU同步
        self._last_depth_ts = self._last_imu_ts if self._last_imu_ts > 0 else time.time()

    def _on_setpoint(self, msg: Setpoint) -> None:
        """缓存当前目标深度，用于显示深度误差。"""
        self._latest_setpoint_depth_m = float(msg.target_depth_m)

    def _on_parameters_changed(self, params) -> SetParametersResult:
        """响应参数更新，支持动态调整发布开关和滤波频率。"""
        for param in params:
            if param.name == 'publish_raw_state':
                self.publish_raw_state = bool(param.value)
            elif param.name == 'publish_sensor_status':
                self.publish_sensor_status = bool(param.value)
            elif param.name == 'seabed_depth_m':
                self.seabed_depth_m = float(param.value)
            elif param.name == 'seabed_proximity_margin_m':
                self.seabed_proximity_margin_m = float(param.value)
            elif param.name == 'battery_low_voltage_threshold':
                self.battery_low_voltage_threshold = float(param.value)
            elif param.name == 'nominal_voltage_v':
                self.nominal_voltage_v = float(param.value)
            elif param.name == 'filter_rate_hz':
                new_rate = float(param.value)
                if new_rate <= 0.0:
                    return SetParametersResult(successful=False, reason='filter_rate_hz must be positive')
                if abs(new_rate - self.filter_rate_hz) > 1e-9:
                    self.filter_rate_hz = new_rate
                    self._filter_timer.cancel()
                    self._filter_timer = self.create_timer(1.0 / max(self.filter_rate_hz, 1e-3), self._on_timer)
        return SetParametersResult(successful=True)

    def _build_sensor_status(self, state: dict) -> SensorStatus:
        """从滤波状态构建最小化的 SensorStatus 消息。

        本地化节点是联调栈里最合适的状态来源，因为它已经融合了深度、
        速度和协方差信息，决策层可以在回放和实时模式下复用同一话题。
        """
        msg = SensorStatus()
        msg.depth_m = float(abs(state['p'][2]))
        msg.speed_mps = float(np.linalg.norm(state['v']))
        msg.seabed_depth_m = float(self.seabed_depth_m)
        msg.seabed_clearance_m = float(self.seabed_depth_m - msg.depth_m)
        msg.seabed_proximity_warning = bool(
            msg.seabed_clearance_m <= float(self.seabed_proximity_margin_m)
        )
        msg.seabed_penetration_warning = bool(msg.seabed_clearance_m < 0.0)

        pos_cov = np.asarray(self.filter.P[:3, :3], dtype=float)
        pos_var = float(max(np.trace(pos_cov), 0.0) / 3.0)
        pos_sigma = float(np.sqrt(pos_var))
        confidence = 1.0 / (1.0 + pos_sigma)
        msg.confidence = float(np.clip(confidence, 0.05, 0.99))

        msg.leak_level = SensorStatus.LEAK_NONE
        msg.total_voltage_v = float(self.nominal_voltage_v)
        msg.battery_low = bool(msg.total_voltage_v < self.battery_low_voltage_threshold)
        msg.anomaly_detected = bool(np.linalg.norm(state['v']) < 1e-6 and self._last_depth is None)
        return msg

    def _publish_display_topics(self, *, status_msg: SensorStatus, lateral_error_m: float) -> None:
        """发布用于可视化面板的深度误差、横向误差和状态文本。"""
        current_depth = float(status_msg.depth_m)
        target_depth = float(self._latest_setpoint_depth_m) if self._latest_setpoint_depth_m is not None else current_depth
        self.depth_error_pub.publish(Float32(data=current_depth - target_depth))
        self.lateral_error_pub.publish(Float32(data=float(lateral_error_m)))
        self.confidence_text_pub.publish(String(data=_format_confidence_markdown(float(status_msg.confidence))))
        self.power_text_pub.publish(
            String(
                data=_format_power_markdown(
                    float(status_msg.total_voltage_v),
                    float(self.battery_low_voltage_threshold),
                )
            )
        )

    def _publish_static_transforms(self) -> None:
        """发布 AUV 基座下的静态传感器 TF 坐标系。

        默认零偏移可以先保证 TF 链完整，后续再统一填充真实传感器安装位姿。
        """
        static_transforms: list[TransformStamped] = []

        def _make_static(child_frame_id: str, xyz: tuple[float, float, float]) -> TransformStamped:
            transform = TransformStamped()
            transform.header.stamp = self.get_clock().now().to_msg()
            transform.header.frame_id = self.base_frame_id
            transform.child_frame_id = child_frame_id
            transform.transform.translation.x = float(xyz[0])
            transform.transform.translation.y = float(xyz[1])
            transform.transform.translation.z = float(xyz[2])
            transform.transform.rotation.w = 1.0
            return transform

        if self.publish_imu_tf:
            static_transforms.append(_make_static(self.imu_frame_id, self.imu_frame_offset_xyz))
        if self.publish_dvl_tf:
            static_transforms.append(_make_static(self.dvl_frame_id, self.dvl_frame_offset_xyz))
        if self.publish_depth_tf:
            static_transforms.append(_make_static(self.depth_frame_id, self.depth_frame_offset_xyz))
        if self.publish_camera_tf:
            static_transforms.append(_make_static(self.camera_frame_id, self.camera_frame_offset_xyz))
        if self.publish_sonar_tf:
            static_transforms.append(_make_static(self.sonar_frame_id, self.sonar_frame_offset_xyz))

        self.static_tf_broadcaster.sendTransform(static_transforms)

    def _publish_state_odom(self, state: dict, publisher, *, publish_tf: bool) -> None:
        odom = Odometry()
        # 严禁使用 get_clock().now()，必须使用传感器原始Header Stamp
        # IMU是最前沿传感器，用IMU时间戳作为状态发布的物理时间锚点
        odom.header.stamp = self._last_imu_header_stamp
        odom.header.frame_id = self.world_frame_id
        odom.child_frame_id = self.base_frame_id
        odom.pose.pose.position.x = float(state['p'][0])
        odom.pose.pose.position.y = float(state['p'][1])
        odom.pose.pose.position.z = float(state['p'][2])
        orientation_q = state['q']
        if self.use_imu_orientation_measurement and self._last_imu_orientation is not None:
            orientation_q = self._last_imu_orientation
        odom.pose.pose.orientation.w = float(orientation_q[0])
        odom.pose.pose.orientation.x = float(orientation_q[1])
        odom.pose.pose.orientation.y = float(orientation_q[2])
        odom.pose.pose.orientation.z = float(orientation_q[3])
        odom.twist.twist.linear.x = float(state['v'][0])
        odom.twist.twist.linear.y = float(state['v'][1])
        odom.twist.twist.linear.z = float(state['v'][2])
        publisher.publish(odom)

        if publish_tf:
            transform = TransformStamped()
            transform.header.stamp = odom.header.stamp  # 与odom使用相同的时间戳
            transform.header.frame_id = self.world_frame_id
            transform.child_frame_id = self.base_frame_id
            transform.transform.translation.x = float(state['p'][0])
            transform.transform.translation.y = float(state['p'][1])
            transform.transform.translation.z = float(state['p'][2])
            transform.transform.rotation.w = float(orientation_q[0])
            transform.transform.rotation.x = float(orientation_q[1])
            transform.transform.rotation.y = float(orientation_q[2])
            transform.transform.rotation.z = float(orientation_q[3])
            self.tf_broadcaster.sendTransform(transform)

    def _on_timer(self) -> None:
        """滤波主循环：推进 ES-EKF、发布状态和调试话题。"""
        now = time.time()
        self._last_loop_ts = now

        # 强制对齐：如果没有收到IMU时间锚点，跳过发布（绝不发布垃圾状态）
        if self._last_imu_header_stamp is None:
            return

        if self._last_imu_ts <= 0.0:
            return

        if self._last_predict_imu_ts <= 0.0:
            self._last_predict_imu_ts = self._last_imu_ts
        elif self._last_imu_ts > self._last_predict_imu_ts:
            dt = max(1e-3, min(0.2, self._last_imu_ts - self._last_predict_imu_ts))
            self._last_predict_imu_ts = self._last_imu_ts
            self.filter.predict(self._last_imu, self._last_gyro, dt)
        elif self._last_imu_ts < self._last_predict_imu_ts:
            self._last_predict_imu_ts = self._last_imu_ts

        raw_state = self.filter.get_state()
        if self.publish_raw_state:
            self._publish_state_odom(raw_state, self.raw_odom_pub, publish_tf=False)

        if self._last_dvl is not None and self._last_dvl_ts > self._last_corrected_dvl_ts:
            was_initialized = self.filter.is_initialized()
            self.filter.correct_dvl_world_with_timestamp(
                self._last_dvl,
                self._last_dvl_ts,
                self._last_imu_ts,
            )
            self._last_corrected_dvl_ts = self._last_dvl_ts
            if not was_initialized and self.filter.is_initialized():
                self._log_filter_initialization("dvl")
        if self._last_depth is not None and self._last_depth_ts > self._last_corrected_depth_ts:
            was_initialized = self.filter.is_initialized()
            self.filter.correct_depth(self._last_depth)
            self._last_corrected_depth_ts = self._last_depth_ts
            if not was_initialized and self.filter.is_initialized():
                self._log_filter_initialization("depth")

        state = self.filter.get_state()

        self._publish_state_odom(state, self.odom_pub, publish_tf=self.publish_tf)

        cov_msg = Float32MultiArray()
        cov_msg.data = self.filter.P.reshape(-1).astype(float).tolist()
        self.cov_pub.publish(cov_msg)

        if self.publish_sensor_status:
            status_msg = self._build_sensor_status(state)
            self.status_pub.publish(status_msg)
            self._publish_display_topics(
                status_msg=status_msg,
                lateral_error_m=float(state['p'][1]),
            )

        latest_sensor_ts = max(self._last_imu_ts, self._last_dvl_ts, self._last_depth_ts)
        if latest_sensor_ts > 0.0:
            latency = now - latest_sensor_ts
            if latency >= 0:
                self._lat_count += 1
                self._lat_sum += latency

    def _log_latency(self) -> None:
        """打印本地化回路平均延迟统计。"""
        if self._lat_count == 0:
            return
        mean_ms = (self._lat_sum / self._lat_count) * 1000.0
        self.get_logger().info(f'[localization] mean sensor->filter latency: {mean_ms:.2f} ms over {self._lat_count} samples')

    def _log_filter_initialization(self, source: str) -> None:
        """记录滤波器初始化事件。"""
        if self._filter_initialized_logged:
            return
        self._filter_initialized_logged = True

        init_info = getattr(self.filter, '_init_info', None)
        if init_info is not None:
            pos_offset = init_info.get('position_offset', [0.0, 0.0, 0.0])
            aligned_pos = init_info.get('aligned_pos', [0.0, 0.0, 0.0])
            self.get_logger().info(
                f'[ES-EKF] Auto-initialized from {source} observation\n'
                f'  Aligned position: [{aligned_pos[0]:.4f}, {aligned_pos[1]:.4f}, {aligned_pos[2]:.4f}]\n'
                f'  Position offset from config: [{pos_offset[0]:.4f}, {pos_offset[1]:.4f}, {pos_offset[2]:.4f}]'
            )
        else:
            state = self.filter.get_state()
            self.get_logger().info(
                f'[ES-EKF] Initialized from {source} observation\n'
                f'  Position: [{state["p"][0]:.4f}, {state["p"][1]:.4f}, {state["p"][2]:.4f}]\n'
                f'  Velocity: [{state["v"][0]:.4f}, {state["v"][1]:.4f}, {state["v"][2]:.4f}]'
            )

##
# @brief Run the localization node until the ROS context stops.
# @param args Optional ROS CLI arguments.
def main(args=None) -> None:
    """节点入口。"""
    rclpy.init(args=args)
    node = AUVLocalizationNode()
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

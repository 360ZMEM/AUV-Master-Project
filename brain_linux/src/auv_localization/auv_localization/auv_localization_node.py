#!/usr/bin/env python3
"""ES-EKF localization node.

Inputs:
- /auv/sensors/imu (sensor_msgs/Imu)
- /auv/sensors/dvl (geometry_msgs/TwistStamped)
- /auv/sensors/depth (std_msgs/Float32)

Outputs:
- /auv/state/filtered (nav_msgs/Odometry)
- /auv/state/covariance (std_msgs/Float32MultiArray)
- /tf (world -> auv/base_link)
- /tf_static (auv/base_link -> sensor links)
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
    def __init__(self) -> None:
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

        self.filter = ES_EKF(ekf_cfg)

        self._last_imu = np.zeros(3, dtype=float)
        self._last_gyro = np.zeros(3, dtype=float)
        self._last_dvl = None
        self._last_depth = None
        self._last_imu_ts = 0.0
        self._last_dvl_ts = 0.0
        self._last_depth_ts = 0.0
        self._last_loop_ts = time.time()
        self._latest_setpoint_depth_m: float | None = None

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

        self.create_subscription(Imu, '/auv/sensors/imu', self._on_imu, 20)
        self.create_subscription(TwistStamped, '/auv/sensors/dvl', self._on_dvl, 20)
        self.create_subscription(Float32, '/auv/sensors/depth', self._on_depth, 20)
        self.create_subscription(Setpoint, '/auv/control/setpoint', self._on_setpoint, 20)

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
            f'seabed_depth_m={self.seabed_depth_m}, '
            f'seabed_proximity_margin_m={self.seabed_proximity_margin_m}, '
            f'battery_low_voltage_threshold={self.battery_low_voltage_threshold}, '
            f'nominal_voltage_v={self.nominal_voltage_v}'
        )

    @staticmethod
    def _load_config(path: str) -> dict:
        p = Path(path)
        if not p.exists():
            return {}
        with p.open('r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
        return data if isinstance(data, dict) else {}

    def _on_imu(self, msg: Imu) -> None:
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
        self._last_imu_ts = time.time()

    def _on_dvl(self, msg: TwistStamped) -> None:
        self._last_dvl = np.array([
            msg.twist.linear.x,
            msg.twist.linear.y,
            msg.twist.linear.z,
        ], dtype=float)
        self._last_dvl_ts = time.time()

    def _on_depth(self, msg: Float32) -> None:
        self._last_depth = float(msg.data)
        self._last_depth_ts = time.time()

    def _on_setpoint(self, msg: Setpoint) -> None:
        self._latest_setpoint_depth_m = float(msg.target_depth_m)

    def _on_parameters_changed(self, params) -> SetParametersResult:
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
        """Build a minimal live SensorStatus message from the filtered state.

        The localization node is the best live source for the status window in
        the integrated stack because it already fuses depth, velocity, and the
        covariance estimate. The decision layer can then consume the same topic
        in both replay and live modes.
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
        """Publish static sensor frames under the AUV base frame.

        The zero-offset defaults keep the TF chain valid today while leaving a
        single place to attach real sensor mounting offsets later.
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
        odom.header.stamp = self.get_clock().now().to_msg()
        odom.header.frame_id = self.world_frame_id
        odom.child_frame_id = self.base_frame_id
        odom.pose.pose.position.x = float(state['p'][0])
        odom.pose.pose.position.y = float(state['p'][1])
        odom.pose.pose.position.z = float(state['p'][2])
        odom.pose.pose.orientation.w = float(state['q'][0])
        odom.pose.pose.orientation.x = float(state['q'][1])
        odom.pose.pose.orientation.y = float(state['q'][2])
        odom.pose.pose.orientation.z = float(state['q'][3])
        odom.twist.twist.linear.x = float(state['v'][0])
        odom.twist.twist.linear.y = float(state['v'][1])
        odom.twist.twist.linear.z = float(state['v'][2])
        publisher.publish(odom)

        if publish_tf:
            transform = TransformStamped()
            transform.header.stamp = odom.header.stamp
            transform.header.frame_id = self.world_frame_id
            transform.child_frame_id = self.base_frame_id
            transform.transform.translation.x = float(state['p'][0])
            transform.transform.translation.y = float(state['p'][1])
            transform.transform.translation.z = float(state['p'][2])
            transform.transform.rotation.w = float(state['q'][0])
            transform.transform.rotation.x = float(state['q'][1])
            transform.transform.rotation.y = float(state['q'][2])
            transform.transform.rotation.z = float(state['q'][3])
            self.tf_broadcaster.sendTransform(transform)

    def _on_timer(self) -> None:
        now = time.time()
        dt = max(1e-3, min(0.2, now - self._last_loop_ts))
        self._last_loop_ts = now

        self.filter.predict(self._last_imu, self._last_gyro, dt)

        raw_state = self.filter.get_state()
        if self.publish_raw_state:
            self._publish_state_odom(raw_state, self.raw_odom_pub, publish_tf=False)

        if self._last_dvl is not None:
            self.filter.correct_dvl_world(self._last_dvl)
        if self._last_depth is not None:
            self.filter.correct_depth(self._last_depth)

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
        if self._lat_count == 0:
            return
        mean_ms = (self._lat_sum / self._lat_count) * 1000.0
        self.get_logger().info(f'[localization] mean sensor->filter latency: {mean_ms:.2f} ms over {self._lat_count} samples')


def main(args=None) -> None:
    rclpy.init(args=args)
    node = AUVLocalizationNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()

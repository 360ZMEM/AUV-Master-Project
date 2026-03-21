#!/usr/bin/env python3
"""ES-EKF localization node.

Inputs:
- /auv/sensors/imu (sensor_msgs/Imu)
- /auv/sensors/dvl (geometry_msgs/TwistStamped)
- /auv/sensors/depth (std_msgs/Float32)

Outputs:
- /auv/state/filtered (nav_msgs/Odometry)
- /auv/state/covariance (std_msgs/Float32MultiArray)
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
from nav_msgs.msg import Odometry
from rclpy.node import Node
from sensor_msgs.msg import Imu
from std_msgs.msg import Float32, Float32MultiArray
import yaml

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


class AUVLocalizationNode(Node):
    def __init__(self) -> None:
        super().__init__('auv_localization_node')

        default_params = str(PROJECT_ROOT / 'brain_linux' / 'config' / 'params.yaml')
        self.declare_parameter('params_file', default_params)
        self.declare_parameter('filter_rate_hz', 20.0)

        self.params_file = str(self.get_parameter('params_file').value)
        self.filter_rate_hz = float(self.get_parameter('filter_rate_hz').value)

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

        self.odom_pub = self.create_publisher(Odometry, '/auv/state/filtered', 10)
        self.cov_pub = self.create_publisher(Float32MultiArray, '/auv/state/covariance', 10)

        self.create_subscription(Imu, '/auv/sensors/imu', self._on_imu, 20)
        self.create_subscription(TwistStamped, '/auv/sensors/dvl', self._on_dvl, 20)
        self.create_subscription(Float32, '/auv/sensors/depth', self._on_depth, 20)

        self.create_timer(1.0 / max(self.filter_rate_hz, 1e-3), self._on_timer)

        self._lat_count = 0
        self._lat_sum = 0.0
        self.create_timer(2.0, self._log_latency)

        self.get_logger().info('auv_localization_node started')

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

    def _on_timer(self) -> None:
        now = time.time()
        dt = max(1e-3, min(0.2, now - self._last_loop_ts))
        self._last_loop_ts = now

        self.filter.predict(self._last_imu, self._last_gyro, dt)

        if self._last_dvl is not None:
            self.filter.correct_dvl_world(self._last_dvl)
        if self._last_depth is not None:
            self.filter.correct_depth(self._last_depth)

        state = self.filter.get_state()

        odom = Odometry()
        odom.header.stamp = self.get_clock().now().to_msg()
        odom.header.frame_id = 'world'
        odom.child_frame_id = 'auv/base_link'
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
        self.odom_pub.publish(odom)

        cov_msg = Float32MultiArray()
        cov_msg.data = self.filter.P.reshape(-1).astype(float).tolist()
        self.cov_pub.publish(cov_msg)

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

#!/usr/bin/env python3
"""Controller node: setpoint + filtered state -> /cmd_vel.

The node wraps existing PID control logic and outputs a fixed Twist mapping:
- linear.x: thrust
- angular.x: right fin
- angular.y: top fin
- angular.z: left fin
- linear.z: bottom fin
"""

from __future__ import annotations

import json
import math
import time
from pathlib import Path
import sys
import importlib.util
import os

import rclpy
from auv_interfaces.msg import Setpoint
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
from rcl_interfaces.msg import SetParametersResult
from rclpy.node import Node
from sensor_msgs.msg import Imu
from std_msgs.msg import String
import yaml

from common.enums import StateEstimateSource
from common.protocol import KEY_STATE_SOURCE

def _resolve_project_root() -> Path:
    env_root = Path(str(os.environ.get('AUV_PROJECT_ROOT', ''))).expanduser() if os.environ.get('AUV_PROJECT_ROOT') else None
    if env_root and (env_root / 'algorithm').exists():
        return env_root

    try:
        from ament_index_python.packages import get_package_share_directory

        share_dir = Path(get_package_share_directory('auv_controller')).resolve()
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
def _load_pid_controller_class():
    module_path = ALGO_DIR / 'auv_pid_controller.py'
    spec = importlib.util.spec_from_file_location('auv_algorithm_pid', str(module_path))
    if spec is None or spec.loader is None:
        raise RuntimeError(f'failed to load PID module: {module_path}')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.AUVPIDController


AUVPIDController = _load_pid_controller_class()


def quat_to_euler(w: float, x: float, y: float, z: float) -> tuple[float, float, float]:
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


class AUVControllerNode(Node):
    def __init__(self) -> None:
        super().__init__('auv_controller_node')

        default_params = str(PROJECT_ROOT / 'brain_linux' / 'config' / 'params.yaml')
        self.declare_parameter('params_file', default_params)
        self.declare_parameter('filtered_state_topic', '/auv/state/filtered')
        self.declare_parameter('raw_state_topic', '/auv/state/raw_dr')
        self.declare_parameter('bypass_ekf', False)
        self.declare_parameter('control_rate_hz', 20.0)

        params_file = str(self.get_parameter('params_file').value)
        cfg = self._load_config(params_file)

        ctrl_cfg = cfg.get('control', {})
        lim_cfg = cfg.get('limits', {})
        self.control_rate_hz = float(self.get_parameter('control_rate_hz').value)
        self.filtered_state_topic = str(self.get_parameter('filtered_state_topic').value)
        self.raw_state_topic = str(self.get_parameter('raw_state_topic').value)
        self.bypass_ekf = bool(self.get_parameter('bypass_ekf').value)

        self.controller = AUVPIDController(ctrl_cfg, lim_cfg)

        self.latest_setpoint: Setpoint | None = None
        self.latest_filtered_state: Odometry | None = None
        self.latest_raw_state: Odometry | None = None
        self.latest_imu_gyro: tuple[float, float, float] | None = None
        self.latest_setpoint_ts = 0.0
        self.latest_filtered_state_ts = 0.0
        self.latest_raw_state_ts = 0.0
        self.latest_imu_ts = 0.0
        self.latest_debug_payload: dict | None = None

        self.setpoint_sub = self.create_subscription(Setpoint, '/auv/control/setpoint', self._on_setpoint, 20)
        self.filtered_state_sub = self.create_subscription(Odometry, self.filtered_state_topic, self._on_filtered_state, 20)
        self.raw_state_sub = self.create_subscription(Odometry, self.raw_state_topic, self._on_raw_state, 20)
        self.imu_sub = self.create_subscription(Imu, '/auv/sensors/imu', self._on_imu, 20)

        self.cmd_pub = self.create_publisher(Twist, '/cmd_vel', 20)
        self.debug_pub = self.create_publisher(String, '/auv/controller/debug', 20)
        self._control_timer = self.create_timer(1.0 / max(self.control_rate_hz, 1e-3), self._on_timer)

        self._lat_count = 0
        self._lat_sum = 0.0
        self.create_timer(2.0, self._log_latency)
        self.create_timer(0.5, self._publish_debug)
        self._param_callback = self.add_on_set_parameters_callback(self._on_parameters_changed)

        self.get_logger().info('auv_controller_node started')

    @staticmethod
    def _load_config(path: str) -> dict:
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f'controller params file not found: {p}')
        with p.open('r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
        if not isinstance(data, dict):
            raise RuntimeError('invalid controller params yaml')
        return data

    def _on_setpoint(self, msg: Setpoint) -> None:
        self.latest_setpoint = msg
        self.latest_setpoint_ts = time.time()

    def _on_filtered_state(self, msg: Odometry) -> None:
        self.latest_filtered_state = msg
        self.latest_filtered_state_ts = time.time()

    def _on_raw_state(self, msg: Odometry) -> None:
        self.latest_raw_state = msg
        self.latest_raw_state_ts = time.time()

    def _on_imu(self, msg: Imu) -> None:
        self.latest_imu_gyro = (
            float(msg.angular_velocity.x),
            float(msg.angular_velocity.y),
            float(msg.angular_velocity.z),
        )
        self.latest_imu_ts = time.time()

    def _resolve_body_rates(self, st: Odometry) -> tuple[float, float, float, str]:
        odom_rates = (
            float(st.twist.twist.angular.x),
            float(st.twist.twist.angular.y),
            float(st.twist.twist.angular.z),
        )
        if any(abs(rate) > 1e-6 for rate in odom_rates):
            return odom_rates[0], odom_rates[1], odom_rates[2], 'odom'

        if self.latest_imu_gyro is not None and (time.time() - self.latest_imu_ts) <= 0.5:
            return self.latest_imu_gyro[0], self.latest_imu_gyro[1], self.latest_imu_gyro[2], 'imu'

        return odom_rates[0], odom_rates[1], odom_rates[2], 'odom'

    def _select_state(self) -> tuple[Odometry | None, StateEstimateSource, bool, float]:
        preferred_source = StateEstimateSource.RAW_DR if self.bypass_ekf else StateEstimateSource.FILTERED
        if preferred_source == StateEstimateSource.RAW_DR:
            if self.latest_raw_state is not None:
                return self.latest_raw_state, preferred_source, False, self.latest_raw_state_ts
            if self.latest_filtered_state is not None:
                return self.latest_filtered_state, StateEstimateSource.FILTERED, True, self.latest_filtered_state_ts
        else:
            if self.latest_filtered_state is not None:
                return self.latest_filtered_state, preferred_source, False, self.latest_filtered_state_ts
            if self.latest_raw_state is not None:
                return self.latest_raw_state, StateEstimateSource.RAW_DR, True, self.latest_raw_state_ts
        return None, preferred_source, False, 0.0

    def _on_parameters_changed(self, params) -> SetParametersResult:
        for param in params:
            if param.name == 'bypass_ekf':
                self.bypass_ekf = bool(param.value)
            elif param.name == 'control_rate_hz':
                new_rate = float(param.value)
                if new_rate <= 0.0:
                    return SetParametersResult(successful=False, reason='control_rate_hz must be positive')
                if abs(new_rate - self.control_rate_hz) > 1e-9:
                    self.control_rate_hz = new_rate
                    self._control_timer.cancel()
                    self._control_timer = self.create_timer(1.0 / max(self.control_rate_hz, 1e-3), self._on_timer)
        return SetParametersResult(successful=True)

    def _on_timer(self) -> None:
        if self.latest_setpoint is None:
            return

        st, state_source, state_source_fallback, state_ts = self._select_state()
        if st is None:
            return

        sp = self.latest_setpoint

        q = st.pose.pose.orientation
        roll, pitch, yaw = quat_to_euler(q.w, q.x, q.y, q.z)
        p_rate, q_rate, r_rate, rate_source = self._resolve_body_rates(st)
        depth_error = float(sp.target_depth_m) - float(-st.pose.pose.position.z)
        yaw_error = math.atan2(
            math.sin(float(sp.target_heading_rad) - yaw),
            math.cos(float(sp.target_heading_rad) - yaw),
        )

        state = {
            'roll': roll,
            'pitch': pitch,
            'yaw': yaw,
            'x': float(st.pose.pose.position.x),
            'y': float(st.pose.pose.position.y),
            'z': float(st.pose.pose.position.z),
            'depth': float(-st.pose.pose.position.z),
            'depth_sensor': float(-st.pose.pose.position.z),
            'u': float(st.twist.twist.linear.x),
            'v': float(st.twist.twist.linear.y),
            'w': float(st.twist.twist.linear.z),
            'p': p_rate,
            'q': q_rate,
            'r': r_rate,
        }

        target = {
            'dt': 1.0 / max(self.control_rate_hz, 1e-3),
            'target_depth': float(sp.target_depth_m),
            'target_yaw': float(sp.target_heading_rad),
            'target_u': float(sp.target_speed_mps),
        }

        cmd, _debug = self.controller.compute(state, target)

        tw = Twist()
        tw.linear.x = float(cmd[4])
        tw.angular.x = float(cmd[0])
        tw.angular.y = float(cmd[1])
        tw.angular.z = float(cmd[2])
        tw.linear.z = float(cmd[3])
        self.cmd_pub.publish(tw)

        now = time.time()
        sensor_to_cmd = now - max(self.latest_setpoint_ts, state_ts)
        if sensor_to_cmd >= 0:
            self._lat_count += 1
            self._lat_sum += sensor_to_cmd

        self.latest_debug_payload = {
            'mode': str(sp.mode),
            'rate_source': rate_source,
            KEY_STATE_SOURCE: state_source.value,
            'state_source_requested': StateEstimateSource.RAW_DR.value if self.bypass_ekf else StateEstimateSource.FILTERED.value,
            'state_source_fallback': bool(state_source_fallback),
            'attitude_guard_active': bool(_debug.get('attitude_guard_active', False)),
            'current_roll_deg': round(float(_debug.get('current_roll_deg', 0.0)), 3),
            'current_pitch_deg': round(float(_debug.get('current_pitch_deg', 0.0)), 3),
            'depth_error_m': round(depth_error, 4),
            'yaw_error_deg': round(math.degrees(yaw_error), 3),
            'current_yaw_deg': round(math.degrees(yaw), 3),
            'target_yaw_deg': round(math.degrees(float(sp.target_heading_rad)), 3),
            'target_depth_m': round(float(sp.target_depth_m), 3),
            'current_depth_m': round(float(-st.pose.pose.position.z), 3),
            'target_speed_mps': round(float(sp.target_speed_mps), 3),
            'current_speed_mps': round(float(st.twist.twist.linear.x), 3),
            'pitch_saturated': bool(_debug.get('pitch_saturated', False)),
            'yaw_saturated': bool(_debug.get('yaw_saturated', False)),
            'thrust_saturated': bool(_debug.get('thrust_saturated', False)),
            'target_pitch_deg': round(math.degrees(float(_debug.get('target_pitch_rad', 0.0))), 3),
            'bypass_ekf': bool(self.bypass_ekf),
            'cmd': {
                'right_deg': round(float(cmd[0]), 3),
                'top_deg': round(float(cmd[1]), 3),
                'left_deg': round(float(cmd[2]), 3),
                'bottom_deg': round(float(cmd[3]), 3),
                'thrust': round(float(cmd[4]), 3),
            },
        }

    def _log_latency(self) -> None:
        if self._lat_count == 0:
            return
        mean_ms = (self._lat_sum / self._lat_count) * 1000.0
        self.get_logger().info(f'[controller] mean state/setpoint->cmd latency: {mean_ms:.2f} ms over {self._lat_count} samples')

    def _publish_debug(self) -> None:
        if self.latest_debug_payload is None:
            return
        self.debug_pub.publish(String(data=json.dumps(self.latest_debug_payload, ensure_ascii=False)))


def main(args=None) -> None:
    rclpy.init(args=args)
    node = AUVControllerNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()

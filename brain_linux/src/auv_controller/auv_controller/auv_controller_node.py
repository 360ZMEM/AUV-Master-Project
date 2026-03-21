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
from rclpy.node import Node
import yaml

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

        params_file = str(self.get_parameter('params_file').value)
        cfg = self._load_config(params_file)

        ctrl_cfg = cfg.get('control', {})
        lim_cfg = cfg.get('limits', {})
        self.control_rate_hz = float(cfg.get('controller', {}).get('control_rate_hz', 20.0))

        self.controller = AUVPIDController(ctrl_cfg, lim_cfg)

        self.latest_setpoint: Setpoint | None = None
        self.latest_state: Odometry | None = None
        self.latest_setpoint_ts = 0.0
        self.latest_state_ts = 0.0

        self.setpoint_sub = self.create_subscription(Setpoint, '/auv/control/setpoint', self._on_setpoint, 20)
        self.state_sub = self.create_subscription(Odometry, '/auv/state/filtered', self._on_state, 20)

        self.cmd_pub = self.create_publisher(Twist, '/cmd_vel', 20)
        self.create_timer(1.0 / max(self.control_rate_hz, 1e-3), self._on_timer)

        self._lat_count = 0
        self._lat_sum = 0.0
        self.create_timer(2.0, self._log_latency)

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

    def _on_state(self, msg: Odometry) -> None:
        self.latest_state = msg
        self.latest_state_ts = time.time()

    def _on_timer(self) -> None:
        if self.latest_setpoint is None or self.latest_state is None:
            return

        st = self.latest_state
        sp = self.latest_setpoint

        q = st.pose.pose.orientation
        roll, pitch, yaw = quat_to_euler(q.w, q.x, q.y, q.z)

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
            'p': float(st.twist.twist.angular.x),
            'q': float(st.twist.twist.angular.y),
            'r': float(st.twist.twist.angular.z),
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
        sensor_to_cmd = now - max(self.latest_setpoint_ts, self.latest_state_ts)
        if sensor_to_cmd >= 0:
            self._lat_count += 1
            self._lat_sum += sensor_to_cmd

    def _log_latency(self) -> None:
        if self._lat_count == 0:
            return
        mean_ms = (self._lat_sum / self._lat_count) * 1000.0
        self.get_logger().info(f'[controller] mean state/setpoint->cmd latency: {mean_ms:.2f} ms over {self._lat_count} samples')


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

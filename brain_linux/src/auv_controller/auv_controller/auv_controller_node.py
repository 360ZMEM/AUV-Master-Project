#!/usr/bin/env python3
"""ROS2 控制节点：支持 PID/MPC 混合控制架构。

该节点是决策层与底层控制器之间的桥梁，负责把 Setpoint 和状态估计
转换为控制指令。支持两种控制器模式：

PID 模式（默认）:
  - 纵向推力：由 PID 速度环闭环计算
  - 舵角：透传（None 标记），由 AMD 本地 PID 闭环处理
  - 输出：Twist (/cmd_vel)

MPC 模式（预留）:
  - 所有通道由 MPC 优化器计算
  - 输出：MpcCmd (/auv/control/mpc_cmd)

切换方式：
  ros2 param set /auv_controller_node use_mpc true/false

输出映射约定（Twist）:
- linear.x: thrust（推力）
- angular.x: right fin（右舵）
- angular.y: top fin（上舵）
- angular.z: left fin（左舵）
- linear.z: bottom fin（下舵）
"""

from __future__ import annotations

import json
import math
import time
from typing import Any
from pathlib import Path
import sys
import importlib.util
import os

import rclpy
from auv_interfaces.msg import Setpoint, MpcCmd
from geometry_msgs.msg import Twist, TwistStamped
from nav_msgs.msg import Odometry
from rcl_interfaces.msg import SetParametersResult
from rclpy.node import Node
from sensor_msgs.msg import Imu
from std_msgs.msg import String, Float32
import yaml

from common.enums import StateEstimateSource, ControlModeByte
from common.protocol import KEY_STATE_SOURCE

from .base_controller import BaseController, ControlOutput
from .pid_controller import PIDController
from .mpc_controller import MPCController
from .terrain_engine import TerrainFollower
from .terrain_perception import ROSTerrainPerception
from .mappers import clamp_int16

def _resolve_project_root() -> Path:
    """解析工程根目录，优先使用环境变量和 ament 安装路径。"""
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


def quat_to_euler(w: float, x: float, y: float, z: float) -> tuple[float, float, float]:
    """将四元数转换为欧拉角，返回 roll、pitch、yaw（弧度）。"""
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
    """AUV 控制节点主类，支持 PID/MPC 混合控制架构。

    该节点订阅控制目标、滤波状态和原始状态，周期性调用当前活跃控制器，
    并根据模式输出 Twist 或 MpcCmd。
    """

    def __init__(self) -> None:
        """初始化控制节点的参数、话题订阅、控制器实例和调试发布器。"""
        super().__init__('auv_controller_node')

        default_params = str(PROJECT_ROOT / 'brain_linux' / 'config' / 'params.yaml')
        self.declare_parameter('params_file', default_params)
        self.declare_parameter('filtered_state_topic', '/auv/state/filtered')
        self.declare_parameter('raw_state_topic', '/auv/state/raw_dr')
        self.declare_parameter('bypass_ekf', False)
        self.declare_parameter('control_rate_hz', 20.0)

        # 混合控制架构参数
        self.declare_parameter('use_mpc', False)
        self.declare_parameter('control_mode_byte', int(ControlModeByte.JETSON_HYBRID))
        self.declare_parameter('heading_ramp_limit_deg', 30.0)
        self.declare_parameter('heading_ramp_rate_deg_s', 10.0)

        # --- 特征开关 (Feature Flags) ---
        self.declare_parameter('depth_mode', 'CONSTANT')
        self.declare_parameter('heading_mode', 'CONSTANT')
        self.declare_parameter('constant_depth_m', 2.0)
        self.declare_parameter('constant_heading_rad', 0.0)
        self.declare_parameter('bypass_zero_effort', False)

        params_file = str(self.get_parameter('params_file').value)
        cfg = self._load_config(params_file)

        ctrl_cfg = cfg.get('control', {})
        lim_cfg = cfg.get('limits', {})
        mapper_cfg = cfg.get('mappers', {})
        self.control_rate_hz = float(self.get_parameter('control_rate_hz').value)
        self.filtered_state_topic = str(self.get_parameter('filtered_state_topic').value)
        self.raw_state_topic = str(self.get_parameter('raw_state_topic').value)
        self.bypass_ekf = bool(self.get_parameter('bypass_ekf').value)

        # 初始化混合控制器
        self._pid_controller = PIDController(ctrl_cfg, lim_cfg, mapper_cfg)
        self._mpc_controller = MPCController(ctrl_cfg, lim_cfg, mapper_cfg)
        self._active_controller: BaseController = self._pid_controller
        self._use_mpc = bool(self.get_parameter('use_mpc').value)
        if self._use_mpc:
            self._active_controller = self._mpc_controller

        # 控制模式字节
        self._control_mode_byte = int(self.get_parameter('control_mode_byte').value)

        # 指令平滑器状态
        self._last_heading_cmd = 0.0
        self._heading_ramp_active = False
        self._heading_ramp_start = 0.0
        self._heading_ramp_target = 0.0
        self._heading_ramp_limit_deg = float(self.get_parameter('heading_ramp_limit_deg').value)
        self._heading_ramp_rate_deg_s = float(self.get_parameter('heading_ramp_rate_deg_s').value)

        self._depth_mode = str(self.get_parameter('depth_mode').value)
        self._heading_mode = str(self.get_parameter('heading_mode').value)
        self._constant_depth_m = float(self.get_parameter('constant_depth_m').value)
        self._constant_heading_rad = float(self.get_parameter('constant_heading_rad').value)
        self._bypass_zero_effort = bool(self.get_parameter('bypass_zero_effort').value)
        self._last_chain_status = ""

        # 实例化地形跟踪模块
        self._terrain_perception = ROSTerrainPerception()
        self._terrain_follower = TerrainFollower(lookahead_time_s=2.0, lpf_alpha=0.2)

        self.latest_setpoint: Setpoint | None = None
        self.latest_filtered_state: Odometry | None = None
        self.latest_raw_state: Odometry | None = None
        self.latest_imu_gyro: tuple[float, float, float] | None = None
        self.latest_setpoint_ts = 0.0
        self.latest_filtered_state_ts = 0.0
        self.latest_raw_state_ts = 0.0
        self.latest_imu_ts = 0.0
        self.latest_debug_payload: dict | None = None
        self._latest_confidence: float = 1.0

        self.setpoint_sub = self.create_subscription(Setpoint, '/auv/control/setpoint', self._on_setpoint, 20)
        self.filtered_state_sub = self.create_subscription(Odometry, self.filtered_state_topic, self._on_filtered_state, 20)
        self.raw_state_sub = self.create_subscription(Odometry, self.raw_state_topic, self._on_raw_state, 20)
        self.imu_sub = self.create_subscription(Imu, '/auv/sensors/imu', self._on_imu, 20)
        self.dvl_sub = self.create_subscription(TwistStamped, '/auv/sensors/dvl', self._on_dvl, 20)
        self.depth_sub = self.create_subscription(Float32, '/auv/sensors/depth', self._on_depth, 20)
        self.altitude_sub = self.create_subscription(Float32, '/auv/sensors/altitude', self._on_altitude, 20)

        self.cmd_pub = self.create_publisher(Twist, '/cmd_vel', 20)
        self.debug_pub = self.create_publisher(String, '/auv/controller/debug', 20)
        self._mpc_cmd_pub = self.create_publisher(MpcCmd, '/auv/control/mpc_cmd', 20)
        self._terrain_debug_pub = self.create_publisher(String, '/auv/controller/terrain_debug', 20)
        self._control_timer = self.create_timer(1.0 / max(self.control_rate_hz, 1e-3), self._on_timer)

        self._lat_count = 0
        self._lat_sum = 0.0
        self.create_timer(2.0, self._log_latency)
        self.create_timer(0.5, self._publish_debug)
        self._param_callback = self.add_on_set_parameters_callback(self._on_parameters_changed)

        mode_str = 'MPC' if self._use_mpc else 'PID'
        self.get_logger().info(f'auv_controller_node started ({mode_str} mode)')
        self.get_logger().info(f'Control mode byte: 0x{self._control_mode_byte:02X}')

    @staticmethod
    def _load_config(path: str) -> dict:
        """加载控制参数 YAML，并确保配置结构是字典。"""
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f'controller params file not found: {p}')
        with p.open('r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
        if not isinstance(data, dict):
            raise RuntimeError('invalid controller params yaml')
        return data

    def _on_setpoint(self, msg: Setpoint) -> None:
        """缓存最新控制目标并记录时间戳。"""
        self.latest_setpoint = msg
        self.latest_setpoint_ts = time.time()

    def _on_filtered_state(self, msg: Odometry) -> None:
        """缓存滤波后的状态估计。"""
        self.latest_filtered_state = msg
        self.latest_filtered_state_ts = time.time()

    def _on_raw_state(self, msg: Odometry) -> None:
        """缓存原始死推进状态估计，供 bypass_ekf 模式使用。"""
        self.latest_raw_state = msg
        self.latest_raw_state_ts = time.time()

    def _on_dvl(self, msg: TwistStamped) -> None:
        """缓存 DVL 速度，并更新地形感知接口（前向速度）。"""
        self._terrain_perception.update_state(
            altitude=self._terrain_perception.get_altitude(),
            depth=self._terrain_perception.get_current_depth(),
            forward_velocity=float(msg.twist.linear.x)
        )

    def _on_depth(self, msg: Float32) -> None:
        """缓存深度。"""
        self._terrain_perception.update_state(
            altitude=self._terrain_perception.get_altitude(),
            depth=float(msg.data),
            forward_velocity=self._terrain_perception.get_forward_velocity(),
        )

    def _on_altitude(self, msg: Float32) -> None:
        """缓存高度。"""
        self._terrain_perception.update_state(
            altitude=float(msg.data),
            depth=self._terrain_perception.get_current_depth(),
            forward_velocity=self._terrain_perception.get_forward_velocity()
        )

    def _on_imu(self, msg: Imu) -> None:
        """缓存 IMU 角速度，用于补充或覆盖状态里的角速度来源。"""
        self.latest_imu_gyro = (
            float(msg.angular_velocity.x),
            float(msg.angular_velocity.y),
            float(msg.angular_velocity.z),
        )
        self.latest_imu_ts = time.time()

    def _resolve_body_rates(self, st: Odometry) -> tuple[float, float, float, str]:
        """优先从里程计获取体轴角速度，否则回退到最新 IMU。"""
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
        """选择当前控制周期应使用的状态源，并指示是否发生了降级回退。"""
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
        """响应运行时参数更新，支持切换控制器模式、状态源和控制频率。"""
        for param in params:
            if param.name == 'use_mpc':
                self._use_mpc = bool(param.value)
                if self._use_mpc:
                    self._active_controller = self._mpc_controller
                    self.get_logger().info('控制器切换为 MPC 模式')
                else:
                    self._active_controller = self._pid_controller
                    self.get_logger().info('控制器切换为 PID 模式')
            elif param.name == 'bypass_ekf':
                self.bypass_ekf = bool(param.value)
            elif param.name == 'control_rate_hz':
                new_rate = float(param.value)
                if new_rate <= 0.0:
                    return SetParametersResult(successful=False, reason='control_rate_hz must be positive')
                if abs(new_rate - self.control_rate_hz) > 1e-9:
                    self.control_rate_hz = new_rate
                    self._control_timer.cancel()
                    self._control_timer = self.create_timer(1.0 / max(self.control_rate_hz, 1e-3), self._on_timer)
            elif param.name == 'heading_ramp_limit_deg':
                self._heading_ramp_limit_deg = float(param.value)
            elif param.name == 'heading_ramp_rate_deg_s':
                self._heading_ramp_rate_deg_s = float(param.value)
            elif param.name == 'control_mode_byte':
                self._control_mode_byte = int(param.value)
            elif param.name == 'depth_mode':
                self._depth_mode = str(param.value)
                self.get_logger().info(f"特征开关: depth_mode -> {self._depth_mode}")
            elif param.name == 'heading_mode':
                self._heading_mode = str(param.value)
                self.get_logger().info(f"特征开关: heading_mode -> {self._heading_mode}")
            elif param.name == 'constant_depth_m':
                self._constant_depth_m = float(param.value)
            elif param.name == 'constant_heading_rad':
                self._constant_heading_rad = float(param.value)
            elif param.name == 'bypass_zero_effort':
                self._bypass_zero_effort = bool(param.value)
                self.get_logger().info(f"特征开关: bypass_zero_effort -> {self._bypass_zero_effort}")
        return SetParametersResult(successful=True)

    def _apply_heading_ramp(self, target_rad: float, now: float) -> float:
        """如果 target_heading 跳变超过阈值，自动生成斜坡信号。

        防止 AMD 侧 PID 产生过大的冲击电流。
        """
        target_deg = math.degrees(target_rad)
        delta = abs(target_deg - self._last_heading_cmd)

        if delta > self._heading_ramp_limit_deg and not self._heading_ramp_active:
            self._heading_ramp_active = True
            self._heading_ramp_start = now
            self._heading_ramp_target = target_deg
            self.get_logger().info(
                f'Heading ramp activated: {self._last_heading_cmd:.1f}° -> {target_deg:.1f}°'
            )

        if self._heading_ramp_active:
            elapsed = now - self._heading_ramp_start
            max_delta = self._heading_ramp_rate_deg_s * elapsed
            actual_delta = min(max_delta, abs(self._heading_ramp_target - self._last_heading_cmd))
            direction = 1 if self._heading_ramp_target > self._last_heading_cmd else -1
            result = self._last_heading_cmd + direction * actual_delta

            if abs(result - self._heading_ramp_target) < 0.1:
                self._heading_ramp_active = False
                result = self._heading_ramp_target

            self._last_heading_cmd = result
            return math.radians(result)

        self._last_heading_cmd = target_deg
        return target_rad

    def _on_timer(self) -> None:
        """控制周期主回调：读取状态、计算控制量并发布。"""
        if self.latest_setpoint is None:
            return

        st, state_source, state_source_fallback, state_ts = self._select_state()
        if st is None:
            return

        # --- 导引旁路与特征控制链处理 ---
        # 复制 Setpoint 以便修改
        sp = Setpoint()
        sp.target_depth_m = self.latest_setpoint.target_depth_m
        sp.target_heading_rad = self.latest_setpoint.target_heading_rad
        sp.target_speed_mps = self.latest_setpoint.target_speed_mps
        
        is_altitude_follow = (self.latest_setpoint.mode == 'ALTITUDE_FOLLOW' or self._depth_mode == 'TERRAIN_FOLLOWING')
        
        # 1. 深度源选择
        work_instruction = 0x00
        if is_altitude_follow:
            target_altitude_m = float(self.latest_setpoint.target_depth_m)
            z_target, terrain_debug = self._terrain_follower.compute(self._terrain_perception, target_altitude_m)
            
            # 安全仲裁：防撞底
            if self._terrain_perception.get_altitude() < 1.5 and self._terrain_perception.get_altitude() > 0.01:
                z_target = self._terrain_perception.get_current_depth() - 2.0
                terrain_debug["safety_override"] = "EMERGENCY_RISE"
            
            # 安全仲裁：防冲出水面
            z_target = max(z_target, 0.5)
            sp.target_depth_m = z_target
            work_instruction = 0xEF
            
            # 发布地形调试信息
            self._terrain_debug_pub.publish(String(data=json.dumps(terrain_debug, ensure_ascii=False)))
            
        elif self._depth_mode == 'CONSTANT':
            sp.target_depth_m = self._constant_depth_m
        elif self._depth_mode == 'SINE_WAVE':
            sp.target_depth_m = self._constant_depth_m + 1.0 * math.sin(time.time() * 0.5)

        # 2. 航向源选择
        if self._heading_mode == 'CONSTANT':
            sp.target_heading_rad = self._constant_heading_rad

        # 打印当前控制链状态日志 (仅在状态改变时打印)
        current_chain = f"Heading:{self._heading_mode} + Depth:{self._depth_mode}"
        if current_chain != self._last_chain_status:
            self.get_logger().info(f"[Controller] Current Chain: {current_chain}")
            self._last_chain_status = current_chain

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

        # --- 指令平滑器 (Heading Ramping) ---
        # 指令平滑器：heading 跳变超过阈值时生成斜坡信号
        now = time.time()
        target_heading = float(sp.target_heading_rad)
        smoothed_heading = self._apply_heading_ramp(target_heading, now=now)

        setpoint = {
            'dt': 1.0 / max(self.control_rate_hz, 1e-3),
            'target_depth_m': float(sp.target_depth_m),
            'target_heading_rad': smoothed_heading,
            'target_speed_mps': float(sp.target_speed_mps),
        }

        if self._bypass_zero_effort:
            # 零推力零舵角保底输出，跳过控制器计算
            from auv_controller.base_controller import ControlOutput
            ctrl_output = ControlOutput(
                thrust_percent=0.0,
                right_fin_deg=0.0,
                top_fin_deg=0.0,
                left_fin_deg=0.0,
                bottom_fin_deg=0.0,
                debug={'note': 'Bypass zero effort active'}
            )
        else:
            # 调用当前活跃控制器
            ctrl_output = self._active_controller.compute(state, setpoint)

        if self._use_mpc or is_altitude_follow:
            # MPC 模式或高度跟随模式：发布 MpcCmd 消息（供 auv_bridge/arbiter 消费）
            mpc_msg = MpcCmd()
            mpc_msg.header.stamp = self.get_clock().now().to_msg()
            mpc_msg.source = 'JETSON_MPC'
            mpc_msg.valid = True
            mpc_msg.healthy = True
            mpc_msg.thrust_percent = float(ctrl_output.thrust_percent)
            mpc_msg.right_fin_deg = float(ctrl_output.right_fin_deg or 0.0)
            mpc_msg.top_fin_deg = float(ctrl_output.top_fin_deg or 0.0)
            mpc_msg.left_fin_deg = float(ctrl_output.left_fin_deg or 0.0)
            mpc_msg.bottom_fin_deg = float(ctrl_output.bottom_fin_deg or 0.0)
            mpc_msg.target_depth_m = float(sp.target_depth_m)
            mpc_msg.work_instruction = work_instruction
            mpc_msg.note = str(ctrl_output.debug.get('note', ''))
            
            self._mpc_cmd_pub.publish(mpc_msg)
        else:
            # PID 模式：直接发布 Twist
            tw = Twist()
            tw.linear.x = float(ctrl_output.thrust_percent)
            tw.angular.x = float(ctrl_output.right_fin_deg or 0.0)
            tw.angular.y = float(ctrl_output.top_fin_deg or 0.0)
            tw.angular.z = float(ctrl_output.left_fin_deg or 0.0)
            tw.linear.z = float(ctrl_output.bottom_fin_deg or 0.0)
            self.cmd_pub.publish(tw)

        # 延迟统计
        sensor_to_cmd = now - max(self.latest_setpoint_ts, state_ts)
        if sensor_to_cmd >= 0:
            self._lat_count += 1
            self._lat_sum += sensor_to_cmd

        # 构建调试信息
        cmd = [
            ctrl_output.right_fin_deg or 0.0,
            ctrl_output.top_fin_deg or 0.0,
            ctrl_output.left_fin_deg or 0.0,
            ctrl_output.bottom_fin_deg or 0.0,
            ctrl_output.thrust_percent,
        ]

        self.latest_debug_payload = {
            'mode': 'MPC' if self._use_mpc else 'PID',
            'control_mode_byte': self._control_mode_byte,
            'thrust_cmd': ctrl_output.thrust_percent,
            'guidance_heading': smoothed_heading,
            'guidance_depth': setpoint.get('target_depth_m', 0.0),
            'rate_source': rate_source,
            KEY_STATE_SOURCE: state_source.value,
            'state_source_requested': StateEstimateSource.RAW_DR.value if self.bypass_ekf else StateEstimateSource.FILTERED.value,
            'state_source_fallback': bool(state_source_fallback),
            'attitude_guard_active': bool(ctrl_output.debug.get('attitude_guard_active', False)),
            'current_roll_deg': round(float(ctrl_output.debug.get('current_roll_deg', 0.0)), 3),
            'current_pitch_deg': round(float(ctrl_output.debug.get('current_pitch_deg', 0.0)), 3),
            'depth_error_m': round(depth_error, 4),
            'yaw_error_deg': round(math.degrees(yaw_error), 3),
            'current_yaw_deg': round(math.degrees(yaw), 3),
            'target_yaw_deg': round(math.degrees(float(sp.target_heading_rad)), 3),
            'target_depth_m': round(float(sp.target_depth_m), 3),
            'current_depth_m': round(float(-st.pose.pose.position.z), 3),
            'target_speed_mps': round(float(sp.target_speed_mps), 3),
            'current_speed_mps': round(float(st.twist.twist.linear.x), 3),
            'pitch_saturated': bool(ctrl_output.debug.get('pitch_saturated', False)),
            'yaw_saturated': bool(ctrl_output.debug.get('yaw_saturated', False)),
            'thrust_saturated': bool(ctrl_output.debug.get('thrust_saturated', False)),
            'target_pitch_deg': round(math.degrees(float(ctrl_output.debug.get('target_pitch_rad', 0.0))), 3),
            'bypass_ekf': bool(self.bypass_ekf),
            'fin_passthrough': bool(ctrl_output.debug.get('fin_passthrough', False)),
            'cmd': {
                'right_deg': round(float(cmd[0]), 3),
                'top_deg': round(float(cmd[1]), 3),
                'left_deg': round(float(cmd[2]), 3),
                'bottom_deg': round(float(cmd[3]), 3),
                'thrust': round(float(cmd[4]), 3),
            },
        }

    def _log_latency(self) -> None:
        """周期性打印控制链路的平均延迟统计。"""
        if self._lat_count == 0:
            return
        mean_ms = (self._lat_sum / self._lat_count) * 1000.0
        self.get_logger().info(f'[controller] mean state/setpoint->cmd latency: {mean_ms:.2f} ms over {self._lat_count} samples')

    def _publish_debug(self) -> None:
        """发布控制调试信息，供可视化和日志订阅。"""
        if self.latest_debug_payload is None:
            return
        payload = self.latest_debug_payload
        cleaned = self._sanitize_for_json(payload)
        try:
            json_str = json.dumps(cleaned, ensure_ascii=False)
            self.debug_pub.publish(String(data=json_str))
        except (TypeError, ValueError) as e:
            self.get_logger().error(f'Failed to serialize debug payload: {e}')
            # Fallback: publish minimal info
            minimal = {
                'mode': cleaned.get('mode', 'UNKNOWN'),
                'error': str(e),
                'thrust_cmd': cleaned.get('thrust_cmd', 0),
            }
            self.debug_pub.publish(String(data=json.dumps(minimal, ensure_ascii=False)))

    @staticmethod
    def _sanitize_for_json(obj: Any) -> Any:
        """将 dict/list 中的 numpy 类型和非 JSON 兼容类型转为标准 Python 类型。"""
        import numpy as np

        if isinstance(obj, dict):
            return {k: AUVControllerNode._sanitize_for_json(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            return [AUVControllerNode._sanitize_for_json(v) for v in obj]

        # 所有 numpy 标量类型
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        if isinstance(obj, (np.bool_,)):
            return bool(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, np.generic):
            return obj.item()

        return obj


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

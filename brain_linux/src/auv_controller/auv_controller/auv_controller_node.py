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
from rclpy.executors import ExternalShutdownException
from auv_interfaces.msg import (
    ArbiterStatus,
    CableTrackingAuthority,
    MpcCmd,
    Setpoint,
)
from geometry_msgs.msg import Twist, TwistStamped
from nav_msgs.msg import Odometry
from rcl_interfaces.msg import SetParametersResult
from rclpy.node import Node
from sensor_msgs.msg import Imu
from std_msgs.msg import String, Float32, Float32MultiArray
import numpy as np
import yaml

from common.enums import StateEstimateSource, ControlModeByte
from common.protocol import KEY_STATE_SOURCE
from common.env_utils import load_config_with_overrides
from auv_decision_ros.sensor_runtime import capability_available, capability_missing_sensors

from .base_controller import BaseController, ControlOutput
from .pid_controller import PIDController
from .mpc_controller import MPCController
from .terrain_engine import TerrainFollower
from .terrain_perception import ROSTerrainPerception
from .virtual_sonar_wrapper import VirtualSonarWrapper
from .mappers import clamp_int16
from .quality_control_policy import (
    AuthoritySnapshot,
    ConservativeQualityControlPolicy,
)

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


def _should_publish_semantic_command(
    *,
    use_mpc: bool,
    is_altitude_follow: bool,
    publish_arbiter_command: bool,
) -> bool:
    """Return whether this cycle must use the arbiter command path."""
    return bool(use_mpc or is_altitude_follow or publish_arbiter_command)


def _resolve_guidance_depth(
    ctrl_output: ControlOutput,
    *,
    fallback_depth_m: float,
    force_fallback: bool = False,
) -> float:
    """Select a finite controller guidance depth, falling back to the setpoint."""
    if force_fallback:
        return float(fallback_depth_m)
    if ctrl_output.guidance_depth is not None:
        try:
            value = float(ctrl_output.guidance_depth)
        except (TypeError, ValueError):
            value = math.nan
        if math.isfinite(value):
            return value
    return float(fallback_depth_m)


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
        self.declare_parameter('publish_arbiter_command', False)
        self.declare_parameter('control_mode_byte', int(ControlModeByte.JETSON_HYBRID))
        self.declare_parameter('heading_ramp_limit_deg', 30.0)
        self.declare_parameter('heading_ramp_rate_deg_s', 10.0)
        self.declare_parameter('runtime_status_topic', '/auv/sensors/runtime_status')
        self.declare_parameter('enable_capability_gate', True)
        self.declare_parameter('quality_control.enable', False)
        self.declare_parameter('quality_control.accept_shadow', False)
        self.declare_parameter(
            'quality_control.allowed_calibration_domain',
            'physical',
        )
        self.declare_parameter('quality_control.maximum_age_s', 0.75)
        self.declare_parameter('quality_control.minimum_speed_scale', 0.35)
        self.declare_parameter(
            'quality_control.maximum_delta_u_penalty_scale',
            4.0,
        )
        self.declare_parameter(
            'quality_control.maximum_safety_margin_scale',
            1.5,
        )

        # --- 特征开关 (Feature Flags) ---
        self.declare_parameter('depth_mode', 'CONSTANT')
        self.declare_parameter('heading_mode', 'CONSTANT')
        self.declare_parameter('constant_depth_m', 2.0)
        self.declare_parameter('constant_heading_rad', 0.0)
        self.declare_parameter('bypass_zero_effort', False)

        params_file = str(self.get_parameter('params_file').value)
        cfg = self._load_config(params_file)

        ctrl_cfg = dict(cfg.get('control', {}))
        for section in ('mpc', 'mpc_model', 'mpc_weights', 'mpc_constraints'):
            if section in cfg:
                ctrl_cfg[section] = cfg[section]
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
        self._publish_arbiter_command = bool(
            self.get_parameter('publish_arbiter_command').value
        )
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
        self._runtime_status_topic = str(self.get_parameter('runtime_status_topic').value)
        self._enable_capability_gate = bool(self.get_parameter('enable_capability_gate').value)

        self._depth_mode = str(self.get_parameter('depth_mode').value)
        self._heading_mode = str(self.get_parameter('heading_mode').value)
        self._constant_depth_m = float(self.get_parameter('constant_depth_m').value)
        self._constant_heading_rad = float(self.get_parameter('constant_heading_rad').value)
        self._bypass_zero_effort = bool(self.get_parameter('bypass_zero_effort').value)
        self._last_chain_status = ""

        # 实例化地形跟踪模块
        terrain_cbf_cfg = dict(ctrl_cfg.get('terrain_cbf', {}) or {})
        self._terrain_perception = ROSTerrainPerception()
        self._terrain_follower = TerrainFollower(
            lookahead_time_s=float(terrain_cbf_cfg.get('lookahead_time_s', 2.0)),
            lpf_alpha=float(terrain_cbf_cfg.get('lpf_alpha', 0.2)),
            min_clearance_m=float(terrain_cbf_cfg.get('min_clearance_m', 1.8)),
            cbf_alpha=float(terrain_cbf_cfg.get('alpha', 0.7)),
            cbf_dt_s=float(
                terrain_cbf_cfg.get(
                    'dt_s',
                    1.0 / max(self.control_rate_hz, 1.0e-3),
                )
            ),
            max_descend_rate_mps=float(
                terrain_cbf_cfg.get('max_descend_rate_mps', 0.4)
            ),
            emergency_clearance_m=float(
                terrain_cbf_cfg.get('emergency_clearance_m', 1.2)
            ),
            emergency_rise_m=float(
                terrain_cbf_cfg.get('emergency_rise_m', 2.0)
            ),
            slowdown_clearance_margin_m=float(
                terrain_cbf_cfg.get('slowdown_clearance_margin_m', 1.5)
            ),
            minimum_control_speed_scale=float(
                terrain_cbf_cfg.get('minimum_control_speed_scale', 0.0)
            ),
            min_depth_m=float(terrain_cbf_cfg.get('min_depth_m', 0.5)),
        )

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
        self.latest_arbiter_status: ArbiterStatus | None = None
        self.latest_runtime_status: dict | None = None
        self._last_capability_gate_reason = ""
        self.latest_tracking_authority: CableTrackingAuthority | None = None
        self.latest_tracking_authority_monotonic_s = 0.0
        self._quality_control_policy = ConservativeQualityControlPolicy(
            enabled=bool(
                self.get_parameter('quality_control.enable').value
            ),
            accept_shadow=bool(
                self.get_parameter('quality_control.accept_shadow').value
            ),
            allowed_calibration_domain=str(
                self.get_parameter(
                    'quality_control.allowed_calibration_domain'
                ).value
            ),
            maximum_age_s=float(
                self.get_parameter('quality_control.maximum_age_s').value
            ),
            minimum_speed_scale=float(
                self.get_parameter(
                    'quality_control.minimum_speed_scale'
                ).value
            ),
            maximum_delta_u_penalty_scale=float(
                self.get_parameter(
                    'quality_control.maximum_delta_u_penalty_scale'
                ).value
            ),
            maximum_safety_margin_scale=float(
                self.get_parameter(
                    'quality_control.maximum_safety_margin_scale'
                ).value
            ),
        )
        self._latest_quality_control_decision = None

        # E4 — EKF 协方差驱动的置信度（论文 §4.4 主创新点）
        self._latest_p_trace_xy = float('nan')
        self._latest_p_trace_z = float('nan')
        self.declare_parameter('cov_to_conf.enable', True)
        self.declare_parameter('cov_to_conf.sigma_xy_ref', 1.0)
        self.declare_parameter('cov_to_conf.sigma_z_ref', 0.5)
        self._cov_conf_enable = bool(self.get_parameter('cov_to_conf.enable').value)
        self._sigma_xy_ref = float(self.get_parameter('cov_to_conf.sigma_xy_ref').value)
        self._sigma_z_ref = float(self.get_parameter('cov_to_conf.sigma_z_ref').value)
        env_mode = os.environ.get('AUV_MPC_MODE', 'ua').strip().lower()
        if env_mode == 'baseline':
            self._cov_conf_enable = False

        self.arbiter_status_sub = self.create_subscription(ArbiterStatus, '/auv/arbiter/status', self._on_arbiter_status, 20)
        self.setpoint_sub = self.create_subscription(Setpoint, '/auv/control/setpoint', self._on_setpoint, 20)
        self.filtered_state_sub = self.create_subscription(Odometry, self.filtered_state_topic, self._on_filtered_state, 20)
        self.raw_state_sub = self.create_subscription(Odometry, self.raw_state_topic, self._on_raw_state, 20)
        self.imu_sub = self.create_subscription(Imu, '/auv/sensors/imu', self._on_imu, 20)
        self.dvl_sub = self.create_subscription(TwistStamped, '/auv/sensors/dvl', self._on_dvl, 20)
        self.depth_sub = self.create_subscription(Float32, '/auv/sensors/depth', self._on_depth, 20)
        self.altitude_sub = self.create_subscription(Float32, '/auv/sensors/altitude', self._on_altitude, 20)
        self.forward_sonar_sub = self.create_subscription(Float32, '/auv/sensors/forward_sonar_slope', self._on_forward_sonar, 20)
        self.cov_sub = self.create_subscription(Float32MultiArray, '/auv/state/covariance', self._on_covariance, 20)
        self.runtime_status_sub = self.create_subscription(String, self._runtime_status_topic, self._on_runtime_status, 20)
        self.tracking_authority_sub = self.create_subscription(
            CableTrackingAuthority,
            '/auv/perception/cable_tracking_authority_shadow',
            self._on_tracking_authority,
            20,
        )

        self.cmd_pub = self.create_publisher(Twist, '/cmd_vel', 20)
        self.debug_pub = self.create_publisher(String, '/auv/controller/debug', 20)
        self._mpc_cmd_pub = self.create_publisher(MpcCmd, '/auv/control/mpc_cmd', 20)
        self._terrain_debug_pub = self.create_publisher(String, '/auv/controller/terrain_debug', 20)
        self._control_timer = self.create_timer(1.0 / max(self.control_rate_hz, 1e-3), self._on_timer)

        self._lat_count = 0
        self._lat_sum = 0.0
        self._control_cycle_count_total = 0
        self._solver_attempt_count_total = 0
        self._solver_success_count_total = 0
        self._solver_fallback_count_total = 0
        self._solver_blocked_count_total = 0
        self._debug_publish_period_s = 0.5
        self.create_timer(2.0, self._log_latency)
        self.create_timer(self._debug_publish_period_s, self._publish_debug)
        self._param_callback = self.add_on_set_parameters_callback(self._on_parameters_changed)

        mode_str = 'MPC' if self._use_mpc else 'PID'
        self.get_logger().info(f'auv_controller_node started ({mode_str} mode)')
        self.get_logger().info(f'Control mode byte: 0x{self._control_mode_byte:02X}')

    @staticmethod
    def _load_config(path: str) -> dict:
        """加载控制参数 YAML，并确保配置结构是字典。"""
        cfg = load_config_with_overrides(path)
        if not isinstance(cfg, dict):
            raise RuntimeError('invalid controller params yaml')
        return cfg

    def _on_arbiter_status(self, msg: ArbiterStatus) -> None:
        """缓存最新仲裁器状态。"""
        self.latest_arbiter_status = msg

    def _on_tracking_authority(
        self,
        msg: CableTrackingAuthority,
    ) -> None:
        self.latest_tracking_authority = msg
        self.latest_tracking_authority_monotonic_s = time.monotonic()

    def _on_setpoint(self, msg: Setpoint) -> None:
        """缓存最新控制目标并记录时间戳。"""
        self.latest_setpoint = msg
        self.latest_setpoint_ts = time.time()

    def _on_runtime_status(self, msg: String) -> None:
        try:
            payload = json.loads(msg.data)
        except json.JSONDecodeError as exc:
            self.get_logger().warning(f'failed to parse runtime status: {exc}')
            return
        if isinstance(payload, dict):
            self.latest_runtime_status = payload

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

    def _on_forward_sonar(self, msg: Float32) -> None:
        """灌入前视声呐斜率到地形跟踪引擎。"""
        VirtualSonarWrapper().update_slope(float(msg.data))

    def _on_covariance(self, msg: Float32MultiArray) -> None:
        """E4 — 订阅 ES-EKF 15x15 P 矩阵 (Float32MultiArray 225 元素)。"""
        data = list(msg.data)
        if len(data) != 225:
            return
        try:
            p = np.asarray(data, dtype=float).reshape(15, 15)
        except Exception:
            return
        self._latest_p_trace_xy = float(p[0, 0] + p[1, 1])
        self._latest_p_trace_z = float(p[2, 2])

    def _confidence_from_cov(self) -> float | None:
        """E4 — 把 EKF P 协方差 trace 映射为置信度 [0,1]；不可用时返回 None。"""
        if not self._cov_conf_enable:
            return None
        if not math.isfinite(self._latest_p_trace_xy):
            return None
        sigma = max(self._sigma_xy_ref, 1e-6)
        conf = math.exp(-self._latest_p_trace_xy / sigma)
        if conf < 0.0:
            conf = 0.0
        elif conf > 1.0:
            conf = 1.0
        return float(conf)

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
        if self._enable_capability_gate and is_altitude_follow and not capability_available(
            self.latest_runtime_status,
            'terrain_following',
        ):
            missing = capability_missing_sensors(self.latest_runtime_status, 'terrain_following')
            reason = f"terrain_following_missing:{','.join(missing) if missing else 'unknown'}"
            if self._last_capability_gate_reason != reason:
                self.get_logger().warning(
                    f'[capability_gate] terrain following disabled, missing={missing}; publishing zero-effort hold'
                )
                self._last_capability_gate_reason = reason
            self._publish_zero_effort_hold(reason=reason, sp=self.latest_setpoint)
            return
        self._last_capability_gate_reason = ""
        
        # 1. 深度源选择
        work_instruction = 0x00
        terrain_debug: dict[str, object] = {}
        if is_altitude_follow:
            target_altitude_m = float(self.latest_setpoint.target_depth_m)
            z_target, terrain_debug = self._terrain_follower.compute(self._terrain_perception, target_altitude_m)
            
            # 紧急上浮由 CBF 配置统一触发，并在 MPC 求解后保持最高优先级。
            if bool(terrain_debug.get("cbf_emergency_active", False)):
                terrain_debug["safety_override"] = "EMERGENCY_RISE"
            
            # 安全仲裁：防冲出水面
            z_target = max(z_target, 0.5)
            sp.target_depth_m = z_target
            cbf_speed_scale = float(terrain_debug.get("cbf_speed_scale", 1.0))
            cbf_speed_scale = min(1.0, max(0.0, cbf_speed_scale))
            original_speed_mps = float(sp.target_speed_mps)
            sp.target_speed_mps = original_speed_mps * cbf_speed_scale
            terrain_debug["cbf_original_speed_mps"] = original_speed_mps
            terrain_debug["cbf_filtered_speed_mps"] = float(sp.target_speed_mps)
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

        # --- 无扰动切换 (Bumpless Transfer) ---
        is_autonomous = False
        if self.latest_arbiter_status is not None:
            is_autonomous = (self.latest_arbiter_status.active_arbiter == 'AUTONOMOUS')

        if not is_autonomous:
            # 重置积分
            if hasattr(self._active_controller, 'reset'):
                self._active_controller.reset()
            # 状态跟随 (Setpoint Shadowing)
            sp.target_depth_m = float(-st.pose.pose.position.z)
            sp.target_heading_rad = yaw

        # === 全局深度安全围栏 (BUG-8: 所有模式通用, 与VxWorks多层协调) ===
        _MAX_DEPTH_M = 50.0   # 最大允许深度
        _MIN_ALTITUDE_M = 2.0  # 最小允许离底高度 (高于VxWorks硬限1.8m)

        # 1. 深度绝对上限
        if sp.target_depth_m > _MAX_DEPTH_M:
            sp.target_depth_m = _MAX_DEPTH_M

        # 2. 离底高度围栏 (当altitude有效且不在ALTITUDE_FOLLOW模式时)
        _current_altitude = self._terrain_perception.get_altitude()
        if (not is_altitude_follow
                and _current_altitude > 0.01
                and _current_altitude < _MIN_ALTITUDE_M):
            _current_depth = float(-st.pose.pose.position.z)
            sp.target_depth_m = min(sp.target_depth_m, _current_depth - 1.0)

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

        # E4 — 用 EKF 协方差驱动的置信度覆盖 setpoint["confidence"]
        conf_from_cov = self._confidence_from_cov()
        if conf_from_cov is not None:
            setpoint['confidence'] = conf_from_cov
            self._latest_confidence = conf_from_cov

        authority_snapshot = None
        if self.latest_tracking_authority is not None:
            authority_snapshot = AuthoritySnapshot(
                mode=int(self.latest_tracking_authority.mode),
                tracking_authorized=bool(
                    self.latest_tracking_authority.tracking_authorized
                ),
                p_track=float(self.latest_tracking_authority.p_track),
                calibration_domain=str(
                    self.latest_tracking_authority.calibration_domain
                ),
                shadow_only=bool(
                    self.latest_tracking_authority.shadow_only
                ),
                age_s=max(
                    time.monotonic()
                    - self.latest_tracking_authority_monotonic_s,
                    0.0,
                ),
            )
        policy_input_target_speed_mps = float(setpoint['target_speed_mps'])
        # Doxygen telemetry contract: expose the R13 authority decision without changing the control law.
        authority_debug_snapshot = None
        if authority_snapshot is not None:
            authority_debug_snapshot = {
                'mode': int(authority_snapshot.mode),
                'tracking_authorized': bool(authority_snapshot.tracking_authorized),
                'p_track': float(authority_snapshot.p_track),
                'calibration_domain': str(authority_snapshot.calibration_domain),
                'shadow_only': bool(authority_snapshot.shadow_only),
                'age_s': float(authority_snapshot.age_s),
            }
        quality_decision = self._quality_control_policy.apply(
            policy_input_target_speed_mps,
            authority_snapshot,
        )
        self._latest_quality_control_decision = quality_decision
        if quality_decision.accepted:
            setpoint['target_speed_mps'] = (
                quality_decision.target_speed_mps
            )
            setpoint['confidence'] = float(quality_decision.confidence)
            setpoint['delta_u_penalty_scale'] = (
                quality_decision.delta_u_penalty_scale
            )
            setpoint['safety_margin_scale'] = (
                quality_decision.safety_margin_scale
            )
            self._latest_confidence = float(quality_decision.confidence)
        applied_target_speed_mps = float(
            setpoint.get('target_speed_mps', policy_input_target_speed_mps)
        )
        if abs(policy_input_target_speed_mps) > 1.0e-9:
            quality_speed_scale = (
                applied_target_speed_mps / policy_input_target_speed_mps
            )
        else:
            quality_speed_scale = 0.0 if abs(applied_target_speed_mps) <= 1.0e-9 else None

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

        guidance_depth_m = _resolve_guidance_depth(
            ctrl_output,
            fallback_depth_m=float(sp.target_depth_m),
            force_fallback=bool(terrain_debug.get("safety_override")),
        )
        self._control_cycle_count_total += 1
        if ctrl_output.debug.get('controller_type') == 'MPC':
            self._solver_attempt_count_total += 1
            solver_status = str(ctrl_output.debug.get('solver_status', ''))
            if solver_status in (
                'Solve_Succeeded',
                'Search_Direction_Becomes_Too_Small',
            ):
                self._solver_success_count_total += 1
            if solver_status.startswith('FALLBACK'):
                self._solver_fallback_count_total += 1
            if bool(ctrl_output.debug.get('control_period_blocked', False)):
                self._solver_blocked_count_total += 1

        if _should_publish_semantic_command(
            use_mpc=self._use_mpc,
            is_altitude_follow=is_altitude_follow,
            publish_arbiter_command=self._publish_arbiter_command,
        ):
            # 语义控制路径：由 arbiter 统一下发推力和 PVS 内层参考。
            mpc_msg = MpcCmd()
            mpc_msg.header.stamp = self.get_clock().now().to_msg()
            mpc_msg.source = 'JETSON_MPC' if self._use_mpc else 'JETSON_PID'
            mpc_msg.valid = True
            mpc_msg.healthy = True
            mpc_msg.thrust_percent = float(ctrl_output.thrust_percent)
            mpc_msg.right_fin_deg = float(ctrl_output.right_fin_deg or 0.0)
            mpc_msg.top_fin_deg = float(ctrl_output.top_fin_deg or 0.0)
            mpc_msg.left_fin_deg = float(ctrl_output.left_fin_deg or 0.0)
            mpc_msg.bottom_fin_deg = float(ctrl_output.bottom_fin_deg or 0.0)
            mpc_msg.target_depth_m = guidance_depth_m
            mpc_msg.work_instruction = work_instruction
            mpc_msg.note = str(ctrl_output.debug.get('note', ''))

            try:
                self._mpc_cmd_pub.publish(mpc_msg)
            except Exception:
                if not rclpy.ok():
                    return
                raise
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
            'controller_type': ctrl_output.debug.get('controller_type', 'MPC' if self._use_mpc else 'PID'),
            'solver_status': ctrl_output.debug.get('solver_status', ''),
            'solver_return_status': ctrl_output.debug.get('solver_return_status', ''),
            'prediction_horizon': ctrl_output.debug.get('prediction_horizon', None),
            'mpc_prediction_dt_s': ctrl_output.debug.get('dt', None),
            'solver_iterations': ctrl_output.debug.get('solver_iterations', None),
            'solve_time_ms': ctrl_output.debug.get('solve_time_ms', None),
            'solve_time_source': ctrl_output.debug.get('solve_time_source', ''),
            'solver_wall_time_current_ms': ctrl_output.debug.get('solver_wall_time_current_ms', None),
            'total_compute_ms': ctrl_output.debug.get('total_compute_ms', None),
            'fallback_reason': ctrl_output.debug.get('fallback_reason', ''),
            'fallback_type': ctrl_output.debug.get('fallback_type', 'none'),
            'confidence': ctrl_output.debug.get(
                'confidence', self._latest_confidence
            ),
            'confidence_policy': ctrl_output.debug.get(
                'confidence_policy', ''
            ),
            'delta_u_previous_control_available': ctrl_output.debug.get(
                'delta_u_previous_control_available', False
            ),
            'quality_control_policy': {
                'accepted': bool(
                    self._latest_quality_control_decision
                    and self._latest_quality_control_decision.accepted
                ),
                'reason': (
                    self._latest_quality_control_decision.reason
                    if self._latest_quality_control_decision
                    else 'not_evaluated'
                ),
                'input_target_speed_mps': policy_input_target_speed_mps,
                'target_speed_mps': (
                    self._latest_quality_control_decision.target_speed_mps
                    if self._latest_quality_control_decision
                    else policy_input_target_speed_mps
                ),
                'applied_target_speed_mps': applied_target_speed_mps,
                'speed_scale': quality_speed_scale,
                'confidence': (
                    self._latest_quality_control_decision.confidence
                    if self._latest_quality_control_decision
                    else None
                ),
                'delta_u_penalty_scale': (
                    self._latest_quality_control_decision.delta_u_penalty_scale
                    if self._latest_quality_control_decision
                    else 1.0
                ),
                'safety_margin_scale': (
                    self._latest_quality_control_decision.safety_margin_scale
                    if self._latest_quality_control_decision
                    else 1.0
                ),
                'authority_snapshot': authority_debug_snapshot,
            },
            'debug_publish_period_s': self._debug_publish_period_s,
            'control_cycle_count_total': self._control_cycle_count_total,
            'solver_attempt_count_total': self._solver_attempt_count_total,
            'solver_success_count_total': self._solver_success_count_total,
            'solver_fallback_count_total': self._solver_fallback_count_total,
            'solver_blocked_count_total': self._solver_blocked_count_total,
            'control_period_ms': ctrl_output.debug.get('control_period_ms', None),
            'control_period_blocked': ctrl_output.debug.get('control_period_blocked', False),
            'warm_start_provided': ctrl_output.debug.get('warm_start_provided', False),
            'warm_start_used': ctrl_output.debug.get('warm_start_used', False),
            'warm_start_control_shift_rms': ctrl_output.debug.get('warm_start_control_shift_rms', None),
            'initial_guess_source': ctrl_output.debug.get('initial_guess_source', ''),
            'initial_guess_projection_rms': ctrl_output.debug.get('initial_guess_projection_rms', None),
            'state_initial_jump_l2': ctrl_output.debug.get('state_initial_jump_l2', None),
            'constraint_slack_enabled': ctrl_output.debug.get('constraint_slack_enabled', False),
            'slack_max': ctrl_output.debug.get('slack_max', None),
            'slack_l1': ctrl_output.debug.get('slack_l1', None),
            'slack_l2': ctrl_output.debug.get('slack_l2', None),
            'slack_active_count': ctrl_output.debug.get('slack_active_count', None),
            'constraint_count': ctrl_output.debug.get('constraint_count', None),
            'initial_constraint_violation_max': ctrl_output.debug.get('initial_constraint_violation_max', None),
            'initial_constraint_violation_l2': ctrl_output.debug.get('initial_constraint_violation_l2', None),
            'initial_active_constraint_count': ctrl_output.debug.get('initial_active_constraint_count', None),
            'final_constraint_violation_max': ctrl_output.debug.get('final_constraint_violation_max', None),
            'final_constraint_violation_l2': ctrl_output.debug.get('final_constraint_violation_l2', None),
            'final_active_constraint_count': ctrl_output.debug.get('final_active_constraint_count', None),
            'capability_gate_status': 'passed',
            'thrust_cmd': ctrl_output.thrust_percent,
            'guidance_heading': smoothed_heading,
            'guidance_depth': guidance_depth_m,
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
            'requested_target_speed_mps': round(policy_input_target_speed_mps, 3),
            'applied_target_speed_mps': round(applied_target_speed_mps, 3),
            'current_speed_mps': round(float(st.twist.twist.linear.x), 3),
            'terrain_cbf': {
                key: terrain_debug.get(key)
                for key in (
                    'cbf_enabled',
                    'cbf_active',
                    'cbf_reason',
                    'cbf_min_clearance_m',
                    'cbf_barrier_now_m',
                    'cbf_preview_barrier_m',
                    'cbf_barrier_decay_reference_m',
                    'cbf_depth_upper_m',
                    'cbf_descend_rate_limited',
                    'cbf_emergency_active',
                    'cbf_emergency_rise_m',
                    'cbf_filtered_depth_m',
                    'cbf_speed_scale',
                    'cbf_raw_speed_scale',
                    'cbf_minimum_control_speed_scale',
                    'cbf_original_speed_mps',
                    'cbf_filtered_speed_mps',
                    'S_now',
                    'S_future',
                    'slope_source',
                    'estimated_slope',
                )
                if key in terrain_debug
            },
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

    def _publish_zero_effort_hold(self, *, reason: str, sp: Setpoint) -> None:
        tw = Twist()
        self.cmd_pub.publish(tw)

        mpc_msg = MpcCmd()
        mpc_msg.header.stamp = self.get_clock().now().to_msg()
        mpc_msg.source = 'CAPABILITY_GATE'
        mpc_msg.valid = True
        mpc_msg.healthy = False
        mpc_msg.thrust_percent = 0.0
        mpc_msg.right_fin_deg = 0.0
        mpc_msg.top_fin_deg = 0.0
        mpc_msg.left_fin_deg = 0.0
        mpc_msg.bottom_fin_deg = 0.0
        mpc_msg.target_depth_m = float(sp.target_depth_m)
        mpc_msg.work_instruction = 0
        mpc_msg.note = reason
        self._mpc_cmd_pub.publish(mpc_msg)

        self.latest_debug_payload = {
            'mode': 'CAPABILITY_DEGRADED_HOLD',
            'controller_type': 'CAPABILITY_GATE',
            'fallback_reason': reason,
            'fallback_type': 'capability_gate_hold',
            'capability_gate_status': 'blocked',
            'thrust_cmd': 0.0,
            'guidance_heading': float(sp.target_heading_rad),
            'guidance_depth': float(sp.target_depth_m),
            'target_speed_mps': 0.0,
            'cmd': {
                'right_deg': 0.0,
                'top_deg': 0.0,
                'left_deg': 0.0,
                'bottom_deg': 0.0,
                'thrust': 0.0,
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

##
# @brief Run the controller node until the ROS context stops.
# @param args Optional ROS CLI arguments.
def main(args=None) -> None:
    rclpy.init(args=args)
    node = AUVControllerNode()
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

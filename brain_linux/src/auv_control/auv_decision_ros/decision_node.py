#!/usr/bin/env python3
"""AUV 决策节点（ROS2 包装层）。

设计说明：
- 本节点只负责 ROS2 通信与调度；
- 核心逻辑（行为树、装饰器、阈值判断、观测快照组装）全部在 `auv_decision_core` 内；
- 通过 10Hz 定时器驱动行为树 tick，并发布控制目标、行为树状态和结构化诊断。
"""

from __future__ import annotations

import math

from nav_msgs.msg import Odometry
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import MagneticField
from std_msgs.msg import Float32, String
import json

from auv_decision_core.bt_engine import DecisionTreeEngine
from auv_decision_core.models import SensorStatusData
from auv_decision_core.telemetry import DecisionTelemetrySnapshot, build_decision_telemetry_snapshot
from auv_interfaces.msg import AuvDiagnostic, ArbiterStatus, ControlGoal, SensorStatus, Setpoint
from common.enums import WorkInstruction

from .mappers import (
    motion_goal_dict_to_msg,
    motion_goal_dict_to_setpoint_msg,
    sensor_msg_to_core,
    telemetry_snapshot_to_msg,
)


class AUVDecisionNode(Node):
    """AUV 决策 ROS2 节点的包装层。

    该节点不实现业务决策本身，而是负责把 ROS2 话题输入转换成决策引擎可消费的
    结构化状态，再把行为树输出的控制目标、诊断信息和状态摘要发布出去。
    """

    def __init__(self) -> None:
        """初始化 ROS2 参数、订阅/发布器、决策引擎和运行时缓存。"""
        super().__init__('auv_decision_node')

        self.declare_parameter('confidence_threshold', 0.7)
        self.declare_parameter('bt_status_publish_period', 0.5)
        self.declare_parameter('tree_print_period', 1.0)
        self.declare_parameter('summary_log_period', 1.0)
        self.declare_parameter('bridge_backend', 'zenoh_json')
        self.declare_parameter('protocol_control_mode_byte', 0xEE)
        self.declare_parameter('guidance_lookahead_distance', 3.5)
        self.declare_parameter('guidance_cross_track_gain', 0.7)
        self.declare_parameter('mock_amd_timeout_s', 5.0)
        self.declare_parameter('debug_level', 0)  # 0:AUTO, 1:HOLD, 2:PATH, 3:FULL
        self.declare_parameter('transition_threshold_m', 2.0)  # 触发平滑过渡的跳变阈值（米）
        self.declare_parameter('transition_duration_s', 3.0)  # 平滑过渡持续时间（秒）

        threshold = float(self.get_parameter('confidence_threshold').value)
        self.bt_status_publish_period = float(self.get_parameter('bt_status_publish_period').value)
        self.tree_print_period = float(self.get_parameter('tree_print_period').value)
        self.summary_log_period = float(self.get_parameter('summary_log_period').value)
        self.bridge_backend = str(self.get_parameter('bridge_backend').value)
        self.protocol_control_mode_byte = int(self.get_parameter('protocol_control_mode_byte').value)
        self.guidance_lookahead_distance = float(self.get_parameter('guidance_lookahead_distance').value)
        self.guidance_cross_track_gain = float(self.get_parameter('guidance_cross_track_gain').value)
        self.mock_amd_timeout_s = float(self.get_parameter('mock_amd_timeout_s').value)
        self.debug_level = int(self.get_parameter('debug_level').value)
        self.transition_threshold_m = float(self.get_parameter('transition_threshold_m').value)
        self.transition_duration_s = float(self.get_parameter('transition_duration_s').value)

        self.engine = DecisionTreeEngine(confidence_threshold=threshold)

        self.latest_sensor_status: SensorStatusData = SensorStatusData()
        self.latest_depth_error_m: float | None = None
        self.latest_lateral_error_m: float | None = None
        self.latest_odom_lateral_y_m: float | None = None
        self.latest_yaw_rad: float | None = None
        self.latest_magnetic_magnitude: float | None = None
        self.last_goal_signature: str = ''
        self.last_behavior_signature: str = ''
        self.last_bt_status_text: str = ''
        self.last_tree_print_ns: int = 0
        self.last_summary_log_ns: int = 0
        self.last_bt_status_ns: int = 0

        # Mock AMD clock synchronization
        self.mock_amd_timestamp_us: int = 0
        self.mock_amd_last_update_ns: int = self.get_clock().now().nanoseconds
        self.mock_amd_synced: bool = False

        # 平滑过渡状态
        self.prev_setpoint: dict | None = None
        self.transition_start_time_ns: int = 0
        self.transition_start_setpoint: dict | None = None
        self.transition_target_setpoint: dict | None = None

        self.create_subscription(SensorStatus, '/auv/sensors/status', self._on_sensor_status, 10)
        self.create_subscription(String, '/auv/mock_amd/time', self._on_mock_amd_time, 10)
        self.create_subscription(Float32, '/auv/metrics/depth_error', self._on_depth_error, 10)
        self.create_subscription(Float32, '/auv/metrics/lateral_error', self._on_lateral_error, 10)
        self.create_subscription(Odometry, '/auv/state/filtered', self._on_state_filtered, 10)
        self.create_subscription(MagneticField, '/auv/sensors/magnetic', self._on_magnetic, 10)
        self.create_subscription(ArbiterStatus, '/auv/arbiter/status', self._on_arbiter_status, 10)

        self.pub_goal = self.create_publisher(ControlGoal, '/auv/control/goal', 10)
        self.pub_setpoint = self.create_publisher(Setpoint, '/auv/control/setpoint', 10)
        self.pub_bt_status = self.create_publisher(String, '/auv/bt_status', 10)
        self.pub_diagnostic = self.create_publisher(AuvDiagnostic, '/auv/diagnostics', 10)

        self.timer = self.create_timer(0.1, self._on_tick)

        self.get_logger().info('AUV 决策节点已启动。')
        self.get_logger().info(f'置信度阈值: {threshold:.2f}')
        self.get_logger().info(f'行为树状态发布周期: {self.bt_status_publish_period:.1f}s')
        self.get_logger().info(f'行为树打印周期: {self.tree_print_period:.1f}s')
        self.get_logger().info(f'摘要日志周期: {self.summary_log_period:.1f}s')
        self.get_logger().info(f'桥接后端: {self.bridge_backend}')
        self.get_logger().info(f'Debug Level: {self.debug_level} (0:AUTO, 1:HOLD, 2:PATH, 3:FULL)')
        self.get_logger().info(f'平滑过渡阈值: {self.transition_threshold_m:.2f}m')
        self.get_logger().info(f'平滑过渡时长: {self.transition_duration_s:.2f}s')
        self.get_logger().info('订阅: /auv/sensors/status (auv_interfaces/SensorStatus)')
        self.get_logger().info('订阅: /auv/mock_amd/time (std_msgs/String)')
        self.get_logger().info('订阅: /auv/metrics/depth_error (std_msgs/Float32)')
        self.get_logger().info('订阅: /auv/metrics/lateral_error (std_msgs/Float32)')
        self.get_logger().info('订阅: /auv/state/filtered (nav_msgs/Odometry)')
        self.get_logger().info('订阅: /auv/sensors/magnetic (sensor_msgs/MagneticField)')
        self.get_logger().info('发布: /auv/control/goal (auv_interfaces/ControlGoal)')
        self.get_logger().info('发布: /auv/control/setpoint (auv_interfaces/Setpoint)')
        self.get_logger().info('发布: /auv/bt_status (std_msgs/String)')
        self.get_logger().info('发布: /auv/diagnostics (auv_interfaces/AuvDiagnostic)')

    def _on_sensor_status(self, msg: SensorStatus) -> None:
        """接收传感器状态并注入决策引擎的黑板缓存。"""
        status = sensor_msg_to_core(msg)
        # 注入 debug_level（从 ROS2 参数覆盖）
        status.debug_level = self.debug_level
        self.latest_sensor_status = status
        self.engine.set_sensor_status(status)

    def _on_depth_error(self, msg: Float32) -> None:
        """缓存最新深度误差，供调试或控制分支使用。"""
        self.latest_depth_error_m = float(msg.data)

    def _on_lateral_error(self, msg: Float32) -> None:
        """缓存最新横向误差，优先使用显式误差话题。"""
        self.latest_lateral_error_m = float(msg.data)

    def _on_state_filtered(self, msg: Odometry) -> None:
        """从滤波后的位姿里提取横向位移与航向角。"""
        self.latest_odom_lateral_y_m = float(msg.pose.pose.position.y)
        q = msg.pose.pose.orientation
        self.latest_yaw_rad = math.atan2(
            2.0 * (q.w * q.z + q.x * q.y),
            1.0 - 2.0 * (q.y * q.y + q.z * q.z),
        )

    def _on_magnetic(self, msg: MagneticField) -> None:
        """缓存磁场模值，用于调试磁异常和巡检状态变化。"""
        x = float(msg.magnetic_field.x)
        y = float(msg.magnetic_field.y)
        z = float(msg.magnetic_field.z)
        self.latest_magnetic_magnitude = math.sqrt(x * x + y * y + z * z)

    def _on_mock_amd_time(self, msg: String) -> None:
        """同步 Mock AMD 时间戳，供解析式轨迹行为按仿真时间采样。"""
        try:
            data = json.loads(msg.data)
            timestamp_us = int(data.get('timestamp_us', 0))
            if timestamp_us > 0:
                self.mock_amd_timestamp_us = timestamp_us
                self.mock_amd_last_update_ns = self.get_clock().now().nanoseconds
                if not self.mock_amd_synced:
                    self.mock_amd_synced = True
                    self.get_logger().info(f"Mock AMD time synchronized: {timestamp_us} µs")
        except (json.JSONDecodeError, ValueError) as e:
            self.get_logger().warning(f"Failed to parse Mock AMD time: {e}")

    def _on_arbiter_status(self, msg: ArbiterStatus) -> None:
        """处理仲裁器下发的工作指令，并在自动模式下切换调试等级。"""
        # 仅在 AUTO 模式下响应 0xA1/0xA2
        if self.debug_level != 0:
            return

        work_instruction = int(msg.effective_work_instruction)

        if work_instruction == WorkInstruction.HOLD_DEBUG:
            self.get_logger().info('收到 0xA1 HOLD_DEBUG 指令，切换到 debug_level=1')
            self.debug_level = 1
        elif work_instruction == WorkInstruction.ANALYTICAL_PATH_DEBUG:
            self.get_logger().info('收到 0xA2 ANALYTICAL_PATH_DEBUG 指令，切换到 debug_level=2')
            self.debug_level = 2

    def _resolve_lateral_error(self) -> float | None:
        """优先返回显式横向误差，否则回退到滤波位姿中的横向偏移。"""
        if self.latest_lateral_error_m is not None:
            return self.latest_lateral_error_m
        return self.latest_odom_lateral_y_m

    @staticmethod
    def _wrap_angle(angle_rad: float) -> float:
        """将角度归一化到 [-pi, pi]，避免跨周期跳变影响控制误差。"""
        return math.atan2(math.sin(angle_rad), math.cos(angle_rad))

    def _check_position_jump(self, current_setpoint: dict, prev_setpoint: dict | None) -> float:
        """检查目标位姿跳变并返回欧氏距离。

        该方法用于识别行为切换时的目标点突变，避免控制器在高置信度轨迹
        与保持/搜索模式之间直接切换时产生过大的瞬时指令。
        """
        if prev_setpoint is None:
            return 0.0

        dx = float(current_setpoint.get('target_x_m', 0.0)) - float(prev_setpoint.get('target_x_m', 0.0))
        dy = float(current_setpoint.get('target_y_m', 0.0)) - float(prev_setpoint.get('target_y_m', 0.0))
        dz = float(current_setpoint.get('target_depth_m', 0.0)) - float(prev_setpoint.get('target_depth_m', 0.0))

        return math.sqrt(dx * dx + dy * dy + dz * dz)

    def _apply_transition_smoothing(
        self, goal_dict: dict, now_ns: int
    ) -> dict:
        """对切换中的目标点执行平滑插值，降低行为模式切换带来的突变。

        当解析式轨迹、保持姿态或其他模式之间发生切换时，本函数会根据过渡时长
        线性插值位置、深度、速度和航向，避免控制目标出现不连续跳变。
        """
        current_mode = goal_dict.get('mode', '')
        prev_mode = self.prev_setpoint.get('mode', '') if self.prev_setpoint else ''

        # 检查是否需要启动新过渡
        if self.transition_start_time_ns == 0:
            # 检测模式切换（AnalyticalPath → 其他 或 其他 → AnalyticalPath）
            mode_switched = current_mode != prev_mode and 'ANALYTICAL_PATH' in (current_mode, prev_mode)

            if mode_switched:
                jump_distance = self._check_position_jump(goal_dict, self.prev_setpoint)
                if jump_distance > self.transition_threshold_m:
                    self.get_logger().info(
                        f'检测到位置跳变 {jump_distance:.2f}m > {self.transition_threshold_m}m, '
                        f'启动平滑过渡（{prev_mode} → {current_mode}）'
                    )
                    self.transition_start_time_ns = now_ns
                    self.transition_start_setpoint = self.prev_setpoint.copy() if self.prev_setpoint else {}
                    self.transition_target_setpoint = goal_dict.copy()

        # 应用线性插值
        if self.transition_start_time_ns > 0 and self.transition_duration_s > 0:
            elapsed_s = (now_ns - self.transition_start_time_ns) / 1e9
            progress = min(elapsed_s / self.transition_duration_s, 1.0)

            # 线性插值目标位置
            if self.transition_start_setpoint and self.transition_target_setpoint:
                start_x = float(self.transition_start_setpoint.get('target_x_m', 0.0))
                start_y = float(self.transition_start_setpoint.get('target_y_m', 0.0))
                start_z = float(self.transition_start_setpoint.get('target_depth_m', 0.0))
                start_speed = float(self.transition_start_setpoint.get('target_speed_mps', 0.0))
                start_heading = float(self.transition_start_setpoint.get('target_heading_rad', 0.0))

                target_x = float(self.transition_target_setpoint.get('target_x_m', 0.0))
                target_y = float(self.transition_target_setpoint.get('target_y_m', 0.0))
                target_z = float(self.transition_target_setpoint.get('target_depth_m', 0.0))
                target_speed = float(self.transition_target_setpoint.get('target_speed_mps', 0.0))
                target_heading = float(self.transition_target_setpoint.get('target_heading_rad', 0.0))

                # 线性插值
                goal_dict['target_x_m'] = start_x + (target_x - start_x) * progress
                goal_dict['target_y_m'] = start_y + (target_y - start_y) * progress
                goal_dict['target_depth_m'] = start_z + (target_z - start_z) * progress
                goal_dict['target_speed_mps'] = start_speed + (target_speed - start_speed) * progress
                goal_dict['target_heading_rad'] = start_heading + (target_heading - start_heading) * progress

                self.get_logger().debug(
                    f'平滑过渡进度: {progress*100:.1f}% | '
                    f'x={goal_dict["target_x_m"]:.2f}m, y={goal_dict["target_y_m"]:.2f}m, '
                    f'z={goal_dict["target_depth_m"]:.2f}m'
                )

            # 检查过渡完成
            if progress >= 1.0:
                self.get_logger().info('平滑过渡完成')
                self.transition_start_time_ns = 0
                self.transition_start_setpoint = None
                self.transition_target_setpoint = None

        return goal_dict

    def _resolve_target_heading(self, goal_dict: dict) -> float:
        explicit_heading = goal_dict.get('target_heading_rad')
        if explicit_heading is not None:
            return self._wrap_angle(float(explicit_heading))

        heading_target_rad = self.latest_yaw_rad if self.latest_yaw_rad is not None else 0.0

        if bool(goal_dict.get('track_cable', False)):
            lateral_error_m = self._resolve_lateral_error()
            if lateral_error_m is not None and self.guidance_lookahead_distance > 1e-6:
                heading_target_rad += -self.guidance_cross_track_gain * math.atan2(
                    lateral_error_m,
                    self.guidance_lookahead_distance,
                )

        return self._wrap_angle(heading_target_rad)

    def _on_tick(self) -> None:
        now_ns = self.get_clock().now().nanoseconds

        if not self.mock_amd_synced:
            time_since_update_s = (now_ns - self.mock_amd_last_update_ns) / 1e9
            if time_since_update_s <= self.mock_amd_timeout_s:
                self.get_logger().info('Waiting for Mock AMD time synchronization...')
                return

            self.get_logger().warning(
                f'Mock AMD time not received within {self.mock_amd_timeout_s:.2f}s; '
                'falling back to system time'
            )
            self.mock_amd_timestamp_us = int(now_ns / 1000)
            self.mock_amd_last_update_ns = now_ns
            self.mock_amd_synced = True

        # 检查Mock AMD时间是否超时
        time_since_update_s = (now_ns - self.mock_amd_last_update_ns) / 1e9
        if time_since_update_s > self.mock_amd_timeout_s:
            self.get_logger().warning(
                f'Mock AMD time timeout: {time_since_update_s:.2f}s > {self.mock_amd_timeout_s}s, '
                'falling back to system time'
            )
            self.mock_amd_timestamp_us = int(now_ns / 1000)

        self.engine.tick()

        goal_dict = self.engine.get_target_motion_state()
        if goal_dict is None:
            return

        if goal_dict.get('mode') in {'PARALLEL_TRACKING', 'ZIGZAG_SEARCH'}:
            goal_dict.setdefault('track_cable', True)

        goal_dict['target_heading_rad'] = self._resolve_target_heading(goal_dict)
        goal_dict.setdefault('bridge_backend', self.bridge_backend)
        if self.bridge_backend == 'protocol_udp':
            goal_dict.setdefault('control_mode_byte', self.protocol_control_mode_byte)

        # 应用平滑过渡（Phase 5）
        goal_dict = self._apply_transition_smoothing(goal_dict, now_ns)

        # 保存当前 setpoint 用于下次跳变检测
        self.prev_setpoint = goal_dict.copy()

        stamp = self.get_clock().now().to_msg()
        self.pub_goal.publish(motion_goal_dict_to_msg(goal_dict))
        self.pub_setpoint.publish(motion_goal_dict_to_setpoint_msg(goal_dict, stamp=stamp))

        telemetry = build_decision_telemetry_snapshot(
            sensor_status=self.latest_sensor_status,
            goal=goal_dict,
            current_behavior=self.engine.current_behavior_name(),
            active_path=self.engine.active_path(),
            tree_snapshot=self.engine.unicode_tree(),
            depth_error_m=self.latest_depth_error_m,
            lateral_error_m=self._resolve_lateral_error(),
            magnetic_magnitude=self.latest_magnetic_magnitude,
        )
        self.pub_diagnostic.publish(telemetry_snapshot_to_msg(telemetry, stamp=stamp))
        self._publish_bt_status(telemetry.bt_status_markdown)
        self._log_readable_status(telemetry)

    def _publish_bt_status(self, bt_status_markdown: str) -> None:
        now_ns = self.get_clock().now().nanoseconds
        should_publish = (
            bt_status_markdown != self.last_bt_status_text
            or now_ns - self.last_bt_status_ns >= int(self.bt_status_publish_period * 1e9)
        )
        if not should_publish:
            return

        self.last_bt_status_text = bt_status_markdown
        self.last_bt_status_ns = now_ns
        self.pub_bt_status.publish(String(data=bt_status_markdown))

    def _log_readable_status(self, telemetry: DecisionTelemetrySnapshot) -> None:
        now_ns = self.get_clock().now().nanoseconds
        goal_signature = (
            f'{telemetry.mode}|'
            f'{telemetry.target_speed_mps:.3f}|'
            f'{telemetry.target_depth_m:.2f}|'
            f'{telemetry.high_priority}'
        )
        behavior_signature = f'{telemetry.current_behavior}|{telemetry.mode}|{telemetry.active_path}'

        if behavior_signature != self.last_behavior_signature:
            self.last_behavior_signature = behavior_signature
            self.get_logger().info(
                '[行为树切换] '
                f'behavior={telemetry.current_behavior} | '
                f'mode={telemetry.mode} | '
                f'path={telemetry.active_path}'
            )

        should_log_summary = (
            goal_signature != self.last_goal_signature
            or now_ns - self.last_summary_log_ns >= int(self.summary_log_period * 1e9)
        )
        if should_log_summary:
            self.last_goal_signature = goal_signature
            self.last_summary_log_ns = now_ns
            self.get_logger().info(telemetry.summary_line)

        should_print_tree = (
            self.tree_print_period > 0.0
            and now_ns - self.last_tree_print_ns >= int(self.tree_print_period * 1e9)
        )
        if should_print_tree:
            self.last_tree_print_ns = now_ns
            self.get_logger().info(f'行为树快照:\n{telemetry.tree_snapshot}')


def main(args=None) -> None:
    """节点入口。"""
    rclpy.init(args=args)
    node = AUVDecisionNode()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()

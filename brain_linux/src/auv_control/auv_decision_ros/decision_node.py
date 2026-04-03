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

from auv_decision_core.bt_engine import DecisionTreeEngine
from auv_decision_core.models import SensorStatusData
from auv_decision_core.telemetry import DecisionTelemetrySnapshot, build_decision_telemetry_snapshot
from auv_interfaces.msg import AuvDiagnostic, ControlGoal, SensorStatus, Setpoint

from .mappers import (
    motion_goal_dict_to_msg,
    motion_goal_dict_to_setpoint_msg,
    sensor_msg_to_core,
    telemetry_snapshot_to_msg,
)


class AUVDecisionNode(Node):
    """AUV 决策 ROS2 节点。"""

    def __init__(self) -> None:
        super().__init__('auv_decision_node')

        self.declare_parameter('confidence_threshold', 0.7)
        self.declare_parameter('bt_status_publish_period', 0.5)
        self.declare_parameter('tree_print_period', 1.0)
        self.declare_parameter('summary_log_period', 1.0)
        self.declare_parameter('bridge_backend', 'zenoh_json')
        self.declare_parameter('protocol_control_mode_byte', 0xEE)
        self.declare_parameter('guidance_lookahead_distance', 3.5)
        self.declare_parameter('guidance_cross_track_gain', 0.7)

        threshold = float(self.get_parameter('confidence_threshold').value)
        self.bt_status_publish_period = float(self.get_parameter('bt_status_publish_period').value)
        self.tree_print_period = float(self.get_parameter('tree_print_period').value)
        self.summary_log_period = float(self.get_parameter('summary_log_period').value)
        self.bridge_backend = str(self.get_parameter('bridge_backend').value)
        self.protocol_control_mode_byte = int(self.get_parameter('protocol_control_mode_byte').value)
        self.guidance_lookahead_distance = float(self.get_parameter('guidance_lookahead_distance').value)
        self.guidance_cross_track_gain = float(self.get_parameter('guidance_cross_track_gain').value)

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

        self.create_subscription(SensorStatus, '/auv/sensors/status', self._on_sensor_status, 10)
        self.create_subscription(Float32, '/auv/metrics/depth_error', self._on_depth_error, 10)
        self.create_subscription(Float32, '/auv/metrics/lateral_error', self._on_lateral_error, 10)
        self.create_subscription(Odometry, '/auv/state/filtered', self._on_state_filtered, 10)
        self.create_subscription(MagneticField, '/auv/sensors/magnetic', self._on_magnetic, 10)

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
        self.get_logger().info('订阅: /auv/sensors/status (auv_interfaces/SensorStatus)')
        self.get_logger().info('订阅: /auv/metrics/depth_error (std_msgs/Float32)')
        self.get_logger().info('订阅: /auv/metrics/lateral_error (std_msgs/Float32)')
        self.get_logger().info('订阅: /auv/state/filtered (nav_msgs/Odometry)')
        self.get_logger().info('订阅: /auv/sensors/magnetic (sensor_msgs/MagneticField)')
        self.get_logger().info('发布: /auv/control/goal (auv_interfaces/ControlGoal)')
        self.get_logger().info('发布: /auv/control/setpoint (auv_interfaces/Setpoint)')
        self.get_logger().info('发布: /auv/bt_status (std_msgs/String)')
        self.get_logger().info('发布: /auv/diagnostics (auv_interfaces/AuvDiagnostic)')

    def _on_sensor_status(self, msg: SensorStatus) -> None:
        status = sensor_msg_to_core(msg)
        self.latest_sensor_status = status
        self.engine.set_sensor_status(status)

    def _on_depth_error(self, msg: Float32) -> None:
        self.latest_depth_error_m = float(msg.data)

    def _on_lateral_error(self, msg: Float32) -> None:
        self.latest_lateral_error_m = float(msg.data)

    def _on_state_filtered(self, msg: Odometry) -> None:
        self.latest_odom_lateral_y_m = float(msg.pose.pose.position.y)
        q = msg.pose.pose.orientation
        self.latest_yaw_rad = math.atan2(
            2.0 * (q.w * q.z + q.x * q.y),
            1.0 - 2.0 * (q.y * q.y + q.z * q.z),
        )

    def _on_magnetic(self, msg: MagneticField) -> None:
        x = float(msg.magnetic_field.x)
        y = float(msg.magnetic_field.y)
        z = float(msg.magnetic_field.z)
        self.latest_magnetic_magnitude = math.sqrt(x * x + y * y + z * z)

    def _resolve_lateral_error(self) -> float | None:
        if self.latest_lateral_error_m is not None:
            return self.latest_lateral_error_m
        return self.latest_odom_lateral_y_m

    @staticmethod
    def _wrap_angle(angle_rad: float) -> float:
        return math.atan2(math.sin(angle_rad), math.cos(angle_rad))

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

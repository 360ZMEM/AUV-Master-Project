#!/usr/bin/env python3
"""AUV 决策节点（ROS2 包装层）。

设计说明：
- 本节点只负责 ROS2 通信与调度；
- 核心逻辑（行为树、装饰器、阈值判断）全部在 `auv_decision_core` 内；
- 通过 10Hz 定时器驱动行为树 tick，并发布 `ControlGoal`。
"""

from __future__ import annotations

import rclpy
from rclpy.node import Node

from auv_decision_core.bt_engine import DecisionTreeEngine
from auv_decision_core.models import SensorStatusData
from auv_interfaces.msg import ControlGoal, SensorStatus, Setpoint

from .mappers import motion_goal_dict_to_msg, motion_goal_dict_to_setpoint_msg, sensor_msg_to_core


class AUVDecisionNode(Node):
    """AUV 决策 ROS2 节点。"""

    def __init__(self) -> None:
        super().__init__('auv_decision_node')

        # 可配置参数：置信度阈值。后续可直接在 launch 或命令行覆盖。
        self.declare_parameter('confidence_threshold', 0.7)
        self.declare_parameter('tree_print_period', 1.0)
        self.declare_parameter('summary_log_period', 1.0)
        threshold = (
            self.get_parameter('confidence_threshold').get_parameter_value().double_value
        )
        self.tree_print_period = float(
            self.get_parameter('tree_print_period').get_parameter_value().double_value
        )
        self.summary_log_period = float(
            self.get_parameter('summary_log_period').get_parameter_value().double_value
        )

        # 初始化核心决策引擎（纯 Python，不依赖 ROS2）。
        self.engine = DecisionTreeEngine(confidence_threshold=float(threshold))

        # 最近一次传感状态，用于日志摘要展示。
        self.latest_sensor_status: SensorStatusData = SensorStatusData()
        self.last_goal_signature: str = ''
        self.last_tree_print_ns: int = 0
        self.last_summary_log_ns: int = 0

        # 订阅传感状态输入。
        self.sub_sensor = self.create_subscription(
            SensorStatus,
            '/auv/sensors/status',
            self._on_sensor_status,
            10,
        )

        # 发布控制目标输出。
        self.pub_goal = self.create_publisher(ControlGoal, '/auv/control/goal', 10)
        # 发布控制语义输出（推荐新接口）。
        self.pub_setpoint = self.create_publisher(Setpoint, '/auv/control/setpoint', 10)

        # 10Hz 驱动行为树。
        self.timer = self.create_timer(0.1, self._on_tick)

        self.get_logger().info('AUV 决策节点已启动。')
        self.get_logger().info(f'置信度阈值: {threshold:.2f}')
        self.get_logger().info(f'行为树打印周期: {self.tree_print_period:.1f}s')
        self.get_logger().info(f'摘要日志周期: {self.summary_log_period:.1f}s')
        self.get_logger().info('订阅: /auv/sensors/status (auv_interfaces/SensorStatus)')
        self.get_logger().info('发布: /auv/control/goal (auv_interfaces/ControlGoal)')
        self.get_logger().info('发布: /auv/control/setpoint (auv_interfaces/Setpoint)')

    def _on_sensor_status(self, msg: SensorStatus) -> None:
        """订阅回调：将 ROS 消息写入核心黑板输入。"""
        status = sensor_msg_to_core(msg)
        self.latest_sensor_status = status
        self.engine.set_sensor_status(status)

    def _on_tick(self) -> None:
        """10Hz 定时调度：tick 行为树并发布结果。"""
        self.engine.tick()

        goal_dict = self.engine.get_target_motion_state()
        if goal_dict is None:
            return

        goal_msg = motion_goal_dict_to_msg(goal_dict)
        self.pub_goal.publish(goal_msg)

        setpoint_msg = motion_goal_dict_to_setpoint_msg(
            goal_dict,
            stamp=self.get_clock().now().to_msg(),
        )
        self.pub_setpoint.publish(setpoint_msg)

        self._log_readable_status(goal_dict)

    def _log_readable_status(self, goal_dict: dict) -> None:
        """输出更易读的状态摘要，并节流打印树图。

        设计目标：
        - 高频只输出一行摘要，方便快速扫日志；
        - 低频打印一次 unicode_tree，保留结构可视化；
        - 当行为模式发生变化时，立即补充一条摘要，便于定位切换时刻。
        """
        now_ns = self.get_clock().now().nanoseconds
        goal_signature = (
            f"{goal_dict.get('mode', 'IDLE')}|"
            f"{goal_dict.get('target_speed_mps', 0.0):.3f}|"
            f"{goal_dict.get('target_depth_m', 0.0):.2f}|"
            f"{goal_dict.get('high_priority', False)}"
        )

        should_log_summary = (
            goal_signature != self.last_goal_signature
            or now_ns - self.last_summary_log_ns >= int(self.summary_log_period * 1e9)
        )
        if should_log_summary:
            self.last_goal_signature = goal_signature
            self.last_summary_log_ns = now_ns
            self.get_logger().info(self._format_summary_line(goal_dict))

        should_print_tree = now_ns - self.last_tree_print_ns >= int(self.tree_print_period * 1e9)
        if should_print_tree:
            self.last_tree_print_ns = now_ns
            self.get_logger().info('行为树快照:')
            print(self.engine.unicode_tree())

    def _format_summary_line(self, goal_dict: dict) -> str:
        """格式化单行状态摘要，便于终端快速阅读。"""
        status = self.latest_sensor_status
        return (
            '[状态摘要] '
            f"mode={goal_dict.get('mode', 'IDLE')} | "
            f"depth={status.depth_m:.2f}m | speed={status.speed_mps:.2f}m/s | "
            f"confidence={status.confidence:.2f} | leak_level={status.leak_level} | "
            f"battery_low={status.battery_low} | anomaly={status.anomaly_detected} | "
            f"seabed_clearance={status.seabed_clearance_m:.2f}m | "
            f"seabed_warn={status.seabed_proximity_warning} | "
            f"seabed_penetration={status.seabed_penetration_warning} | "
            f"goal_speed={float(goal_dict.get('target_speed_mps', 0.0)):.2f}m/s | "
            f"goal_depth={float(goal_dict.get('target_depth_m', 0.0)):.2f}m | "
            f"priority={bool(goal_dict.get('high_priority', False))}"
        )


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
        # 说明：部分运行场景下 Ctrl+C 会触发系统先行 shutdown，
        # 这里做幂等保护，避免重复 shutdown 抛 RCLError。
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()

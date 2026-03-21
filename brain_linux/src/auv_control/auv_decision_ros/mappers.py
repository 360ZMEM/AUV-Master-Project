"""ROS 消息与 Core 数据模型转换工具。"""

from __future__ import annotations

from builtin_interfaces.msg import Time
from auv_decision_core.models import MotionGoal, SensorStatusData
from auv_interfaces.msg import ControlGoal, SensorStatus, Setpoint


def sensor_msg_to_core(msg: SensorStatus) -> SensorStatusData:
    """将 ROS2 `SensorStatus` 消息转换为核心层 `SensorStatusData`。"""
    return SensorStatusData(
        confidence=float(msg.confidence),
        leak_level=int(msg.leak_level),
        battery_low=bool(msg.battery_low),
        anomaly_detected=bool(msg.anomaly_detected),
        depth_m=float(msg.depth_m),
        speed_mps=float(msg.speed_mps),
    )


def motion_goal_dict_to_msg(goal: dict) -> ControlGoal:
    """将核心层输出 dict 转换为 ROS2 `ControlGoal` 消息。"""
    msg = ControlGoal()
    msg.mode = str(goal.get('mode', 'IDLE'))
    msg.target_depth_m = float(goal.get('target_depth_m', 0.0))
    msg.target_speed_mps = float(goal.get('target_speed_mps', 0.0))
    msg.sine_amplitude = float(goal.get('sine_amplitude', 0.0))
    msg.sine_period_s = float(goal.get('sine_period_s', 0.0))
    msg.high_priority = bool(goal.get('high_priority', False))
    msg.note = str(goal.get('note', ''))
    return msg


def motion_goal_to_msg(goal: MotionGoal) -> ControlGoal:
    """如后续直接传递 `MotionGoal` 对象，可复用该转换函数。"""
    return motion_goal_dict_to_msg(
        {
            'mode': goal.mode,
            'target_depth_m': goal.target_depth_m,
            'target_speed_mps': goal.target_speed_mps,
            'sine_amplitude': goal.sine_amplitude,
            'sine_period_s': goal.sine_period_s,
            'high_priority': goal.high_priority,
            'note': goal.note,
        }
    )


def motion_goal_dict_to_setpoint_msg(goal: dict, stamp: Time | None = None) -> Setpoint:
    """Convert decision goal dict to controller setpoint message."""
    msg = Setpoint()
    if stamp is not None:
        msg.header.stamp = stamp
    msg.mode = str(goal.get('mode', 'IDLE'))
    msg.target_depth_m = float(goal.get('target_depth_m', 0.0))
    msg.target_heading_rad = float(goal.get('target_heading_rad', 0.0))
    msg.target_speed_mps = float(goal.get('target_speed_mps', 0.0))
    msg.track_cable = bool(goal.get('track_cable', True))
    msg.sine_amplitude = float(goal.get('sine_amplitude', 0.0))
    msg.sine_period_s = float(goal.get('sine_period_s', 0.0))
    msg.high_priority = bool(goal.get('high_priority', False))
    msg.note = str(goal.get('note', ''))
    return msg

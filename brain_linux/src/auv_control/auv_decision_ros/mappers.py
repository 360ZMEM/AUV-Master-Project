"""ROS 消息与 Core 数据模型转换工具。

本模块提供 ROS2 消息与决策引擎核心数据结构之间的双向转换。
功能：
  1. 传感器消息（SensorStatus）-> 核心感知数据模型（SensorStatusData）
  2. 控制目标（MotionGoal/dict）-> ROS2 消息（ControlGoal/Setpoint）
  3. 诊断快照（DecisionTelemetrySnapshot）-> 诊断消息（AuvDiagnostic）

设计原则：
  - 消息转换是单向的，无回溯依赖
  - 所有数值字段进行显式类型转换，避免隐式转换错误
  - 缺失字段采用合理的默认值，便于向后兼容
"""

from __future__ import annotations

from builtin_interfaces.msg import Time
from auv_decision_core.models import MotionGoal, SensorStatusData
from auv_decision_core.telemetry import DecisionTelemetrySnapshot
from auv_interfaces.msg import AuvDiagnostic, ControlGoal, SensorStatus, Setpoint


def sensor_msg_to_core(msg: SensorStatus) -> SensorStatusData:
    """将 ROS2 `SensorStatus` 消息转换为核心层 `SensorStatusData`。
    
    Args:
        msg: ROS2 SensorStatus 消息，包含实时传感器数据
        
    Returns:
        SensorStatusData: 核心层感知状态对象，供决策引擎使用
        
    说明：
        通过显式类型转换确保数值精度一致性，会自动处理
        旧版本消息中缺失的字段（如heading_rad、mock_amd_timestamp_us）。
    """
    return SensorStatusData(
        confidence=float(msg.confidence),
        leak_level=int(msg.leak_level),
        battery_low=bool(msg.battery_low),
        total_voltage_v=float(msg.total_voltage_v),
        anomaly_detected=bool(msg.anomaly_detected),
        depth_m=float(msg.depth_m),
        speed_mps=float(msg.speed_mps),
        seabed_depth_m=float(msg.seabed_depth_m),
        seabed_clearance_m=float(msg.seabed_clearance_m),
        seabed_proximity_warning=bool(msg.seabed_proximity_warning),
        seabed_penetration_warning=bool(msg.seabed_penetration_warning),
        heading_rad=float(msg.heading_rad) if hasattr(msg, 'heading_rad') else 0.0,
        mock_amd_timestamp_us=int(msg.mock_amd_timestamp_us) if hasattr(msg, 'mock_amd_timestamp_us') else 0,
        debug_level=int(msg.debug_level) if hasattr(msg, 'debug_level') else 0,
    )


def motion_goal_dict_to_msg(goal: dict) -> ControlGoal:
    """将核心层输出 dict 转换为 ROS2 `ControlGoal` 消息。
    
    Args:
        goal: 核心层输出的目标字典，包含mode、target_depth_m等字段
        
    Returns:
        ControlGoal: ROS2 控制目标消息
        
    说明：
        该函数是决策引擎 -> ROS2 发送者的关键桥梁，处理所有
        可选字段的默认值填充，保证消息完整性。
    """
    msg = ControlGoal()
    msg.mode = str(goal.get('mode', 'IDLE'))
    msg.bridge_backend = str(goal.get('bridge_backend', ''))
    msg.control_mode_byte = int(goal.get('control_mode_byte', 0))
    msg.target_depth_m = float(goal.get('target_depth_m', 0.0))
    msg.target_speed_mps = float(goal.get('target_speed_mps', 0.0))
    msg.sine_amplitude = float(goal.get('sine_amplitude', 0.0))
    msg.sine_period_s = float(goal.get('sine_period_s', 0.0))
    msg.high_priority = bool(goal.get('high_priority', False))
    msg.note = str(goal.get('note', ''))
    return msg


def motion_goal_to_msg(goal: MotionGoal) -> ControlGoal:
    """如后续直接传递 `MotionGoal` 对象，可复用该转换函数。
    
    Args:
        goal: 核心层 MotionGoal 对象
        
    Returns:
        ControlGoal: ROS2 控制目标消息
        
    说明：
        基于motion_goal_dict_to_msg()实现，提供MotionGoal对象的
        直接转换接口，减少中间dict转换步骤。
    """
    return motion_goal_dict_to_msg(
        {
            'mode': goal.mode,
            'bridge_backend': '',
            'control_mode_byte': 0,
            'target_depth_m': goal.target_depth_m,
            'target_speed_mps': goal.target_speed_mps,
            'sine_amplitude': goal.sine_amplitude,
            'sine_period_s': goal.sine_period_s,
            'high_priority': goal.high_priority,
            'note': goal.note,
        }
    )


def motion_goal_dict_to_setpoint_msg(goal: dict, stamp: Time | None = None) -> Setpoint:
    """将决策目标 dict 转换为控制器设定点消息。
    
    Args:
        goal: 决策层输出的目标字典
        stamp: 可选的时间戳（ROS2 Time 对象），若无则不设置
        
    Returns:
        Setpoint: 控制器订阅的设定点消息
        
    说明：
        相比ControlGoal，Setpoint包含更丰富的控制参数
        （target_heading_rad、track_cable、target_x_m/target_y_m）。
    """
    msg = Setpoint()
    if stamp is not None:
        msg.header.stamp = stamp
    msg.mode = str(goal.get('mode', 'IDLE'))
    msg.bridge_backend = str(goal.get('bridge_backend', ''))
    msg.control_mode_byte = int(goal.get('control_mode_byte', 0))
    msg.target_depth_m = float(goal.get('target_depth_m', 0.0))
    msg.target_heading_rad = float(goal.get('target_heading_rad', 0.0))
    msg.target_speed_mps = float(goal.get('target_speed_mps', 0.0))
    msg.track_cable = bool(goal.get('track_cable', True))
    msg.sine_amplitude = float(goal.get('sine_amplitude', 0.0))
    msg.sine_period_s = float(goal.get('sine_period_s', 0.0))
    msg.high_priority = bool(goal.get('high_priority', False))
    msg.note = str(goal.get('note', ''))
    msg.target_x_m = float(goal.get('target_x_m', 0.0))
    msg.target_y_m = float(goal.get('target_y_m', 0.0))
    return msg


def telemetry_snapshot_to_msg(
    snapshot: DecisionTelemetrySnapshot,
    *,
    stamp: Time | None = None,
) -> AuvDiagnostic:
    """将核心层诊断快照转换为 ROS2 `AuvDiagnostic` 消息。
    
    Args:
        snapshot: 核心层决策诊断快照对象
        stamp: 可选的消息时间戳
        
    Returns:
        AuvDiagnostic: ROS2 诊断消息，用于Foxglove可视化与监控
        
    说明：
        该转换用于将决策引擎的实时诊断信息（行为、置信度、错误等）
        发布到ROS2以供可视化与记录。
    """
    msg = AuvDiagnostic()
    if stamp is not None:
        msg.header.stamp = stamp
    msg.current_behavior = snapshot.current_behavior
    msg.active_path = snapshot.active_path
    msg.mode = snapshot.mode
    msg.confidence = float(snapshot.confidence)
    msg.leak_level = int(snapshot.leak_level)
    msg.battery_low = bool(snapshot.battery_low)
    msg.total_voltage_v = float(snapshot.total_voltage_v)
    msg.anomaly_detected = bool(snapshot.anomaly_detected)
    msg.depth_m = float(snapshot.depth_m)
    msg.target_depth_m = float(snapshot.target_depth_m)
    msg.depth_error_m = float(snapshot.depth_error_m)
    msg.speed_mps = float(snapshot.speed_mps)
    msg.target_speed_mps = float(snapshot.target_speed_mps)
    msg.has_lateral_error = bool(snapshot.has_lateral_error)
    msg.lateral_error_m = float(snapshot.lateral_error_m)
    msg.has_magnetic_magnitude = bool(snapshot.has_magnetic_magnitude)
    msg.magnetic_magnitude = float(snapshot.magnetic_magnitude)
    msg.seabed_clearance_m = float(snapshot.seabed_clearance_m)
    msg.seabed_proximity_warning = bool(snapshot.seabed_proximity_warning)
    msg.seabed_penetration_warning = bool(snapshot.seabed_penetration_warning)
    msg.high_priority = bool(snapshot.high_priority)
    msg.note = snapshot.note
    return msg

"""核心领域数据模型。

注意：
- 本文件属于洋葱架构的 Core 层；
- 仅使用 Python 标准库与 dataclass；
- 禁止引入 `rclpy`、ROS 消息类型等基础设施依赖。
"""

from dataclasses import dataclass


@dataclass
class SensorStatusData:
    """行为树输入状态的核心数据结构。

    该数据类承载决策树在每次 tick 时需要读取的所有传感与运行时上下文，
    目标是把 ROS2、仿真和协议层的输入统一收敛成一个稳定的 Python 对象。

    字段用途：
        confidence: 目标跟踪/电缆识别置信度，范围 [0.0, 1.0]。
        leak_level: 漏水等级编码（0:无漏水,1:内部,2:外部,3:内外同时）。
        battery_low: 是否低电。
        total_voltage_v: 当前总电压（V）。
        anomaly_detected: 是否检测到异常（用于装饰器降速语义）。
        depth_m: 当前深度（米）。
        speed_mps: 当前速度（米/秒）。
        seabed_depth_m: 海底参考深度（米）。
        seabed_clearance_m: 到海底的剩余净空（米）。
        seabed_proximity_warning: 是否接近海底（用于保守减速）。
        seabed_penetration_warning: 是否已穿底（用于紧急上浮）。
        heading_rad: 当前航向（弧度，NED 坐标系）。
        mock_amd_timestamp_us: Mock AMD 时钟时间戳（Unix 微秒）。
        debug_level: 算法透明度级别（0:AUTO, 1:HOLD, 2:PATH, 3:FULL）。
        execution_fault_word: 执行脑上报的原始故障字，仅用于诊断追溯。
        communication_link_ok: 执行脑与上层通信是否允许继续自治。
        velocity_aiding_valid: 执行脑报告的速度辅助信息是否有效。
    """

    confidence: float = 0.5
    leak_level: int = 0
    battery_low: bool = False
    total_voltage_v: float = 48.0
    anomaly_detected: bool = False
    depth_m: float = 0.0
    speed_mps: float = 0.0
    seabed_depth_m: float = 15.0
    seabed_clearance_m: float = 15.0
    seabed_proximity_warning: bool = False
    seabed_penetration_warning: bool = False
    heading_rad: float = 0.0
    mock_amd_timestamp_us: int = 0
    debug_level: int = 0
    auto_state: str = 'LOCKED'
    execution_fault_word: int = 0
    communication_link_ok: bool = True
    velocity_aiding_valid: bool = True

    def is_leaking(self) -> bool:
        """判断当前是否存在漏水风险。"""
        return self.leak_level > 0

    def is_seabed_risky(self) -> bool:
        """判断当前是否存在近底或穿底风险。"""
        return self.seabed_proximity_warning or self.seabed_penetration_warning

    def is_seabed_penetrated(self) -> bool:
        """判断当前是否已经穿底。"""
        return self.seabed_penetration_warning

    def autonomy_link_available(self) -> bool:
        """判断执行脑通信状态是否允许任务层继续自治。"""
        return self.communication_link_ok

    def localization_aiding_available(self) -> bool:
        """判断速度辅助是否可用于精准巡检分支。"""
        return self.velocity_aiding_valid


@dataclass
class MotionGoal:
    """行为树输出目标的统一表示。

    该数据类描述行为树最终想要驱动 AUV 达成的任务意图，供 ROS2 控制层、
    调试可视化和协议转换层共同消费。

    字段用途：
        mode: 当前目标行为模式。
        target_depth_m: 目标深度（米）。
        target_speed_mps: 目标速度（米/秒）。
        sine_amplitude: 正弦扰动幅值（用于并行巡检等轨迹控制）。
        sine_period_s: 正弦扰动周期（秒）。
        high_priority: 是否高优先级（紧急动作置 True）。
        note: 备注说明（便于调试与可视化）。
        target_heading_rad: 目标航向（弧度，用于解析轨迹模式）。
        target_x_m: 目标 x 坐标（米，用于解析轨迹模式）。
        target_y_m: 目标 y 坐标（米，用于解析轨迹模式）。
    """

    mode: str = 'IDLE'
    target_depth_m: float = 0.0
    target_speed_mps: float = 0.0
    sine_amplitude: float = 0.0
    sine_period_s: float = 0.0
    high_priority: bool = False
    note: str = ''
    target_heading_rad: float = 0.0
    target_x_m: float = 0.0
    target_y_m: float = 0.0

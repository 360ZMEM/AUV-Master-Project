"""核心领域数据模型。

注意：
- 本文件属于洋葱架构的 Core 层；
- 仅使用 Python 标准库与 dataclass；
- 禁止引入 `rclpy`、ROS 消息类型等基础设施依赖。
"""

from dataclasses import dataclass


@dataclass
class SensorStatusData:
    """行为树输入状态。

    Attributes:
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

    def is_leaking(self) -> bool:
        """是否漏水（任意漏水等级 > 0 即认为漏水）。"""
        return self.leak_level > 0

    def is_seabed_risky(self) -> bool:
        """是否存在海底接近或穿底风险。"""
        return self.seabed_proximity_warning or self.seabed_penetration_warning

    def is_seabed_penetrated(self) -> bool:
        """是否已穿过海底。"""
        return self.seabed_penetration_warning


@dataclass
class MotionGoal:
    """行为树输出目标。

    Attributes:
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

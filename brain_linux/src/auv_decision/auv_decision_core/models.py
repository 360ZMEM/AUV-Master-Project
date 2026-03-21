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
        anomaly_detected: 是否检测到异常（用于装饰器降速语义）。
        depth_m: 当前深度（米）。
        speed_mps: 当前速度（米/秒）。
    """

    confidence: float = 0.5
    leak_level: int = 0
    battery_low: bool = False
    anomaly_detected: bool = False
    depth_m: float = 0.0
    speed_mps: float = 0.0

    def is_leaking(self) -> bool:
        """是否漏水（任意漏水等级 > 0 即认为漏水）。"""
        return self.leak_level > 0


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
    """

    mode: str = 'IDLE'
    target_depth_m: float = 0.0
    target_speed_mps: float = 0.0
    sine_amplitude: float = 0.0
    sine_period_s: float = 0.0
    high_priority: bool = False
    note: str = ''

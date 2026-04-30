"""控制器基类：定义统一的控制器接口和输出结构。

本模块提供：
  1. ControlOutput 数据类：统一的控制器输出结构
  2. BaseController 抽象基类：所有控制器必须实现的接口

设计原则：
  - 所有控制器（PID、MPC 等）必须继承 BaseController
  - compute 方法接受相同的状态和设定点格式
  - 输出统一的 ControlOutput 结构，便于下游消费
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ControlOutput:
    """控制器统一输出结构。

    Attributes:
        thrust_percent: 推力百分比，范围 [-100, 100]
        right_fin_deg: 右舵角度（度），None 表示透传/不干预
        top_fin_deg: 上舵角度（度）
        left_fin_deg: 左舵角度（度）
        bottom_fin_deg: 下舵角度（度）
        guidance_heading: 引导航向（弧度），None 表示透传
        guidance_depth: 引导深度（米），None 表示透传
        debug: 调试信息字典，用于可视化和日志
    """

    thrust_percent: float = 0.0
    right_fin_deg: float | None = None
    top_fin_deg: float | None = None
    left_fin_deg: float | None = None
    bottom_fin_deg: float | None = None
    guidance_heading: float | None = None
    guidance_depth: float | None = None
    debug: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """将输出转换为字典格式，便于序列化和调试。

        Returns:
            dict: 包含所有输出字段的字典
        """
        return {
            "thrust_percent": self.thrust_percent,
            "right_fin_deg": self.right_fin_deg,
            "top_fin_deg": self.top_fin_deg,
            "left_fin_deg": self.left_fin_deg,
            "bottom_fin_deg": self.bottom_fin_deg,
            "guidance_heading": self.guidance_heading,
            "guidance_depth": self.guidance_depth,
            "debug": self.debug,
        }


class BaseController(ABC):
    """控制器抽象基类。

    所有控制器实现（PID、MPC 等）必须继承此类并实现 compute 方法。
    """

    @abstractmethod
    def compute(self, state: dict, setpoint: dict) -> ControlOutput:
        """计算控制指令。

        Args:
            state: 当前状态字典，包含：
                - x, y, z: 位置（米）
                - u, v, w: 体轴速度（m/s）
                - roll, pitch, yaw: 欧拉角（弧度）
                - p, q, r: 体轴角速度（rad/s）
                - depth: 当前深度（米）
            setpoint: 目标设定点字典，包含：
                - target_depth_m: 目标深度（米）
                - target_heading_rad: 目标航向（弧度）
                - target_speed_mps: 目标速度（m/s）
                - target_x_m: 目标 X 位置（米，可选）
                - target_y_m: 目标 Y 位置（米，可选）
                - dt: 控制周期（秒）

        Returns:
            ControlOutput: 控制器输出指令

        Note:
            - 对于 PID 控制器，速度环闭环计算推力，舵角透传
            - 对于 MPC 控制器，所有通道均由优化器计算
        """
        ...

    def reset(self) -> None:
        """重置控制器内部状态（如积分项、历史状态等）。

        子类可根据需要重写此方法。默认实现为空。
        """
        pass

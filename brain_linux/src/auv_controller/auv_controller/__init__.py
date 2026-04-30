"""auv_controller 包初始化。

导出混合控制引擎的核心类：
  - BaseController: 控制器抽象基类
  - PIDController: PID 控制器实现
  - MPCController: MPC 控制器占位类
  - ControlOutput: 统一输出结构
"""

from .base_controller import BaseController, ControlOutput
from .pid_controller import PIDController
from .mpc_controller import MPCController

__all__ = [
    'BaseController',
    'ControlOutput',
    'PIDController',
    'MPCController',
]

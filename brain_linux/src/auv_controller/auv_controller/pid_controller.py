"""PID 控制器封装：将现有 AUVPIDController 包装为 BaseController 接口。

本模块提供：
  1. PIDController: 继承 BaseController，包装 algorithm/auv_pid_controller.py
  2. 混合控制逻辑：
     - 纵向（Surge）：使用 AUVPIDController 的速度环闭环
     - 横/垂向：直接透传 guidance（不干预 AMD 本地闭环）

设计说明：
  - 现有的 AUVPIDController 输出五通道舵面/推力指令
  - 混合控制模式下，只取其 thrust 输出作为推力指令
  - 舵角输出标记为 None，确保下游知道是"透传"模式
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from .base_controller import BaseController, ControlOutput

# 动态加载 AUVPIDController
def _resolve_project_root() -> Path:
    cur = Path(__file__).resolve()
    for parent in cur.parents:
        if (parent / 'algorithm').exists():
            return parent
    raise RuntimeError('无法找到包含 algorithm 目录的项目根目录')

import importlib.util

_ALGO_DIR = _resolve_project_root() / 'algorithm'

def _load_auv_pid():
    module_path = _ALGO_DIR / 'auv_pid_controller.py'
    spec = importlib.util.spec_from_file_location('auv_algorithm_pid', str(module_path))
    if spec is None or spec.loader is None:
        raise RuntimeError(f'无法加载 PID 模块: {module_path}')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.AUVPIDController

AUVPIDController = _load_auv_pid()


class PIDController(BaseController):
    """PID 控制器实现，包装现有的 AUVPIDController。

    混合控制策略：
    - 纵向推力：由 AUVPIDController 的速度环计算
    - 舵角输出：全部为 None（透传），由 AMD 本地 PID 闭环处理

    这种设计确保 Jetson 只负责航速维持，不干扰 AMD 的舵面控制。
    """

    def __init__(self, ctrl_cfg: dict, lim_cfg: dict, mapper_cfg: dict | None = None) -> None:
        self._pid = AUVPIDController(ctrl_cfg, lim_cfg)
        self._mapper_cfg = mapper_cfg or {}

    def compute(self, state: dict, setpoint: dict) -> ControlOutput:
        target = {
            'dt': float(setpoint.get('dt', 0.05)),
            'target_depth': float(state.get('depth', 0.0)),
            'target_yaw': float(state.get('yaw', 0.0)),
            'target_u': float(setpoint.get('target_speed_mps', 0.0)),
        }

        pid_cmd, debug = self._pid.compute(state, target)

        thrust_percent = float(pid_cmd[4])

        return ControlOutput(
            thrust_percent=thrust_percent,
            right_fin_deg=None,
            top_fin_deg=None,
            left_fin_deg=None,
            bottom_fin_deg=None,
            guidance_heading=setpoint.get('target_heading_rad'),
            guidance_depth=setpoint.get('target_depth_m'),
            debug={
                **debug,
                'controller_type': 'PID',
                'mode': 'hybrid',
                'fin_passthrough': True,
            },
        )

    def reset(self) -> None:
        for pid_axis in [self._pid.depth_pid, self._pid.pitch_pid,
                         self._pid.yaw_pid, self._pid.speed_pid]:
            pid_axis.reset_integral()
        self._pid.prev_target_pitch = 0.0

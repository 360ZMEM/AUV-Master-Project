"""MPC 控制器封装：基于 CasADi 的模型预测控制（Guidance-level）。

本模块将 algorithm/auv_mpc_controller.py 中的核心 MPC 求解器封装为
BaseController 接口，提供：
  - Guidance-level 输出：guidance_heading + guidance_depth + thrust_percent
  - 不输出舵角（交由 AMD 侧 PID 处理）
  - 置信度自适应权重（盲跟模式）
  - 热启动加速求解
  - 失效降级信号（抛异常供节点捕获）

设计原则：
  - MPC 与 PID 控制器平级，输出格式统一为 ControlOutput
  - 内部使用 NED 坐标系
  - 4-DOF 预测模型 (Surge-Heave-Pitch-Yaw)
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

from .base_controller import BaseController, ControlOutput


def _resolve_project_root() -> Path:
    cur = Path(__file__).resolve()
    for parent in cur.parents:
        if (parent / "algorithm").exists():
            return parent
    raise RuntimeError("无法找到包含 algorithm 目录的项目根目录")


_ALGO_DIR = _resolve_project_root() / "algorithm"
_SYS_DIR = _resolve_project_root() / "sim_holoocean" / "interfaces"


def _load_mpc_algorithm():
    module_path = _ALGO_DIR / "auv_mpc_controller.py"
    spec = __import__("importlib.util").util.spec_from_file_location(
        "auv_algorithm_mpc", str(module_path)
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载 MPC 模块: {module_path}")
    mod = __import__("importlib.util").util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.AUVMPCOptimizer, mod.AUVKinematicsModel


AUVMPCOptimizer, AUVKinematicsModel = _load_mpc_algorithm()


def _load_guidance_module():
    module_path = _ALGO_DIR / "guidance.py"
    spec = __import__("importlib.util").util.spec_from_file_location(
        "auv_algorithm_guidance", str(module_path)
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载 guidance 模块: {module_path}")
    mod = __import__("importlib.util").util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_guidance_mod = _load_guidance_module()


def _wrap_angle(angle: float) -> float:
    return (angle + np.pi) % (2 * np.pi) - np.pi


class MPCController(BaseController):
    """Guidance-level MPC 控制器。

    基于 CasADi + IPOPT 的模型预测控制，输出引导航向、引导深度和推力百分比。
    不直接输出舵角，舵角交由 AMD 侧底层 PID 闭环处理。

    输入状态量 (state dict):
        x, y, z     : NED 位置 (m)
        u, v, w     : 体轴速度 (m/s)
        roll, pitch, yaw : 欧拉角 (rad)
        p, q, r     : 体轴角速度 (rad/s)
        depth       : 当前深度 (m)

    设定点 (setpoint dict):
        target_depth_m     : 目标深度 (m)
        target_heading_rad : 目标航向 (rad)
        target_speed_mps   : 目标速度 (m/s)
        dt                 : 控制周期 (s)
        confidence         : 传感器置信度 [0, 1]（可选，默认 1.0）

    输出 (ControlOutput):
        guidance_heading : 最优引导航向 (rad)
        guidance_depth   : 最优引导深度 (m)
        thrust_percent   : 最优推力百分比 (%)
        fin_deg          : 全部为 None（透传，不干预 AMD）
    """

    def __init__(
        self,
        ctrl_cfg: dict,
        lim_cfg: dict,
        mapper_cfg: dict | None = None,
    ) -> None:
        mpc_cfg = ctrl_cfg.get("mpc", {})
        model_cfg = ctrl_cfg.get("mpc_model", {})
        weights_cfg = ctrl_cfg.get("mpc_weights", {})
        constraints_cfg = ctrl_cfg.get("mpc_constraints", {})

        self._N = int(mpc_cfg.get("prediction_horizon", 20))
        self._dt = float(mpc_cfg.get("dt", 0.1))
        self._max_solve_time_ms = float(mpc_cfg.get("max_solve_time_ms", 50.0))

        self._kinematics = AUVKinematicsModel(model_cfg)
        self._optimizer = AUVMPCOptimizer(
            self._kinematics,
            N=self._N,
            dt=self._dt,
            weights=weights_cfg,
            constraints=constraints_cfg,
        )

        self._prev_U: np.ndarray | None = None
        self._solve_time_ms: float = 0.0
        self._solver_status: str = "NOT_RUN"
        self._last_cost: float = 0.0
        self._confidence: float = 1.0

        self._use_los_reference: bool = mpc_cfg.get("use_los_reference", False)
        self._los_lookahead_distance: float = mpc_cfg.get("los_lookahead_distance", 3.0)
        self._last_los_index: int = 0

    def compute(self, state: dict, setpoint: dict) -> ControlOutput:
        """求解 MPC 并返回引导指令。

        Args:
            state: 当前状态（来自 ES-EKF）
            setpoint: 目标设定点，包含置信度

        Returns:
            ControlOutput 包含 guidance_heading, guidance_depth, thrust_percent

        Raises:
            RuntimeError: 如果 MPC 求解失败，调用方应捕获并回退到 PID
        """
        t_start = time.time()

        x0 = np.array(
            [
                float(state["x"]),
                float(state["y"]),
                float(state["z"]),
                float(state["yaw"]),
                float(state["u"]),
                float(state["w"]),
            ],
            dtype=np.float64,
        )

        target_heading = float(setpoint.get("target_heading_rad", state["yaw"]))
        target_depth = float(setpoint.get("target_depth_m", 0.0))
        target_speed = float(setpoint.get("target_speed_mps", 1.0))
        confidence = float(setpoint.get("confidence", 1.0))
        cable_points = setpoint.get("cable_points", None)
        self._confidence = confidence

        ref_traj = self._build_reference_trajectory(
            x0, target_heading, target_depth, target_speed,
            cable_points=cable_points,
        )

        try:
            result = self._optimizer.solve(
                x0=x0,
                ref_trajectory=ref_traj,
                confidence=confidence,
                warm_start_U=self._prev_U,
            )
        except RuntimeError:
            raise

        self._solve_time_ms = result["solve_time_ms"]
        self._solver_status = result["solver_status"]
        self._last_cost = result["cost_value"]
        self._prev_U = result["U_opt"].copy()

        U_first = result["U_opt"][:, 0]
        psi_opt = float(U_first[0])
        z_opt = float(U_first[1])
        T_opt = float(U_first[2])

        elapsed = (time.time() - t_start) * 1000.0

        X_opt = result["X_opt"]
        pred_trajectory = []
        for k in range(self._N + 1):
            pred_trajectory.append(
                {
                    "x": float(X_opt[0, k]),
                    "y": float(X_opt[1, k]),
                    "z": float(X_opt[2, k]),
                    "psi": float(X_opt[3, k]),
                }
            )

        ref_traj_list = []
        for k in range(self._N + 1):
            ref_traj_list.append(
                {
                    "x": float(ref_traj[0, k]),
                    "y": float(ref_traj[1, k]),
                    "z": float(ref_traj[2, k]),
                }
            )

        return ControlOutput(
            thrust_percent=float(np.clip(T_opt, 0.0, 100.0)),
            right_fin_deg=None,
            top_fin_deg=None,
            left_fin_deg=None,
            bottom_fin_deg=None,
            guidance_heading=float(psi_opt),
            guidance_depth=float(z_opt),
            debug={
                "controller_type": "MPC",
                "solver_status": self._solver_status,
                "solve_time_ms": round(self._solve_time_ms, 2),
                "total_compute_ms": round(elapsed, 2),
                "cost_value": round(self._last_cost, 4),
                "confidence": round(confidence, 3),
                "prediction_horizon": self._N,
                "dt": self._dt,
                "optimal_control": {
                    "psi_cmd_rad": round(psi_opt, 4),
                    "z_cmd_m": round(z_opt, 2),
                    "T_cmd_pct": round(T_opt, 2),
                },
                "pred_trajectory": pred_trajectory,
                "ref_trajectory": ref_traj_list,
            },
        )

    def _build_reference_trajectory(
        self,
        x0: np.ndarray,
        target_heading: float,
        target_depth: float,
        target_speed: float,
        cable_points: np.ndarray | None = None,
    ) -> np.ndarray:
        """生成未来 N+1 步的参考轨迹。

        两种模式:
          1. LOS 动态模式: 基于电缆点序列 + LOS 前视距离生成参考轨迹
          2. 恒定航向模式: 使用恒定航向 + 恒定深度的前向推进策略

        Args:
            x0: 当前状态 [x, y, z, psi, u, w]
            target_heading: 目标航向 (rad)
            target_depth: 目标深度 (m)
            target_speed: 目标速度 (m/s)
            cable_points: 电缆参考点序列 (N_pts, 3) 或 None

        Returns:
            np.ndarray: 参考轨迹 (6, N+1)
        """
        if self._use_los_reference and cable_points is not None and len(cable_points) > 1:
            return self._build_los_reference_trajectory(
                x0, target_speed, cable_points,
            )
        return self._build_constant_reference_trajectory(
            x0, target_heading, target_depth, target_speed,
        )

    def _build_los_reference_trajectory(
        self,
        x0: np.ndarray,
        target_speed: float,
        cable_points: np.ndarray,
    ) -> np.ndarray:
        """基于 LOS 导引生成动态参考轨迹。

        算法:
          1. 使用 find_nearest_index 找到当前 AUV 位置最近的电缆点
          2. 使用 compute_los_target 计算前视目标点
          3. 沿电缆点序列向前采样 N+1 个参考点

        Args:
            x0: 当前状态 [x, y, z, psi, u, w]
            target_speed: 目标速度 (m/s)
            cable_points: 电缆参考点序列 (N_pts, 3)

        Returns:
            np.ndarray: 参考轨迹 (6, N+1)
        """
        N = self._N
        ref = np.zeros((6, N + 1), dtype=np.float64)

        points_xy = cable_points[:, :2]
        current_xy = x0[:2]

        self._last_los_index = _guidance_mod.find_nearest_index(
            points_xy, current_xy, self._last_los_index, search_window=50,
        )

        los_lookahead = self._los_lookahead_distance

        for k in range(N + 1):
            los_point, next_index = _guidance_mod.compute_los_target(
                cable_points, self._last_los_index, los_lookahead,
            )
            self._last_los_index = next_index

            ref[0, k] = float(los_point[0])
            ref[1, k] = float(los_point[1])
            ref[2, k] = float(los_point[2]) if len(los_point) > 2 else float(x0[2])

            if next_index < len(cable_points) - 1:
                next_pt = cable_points[next_index + 1]
                ref[3, k] = float(np.arctan2(
                    next_pt[1] - los_point[1],
                    next_pt[0] - los_point[0],
                ))
            else:
                ref[3, k] = float(x0[3])

            ref[4, k] = float(target_speed)
            ref[5, k] = 0.0

            los_lookahead += target_speed * self._dt

        return ref

    def _build_constant_reference_trajectory(
        self,
        x0: np.ndarray,
        target_heading: float,
        target_depth: float,
        target_speed: float,
    ) -> np.ndarray:
        """生成恒定航向 + 恒定深度的参考轨迹。

        Args:
            x0: 当前状态 [x, y, z, psi, u, w]
            target_heading: 目标航向 (rad)
            target_depth: 目标深度 (m)
            target_speed: 目标速度 (m/s)

        Returns:
            np.ndarray: 参考轨迹 (6, N+1)
        """
        N = self._N
        dt = self._dt
        ref = np.zeros((6, N + 1), dtype=np.float64)

        for k in range(N + 1):
            t_k = k * dt
            ref[0, k] = x0[0] + target_speed * np.cos(target_heading) * t_k
            ref[1, k] = x0[1] + target_speed * np.sin(target_heading) * t_k
            ref[2, k] = float(target_depth)
            ref[3, k] = float(target_heading)
            ref[4, k] = float(target_speed)
            ref[5, k] = 0.0

        return ref

    def reset(self) -> None:
        """重置 MPC 内部状态（热启动缓存清零）。"""
        self._prev_U = None
        self._solve_time_ms = 0.0
        self._solver_status = "NOT_RUN"
        self._last_cost = 0.0

    @property
    def solve_time_ms(self) -> float:
        return self._solve_time_ms

    @property
    def solver_status(self) -> str:
        return self._solver_status

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

import json
import os
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

_SOLVER_DIAGNOSTIC_KEYS = (
    "solver_iterations",
    "solver_wall_time_current_ms",
    "control_period_ms",
    "control_period_blocked",
    "warm_start_provided",
    "warm_start_used",
    "warm_start_control_shift_rms",
    "initial_guess_source",
    "initial_guess_projection_rms",
    "state_initial_jump_l2",
    "constraint_slack_enabled",
    "slack_max",
    "slack_l1",
    "slack_l2",
    "slack_active_count",
    "constraint_count",
    "initial_constraint_violation_max",
    "initial_constraint_violation_l2",
    "initial_active_constraint_count",
    "final_constraint_violation_max",
    "final_constraint_violation_l2",
    "final_active_constraint_count",
)


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
        mpc_cfg = dict(ctrl_cfg.get("mpc", {}))
        model_cfg = ctrl_cfg.get("mpc_model", {})
        weights_cfg = dict(ctrl_cfg.get("mpc_weights", {}))
        constraints_cfg = dict(ctrl_cfg.get("mpc_constraints", {}))
        solver_max_iter = int(mpc_cfg.get("max_iter", 100))

        # E3 — sweep harness 通过 AUV_MPC_MODE 注入消融模式 (ua/baseline)
        env_mpc_mode = os.environ.get("AUV_MPC_MODE", "").strip().lower()
        if env_mpc_mode in ("ua", "baseline"):
            weights_cfg["mpc_mode"] = env_mpc_mode

        # E6 — sweep harness 通过 AUV_MPC_PARAM_OVERRIDES 注入参数网格 (论文 §5.5.1)
        overrides_json = os.environ.get("AUV_MPC_PARAM_OVERRIDES", "").strip()
        if overrides_json:
            try:
                overrides = json.loads(overrides_json)
                if isinstance(overrides, dict):
                    solver_max_iter = int(
                        overrides.pop("max_iter", solver_max_iter)
                    )
                    for key in ("warm_start",):
                        if key in overrides:
                            mpc_cfg[key] = overrides.pop(key)
                    constraint_override_keys = {
                        "enable_rate_constraints",
                        "enable_band_constraints",
                        "enable_constraint_slack",
                        "constraint_slack_weight",
                        "max_speed_slack_ms",
                        "max_depth_rate_slack_m",
                        "max_heading_rate_slack_rad",
                        "max_depth_band_slack_m",
                        "max_heading_band_slack_rad",
                    }
                    for key in constraint_override_keys:
                        if key in overrides:
                            constraints_cfg[key] = overrides.pop(key)
                    weights_cfg.update(overrides)
            except Exception:
                pass

        self._N = int(mpc_cfg.get("prediction_horizon", 20))
        self._dt = float(mpc_cfg.get("dt", 0.1))
        self._max_solve_time_ms = float(mpc_cfg.get("max_solve_time_ms", 50.0))
        self._fail_safe_fallback = bool(mpc_cfg.get("fail_safe_fallback", True))
        self._warm_start_enabled = bool(mpc_cfg.get("warm_start", True))
        self._fallback_thrust_percent = float(constraints_cfg.get("min_thrust_percent", 15.0))

        # WP-C C2: 输出级深度积分补偿（抗稳态漂移），抗饱和 clamp。
        self._ki_z = float(mpc_cfg.get("ki_z", 0.0))
        self._integral_clamp_m = float(mpc_cfg.get("z_integral_clamp_m", 2.0))
        self._z_integral = 0.0
        self._min_z_cmd = float(constraints_cfg.get("min_z_cmd_m", 0.0))
        self._max_z_cmd = float(constraints_cfg.get("max_z_cmd_m", 50.0))

        self._kinematics = AUVKinematicsModel(model_cfg)
        self._optimizer = AUVMPCOptimizer(
            self._kinematics,
            N=self._N,
            dt=self._dt,
            weights=weights_cfg,
            constraints=constraints_cfg,
            max_iter=solver_max_iter,
        )

        self._prev_U: np.ndarray | None = None
        self._previous_applied_control: np.ndarray | None = None
        self._solve_time_ms: float = 0.0
        self._solve_time_source: str = "not_run"
        self._solver_status: str = "NOT_RUN"
        self._last_cost: float = 0.0
        self._confidence: float = 1.0
        self._last_output: ControlOutput | None = None

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
        t_start = time.perf_counter()

        # MPC 内部统一使用 NED 深度：z 正向下、w 正向下。
        # 新版 auv_controller_node 已传入 state["z"] = state["depth"] = 正深度；
        # 这里保留 fallback，防止其他调用方仍只提供 depth。
        depth_ned = float(state.get("depth", state.get("z", 0.0)))
        w_ned = float(state.get("w", 0.0))

        x0 = np.array(
            [
                float(state["x"]),
                float(state["y"]),
                depth_ned,
                float(state["yaw"]),
                float(state["u"]),
                w_ned,
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
        previous_control = (
            self._previous_applied_control.copy()
            if self._previous_applied_control is not None
            else None
        )
        previous_control_available = previous_control is not None

        try:
            result = self._optimizer.solve(
                x0=x0,
                ref_trajectory=ref_traj,
                confidence=confidence,
                warm_start_U=self._prev_U if self._warm_start_enabled else None,
                delta_u_penalty_scale=float(
                    setpoint.get("delta_u_penalty_scale", 1.0)
                ),
                previous_control=previous_control,
            )
        except RuntimeError as exc:
            if not self._fail_safe_fallback:
                raise
            cycle_diagnostics = dict(getattr(exc, "diagnostics", {}))
            elapsed_ms = (time.perf_counter() - t_start) * 1000.0
            solver_wall_ms = float(
                cycle_diagnostics.get("solver_wall_time_current_ms", elapsed_ms)
            )
            control_period_ms = (
                max(float(setpoint.get("dt", self._dt)), 1e-6) * 1000.0
            )
            cycle_diagnostics["control_period_ms"] = control_period_ms
            cycle_diagnostics["control_period_blocked"] = (
                solver_wall_ms > control_period_ms
            )
            self._solve_time_ms = solver_wall_ms
            self._solve_time_source = str(
                cycle_diagnostics.get(
                    "solve_time_source", "controller_wall_perf_counter_failed"
                )
            )
            # WP-C C2: 求解失败时重置积分器，避免 windup。
            self._z_integral = 0.0
            fallback_type = (
                "last_output" if self._last_output is not None else "setpoint"
            )
            self._solver_status = (
                "FALLBACK_LAST_OUTPUT"
                if self._last_output is not None
                else "FALLBACK_SETPOINT"
            )
            debug = {
                "controller_type": "MPC",
                "solver_status": self._solver_status,
                "solver_return_status": cycle_diagnostics.get(
                    "solver_status", "FAILED"
                ),
                "fallback_reason": str(exc),
                "fallback_type": fallback_type,
                "solve_time_ms": round(solver_wall_ms, 2),
                "solve_time_source": self._solve_time_source,
                "solver_wall_time_current_ms": round(solver_wall_ms, 2),
                "total_compute_ms": round(elapsed_ms, 2),
                "confidence": round(confidence, 3),
                "confidence_policy": self._optimizer.confidence_policy,
                "delta_u_penalty_scale": float(
                    setpoint.get("delta_u_penalty_scale", 1.0)
                ),
                "delta_u_previous_control_available": (
                    previous_control_available
                ),
                "prediction_horizon": self._N,
                "dt": self._dt,
                "warm_start_enabled": self._warm_start_enabled,
            }
            debug.update(
                {
                    key: cycle_diagnostics[key]
                    for key in _SOLVER_DIAGNOSTIC_KEYS
                    if key in cycle_diagnostics
                }
            )
            if self._last_output is not None:
                self._previous_applied_control = np.array(
                    [
                        self._last_output.guidance_heading,
                        self._last_output.guidance_depth,
                        self._last_output.thrust_percent,
                    ],
                    dtype=float,
                )
                debug["last_successful_solver_status"] = self._last_output.debug.get(
                    "solver_status", ""
                )
                return ControlOutput(
                    thrust_percent=self._last_output.thrust_percent,
                    right_fin_deg=self._last_output.right_fin_deg,
                    top_fin_deg=self._last_output.top_fin_deg,
                    left_fin_deg=self._last_output.left_fin_deg,
                    bottom_fin_deg=self._last_output.bottom_fin_deg,
                    guidance_heading=self._last_output.guidance_heading,
                    guidance_depth=self._last_output.guidance_depth,
                    debug=debug,
                )
            fallback_output = ControlOutput(
                thrust_percent=float(np.clip(self._fallback_thrust_percent, 0.0, 100.0)),
                right_fin_deg=None,
                top_fin_deg=None,
                left_fin_deg=None,
                bottom_fin_deg=None,
                guidance_heading=float(target_heading),
                guidance_depth=float(target_depth),
                debug=debug,
            )
            self._previous_applied_control = np.array(
                [
                    fallback_output.guidance_heading,
                    fallback_output.guidance_depth,
                    fallback_output.thrust_percent,
                ],
                dtype=float,
            )
            return fallback_output

        self._solve_time_ms = result["solve_time_ms"]
        control_period_ms = (
            max(float(setpoint.get("dt", self._dt)), 1e-6) * 1000.0
        )
        result["control_period_ms"] = control_period_ms
        result["control_period_blocked"] = (
            float(result.get("solver_wall_time_current_ms", self._solve_time_ms))
            > control_period_ms
        )
        self._solver_status = result["solver_status"]
        self._solve_time_source = result.get("solve_time_source", "unknown")
        self._last_cost = result["cost_value"]
        self._prev_U = (
            result["U_opt"].copy() if self._warm_start_enabled else None
        )

        U_first = result["U_opt"][:, 0]
        psi_opt = float(U_first[0])
        z_opt = float(U_first[1])
        T_opt = float(U_first[2])

        # WP-C C2: 输出级深度积分补偿。每帧累加深度误差（NED），抗饱和 clamp，
        # 叠加到 MPC 的 z_cmd 上再 clip 到深度约束，消除残余稳态漂移。
        z_cmd_raw = z_opt
        ctrl_dt = float(setpoint.get("dt", self._dt))
        if self._ki_z != 0.0:
            self._z_integral += (target_depth - depth_ned) * ctrl_dt
            self._z_integral = float(
                np.clip(self._z_integral, -self._integral_clamp_m, self._integral_clamp_m)
            )
            z_cmd_out = z_cmd_raw + self._ki_z * self._z_integral
            z_cmd_out = float(np.clip(z_cmd_out, self._min_z_cmd, self._max_z_cmd))
        else:
            z_cmd_out = z_cmd_raw
        z_opt = z_cmd_out
        self._previous_applied_control = np.array(
            [psi_opt, z_opt, T_opt],
            dtype=float,
        )

        elapsed = (time.perf_counter() - t_start) * 1000.0

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

        output = ControlOutput(
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
                "solve_time_source": self._solve_time_source,
                "total_compute_ms": round(elapsed, 2),
                "cost_value": round(self._last_cost, 4),
                "confidence": round(confidence, 3),
                "confidence_policy": self._optimizer.confidence_policy,
                "delta_u_penalty_scale": float(
                    setpoint.get("delta_u_penalty_scale", 1.0)
                ),
                "delta_u_previous_control_available": (
                    previous_control_available
                ),
                "prediction_horizon": self._N,
                "dt": self._dt,
                "warm_start_enabled": self._warm_start_enabled,
                "optimal_control": {
                    "psi_cmd_rad": round(psi_opt, 4),
                    "z_cmd_m": round(z_opt, 2),
                    "T_cmd_pct": round(T_opt, 2),
                },
                "z_cmd_raw": round(z_cmd_raw, 3),
                "z_cmd_out": round(z_cmd_out, 3),
                "z_integral": round(self._z_integral, 4),
                "pred_trajectory": pred_trajectory,
                "ref_trajectory": ref_traj_list,
                "fallback_type": "none",
                **{
                    key: result[key]
                    for key in _SOLVER_DIAGNOSTIC_KEYS
                    if key in result
                },
            },
        )
        self._last_output = output
        return output

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
        self._previous_applied_control = None
        self._solve_time_ms = 0.0
        self._solve_time_source = "not_run"
        self._solver_status = "NOT_RUN"
        self._last_cost = 0.0
        self._z_integral = 0.0
        self._last_output = None

    @property
    def solve_time_ms(self) -> float:
        return self._solve_time_ms

    @property
    def solver_status(self) -> str:
        return self._solver_status

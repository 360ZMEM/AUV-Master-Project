"""AUV 中级模型预测控制器 (MPC) - 核心数学模型与 CasADi 求解器。

本模块实现 Guidance-level MPC（导引层），输出目标航向、目标深度、推力百分比，
而非直接驱动舵角。与 PID 控制器平级，共同构成混合控制架构。

核心设计:
  - 4-DOF 预测模型 (Surge-Heave-Pitch-Yaw)
  - NED 坐标系
  - CasADi Opti + IPOPT 求解器
  - 置信度自适应权重
  - 热启动 (Warm Start)
  - 失效降级信号
"""

import time

import numpy as np
import casadi as ca


class AUVKinematicsModel:
    """AUV 4-DOF 运动学/动力学模型（欠驱动）。

    状态向量 (6):
        X = [x, y, z, psi, u, w]^T
        x, y   : NED 平面位置 (m)
        z      : NED 深度 (m, 正向下)
        psi    : 航向角 (rad)
        u      : 前向速度 Surge (m/s)
        w      : 垂向速度 Heave (m/s)

    控制向量 (3):
        U = [psi_cmd, z_cmd, T_cmd]^T
        psi_cmd : 目标航向 (rad)
        z_cmd   : 目标深度 (m)
        T_cmd   : 推力百分比 (0 ~ 100)

    欠驱动假设:
        - 横向 sway (v) 不被控制，通过 psi 偏转间接影响 (x, y) 轨迹
        - 俯仰角 theta 作为内部状态，由深度跟踪隐式驱动
    """

    def __init__(self, params):
        """从参数字典初始化水动力系数。

        Args:
            params (dict): 包含 mass_u, mass_w, drag_u, drag_w,
                          buoyancy_term, yaw_rate_gain, pitch_depth_gain,
                          depth_to_heave_gain, max_pitch_deg
        """
        self.mass_u = float(params.get("mass_u", 50.0))
        self.mass_w = float(params.get("mass_w", 50.0))
        self.drag_u = float(params.get("drag_u", 15.0))
        self.drag_w = float(params.get("drag_w", 30.0))
        self.buoyancy_term = float(params.get("buoyancy_term", 0.0))
        self.yaw_rate_gain = float(params.get("yaw_rate_gain", 0.5))
        self.pitch_depth_gain = float(params.get("pitch_depth_gain", 0.3))
        self.depth_to_heave_gain = float(params.get("depth_to_heave_gain", 5.0))
        max_pitch_deg = float(params.get("max_pitch_deg", 15.0))
        self.max_pitch_rad = np.deg2rad(max_pitch_deg)

    def compute_dynamics(self, X, U):
        """计算连续时间动力学 dX/dt = f(X, U)。

        Args:
            X (ca.MX): 状态向量 [x, y, z, psi, u, w]
            U (ca.MX): 控制向量 [psi_cmd, z_cmd, T_cmd]

        Returns:
            ca.MX: 状态导数 [dx, dy, dz, dpsi, du, dw]
        """
        x, y, z, psi, u, w = X[0], X[1], X[2], X[3], X[4], X[5]
        psi_cmd, z_cmd, T_cmd = U[0], U[1], U[2]

        dx = u * ca.cos(psi)
        dy = u * ca.sin(psi)

        depth_err = z_cmd - z
        # NED convention: z is positive downward, while positive pitch (theta)
        # is nose-up. A deeper target therefore requires negative pitch so that
        # -u*sin(theta) contributes positive dz (downward motion).
        theta_approx = ca.fmax(-self.max_pitch_rad,
                               ca.fmin(self.max_pitch_rad,
                                       -self.pitch_depth_gain * depth_err))

        sin_theta = ca.sin(theta_approx)
        cos_theta = ca.cos(theta_approx)
        dz = -u * sin_theta + w * cos_theta

        psi_err = psi_cmd - psi
        r = self.yaw_rate_gain * psi_err
        dpsi = r

        thrust_actual = ca.fmax(0.0, T_cmd)
        drag_u_val = self.drag_u * u * ca.fabs(u)
        du = (thrust_actual - drag_u_val) / self.mass_u

        dw = (
            -self.drag_w * w
            + self.depth_to_heave_gain * depth_err
            + self.buoyancy_term
        ) / self.mass_w

        return ca.vertcat(dx, dy, dz, dpsi, du, dw)

    def discrete_step(self, X, U, dt):
        """Euler forward 离散化一步。

        Args:
            X (ca.MX): 当前状态
            U (ca.MX): 当前控制量
            dt (float): 时间步长

        Returns:
            ca.MX: 下一时刻状态
        """
        dX = self.compute_dynamics(X, U)
        return X + dt * dX


class AUVMPCOptimizer:
    """基于 CasADi Opti 的 MPC 优化器。

    构建一次，反复求解。支持热启动和置信度自适应权重。
    """

    N_STATES = 6
    N_CONTROLS = 3

    @staticmethod
    def _normalize_weights(weights):
        """兼容 params.yaml 的嵌套权重格式与测试中的扁平格式。"""
        weights = dict(weights or {})
        normalized = {}
        for section in ("tracking", "control"):
            section_values = weights.get(section)
            if isinstance(section_values, dict):
                normalized.update(section_values)
        for key, value in weights.items():
            if key not in ("tracking", "control"):
                normalized[key] = value
        return normalized

    def __init__(
        self,
        kinematics,
        N=20,
        dt=0.1,
        weights=None,
        constraints=None,
    ):
        """构建 MPC 优化器。

        Args:
            kinematics (AUVKinematicsModel): 运动学模型
            N (int): 预测步数
            dt (float): 时间步长 (秒)
            weights (dict): 代价函数权重
            constraints (dict): 物理约束边界
        """
        self.kinematics = kinematics
        self.N = N
        self.dt = dt

        weights = self._normalize_weights(weights)
        self.W_x = float(weights.get("x", 1.0))
        self.W_y = float(weights.get("y", 1.0))
        self.W_z = float(weights.get("z", 5.0))
        self.W_psi = float(weights.get("psi", 3.0))
        self.W_u = float(weights.get("u", 0.5))
        self.W_w = float(weights.get("w", 1.0))
        self.W_psi_cmd = float(weights.get("psi_cmd", 0.1))
        self.W_z_cmd = float(weights.get("z_cmd", 0.1))
        self.W_T = float(weights.get("T_cmd", 0.05))
        self.confidence_threshold = float(weights.get("confidence_threshold", 0.6))
        self.low_conf_scale = float(weights.get("low_confidence_scale", 3.0))
        self.low_conf_ctrl_scale = float(weights.get("low_confidence_control_scale", 0.3))
        # E3 — sigmoid 平滑 + 消融开关（论文 §4.4.2）
        self.confidence_smoothness_k = float(weights.get("confidence_smoothness_k", 8.0))
        self.confidence_alpha = float(weights.get("confidence_alpha", 1.5))
        self.mpc_mode = str(weights.get("mpc_mode", "ua")).lower()
        if self.mpc_mode not in ("ua", "baseline"):
            self.mpc_mode = "ua"

        constraints = constraints or {}
        self.min_speed = float(constraints.get("min_speed_ms", 0.1))
        self.max_thrust = float(constraints.get("max_thrust_percent", 100.0))
        self.min_thrust = float(constraints.get("min_thrust_percent", 0.0))
        self.min_z_cmd = float(constraints.get("min_z_cmd_m", 0.0))
        self.max_z_cmd = float(constraints.get("max_z_cmd_m", 50.0))
        self.min_psi_cmd = float(constraints.get("min_psi_cmd_rad", -np.pi))
        self.max_psi_cmd = float(constraints.get("max_psi_cmd_rad", np.pi))
        # P1: 参考速率约束（每个 dt 的最大变化量）
        # 默认值与 PVS v2 内环 wn_d_z=0.4 / r_max=12deg/s 相容。
        self.delta_z_max_per_step = float(
            constraints.get("delta_z_max_per_step", 0.5)
        )  # m / step
        self.delta_psi_max_per_step = float(
            constraints.get(
                "delta_psi_max_per_step",
                np.deg2rad(8.0),
            )
        )  # rad / step
        # P1: 参考相对当前态的带宽约束（z_cmd, psi_cmd 不能离当前 z, psi 太远）
        self.z_band = float(constraints.get("z_band_m", 3.0))
        self.psi_band = float(constraints.get("psi_band_rad", np.deg2rad(45.0)))
        # P1: 启用/禁用速率/带宽约束（用于消融）
        self.enable_rate_constraints = bool(
            constraints.get("enable_rate_constraints", True)
        )
        self.enable_band_constraints = bool(
            constraints.get("enable_band_constraints", True)
        )

        self._build_solver()

    def _build_solver(self):
        """构建 CasADi Opti 优化问题（编译一次）。"""
        n_s = self.N_STATES
        n_c = self.N_CONTROLS
        N = self.N
        dt = self.dt

        opti = ca.Opti()

        # 决策变量
        X = opti.variable(n_s, N + 1)
        U = opti.variable(n_c, N)

        # 参数
        x0_param = opti.parameter(n_s)
        ref_X_param = opti.parameter(n_s, N + 1)
        confidence_param = opti.parameter()

        # 初始状态约束
        opti.subject_to(X[:, 0] == x0_param)

        # 动力学约束
        for k in range(N):
            x_next = self.kinematics.discrete_step(X[:, k], U[:, k], dt)
            opti.subject_to(X[:, k + 1] == x_next)

        # 硬约束：航速下限（确保舵效）
        opti.subject_to(X[4, 1:] >= self.min_speed)

        # 硬约束：制导指令边界，防止优化器输出不可执行的极端参考。
        opti.subject_to(opti.bounded(self.min_psi_cmd, U[0, :], self.max_psi_cmd))
        opti.subject_to(opti.bounded(self.min_z_cmd, U[1, :], self.max_z_cmd))

        # 硬约束：推力上下限（min_thrust 防止 z_cmd 拉飞时把推力清零导致失稳）
        opti.subject_to(opti.bounded(self.min_thrust, U[2, :], self.max_thrust))

        # P1: 参考速率约束（z_cmd / psi_cmd 每个 dt 的最大变化量）
        if self.enable_rate_constraints and N >= 2:
            for k in range(N - 1):
                opti.subject_to(opti.bounded(
                    -self.delta_z_max_per_step,
                    U[1, k + 1] - U[1, k],
                    self.delta_z_max_per_step,
                ))
                # psi 速率约束（差分 wrap 不严格，但 N·dt 内 psi 不会绕圈）
                opti.subject_to(opti.bounded(
                    -self.delta_psi_max_per_step,
                    U[0, k + 1] - U[0, k],
                    self.delta_psi_max_per_step,
                ))
            # 第一步参考相对当前态的速率限制
            opti.subject_to(opti.bounded(
                -self.delta_z_max_per_step,
                U[1, 0] - x0_param[2],
                self.delta_z_max_per_step,
            ))
            opti.subject_to(opti.bounded(
                -self.delta_psi_max_per_step,
                U[0, 0] - x0_param[3],
                self.delta_psi_max_per_step,
            ))

        # P1: 参考带宽约束（z_cmd / psi_cmd 与当前 z, psi 偏差不超过带宽）
        if self.enable_band_constraints:
            for k in range(N):
                opti.subject_to(opti.bounded(
                    -self.z_band,
                    U[1, k] - x0_param[2],
                    self.z_band,
                ))
                opti.subject_to(opti.bounded(
                    -self.psi_band,
                    U[0, k] - x0_param[3],
                    self.psi_band,
                ))

        # 软约束：指令物理合理性 (作为代价函数的惩罚项而非硬约束)
        # 这些约束通过代价函数中的控制权重自然限制

        # 代价函数
        J = 0

        for k in range(N + 1):
            err = X[:, k] - ref_X_param[:, k]
            conf = confidence_param

            if self.mpc_mode == "baseline":
                # 消融基线：忽略置信度，权重恒定
                w_x = self.W_x
                w_y = self.W_y
                w_z = self.W_z
                w_psi = self.W_psi
            else:
                # UA-MPC：(1 - conf)^alpha 平滑放大跟踪权重
                conf_pow = ca.power(ca.fmax(0.0, 1.0 - conf), self.confidence_alpha)
                w_x = self.W_x * (1.0 + (self.low_conf_scale - 1.0) * conf_pow)
                w_y = self.W_y * (1.0 + (self.low_conf_scale - 1.0) * conf_pow)
                w_z = self.W_z * (1.0 + 0.5 * conf_pow)
                w_psi = self.W_psi * (1.0 + (self.low_conf_scale - 1.0) * conf_pow)

            J += (
                w_x * err[0] ** 2
                + w_y * err[1] ** 2
                + w_z * err[2] ** 2
                + w_psi * err[3] ** 2
                + self.W_u * err[4] ** 2
                + self.W_w * err[5] ** 2
            )

        for k in range(N):
            ctrl_effort = (
                self.W_psi_cmd * U[0, k] ** 2
                + self.W_z_cmd * U[1, k] ** 2
                + self.W_T * U[2, k] ** 2
            )

            conf = confidence_param
            if self.mpc_mode == "baseline":
                control_scale = 1.0
            else:
                # sigmoid 平滑：conf 高 → control_scale ≈ 1；conf 低 → low_conf_ctrl_scale
                sig = 1.0 / (1.0 + ca.exp(
                    self.confidence_smoothness_k * (conf - self.confidence_threshold)
                ))
                control_scale = (
                    self.low_conf_ctrl_scale
                    + (1.0 - self.low_conf_ctrl_scale) * (1.0 - sig)
                )
            J += control_scale * ctrl_effort

        opti.minimize(J)

        opts = {
            "ipopt.print_level": 0,
            "print_time": False,
            "ipopt.tol": 1e-4,
            "ipopt.max_iter": 100,
        }
        opti.solver("ipopt", opts)

        self.opti = opti
        self.X = X
        self.U = U
        self.x0_param = x0_param
        self.ref_X_param = ref_X_param
        self.confidence_param = confidence_param

    def solve(self, x0, ref_trajectory, confidence, warm_start_U=None):
        """求解 MPC 优化问题。

        Args:
            x0 (np.ndarray): 当前状态 (6,)
            ref_trajectory (np.ndarray): 参考轨迹 (6, N+1)
            confidence (float): 传感器置信度 [0, 1]
            warm_start_U (np.ndarray | None): 上一次最优控制序列 (3, N)

        Returns:
            dict: 包含最优控制、预测轨迹、求解统计
        """
        opti = self.opti

        opti.set_value(self.x0_param, x0)
        opti.set_value(self.ref_X_param, ref_trajectory)
        opti.set_value(self.confidence_param, float(np.clip(confidence, 0.0, 1.0)))

        if warm_start_U is not None:
            for k in range(self.N):
                if k < self.N - 1:
                    u_guess = warm_start_U[:, k + 1]
                else:
                    u_guess = warm_start_U[:, -1]
                opti.set_initial(self.U[:, k], u_guess)

        try:
            t0 = time.perf_counter()
            sol = opti.solve()
            wall_ms = (time.perf_counter() - t0) * 1000.0
            status = str(sol.stats()["return_status"])
            ipopt_ms = float(sol.stats().get("t_proc_total", 0)) * 1000.0
            if ipopt_ms > 0.0:
                solve_time_ms = ipopt_ms
                solve_time_source = "ipopt_t_proc"
            else:
                solve_time_ms = wall_ms
                solve_time_source = "wall_perf_counter"
        except RuntimeError as e:
            status = f"FAILED: {str(e)}"
            solve_time_ms = 0.0
            solve_time_source = "failed"
            raise RuntimeError(f"MPC solver failed: {status}") from e

        if status not in (
            "Solve_Succeeded",
            "Search_Direction_Becomes_Too_Small",
        ):
            raise RuntimeError(f"MPC infeasible: {status}")

        U_opt = sol.value(self.U)
        X_opt = sol.value(self.X)
        cost_val = float(sol.value(opti.f))

        return {
            "U_opt": np.array(U_opt),
            "X_opt": np.array(X_opt),
            "solver_status": status,
            "solve_time_ms": solve_time_ms,
            "solve_time_source": solve_time_source,
            "cost_value": cost_val,
        }

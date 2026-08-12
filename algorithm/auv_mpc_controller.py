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


class MPCSolveError(RuntimeError):
    """MPC solve failure carrying diagnostics for the current control cycle."""

    def __init__(self, message, diagnostics):
        super().__init__(message)
        self.diagnostics = dict(diagnostics)


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
        # A hard clamp creates a zero-gradient plateau once the depth error
        # exceeds max_pitch / pitch_depth_gain. The smooth saturation preserves
        # the same physical bound while keeping the NLP differentiable.
        theta_raw = -self.pitch_depth_gain * depth_err
        theta_approx = self.max_pitch_rad * ca.tanh(
            theta_raw / self.max_pitch_rad
        )

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
        max_iter=100,
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
        self.max_iter = max(1, int(max_iter))

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
        self.confidence_policy = str(
            weights.get("confidence_policy", "legacy_aggressive")
        ).strip().lower()
        if self.confidence_policy not in {
            "legacy_aggressive",
            "conservative",
        }:
            raise ValueError(
                f"unsupported confidence_policy={self.confidence_policy!r}"
            )
        self.low_conf_control_penalty_scale = float(
            weights.get("low_conf_control_penalty_scale", 3.0)
        )
        self.low_conf_tracking_floor = float(
            weights.get("low_conf_tracking_floor", 0.5)
        )
        self.W_delta_psi_cmd = float(weights.get("delta_psi_cmd", 0.0))
        self.W_delta_z_cmd = float(weights.get("delta_z_cmd", 0.0))
        self.W_delta_T_cmd = float(weights.get("delta_T_cmd", 0.0))
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
        self.enable_constraint_slack = bool(
            constraints.get("enable_constraint_slack", False)
        )
        self.constraint_slack_weight = float(
            constraints.get("constraint_slack_weight", 1e4)
        )
        self.max_speed_slack = float(
            constraints.get("max_speed_slack_ms", max(self.min_speed, 0.1))
        )
        self.max_depth_rate_slack = float(
            constraints.get(
                "max_depth_rate_slack_m",
                max(self.delta_z_max_per_step, 0.1),
            )
        )
        self.max_heading_rate_slack = float(
            constraints.get(
                "max_heading_rate_slack_rad",
                max(self.delta_psi_max_per_step, np.deg2rad(1.0)),
            )
        )
        self.max_depth_band_slack = float(
            constraints.get("max_depth_band_slack_m", max(self.z_band, 0.1))
        )
        self.max_heading_band_slack = float(
            constraints.get(
                "max_heading_band_slack_rad",
                max(self.psi_band, np.deg2rad(1.0)),
            )
        )
        self._last_x0 = None

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
        delta_u_penalty_scale_param = opti.parameter()
        previous_control_param = opti.parameter(n_c)

        # 初始状态约束
        opti.subject_to(X[:, 0] == x0_param)

        # 动力学约束
        for k in range(N):
            x_next = self.kinematics.discrete_step(X[:, k], U[:, k], dt)
            opti.subject_to(X[:, k + 1] == x_next)

        slack_variables = []
        slack_penalties = []

        def add_slack(name, count, maximum):
            slack = opti.variable(1, count)
            opti.subject_to(opti.bounded(0.0, slack, maximum))
            opti.set_initial(slack, 0.0)
            slack_variables.append(slack)
            scale = max(float(maximum), 1e-6)
            slack_penalties.append(ca.sum2(slack / scale))
            return slack

        # 航速下限用于维持舵效；恢复模式允许显式、有界的软化。
        if self.enable_constraint_slack:
            speed_slack = add_slack("speed", N, self.max_speed_slack)
            opti.subject_to(X[4, 1:] + speed_slack >= self.min_speed)
        else:
            opti.subject_to(X[4, 1:] >= self.min_speed)

        # 硬约束：制导指令边界，防止优化器输出不可执行的极端参考。
        opti.subject_to(opti.bounded(self.min_psi_cmd, U[0, :], self.max_psi_cmd))
        opti.subject_to(opti.bounded(self.min_z_cmd, U[1, :], self.max_z_cmd))

        # 硬约束：推力上下限（min_thrust 防止 z_cmd 拉飞时把推力清零导致失稳）
        opti.subject_to(opti.bounded(self.min_thrust, U[2, :], self.max_thrust))

        # P1: 参考速率约束（z_cmd / psi_cmd 每个 dt 的最大变化量）
        if self.enable_rate_constraints and N >= 2:
            if self.enable_constraint_slack:
                depth_rate_slack = add_slack(
                    "depth_rate", N, self.max_depth_rate_slack
                )
                heading_rate_slack = add_slack(
                    "heading_rate", N, self.max_heading_rate_slack
                )
                depth_deltas = [U[1, 0] - x0_param[2]]
                heading_deltas = [U[0, 0] - x0_param[3]]
                depth_deltas.extend(
                    U[1, k + 1] - U[1, k] for k in range(N - 1)
                )
                heading_deltas.extend(
                    U[0, k + 1] - U[0, k] for k in range(N - 1)
                )
                for k, delta in enumerate(depth_deltas):
                    opti.subject_to(
                        delta <= self.delta_z_max_per_step + depth_rate_slack[k]
                    )
                    opti.subject_to(
                        delta >= -self.delta_z_max_per_step - depth_rate_slack[k]
                    )
                for k, delta in enumerate(heading_deltas):
                    opti.subject_to(
                        delta
                        <= self.delta_psi_max_per_step + heading_rate_slack[k]
                    )
                    opti.subject_to(
                        delta
                        >= -self.delta_psi_max_per_step - heading_rate_slack[k]
                    )
            else:
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
            if self.enable_constraint_slack:
                depth_band_slack = add_slack(
                    "depth_band", N, self.max_depth_band_slack
                )
                heading_band_slack = add_slack(
                    "heading_band", N, self.max_heading_band_slack
                )
                for k in range(N):
                    depth_delta = U[1, k] - x0_param[2]
                    heading_delta = U[0, k] - x0_param[3]
                    opti.subject_to(
                        depth_delta <= self.z_band + depth_band_slack[k]
                    )
                    opti.subject_to(
                        depth_delta >= -self.z_band - depth_band_slack[k]
                    )
                    opti.subject_to(
                        heading_delta <= self.psi_band + heading_band_slack[k]
                    )
                    opti.subject_to(
                        heading_delta >= -self.psi_band - heading_band_slack[k]
                    )
            else:
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
            elif self.confidence_policy == "conservative":
                conf_pow = ca.power(
                    ca.fmax(0.0, 1.0 - conf),
                    self.confidence_alpha,
                )
                tracking_scale = self.low_conf_tracking_floor + (
                    1.0 - self.low_conf_tracking_floor
                ) * conf
                w_x = self.W_x * tracking_scale
                w_y = self.W_y * tracking_scale
                w_z = self.W_z
                w_psi = self.W_psi * tracking_scale
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
            elif self.confidence_policy == "conservative":
                conf_pow = ca.power(
                    ca.fmax(0.0, 1.0 - conf),
                    self.confidence_alpha,
                )
                control_scale = 1.0 + (
                    self.low_conf_control_penalty_scale - 1.0
                ) * conf_pow
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
            previous_control = (
                previous_control_param if k == 0 else U[:, k - 1]
            )
            if (
                self.W_delta_psi_cmd > 0.0
                or self.W_delta_z_cmd > 0.0
                or self.W_delta_T_cmd > 0.0
            ):
                delta_cost = (
                    self.W_delta_psi_cmd
                    * (U[0, k] - previous_control[0]) ** 2
                    + self.W_delta_z_cmd
                    * (U[1, k] - previous_control[1]) ** 2
                    + self.W_delta_T_cmd
                    * (U[2, k] - previous_control[2]) ** 2
                )
                J += delta_u_penalty_scale_param * delta_cost

        if slack_penalties:
            J += self.constraint_slack_weight * sum(slack_penalties)

        opti.minimize(J)

        opts = {
            "ipopt.print_level": 0,
            "print_time": False,
            "ipopt.tol": 1e-4,
            "ipopt.max_iter": self.max_iter,
        }
        opti.solver("ipopt", opts)

        self.opti = opti
        self.X = X
        self.U = U
        self.x0_param = x0_param
        self.ref_X_param = ref_X_param
        self.confidence_param = confidence_param
        self.delta_u_penalty_scale_param = delta_u_penalty_scale_param
        self.previous_control_param = previous_control_param
        self.slack_vector = (
            ca.vertcat(*slack_variables) if slack_variables else None
        )

    @staticmethod
    def _slack_metrics(values):
        if values is None:
            return {
                "slack_max": 0.0,
                "slack_l1": 0.0,
                "slack_l2": 0.0,
                "slack_active_count": 0,
            }
        values = np.asarray(values, dtype=float).reshape(-1)
        if not values.size:
            return {
                "slack_max": 0.0,
                "slack_l1": 0.0,
                "slack_l2": 0.0,
                "slack_active_count": 0,
            }
        values = np.maximum(values, 0.0)
        return {
            "slack_max": float(np.max(values)),
            "slack_l1": float(np.sum(values)),
            "slack_l2": float(np.linalg.norm(values)),
            "slack_active_count": int(np.count_nonzero(values > 1e-6)),
        }

    def _evaluate_slack(self, *, solution=None):
        if self.slack_vector is None:
            return self._slack_metrics(None)
        try:
            values = (
                solution.value(self.slack_vector)
                if solution is not None
                else self.opti.debug.value(self.slack_vector)
            )
        except RuntimeError:
            return {
                "slack_max": None,
                "slack_l1": None,
                "slack_l2": None,
                "slack_active_count": None,
            }
        return self._slack_metrics(values)

    def _reference_control_guess(self, x0, ref_trajectory):
        guess = np.zeros((self.N_CONTROLS, self.N), dtype=float)
        guess[0, :] = np.asarray(ref_trajectory[3, : self.N], dtype=float)
        guess[1, :] = np.asarray(ref_trajectory[2, : self.N], dtype=float)
        target_speed = np.asarray(ref_trajectory[4, : self.N], dtype=float)
        guess[2, :] = (
            self.kinematics.drag_u * target_speed * np.abs(target_speed)
        )
        return guess

    def _project_control_guess(self, x0, guess):
        projected = np.asarray(guess, dtype=float).copy()
        projected[0, :] = np.clip(
            projected[0, :], self.min_psi_cmd, self.max_psi_cmd
        )
        projected[1, :] = np.clip(
            projected[1, :], self.min_z_cmd, self.max_z_cmd
        )
        projected[2, :] = np.clip(
            projected[2, :], self.min_thrust, self.max_thrust
        )

        previous_heading = float(x0[3])
        previous_depth = float(x0[2])
        for k in range(self.N):
            heading_low = self.min_psi_cmd
            heading_high = self.max_psi_cmd
            depth_low = self.min_z_cmd
            depth_high = self.max_z_cmd
            if self.enable_rate_constraints:
                heading_low = max(
                    heading_low,
                    previous_heading - self.delta_psi_max_per_step,
                )
                heading_high = min(
                    heading_high,
                    previous_heading + self.delta_psi_max_per_step,
                )
                depth_low = max(
                    depth_low,
                    previous_depth - self.delta_z_max_per_step,
                )
                depth_high = min(
                    depth_high,
                    previous_depth + self.delta_z_max_per_step,
                )
            if self.enable_band_constraints:
                heading_low = max(heading_low, float(x0[3]) - self.psi_band)
                heading_high = min(heading_high, float(x0[3]) + self.psi_band)
                depth_low = max(depth_low, float(x0[2]) - self.z_band)
                depth_high = min(depth_high, float(x0[2]) + self.z_band)
            if heading_low <= heading_high:
                projected[0, k] = np.clip(
                    projected[0, k], heading_low, heading_high
                )
            if depth_low <= depth_high:
                projected[1, k] = np.clip(
                    projected[1, k], depth_low, depth_high
                )
            previous_heading = float(projected[0, k])
            previous_depth = float(projected[1, k])
        return projected

    def _rollout_state_guess(self, x0, control_guess):
        states = np.zeros((self.N_STATES, self.N + 1), dtype=float)
        states[:, 0] = np.asarray(x0, dtype=float)
        model = self.kinematics
        for k in range(self.N):
            x, y, z, psi, u, w = states[:, k]
            psi_cmd, z_cmd, thrust_cmd = control_guess[:, k]
            depth_error = z_cmd - z
            theta_raw = -model.pitch_depth_gain * depth_error
            theta = model.max_pitch_rad * np.tanh(
                theta_raw / model.max_pitch_rad
            )
            derivatives = np.array(
                [
                    u * np.cos(psi),
                    u * np.sin(psi),
                    -u * np.sin(theta) + w * np.cos(theta),
                    model.yaw_rate_gain * (psi_cmd - psi),
                    (
                        max(0.0, thrust_cmd)
                        - model.drag_u * u * abs(u)
                    )
                    / model.mass_u,
                    (
                        -model.drag_w * w
                        + model.depth_to_heave_gain * depth_error
                        + model.buoyancy_term
                    )
                    / model.mass_w,
                ],
                dtype=float,
            )
            states[:, k + 1] = states[:, k] + self.dt * derivatives
        return states

    @staticmethod
    def _constraint_metrics(values, lower_bounds, upper_bounds):
        """Summarize bound violations without exposing solver-sized arrays."""
        values = np.asarray(values, dtype=float).reshape(-1)
        lower = np.asarray(lower_bounds, dtype=float).reshape(-1)
        upper = np.asarray(upper_bounds, dtype=float).reshape(-1)
        if not (values.size == lower.size == upper.size):
            return {
                "constraint_count": 0,
                "constraint_violation_max": None,
                "constraint_violation_l2": None,
                "active_constraint_count": 0,
            }

        lower_violation = np.where(
            np.isfinite(lower), np.maximum(lower - values, 0.0), 0.0
        )
        upper_violation = np.where(
            np.isfinite(upper), np.maximum(values - upper, 0.0), 0.0
        )
        violation = np.maximum(lower_violation, upper_violation)

        tolerance = 1e-4
        equality = (
            np.isfinite(lower)
            & np.isfinite(upper)
            & (np.abs(upper - lower) <= tolerance)
        )
        active_lower = np.isfinite(lower) & (np.abs(values - lower) <= tolerance)
        active_upper = np.isfinite(upper) & (np.abs(values - upper) <= tolerance)
        active = equality | active_lower | active_upper
        return {
            "constraint_count": int(values.size),
            "constraint_violation_max": float(np.max(violation))
            if violation.size
            else 0.0,
            "constraint_violation_l2": float(np.linalg.norm(violation)),
            "active_constraint_count": int(np.count_nonzero(active)),
        }

    def _evaluate_constraints(self, *, solution=None, initial=False):
        """Evaluate constraints at the configured initial point or latest iterate."""
        opti = self.opti
        try:
            if solution is not None:
                values = solution.value(opti.g)
                lower = solution.value(opti.lbg)
                upper = solution.value(opti.ubg)
            elif initial:
                values = opti.value(opti.g, opti.initial())
                lower = opti.value(opti.lbg, opti.initial())
                upper = opti.value(opti.ubg, opti.initial())
            else:
                values = opti.debug.value(opti.g)
                lower = opti.debug.value(opti.lbg)
                upper = opti.debug.value(opti.ubg)
        except RuntimeError:
            return {
                "constraint_count": 0,
                "constraint_violation_max": None,
                "constraint_violation_l2": None,
                "active_constraint_count": 0,
            }
        return self._constraint_metrics(values, lower, upper)

    @staticmethod
    def _prefixed_metrics(prefix, metrics):
        return {
            f"{prefix}_constraint_violation_max": metrics[
                "constraint_violation_max"
            ],
            f"{prefix}_constraint_violation_l2": metrics[
                "constraint_violation_l2"
            ],
            f"{prefix}_active_constraint_count": metrics[
                "active_constraint_count"
            ],
        }

    def solve(
        self,
        x0,
        ref_trajectory,
        confidence,
        warm_start_U=None,
        delta_u_penalty_scale=1.0,
        previous_control=None,
    ):
        """求解 MPC 优化问题。

        Args:
            x0 (np.ndarray): 当前状态 (6,)
            ref_trajectory (np.ndarray): 参考轨迹 (6, N+1)
            confidence (float): 传感器置信度 [0, 1]
            warm_start_U (np.ndarray | None): 上一次最优控制序列 (3, N)
            delta_u_penalty_scale (float): 当前置信度对应的控制增量惩罚倍率
            previous_control (np.ndarray | None): 上一周期实际应用的控制量 (3,)

        Returns:
            dict: 包含最优控制、预测轨迹、求解统计
        """
        opti = self.opti

        opti.set_value(self.x0_param, x0)
        opti.set_value(self.ref_X_param, ref_trajectory)
        opti.set_value(self.confidence_param, float(np.clip(confidence, 0.0, 1.0)))
        opti.set_value(
            self.delta_u_penalty_scale_param,
            max(float(delta_u_penalty_scale), 1.0),
        )
        if previous_control is None:
            previous_control_value = self._reference_control_guess(
                x0,
                ref_trajectory,
            )[:, 0]
        else:
            previous_control_value = np.asarray(
                previous_control,
                dtype=float,
            ).reshape(self.N_CONTROLS)
        opti.set_value(
            self.previous_control_param,
            previous_control_value,
        )

        x0_array = np.asarray(x0, dtype=float).reshape(-1)
        warm_start_provided = warm_start_U is not None
        warm_start_used = False
        warm_start_shift_rms = None
        initial_guess_source = "reference_projected"
        if warm_start_U is not None:
            warm_start_array = np.asarray(warm_start_U, dtype=float)
            warm_start_used = (
                warm_start_array.shape == (self.N_CONTROLS, self.N)
                and np.all(np.isfinite(warm_start_array))
            )
        if warm_start_used:
            shifted_warm_start = np.column_stack(
                [warm_start_array[:, 1:], warm_start_array[:, -1]]
            )
            warm_start_shift_rms = float(
                np.sqrt(np.mean((shifted_warm_start - warm_start_array) ** 2))
            )
            raw_control_guess = shifted_warm_start
            initial_guess_source = "warm_shifted_projected"
        else:
            raw_control_guess = self._reference_control_guess(
                x0_array,
                ref_trajectory,
            )

        control_guess = self._project_control_guess(
            x0_array,
            raw_control_guess,
        )
        projection_rms = float(
            np.sqrt(np.mean((control_guess - raw_control_guess) ** 2))
        )
        state_guess = self._rollout_state_guess(x0_array, control_guess)
        opti.set_initial(self.U, control_guess)
        opti.set_initial(self.X, state_guess)

        state_initial_jump_l2 = None
        if self._last_x0 is not None and self._last_x0.shape == x0_array.shape:
            state_initial_jump_l2 = float(np.linalg.norm(x0_array - self._last_x0))
        self._last_x0 = x0_array.copy()

        initial_metrics = self._evaluate_constraints(initial=True)
        diagnostics = {
            "warm_start_provided": bool(warm_start_provided),
            "warm_start_used": bool(warm_start_used),
            "warm_start_control_shift_rms": warm_start_shift_rms,
            "initial_guess_source": initial_guess_source,
            "initial_guess_projection_rms": projection_rms,
            "state_initial_jump_l2": state_initial_jump_l2,
            "constraint_slack_enabled": bool(self.enable_constraint_slack),
            "constraint_count": initial_metrics["constraint_count"],
            **self._prefixed_metrics("initial", initial_metrics),
        }

        t0 = time.perf_counter()
        try:
            sol = opti.solve()
            wall_ms = (time.perf_counter() - t0) * 1000.0
            stats = sol.stats()
            status = str(stats["return_status"])
            ipopt_ms = float(stats.get("t_proc_total", 0)) * 1000.0
            if ipopt_ms > 0.0:
                solve_time_ms = ipopt_ms
                solve_time_source = "ipopt_t_proc"
            else:
                solve_time_ms = wall_ms
                solve_time_source = "wall_perf_counter"
        except RuntimeError as e:
            wall_ms = (time.perf_counter() - t0) * 1000.0
            try:
                stats = opti.stats()
            except RuntimeError:
                stats = {}
            status = str(stats.get("return_status") or f"FAILED: {str(e)}")
            final_metrics = self._evaluate_constraints()
            slack_metrics = self._evaluate_slack()
            diagnostics.update(
                {
                    "solver_status": status,
                    "solver_success": False,
                    "solver_iterations": int(stats.get("iter_count", 0)),
                    "solve_time_ms": wall_ms,
                    "solve_time_source": "wall_perf_counter_failed",
                    "solver_wall_time_current_ms": wall_ms,
                    "control_period_ms": self.dt * 1000.0,
                    "control_period_blocked": wall_ms > self.dt * 1000.0,
                    "constraint_count": max(
                        diagnostics["constraint_count"],
                        final_metrics["constraint_count"],
                    ),
                    **self._prefixed_metrics("final", final_metrics),
                    **slack_metrics,
                }
            )
            raise MPCSolveError(f"MPC solver failed: {status}", diagnostics) from e

        if status not in (
            "Solve_Succeeded",
            "Search_Direction_Becomes_Too_Small",
        ):
            final_metrics = self._evaluate_constraints(solution=sol)
            slack_metrics = self._evaluate_slack(solution=sol)
            diagnostics.update(
                {
                    "solver_status": status,
                    "solver_success": False,
                    "solver_iterations": int(stats.get("iter_count", 0)),
                    "solve_time_ms": solve_time_ms,
                    "solve_time_source": solve_time_source,
                    "solver_wall_time_current_ms": wall_ms,
                    "control_period_ms": self.dt * 1000.0,
                    "control_period_blocked": wall_ms > self.dt * 1000.0,
                    "constraint_count": max(
                        diagnostics["constraint_count"],
                        final_metrics["constraint_count"],
                    ),
                    **self._prefixed_metrics("final", final_metrics),
                    **slack_metrics,
                }
            )
            raise MPCSolveError(f"MPC infeasible: {status}", diagnostics)

        U_opt = sol.value(self.U)
        X_opt = sol.value(self.X)
        cost_val = float(sol.value(opti.f))
        final_metrics = self._evaluate_constraints(solution=sol)
        slack_metrics = self._evaluate_slack(solution=sol)
        diagnostics.update(
            {
                "solver_status": status,
                "solver_success": True,
                "solver_iterations": int(stats.get("iter_count", 0)),
                "solve_time_ms": solve_time_ms,
                "solve_time_source": solve_time_source,
                "solver_wall_time_current_ms": wall_ms,
                "control_period_ms": self.dt * 1000.0,
                "control_period_blocked": wall_ms > self.dt * 1000.0,
                "constraint_count": max(
                    diagnostics["constraint_count"],
                    final_metrics["constraint_count"],
                ),
                **self._prefixed_metrics("final", final_metrics),
                **slack_metrics,
            }
        )

        return {
            "U_opt": np.array(U_opt),
            "X_opt": np.array(X_opt),
            "cost_value": cost_val,
            **diagnostics,
        }

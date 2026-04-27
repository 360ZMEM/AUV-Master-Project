import numpy as np


def wrap_angle(angle):
    """将角度包裹到主值区间，用于航向误差连续化。"""
    return (angle + np.pi) % (2 * np.pi) - np.pi


class PIDAxis:
    """单轴 PID 调节器。

    该类用于深度、俯仰、航向和速度四个控制通道，统一处理积分限幅、
    导数反馈和输出饱和后的积分回退逻辑。
    """

    def __init__(self, kp, ki, kd, integral_limit):
        """初始化 PID 增益和积分限幅。

        Args:
            kp (float): 比例增益。
            ki (float): 积分增益。
            kd (float): 微分增益。
            integral_limit (float): 积分状态绝对值上限。
        """
        self.kp = float(kp)
        self.ki = float(ki)
        self.kd = float(kd)
        self.integral_limit = float(integral_limit)
        self.integral = 0.0

    def reset_integral(self):
        """清零积分项，用于失速、保护或模式切换后的恢复。"""
        self.integral = 0.0

    def compute(
        self,
        error,
        dt,
        d_feedback=0.0,
        gain_scale=1.0,
        output_limit=None,
        integrate_enabled=True,
    ):
        """根据当前误差和反馈量计算 PID 输出。

        Args:
            error (float): 当前控制误差。
            dt (float): 控制周期，单位秒。
            d_feedback (float): 导数反馈量，通常是被控量变化率。
            gain_scale (float): 速度相关的增益缩放因子。
            output_limit (float | None): 输出限幅；为 None 时不饱和。
            integrate_enabled (bool): 是否允许积分累积。

        Returns:
            tuple[float, bool]: 控制输出和是否发生饱和。
        """
        proportional = self.kp * error
        derivative = -self.kd * d_feedback

        if integrate_enabled:
            self.integral += error * dt
            self.integral = float(np.clip(self.integral, -self.integral_limit, self.integral_limit))

        integral_term = self.ki * self.integral
        output_unsat = gain_scale * (proportional + integral_term + derivative)

        if output_limit is None:
            return output_unsat, False

        output_sat = float(np.clip(output_unsat, -output_limit, output_limit))
        saturated = abs(output_sat - output_unsat) > 1e-9

        if saturated and integrate_enabled:
            self.integral -= error * dt
            self.integral = float(np.clip(self.integral, -self.integral_limit, self.integral_limit))
            integral_term = self.ki * self.integral
            output_unsat = gain_scale * (proportional + integral_term + derivative)
            output_sat = float(np.clip(output_unsat, -output_limit, output_limit))

        return output_sat, saturated


class AUVPIDController:
    """AUV 级联 PID 控制器。

    控制链路按深度外环、俯仰内环、航向内环和速度环组织，输出五通道
    舵面/推力指令，供仿真与 ROS2 控制节点共享。
    """

    def __init__(self, control_cfg, limits_cfg):
        """从控制参数和物理约束参数初始化控制器。

        Args:
            control_cfg (dict): 控制器配置，包含 depth/pitch/yaw/speed 等子项。
            limits_cfg (dict): 舵面和推力物理上限配置。
        """
        self.u0 = float(control_cfg["u0"])
        self.u_min = float(control_cfg["u_min"])
        self.target_u_default = float(control_cfg["target_u"])

        self.fin_deg_max = float(limits_cfg["fin_deg_max"])
        self.thrust_min = float(limits_cfg["thrust_min"])
        self.thrust_max = float(limits_cfg["thrust_max"])

        self.depth_pid = PIDAxis(**self._pid_cfg(control_cfg["depth"]))
        self.pitch_pid = PIDAxis(**self._pid_cfg(control_cfg["pitch"]))
        self.yaw_pid = PIDAxis(**self._pid_cfg(control_cfg["yaw"]))
        self.speed_pid = PIDAxis(**self._pid_cfg(control_cfg["speed"]))

        self.target_pitch_limit_rad = np.deg2rad(float(control_cfg["depth"]["target_pitch_deg_max"]))
        self.target_pitch_rate_limit = np.deg2rad(float(control_cfg["depth"].get("target_pitch_rate_limit_deg_s", 10.0)))
        self.feedforward_trim = np.deg2rad(float(control_cfg.get("feedforward_trim_deg", 0.0)))

        speed_ff_cfg = control_cfg.get("speed", {}).get("feedforward", {})
        self.speed_ff_a = float(speed_ff_cfg.get("a", 0.0))
        self.speed_ff_b = float(speed_ff_cfg.get("b", 0.0))
        self.speed_ff_c = float(speed_ff_cfg.get("c", 0.0))

        attitude_guard_cfg = control_cfg.get("attitude_guard", {})
        self.attitude_guard_enable = bool(attitude_guard_cfg.get("enable", False))
        self.attitude_guard_roll_deg_max = float(attitude_guard_cfg.get("roll_deg_max", 120.0))
        self.attitude_guard_pitch_deg_max = float(attitude_guard_cfg.get("pitch_deg_max", 45.0))
        self.attitude_guard_recovery_target_pitch_rad = np.deg2rad(
            float(attitude_guard_cfg.get("recovery_target_pitch_deg", 0.0))
        )
        self.attitude_guard_recovery_thrust = float(attitude_guard_cfg.get("recovery_thrust", 20.0))

        self.prev_target_pitch = 0.0

    @staticmethod
    def _pid_cfg(cfg):
        """提取单轴 PID 配置并转为标准字典。"""
        return {
            "kp": cfg["kp"],
            "ki": cfg["ki"],
            "kd": cfg["kd"],
            "integral_limit": cfg["integral_limit"],
        }

    def _gain_scale(self, u_forward):
        """根据当前航速计算控制增益缩放因子。"""
        effective_u = max(float(abs(u_forward)), self.u_min)
        return (self.u0 / effective_u) ** 2

    def compute(self, state, target):
        """根据当前状态和目标值生成舵面与推力指令。

        Args:
            state (dict): 当前姿态、速度和角速度状态，角度单位为弧度，
                深度单位为米，速度单位为 m/s。
            target (dict): 目标深度、目标航向和目标前进速度。

        Returns:
            tuple[np.ndarray, dict]: 五通道控制命令和调试信息。

        Notes:
            输出顺序为 [right, top, left, bottom, thrust]，其中前四项最终
            会转换为角度制并做物理限幅。
        """
        dt = float(target.get("dt", 0.0333333333))

        current_pitch = float(state["pitch"])
        current_roll = float(state["roll"])
        current_yaw = float(state["yaw"])
        current_depth = float(state["depth"])
        u_forward = float(state["u"])
        gyro_y = float(state["q"])
        gyro_z = float(state["r"])

        target_depth = float(target["target_depth"])
        target_yaw = float(target["target_yaw"])
        target_u = float(target.get("target_u", self.target_u_default))

        gain_scale = self._gain_scale(u_forward)
        low_speed = abs(u_forward) < self.u_min
        attitude_guard_active = self.attitude_guard_enable and (
            abs(np.rad2deg(current_roll)) > self.attitude_guard_roll_deg_max
            or abs(np.rad2deg(current_pitch)) > self.attitude_guard_pitch_deg_max
        )

        depth_error = target_depth - current_depth

        if attitude_guard_active:
            self.depth_pid.reset_integral()
            self.yaw_pid.reset_integral()
            target_pitch = float(self.attitude_guard_recovery_target_pitch_rad)
            pitch_error = current_pitch - target_pitch
            elevator_cmd, pitch_sat = self.pitch_pid.compute(
                error=pitch_error,
                dt=dt,
                d_feedback=gyro_y,
                gain_scale=gain_scale,
                output_limit=np.deg2rad(self.fin_deg_max),
                integrate_enabled=False,
            )
            elevator_cmd = float(np.clip(elevator_cmd, -np.deg2rad(self.fin_deg_max), np.deg2rad(self.fin_deg_max)))
            yaw_err = 0.0
            rudder_cmd = 0.0
            yaw_sat = False
            speed_error = target_u - u_forward
            thrust_feedforward = 0.0
            thrust_feedback = 0.0
            thrust_cmd = float(np.clip(self.attitude_guard_recovery_thrust, self.thrust_min, self.thrust_max))
            thrust_sat = False
        else:
            depth_outer_raw, _ = self.depth_pid.compute(
                error=depth_error,
                dt=dt,
                d_feedback=0.0,
                gain_scale=1.0,
                output_limit=None,
                integrate_enabled=not low_speed,
            )

            target_pitch_raw = float(np.clip(depth_outer_raw, -self.target_pitch_limit_rad, self.target_pitch_limit_rad))
            max_pitch_delta = self.target_pitch_rate_limit * dt
            target_pitch = float(
                np.clip(
                    target_pitch_raw,
                    self.prev_target_pitch - max_pitch_delta,
                    self.prev_target_pitch + max_pitch_delta,
                )
            )
            self.prev_target_pitch = target_pitch

            pitch_error = current_pitch - target_pitch
            elevator_cmd, pitch_sat = self.pitch_pid.compute(
                error=pitch_error,
                dt=dt,
                d_feedback=gyro_y,
                gain_scale=gain_scale,
                output_limit=np.deg2rad(self.fin_deg_max),
                integrate_enabled=not low_speed,
            )
            elevator_cmd += self.feedforward_trim
            elevator_cmd = float(np.clip(elevator_cmd, -np.deg2rad(self.fin_deg_max), np.deg2rad(self.fin_deg_max)))

            yaw_err = wrap_angle(target_yaw - current_yaw)
            rudder_cmd, yaw_sat = self.yaw_pid.compute(
                error=yaw_err,
                dt=dt,
                d_feedback=gyro_z,
                gain_scale=gain_scale,
                output_limit=np.deg2rad(self.fin_deg_max),
                integrate_enabled=not low_speed,
            )

            speed_error = target_u - u_forward
            thrust_feedback, _ = self.speed_pid.compute(
                error=speed_error,
                dt=dt,
                d_feedback=0.0,
                gain_scale=1.0,
                output_limit=None,
                integrate_enabled=True,
            )

            thrust_feedforward = self.speed_ff_a * (target_u ** 2) + self.speed_ff_b * target_u + self.speed_ff_c
            thrust_cmd = thrust_feedforward + thrust_feedback
            thrust_sat = (thrust_cmd < self.thrust_min) or (thrust_cmd > self.thrust_max)
            thrust_cmd = float(np.clip(thrust_cmd, self.thrust_min, self.thrust_max))

        command = np.zeros(5, dtype=float)
        command[0] = -elevator_cmd
        command[2] = +elevator_cmd
        command[1] = -rudder_cmd
        command[3] = +rudder_cmd
        command[4] = thrust_cmd

        command[:4] = np.rad2deg(command[:4])
        command[:4] = np.clip(command[:4], -self.fin_deg_max, self.fin_deg_max)
        command[4] = np.clip(command[4], self.thrust_min, self.thrust_max)

        if low_speed:
            self.depth_pid.reset_integral()
            self.pitch_pid.reset_integral()
            self.yaw_pid.reset_integral()

        debug = {
            "attitude_guard_active": bool(attitude_guard_active),
            "current_roll_deg": float(np.rad2deg(current_roll)),
            "current_pitch_deg": float(np.rad2deg(current_pitch)),
            "gain_scale": gain_scale,
            "low_speed": low_speed,
            "depth_error": depth_error,
            "target_pitch_rad": target_pitch,
            "pitch_error": pitch_error,
            "yaw_error": yaw_err,
            "speed_error": speed_error,
            "thrust_feedforward": thrust_feedforward,
            "thrust_feedback": thrust_feedback,
            "pitch_saturated": bool(pitch_sat),
            "yaw_saturated": bool(yaw_sat),
            "thrust_saturated": bool(thrust_sat),
            "target_yaw": target_yaw,
            "target_depth": target_depth,
            "target_u": target_u,
        }

        return command, debug

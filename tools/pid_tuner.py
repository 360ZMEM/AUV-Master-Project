#!/usr/bin/env python3
"""PID 控制器自动调优脚本 v4。

使用 PVS 原生 remus100 仿真器，确保物理模型和符号约定完全正确。

核心方法:
  1. 基于 PVS remus100 完整动力学模型
  2. 将 AUVPIDController 输出映射到 PVS 的 [delta_r, delta_s, n] 格式
  3. 深度/航向分离调优
  4. RMSE 作为核心指标
"""

import sys
import time
from pathlib import Path

import numpy as np

def _resolve_project_root() -> Path:
    cur = Path(__file__).resolve()
    for parent in cur.parents:
        if (parent / "algorithm").exists():
            return parent
    raise RuntimeError("无法找到项目根目录")

sys.path.insert(0, str(_resolve_project_root()))
sys.path.insert(0, '/root/PythonVehicleSimulator/src')

from algorithm.auv_pid_controller import AUVPIDController
from python_vehicle_simulator.vehicles.remus100 import remus100


def _wrap(angle):
    return (angle + np.pi) % (2 * np.pi) - np.pi


class PVSAUVSim:
    """基于 PVS remus100 的完整 AUV 仿真器。
    
    使用 Fossen (2021) 的 NED 坐标系约定:
    - z 正 = 向下 (深度)
    - theta 正 = 船头上仰 => dz/dt = -u*sin(theta) < 0 => 上浮
    - theta 负 = 船头下俯 => dz/dt = -u*sin(theta) > 0 => 下潜
    """

    def __init__(self, dt=0.02):
        self.dt = dt
        self.vehicle = None
        self.eta = np.zeros(6, float)
        self.nu = np.zeros(6, float)
        self.u_actual = np.array([0, 0, 0], float)

    def reset(self, u_init=1.5):
        """初始化仿真器。
        
        Args:
            u_init: 初始前进速度 (m/s)
        """
        self.vehicle = remus100()
        self.eta = np.array([0, 0, 0, 0, 0, 0], float)
        self.nu = np.array([u_init, 0, 0, 0, 0, 0], float)
        self.u_actual = np.array([0, 0, 1525], float)

    def step(self, rudder_deg, stern_deg, thrust_pct):
        """推进仿真一步。

        Args:
            rudder_deg: 舵角指令 (deg), 正 = 右转 (yaw right)
            stern_deg: 尾翼指令 (deg), 正 = 上仰 (pitch up)
            thrust_pct: 推力百分比 (%), 0-100 对应 0-1525 RPM
        """
        dt = self.dt

        # 转换到 PVS 格式
        delta_r = np.deg2rad(np.clip(rudder_deg, -15, 15))
        delta_s = np.deg2rad(np.clip(stern_deg, -15, 15))
        n = np.clip(thrust_pct * 1525 / 100.0, 0, 1525)

        u_control = np.array([delta_r, delta_s, n], float)

        # PVS 动力学
        self.nu, self.u_actual = self.vehicle.dynamics(
            self.eta, self.nu, self.u_actual, u_control, dt
        )

        # 运动学 (Fossen 2021, Eq. 2.85)
        # eta_dot = J(eta) * nu
        phi, theta, psi = self.eta[3], self.eta[4], self.eta[5]
        u, v, w = self.nu[0], self.nu[1], self.nu[2]
        p, q, r = self.nu[3], self.nu[4], self.nu[5]

        cphi = np.cos(phi)
        sphi = np.sin(phi)
        ctheta = np.cos(theta)
        stheta = np.sin(theta)
        cpsi = np.cos(psi)
        spsi = np.sin(psi)

        J = np.array([
            [cpsi*ctheta, -spsi*cphi+cpsi*stheta*sphi, spsi*sphi+cpsi*cphi*stheta, 0, 0, 0],
            [spsi*ctheta, cpsi*cphi+spsi*stheta*sphi, -cpsi*sphi+spsi*ctheta*sphi, 0, 0, 0],
            [-stheta, ctheta*sphi, ctheta*cphi, 0, 0, 0],
            [0, 0, 0, 1, sphi*stheta/ctheta, cphi*stheta/ctheta],
            [0, 0, 0, 0, cphi, -sphi],
            [0, 0, 0, 0, sphi/ctheta, cphi/ctheta]
        ])

        eta_dot = J @ self.nu
        self.eta += dt * eta_dot

    def get_state(self):
        return {
            "x": self.eta[0],
            "y": self.eta[1],
            "depth": self.eta[2],  # z in NED (positive down)
            "roll": self.eta[3],
            "pitch": self.eta[4],
            "yaw": self.eta[5],
            "u": self.nu[0],
            "v": self.nu[1],
            "w": self.nu[2],
            "p": self.nu[3],
            "q": self.nu[4],
            "r": self.nu[5],
        }


def simulate_pid(ctrl, sim, duration, target_fn):
    """运行仿真并计算 RMSE。"""
    dt = sim.dt
    n_steps = int(duration / dt)
    yaw_errors = []
    depth_errors = []

    for step in range(n_steps):
        t = step * dt
        target = target_fn(t)
        state = sim.get_state()

        setpoint = {
            "target_depth": target["depth"],
            "target_yaw": target["yaw"],
            "target_u": target.get("u", 1.1),
            "dt": dt,
        }

        cmd, _ = ctrl.compute(state, setpoint)

        # PID output: [right_fin, top_fin, left_fin, bottom_fin, thrust]
        # 关键符号修正:
        #  - AUVPIDController约定: elevator_cmd正 = pitch正 = 下俯 = 下潜
        #  - PVS约定: delta_s正 = 上仰 = 上浮, delta_s负 = 下俯 = 下潜
        #  - 因此: stern_deg = -elevator_cmd 才能正确映射
        #  - PID: command[0] = -elevator_cmd (right_fin)
        #  - 所以: elevator_cmd = -command[0]
        #  - stern_deg = -elevator_cmd = command[0]
        #
        # 航向控制同理:
        #  - AUVPIDController约定: rudder_cmd正 = 右转
        #  - PVS约定: delta_r正 = 右转
        #  - PID: command[1] = -rudder_cmd (top_fin)
        #  - 所以: rudder_cmd = -command[1]
        stern_deg = cmd[0]  # = -elevator_cmd
        rudder_deg = -cmd[1]  # = rudder_cmd
        thrust_pct = cmd[4]

        sim.step(rudder_deg, stern_deg, thrust_pct)

        yaw_errors.append(abs(_wrap(state["yaw"] - target["yaw"])))
        depth_errors.append(abs(state["depth"] - target["depth"]))

    return {
        "yaw_rmse": float(np.sqrt(np.mean(np.array(yaw_errors) ** 2))),
        "depth_rmse": float(np.sqrt(np.mean(np.array(depth_errors) ** 2))),
        "yaw_max": float(np.max(yaw_errors)),
        "depth_max": float(np.max(depth_errors)),
    }


def tune_depth():
    """深度通道调优。"""
    print("\n" + "=" * 60)
    print("深度通道调优 (z=0 → z=5m 阶跃)")
    print("=" * 60)

    limits = {"fin_deg_max": 15.0, "thrust_min": 0.0, "thrust_max": 100.0}

    best_rmse = float("inf")
    best_params = None

    for kp_z in [0.1, 0.2, 0.5, 1.0]:
        for kp_t in [3.0, 5.0, 8.0, 12.0]:
            for kd_t in [1.0, 2.0, 3.0, 5.0]:
                cfg = {
                    "u0": 1.0, "u_min": 0.1, "target_u": 1.1,
                    "depth": {"kp": kp_z, "ki": 0.005, "kd": 0.0, "integral_limit": 50.0,
                              "target_pitch_deg_max": 15.0, "target_pitch_rate_limit_deg_s": 10.0},
                    "pitch": {"kp": kp_t, "ki": 0.3, "kd": kd_t, "integral_limit": 45.0},
                    "yaw": {"kp": 30.0, "ki": 1.0, "kd": 10.0, "integral_limit": 45.0},
                    "speed": {"kp": 5.0, "ki": 2.0, "kd": 1.0, "integral_limit": 30.0,
                              "feedforward": {"a": 0.0, "b": 0.0, "c": 0.0}},
                    "feedforward_trim_deg": 0.0, "anti_windup": True,
                }

                ctrl = AUVPIDController(cfg, limits)
                sim = PVSAUVSim(dt=0.02)  # 使用 PVS 默认步长
                sim.reset(u_init=1.5)

                def target(t):
                    return {"depth": 5.0 if t > 3.0 else 0.0, "yaw": 0.0, "u": 1.5}

                try:
                    r = simulate_pid(ctrl, sim, 40.0, target)
                except Exception:
                    continue

                if r["depth_rmse"] < best_rmse:
                    best_rmse = r["depth_rmse"]
                    best_params = {"kp_z": kp_z, "kp_t": kp_t, "kd_t": kd_t,
                                   "results": r}

    if best_params:
        print(f"  最佳: Kp_z={best_params['kp_z']}, Kp_theta={best_params['kp_t']}, "
              f"Kd_theta={best_params['kd_t']}")
        print(f"  深度 RMSE={best_params['results']['depth_rmse']:.3f}m, "
              f"最大误差={best_params['results']['depth_max']:.3f}m")
    else:
        print("  未找到可行参数")
    return best_params


def tune_yaw():
    """航向通道调优。"""
    print("\n" + "=" * 60)
    print("航向通道调优 (ψ=0 → ψ=30° 阶跃)")
    print("=" * 60)

    limits = {"fin_deg_max": 15.0, "thrust_min": 0.0, "thrust_max": 100.0}

    best_rmse = float("inf")
    best_params = None

    for kp_y in [10.0, 20.0, 30.0, 40.0, 50.0]:
        for ki_y in [0.5, 1.0, 2.0, 3.0, 5.0]:
            for kd_y in [5.0, 10.0, 15.0, 20.0]:
                cfg = {
                    "u0": 1.0, "u_min": 0.1, "target_u": 1.1,
                    "depth": {"kp": 0.5, "ki": 0.005, "kd": 0.0, "integral_limit": 50.0,
                              "target_pitch_deg_max": 15.0, "target_pitch_rate_limit_deg_s": 10.0},
                    "pitch": {"kp": 8.0, "ki": 0.3, "kd": 3.0, "integral_limit": 45.0},
                    "yaw": {"kp": kp_y, "ki": ki_y, "kd": kd_y, "integral_limit": 45.0},
                    "speed": {"kp": 5.0, "ki": 2.0, "kd": 1.0, "integral_limit": 30.0,
                              "feedforward": {"a": 0.0, "b": 0.0, "c": 0.0}},
                    "feedforward_trim_deg": 0.0, "anti_windup": True,
                }

                ctrl = AUVPIDController(cfg, limits)
                sim = PVSAUVSim(dt=0.02)
                sim.reset(u_init=1.5)

                def target(t):
                    return {"depth": 5.0, "yaw": np.deg2rad(30.0) if t > 3.0 else 0.0, "u": 1.5}

                try:
                    r = simulate_pid(ctrl, sim, 40.0, target)
                except Exception:
                    continue

                if r["yaw_rmse"] < best_rmse:
                    best_rmse = r["yaw_rmse"]
                    best_params = {"kp_y": kp_y, "ki_y": ki_y, "kd_y": kd_y,
                                   "results": r}

    if best_params:
        print(f"  最佳: Kp_yaw={best_params['kp_y']}, Ki_yaw={best_params['ki_y']}, "
              f"Kd_yaw={best_params['kd_y']}")
        print(f"  航向 RMSE={best_params['results']['yaw_rmse']:.4f}rad "
              f"({np.rad2deg(best_params['results']['yaw_rmse']):.2f}°), "
              f"最大误差={np.rad2deg(best_params['results']['yaw_max']):.2f}°")
    else:
        print("  未找到可行参数")
    return best_params


def evaluate_combined(depth_p, yaw_p):
    """评估最优参数在电缆跟踪轨迹上的表现。"""
    print("\n" + "=" * 60)
    print("电缆跟踪轨迹评估")
    print("=" * 60)

    limits = {"fin_deg_max": 15.0, "thrust_min": 0.0, "thrust_max": 100.0}

    kp_z = depth_p["kp_z"] if depth_p else 0.5
    kp_t = depth_p["kp_t"] if depth_p else 8.0
    kd_t = depth_p["kd_t"] if depth_p else 3.0
    kp_y = yaw_p["kp_y"] if yaw_p else 30.0
    ki_y = yaw_p["ki_y"] if yaw_p else 1.0
    kd_y = yaw_p["kd_y"] if yaw_p else 10.0

    cfg = {
        "u0": 1.0, "u_min": 0.1, "target_u": 1.1,
        "depth": {"kp": kp_z, "ki": 0.005, "kd": 0.0, "integral_limit": 50.0,
                  "target_pitch_deg_max": 15.0, "target_pitch_rate_limit_deg_s": 10.0},
        "pitch": {"kp": kp_t, "ki": 0.3, "kd": kd_t, "integral_limit": 45.0},
        "yaw": {"kp": kp_y, "ki": ki_y, "kd": kd_y, "integral_limit": 45.0},
        "speed": {"kp": 5.0, "ki": 2.0, "kd": 1.0, "integral_limit": 30.0,
                  "feedforward": {"a": 0.0, "b": 0.0, "c": 0.0}},
        "feedforward_trim_deg": 0.0, "anti_windup": True,
    }

    ctrl = AUVPIDController(cfg, limits)
    sim = PVSAUVSim(dt=0.02)
    sim.reset(u_init=1.5)

    def cable_target(t):
        x = 1.1 * t
        z = 5.0 + 0.5 * np.sin(0.05 * x)
        yaw = np.arctan2(2.0 * 0.12 * 1.1 * np.cos(0.12 * x), 1.1)
        return {"depth": z, "yaw": yaw, "u": 1.1}

    r = simulate_pid(ctrl, sim, 60.0, cable_target)
    print(f"  航向 RMSE: {r['yaw_rmse']:.4f} rad ({np.rad2deg(r['yaw_rmse']):.2f}°)")
    print(f"  深度 RMSE: {r['depth_rmse']:.3f} m")
    print(f"  航向最大误差: {np.rad2deg(r['yaw_max']):.2f}°")
    print(f"  深度最大误差: {r['depth_max']:.3f} m")
    return r


if __name__ == "__main__":
    print("PID 控制器自动调优 v4 (使用 PVS 原生 remus100)")
    depth_p = tune_depth()
    yaw_p = tune_yaw()
    evaluate_combined(depth_p, yaw_p)

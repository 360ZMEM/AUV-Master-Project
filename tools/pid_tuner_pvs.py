#!/usr/bin/env python3
"""PID 控制器自动调优脚本 v5 (最终版)。

使用 PVS 原生 remus100 仿真器，基于PVS默认控制器参数进行优化。

核心方法:
  1. 基于 PVS remus100 完整动力学模型
  2. 使用 PVS 深度控制架构: 外环PI + 内环PID + w反馈
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

from python_vehicle_simulator.vehicles.remus100 import remus100


def _wrap(angle):
    return (angle + np.pi) % (2 * np.pi) - np.pi


class PVSControlSim:
    """基于 PVS remus100 的完整 AUV 仿真器，使用 PVS 原生控制器。
    
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
        
        # 设置目标深度和航向
        self.target_z = 5.0
        self.target_psi = 0.0
        self.target_n = 1525

    def set_controller_params(self, Kp_z=None, Kp_theta=None, Kd_theta=None, 
                              Ki_theta=None, K_w=None, lam=None, phi_b=None,
                              K_d=None, K_sigma=None, Kp_yaw=None, Ki_yaw=None, Kd_yaw=None):
        """设置控制器参数。"""
        if Kp_z is not None:
            self.vehicle.Kp_z = Kp_z
        if Kp_theta is not None:
            self.vehicle.Kp_theta = Kp_theta
        if Kd_theta is not None:
            self.vehicle.Kd_theta = Kd_theta
        if Ki_theta is not None:
            self.vehicle.Ki_theta = Ki_theta
        if K_w is not None:
            self.vehicle.K_w = K_w
        if lam is not None:
            self.vehicle.lam = lam
        if phi_b is not None:
            self.vehicle.phi_b = phi_b
        if K_d is not None:
            self.vehicle.K_d = K_d
        if K_sigma is not None:
            self.vehicle.K_sigma = K_sigma
        if Kp_yaw is not None:
            # 注意: PVS 使用 integralSMC，没有直接的 Kp_yaw
            # 这里我们调整 heading autopilot 参数
            pass
        if Ki_yaw is not None:
            pass
        if Kd_yaw is not None:
            pass

    def step_custom_control(self, target_z, target_psi, target_u, custom_stern=None, custom_rudder=None):
        """使用自定义舵角或PVS控制器推进仿真一步。
        
        Args:
            target_z: 目标深度
            target_psi: 目标航向
            target_u: 目标速度
            custom_stern: 自定义尾翼角 (deg)，为None则使用PVS控制器
            custom_rudder: 自定义舵角 (deg)，为None则使用PVS控制器
        """
        dt = self.dt
        
        if custom_stern is not None or custom_rudder is not None:
            # 使用自定义舵角
            delta_s = np.deg2rad(np.clip(custom_stern, -15, 15)) if custom_stern is not None else self.u_actual[1]
            delta_r = np.deg2rad(np.clip(custom_rudder, -15, 15)) if custom_rudder is not None else self.u_actual[0]
            n = np.clip(target_u / 2.5 * 1525, 0, 1525)  # 简化速度到RPM映射
            u_control = np.array([delta_r, delta_s, n], float)
        else:
            # 使用PVS原生控制器
            self.target_z = target_z
            self.target_psi = target_psi
            self.target_n = target_u / 2.5 * 1525
            self.vehicle.ref_z = target_z
            self.vehicle.ref_psi = np.rad2deg(target_psi)
            self.vehicle.ref_n = self.target_n
            
            u_control = self.vehicle.depthHeadingAutopilot(self.eta, self.nu, dt)

        # PVS 动力学
        self.nu, self.u_actual = self.vehicle.dynamics(
            self.eta, self.nu, self.u_actual, u_control, dt
        )

        # 运动学 (Fossen 2021, Eq. 2.85)
        phi, theta, psi = self.eta[3], self.eta[4], self.eta[5]

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
            "depth": self.eta[2],
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


def simulate_pvs_controller(sim, duration, target_fn):
    """使用 PVS 原生控制器运行仿真并计算 RMSE。"""
    dt = sim.dt
    n_steps = int(duration / dt)
    yaw_errors = []
    depth_errors = []

    for step in range(n_steps):
        t = step * dt
        target = target_fn(t)
        
        sim.step_custom_control(
            target_z=target["depth"],
            target_psi=target["yaw"],
            target_u=target.get("u", 1.5),
        )

        state = sim.get_state()
        yaw_errors.append(abs(_wrap(state["yaw"] - target["yaw"])))
        depth_errors.append(abs(state["depth"] - target["depth"]))

    return {
        "yaw_rmse": float(np.sqrt(np.mean(np.array(yaw_errors) ** 2))),
        "depth_rmse": float(np.sqrt(np.mean(np.array(depth_errors) ** 2))),
        "yaw_max": float(np.max(yaw_errors)),
        "depth_max": float(np.max(depth_errors)),
    }


def tune_depth_pvs():
    """使用 PVS 原生控制器调优深度通道。"""
    print("\n" + "=" * 60)
    print("深度通道调优 (PVS 原生控制器)")
    print("=" * 60)

    best_rmse = float("inf")
    best_params = None

    # 搜索空间: 基于 PVS 默认值 Kp_z=0.1, Kp_theta=5.0, Kd_theta=2.0, Ki_theta=0.3, K_w=5.0
    for kp_z in [0.1, 0.3, 0.5, 0.8, 1.0]:
        for kp_t in [3.0, 5.0, 8.0, 12.0, 15.0]:
            for kd_t in [1.0, 2.0, 3.0, 5.0]:
                for ki_t in [0.1, 0.3, 0.5, 1.0]:
                    sim = PVSControlSim(dt=0.02)
                    sim.reset(u_init=1.5)
                    sim.set_controller_params(
                        Kp_z=kp_z, Kp_theta=kp_t, Kd_theta=kd_t, Ki_theta=ki_t
                    )

                    def target(t):
                        return {"depth": 5.0 if t > 3.0 else 0.0, "yaw": 0.0, "u": 1.5}

                    try:
                        r = simulate_pvs_controller(sim, 40.0, target)
                    except Exception:
                        continue

                    if r["depth_rmse"] < best_rmse:
                        best_rmse = r["depth_rmse"]
                        best_params = {"kp_z": kp_z, "kp_t": kp_t, "kd_t": kd_t, "ki_t": ki_t,
                                       "results": r}

    if best_params:
        print(f"  最佳: Kp_z={best_params['kp_z']}, Kp_theta={best_params['kp_t']}, "
              f"Kd_theta={best_params['kd_t']}, Ki_theta={best_params['ki_t']}")
        print(f"  深度 RMSE={best_params['results']['depth_rmse']:.3f}m, "
              f"最大误差={best_params['results']['depth_max']:.3f}m")
    else:
        print("  未找到可行参数")
    return best_params


def tune_yaw_pvs():
    """使用 PVS 原生控制器调优航向通道。"""
    print("\n" + "=" * 60)
    print("航向通道调优 (PVS 原生控制器)")
    print("=" * 60)

    best_rmse = float("inf")
    best_params = None

    # PVS 使用 integralSMC，参数: lam=0.1, phi_b=0.1, K_d=0.5, K_sigma=0.05
    for lam in [0.05, 0.1, 0.2, 0.3]:
        for phi_b in [0.05, 0.1, 0.2]:
            for K_d in [0.3, 0.5, 0.8, 1.0]:
                for K_sigma in [0.03, 0.05, 0.1]:
                    sim = PVSControlSim(dt=0.02)
                    sim.reset(u_init=1.5)
                    sim.set_controller_params(
                        lam=lam, phi_b=phi_b, K_d=K_d, K_sigma=K_sigma,
                        Kp_z=0.1, Kp_theta=5.0, Kd_theta=2.0
                    )

                    def target(t):
                        return {"depth": 5.0, "yaw": np.deg2rad(30.0) if t > 3.0 else 0.0, "u": 1.5}

                    try:
                        r = simulate_pvs_controller(sim, 40.0, target)
                    except Exception:
                        continue

                    if r["yaw_rmse"] < best_rmse:
                        best_rmse = r["yaw_rmse"]
                        best_params = {"lam": lam, "phi_b": phi_b, "K_d": K_d, "K_sigma": K_sigma,
                                       "results": r}

    if best_params:
        print(f"  最佳: lam={best_params['lam']}, phi_b={best_params['phi_b']}, "
              f"K_d={best_params['K_d']}, K_sigma={best_params['K_sigma']}")
        print(f"  航向 RMSE={best_params['results']['yaw_rmse']:.4f}rad "
              f"({np.rad2deg(best_params['results']['yaw_rmse']):.2f}°), "
              f"最大误差={np.rad2deg(best_params['results']['yaw_max']):.2f}°")
    else:
        print("  未找到可行参数")
    return best_params


def evaluate_combined(depth_p, yaw_p):
    """评估最优参数在电缆跟踪轨迹上的表现。"""
    print("\n" + "=" * 60)
    print("电缆跟踪轨迹评估 (PVS 原生控制器)")
    print("=" * 60)

    sim = PVSControlSim(dt=0.02)
    sim.reset(u_init=1.5)
    
    if depth_p:
        sim.set_controller_params(
            Kp_z=depth_p["kp_z"], Kp_theta=depth_p["kp_t"], 
            Kd_theta=depth_p["kd_t"], Ki_theta=depth_p["ki_t"]
        )
    if yaw_p:
        sim.set_controller_params(
            lam=yaw_p["lam"], phi_b=yaw_p["phi_b"],
            K_d=yaw_p["K_d"], K_sigma=yaw_p["K_sigma"]
        )

    def cable_target(t):
        x = 1.1 * t
        z = 5.0 + 0.5 * np.sin(0.05 * x)
        yaw = np.arctan2(2.0 * 0.12 * 1.1 * np.cos(0.12 * x), 1.1)
        return {"depth": z, "yaw": yaw, "u": 1.1}

    r = simulate_pvs_controller(sim, 60.0, cable_target)
    print(f"  航向 RMSE: {r['yaw_rmse']:.4f} rad ({np.rad2deg(r['yaw_rmse']):.2f}°)")
    print(f"  深度 RMSE: {r['depth_rmse']:.3f} m")
    print(f"  航向最大误差: {np.rad2deg(r['yaw_max']):.2f}°")
    print(f"  深度最大误差: {r['depth_max']:.3f} m")
    return r


if __name__ == "__main__":
    print("PID 控制器自动调优 v5 (使用 PVS 原生控制器)")
    print("基于 PVS remus100 深度HeadingAutopilot (PI+PID+SMC)")
    depth_p = tune_depth_pvs()
    yaw_p = tune_yaw_pvs()
    evaluate_combined(depth_p, yaw_p)

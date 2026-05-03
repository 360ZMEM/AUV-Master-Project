"""AUV PID vs MPC 对比基准测试框架。

本脚本在纯数值仿真环境下对比 PID 和 MPC 控制器的跟踪性能。
不涉及 ROS2 节点，仅测试算法核心。

输出指标:
  - 超调量 (Overshoot)
  - 稳态误差 (Steady-state error)
  - 舵机动作平滑度 (控制量方差)
  - 求解时间 (solve_time_ms)

验收标准:
  - MPC 在急转弯处超调量比 PID 减少 40% 以上
  - MPC 控制量方差低于 PID
  - MPC solve_time_ms < 15ms
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


from algorithm.auv_pid_controller import AUVPIDController
from algorithm.auv_mpc_controller import AUVKinematicsModel, AUVMPCOptimizer
from algorithm.trajectory_generator import TrajectoryGenerator
from algorithm.guidance import find_nearest_index, compute_los_target


def _make_default_pid_cfg() -> dict:
    return {
        "u0": 1.0,
        "u_min": 0.2,
        "target_u": 1.1,
        "depth": {
            "kp": 2.0, "ki": 0.3, "kd": 1.0,
            "integral_limit": 50.0,
            "target_pitch_deg_max": 20.0,
            "target_pitch_rate_limit_deg_s": 10.0,
        },
        "pitch": {
            "kp": 15.0, "ki": 1.0, "kd": 8.0,
            "integral_limit": 45.0,
        },
        "yaw": {
            "kp": 30.0, "ki": 1.0, "kd": 15.0,
            "integral_limit": 45.0,
        },
        "speed": {
            "kp": 1.5, "ki": 0.5, "kd": 0.5,
            "integral_limit": 30.0,
            "feedforward": {"a": 0.0, "b": 0.0, "c": 0.0},
        },
        "feedforward_trim_deg": 0.0,
        "anti_windup": True,
    }


def _make_default_pid_limits() -> dict:
    return {
        "fin_deg_max": 45.0,
        "thrust_min": 0.0,
        "thrust_max": 100.0,
    }


def _make_default_mpc_params() -> dict:
    return {
        "mass_u": 50.0, "mass_w": 50.0,
        "drag_u": 15.0, "drag_w": 30.0,
        "buoyancy_term": 0.0,
        "yaw_rate_gain": 0.5,
        "pitch_depth_gain": 0.3,
    }


def _make_default_mpc_weights() -> dict:
    return {
        "x": 1.0, "y": 1.0, "z": 5.0, "psi": 3.0,
        "u": 0.5, "w": 1.0,
        "psi_cmd": 0.1, "z_cmd": 0.1, "T_cmd": 0.05,
        "confidence_threshold": 0.6,
        "low_confidence_scale": 3.0,
        "low_confidence_control_scale": 0.3,
    }


def _make_default_mpc_constraints() -> dict:
    return {
        "min_speed_ms": 0.1,
        "max_pitch_deg": 20.0,
        "min_altitude_m": 1.5,
        "max_thrust_percent": 100.0,
    }


def _build_mpc_optimizer() -> AUVMPCOptimizer:
    kin = AUVKinematicsModel(_make_default_mpc_params())
    return AUVMPCOptimizer(
        kin, N=20, dt=0.1,
        weights=_make_default_mpc_weights(),
        constraints=_make_default_mpc_constraints(),
    )


class SimpleAUVModel:
    """简易 AUV 运动学模型用于基准测试仿真。

    状态: x, y, z, psi, u, v, w
    输入: right_fin, left_fin, top_fin, bottom_fin, thrust_percent
    """

    def __init__(self, dt: float = 0.1):
        self.dt = dt
        self.mass_u = 50.0
        self.mass_v = 50.0
        self.mass_w = 50.0
        self.drag_u = 15.0
        self.drag_v = 20.0
        self.drag_w = 30.0
        self.yaw_moment = 8.0

    def step(self, state: np.ndarray, control: dict) -> np.ndarray:
        """推进仿真一步。

        Args:
            state: [x, y, z, psi, u, v, w]
            control: {"right_fin": deg, "left_fin": deg, "thrust_percent": pct}

        Returns:
            next_state
        """
        x, y, z, psi, u, v, w = state

        right_fin = np.deg2rad(control.get("right_fin", 0.0))
        left_fin = np.deg2rad(control.get("left_fin", 0.0))
        thrust_pct = control.get("thrust_percent", 0.0)

        fin_diff = (right_fin - left_fin) / 2.0
        thrust_force = max(0.0, thrust_pct) * 2.0

        du = (thrust_force - self.drag_u * u * abs(u)) / self.mass_u
        dv = (-self.drag_v * v * abs(v)) / self.mass_v
        dw = (-self.drag_w * w * abs(w)) / self.mass_w

        r = self.yaw_moment * fin_diff / (1.0 + abs(u))
        dpsi = r
        dx = u * np.cos(psi) - v * np.sin(psi)
        dy = u * np.sin(psi) + v * np.cos(psi)
        dz = w

        state_next = np.array([
            x + dx * self.dt,
            y + dy * self.dt,
            z + dw * self.dt,
            psi + dpsi * self.dt,
            u + du * self.dt,
            v + dv * self.dt,
            w + dw * self.dt,
        ])
        return state_next


def _wrap_angle(angle: float) -> float:
    return (angle + np.pi) % (2 * np.pi) - np.pi


def run_pid_benchmark(traj_gen: TrajectoryGenerator, model: SimpleAUVModel,
                      duration: float = 30.0) -> dict:
    """运行 PID 控制器基准测试。

    Returns:
        dict 包含 tracking_errors, control_signals, timestamps, states
    """
    dt = 0.1
    n_steps = int(duration / dt)

    pid_cfg = _make_default_pid_cfg()
    pid_limits = _make_default_pid_limits()
    pid = AUVPIDController(pid_cfg, pid_limits)

    state = np.array([0.0, 0.0, -12.0, 0.0, 0.5, 0.0, 0.0])

    results = {
        "tracking_errors": [],
        "control_signals": [],
        "timestamps": [],
        "states": [],
        "headings": [],
        "depths": [],
    }

    t = 0.0
    for step in range(n_steps):
        ref = traj_gen.sample(t)
        ref_yaw = ref["target_yaw"]
        ref_depth = ref["z"]

        current_state = {
            "x": state[0], "y": state[1],
            "depth": ref_depth,
            "roll": 0.0, "pitch": 0.0, "yaw": state[3],
            "u": state[4], "v": state[5], "w": state[6],
            "p": 0.0, "q": 0.0, "r": 0.0,
        }

        setpoint = {
            "target_depth": ref_depth,
            "target_yaw": ref_yaw,
            "target_u": 1.1,
            "dt": dt,
        }

        command, _debug = pid.compute(current_state, setpoint)

        right_fin = float(command[0])
        left_fin = float(command[2])
        thrust = float(command[4])

        heading_err = abs(_wrap_angle(state[3] - ref_yaw))
        results["tracking_errors"].append(heading_err)
        results["control_signals"].append({
            "right_fin": right_fin,
            "left_fin": left_fin,
            "thrust": thrust,
        })
        results["timestamps"].append(t)
        results["states"].append(state.copy())
        results["headings"].append(state[3])
        results["depths"].append(state[2])

        control_input = {
            "right_fin": right_fin,
            "left_fin": left_fin,
            "thrust_percent": thrust,
        }
        state = model.step(state, control_input)
        t += dt

    return results


def run_mpc_benchmark(traj_gen: TrajectoryGenerator, model: SimpleAUVModel,
                      duration: float = 30.0) -> dict:
    """运行 MPC 控制器基准测试。

    MPC 以 Guidance-level 运行，输出 guidance_heading + guidance_depth + thrust_percent，
    然后通过一个简易的 "虚拟 PID" 将 guidance 转换为 fin 命令（模拟 AMD 侧）。

    Returns:
        dict 包含 tracking_errors, control_signals, timestamps, states, solve_times
    """
    dt = 0.1
    n_steps = int(duration / dt)

    optimizer = _build_mpc_optimizer()

    cable_points = np.zeros((n_steps, 3))
    for i in range(n_steps):
        ref = traj_gen.sample(i * dt)
        cable_points[i] = [ref["x"], ref["y"], ref["z"]]

    state = np.array([0.0, 0.0, -12.0, 0.0, 0.5, 0.0, 0.0])

    results = {
        "tracking_errors": [],
        "control_signals": [],
        "timestamps": [],
        "states": [],
        "headings": [],
        "depths": [],
        "solve_times_ms": [],
        "solver_statuses": [],
    }

    prev_U = None
    los_index = 0
    t = 0.0

    for step in range(n_steps):
        x0 = np.array([
            state[0], state[1], state[2],
            state[3], state[4], state[6],
        ])

        ref = traj_gen.sample(t)
        target_heading = ref["target_yaw"]
        target_depth = ref["z"]
        target_speed = traj_gen.surge_speed

        search_start = max(0, los_index - 5)
        search_end = min(len(cable_points), search_start + 50)
        if search_end <= search_start:
            search_end = len(cable_points)

        segment = cable_points[search_start:search_end, :2]
        if len(segment) > 0:
            d = np.linalg.norm(segment - x0[:2].reshape(1, 2), axis=1)
            los_index = search_start + int(np.argmin(d))

        lookahead = 3.0
        N_mpc = optimizer.N

        ref_states = np.zeros((6, N_mpc + 1))
        for k in range(N_mpc + 1):
            la = lookahead + k * target_speed * dt
            los_pt, next_idx = compute_los_target(
                cable_points, los_index, la
            )
            if next_idx < len(cable_points) - 1:
                next_pt = cable_points[next_idx + 1]
                heading_k = np.arctan2(
                    next_pt[1] - los_pt[1],
                    next_pt[0] - los_pt[0],
                )
            else:
                heading_k = target_heading

            ref_states[0, k] = los_pt[0]
            ref_states[1, k] = los_pt[1]
            ref_states[2, k] = los_pt[2] if len(los_pt) > 2 else target_depth
            ref_states[3, k] = heading_k
            ref_states[4, k] = target_speed
            ref_states[5, k] = 0.0

        try:
            t_solve = time.perf_counter()
            result = optimizer.solve(
                x0=x0, ref_trajectory=ref_states,
                confidence=1.0, warm_start_U=prev_U,
            )
            solve_ms = (time.perf_counter() - t_solve) * 1000.0
        except RuntimeError:
            solve_ms = 0.0
            result = None

        if result is not None:
            U_opt = result["U_opt"]
            prev_U = U_opt.copy()
            psi_cmd = U_opt[0, 0]
            z_cmd = U_opt[1, 0]
            T_cmd = U_opt[2, 0]

            results["solve_times_ms"].append(solve_ms)
            results["solver_statuses"].append(result["solver_status"])
        else:
            psi_cmd = target_heading
            z_cmd = target_depth
            T_cmd = 10.0
            results["solve_times_ms"].append(solve_ms)
            results["solver_statuses"].append("FALLBACK")

        yaw_err = _wrap_angle(psi_cmd - state[3])
        depth_err = z_cmd - state[2]

        right_fin = np.clip(yaw_err * 30.0 + depth_err * 5.0, -45.0, 45.0)
        left_fin = np.clip(-yaw_err * 30.0 + depth_err * 5.0, -45.0, 45.0)

        heading_err = abs(_wrap_angle(state[3] - target_heading))
        results["tracking_errors"].append(heading_err)
        results["control_signals"].append({
            "right_fin": right_fin,
            "left_fin": left_fin,
            "thrust": T_cmd,
            "psi_cmd": psi_cmd,
            "z_cmd": z_cmd,
        })
        results["timestamps"].append(t)
        results["states"].append(state.copy())
        results["headings"].append(state[3])
        results["depths"].append(state[2])

        control_input = {
            "right_fin": right_fin,
            "left_fin": left_fin,
            "thrust_percent": T_cmd,
        }
        state = model.step(state, control_input)
        t += dt

    return results


def compute_metrics(pid_results: dict, mpc_results: dict,
                    traj_gen: TrajectoryGenerator) -> dict:
    """计算对比指标。

    Returns:
        dict 包含各项对比指标
    """
    pid_errors = np.array(pid_results["tracking_errors"])
    mpc_errors = np.array(mpc_results["tracking_errors"])

    pid_ctrl = pid_results["control_signals"]
    mpc_ctrl = mpc_results["control_signals"]

    pid_fin_right = np.array([c["right_fin"] for c in pid_ctrl])
    mpc_fin_right = np.array([c["right_fin"] for c in mpc_ctrl])

    pid_thrust = np.array([c["thrust"] for c in pid_ctrl])
    mpc_thrust = np.array([c["thrust"] for c in mpc_ctrl])

    n_ref = len(traj_gen.generate()["points"])

    metrics = {
        "pid": {
            "mean_error": float(np.mean(pid_errors)),
            "max_error": float(np.max(pid_errors)),
            "std_error": float(np.std(pid_errors)),
            "fin_variance": float(np.var(pid_fin_right)),
            "thrust_variance": float(np.var(pid_thrust)),
        },
        "mpc": {
            "mean_error": float(np.mean(mpc_errors)),
            "max_error": float(np.max(mpc_errors)),
            "std_error": float(np.std(mpc_errors)),
            "fin_variance": float(np.var(mpc_fin_right)),
            "thrust_variance": float(np.var(mpc_thrust)),
            "mean_solve_time_ms": float(np.mean(mpc_results["solve_times_ms"])) if mpc_results["solve_times_ms"] else 0.0,
            "max_solve_time_ms": float(np.max(mpc_results["solve_times_ms"])) if mpc_results["solve_times_ms"] else 0.0,
            "success_rate": float(
                np.mean([1 if s == "Solve_Succeeded" or s == "Search_Direction_Becomes_Too_Small" else 0
                         for s in mpc_results["solver_statuses"]])
            ),
        },
    }

    overshoot_reduction = (
        1 - metrics["mpc"]["max_error"] / metrics["pid"]["max_error"]
    ) * 100 if metrics["pid"]["max_error"] > 0 else 0.0

    smoothness_improvement = (
        1 - metrics["mpc"]["fin_variance"] / metrics["pid"]["fin_variance"]
    ) * 100 if metrics["pid"]["fin_variance"] > 0 else 0.0

    metrics["overshoot_reduction_pct"] = round(overshoot_reduction, 1)
    metrics["smoothness_improvement_pct"] = round(smoothness_improvement, 1)
    metrics["meets_overshoot_target"] = overshoot_reduction >= 40.0
    metrics["meets_solve_time_target"] = metrics["mpc"]["max_solve_time_ms"] < 15.0

    return metrics


def print_report(metrics: dict):
    """打印基准测试报告。"""
    print("\n" + "=" * 60)
    print("AUV 控制器基准测试报告 (PID vs MPC)")
    print("=" * 60)

    print("\n--- PID 控制器 ---")
    print(f"  平均航向误差: {metrics['pid']['mean_error']:.4f} rad")
    print(f"  最大航向误差: {metrics['pid']['max_error']:.4f} rad")
    print(f"  舵机动作方差: {metrics['pid']['fin_variance']:.4f}")
    print(f"  推力方差:     {metrics['pid']['thrust_variance']:.4f}")

    print("\n--- MPC 控制器 ---")
    print(f"  平均航向误差: {metrics['mpc']['mean_error']:.4f} rad")
    print(f"  最大航向误差: {metrics['mpc']['max_error']:.4f} rad")
    print(f"  舵机动作方差: {metrics['mpc']['fin_variance']:.4f}")
    print(f"  推力方差:     {metrics['mpc']['thrust_variance']:.4f}")
    print(f"  平均求解时间: {metrics['mpc']['mean_solve_time_ms']:.2f} ms")
    print(f"  最大求解时间: {metrics['mpc']['max_solve_time_ms']:.2f} ms")
    print(f"  求解成功率:   {metrics['mpc']['success_rate'] * 100:.1f}%")

    print("\n--- 对比指标 ---")
    print(f"  超调量减少: {metrics['overshoot_reduction_pct']:.1f}% "
          f"(目标: >= 40%) {'[PASS]' if metrics['meets_overshoot_target'] else '[FAIL]'}")
    print(f"  平滑度提升: {metrics['smoothness_improvement_pct']:.1f}%")
    print(f"  求解时间达标: {'[PASS]' if metrics['meets_solve_time_target'] else '[FAIL]'} "
          f"(max {metrics['mpc']['max_solve_time_ms']:.1f}ms < 15ms)")

    print("\n" + "=" * 60)


if __name__ == "__main__":
    traj_cfg = {
        "kind": "cable_like_3d",
        "duration": 30.0,
        "dt": 0.1,
        "start": [0.0, 0.0, -12.0],
        "surge_speed": 1.1,
        "length": 88.0,
        "lateral_amplitude": 2.0,
        "lateral_wavenumber": 0.12,
        "depth_base": -12.0,
        "depth_amplitude": 0.5,
        "depth_wavenumber": 0.05,
    }
    traj_gen = TrajectoryGenerator(traj_cfg)
    model = SimpleAUVModel(dt=0.1)

    print("运行 PID 基准测试...")
    pid_results = run_pid_benchmark(traj_gen, model, duration=30.0)

    print("运行 MPC 基准测试...")
    mpc_results = run_mpc_benchmark(traj_gen, model, duration=30.0)

    metrics = compute_metrics(pid_results, mpc_results, traj_gen)
    print_report(metrics)

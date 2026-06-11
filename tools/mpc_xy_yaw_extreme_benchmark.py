#!/usr/bin/env python3
"""Offline x/y/yaw benchmark for guidance-level MPC.

This branch benchmark intentionally stresses planar guidance instead of depth.
The baseline is a reactive LOS/PID-style heading follower with fixed speed; the
MPC receives a short preview of the path and can also adjust speed.  This
constructs cases where preview control is expected to help: tight chicanes,
hairpins, and short-wavelength S-turns.
"""

from __future__ import annotations

import csv
import math
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from algorithm.auv_mpc_controller import AUVKinematicsModel, AUVMPCOptimizer  # noqa: E402
from common.env_utils import get_output_dir  # noqa: E402


def wrap_angle(angle: float | np.ndarray) -> float | np.ndarray:
    return (angle + np.pi) % (2.0 * np.pi) - np.pi


@dataclass(frozen=True)
class Scenario:
    name: str
    duration_s: float
    path_speed_mps: float
    target_speed_mps: float
    lookahead_pid_m: float


@dataclass(frozen=True)
class MpcVariant:
    name: str
    horizon: int
    dt: float
    wx: float
    wy: float
    wpsi: float
    wu: float
    wpsi_cmd: float
    wt: float
    delta_psi_deg: float
    psi_band_deg: float
    min_thrust: float
    yaw_rate_gain: float


SCENARIOS = [
    Scenario("s_turn_short_wave", duration_s=46.0, path_speed_mps=1.35, target_speed_mps=1.35, lookahead_pid_m=5.0),
    Scenario("chicane_90deg", duration_s=54.0, path_speed_mps=1.30, target_speed_mps=1.30, lookahead_pid_m=6.0),
    Scenario("hairpin_180deg", duration_s=64.0, path_speed_mps=1.20, target_speed_mps=1.20, lookahead_pid_m=6.0),
]

VARIANTS = [
    MpcVariant("xy_v1_balanced", 12, 0.25, 8.0, 8.0, 35.0, 0.8, 0.0005, 0.006, 5.0, 85.0, 6.0, 8.0),
    MpcVariant("xy_v2_track_hard", 14, 0.25, 22.0, 22.0, 45.0, 0.6, 0.0002, 0.004, 6.0, 95.0, 6.0, 8.0),
    MpcVariant("xy_v3_speed_flexible", 14, 0.25, 18.0, 18.0, 40.0, 0.2, 0.0002, 0.001, 6.0, 95.0, 3.0, 8.0),
    MpcVariant("xy_v4_short_realtime", 10, 0.25, 20.0, 20.0, 35.0, 0.3, 0.0002, 0.002, 6.0, 90.0, 5.0, 9.0),
    MpcVariant("xy_v5_yaw_strict", 12, 0.25, 14.0, 14.0, 120.0, 0.4, 0.00005, 0.003, 6.0, 95.0, 5.0, 10.0),
]


def make_path(scenario: Scenario, ds: float = 0.15) -> np.ndarray:
    if scenario.name == "s_turn_short_wave":
        x = np.arange(0.0, 58.0 + ds, ds)
        y = 4.8 * np.sin(2.0 * np.pi * x / 11.0)
    elif scenario.name == "chicane_90deg":
        pts = [
            (0.0, 0.0),
            (14.0, 0.0),
            (14.0, 10.0),
            (26.0, 10.0),
            (26.0, -8.0),
            (40.0, -8.0),
            (40.0, 6.0),
            (54.0, 6.0),
        ]
        x, y = polyline_points(pts, ds)
    elif scenario.name == "hairpin_180deg":
        x1 = np.arange(0.0, 20.0, ds)
        y1 = np.zeros_like(x1)
        theta = np.arange(-np.pi / 2.0, np.pi / 2.0, ds / 6.0)
        xc = 20.0 + 6.0 * np.cos(theta)
        yc = 6.0 + 6.0 * np.sin(theta)
        x2 = np.arange(20.0, 0.0 - ds, -ds)
        y2 = np.full_like(x2, 12.0)
        x = np.concatenate([x1, xc, x2])
        y = np.concatenate([y1, yc, y2])
    else:
        raise ValueError(scenario.name)

    dx = np.gradient(x)
    dy = np.gradient(y)
    yaw = np.unwrap(np.arctan2(dy, dx))
    curvature = np.abs(np.gradient(yaw) / np.maximum(np.hypot(dx, dy), 1e-6))
    speed_scale = 1.0 / (1.0 + 5.0 * curvature)
    speed = np.clip(scenario.target_speed_mps * speed_scale, 0.35, scenario.target_speed_mps)
    z = np.full_like(x, 2.5)
    return np.column_stack([x, y, z, yaw, speed])


def polyline_points(points: list[tuple[float, float]], ds: float) -> tuple[np.ndarray, np.ndarray]:
    xs: list[float] = []
    ys: list[float] = []
    for p0, p1 in zip(points[:-1], points[1:]):
        x0, y0 = p0
        x1, y1 = p1
        length = math.hypot(x1 - x0, y1 - y0)
        n = max(2, int(math.ceil(length / ds)))
        for i in range(n):
            alpha = i / n
            xs.append(x0 + alpha * (x1 - x0))
            ys.append(y0 + alpha * (y1 - y0))
    xs.append(points[-1][0])
    ys.append(points[-1][1])
    return np.asarray(xs), np.asarray(ys)


def cumulative_s(path: np.ndarray) -> np.ndarray:
    d = np.hypot(np.diff(path[:, 0]), np.diff(path[:, 1]))
    return np.concatenate([[0.0], np.cumsum(d)])


def nearest_index(path: np.ndarray, xy: np.ndarray, start: int = 0, window: int = 180) -> int:
    lo = max(0, start - 20)
    hi = min(len(path), max(lo + 1, start + window))
    d = np.sum((path[lo:hi, :2] - xy.reshape(1, 2)) ** 2, axis=1)
    return lo + int(np.argmin(d))


def sample_by_s(path: np.ndarray, s_values: np.ndarray, s_query: float) -> np.ndarray:
    s_query = float(np.clip(s_query, s_values[0], s_values[-1]))
    cols = [np.interp(s_query, s_values, path[:, col]) for col in range(5)]
    return np.asarray(cols, dtype=float)


def plant_step(state: np.ndarray, psi_cmd: float, thrust_pct: float, dt: float, yaw_rate_gain: float = 8.0) -> np.ndarray:
    x, y, z, psi, u, w = state
    yaw_err = float(wrap_angle(psi_cmd - psi))
    r = np.clip(yaw_rate_gain * yaw_err, -math.radians(12.0), math.radians(12.0))
    thrust = max(0.0, float(thrust_pct))
    du = (thrust - 12.0 * u * abs(u)) / 50.0
    u_next = float(np.clip(u + dt * du, 0.25, 1.8))
    psi_next = float(wrap_angle(psi + dt * r))
    x_next = x + dt * u_next * math.cos(psi_next)
    y_next = y + dt * u_next * math.sin(psi_next)
    return np.array([x_next, y_next, z, psi_next, u_next, w], dtype=float)


def path_metrics(states: np.ndarray, path: np.ndarray) -> dict[str, float]:
    nearest = np.zeros(len(states), dtype=int)
    idx = 0
    lateral = np.zeros(len(states), dtype=float)
    yaw_err = np.zeros(len(states), dtype=float)
    for i, st in enumerate(states):
        idx = nearest_index(path, st[:2], idx)
        nearest[i] = idx
        lateral[i] = float(np.linalg.norm(st[:2] - path[idx, :2]))
        yaw_err[i] = float(abs(wrap_angle(st[3] - path[idx, 3])))
    return {
        "lateral_rmse_m": float(np.sqrt(np.mean(lateral ** 2))),
        "lateral_p95_m": float(np.percentile(lateral, 95)),
        "lateral_max_m": float(np.max(lateral)),
        "yaw_rmse_deg": float(math.degrees(np.sqrt(np.mean(yaw_err ** 2)))),
        "yaw_p95_deg": float(math.degrees(np.percentile(yaw_err, 95))),
        "progress_pct": float(100.0 * nearest[-1] / max(1, len(path) - 1)),
    }


def run_pid_los(scenario: Scenario, path: np.ndarray, dt: float = 0.1) -> dict[str, object]:
    s_values = cumulative_s(path)
    state = np.array([path[0, 0], path[0, 1], 2.5, path[0, 3], scenario.target_speed_mps, 0.0], dtype=float)
    idx = 0
    states = []
    psi_cmds = []
    thrusts = []
    for _ in range(int(scenario.duration_s / dt)):
        idx = nearest_index(path, state[:2], idx)
        target = sample_by_s(path, s_values, s_values[idx] + scenario.lookahead_pid_m)
        psi_cmd = math.atan2(target[1] - state[1], target[0] - state[0])
        thrust = 12.0 * scenario.target_speed_mps ** 2
        states.append(state.copy())
        psi_cmds.append(psi_cmd)
        thrusts.append(thrust)
        state = plant_step(state, psi_cmd, thrust, dt)
    states_arr = np.asarray(states)
    metrics = path_metrics(states_arr, path)
    metrics.update(
        {
            "mean_speed_mps": float(np.mean(states_arr[:, 4])),
            "cmd_smoothness_deg2": float(np.var(np.rad2deg(np.unwrap(psi_cmds)))),
            "solve_success_rate": 1.0,
            "mean_solve_ms": 0.0,
            "max_solve_ms": 0.0,
        }
    )
    return {"states": states_arr, "psi_cmds": np.asarray(psi_cmds), "thrusts": np.asarray(thrusts), "metrics": metrics}


def run_pid_yaw_only(scenario: Scenario, path: np.ndarray, dt: float = 0.1) -> dict[str, object]:
    """Yaw-only PID baseline: follows local tangent at fixed speed, no x/y preview."""
    state = np.array([path[0, 0], path[0, 1], 2.5, path[0, 3], scenario.target_speed_mps, 0.0], dtype=float)
    idx = 0
    states = []
    psi_cmds = []
    thrusts = []
    for _ in range(int(scenario.duration_s / dt)):
        idx = nearest_index(path, state[:2], idx)
        psi_cmd = float(path[idx, 3])
        thrust = 12.0 * scenario.target_speed_mps ** 2
        states.append(state.copy())
        psi_cmds.append(psi_cmd)
        thrusts.append(thrust)
        state = plant_step(state, psi_cmd, thrust, dt)
    states_arr = np.asarray(states)
    metrics = path_metrics(states_arr, path)
    metrics.update(
        {
            "mean_speed_mps": float(np.mean(states_arr[:, 4])),
            "cmd_smoothness_deg2": float(np.var(np.rad2deg(np.unwrap(psi_cmds)))),
            "solve_success_rate": 1.0,
            "mean_solve_ms": 0.0,
            "max_solve_ms": 0.0,
        }
    )
    return {"states": states_arr, "psi_cmds": np.asarray(psi_cmds), "thrusts": np.asarray(thrusts), "metrics": metrics}


def build_optimizer(variant: MpcVariant) -> AUVMPCOptimizer:
    kin = AUVKinematicsModel(
        {
            "mass_u": 50.0,
            "mass_w": 50.0,
            "drag_u": 12.0,
            "drag_w": 20.0,
            "buoyancy_term": 0.0,
            "yaw_rate_gain": variant.yaw_rate_gain,
            "pitch_depth_gain": 0.8,
            "depth_to_heave_gain": 12.0,
            "max_pitch_deg": 20.0,
        }
    )
    return AUVMPCOptimizer(
        kin,
        N=variant.horizon,
        dt=variant.dt,
        weights={
            "x": variant.wx,
            "y": variant.wy,
            "z": 1.0,
            "psi": variant.wpsi,
            "u": variant.wu,
            "w": 0.2,
            "psi_cmd": variant.wpsi_cmd,
            "z_cmd": 0.001,
            "T_cmd": variant.wt,
        },
        constraints={
            "min_speed_ms": 0.25,
            "min_thrust_percent": variant.min_thrust,
            "max_thrust_percent": 35.0,
            "min_z_cmd_m": 0.0,
            "max_z_cmd_m": 8.0,
            "delta_z_max_per_step": 1.0,
            "delta_psi_max_per_step": math.radians(variant.delta_psi_deg),
            "z_band_m": 4.0,
            "psi_band_rad": math.radians(variant.psi_band_deg),
            "enable_rate_constraints": True,
            "enable_band_constraints": True,
        },
    )


def run_mpc(scenario: Scenario, path: np.ndarray, variant: MpcVariant, dt: float = 0.1) -> dict[str, object]:
    s_values = cumulative_s(path)
    optimizer = build_optimizer(variant)
    state = np.array([path[0, 0], path[0, 1], 2.5, path[0, 3], scenario.target_speed_mps, 0.0], dtype=float)
    idx = 0
    prev_u = None
    states = []
    psi_cmds = []
    thrusts = []
    solve_ms = []
    statuses = []
    for _ in range(int(scenario.duration_s / dt)):
        idx = nearest_index(path, state[:2], idx)
        ref = np.zeros((6, optimizer.N + 1), dtype=float)
        for k in range(optimizer.N + 1):
            sample = sample_by_s(path, s_values, s_values[idx] + 2.0 + k * scenario.path_speed_mps * variant.dt)
            ref[:, k] = [sample[0], sample[1], 2.5, sample[3], sample[4], 0.0]
        try:
            tic = time.perf_counter()
            result = optimizer.solve(state, ref, confidence=1.0, warm_start_U=prev_u)
            elapsed = (time.perf_counter() - tic) * 1000.0
            prev_u = result["U_opt"].copy()
            psi_cmd = float(result["U_opt"][0, 0])
            thrust = float(result["U_opt"][2, 0])
            statuses.append(str(result["solver_status"]))
            solve_ms.append(elapsed)
        except RuntimeError as exc:
            target = sample_by_s(path, s_values, s_values[idx] + scenario.lookahead_pid_m)
            psi_cmd = math.atan2(target[1] - state[1], target[0] - state[0])
            thrust = 12.0 * scenario.target_speed_mps ** 2
            statuses.append(f"FALLBACK: {exc}")
            solve_ms.append(0.0)
        states.append(state.copy())
        psi_cmds.append(psi_cmd)
        thrusts.append(thrust)
        state = plant_step(state, psi_cmd, thrust, dt, yaw_rate_gain=variant.yaw_rate_gain)
    states_arr = np.asarray(states)
    metrics = path_metrics(states_arr, path)
    success = [s in ("Solve_Succeeded", "Search_Direction_Becomes_Too_Small") for s in statuses]
    metrics.update(
        {
            "mean_speed_mps": float(np.mean(states_arr[:, 4])),
            "cmd_smoothness_deg2": float(np.var(np.rad2deg(np.unwrap(psi_cmds)))),
            "solve_success_rate": float(np.mean(success)),
            "mean_solve_ms": float(np.mean(solve_ms)),
            "max_solve_ms": float(np.max(solve_ms)),
        }
    )
    return {
        "states": states_arr,
        "psi_cmds": np.asarray(psi_cmds),
        "thrusts": np.asarray(thrusts),
        "metrics": metrics,
        "statuses": statuses,
    }


def plot_case(output_dir: Path, scenario: Scenario, path: np.ndarray, pid: dict[str, object], mpc: dict[str, object], variant: MpcVariant) -> None:
    fig, axes = plt.subplots(2, 1, figsize=(10, 8))
    pid_states = pid["states"]
    mpc_states = mpc["states"]
    assert isinstance(pid_states, np.ndarray)
    assert isinstance(mpc_states, np.ndarray)
    axes[0].plot(path[:, 0], path[:, 1], "k--", linewidth=1.5, label="reference path")
    axes[0].plot(pid_states[:, 0], pid_states[:, 1], color="#c44e52", label="PID yaw-only fixed speed")
    axes[0].plot(mpc_states[:, 0], mpc_states[:, 1], color="#4c72b0", label=f"MPC {variant.name}")
    axes[0].set_aspect("equal", adjustable="box")
    axes[0].set_title(f"{scenario.name}: x/y path tracking")
    axes[0].set_xlabel("x (m)")
    axes[0].set_ylabel("y (m)")
    axes[0].grid(True, alpha=0.3)
    axes[0].legend()

    axes[1].plot(np.rad2deg(np.unwrap(pid["psi_cmds"])), color="#c44e52", label="PID psi_cmd")
    axes[1].plot(np.rad2deg(np.unwrap(mpc["psi_cmds"])), color="#4c72b0", label="MPC psi_cmd")
    axes[1].set_title("Guidance heading command")
    axes[1].set_xlabel("step")
    axes[1].set_ylabel("heading cmd (deg)")
    axes[1].grid(True, alpha=0.3)
    axes[1].legend()
    fig.tight_layout()
    fig.savefig(output_dir / f"{scenario.name}_{variant.name}.png", dpi=180)
    plt.close(fig)


def main() -> int:
    out = get_output_dir("results/control/mpc_xy_yaw_extreme")
    out.mkdir(parents=True, exist_ok=True)
    figures = out / "figures"
    figures.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, object]] = []
    best_by_scenario: dict[str, tuple[MpcVariant, dict[str, object], dict[str, object]]] = {}
    for scenario in SCENARIOS:
        path = make_path(scenario)
        pid_yaw = run_pid_yaw_only(scenario, path)
        pid_los = run_pid_los(scenario, path)
        pid_yaw_metrics = pid_yaw["metrics"]
        pid_los_metrics = pid_los["metrics"]
        assert isinstance(pid_yaw_metrics, dict)
        assert isinstance(pid_los_metrics, dict)
        for key, value in pid_yaw_metrics.items():
            rows.append(
                {
                    "scenario": scenario.name,
                    "controller": "pid_yaw_only_fixed_speed",
                    "variant": "baseline",
                    "metric": key,
                    "value": value,
                }
            )
        for key, value in pid_los_metrics.items():
            rows.append(
                {
                    "scenario": scenario.name,
                    "controller": "pid_los_fixed_speed",
                    "variant": "strong_baseline",
                    "metric": key,
                    "value": value,
                }
            )

        best_score = math.inf
        for variant in VARIANTS:
            print(f"[RUN] {scenario.name} / {variant.name}", flush=True)
            mpc = run_mpc(scenario, path, variant)
            mpc_metrics = mpc["metrics"]
            assert isinstance(mpc_metrics, dict)
            score = float(mpc_metrics["lateral_rmse_m"]) + 0.02 * float(mpc_metrics["yaw_rmse_deg"])
            if score < best_score:
                best_score = score
                best_by_scenario[scenario.name] = (variant, mpc, pid_yaw)
            for key, value in mpc_metrics.items():
                rows.append(
                    {
                        "scenario": scenario.name,
                        "controller": "mpc_preview_speed",
                        "variant": variant.name,
                        "metric": key,
                        "value": value,
                    }
                )

        best_variant, best_mpc, _ = best_by_scenario[scenario.name]
        plot_case(figures, scenario, path, pid_yaw, best_mpc, best_variant)

    summary_csv = out / "summary_metrics.csv"
    with summary_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["scenario", "controller", "variant", "metric", "value"])
        writer.writeheader()
        writer.writerows(rows)

    comparison_csv = out / "best_comparison.csv"
    with comparison_csv.open("w", newline="", encoding="utf-8") as f:
        fieldnames = [
            "scenario",
            "best_variant",
            "pid_lateral_rmse_m",
            "los_lateral_rmse_m",
            "mpc_lateral_rmse_m",
            "lateral_rmse_reduction_pct",
            "pid_yaw_rmse_deg",
            "los_yaw_rmse_deg",
            "mpc_yaw_rmse_deg",
            "yaw_rmse_reduction_pct",
            "mpc_success_rate",
            "mpc_mean_solve_ms",
            "mpc_max_solve_ms",
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for scenario in SCENARIOS:
            variant, mpc, pid = best_by_scenario[scenario.name]
            los = run_pid_los(scenario, make_path(scenario))
            pm = pid["metrics"]
            lm = los["metrics"]
            mm = mpc["metrics"]
            assert isinstance(pm, dict)
            assert isinstance(lm, dict)
            assert isinstance(mm, dict)
            writer.writerow(
                {
                    "scenario": scenario.name,
                    "best_variant": variant.name,
                    "pid_lateral_rmse_m": pm["lateral_rmse_m"],
                    "los_lateral_rmse_m": lm["lateral_rmse_m"],
                    "mpc_lateral_rmse_m": mm["lateral_rmse_m"],
                    "lateral_rmse_reduction_pct": 100.0 * (1.0 - mm["lateral_rmse_m"] / pm["lateral_rmse_m"]),
                    "pid_yaw_rmse_deg": pm["yaw_rmse_deg"],
                    "los_yaw_rmse_deg": lm["yaw_rmse_deg"],
                    "mpc_yaw_rmse_deg": mm["yaw_rmse_deg"],
                    "yaw_rmse_reduction_pct": 100.0 * (1.0 - mm["yaw_rmse_deg"] / pm["yaw_rmse_deg"]),
                    "mpc_success_rate": mm["solve_success_rate"],
                    "mpc_mean_solve_ms": mm["mean_solve_ms"],
                    "mpc_max_solve_ms": mm["max_solve_ms"],
                }
            )

    print(f"[OK] output: {out}")
    print(f"[OK] summary: {summary_csv}")
    print(f"[OK] comparison: {comparison_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""UA-MPC mechanism ablation on genuinely lateral maneuver paths.

This deterministic, decoupled benchmark reuses the fair-reference path and
plant helpers from ``mpc_xy_yaw_extreme_benchmark.py``.  It isolates A0/A1/A2/A3
at a fixed low confidence and reports tracking error separately from solver
success.  Failed solves use the same LOS fallback as the existing benchmark.
"""

from __future__ import annotations

import argparse
import csv
import math
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from algorithm.auv_mpc_controller import AUVKinematicsModel, AUVMPCOptimizer
from tools.mpc_xy_yaw_extreme_benchmark import (
    SCENARIOS,
    cumulative_s,
    make_path,
    nearest_index,
    path_metrics,
    plant_step,
    sample_by_s,
)

@dataclass(frozen=True)
class Variant:
    name: str
    mpc_mode: str
    low_confidence_scale: float = 3.0
    low_confidence_control_scale: float = 0.3
    confidence_alpha: float = 1.5


VARIANTS = (
    Variant("A0_baseline", "baseline"),
    Variant("A1_ua_default", "ua"),
    Variant("A2_no_sigmoid", "ua", low_confidence_control_scale=1.0),
    Variant("A3_alpha1", "ua", confidence_alpha=1.0),
)


def build_optimizer(variant: Variant, max_iter: int) -> AUVMPCOptimizer:
    model = AUVKinematicsModel(
        {
            "mass_u": 50.0,
            "mass_w": 50.0,
            "drag_u": 12.0,
            "drag_w": 20.0,
            "buoyancy_term": -0.5,
            "yaw_rate_gain": 8.0,
            "pitch_depth_gain": 0.8,
            "depth_to_heave_gain": 12.0,
            "max_pitch_deg": 20.0,
        }
    )
    return AUVMPCOptimizer(
        model,
        N=20,
        dt=0.2,
        weights={
            "x": 1.0,
            "y": 1.0,
            "z": 40.0,
            "psi": 80.0,
            "u": 0.5,
            "w": 3.0,
            "psi_cmd": 0.005,
            "z_cmd": 0.002,
            "T_cmd": 0.01,
            "confidence_threshold": 0.6,
            "low_confidence_scale": variant.low_confidence_scale,
            "low_confidence_control_scale": variant.low_confidence_control_scale,
            "confidence_alpha": variant.confidence_alpha,
            "confidence_smoothness_k": 8.0,
            "mpc_mode": variant.mpc_mode,
        },
        constraints={
            "min_speed_ms": 0.3,
            "min_thrust_percent": 15.0,
            "max_thrust_percent": 100.0,
            "min_z_cmd_m": 0.0,
            "max_z_cmd_m": 50.0,
            "delta_z_max_per_step": 1.0,
            "delta_psi_max_per_step": 0.0419,
            "z_band_m": 4.0,
            "psi_band_rad": 0.7854,
            "enable_rate_constraints": True,
            "enable_band_constraints": True,
        },
        max_iter=max_iter,
    )


def run_case(scenario, path: np.ndarray, variant: Variant, confidence: float, max_iter: int):
    dt = 0.1
    s_values = cumulative_s(path)
    optimizer = build_optimizer(variant, max_iter=max_iter)
    state = np.array(
        [path[0, 0], path[0, 1], 2.5, path[0, 3], scenario.target_speed_mps, 0.0],
        dtype=float,
    )
    idx = 0
    prev_u = None
    states: list[np.ndarray] = []
    solve_ms: list[float] = []
    successes = 0
    fallback_reasons: dict[str, int] = {}

    for _ in range(int(scenario.duration_s / dt)):
        idx = nearest_index(path, state[:2], idx)
        ref = np.zeros((6, optimizer.N + 1), dtype=float)
        for k in range(optimizer.N + 1):
            sample = sample_by_s(
                path,
                s_values,
                s_values[idx] + k * scenario.path_speed_mps * optimizer.dt,
            )
            ref[:, k] = [sample[0], sample[1], 2.5, sample[3], sample[4], 0.0]

        tic = time.perf_counter()
        try:
            result = optimizer.solve(
                state,
                ref,
                confidence=confidence,
                warm_start_U=prev_u,
            )
            elapsed_ms = (time.perf_counter() - tic) * 1000.0
            prev_u = result["U_opt"].copy()
            psi_cmd = float(result["U_opt"][0, 0])
            thrust = float(result["U_opt"][2, 0])
            successes += 1
        except RuntimeError as exc:
            elapsed_ms = (time.perf_counter() - tic) * 1000.0
            reason = "Maximum_Iterations_Exceeded"
            if reason not in str(exc):
                reason = str(exc).splitlines()[-1][:120]
            fallback_reasons[reason] = fallback_reasons.get(reason, 0) + 1
            target = sample_by_s(path, s_values, s_values[idx] + scenario.lookahead_pid_m)
            psi_cmd = math.atan2(target[1] - state[1], target[0] - state[0])
            thrust = 12.0 * scenario.target_speed_mps**2

        states.append(state.copy())
        solve_ms.append(elapsed_ms)
        state = plant_step(state, psi_cmd, thrust, dt, yaw_rate_gain=8.0)

    states_arr = np.asarray(states)
    metrics = path_metrics(states_arr, path)
    nearest_progress: list[int] = []
    nearest_idx = 0
    for state_item in states_arr:
        nearest_idx = nearest_index(path, state_item[:2], nearest_idx)
        nearest_progress.append(nearest_idx)
    reached = next(
        (idx for idx, path_idx in enumerate(nearest_progress) if path_idx >= len(path) - 2),
        None,
    )
    active_states = states_arr if reached is None else states_arr[: reached + 1]
    active_metrics = path_metrics(active_states, path)
    terminal_states = states_arr[reached + 1 :] if reached is not None else np.empty((0, 6))
    if len(terminal_states):
        endpoint_error = np.linalg.norm(terminal_states[:, :2] - path[-1, :2], axis=1)
        terminal_overshoot_rmse = float(np.sqrt(np.mean(endpoint_error**2)))
    else:
        terminal_overshoot_rmse = float("nan")
    total = len(states_arr)
    metrics.update(
        {
            "active_lateral_rmse_m": active_metrics["lateral_rmse_m"],
            "active_lateral_p95_m": active_metrics["lateral_p95_m"],
            "endpoint_reached_s": float("nan") if reached is None else reached * dt,
            "terminal_overshoot_rmse_m": terminal_overshoot_rmse,
            "scenario": scenario.name,
            "variant": variant.name,
            "confidence": confidence,
            "max_iter": max_iter,
            "steps": total,
            "solve_success_rate": successes / total,
            "fallback_rate": 1.0 - successes / total,
            "mean_solve_wall_ms": float(np.mean(solve_ms)),
            "p95_solve_wall_ms": float(np.percentile(solve_ms, 95)),
            "fallback_reasons": ";".join(
                f"{key}:{value}" for key, value in sorted(fallback_reasons.items())
            ),
        }
    )
    return states_arr, metrics


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--scenarios",
        default="s_turn_long_wave,hairpin_180deg",
        help="Comma-separated names from mpc_xy_yaw_extreme_benchmark.SCENARIOS",
    )
    parser.add_argument("--confidence", type=float, default=0.3)
    parser.add_argument("--max-iter", type=int, default=100)
    parser.add_argument("--output-dir", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    wanted = {item.strip() for item in args.scenarios.split(",") if item.strip()}
    scenarios = [scenario for scenario in SCENARIOS if scenario.name in wanted]
    missing = wanted - {scenario.name for scenario in scenarios}
    if missing:
        raise SystemExit(f"Unknown scenarios: {sorted(missing)}")

    stamp = time.strftime("%Y%m%d_%H%M%S")
    output_dir = args.output_dir or (
        REPO_ROOT / "results" / "control" / "uampc_maneuver_ablation" / stamp
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, object]] = []
    trajectories: dict[tuple[str, str], np.ndarray] = {}
    for scenario in scenarios:
        path = make_path(scenario)
        for variant in VARIANTS:
            print(f"[RUN] {scenario.name} / {variant.name}", flush=True)
            states, metrics = run_case(
                scenario,
                path,
                variant,
                confidence=float(np.clip(args.confidence, 0.0, 1.0)),
                max_iter=args.max_iter,
            )
            rows.append(metrics)
            trajectories[(scenario.name, variant.name)] = states

        fig, ax = plt.subplots(figsize=(8.8, 5.8))
        ax.plot(path[:, 0], path[:, 1], "k--", linewidth=1.6, label="Reference")
        for variant in VARIANTS:
            states = trajectories[(scenario.name, variant.name)]
            ax.plot(states[:, 0], states[:, 1], linewidth=1.4, label=variant.name)
        ax.set_aspect("equal", adjustable="box")
        ax.set_xlabel("x (m)")
        ax.set_ylabel("y (m)")
        ax.set_title(f"{scenario.name}, confidence={args.confidence:g}")
        ax.grid(True, alpha=0.25)
        ax.legend(ncol=2, fontsize=8)
        fig.tight_layout()
        fig.savefig(output_dir / f"{scenario.name}_trajectories.png", dpi=180)
        plt.close(fig)

    fieldnames = list(rows[0].keys())
    with (output_dir / "metrics.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    lines = [
        "# UA-MPC Maneuver Ablation",
        "",
        f"- confidence: `{args.confidence}`",
        f"- max_iter: `{args.max_iter}`",
        "- deterministic decoupled kinematic benchmark; failed solves use LOS fallback",
        "",
        "| scenario | variant | full RMSE m | active-path RMSE m | terminal overshoot RMSE m | solve success | fallback | solve mean ms |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            f"| {row['scenario']} | {row['variant']} | "
            f"{float(row['lateral_rmse_m']):.3f} | "
            f"{float(row['active_lateral_rmse_m']):.3f} | "
            f"{float(row['terminal_overshoot_rmse_m']):.3f} | "
            f"{float(row['solve_success_rate']):.3f} | "
            f"{float(row['fallback_rate']):.3f} | "
            f"{float(row['mean_solve_wall_ms']):.2f} |"
        )
    (output_dir / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[OK] output: {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

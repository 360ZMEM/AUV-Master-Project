#!/usr/bin/env python3
"""R16 orthogonal ablation for MPC feasibility and terminal behavior."""

from __future__ import annotations

import argparse
import json
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
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from algorithm.auv_mpc_controller import (  # noqa: E402
    AUVKinematicsModel,
    AUVMPCOptimizer,
)
from tools.experiment_contract import finalize_bundle, initialize_bundle  # noqa: E402
from tools.mpc_xy_yaw_extreme_benchmark import (  # noqa: E402
    SCENARIOS,
    cumulative_s,
    make_path,
    nearest_index,
    path_metrics,
    plant_step,
    sample_by_s,
    wrap_angle,
)


@dataclass(frozen=True)
class MechanismVariant:
    name: str
    warm_start: bool = True
    reference_ramp: bool = False
    constraint_slack: bool = False
    terminal_hold: bool = False


VARIANTS = (
    MechanismVariant("B0_current"),
    MechanismVariant("B1_no_warm_start", warm_start=False),
    MechanismVariant("B2_reference_ramp", reference_ramp=True),
    MechanismVariant("B3_constraint_slack", constraint_slack=True),
    MechanismVariant("B4_terminal_hold", terminal_hold=True),
    MechanismVariant(
        "B5_combined",
        reference_ramp=True,
        constraint_slack=True,
        terminal_hold=True,
    ),
)


def build_optimizer(variant: MechanismVariant, max_iter: int) -> AUVMPCOptimizer:
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
            "low_confidence_scale": 3.0,
            "low_confidence_control_scale": 0.3,
            "confidence_alpha": 1.5,
            "confidence_smoothness_k": 8.0,
            "mpc_mode": "ua",
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
            "enable_constraint_slack": variant.constraint_slack,
            "constraint_slack_weight": 1e3,
            "max_speed_slack_ms": 0.3,
            "max_depth_rate_slack_m": 0.5,
            "max_heading_rate_slack_rad": math.radians(2.4),
            "max_depth_band_slack_m": 1.0,
            "max_heading_band_slack_rad": math.radians(15.0),
        },
        max_iter=max_iter,
    )


def _ramp_reference_heading(
    reference: np.ndarray,
    *,
    current_heading: float,
    previous_heading: float | None,
    cycle_limit_rad: float,
    preview_limit_rad: float,
) -> tuple[np.ndarray, float]:
    ramped = reference.copy()
    desired = float(reference[3, 0])
    start = current_heading if previous_heading is None else previous_heading
    first_delta = float(np.clip(wrap_angle(desired - start), -cycle_limit_rad, cycle_limit_rad))
    ramped[3, 0] = start + first_delta
    for k in range(1, ramped.shape[1]):
        delta = float(
            np.clip(
                wrap_angle(float(reference[3, k]) - float(ramped[3, k - 1])),
                -preview_limit_rad,
                preview_limit_rad,
            )
        )
        ramped[3, k] = ramped[3, k - 1] + delta
    return ramped, float(ramped[3, 0])


def _terminal_hold_step(
    state: np.ndarray,
    endpoint: np.ndarray,
    dt: float,
) -> np.ndarray:
    x, y, z, psi, u, w = state
    displacement = endpoint[:2] - state[:2]
    distance = float(np.linalg.norm(displacement))
    desired_heading = (
        float(math.atan2(displacement[1], displacement[0]))
        if distance > 0.1
        else float(psi)
    )
    yaw_error = float(wrap_angle(desired_heading - psi))
    yaw_rate = float(
        np.clip(8.0 * yaw_error, -math.radians(12.0), math.radians(12.0))
    )
    u_next = max(0.0, float(u) + dt * (-12.0 * float(u) * abs(float(u))) / 50.0)
    psi_next = float(wrap_angle(float(psi) + dt * yaw_rate))
    return np.array(
        [
            float(x) + dt * u_next * math.cos(psi_next),
            float(y) + dt * u_next * math.sin(psi_next),
            float(z),
            psi_next,
            u_next,
            float(w),
        ],
        dtype=float,
    )


def _finite_summary(values: list[float], statistic: str) -> float:
    finite = np.asarray([value for value in values if np.isfinite(value)], dtype=float)
    if not finite.size:
        return float("nan")
    if statistic == "mean":
        return float(np.mean(finite))
    if statistic == "p95":
        return float(np.percentile(finite, 95))
    if statistic == "max":
        return float(np.max(finite))
    raise ValueError(statistic)


def _as_float(value: object, default: float = float("nan")) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def run_case(
    scenario,
    path: np.ndarray,
    variant: MechanismVariant,
    *,
    confidence: float,
    max_iter: int,
    max_steps: int | None,
) -> tuple[np.ndarray, dict[str, object]]:
    plant_dt = 0.1
    optimizer = build_optimizer(variant, max_iter)
    s_values = cumulative_s(path)
    state = np.array(
        [
            path[0, 0],
            path[0, 1],
            2.5,
            path[0, 3],
            scenario.target_speed_mps,
            0.0,
        ],
        dtype=float,
    )
    total_steps = int(scenario.duration_s / plant_dt)
    if max_steps is not None:
        total_steps = min(total_steps, max_steps)

    path_index = 0
    previous_control = None
    previous_reference_heading = None
    reached_step = None
    states: list[np.ndarray] = []
    solver_wall_ms: list[float] = []
    solver_iterations: list[float] = []
    initial_violation: list[float] = []
    final_violation: list[float] = []
    slack_maximum: list[float] = []
    blocked_cycles = 0
    successes = 0
    failures = 0
    terminal_hold_cycles = 0
    fallback_reasons: dict[str, int] = {}

    for step in range(total_steps):
        path_index = nearest_index(path, state[:2], path_index)
        if reached_step is None and path_index >= len(path) - 2:
            reached_step = step

        states.append(state.copy())
        if variant.terminal_hold and reached_step is not None:
            terminal_hold_cycles += 1
            state = _terminal_hold_step(state, path[-1], plant_dt)
            continue

        reference = np.zeros((6, optimizer.N + 1), dtype=float)
        for k in range(optimizer.N + 1):
            sample = sample_by_s(
                path,
                s_values,
                s_values[path_index] + k * scenario.path_speed_mps * optimizer.dt,
            )
            reference[:, k] = [
                sample[0],
                sample[1],
                2.5,
                sample[3],
                sample[4],
                0.0,
            ]
        if variant.reference_ramp:
            reference, previous_reference_heading = _ramp_reference_heading(
                reference,
                current_heading=float(state[3]),
                previous_heading=previous_reference_heading,
                cycle_limit_rad=math.radians(1.0),
                preview_limit_rad=0.0419,
            )

        try:
            result = optimizer.solve(
                state,
                reference,
                confidence=confidence,
                warm_start_U=previous_control if variant.warm_start else None,
            )
            diagnostics = result
            previous_control = (
                result["U_opt"].copy() if variant.warm_start else None
            )
            heading_command = float(result["U_opt"][0, 0])
            thrust_command = float(result["U_opt"][2, 0])
            successes += 1
        except RuntimeError as exc:
            diagnostics = dict(getattr(exc, "diagnostics", {}))
            failures += 1
            reason = str(diagnostics.get("solver_status", str(exc))).splitlines()[-1]
            fallback_reasons[reason] = fallback_reasons.get(reason, 0) + 1
            target = sample_by_s(
                path,
                s_values,
                s_values[path_index] + scenario.lookahead_pid_m,
            )
            heading_command = math.atan2(
                target[1] - state[1],
                target[0] - state[0],
            )
            thrust_command = 12.0 * scenario.target_speed_mps**2

        solver_wall_ms.append(
            _as_float(diagnostics.get("solver_wall_time_current_ms"))
        )
        solver_iterations.append(
            _as_float(diagnostics.get("solver_iterations"))
        )
        initial_violation.append(
            _as_float(
                diagnostics.get("initial_constraint_violation_max")
            )
        )
        final_violation.append(
            _as_float(
                diagnostics.get("final_constraint_violation_max")
            )
        )
        slack_maximum.append(
            max(0.0, _as_float(diagnostics.get("slack_max"), 0.0))
        )
        blocked_cycles += int(bool(diagnostics.get("control_period_blocked", False)))
        state = plant_step(
            state,
            heading_command,
            thrust_command,
            plant_dt,
            yaw_rate_gain=8.0,
        )

    states_array = np.asarray(states)
    metrics = path_metrics(states_array, path)
    if reached_step is None:
        active_states = states_array
        terminal_states = np.empty((0, 6))
    else:
        active_states = states_array[: reached_step + 1]
        terminal_states = states_array[reached_step + 1 :]
    active_metrics = path_metrics(active_states, path)
    if len(terminal_states):
        endpoint_error = np.linalg.norm(
            terminal_states[:, :2] - path[-1, :2],
            axis=1,
        )
        terminal_rmse = float(np.sqrt(np.mean(endpoint_error**2)))
        terminal_p95 = float(np.percentile(endpoint_error, 95))
    else:
        terminal_rmse = float("nan")
        terminal_p95 = float("nan")

    solver_attempts = successes + failures
    metrics.update(
        {
            "scenario": scenario.name,
            "seed": "deterministic",
            "mpc_mode": "ua",
            "run_id": f"{scenario.name}__{variant.name}",
            "variant": variant.name,
            "status": "ok",
            "confidence": confidence,
            "max_iter": max_iter,
            "warm_start_enabled": variant.warm_start,
            "reference_ramp_enabled": variant.reference_ramp,
            "constraint_slack_enabled": variant.constraint_slack,
            "terminal_hold_enabled": variant.terminal_hold,
            "effective_sample_count": len(states_array),
            "solver_attempt_count": solver_attempts,
            "solver_success_count": successes,
            "failure_event_count": failures,
            "solve_success_rate": successes / max(solver_attempts, 1),
            "fallback_rate": failures / max(solver_attempts, 1),
            "fallback_type": "los" if failures else "none",
            "capability_gate_status": "passed",
            "solver_wall_time_current_ms": _finite_summary(
                solver_wall_ms, "mean"
            ),
            "solver_wall_time_p95_ms": _finite_summary(solver_wall_ms, "p95"),
            "solver_wall_time_max_ms": _finite_summary(solver_wall_ms, "max"),
            "solver_iterations_mean": _finite_summary(
                solver_iterations, "mean"
            ),
            "solver_iterations_max": _finite_summary(solver_iterations, "max"),
            "control_period_blocked_count": blocked_cycles,
            "control_period_blocked_rate": blocked_cycles
            / max(solver_attempts, 1),
            "initial_constraint_violation_max": _finite_summary(
                initial_violation, "max"
            ),
            "final_constraint_violation_max": _finite_summary(
                final_violation, "max"
            ),
            "slack_max": _finite_summary(slack_maximum, "max"),
            "slack_mean": _finite_summary(slack_maximum, "mean"),
            "active_lateral_rmse_m": active_metrics["lateral_rmse_m"],
            "active_lateral_p95_m": active_metrics["lateral_p95_m"],
            "endpoint_reached_s": (
                float("nan") if reached_step is None else reached_step * plant_dt
            ),
            "terminal_hold_cycles": terminal_hold_cycles,
            "terminal_overshoot_rmse_m": terminal_rmse,
            "terminal_overshoot_p95_m": terminal_p95,
            "fallback_reasons": ";".join(
                f"{key}:{value}"
                for key, value in sorted(fallback_reasons.items())
            ),
        }
    )
    return states_array, metrics


def _write_report(output_dir: Path, rows: list[dict[str, object]]) -> None:
    lines = [
        "# R16 MPC Feasibility Mechanism Ablation",
        "",
        "The variants are orthogonal mechanism probes. A lower fallback rate is "
        "not accepted when it is purchased by control-period blocking.",
        "",
        "| scenario | variant | success | blocked | wall p95 ms | active RMSE m | terminal RMSE m | slack max |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            "| {scenario} | {variant} | {success:.3f} | {blocked:.3f} | "
            "{wall:.2f} | {active:.3f} | {terminal:.3f} | {slack:.3g} |".format(
                scenario=row["scenario"],
                variant=row["variant"],
                success=float(row["solve_success_rate"]),
                blocked=float(row["control_period_blocked_rate"]),
                wall=float(row["solver_wall_time_p95_ms"]),
                active=float(row["active_lateral_rmse_m"]),
                terminal=float(row["terminal_overshoot_rmse_m"]),
                slack=float(row["slack_max"]),
            )
        )
    lines.extend(
        [
            "",
            "Terminal hold is evaluated separately from solver feasibility: after "
            "the endpoint is reached, it bypasses further path-progress commands "
            "and applies zero propulsion with passive drag.",
            "",
        ]
    )
    (output_dir / "report.md").write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )


def _write_figures(
    output_dir: Path,
    paths: dict[tuple[str, str], tuple[np.ndarray, np.ndarray]],
    rows: list[dict[str, object]],
    variants: list[MechanismVariant],
) -> list[str]:
    figures: list[str] = []
    scenarios = sorted({key[0] for key in paths})
    for scenario in scenarios:
        fig, ax = plt.subplots(figsize=(8.8, 5.8), dpi=180)
        reference = next(
            path for (name, _), (_, path) in paths.items() if name == scenario
        )
        ax.plot(
            reference[:, 0],
            reference[:, 1],
            "k--",
            linewidth=1.5,
            label="Reference",
        )
        for variant in variants:
            states, _ = paths[(scenario, variant.name)]
            ax.plot(
                states[:, 0],
                states[:, 1],
                linewidth=1.2,
                label=variant.name,
            )
        ax.set_aspect("equal", adjustable="box")
        ax.set_xlabel("x (m)")
        ax.set_ylabel("y (m)")
        ax.set_title(f"R16 mechanism ablation: {scenario}")
        ax.grid(True, alpha=0.25)
        ax.legend(ncol=2, fontsize=7)
        fig.tight_layout()
        target = output_dir / "figures" / f"{scenario}_trajectories.png"
        fig.savefig(target)
        plt.close(fig)
        figures.append(str(target.relative_to(output_dir)))

    fig, ax = plt.subplots(figsize=(9.2, 4.8), dpi=180)
    labels = [f"{row['scenario']}\n{row['variant']}" for row in rows]
    fallback = [float(row["fallback_rate"]) for row in rows]
    blocked = [float(row["control_period_blocked_rate"]) for row in rows]
    x = np.arange(len(rows))
    width = 0.38
    ax.bar(x - width / 2, fallback, width, label="Fallback rate")
    ax.bar(x + width / 2, blocked, width, label="Period-block rate")
    ax.set_xticks(x, labels, rotation=65, ha="right", fontsize=7)
    ax.set_ylabel("Ratio")
    ax.set_ylim(0.0, 1.05)
    ax.grid(axis="y", alpha=0.25)
    ax.legend()
    fig.tight_layout()
    target = output_dir / "figures" / "fallback_blocking_comparison.png"
    fig.savefig(target)
    plt.close(fig)
    figures.append(str(target.relative_to(output_dir)))
    return figures


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--scenarios",
        default="s_turn_long_wave,hairpin_180deg",
    )
    parser.add_argument(
        "--variants",
        default=",".join(variant.name for variant in VARIANTS),
    )
    parser.add_argument("--confidence", type=float, default=0.3)
    parser.add_argument("--max-iter", type=int, default=100)
    parser.add_argument("--max-steps", type=int)
    parser.add_argument("--output-dir", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    scenario_names = {
        item.strip() for item in args.scenarios.split(",") if item.strip()
    }
    variant_names = {
        item.strip() for item in args.variants.split(",") if item.strip()
    }
    scenarios = [
        scenario for scenario in SCENARIOS if scenario.name in scenario_names
    ]
    variants = [
        variant for variant in VARIANTS if variant.name in variant_names
    ]
    missing_scenarios = scenario_names - {item.name for item in scenarios}
    missing_variants = variant_names - {item.name for item in variants}
    if missing_scenarios or missing_variants:
        raise SystemExit(
            f"Unknown scenarios={sorted(missing_scenarios)} "
            f"variants={sorted(missing_variants)}"
        )
    if not scenarios or not variants:
        raise SystemExit("At least one scenario and one variant are required")

    stamp = time.strftime("%Y%m%dT%H%M%S")
    output_dir = args.output_dir or (
        REPO_ROOT / "results" / "control" / "r16_feasibility" / stamp
    )
    initialize_bundle(
        output_dir,
        experiment_id=f"r16_mpc_feasibility_{stamp}",
        runner=str(Path(__file__).resolve().relative_to(REPO_ROOT)),
        argv=sys.argv,
        data_layer="deterministic_decoupled_kinematic",
        matrix={
            "scenarios": [item.name for item in scenarios],
            "variants": [item.name for item in variants],
            "confidence": args.confidence,
            "max_iter": args.max_iter,
            "max_steps": args.max_steps,
        },
        duration_s=None,
        config_paths=[
            Path(__file__),
            REPO_ROOT / "algorithm" / "auv_mpc_controller.py",
            REPO_ROOT / "brain_linux" / "config" / "params.yaml",
        ],
        extra_manifest={
            "control_period_ms": 200.0,
            "formal_run": args.max_steps is None,
            "hardware_claim": False,
        },
    )

    rows: list[dict[str, object]] = []
    paths: dict[tuple[str, str], tuple[np.ndarray, np.ndarray]] = {}
    for scenario in scenarios:
        path = make_path(scenario)
        for variant in variants:
            print(f"[R16] {scenario.name} / {variant.name}", flush=True)
            states, metrics = run_case(
                scenario,
                path,
                variant,
                confidence=float(np.clip(args.confidence, 0.0, 1.0)),
                max_iter=max(1, args.max_iter),
                max_steps=args.max_steps,
            )
            rows.append(metrics)
            paths[(scenario.name, variant.name)] = (states, path)

    status = finalize_bundle(output_dir, rows)
    figures = _write_figures(output_dir, paths, rows, variants)
    _write_report(output_dir, rows)
    summary = {
        "status": status,
        "rows": rows,
        "figures": figures,
        "formal_run": args.max_steps is None,
    }
    (output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False, allow_nan=True) + "\n",
        encoding="utf-8",
    )
    print(f"[R16] output={output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

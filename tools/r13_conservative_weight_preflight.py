#!/usr/bin/env python3
"""Preflight and freeze conservative P6 delta-U weights for R13-v2.

This is not an R13 experiment. It combines the 36 archived R14 state
snapshots with a deterministic short S-turn to reject numerically unsafe or
needlessly aggressive delta-U profiles before any proxy closed-loop pilot.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from dataclasses import dataclass
from pathlib import Path
import sys
import time

import numpy as np
import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from algorithm.auv_mpc_controller import (  # noqa: E402
    AUVKinematicsModel,
    AUVMPCOptimizer,
)
from tools.experiment_contract import (  # noqa: E402
    finalize_bundle,
    initialize_bundle,
)
from tools.mpc_xy_yaw_extreme_benchmark import (  # noqa: E402
    SCENARIOS,
    cumulative_s,
    make_path,
    nearest_index,
    path_metrics,
    plant_step,
    sample_by_s,
)


DEFAULT_SNAPSHOTS = (
    REPO_ROOT
    / "results/control/r14_r13_diagnosis/20260809_r14/r13_snapshots.csv"
)
DEFAULT_CONFIG = REPO_ROOT / "brain_linux/config/params.protocol_udp_arbiter.yaml"


@dataclass(frozen=True)
class WeightProfile:
    name: str
    delta_psi_cmd: float
    delta_z_cmd: float
    delta_T_cmd: float

    @property
    def has_delta_penalty(self) -> bool:
        return any(
            value > 0.0
            for value in (
                self.delta_psi_cmd,
                self.delta_z_cmd,
                self.delta_T_cmd,
            )
        )


PROFILES = (
    WeightProfile("D0_no_delta_reference", 0.0, 0.0, 0.0),
    WeightProfile("D1_previous_dryrun", 0.05, 0.05, 0.01),
    WeightProfile("D2_light", 0.5, 0.1, 0.05),
    WeightProfile("D3_balanced", 2.0, 0.5, 0.1),
    WeightProfile("D4_strong", 10.0, 2.0, 0.5),
    WeightProfile("D5_very_strong", 50.0, 10.0, 2.0),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshots", type=Path, default=DEFAULT_SNAPSHOTS)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--scenario", default="s_turn_long_wave")
    parser.add_argument("--closed-loop-steps", type=int, default=180)
    parser.add_argument("--rmse-tolerance-ratio", type=float, default=1.05)
    parser.add_argument(
        "--maximum-control-variation-ratio",
        type=float,
        default=0.99,
    )
    parser.add_argument("--output-dir", type=Path)
    return parser.parse_args()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    fields: list[str] = []
    for row in rows:
        for field in row:
            if field not in fields:
                fields.append(field)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def build_optimizer(config: dict, profile: WeightProfile) -> AUVMPCOptimizer:
    weights = dict(config["mpc_weights"])
    weights.update(
        {
            "mpc_mode": "ua",
            "confidence_policy": "conservative",
            "low_conf_control_penalty_scale": 3.0,
            "low_conf_tracking_floor": 0.5,
            "delta_psi_cmd": profile.delta_psi_cmd,
            "delta_z_cmd": profile.delta_z_cmd,
            "delta_T_cmd": profile.delta_T_cmd,
        }
    )
    return AUVMPCOptimizer(
        AUVKinematicsModel(config["mpc_model"]),
        N=int(config["mpc"]["prediction_horizon"]),
        dt=float(config["mpc"]["dt"]),
        weights=weights,
        constraints=config["mpc_constraints"],
        max_iter=int(config["mpc"].get("max_iter", 100)),
    )


def quality_mapping(p_track: float) -> tuple[float, float]:
    probability = float(np.clip(p_track, 0.0, 1.0))
    speed_scale = 0.35 + 0.65 * probability
    delta_penalty_scale = 1.0 + 3.0 * (1.0 - probability)
    return speed_scale, delta_penalty_scale


def make_reference(
    optimizer: AUVMPCOptimizer,
    *,
    current_yaw: float,
    target_yaw: float,
    target_depth: float,
    target_speed: float,
) -> np.ndarray:
    reference = np.zeros((6, optimizer.N + 1), dtype=float)
    for index in range(optimizer.N + 1):
        elapsed_s = index * optimizer.dt
        reference[:, index] = [
            target_speed * math.cos(target_yaw) * elapsed_s,
            target_speed * math.sin(target_yaw) * elapsed_s,
            target_depth,
            target_yaw,
            target_speed,
            0.0,
        ]
    reference[3, 0] = current_yaw
    return reference


def snapshot_gate(
    config: dict,
    snapshots: list[dict[str, str]],
    profile: WeightProfile,
) -> dict[str, object]:
    optimizer = build_optimizer(config, profile)
    probabilities = (0.4, 0.6, 0.8)
    wall_times: list[float] = []
    iterations: list[float] = []
    failures = 0
    blocked = 0

    first = snapshots[0]
    warm_state = np.array(
        [
            0.0,
            0.0,
            float(first["current_depth_m"]),
            float(first["current_yaw_rad"]),
            float(first["current_speed_mps"]),
            0.0,
        ],
        dtype=float,
    )
    warm_reference = make_reference(
        optimizer,
        current_yaw=float(first["current_yaw_rad"]),
        target_yaw=float(first["target_yaw_rad"]),
        target_depth=float(first["target_depth_m"]),
        target_speed=float(first["target_speed_mps"]),
    )
    optimizer.solve(warm_state, warm_reference, confidence=0.8)

    for snapshot in snapshots:
        for p_track in probabilities:
            speed_scale, penalty_scale = quality_mapping(p_track)
            state = np.array(
                [
                    0.0,
                    0.0,
                    float(snapshot["current_depth_m"]),
                    float(snapshot["current_yaw_rad"]),
                    float(snapshot["current_speed_mps"]),
                    0.0,
                ],
                dtype=float,
            )
            reference = make_reference(
                optimizer,
                current_yaw=float(snapshot["current_yaw_rad"]),
                target_yaw=float(snapshot["target_yaw_rad"]),
                target_depth=float(snapshot["target_depth_m"]),
                target_speed=float(snapshot["target_speed_mps"])
                * speed_scale,
            )
            try:
                result = optimizer.solve(
                    state,
                    reference,
                    confidence=p_track,
                    delta_u_penalty_scale=penalty_scale,
                )
                wall_time = float(
                    result.get("solver_wall_time_current_ms", float("nan"))
                )
                iteration = float(result.get("solver_iterations", float("nan")))
            except RuntimeError as error:
                diagnostics = dict(getattr(error, "diagnostics", {}))
                wall_time = float(
                    diagnostics.get(
                        "solver_wall_time_current_ms",
                        float("nan"),
                    )
                )
                iteration = float(
                    diagnostics.get("solver_iterations", float("nan"))
                )
                failures += 1
            wall_times.append(wall_time)
            iterations.append(iteration)
            blocked += int(math.isfinite(wall_time) and wall_time > 50.0)

    finite_wall = np.asarray(
        [value for value in wall_times if math.isfinite(value)],
        dtype=float,
    )
    finite_iterations = np.asarray(
        [value for value in iterations if math.isfinite(value)],
        dtype=float,
    )
    attempt_count = len(snapshots) * len(probabilities)
    return {
        "profile": profile.name,
        "snapshot_attempt_count": attempt_count,
        "snapshot_failure_count": failures,
        "snapshot_fallback_rate": failures / max(attempt_count, 1),
        "snapshot_blocked_count": blocked,
        "snapshot_blocked_rate": blocked / max(attempt_count, 1),
        "snapshot_wall_mean_ms": float(np.mean(finite_wall)),
        "snapshot_wall_p95_ms": float(np.percentile(finite_wall, 95)),
        "snapshot_wall_max_ms": float(np.max(finite_wall)),
        "snapshot_iterations_mean": float(np.mean(finite_iterations)),
        "snapshot_iterations_max": float(np.max(finite_iterations)),
    }


def p_track_schedule(step: int, total_steps: int) -> float:
    phase = step / max(total_steps - 1, 1)
    if phase < 0.2:
        return 0.9
    if phase < 0.4:
        return 0.9 - 2.5 * (phase - 0.2)
    if phase < 0.65:
        return 0.4
    if phase < 0.85:
        return 0.4 + 2.0 * (phase - 0.65)
    return 0.8


def closed_loop_gate(
    config: dict,
    profile: WeightProfile,
    *,
    scenario,
    total_steps: int,
) -> dict[str, object]:
    optimizer = build_optimizer(config, profile)
    path = make_path(scenario)
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
    path_index = 0
    previous_control = None
    previous_applied_control = None
    states: list[np.ndarray] = []
    controls: list[np.ndarray] = []
    probabilities: list[float] = []
    speed_scales: list[float] = []
    penalty_scales: list[float] = []
    wall_times: list[float] = []
    failures = 0
    blocked = 0

    for step in range(total_steps):
        path_index = nearest_index(path, state[:2], path_index)
        p_track = p_track_schedule(step, total_steps)
        speed_scale, penalty_scale = quality_mapping(p_track)
        local_speed = max(
            0.3,
            float(path[path_index, 4]) * speed_scale,
        )
        reference = np.zeros((6, optimizer.N + 1), dtype=float)
        for preview in range(optimizer.N + 1):
            sample = sample_by_s(
                path,
                s_values,
                s_values[path_index]
                + preview * local_speed * optimizer.dt,
            )
            reference[:, preview] = [
                sample[0],
                sample[1],
                2.5,
                sample[3],
                local_speed,
                0.0,
            ]
        try:
            result = optimizer.solve(
                state,
                reference,
                confidence=p_track,
                warm_start_U=previous_control,
                delta_u_penalty_scale=penalty_scale,
                previous_control=previous_applied_control,
            )
            control = np.asarray(result["U_opt"][:, 0], dtype=float)
            previous_control = np.asarray(result["U_opt"], dtype=float)
            wall_time = float(
                result.get("solver_wall_time_current_ms", float("nan"))
            )
        except RuntimeError as error:
            diagnostics = dict(getattr(error, "diagnostics", {}))
            wall_time = float(
                diagnostics.get(
                    "solver_wall_time_current_ms",
                    float("nan"),
                )
            )
            failures += 1
            target = sample_by_s(
                path,
                s_values,
                s_values[path_index] + scenario.lookahead_pid_m,
            )
            control = np.array(
                [
                    math.atan2(target[1] - state[1], target[0] - state[0]),
                    2.5,
                    12.0 * local_speed**2,
                ],
                dtype=float,
            )
            previous_control = None
        previous_applied_control = control.copy()
        blocked += int(math.isfinite(wall_time) and wall_time > 50.0)
        states.append(state.copy())
        controls.append(control)
        probabilities.append(p_track)
        speed_scales.append(speed_scale)
        penalty_scales.append(penalty_scale)
        wall_times.append(wall_time)
        state = plant_step(
            state,
            float(control[0]),
            float(control[2]),
            0.1,
            yaw_rate_gain=8.0,
        )

    states_array = np.asarray(states, dtype=float)
    controls_array = np.asarray(controls, dtype=float)
    deltas = np.diff(controls_array, axis=0)
    normalized = np.column_stack(
        (
            deltas[:, 0] / 0.0419,
            deltas[:, 1] / 1.0,
            deltas[:, 2] / 10.0,
        )
    )
    metrics = path_metrics(states_array, path)
    finite_wall = np.asarray(
        [value for value in wall_times if math.isfinite(value)],
        dtype=float,
    )
    speed_monotonic = all(
        quality_mapping(lower)[0] <= quality_mapping(upper)[0]
        for lower, upper in zip((0.2, 0.4, 0.6, 0.8), (0.4, 0.6, 0.8, 1.0))
    )
    penalty_monotonic = all(
        quality_mapping(lower)[1] >= quality_mapping(upper)[1]
        for lower, upper in zip((0.2, 0.4, 0.6, 0.8), (0.4, 0.6, 0.8, 1.0))
    )
    metrics.update(
        {
            "profile": profile.name,
            "closed_loop_step_count": total_steps,
            "closed_loop_failure_count": failures,
            "closed_loop_fallback_rate": failures / max(total_steps, 1),
            "closed_loop_blocked_count": blocked,
            "closed_loop_blocked_rate": blocked / max(total_steps, 1),
            "closed_loop_wall_mean_ms": float(np.mean(finite_wall)),
            "closed_loop_wall_p95_ms": float(
                np.percentile(finite_wall, 95)
            ),
            "heading_delta_rms_deg": float(
                math.degrees(np.sqrt(np.mean(deltas[:, 0] ** 2)))
            ),
            "depth_delta_rms_m": float(
                np.sqrt(np.mean(deltas[:, 1] ** 2))
            ),
            "thrust_delta_rms_pct": float(
                np.sqrt(np.mean(deltas[:, 2] ** 2))
            ),
            "normalized_delta_u_rms": float(
                np.sqrt(np.mean(np.sum(normalized**2, axis=1)))
            ),
            "p_track_min": float(np.min(probabilities)),
            "p_track_max": float(np.max(probabilities)),
            "speed_scale_min": float(np.min(speed_scales)),
            "speed_scale_max": float(np.max(speed_scales)),
            "delta_penalty_scale_min": float(np.min(penalty_scales)),
            "delta_penalty_scale_max": float(np.max(penalty_scales)),
            "speed_mapping_monotonic": speed_monotonic,
            "delta_penalty_mapping_monotonic": penalty_monotonic,
        }
    )
    return metrics


def select_profile(
    rows: list[dict[str, object]],
    *,
    rmse_tolerance_ratio: float,
    maximum_control_variation_ratio: float,
) -> tuple[str | None, list[dict[str, object]]]:
    reference = next(
        row for row in rows if row["profile"] == "D0_no_delta_reference"
    )
    reference_rmse = float(reference["lateral_rmse_m"])
    reference_delta = float(reference["normalized_delta_u_rms"])
    eligible: list[dict[str, object]] = []
    for row in rows:
        profile = next(item for item in PROFILES if item.name == row["profile"])
        reasons: list[str] = []
        if not profile.has_delta_penalty:
            reasons.append("reference_only")
        if int(row["snapshot_failure_count"]) > 0:
            reasons.append("snapshot_fallback")
        if int(row["snapshot_blocked_count"]) > 0:
            reasons.append("snapshot_period_block")
        if int(row["closed_loop_failure_count"]) > 0:
            reasons.append("closed_loop_fallback")
        if int(row["closed_loop_blocked_count"]) > 0:
            reasons.append("closed_loop_period_block")
        if float(row["lateral_rmse_m"]) > reference_rmse * rmse_tolerance_ratio:
            reasons.append("rmse_degradation")
        if (
            float(row["normalized_delta_u_rms"])
            > reference_delta * maximum_control_variation_ratio
        ):
            reasons.append("no_smoothing_gain")
        if not bool(row["speed_mapping_monotonic"]):
            reasons.append("speed_mapping_nonmonotonic")
        if not bool(row["delta_penalty_mapping_monotonic"]):
            reasons.append("penalty_mapping_nonmonotonic")
        row["eligible_for_freeze"] = not reasons
        row["rejection_reasons"] = ";".join(reasons)
        if not reasons:
            eligible.append(row)
    if not eligible:
        return None, rows
    profile_order = {profile.name: index for index, profile in enumerate(PROFILES)}
    selected = min(
        eligible,
        key=lambda row: profile_order[str(row["profile"])],
    )
    return str(selected["profile"]), rows


def render_report(
    output_dir: Path,
    rows: list[dict[str, object]],
    selected_name: str | None,
) -> None:
    lines = [
        "# R13-v2 Conservative Weight Preflight",
        "",
        "This bundle is a preflight, not an R13 result.",
        "",
        "| profile | snap fallback | snap block | loop fallback | loop block | "
        "RMSE m | delta-U RMS | wall p95 ms | eligible |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in rows:
        lines.append(
            "| {profile} | {sf:.3f} | {sb:.3f} | {lf:.3f} | {lb:.3f} | "
            "{rmse:.4f} | {du:.4f} | {wall:.2f} | {eligible} |".format(
                profile=row["profile"],
                sf=float(row["snapshot_fallback_rate"]),
                sb=float(row["snapshot_blocked_rate"]),
                lf=float(row["closed_loop_fallback_rate"]),
                lb=float(row["closed_loop_blocked_rate"]),
                rmse=float(row["lateral_rmse_m"]),
                du=float(row["normalized_delta_u_rms"]),
                wall=float(row["closed_loop_wall_p95_ms"]),
                eligible=bool(row["eligible_for_freeze"]),
            )
        )
    lines.extend(
        [
            "",
            f"Selected profile: `{selected_name or 'NONE'}`.",
            "",
            "Selection is lexicographic after hard rejection: no fallback, no "
            "50 ms block, RMSE within 5% of the no-delta reference, strictly "
            "lower normalized control variation by at least the configured "
            "minimum gain, and monotonic P6 mappings. Among passing profiles, "
            "the lowest tested regularization is frozen.",
            "",
        ]
    )
    (output_dir / "report.md").write_text(
        "\n".join(lines),
        encoding="utf-8",
    )


def main() -> int:
    args = parse_args()
    snapshots = read_csv(args.snapshots)
    config = yaml.safe_load(args.config.read_text(encoding="utf-8")) or {}
    scenario = next(
        (item for item in SCENARIOS if item.name == args.scenario),
        None,
    )
    if scenario is None:
        raise SystemExit(f"unknown scenario: {args.scenario}")
    if len(snapshots) != 36:
        raise SystemExit(f"expected 36 R14 snapshots, got {len(snapshots)}")
    stamp = time.strftime("%Y%m%dT%H%M%S")
    output_dir = args.output_dir or (
        REPO_ROOT / "results/control/r13_conservative_weight_preflight" / stamp
    )
    initialize_bundle(
        output_dir,
        experiment_id=f"r13_conservative_weight_preflight_{stamp}",
        runner=str(Path(__file__).resolve().relative_to(REPO_ROOT)),
        argv=sys.argv,
        data_layer="r14_snapshot_gate_plus_deterministic_s_turn",
        matrix={
            "snapshot_count": len(snapshots),
            "snapshot_p_track": [0.4, 0.6, 0.8],
            "profiles": [profile.__dict__ for profile in PROFILES],
            "scenario": scenario.name,
            "closed_loop_steps": args.closed_loop_steps,
            "rmse_tolerance_ratio": args.rmse_tolerance_ratio,
            "maximum_control_variation_ratio": (
                args.maximum_control_variation_ratio
            ),
        },
        duration_s=0.0,
        config_paths=[
            Path(__file__),
            args.snapshots,
            args.config,
            REPO_ROOT / "algorithm/auv_mpc_controller.py",
            REPO_ROOT
            / "brain_linux/src/auv_controller/auv_controller/quality_control_policy.py",
        ],
        extra_manifest={
            "formal_r13_run": False,
            "hardware_claim": False,
            "control_period_ms": 50.0,
        },
    )

    rows: list[dict[str, object]] = []
    for profile in PROFILES:
        print(f"[R13-weight] snapshot gate {profile.name}", flush=True)
        snapshot = snapshot_gate(config, snapshots, profile)
        print(f"[R13-weight] closed loop {profile.name}", flush=True)
        closed_loop = closed_loop_gate(
            config,
            profile,
            scenario=scenario,
            total_steps=max(args.closed_loop_steps, 20),
        )
        rows.append(
            {
                "scenario": "r13_weight_preflight",
                "seed": "deterministic",
                "mpc_mode": "ua_conservative",
                "status": "ok",
                "effective_sample_count": int(
                    snapshot["snapshot_attempt_count"]
                )
                + int(closed_loop["closed_loop_step_count"]),
                "failure_event_count": int(
                    snapshot["snapshot_failure_count"]
                )
                + int(closed_loop["closed_loop_failure_count"]),
                "capability_gate_status": "not_applicable_offline_preflight",
                "solver_wall_time_current_ms": closed_loop[
                    "closed_loop_wall_mean_ms"
                ],
                "fallback_type": (
                    "none"
                    if int(snapshot["snapshot_failure_count"]) == 0
                    and int(closed_loop["closed_loop_failure_count"]) == 0
                    else "solver_failure"
                ),
                "delta_psi_cmd": profile.delta_psi_cmd,
                "delta_z_cmd": profile.delta_z_cmd,
                "delta_T_cmd": profile.delta_T_cmd,
                **snapshot,
                **closed_loop,
            }
        )

    selected_name, rows = select_profile(
        rows,
        rmse_tolerance_ratio=args.rmse_tolerance_ratio,
        maximum_control_variation_ratio=(
            args.maximum_control_variation_ratio
        ),
    )
    write_csv(output_dir / "weight_metrics.csv", rows)
    status = finalize_bundle(output_dir, rows)
    selected_profile = next(
        (profile for profile in PROFILES if profile.name == selected_name),
        None,
    )
    frozen = {
        "schema_version": "r13_conservative_weights.v1",
        "preflight_passed": selected_profile is not None,
        "selected_profile": selected_name,
        "confidence_policy": "conservative",
        "delta_psi_cmd": (
            selected_profile.delta_psi_cmd if selected_profile else None
        ),
        "delta_z_cmd": (
            selected_profile.delta_z_cmd if selected_profile else None
        ),
        "delta_T_cmd": (
            selected_profile.delta_T_cmd if selected_profile else None
        ),
        "source_bundle": str(output_dir),
        "bundle_status": status,
    }
    (output_dir / "frozen_weights.json").write_text(
        json.dumps(frozen, indent=2, ensure_ascii=False, allow_nan=False)
        + "\n",
        encoding="utf-8",
    )
    render_report(output_dir, rows, selected_name)
    print(f"[R13-weight] selected={selected_name} output={output_dir}")
    return 0 if selected_profile is not None else 2


if __name__ == "__main__":
    raise SystemExit(main())

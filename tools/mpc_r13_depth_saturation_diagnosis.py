#!/usr/bin/env python3
"""R14 diagnosis of the R13 depth-saturation solver failures."""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

import casadi as ca
import matplotlib
import numpy as np
import yaml
from mcap_ros2.reader import read_ros2_messages

matplotlib.use("Agg")
import matplotlib.pyplot as plt

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from algorithm.auv_mpc_controller import (  # noqa: E402
    AUVKinematicsModel,
    AUVMPCOptimizer,
)
from tools.experiment_contract import finalize_bundle, initialize_bundle  # noqa: E402


class HardClipAUVKinematicsModel(AUVKinematicsModel):
    """Pre-R14 model retained as the explicit negative-result baseline."""

    def compute_dynamics(self, state, control):
        _x, _y, z, psi, u, w = [state[index] for index in range(6)]
        psi_cmd, z_cmd, thrust_cmd = [control[index] for index in range(3)]
        depth_error = z_cmd - z
        theta = ca.fmax(
            -self.max_pitch_rad,
            ca.fmin(
                self.max_pitch_rad,
                -self.pitch_depth_gain * depth_error,
            ),
        )
        return ca.vertcat(
            u * ca.cos(psi),
            u * ca.sin(psi),
            -u * ca.sin(theta) + w * ca.cos(theta),
            self.yaw_rate_gain * (psi_cmd - psi),
            (
                ca.fmax(0.0, thrust_cmd)
                - self.drag_u * u * ca.fabs(u)
            )
            / self.mass_u,
            (
                -self.drag_w * w
                + self.depth_to_heave_gain * depth_error
                + self.buoyancy_term
            )
            / self.mass_w,
        )


class HardClipOptimizer(AUVMPCOptimizer):
    def _rollout_state_guess(self, x0, control_guess):
        states = np.zeros((self.N_STATES, self.N + 1), dtype=float)
        states[:, 0] = np.asarray(x0, dtype=float)
        model = self.kinematics
        for index in range(self.N):
            x, y, z, psi, u, w = states[:, index]
            psi_cmd, z_cmd, thrust_cmd = control_guess[:, index]
            depth_error = z_cmd - z
            theta = np.clip(
                -model.pitch_depth_gain * depth_error,
                -model.max_pitch_rad,
                model.max_pitch_rad,
            )
            derivative = np.array(
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
            states[:, index + 1] = states[:, index] + self.dt * derivative
        return states


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


def covariance_confidence(mcap_path: Path) -> float:
    values = []
    for decoded in read_ros2_messages(
        str(mcap_path),
        topics={"/auv/state/covariance"},
    ):
        covariance = np.asarray(decoded.ros_msg.data, dtype=float)
        if covariance.size == 225:
            values.append(math.exp(-float(covariance[0] + covariance[16])))
    return float(np.mean(values)) if values else 1.0


def first_debug_snapshot(source_row: dict[str, str]) -> dict[str, object]:
    mcap_path = Path(source_row["mcap"])
    payload = None
    for decoded in read_ros2_messages(
        str(mcap_path),
        topics={"/auv/controller/debug"},
    ):
        candidate = json.loads(decoded.ros_msg.data)
        if all(
            candidate.get(field) is not None
            for field in (
                "current_depth_m",
                "target_depth_m",
                "current_yaw_deg",
                "target_yaw_deg",
                "current_speed_mps",
                "target_speed_mps",
            )
        ):
            payload = candidate
            break
    if payload is None:
        raise RuntimeError(f"no usable controller debug payload: {mcap_path}")
    return {
        "scenario": source_row["scenario"],
        "seed": source_row["seed"],
        "mpc_mode": source_row["mpc_mode"],
        "mcap": str(mcap_path),
        "current_depth_m": float(payload["current_depth_m"]),
        "target_depth_m": float(payload["target_depth_m"]),
        "current_yaw_rad": math.radians(float(payload["current_yaw_deg"])),
        "target_yaw_rad": math.radians(float(payload["target_yaw_deg"])),
        "current_speed_mps": float(payload["current_speed_mps"]),
        "target_speed_mps": float(payload["target_speed_mps"]),
        "confidence": covariance_confidence(mcap_path),
    }


def build_optimizer(
    config: dict[str, object],
    *,
    model_kind: str,
    horizon: int,
    mode: str,
) -> AUVMPCOptimizer:
    weights = dict(config["mpc_weights"])
    weights["mpc_mode"] = mode
    model_type = (
        HardClipAUVKinematicsModel
        if model_kind == "hard_clip"
        else AUVKinematicsModel
    )
    optimizer_type = (
        HardClipOptimizer if model_kind == "hard_clip" else AUVMPCOptimizer
    )
    return optimizer_type(
        model_type(config["mpc_model"]),
        N=horizon,
        dt=float(config["mpc"]["dt"]),
        weights=weights,
        constraints=config["mpc_constraints"],
        max_iter=100,
    )


def run_solver(
    *,
    config: dict[str, object],
    case_id: str,
    case_source: str,
    mode: str,
    model_kind: str,
    horizon: int,
    current_depth_m: float,
    target_depth_m: float,
    current_yaw_rad: float,
    target_yaw_rad: float,
    current_speed_mps: float,
    target_speed_mps: float,
    confidence: float,
    source_mcap: str = "",
) -> dict[str, object]:
    optimizer = build_optimizer(
        config,
        model_kind=model_kind,
        horizon=horizon,
        mode=mode,
    )
    dt = float(config["mpc"]["dt"])
    initial_state = np.array(
        [
            0.0,
            0.0,
            current_depth_m,
            current_yaw_rad,
            current_speed_mps,
            0.0,
        ],
        dtype=float,
    )
    reference = np.zeros((6, horizon + 1), dtype=float)
    for index in range(horizon + 1):
        time_s = index * dt
        reference[:, index] = [
            target_speed_mps * math.cos(target_yaw_rad) * time_s,
            target_speed_mps * math.sin(target_yaw_rad) * time_s,
            target_depth_m,
            target_yaw_rad,
            target_speed_mps,
            0.0,
        ]
    success = False
    diagnostics: dict[str, object]
    try:
        result = optimizer.solve(
            initial_state,
            reference,
            confidence,
        )
        success = True
        diagnostics = result
    except RuntimeError as error:
        diagnostics = dict(getattr(error, "diagnostics", {}))
    wall_time = float(
        diagnostics.get("solver_wall_time_current_ms", float("nan"))
    )
    iterations = int(diagnostics.get("solver_iterations", 0))
    final_violation = float(
        diagnostics.get("final_constraint_violation_max", float("nan"))
    )
    return {
        "run_id": f"{case_id}__{model_kind}__N{horizon}",
        "scenario": case_id,
        "seed": 0,
        "mpc_mode": mode,
        "status": "ok",
        "case_source": case_source,
        "model_kind": model_kind,
        "prediction_horizon": horizon,
        "current_depth_m": current_depth_m,
        "target_depth_m": target_depth_m,
        "absolute_depth_error_m": abs(current_depth_m - target_depth_m),
        "current_yaw_rad": current_yaw_rad,
        "target_yaw_rad": target_yaw_rad,
        "current_speed_mps": current_speed_mps,
        "target_speed_mps": target_speed_mps,
        "confidence": confidence,
        "solve_success": success,
        "solver_status": diagnostics.get("solver_status", "unknown"),
        "solver_iterations": iterations,
        "solver_wall_time_current_ms": wall_time,
        "control_period_blocked": wall_time > 50.0,
        "final_constraint_violation_max": final_violation,
        "source_mcap": source_mcap,
        "effective_sample_count": 1,
        "failure_event_count": int(not success),
        "capability_gate_status": "not_applicable_offline_snapshot",
        "fallback_type": "none" if success else "solver_failure",
    }


def summarize(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    groups: dict[tuple[str, str, int], list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        groups[
            (
                str(row["case_source"]),
                str(row["model_kind"]),
                int(row["prediction_horizon"]),
            )
        ].append(row)
    output = []
    for (source, model, horizon), group in sorted(groups.items()):
        wall = np.asarray(
            [float(row["solver_wall_time_current_ms"]) for row in group]
        )
        iterations = np.asarray([int(row["solver_iterations"]) for row in group])
        output.append(
            {
                "case_source": source,
                "model_kind": model,
                "prediction_horizon": horizon,
                "run_count": len(group),
                "solve_success_rate": float(
                    np.mean([bool(row["solve_success"]) for row in group])
                ),
                "control_period_block_rate": float(
                    np.mean([bool(row["control_period_blocked"]) for row in group])
                ),
                "solver_wall_time_mean_ms": float(np.mean(wall)),
                "solver_wall_time_p95_ms": float(np.percentile(wall, 95)),
                "solver_iterations_mean": float(np.mean(iterations)),
            }
        )
    return output


def plot_results(output_dir: Path, summary: list[dict[str, object]]) -> None:
    actual = [row for row in summary if row["case_source"] == "r13_snapshot"]
    labels = [
        f"{row['model_kind']} N={row['prediction_horizon']}" for row in actual
    ]
    success = [float(row["solve_success_rate"]) for row in actual]
    wall = [float(row["solver_wall_time_p95_ms"]) for row in actual]
    x = np.arange(len(labels))
    fig, axes = plt.subplots(1, 2, figsize=(10.5, 4.2), dpi=180)
    axes[0].bar(x, success, color="#4C78A8")
    axes[0].set_ylabel("Solve success rate")
    axes[0].set_ylim(0.0, 1.05)
    axes[1].bar(x, wall, color="#F58518")
    axes[1].axhline(50.0, color="#E45756", linestyle="--", label="50 ms")
    axes[1].set_ylabel("Solver wall-time p95 (ms)")
    axes[1].legend(frameon=False)
    for axis in axes:
        axis.set_xticks(x)
        axis.set_xticklabels(labels, rotation=25, ha="right")
        axis.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(output_dir / "figures/r14_depth_saturation_diagnosis.png")
    plt.close(fig)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-results",
        type=Path,
        default=REPO_ROOT
        / "results/control_aggregates/20260809_r13_authoritative/"
        "authoritative_results.csv",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=REPO_ROOT
        / "brain_linux/config/params.protocol_udp_arbiter.yaml",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPO_ROOT
        / "results/control/r14_r13_diagnosis/20260809_r14",
    )
    args = parser.parse_args()
    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    snapshots = [
        first_debug_snapshot(row) for row in read_csv(args.source_results)
    ]
    initialize_bundle(
        args.output_dir,
        experiment_id="r14_r13_depth_saturation_diagnosis",
        runner="tools/mpc_r13_depth_saturation_diagnosis.py",
        argv=sys.argv,
        data_layer="r13_mcap_snapshot_replay_and_controlled_grid",
        matrix={
            "r13_snapshot_count": len(snapshots),
            "models": ["hard_clip", "smooth_tanh"],
            "snapshot_horizons": [5, 20],
            "grid_horizons": [5, 10, 20],
            "depth_errors_m": [0.0, 0.2, 0.4, 0.5, 0.7, 1.0],
        },
        duration_s=0.0,
        config_paths=[
            Path(__file__),
            REPO_ROOT / "algorithm/auv_mpc_controller.py",
            args.source_results,
            args.config,
        ],
        extra_manifest={"hardware_claim": False},
    )
    rows: list[dict[str, object]] = []
    for index, snapshot in enumerate(snapshots):
        case_id = (
            f"snapshot_{index:02d}_{snapshot['scenario']}_"
            f"seed{snapshot['seed']}_{snapshot['mpc_mode']}"
        )
        for model_kind in ("hard_clip", "smooth_tanh"):
            for horizon in (5, 20):
                rows.append(
                    run_solver(
                        config=config,
                        case_id=case_id,
                        case_source="r13_snapshot",
                        mode=str(snapshot["mpc_mode"]),
                        model_kind=model_kind,
                        horizon=horizon,
                        current_depth_m=float(snapshot["current_depth_m"]),
                        target_depth_m=float(snapshot["target_depth_m"]),
                        current_yaw_rad=float(snapshot["current_yaw_rad"]),
                        target_yaw_rad=float(snapshot["target_yaw_rad"]),
                        current_speed_mps=float(snapshot["current_speed_mps"]),
                        target_speed_mps=float(snapshot["target_speed_mps"]),
                        confidence=float(snapshot["confidence"]),
                        source_mcap=str(snapshot["mcap"]),
                    )
                )
    for mode in ("baseline", "ua"):
        for depth_error in (0.0, 0.2, 0.4, 0.5, 0.7, 1.0):
            for model_kind in ("hard_clip", "smooth_tanh"):
                for horizon in (5, 10, 20):
                    rows.append(
                        run_solver(
                            config=config,
                            case_id=f"grid_{mode}_depth{depth_error:.1f}",
                            case_source="controlled_depth_grid",
                            mode=mode,
                            model_kind=model_kind,
                            horizon=horizon,
                            current_depth_m=12.0 + depth_error,
                            target_depth_m=12.0,
                            current_yaw_rad=0.0,
                            target_yaw_rad=0.0,
                            current_speed_mps=0.84,
                            target_speed_mps=0.4,
                            confidence=0.367,
                        )
                    )
    finalize_bundle(args.output_dir, rows)
    summary = summarize(rows)
    write_csv(args.output_dir / "summary_by_model_horizon.csv", summary)
    write_csv(args.output_dir / "r13_snapshots.csv", snapshots)
    plot_results(args.output_dir, summary)
    report = [
        "# R14 R13 Depth-Saturation Diagnosis",
        "",
        "| source | model | horizon | runs | success | blocked | wall p95 ms | iterations mean |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in summary:
        report.append(
            f"| {row['case_source']} | {row['model_kind']} | "
            f"{row['prediction_horizon']} | {row['run_count']} | "
            f"{float(row['solve_success_rate']):.3f} | "
            f"{float(row['control_period_block_rate']):.3f} | "
            f"{float(row['solver_wall_time_p95_ms']):.2f} | "
            f"{float(row['solver_iterations_mean']):.2f} |"
        )
    report.extend(
        [
            "",
            "The hard clip is retained only as the pre-R14 baseline. "
            "The smooth model preserves the pitch bound without a zero-gradient "
            "plateau. Snapshot replay is diagnostic evidence, not a replacement "
            "for a new closed-loop PVS matrix.",
            "",
        ]
    )
    (args.output_dir / "report.md").write_text(
        "\n".join(report),
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

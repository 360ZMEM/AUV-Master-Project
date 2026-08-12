#!/usr/bin/env python3
"""R20 fixed/adaptive/robust ES-EKF and timestamp-handling benchmark."""

from __future__ import annotations

import argparse
import csv
import math
import sys
from collections import defaultdict, deque
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from algorithm.es_ekf import ES_EKF  # noqa: E402
from tools.es_ekf_extrinsics_benchmark import (  # noqa: E402
    ekf_config,
    generate_trajectory,
    profile_by_name,
)
from tools.experiment_contract import finalize_bundle, initialize_bundle  # noqa: E402
from tools.offline_ekf_benchmark import StandardEKFEngine  # noqa: E402


SCENARIOS = {
    "nominal": {"dvl_outlier_rate": 0.0, "depth_spike_rate": 0.0, "delay_s": 0.0},
    "impulsive_outliers": {
        "dvl_outlier_rate": 0.10,
        "depth_spike_rate": 0.02,
        "delay_s": 0.0,
    },
    "delayed_outliers": {
        "dvl_outlier_rate": 0.10,
        "depth_spike_rate": 0.02,
        "delay_s": 0.10,
    },
}
VARIANTS = {
    "standard_ekf": {"engine": "standard"},
    "es_fixed_r": {"adaptive_r_mode": "fixed"},
    "es_global_adaptive": {"adaptive_r_mode": "global"},
    "es_per_source_adaptive": {"adaptive_r_mode": "per_source"},
    "es_per_source_huber": {
        "adaptive_r_mode": "per_source",
        "robust_huber_delta": 2.0,
    },
    "es_per_source_huber_timestamp": {
        "adaptive_r_mode": "per_source",
        "robust_huber_delta": 2.0,
        "timestamp_aware": True,
    },
}
CHI2_95 = {1: (0.000982, 5.024), 3: (0.216, 9.348)}


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def nis_metrics(history: list[dict[str, object]], source: str) -> dict[str, float]:
    entries = [entry for entry in history if str(entry["source"]) == source]
    if not entries:
        return {
            f"{source}_nis_normalized_mean": math.nan,
            f"{source}_nis_95_coverage": math.nan,
            f"{source}_robust_active_rate": math.nan,
            f"{source}_r_scale_mean": math.nan,
        }
    values = np.asarray([float(entry["nis"]) for entry in entries])
    dimensions = np.asarray([int(entry["dim"]) for entry in entries])
    normalized = values / dimensions
    covered = []
    for value, dimension in zip(values, dimensions):
        lower, upper = CHI2_95[int(dimension)]
        covered.append(lower <= value <= upper)
    return {
        f"{source}_nis_normalized_mean": float(np.mean(normalized)),
        f"{source}_nis_95_coverage": float(np.mean(covered)),
        f"{source}_robust_active_rate": float(
            np.mean([float(entry.get("robust_scale", 1.0)) > 1.0 for entry in entries])
        ),
        f"{source}_r_scale_mean": float(
            np.mean([float(entry.get("r_scale", 1.0)) for entry in entries])
        ),
    }


def run_case(
    *,
    scenario_name: str,
    scenario: dict[str, float],
    variant_name: str,
    variant: dict[str, object],
    seed: int,
    duration_s: float,
    dt: float,
) -> dict[str, object]:
    trajectory = generate_trajectory(duration_s, dt)
    count = trajectory.times.size
    rng = np.random.default_rng(seed + 20000)
    acc_noise = rng.normal(0.0, 0.008, size=(count, 3))
    gyro_noise = rng.normal(0.0, 0.001, size=(count, 3))
    dvl_noise = rng.normal(0.0, 0.005, size=(count, 3))
    depth_noise = rng.normal(0.0, 0.01, size=count)
    dvl_outlier = rng.random(count) < float(scenario["dvl_outlier_rate"])
    depth_spike = rng.random(count) < float(scenario["depth_spike_rate"])
    dvl_outlier_vector = rng.normal(0.0, 0.8, size=(count, 3))
    depth_spike_value = rng.choice((-1.0, 1.0), size=count) * 0.5
    config = ekf_config(profile_by_name("none"), trajectory)

    standard = variant["engine"] == "standard" if "engine" in variant else False
    if standard:
        engine = StandardEKFEngine(config)
    else:
        config.update(variant)
        config["nis_window_size"] = 30
        config["adaptive_r_normalized_threshold"] = 1.5
        engine = ES_EKF(config)

    dvl_stride = max(1, int(round(0.2 / dt)))
    depth_stride = max(1, int(round(0.1 / dt)))
    delay_steps = int(round(float(scenario["delay_s"]) / dt))
    queue: deque[tuple[int, float, np.ndarray]] = deque()
    estimates: list[np.ndarray] = []
    nonfinite = False

    for index, time_s in enumerate(trajectory.times):
        if index > 0:
            engine.predict(
                trajectory.acc_body[index] + acc_noise[index],
                trajectory.gyro_body[index] + gyro_noise[index],
                dt,
            )
        if index % dvl_stride == 0:
            measurement = trajectory.v[index] + dvl_noise[index]
            if dvl_outlier[index]:
                measurement = measurement + dvl_outlier_vector[index]
            queue.append((index + delay_steps, float(time_s), measurement))
        while queue and queue[0][0] <= index:
            _arrival_index, capture_time, measurement = queue.popleft()
            if standard:
                engine.update_dvl(measurement)
            elif bool(variant.get("timestamp_aware", False)):
                engine.correct_dvl_world_with_timestamp(
                    measurement,
                    dvl_timestamp=capture_time,
                    current_timestamp=float(time_s),
                )
            else:
                engine.correct_dvl_world(measurement)
        if index % depth_stride == 0:
            positive_depth = float(-trajectory.p[index, 2] + depth_noise[index])
            if depth_spike[index]:
                positive_depth += float(depth_spike_value[index])
            if standard:
                engine.update_depth(-positive_depth)
            else:
                engine.correct_depth(positive_depth)
        position = engine.get_position() if standard else engine.get_state()["p"].copy()
        if not np.all(np.isfinite(position)):
            nonfinite = True
            break
        estimates.append(position)

    estimate = np.asarray(estimates)
    truth = trajectory.p[: estimate.shape[0]]
    errors = estimate - truth
    distance = np.linalg.norm(errors, axis=1)
    xy = np.linalg.norm(errors[:, :2], axis=1)
    history = [] if standard else engine.nis_history
    metrics = {}
    for source in ("dvl_world", "dvl_world_ts", "depth"):
        metrics.update(nis_metrics(history, source))
    failure = nonfinite or not distance.size or float(np.max(distance)) > 500.0
    return {
        "run_id": f"{scenario_name}__{variant_name}__seed{seed}",
        "scenario": scenario_name,
        "seed": seed,
        "mpc_mode": "not_applicable",
        "status": "ok",
        "filter_variant": variant_name,
        "duration_s": duration_s,
        "delay_s": scenario["delay_s"],
        "xy_rmse_m": float(np.sqrt(np.mean(xy * xy))),
        "rmse_3d_m": float(np.sqrt(np.mean(distance * distance))),
        "max_drift_m": float(np.max(distance)),
        "final_drift_m": float(distance[-1]),
        "estimation_failure": failure,
        "observation_update_count": len(history),
        **metrics,
        "effective_sample_count": int(estimate.shape[0]),
        "failure_event_count": int(failure),
        "capability_gate_status": "not_applicable_offline_ekf",
        "solver_wall_time_current_ms": "not_applicable",
        "fallback_type": "not_applicable",
    }


def summarize(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[(str(row["scenario"]), str(row["filter_variant"]))].append(row)
    metrics = (
        "xy_rmse_m",
        "rmse_3d_m",
        "max_drift_m",
        "dvl_world_nis_normalized_mean",
        "dvl_world_nis_95_coverage",
        "dvl_world_ts_nis_normalized_mean",
        "dvl_world_ts_nis_95_coverage",
        "depth_nis_normalized_mean",
        "depth_nis_95_coverage",
        "dvl_world_robust_active_rate",
        "dvl_world_ts_robust_active_rate",
    )
    output: list[dict[str, object]] = []
    for (scenario, variant), group in sorted(grouped.items()):
        item: dict[str, object] = {
            "scenario": scenario,
            "filter_variant": variant,
            "run_count": len(group),
            "failure_rate": float(
                np.mean([bool(row["estimation_failure"]) for row in group])
            ),
        }
        for metric in metrics:
            values = np.asarray([float(row[metric]) for row in group])
            item[f"{metric}_mean"] = (
                float(np.nanmean(values))
                if np.any(np.isfinite(values))
                else math.nan
            )
        output.append(item)
    return output


def plot(output_dir: Path, summary: list[dict[str, object]]) -> None:
    scenarios = list(SCENARIOS)
    variants = list(VARIANTS)
    width = 0.13
    x = np.arange(len(scenarios))
    fig, ax = plt.subplots(figsize=(11.0, 4.8), dpi=180)
    for index, variant in enumerate(variants):
        values = [
            next(
                float(row["rmse_3d_m_mean"])
                for row in summary
                if row["scenario"] == scenario
                and row["filter_variant"] == variant
            )
            for scenario in scenarios
        ]
        ax.bar(x + (index - 2.5) * width, values, width, label=variant)
    ax.set_xticks(x)
    ax.set_xticklabels(scenarios)
    ax.set_ylabel("3D RMSE (m)")
    ax.grid(axis="y", alpha=0.25)
    ax.legend(frameon=False, ncol=3, fontsize=8)
    fig.tight_layout()
    fig.savefig(output_dir / "figures/r20_filter_strategy_comparison.png")
    plt.close(fig)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--duration", type=float, default=120.0)
    parser.add_argument("--dt", type=float, default=0.05)
    parser.add_argument("--seeds", default="0,1,2,3,4")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPO_ROOT
        / "results/state_estimation/r20_filter_strategies/20260809_r20",
    )
    args = parser.parse_args()
    seeds = [int(value) for value in args.seeds.split(",") if value.strip()]
    output_dir = args.output_dir
    initialize_bundle(
        output_dir,
        experiment_id="r20_filter_strategy_benchmark",
        runner="tools/es_ekf_r_strategy_benchmark.py",
        argv=sys.argv,
        data_layer="offline_filter_strategy_ablation",
        matrix={
            "scenarios": list(SCENARIOS),
            "variants": list(VARIANTS),
            "seeds": seeds,
        },
        duration_s=args.duration,
        config_paths=[
            Path(__file__),
            REPO_ROOT / "algorithm/es_ekf.py",
        ],
        extra_manifest={"hardware_claim": False},
    )
    rows = [
        run_case(
            scenario_name=scenario_name,
            scenario=scenario,
            variant_name=variant_name,
            variant=variant,
            seed=seed,
            duration_s=args.duration,
            dt=args.dt,
        )
        for scenario_name, scenario in SCENARIOS.items()
        for variant_name, variant in VARIANTS.items()
        for seed in seeds
    ]
    finalize_bundle(output_dir, rows)
    summary = summarize(rows)
    write_csv(output_dir / "summary_by_strategy.csv", summary)
    plot(output_dir, summary)
    lines = [
        "# R20 Filter Strategy and Timestamp Benchmark",
        "",
        "| scenario | strategy | runs | 3D RMSE | max drift | failure rate |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for row in summary:
        lines.append(
            f"| {row['scenario']} | {row['filter_variant']} | "
            f"{row['run_count']} | {float(row['rmse_3d_m_mean']):.4f} | "
            f"{float(row['max_drift_m_mean']):.4f} | "
            f"{float(row['failure_rate']):.3f} |"
        )
    (output_dir / "report.md").write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

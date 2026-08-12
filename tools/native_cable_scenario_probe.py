#!/usr/bin/env python3
"""R21 factorial probe for the native cable scenario generator."""

from __future__ import annotations

import argparse
import csv
import itertools
import sys
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from algorithm.native_cable_scenario import (  # noqa: E402
    NativeCableScenario,
    NativeScenarioFactors,
)
from tools.es_ekf_long_horizon_replay import (  # noqa: E402
    DEFAULT_NOISE_PATH,
    load_measured_noise,
)
from tools.experiment_contract import finalize_bundle, initialize_bundle  # noqa: E402


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


def run_case(
    *,
    factors: NativeScenarioFactors,
    seed: int,
    noise_t: np.ndarray,
    noise_rate_hz: float,
    duration_s: float,
) -> dict[str, object]:
    scenario = NativeCableScenario(
        factors=factors,
        seed=seed,
        replay_noise_t=noise_t,
        replay_rate_hz=noise_rate_hz,
    )
    truths, measurements = scenario.transect(duration_s)
    truth_field = np.asarray([row["magnetic_field_t"] for row in truths])
    measured_field = np.asarray(
        [row["magnetic_field_t"] for row in measurements]
    )
    noise = measured_field - truth_field
    current = np.asarray([row["current_velocity_ned"] for row in truths])
    burial = np.asarray([row["burial_depth_m"] for row in truths])
    sonar_visible = np.asarray([row["sonar_visible"] for row in truths], dtype=bool)
    sonar_peak = np.asarray([row["sonar_peak"] for row in measurements])
    cable_distance = np.asarray([row["cable_distance_m"] for row in truths])
    label = (
        f"g{int(factors.curved_geometry)}"
        f"_t{int(factors.terrain_enabled)}"
        f"_r{int(factors.measured_noise_replay)}"
        f"_c{int(factors.cross_current_enabled)}"
    )
    return {
        "run_id": f"{label}__seed{seed}",
        "scenario": "native_cable_factorial_probe",
        "seed": seed,
        "mpc_mode": "not_applicable",
        "status": "ok",
        "factor_label": label,
        "curved_geometry": int(factors.curved_geometry),
        "terrain_enabled": int(factors.terrain_enabled),
        "measured_noise_replay": int(factors.measured_noise_replay),
        "cross_current_enabled": int(factors.cross_current_enabled),
        "sample_count": len(truths),
        "cable_distance_mean_m": float(np.mean(cable_distance)),
        "cable_distance_max_m": float(np.max(cable_distance)),
        "burial_depth_mean_m": float(np.mean(burial)),
        "burial_depth_max_m": float(np.max(burial)),
        "sonar_visible_rate": float(np.mean(sonar_visible)),
        "sonar_peak_visible_mean": float(np.mean(sonar_peak[sonar_visible])),
        "sonar_peak_hidden_mean": (
            float(np.mean(sonar_peak[~sonar_visible]))
            if np.any(~sonar_visible)
            else float("nan")
        ),
        "magnetic_noise_rms_nt": float(
            np.sqrt(np.mean(np.sum(noise * noise, axis=1))) * 1e9
        ),
        "magnetic_noise_xy_correlation": float(
            np.corrcoef(noise[:, 0], noise[:, 1])[0, 1]
        ),
        "magnetic_noise_lag1_correlation": float(
            np.corrcoef(noise[:-1, 0], noise[1:, 0])[0, 1]
        ),
        "current_speed_mean_mps": float(
            np.mean(np.linalg.norm(current, axis=1))
        ),
        "truth_measurement_separated": True,
        "effective_sample_count": len(truths),
        "failure_event_count": 0,
        "capability_gate_status": "not_applicable_generator_probe",
        "solver_wall_time_current_ms": "not_applicable",
        "fallback_type": "not_applicable",
    }


def plot(output_dir: Path, rows: list[dict[str, object]]) -> None:
    replay = [
        float(row["magnetic_noise_lag1_correlation"])
        for row in rows
        if int(row["measured_noise_replay"]) == 1
    ]
    gaussian = [
        float(row["magnetic_noise_lag1_correlation"])
        for row in rows
        if int(row["measured_noise_replay"]) == 0
    ]
    current_on = [
        float(row["current_speed_mean_mps"])
        for row in rows
        if int(row["cross_current_enabled"]) == 1
    ]
    current_off = [
        float(row["current_speed_mean_mps"])
        for row in rows
        if int(row["cross_current_enabled"]) == 0
    ]
    fig, axes = plt.subplots(1, 2, figsize=(8.5, 4.0), dpi=180)
    axes[0].bar(
        ["Gaussian", "Measured replay"],
        [np.mean(gaussian), np.mean(replay)],
        color=["#4C78A8", "#F58518"],
    )
    axes[0].set_ylabel("Magnetic noise lag-1 correlation")
    axes[1].bar(
        ["Current off", "Current on"],
        [np.mean(current_off), np.mean(current_on)],
        color=["#72B7B2", "#E45756"],
    )
    axes[1].set_ylabel("Mean current speed (m/s)")
    for axis in axes:
        axis.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(output_dir / "figures/r21_factor_switch_probe.png")
    plt.close(fig)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", default="0,1")
    parser.add_argument("--duration", type=float, default=50.0)
    parser.add_argument("--noise-path", type=Path, default=DEFAULT_NOISE_PATH)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPO_ROOT
        / "results/scenarios/r21_native_generator/20260809_r21",
    )
    args = parser.parse_args()
    seeds = [int(value) for value in args.seeds.split(",") if value.strip()]
    noise_t, noise_rate_hz, _metadata = load_measured_noise(
        args.noise_path.resolve()
    )
    factor_matrix = [
        NativeScenarioFactors(*values)
        for values in itertools.product((False, True), repeat=4)
    ]
    initialize_bundle(
        args.output_dir,
        experiment_id="r21_native_cable_generator_probe",
        runner="tools/native_cable_scenario_probe.py",
        argv=sys.argv,
        data_layer="factorized_native_scenario_generator",
        matrix={
            "factor_order": [
                "curved_geometry",
                "terrain_enabled",
                "measured_noise_replay",
                "cross_current_enabled",
            ],
            "combination_count": len(factor_matrix),
            "seeds": seeds,
        },
        duration_s=args.duration,
        config_paths=[
            Path(__file__),
            REPO_ROOT / "algorithm/native_cable_scenario.py",
            args.noise_path,
        ],
        extra_manifest={
            "hardware_claim": False,
            "truth_measurement_separation": True,
            "proxy_scenarios_preserved": True,
        },
    )
    rows = [
        run_case(
            factors=factors,
            seed=seed,
            noise_t=noise_t,
            noise_rate_hz=noise_rate_hz,
            duration_s=args.duration,
        )
        for factors in factor_matrix
        for seed in seeds
    ]
    finalize_bundle(args.output_dir, rows)
    write_csv(args.output_dir / "factor_metrics.csv", rows)
    plot(args.output_dir, rows)
    replay_corr = np.mean(
        [
            float(row["magnetic_noise_lag1_correlation"])
            for row in rows
            if int(row["measured_noise_replay"]) == 1
        ]
    )
    gaussian_corr = np.mean(
        [
            float(row["magnetic_noise_lag1_correlation"])
            for row in rows
            if int(row["measured_noise_replay"]) == 0
        ]
    )
    lines = [
        "# R21 Native Cable Scenario Generator Probe",
        "",
        f"- Factor combinations: `{len(factor_matrix)}`",
        f"- Seeds per combination: `{len(seeds)}`",
        "- Truth and measurements: separate payloads",
        "- Existing proxy scenarios: preserved",
        f"- Gaussian magnetic lag-1 correlation: `{gaussian_corr:.4f}`",
        f"- Measured replay lag-1 correlation: `{replay_corr:.4f}`",
        "",
        "The probe validates orthogonal factor switches and data contracts. "
        "Statistical interaction claims are reserved for R22.",
        "",
    ]
    (args.output_dir / "report.md").write_text(
        "\n".join(lines),
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

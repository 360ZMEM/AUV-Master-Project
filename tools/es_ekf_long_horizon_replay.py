#!/usr/bin/env python3
"""R18 long-horizon ES-EKF sensitivity and R19 measured-noise replay."""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from algorithm.es_ekf import ES_EKF, quat_to_rotmat  # noqa: E402
from tools.es_ekf_extrinsics_benchmark import (  # noqa: E402
    ekf_config,
    generate_trajectory,
    profile_by_name,
)
from tools.experiment_contract import finalize_bundle, initialize_bundle  # noqa: E402


DEFAULT_NOISE_PATH = (
    REPO_ROOT
    / "hardware_wrappers/fangkong_adc/raw_data/1780675809_291477.npz"
)
R18_SCENARIOS = {
    "baseline": {
        "drop_rate": 0.0,
        "freeze_interval_s": None,
        "freeze_duration_s": None,
        "imu_noise_scale": 1.0,
        "imu_bias_rate": 0.0,
        "depth_spike_rate_hz": 0.0,
        "depth_spike_amplitude_m": 0.0,
    },
    "dvl_dropout_60": {
        "drop_rate": 0.60,
        "freeze_interval_s": 20.0,
        "freeze_duration_s": (1.0, 4.0),
        "imu_noise_scale": 1.0,
        "imu_bias_rate": 0.0,
        "depth_spike_rate_hz": 0.0,
        "depth_spike_amplitude_m": 0.0,
    },
    "combined_stress": {
        "drop_rate": 0.30,
        "freeze_interval_s": 30.0,
        "freeze_duration_s": (1.0, 3.0),
        "imu_noise_scale": 1.5,
        "imu_bias_rate": 0.001,
        "depth_spike_rate_hz": 0.05,
        "depth_spike_amplitude_m": 0.5,
    },
}


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


def load_measured_noise(path: Path) -> tuple[np.ndarray, float, dict[str, object]]:
    with np.load(path, allow_pickle=False) as payload:
        voltage = np.asarray(payload["voltage"], dtype=float)
        sensitivity = np.asarray(payload["sensitivity_mv_per_ut"], dtype=float)
        sample_rate_hz = float(payload["sample_rate_hz"])
    if voltage.ndim != 2 or voltage.shape[1] != 3:
        raise ValueError("measured replay must contain an N x 3 voltage array")
    if sensitivity.shape != (3,) or np.any(sensitivity <= 0.0):
        raise ValueError("sensitivity_mv_per_ut must contain three positive values")

    magnetic_ut = voltage / (sensitivity.reshape(1, 3) / 1000.0)
    centered_t = (magnetic_ut - np.mean(magnetic_ut, axis=0)) * 1e-6
    covariance_t2 = np.cov(centered_t, rowvar=False)
    correlation = np.corrcoef(centered_t, rowvar=False)
    block_size = max(1, int(round(sample_rate_hz * 0.5)))
    block_means = np.asarray(
        [
            np.mean(centered_t[start : start + block_size], axis=0)
            for start in range(0, centered_t.shape[0], block_size)
            if centered_t[start : start + block_size].shape[0] >= block_size // 2
        ]
    )
    if block_means.size == 0:
        block_means = np.mean(centered_t, axis=0, keepdims=True)
    spectrum = np.fft.rfft(centered_t, axis=0)
    frequencies = np.fft.rfftfreq(centered_t.shape[0], 1.0 / sample_rate_hz)
    positive = frequencies > 0.0
    peak_indices = np.argmax(np.abs(spectrum[positive]), axis=0)
    peak_frequencies = frequencies[positive][peak_indices]
    try:
        source_path = str(path.resolve().relative_to(REPO_ROOT.resolve()))
    except ValueError:
        source_path = str(path.resolve())
    metadata = {
        "source_path": source_path,
        "sample_count": int(centered_t.shape[0]),
        "sample_rate_hz": sample_rate_hz,
        "duration_s": centered_t.shape[0] / sample_rate_hz,
        "axis_rms_nt": (np.std(centered_t, axis=0) * 1e9).tolist(),
        "axis_covariance_nt2": (covariance_t2 * 1e18).tolist(),
        "axis_correlation": correlation.tolist(),
        "half_second_block_mean_span_nt": (
            (np.max(block_means, axis=0) - np.min(block_means, axis=0)) * 1e9
        ).tolist(),
        "dominant_frequency_hz": peak_frequencies.tolist(),
        "centering": "per-axis arithmetic mean only; drift and spectrum retained",
    }
    return centered_t, sample_rate_hz, metadata


def build_dvl_schedule(
    *,
    duration_s: float,
    dt: float,
    seed: int,
    scenario: dict[str, object],
    phase_steps_override: int | None = None,
) -> tuple[set[int], dict[str, float]]:
    rng = np.random.default_rng(seed + 31000)
    stride = max(1, int(round(0.2 / dt)))
    phase_steps = (
        int(rng.integers(0, stride))
        if phase_steps_override is None
        else int(phase_steps_override) % stride
    )
    candidate = np.arange(phase_steps, int(duration_s / dt), stride, dtype=int)
    frozen = np.zeros(candidate.size, dtype=bool)

    interval = scenario["freeze_interval_s"]
    duration_range = scenario["freeze_duration_s"]
    if interval is not None and duration_range is not None:
        start = float(interval) + float(rng.uniform(-2.0, 2.0))
        while start < duration_s:
            length = float(rng.uniform(*duration_range))
            times = candidate * dt
            frozen |= (times >= start) & (times < start + length)
            start += float(interval) + float(rng.uniform(-2.0, 2.0))

    target_drop = float(scenario["drop_rate"])
    frozen_fraction = float(np.mean(frozen)) if frozen.size else 0.0
    independent_drop = max(
        0.0,
        min(1.0, (target_drop - frozen_fraction) / max(1e-9, 1.0 - frozen_fraction)),
    )
    dropped = frozen | (rng.random(candidate.size) < independent_drop)
    kept = candidate[~dropped]
    times = kept * dt
    gaps = np.diff(times) if times.size > 1 else np.asarray([duration_s])
    diagnostics = {
        "dvl_phase_s": phase_steps * dt,
        "dvl_candidate_count": float(candidate.size),
        "dvl_retained_count": float(kept.size),
        "dvl_retained_rate": float(kept.size / max(1, candidate.size)),
        "dvl_max_gap_s": float(np.max(gaps)) if gaps.size else duration_s,
        "dvl_first_update_s": float(times[0]) if times.size else duration_s,
        "dvl_frozen_fraction": frozen_fraction,
    }
    return set(int(value) for value in kept), diagnostics


def prefix_errors(
    estimates: np.ndarray,
    truth: np.ndarray,
    times: np.ndarray,
    horizons: tuple[float, ...] = (60.0, 120.0, 300.0),
) -> dict[str, float]:
    result: dict[str, float] = {}
    error = estimates - truth
    for horizon in horizons:
        mask = times < min(horizon, times[-1] + 1e-9)
        distance = np.linalg.norm(error[mask], axis=1)
        result[f"rmse_3d_{int(horizon)}s_m"] = float(
            np.sqrt(np.mean(distance * distance))
        )
        result[f"max_drift_{int(horizon)}s_m"] = float(np.max(distance))
    return result


def run_r18_case(
    *,
    scenario_name: str,
    scenario: dict[str, object],
    seed: int,
    duration_s: float,
    dt: float,
    timing_variant: str,
    phase_steps: int,
) -> dict[str, object]:
    trajectory = generate_trajectory(duration_s, dt)
    sample_count = trajectory.times.size
    imu_rng = np.random.default_rng(seed + 18100)
    dvl_rng = np.random.default_rng(seed + 18200)
    depth_rng = np.random.default_rng(seed + 18300)
    event_rng = np.random.default_rng(seed + 18400)
    acc_noise_unit = imu_rng.normal(0.0, 0.008, size=(sample_count, 3))
    gyro_noise_unit = imu_rng.normal(0.0, 0.001, size=(sample_count, 3))
    dvl_noise = dvl_rng.normal(0.0, 0.005, size=(sample_count, 3))
    depth_noise = depth_rng.normal(0.0, 0.01, size=sample_count)
    spike_uniform = event_rng.random(sample_count)
    spike_sign = event_rng.choice((-1.0, 1.0), size=sample_count)
    profile = profile_by_name("none")
    config = ekf_config(profile, trajectory)
    filter_obj = ES_EKF(config)
    dvl_schedule, timing = build_dvl_schedule(
        duration_s=duration_s,
        dt=dt,
        seed=seed,
        scenario=scenario,
        phase_steps_override=phase_steps,
    )
    depth_stride = max(1, int(round(0.1 / dt)))
    depth_phase = int(event_rng.integers(0, depth_stride))
    bias_direction = event_rng.normal(size=3)
    bias_direction /= max(np.linalg.norm(bias_direction), 1e-12)
    estimates: list[np.ndarray] = []
    velocities: list[np.ndarray] = []
    depth_spikes = 0

    for index, time_s in enumerate(trajectory.times):
        if index > 0:
            acc_noise = acc_noise_unit[index] * float(
                scenario["imu_noise_scale"]
            )
            gyro_noise = gyro_noise_unit[index] * float(
                scenario["imu_noise_scale"]
            )
            acc_bias = (
                bias_direction * float(scenario["imu_bias_rate"]) * float(time_s)
            )
            filter_obj.predict(
                trajectory.acc_body[index] + acc_noise + acc_bias,
                trajectory.gyro_body[index] + gyro_noise,
                dt,
            )

        if index in dvl_schedule:
            rotation = quat_to_rotmat(trajectory.q[index])
            body_velocity = rotation.T @ trajectory.v[index]
            measurement = body_velocity + dvl_noise[index]
            filter_obj.correct_dvl_sensor(
                measurement,
                gyro_body=trajectory.gyro_body[index],
            )

        if index % depth_stride == depth_phase:
            measurement = float(-trajectory.p[index, 2] + depth_noise[index])
            spike_probability = (
                float(scenario["depth_spike_rate_hz"]) * depth_stride * dt
            )
            if spike_uniform[index] < spike_probability:
                measurement += (
                    float(scenario["depth_spike_amplitude_m"])
                    * float(spike_sign[index])
                )
                depth_spikes += 1
            filter_obj.correct_depth(measurement)

        state = filter_obj.get_state()
        estimates.append(state["p"].copy())
        velocities.append(state["v"].copy())

    estimates_array = np.asarray(estimates)
    velocities_array = np.asarray(velocities)
    position_error = estimates_array - trajectory.p
    velocity_error = velocities_array - trajectory.v
    xy_error = np.linalg.norm(position_error[:, :2], axis=1)
    distance = np.linalg.norm(position_error, axis=1)
    speed_error = np.linalg.norm(velocity_error, axis=1)
    dvl_nis = [
        float(entry["nis"])
        for entry in filter_obj.nis_history
        if entry["source"] == "dvl_sensor"
    ]
    depth_nis = [
        float(entry["nis"])
        for entry in filter_obj.nis_history
        if entry["source"] == "depth"
    ]
    return {
        "run_id": f"{scenario_name}__seed{seed}__{timing_variant}",
        "scenario": scenario_name,
        "seed": seed,
        "mpc_mode": "not_applicable",
        "status": "ok",
        "duration_s": duration_s,
        "dt_s": dt,
        "timing_variant": timing_variant,
        **timing,
        "depth_phase_s": depth_phase * dt,
        "depth_spike_count": depth_spikes,
        "xy_rmse_m": float(np.sqrt(np.mean(xy_error * xy_error))),
        "rmse_3d_m": float(np.sqrt(np.mean(distance * distance))),
        "velocity_rmse_mps": float(np.sqrt(np.mean(speed_error * speed_error))),
        "max_drift_m": float(np.max(distance)),
        "final_drift_m": float(distance[-1]),
        "dvl_nis_mean": float(np.mean(dvl_nis)) if dvl_nis else math.nan,
        "dvl_nis_p95": float(np.percentile(dvl_nis, 95)) if dvl_nis else math.nan,
        "depth_nis_mean": float(np.mean(depth_nis)) if depth_nis else math.nan,
        **prefix_errors(
            estimates_array,
            trajectory.p,
            trajectory.times,
        ),
        "effective_sample_count": int(trajectory.times.size),
        "failure_event_count": 0,
        "capability_gate_status": "not_applicable_offline_ekf",
        "solver_wall_time_current_ms": "not_applicable",
        "fallback_type": "not_applicable",
    }


def summarize_r18(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[(str(row["scenario"]), str(row["timing_variant"]))].append(row)
    metrics = (
        "xy_rmse_m",
        "rmse_3d_m",
        "velocity_rmse_mps",
        "max_drift_m",
        "dvl_retained_rate",
        "dvl_max_gap_s",
        "dvl_nis_mean",
        "depth_nis_mean",
        "rmse_3d_60s_m",
        "rmse_3d_120s_m",
        "rmse_3d_300s_m",
    )
    summary: list[dict[str, object]] = []
    for (scenario, timing_variant), group in sorted(grouped.items()):
        item: dict[str, object] = {
            "scenario": scenario,
            "timing_variant": timing_variant,
            "run_count": len(group),
        }
        for metric in metrics:
            values = np.asarray([float(row[metric]) for row in group])
            item[f"{metric}_mean"] = float(np.nanmean(values))
            item[f"{metric}_std"] = float(np.nanstd(values))
        gaps = np.asarray([float(row["dvl_max_gap_s"]) for row in group])
        errors = np.asarray([float(row["rmse_3d_m"]) for row in group])
        item["gap_rmse_correlation"] = (
            float(np.corrcoef(gaps, errors)[0, 1])
            if np.std(gaps) > 0.0 and np.std(errors) > 0.0
            else math.nan
        )
        summary.append(item)
    by_scenario_seed: dict[tuple[str, int], dict[str, float]] = defaultdict(dict)
    for row in rows:
        by_scenario_seed[(str(row["scenario"]), int(row["seed"]))][
            str(row["timing_variant"])
        ] = float(row["rmse_3d_m"])
    phase_deltas: dict[str, list[float]] = defaultdict(list)
    for (scenario, _seed), values in by_scenario_seed.items():
        if {"phase_0ms", "phase_100ms"} <= values.keys():
            phase_deltas[scenario].append(
                abs(values["phase_100ms"] - values["phase_0ms"])
            )
    for item in summary:
        deltas = phase_deltas[str(item["scenario"])]
        item["paired_phase_rmse_delta_mean_m"] = float(np.mean(deltas))
        item["paired_phase_rmse_delta_max_m"] = float(np.max(deltas))
    return summary


def plot_r18(output_dir: Path, rows: list[dict[str, object]]) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(10.0, 4.2), dpi=180)
    scenarios = list(R18_SCENARIOS)
    for scenario in scenarios:
        group = [
            row
            for row in rows
            if row["scenario"] == scenario
            and row["timing_variant"] == "phase_0ms"
        ]
        axes[0].scatter(
            [float(row["dvl_max_gap_s"]) for row in group],
            [float(row["rmse_3d_m"]) for row in group],
            label=scenario,
        )
        axes[1].plot(
            [60, 120, 300],
            [
                np.mean([float(row[f"rmse_3d_{horizon}s_m"]) for row in group])
                for horizon in (60, 120, 300)
            ],
            "o-",
            label=scenario,
        )
    axes[0].set_xlabel("Longest DVL observation gap (s)")
    axes[0].set_ylabel("300 s 3D RMSE (m)")
    axes[1].set_xlabel("Evaluation horizon (s)")
    axes[1].set_ylabel("3D RMSE (m)")
    for axis in axes:
        axis.grid(alpha=0.25)
        axis.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(output_dir / "figures/r18_timing_duration_sensitivity.png")
    plt.close(fig)


def run_r18(output_dir: Path, seeds: list[int], duration_s: float, dt: float) -> None:
    initialize_bundle(
        output_dir,
        experiment_id="r18_es_ekf_long_horizon",
        runner="tools/es_ekf_long_horizon_replay.py",
        argv=sys.argv,
        data_layer="offline_es_ekf_dynamics",
        matrix={
            "scenarios": list(R18_SCENARIOS),
            "timing_variants": ["phase_0ms", "phase_100ms"],
            "seeds": seeds,
            "duration_s": duration_s,
        },
        duration_s=duration_s,
        config_paths=[
            Path(__file__),
            REPO_ROOT / "algorithm/es_ekf.py",
            REPO_ROOT / "scenarios/scenario_baseline.yaml",
            REPO_ROOT / "scenarios/scenario_dvl_dropout_60.yaml",
            REPO_ROOT / "scenarios/scenario_combined_stress.yaml",
        ],
        extra_manifest={"hardware_claim": False, "minimum_duration_s": 300},
    )
    timing_variants = (("phase_0ms", 0), ("phase_100ms", 2))
    rows = [
        run_r18_case(
            scenario_name=scenario_name,
            scenario=scenario,
            seed=seed,
            duration_s=duration_s,
            dt=dt,
            timing_variant=timing_variant,
            phase_steps=phase_steps,
        )
        for scenario_name, scenario in R18_SCENARIOS.items()
        for seed in seeds
        for timing_variant, phase_steps in timing_variants
    ]
    finalize_bundle(output_dir, rows)
    summary = summarize_r18(rows)
    write_csv(output_dir / "summary_by_scenario.csv", summary)
    plot_r18(output_dir, rows)
    lines = [
        "# R18 ES-EKF Long-Horizon and Observation-Timing Sensitivity",
        "",
        "| scenario | timing | runs | 3D RMSE mean | max drift mean | DVL retained | max gap | paired phase delta |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in summary:
        lines.append(
            f"| {row['scenario']} | {row['timing_variant']} | {row['run_count']} | "
            f"{float(row['rmse_3d_m_mean']):.4f} | "
            f"{float(row['max_drift_m_mean']):.4f} | "
            f"{float(row['dvl_retained_rate_mean']):.3f} | "
            f"{float(row['dvl_max_gap_s_mean']):.2f} | "
            f"{float(row['paired_phase_rmse_delta_mean_m']):.3f} |"
        )
    lines.extend(
        [
            "",
            f"Each run is {duration_s:.0f} s. The 0/100 ms DVL phases use the "
            "same seed-specific sensor noise, so their within-seed difference "
            "isolates observation timing. Clustered dropout timing is retained "
            "as a second explanatory variable; scenario severity alone is not "
            "assumed to order state error monotonically.",
            "",
        ]
    )
    (output_dir / "report.md").write_text("\n".join(lines), encoding="utf-8")


def run_r19_case(
    *,
    mode: str,
    seed: int,
    duration_s: float,
    dt: float,
    noise_t: np.ndarray,
    source_rate_hz: float,
) -> dict[str, object]:
    trajectory = generate_trajectory(duration_s, dt)
    sample_count = trajectory.times.size
    sensor_rng = np.random.default_rng(seed + 19100)
    gaussian_rng = np.random.default_rng(seed + 19200)
    timing_rng = np.random.default_rng(seed + 19300)
    acc_noise = sensor_rng.normal(0.0, 0.008, size=(sample_count, 3))
    gyro_noise = sensor_rng.normal(0.0, 0.001, size=(sample_count, 3))
    dvl_noise = sensor_rng.normal(0.0, 0.005, size=(sample_count, 3))
    depth_noise = sensor_rng.normal(0.0, 0.01, size=sample_count)
    profile = profile_by_name("none")
    config = ekf_config(profile, trajectory)
    config["feature_flags"] = {"enable_mag_correction": True}
    config["sigma_mag_depth"] = 0.20
    filter_obj = ES_EKF(config)
    covariance = np.cov(noise_t, rowvar=False)
    gaussian_noise = gaussian_rng.multivariate_normal(
        np.zeros(3),
        covariance,
        size=sample_count,
    )
    phase = int(timing_rng.integers(0, noise_t.shape[0]))
    source_step = source_rate_hz * dt
    dvl_stride = max(1, int(round(0.2 / dt)))
    depth_stride = max(1, int(round(1.0 / dt)))
    distance_errors: list[float] = []
    estimates: list[np.ndarray] = []

    for index, time_s in enumerate(trajectory.times):
        if index > 0:
            filter_obj.predict(
                trajectory.acc_body[index] + acc_noise[index],
                trajectory.gyro_body[index] + gyro_noise[index],
                dt,
            )
        if index % dvl_stride == 0:
            rotation = quat_to_rotmat(trajectory.q[index])
            body_velocity = rotation.T @ trajectory.v[index]
            filter_obj.correct_dvl_sensor(
                body_velocity + dvl_noise[index],
                gyro_body=trajectory.gyro_body[index],
            )
        if index % depth_stride == 0:
            filter_obj.correct_depth(
                float(-trajectory.p[index, 2] + depth_noise[index])
            )

        true_distance = float(-trajectory.p[index, 2])
        field_magnitude = 2e-7 * 500.0 / true_distance
        nominal_field = np.array([0.0, field_magnitude, 0.0])
        if mode == "measured_replay":
            source_index = (phase + int(round(index * source_step))) % noise_t.shape[0]
            noise_sample = noise_t[source_index]
        elif mode == "covariance_matched_gaussian":
            noise_sample = gaussian_noise[index]
        else:
            raise ValueError(f"unknown R19 mode: {mode}")
        measured_field = nominal_field + noise_sample
        measured_norm = max(float(np.linalg.norm(measured_field)), 1e-12)
        measured_distance = 2e-7 * 500.0 / measured_norm
        distance_errors.append(measured_distance - true_distance)
        filter_obj.correct_mag(measured_field)
        estimates.append(filter_obj.get_state()["p"].copy())

    estimate = np.asarray(estimates)
    position_error = estimate - trajectory.p
    distance_error = np.asarray(distance_errors)
    z_error = position_error[:, 2]
    mag_nis = [
        float(entry["nis"])
        for entry in filter_obj.nis_history
        if entry["source"] == "mag"
    ]
    return {
        "run_id": f"{mode}__seed{seed}",
        "scenario": "magnetic_background_replay",
        "seed": seed,
        "mpc_mode": "not_applicable",
        "status": "ok",
        "noise_mode": mode,
        "duration_s": duration_s,
        "replay_phase_index": phase,
        "replay_cycle_count": duration_s
        / (noise_t.shape[0] / source_rate_hz),
        "distance_error_rmse_m": float(
            np.sqrt(np.mean(distance_error * distance_error))
        ),
        "distance_error_bias_m": float(np.mean(distance_error)),
        "distance_error_p95_abs_m": float(
            np.percentile(np.abs(distance_error), 95)
        ),
        "z_rmse_m": float(np.sqrt(np.mean(z_error * z_error))),
        "rmse_3d_m": float(
            np.sqrt(np.mean(np.sum(position_error * position_error, axis=1)))
        ),
        "mag_nis_mean": float(np.mean(mag_nis)),
        "mag_nis_p95": float(np.percentile(mag_nis, 95)),
        "effective_sample_count": int(trajectory.times.size),
        "failure_event_count": 0,
        "capability_gate_status": "not_applicable_offline_ekf",
        "solver_wall_time_current_ms": "not_applicable",
        "fallback_type": "not_applicable",
    }


def summarize_r19(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["noise_mode"])].append(row)
    metrics = (
        "distance_error_rmse_m",
        "distance_error_bias_m",
        "distance_error_p95_abs_m",
        "z_rmse_m",
        "rmse_3d_m",
        "mag_nis_mean",
        "mag_nis_p95",
    )
    summary: list[dict[str, object]] = []
    for mode, group in sorted(grouped.items()):
        item: dict[str, object] = {"noise_mode": mode, "run_count": len(group)}
        for metric in metrics:
            values = np.asarray([float(row[metric]) for row in group])
            item[f"{metric}_mean"] = float(np.mean(values))
            item[f"{metric}_std"] = float(np.std(values))
        summary.append(item)
    return summary


def plot_r19(output_dir: Path, summary: list[dict[str, object]]) -> None:
    labels = [str(row["noise_mode"]).replace("_", "\n") for row in summary]
    distance = [float(row["distance_error_rmse_m_mean"]) for row in summary]
    nis = [float(row["mag_nis_mean_mean"]) for row in summary]
    fig, axes = plt.subplots(1, 2, figsize=(8.5, 4.0), dpi=180)
    axes[0].bar(labels, distance, color=["#4C78A8", "#F58518"])
    axes[0].set_ylabel("Magnetic distance RMSE (m)")
    axes[1].bar(labels, nis, color=["#4C78A8", "#F58518"])
    axes[1].set_ylabel("Magnetic NIS mean")
    for axis in axes:
        axis.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(output_dir / "figures/r19_gaussian_vs_measured_replay.png")
    plt.close(fig)


def run_r19(
    output_dir: Path,
    seeds: list[int],
    duration_s: float,
    dt: float,
    noise_path: Path,
) -> None:
    noise_t, source_rate_hz, characterization = load_measured_noise(noise_path)
    initialize_bundle(
        output_dir,
        experiment_id="r19_measured_magnetic_noise_replay",
        runner="tools/es_ekf_long_horizon_replay.py",
        argv=sys.argv,
        data_layer="measured_noise_offline_replay",
        matrix={
            "noise_modes": [
                "covariance_matched_gaussian",
                "measured_replay",
            ],
            "seeds": seeds,
            "duration_s": duration_s,
        },
        duration_s=duration_s,
        config_paths=[
            Path(__file__),
            REPO_ROOT / "algorithm/es_ekf.py",
            noise_path,
        ],
        extra_manifest={
            "hardware_claim": False,
            "source_recording_duration_s": characterization["duration_s"],
            "replay_is_cyclic": True,
        },
    )
    modes = ("covariance_matched_gaussian", "measured_replay")
    rows = [
        run_r19_case(
            mode=mode,
            seed=seed,
            duration_s=duration_s,
            dt=dt,
            noise_t=noise_t,
            source_rate_hz=source_rate_hz,
        )
        for mode in modes
        for seed in seeds
    ]
    finalize_bundle(output_dir, rows)
    summary = summarize_r19(rows)
    write_csv(output_dir / "summary_by_noise_mode.csv", summary)
    (output_dir / "noise_characterization.json").write_text(
        json.dumps(characterization, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    plot_r19(output_dir, summary)
    lines = [
        "# R19 Measured 45 Hz Background-Noise Replay",
        "",
        f"- Source duration: `{float(characterization['duration_s']):.3f} s`",
        f"- Source rate: `{float(characterization['sample_rate_hz']):.1f} Hz`",
        "- Conversion: per-axis voltage / sensitivity, then mean centering only.",
        "- Gaussian comparator: identical three-axis covariance, no temporal structure.",
        "- Replay: original three-axis samples, shared phase, cyclic continuation.",
        "",
        "| noise mode | runs | distance RMSE | RMSE std | distance p95 | Z RMSE | mag NIS mean | NIS std |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in summary:
        lines.append(
            f"| {row['noise_mode']} | {row['run_count']} | "
            f"{float(row['distance_error_rmse_m_mean']):.4f} | "
            f"{float(row['distance_error_rmse_m_std']):.4f} | "
            f"{float(row['distance_error_p95_abs_m_mean']):.4f} | "
            f"{float(row['z_rmse_m_mean']):.4f} | "
            f"{float(row['mag_nis_mean_mean']):.3f} | "
            f"{float(row['mag_nis_mean_std']):.3f} |"
        )
    lines.extend(
        [
            "",
            "This is a measured-noise replay, not a complete Sim-to-Real "
            "experiment. The short recording is repeated cyclically, so it "
            "preserves within-record three-axis correlation, drift and spectrum "
            "but cannot establish long-term stationarity.",
            "",
        ]
    )
    (output_dir / "report.md").write_text("\n".join(lines), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment", choices=("r18", "r19", "both"), default="both")
    parser.add_argument("--seeds", default="0,1,2,3,4")
    parser.add_argument("--r18-duration", type=float, default=300.0)
    parser.add_argument("--r18-dt", type=float, default=0.05)
    parser.add_argument("--r19-duration", type=float, default=60.0)
    parser.add_argument("--r19-dt", type=float, default=0.01)
    parser.add_argument("--noise-path", type=Path, default=DEFAULT_NOISE_PATH)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=REPO_ROOT / "results/state_estimation",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    seeds = [int(value) for value in args.seeds.split(",") if value.strip()]
    if args.experiment in {"r18", "both"}:
        output = args.output_root / "r18_long_horizon/20260809_r18"
        print(f"[R18] output={output}", flush=True)
        run_r18(output, seeds, args.r18_duration, args.r18_dt)
    if args.experiment in {"r19", "both"}:
        output = args.output_root / "r19_measured_noise_replay/20260809_r19"
        print(f"[R19] output={output}", flush=True)
        run_r19(
            output,
            seeds,
            args.r19_duration,
            args.r19_dt,
            args.noise_path.resolve(),
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

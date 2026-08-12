#!/usr/bin/env python3
"""Attribute residuals in the archived 45 Hz TMR-ArUco Biot-Savart fit."""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np


AXES = ("x", "y", "z")
DEFAULT_BUNDLE = Path(
    "hardware_wrappers/fangkong_adc/raw_data/joint_analysis/1783235358_205719"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Post-hoc residual attribution for the archived 45 Hz "
            "TMR/SK2301-ArUco joint Biot-Savart fit."
        )
    )
    parser.add_argument(
        "--aligned-npz",
        type=Path,
        default=DEFAULT_BUNDLE / "aligned_timeseries.npz",
        help="Archived aligned time series containing measured and modeled complex I/Q.",
    )
    parser.add_argument(
        "--fit-summary",
        type=Path,
        default=DEFAULT_BUNDLE / "fit_summary.json",
        help="Archived joint fit summary JSON.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Directory for machine-readable attribution outputs and plots.",
    )
    parser.add_argument(
        "--lag-window-count",
        type=int,
        default=10,
        help="Maximum +/- window shift for the time-lag attribution probe.",
    )
    return parser.parse_args()


def finite_pearson(x: np.ndarray, y: np.ndarray) -> float:
    mask = np.isfinite(x) & np.isfinite(y)
    if int(np.sum(mask)) < 3:
        return float("nan")
    x0 = x[mask] - float(np.mean(x[mask]))
    y0 = y[mask] - float(np.mean(y[mask]))
    denom = float(np.linalg.norm(x0) * np.linalg.norm(y0))
    if denom <= 1.0e-12:
        return float("nan")
    return float(np.dot(x0, y0) / denom)


def quantiles(values: np.ndarray) -> dict[str, float]:
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return {name: float("nan") for name in ("p50", "p90", "p95", "p99", "max")}
    return {
        "p50": float(np.quantile(finite, 0.50)),
        "p90": float(np.quantile(finite, 0.90)),
        "p95": float(np.quantile(finite, 0.95)),
        "p99": float(np.quantile(finite, 0.99)),
        "max": float(np.max(finite)),
    }


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def group_metrics(
    name: str,
    mask: np.ndarray,
    residual: np.ndarray,
    measured: np.ndarray,
    predicted: np.ndarray,
    distance_m: np.ndarray,
    total_sse: float,
) -> dict[str, Any]:
    count = int(np.sum(mask))
    if count == 0:
        return {
            "group": name,
            "sample_count": 0,
            "component_rmse_ut": float("nan"),
            "vector_rmse_ut": float("nan"),
            "sse_fraction": float("nan"),
        }
    res = residual[mask]
    meas = measured[mask]
    pred = predicted[mask]
    dist = distance_m[mask]
    sse = float(np.sum(np.abs(res) ** 2))
    vector_residual = np.linalg.norm(res, axis=1)
    measured_norm = np.linalg.norm(meas, axis=1)
    relative_residual = vector_residual / np.maximum(measured_norm, 1.0e-12)
    return {
        "group": name,
        "sample_count": count,
        "distance_min_m": float(np.min(dist)),
        "distance_max_m": float(np.max(dist)),
        "distance_mean_m": float(np.mean(dist)),
        "component_rmse_ut": float(np.sqrt(np.mean(np.abs(res) ** 2))),
        "vector_rmse_ut": float(np.sqrt(np.mean(vector_residual**2))),
        "vector_residual_p95_ut": quantiles(vector_residual)["p95"],
        "relative_residual_median": float(np.median(relative_residual)),
        "relative_residual_p95": quantiles(relative_residual)["p95"],
        "measured_vector_mean_ut": float(np.mean(measured_norm)),
        "predicted_vector_mean_ut": float(np.mean(np.linalg.norm(pred, axis=1))),
        "sse": sse,
        "sse_fraction": sse / total_sse if total_sse > 0.0 else float("nan"),
    }


def fit_complex_gain(
    predicted: np.ndarray,
    measured: np.ndarray,
    *,
    per_axis: bool,
) -> tuple[np.ndarray, np.ndarray, float]:
    if per_axis:
        gains = []
        adjusted = np.empty_like(predicted)
        for axis_index in range(predicted.shape[1]):
            p = predicted[:, axis_index]
            m = measured[:, axis_index]
            denom = np.vdot(p, p)
            gain = np.vdot(p, m) / denom if abs(denom) > 1.0e-12 else 1.0 + 0.0j
            gains.append(gain)
            adjusted[:, axis_index] = gain * p
        gain_array = np.asarray(gains, dtype=complex)
    else:
        denom = np.vdot(predicted.ravel(), predicted.ravel())
        gain = (
            np.vdot(predicted.ravel(), measured.ravel()) / denom
            if abs(denom) > 1.0e-12
            else 1.0 + 0.0j
        )
        gain_array = np.asarray([gain], dtype=complex)
        adjusted = gain * predicted
    sse = float(np.sum(np.abs(adjusted - measured) ** 2))
    return gain_array, adjusted, sse


def affine_per_axis(predicted: np.ndarray, measured: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, float]:
    gains = []
    offsets = []
    adjusted = np.empty_like(predicted)
    for axis_index in range(predicted.shape[1]):
        p = predicted[:, axis_index]
        m = measured[:, axis_index]
        design = np.column_stack([p, np.ones_like(p)])
        params, *_ = np.linalg.lstsq(design, m, rcond=None)
        gains.append(params[0])
        offsets.append(params[1])
        adjusted[:, axis_index] = design @ params
    sse = float(np.sum(np.abs(adjusted - measured) ** 2))
    return (
        np.asarray(gains, dtype=complex),
        np.asarray(offsets, dtype=complex),
        adjusted,
        sse,
    )


def lag_probe(
    predicted: np.ndarray,
    measured: np.ndarray,
    timestamps: np.ndarray,
    window_count: int,
) -> list[dict[str, Any]]:
    rows = []
    for shift in range(-window_count, window_count + 1):
        if shift < 0:
            pred = predicted[-shift:]
            meas = measured[: predicted.shape[0] + shift]
        elif shift > 0:
            pred = predicted[: predicted.shape[0] - shift]
            meas = measured[shift:]
        else:
            pred = predicted
            meas = measured
        if pred.size == 0 or meas.size == 0:
            continue
        residual = pred - meas
        rows.append(
            {
                "shift_windows": shift,
                "shift_s": float(shift * np.median(np.diff(timestamps))),
                "overlap_count": int(pred.shape[0]),
                "component_rmse_ut": float(np.sqrt(np.mean(np.abs(residual) ** 2))),
                "sse": float(np.sum(np.abs(residual) ** 2)),
            }
        )
    return rows


def run(args: argparse.Namespace) -> dict[str, Any]:
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    with np.load(args.aligned_npz, allow_pickle=False) as archive:
        timestamps = np.asarray(archive["timestamp"], dtype=float)
        positions = np.asarray(archive["tmr_position_m"], dtype=float)
        measured = np.asarray(archive["complex_phasor_real_ut"], dtype=float) + 1j * np.asarray(
            archive["complex_phasor_imag_ut"], dtype=float
        )
        predicted = np.asarray(archive["complex_model_real_ut"], dtype=float) + 1j * np.asarray(
            archive["complex_model_imag_ut"], dtype=float
        )
        distance_m = np.asarray(archive["complex_fitted_wire_distance_m"], dtype=float)

    fit_summary = json.loads(args.fit_summary.read_text(encoding="utf-8"))
    residual = predicted - measured
    sample_count = int(residual.shape[0])
    component_count = int(residual.size)
    total_sse = float(np.sum(np.abs(residual) ** 2))
    component_rmse = float(np.sqrt(np.mean(np.abs(residual) ** 2)))
    vector_residual = np.linalg.norm(residual, axis=1)
    vector_rmse = float(np.sqrt(np.mean(vector_residual**2)))
    measured_vector = np.linalg.norm(measured, axis=1)
    predicted_vector = np.linalg.norm(predicted, axis=1)
    centered = measured - np.mean(measured, axis=0)
    total_variation = float(np.sum(np.abs(centered) ** 2))
    complex_r2 = 1.0 - total_sse / total_variation if total_variation > 1.0e-12 else float("nan")

    axis_rows = []
    for axis_index, axis_name in enumerate(AXES):
        axis_residual = residual[:, axis_index]
        axis_sse = float(np.sum(np.abs(axis_residual) ** 2))
        real_sse = float(np.sum(axis_residual.real**2))
        imag_sse = float(np.sum(axis_residual.imag**2))
        axis_rows.append(
            {
                "axis": axis_name,
                "sample_count": sample_count,
                "complex_rmse_ut": float(np.sqrt(np.mean(np.abs(axis_residual) ** 2))),
                "real_rmse_ut": float(np.sqrt(np.mean(axis_residual.real**2))),
                "imag_rmse_ut": float(np.sqrt(np.mean(axis_residual.imag**2))),
                "complex_sse_fraction": axis_sse / total_sse,
                "real_sse_fraction": real_sse / total_sse,
                "imag_sse_fraction": imag_sse / total_sse,
                "residual_real_bias_ut": float(np.mean(axis_residual.real)),
                "residual_imag_bias_ut": float(np.mean(axis_residual.imag)),
            }
        )
    write_csv(output_dir / "residual_by_axis_component.csv", axis_rows)

    pred_energy = np.sum(np.abs(predicted) ** 2, axis=1)
    alpha = np.zeros(sample_count, dtype=complex)
    valid_pred = pred_energy > 1.0e-12
    alpha[valid_pred] = np.sum(np.conj(predicted[valid_pred]) * residual[valid_pred], axis=1) / pred_energy[valid_pred]
    parallel = alpha[:, None] * predicted
    orthogonal = residual - parallel
    parallel_sse = float(np.sum(np.abs(parallel) ** 2))
    orthogonal_sse = float(np.sum(np.abs(orthogonal) ** 2))

    _, common_gain_adjusted, common_gain_sse = fit_complex_gain(
        predicted, measured, per_axis=False
    )
    per_axis_gain, per_axis_gain_adjusted, per_axis_gain_sse = fit_complex_gain(
        predicted, measured, per_axis=True
    )
    offsets = np.mean(measured - predicted, axis=0)
    offset_adjusted = predicted + offsets[None, :]
    offset_sse = float(np.sum(np.abs(offset_adjusted - measured) ** 2))
    affine_gain, affine_offset, _, affine_sse = affine_per_axis(predicted, measured)

    explanation_rows = [
        {
            "model": "archived_common_complex_scale",
            "component_rmse_ut": component_rmse,
            "sse": total_sse,
            "residual_sse_reduction_fraction": 0.0,
        },
        {
            "model": "posthoc_common_complex_gain",
            "component_rmse_ut": float(np.sqrt(common_gain_sse / component_count)),
            "sse": common_gain_sse,
            "residual_sse_reduction_fraction": 1.0 - common_gain_sse / total_sse,
        },
        {
            "model": "posthoc_per_axis_complex_gain",
            "component_rmse_ut": float(np.sqrt(per_axis_gain_sse / component_count)),
            "sse": per_axis_gain_sse,
            "residual_sse_reduction_fraction": 1.0 - per_axis_gain_sse / total_sse,
        },
        {
            "model": "posthoc_per_axis_complex_offset",
            "component_rmse_ut": float(np.sqrt(offset_sse / component_count)),
            "sse": offset_sse,
            "residual_sse_reduction_fraction": 1.0 - offset_sse / total_sse,
        },
        {
            "model": "posthoc_per_axis_gain_plus_offset",
            "component_rmse_ut": float(np.sqrt(affine_sse / component_count)),
            "sse": affine_sse,
            "residual_sse_reduction_fraction": 1.0 - affine_sse / total_sse,
        },
    ]
    write_csv(output_dir / "residual_explanation_models.csv", explanation_rows)

    distance_edges = np.quantile(distance_m, [0.0, 1.0 / 3.0, 2.0 / 3.0, 1.0])
    distance_rows = []
    for index, label in enumerate(("near", "mid", "far")):
        lo = distance_edges[index]
        hi = distance_edges[index + 1]
        if index == 2:
            mask = (distance_m >= lo) & (distance_m <= hi)
        else:
            mask = (distance_m >= lo) & (distance_m < hi)
        distance_rows.append(
            group_metrics(
                f"{label}_{lo:.3f}_{hi:.3f}m",
                mask,
                residual,
                measured,
                predicted,
                distance_m,
                total_sse,
            )
        )
    write_csv(output_dir / "residual_by_distance_bin.csv", distance_rows)

    rel_t = timestamps - timestamps[0]
    time_edges = np.quantile(rel_t, [0.0, 0.25, 0.50, 0.75, 1.0])
    time_rows = []
    for index in range(4):
        lo = time_edges[index]
        hi = time_edges[index + 1]
        mask = (rel_t >= lo) & ((rel_t <= hi) if index == 3 else (rel_t < hi))
        time_rows.append(
            group_metrics(
                f"q{index + 1}_{lo:.2f}_{hi:.2f}s",
                mask,
                residual,
                measured,
                predicted,
                distance_m,
                total_sse,
            )
        )
    write_csv(output_dir / "residual_by_time_bin.csv", time_rows)

    axis_unit = np.asarray(fit_summary["complex_iq_free_scale"]["axis_unit"], dtype=float)
    axis_unit /= max(float(np.linalg.norm(axis_unit)), 1.0e-12)
    velocity = np.gradient(positions, timestamps, axis=0)
    along_axis_speed = velocity @ axis_unit
    speed_abs = np.linalg.norm(velocity, axis=1)
    stationary = speed_abs < 0.01
    lateral_or_slow = (np.abs(along_axis_speed) <= 0.01) & ~stationary
    motion_rows = []
    for name, mask in (
        ("reverse_along_axis", along_axis_speed < -0.01),
        ("stationary_or_slow", stationary),
        ("lateral_or_low_axis_speed", lateral_or_slow),
        ("forward_along_axis", along_axis_speed > 0.01),
    ):
        motion_rows.append(
            group_metrics(
                name,
                mask,
                residual,
                measured,
                predicted,
                distance_m,
                total_sse,
            )
        )
    write_csv(output_dir / "residual_by_motion_bin.csv", motion_rows)

    lag_rows = lag_probe(predicted, measured, timestamps, args.lag_window_count)
    write_csv(output_dir / "residual_time_lag_probe.csv", lag_rows)
    best_lag = min(lag_rows, key=lambda row: row["component_rmse_ut"])
    zero_lag = next(row for row in lag_rows if row["shift_windows"] == 0)

    timeseries_rows = []
    for index in range(sample_count):
        row: dict[str, Any] = {
            "sample_index": index,
            "timestamp": float(timestamps[index]),
            "relative_time_s": float(rel_t[index]),
            "distance_m": float(distance_m[index]),
            "speed_mps": float(speed_abs[index]),
            "along_axis_speed_mps": float(along_axis_speed[index]),
            "measured_vector_ut": float(measured_vector[index]),
            "predicted_vector_ut": float(predicted_vector[index]),
            "vector_residual_ut": float(vector_residual[index]),
            "parallel_residual_ut": float(np.linalg.norm(parallel[index])),
            "orthogonal_residual_ut": float(np.linalg.norm(orthogonal[index])),
            "parallel_fraction": (
                float(np.linalg.norm(parallel[index]) ** 2 / (vector_residual[index] ** 2))
                if vector_residual[index] > 1.0e-12
                else float("nan")
            ),
        }
        for axis_index, axis_name in enumerate(AXES):
            row[f"{axis_name}_real_residual_ut"] = float(residual[index, axis_index].real)
            row[f"{axis_name}_imag_residual_ut"] = float(residual[index, axis_index].imag)
        timeseries_rows.append(row)
    write_csv(output_dir / "residual_attribution_timeseries.csv", timeseries_rows)

    fig, ax = plt.subplots(figsize=(8.0, 4.8))
    labels = [f"{row['axis'].upper()} Re" for row in axis_rows] + [
        f"{row['axis'].upper()} Im" for row in axis_rows
    ]
    fractions = [row["real_sse_fraction"] for row in axis_rows] + [
        row["imag_sse_fraction"] for row in axis_rows
    ]
    ax.bar(labels, np.asarray(fractions) * 100.0)
    ax.set_ylabel("Residual energy contribution [%]")
    ax.set_title("45 Hz complex fit residual by axis/component")
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(output_dir / "residual_axis_component_breakdown.png", dpi=200)
    fig.savefig(output_dir / "residual_axis_component_breakdown.pdf")
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(8.0, 4.8))
    scatter = ax.scatter(
        distance_m,
        vector_residual,
        c=rel_t,
        s=12,
        cmap="viridis",
        alpha=0.8,
    )
    ax.set_xlabel("Fitted wire distance [m]")
    ax.set_ylabel("Complex vector residual [uT]")
    ax.set_title("Residual vs fitted wire distance")
    ax.grid(True, alpha=0.3)
    cbar = fig.colorbar(scatter, ax=ax)
    cbar.set_label("Relative time [s]")
    fig.tight_layout()
    fig.savefig(output_dir / "residual_vs_distance.png", dpi=200)
    fig.savefig(output_dir / "residual_vs_distance.pdf")
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(9.0, 4.8))
    ax.plot(rel_t, vector_residual, linewidth=1.0, label="total")
    ax.plot(rel_t, np.linalg.norm(parallel, axis=1), linewidth=0.9, label="parallel")
    ax.plot(rel_t, np.linalg.norm(orthogonal, axis=1), linewidth=0.9, label="orthogonal")
    ax.set_xlabel("Relative time [s]")
    ax.set_ylabel("Complex vector residual [uT]")
    ax.set_title("Residual decomposition over trajectory")
    ax.grid(True, alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(output_dir / "residual_parallel_orthogonal_timeseries.png", dpi=200)
    fig.savefig(output_dir / "residual_parallel_orthogonal_timeseries.pdf")
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(8.0, 4.8))
    ax.plot(
        [row["shift_s"] for row in lag_rows],
        [row["component_rmse_ut"] for row in lag_rows],
        marker="o",
    )
    ax.axvline(0.0, color="black", linewidth=0.8, linestyle="--")
    ax.set_xlabel("Model-to-measurement shift [s]")
    ax.set_ylabel("Component RMSE [uT]")
    ax.set_title("Time-lag residual probe")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(output_dir / "residual_time_lag_probe.png", dpi=200)
    fig.savefig(output_dir / "residual_time_lag_probe.pdf")
    plt.close(fig)

    summary: dict[str, Any] = {
        "schema_version": 1,
        "inputs": {
            "aligned_npz": str(args.aligned_npz.resolve()),
            "fit_summary": str(args.fit_summary.resolve()),
        },
        "frequency_contract": {
            "excitation_hz": float(fit_summary["constants"]["lockin_frequency_hz"]),
            "reference_hz": float(fit_summary["constants"]["lockin_frequency_hz"]),
            "source": "archived_fit_summary",
        },
        "sample_count": sample_count,
        "complex_r2_recomputed": complex_r2,
        "component_rmse_ut": component_rmse,
        "vector_rmse_ut": vector_rmse,
        "vector_residual_quantiles_ut": quantiles(vector_residual),
        "parallel_residual_sse_fraction": parallel_sse / total_sse,
        "orthogonal_residual_sse_fraction": orthogonal_sse / total_sse,
        "axis_component_top_contributor": max(
            axis_rows,
            key=lambda row: row["complex_sse_fraction"],
        )["axis"],
        "distance_bin_top_contributor": max(
            distance_rows,
            key=lambda row: row["sse_fraction"],
        )["group"],
        "correlations": {
            "vector_residual_vs_distance": finite_pearson(vector_residual, distance_m),
            "vector_residual_vs_measured_magnitude": finite_pearson(vector_residual, measured_vector),
            "vector_residual_vs_predicted_magnitude": finite_pearson(vector_residual, predicted_vector),
            "vector_residual_vs_speed": finite_pearson(vector_residual, speed_abs),
            "vector_residual_vs_along_axis_speed": finite_pearson(vector_residual, along_axis_speed),
        },
        "posthoc_explanation": {
            "common_complex_gain_sse_reduction_fraction": 1.0 - common_gain_sse / total_sse,
            "per_axis_complex_gain_sse_reduction_fraction": 1.0 - per_axis_gain_sse / total_sse,
            "per_axis_complex_offset_sse_reduction_fraction": 1.0 - offset_sse / total_sse,
            "per_axis_gain_plus_offset_sse_reduction_fraction": 1.0 - affine_sse / total_sse,
            "per_axis_gain_abs": [float(abs(item)) for item in per_axis_gain],
            "per_axis_gain_phase_deg": [float(np.rad2deg(np.angle(item))) for item in per_axis_gain],
            "per_axis_offset_abs_ut": [float(abs(item)) for item in offsets],
            "affine_per_axis_gain_abs": [float(abs(item)) for item in affine_gain],
            "affine_per_axis_gain_phase_deg": [
                float(np.rad2deg(np.angle(item))) for item in affine_gain
            ],
            "affine_per_axis_offset_abs_ut": [float(abs(item)) for item in affine_offset],
        },
        "time_lag_probe": {
            "best_shift_windows": int(best_lag["shift_windows"]),
            "best_shift_s": float(best_lag["shift_s"]),
            "zero_lag_component_rmse_ut": float(zero_lag["component_rmse_ut"]),
            "best_lag_component_rmse_ut": float(best_lag["component_rmse_ut"]),
            "best_lag_rmse_reduction_fraction": 1.0
            - float(best_lag["component_rmse_ut"]) / float(zero_lag["component_rmse_ut"]),
        },
    }
    (output_dir / "residual_attribution_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    report = [
        "# 45 Hz Joint Residual Attribution",
        "",
        f"- Samples: `{sample_count}` aligned TMR-ArUco points.",
        f"- Recomputed complex R2: `{complex_r2:.6f}`.",
        f"- Component RMSE: `{component_rmse:.4f} uT`; vector RMSE: `{vector_rmse:.4f} uT`.",
        (
            f"- Residual energy split: parallel `{parallel_sse / total_sse:.3f}`, "
            f"orthogonal `{orthogonal_sse / total_sse:.3f}`."
        ),
        (
            f"- Per-axis complex gain explains "
            f"`{1.0 - per_axis_gain_sse / total_sse:.3f}` of residual SSE; "
            f"gain+offset explains `{1.0 - affine_sse / total_sse:.3f}`."
        ),
        (
            f"- Best lag probe shift: `{best_lag['shift_s']:.3f} s`, "
            f"RMSE reduction `{summary['time_lag_probe']['best_lag_rmse_reduction_fraction']:.3f}`."
        ),
        (
            f"- Residual-distance Pearson correlation: "
            f"`{summary['correlations']['vector_residual_vs_distance']:.3f}`."
        ),
        "",
        "Boundary: this is a post-hoc attribution of the archived straight-wire/common-complex-scale fit. "
        "It does not create new hardware data, does not validate armored three-phase subsea cables, "
        "and does not replace traceable current/distance calibration.",
        "",
    ]
    (output_dir / "report.md").write_text("\n".join(report), encoding="utf-8")
    return summary


def main() -> int:
    args = parse_args()
    summary = run(args)
    print(
        "[joint-residual] n={n} r2={r2:.6f} rmse={rmse:.4f}uT orthogonal={orth:.3f}".format(
            n=summary["sample_count"],
            r2=summary["complex_r2_recomputed"],
            rmse=summary["component_rmse_ut"],
            orth=summary["orthogonal_residual_sse_fraction"],
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Compare new headless lock-in output with the historical 777-point bundle."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np


AXES = ("x", "y", "z")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lockin-csv", type=Path, required=True)
    parser.add_argument("--aligned-npz", type=Path, required=True)
    parser.add_argument("--fit-summary", type=Path, required=True)
    parser.add_argument("--rerun-fit-summary", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def load_lockin(path: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    timestamps = np.asarray([float(row["timestamp"]) for row in rows])
    real = np.asarray(
        [[float(row[f"{axis}_i_ut"]) for axis in AXES] for row in rows]
    )
    imag = np.asarray(
        [[float(row[f"{axis}_q_ut"]) for axis in AXES] for row in rows]
    )
    return timestamps, real, imag


def nearest_indices(
    source_timestamps: np.ndarray,
    target_timestamps: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    indices = np.searchsorted(source_timestamps, target_timestamps)
    indices = np.clip(indices, 0, source_timestamps.size - 1)
    previous = np.clip(indices - 1, 0, source_timestamps.size - 1)
    use_previous = (
        np.abs(source_timestamps[previous] - target_timestamps)
        < np.abs(source_timestamps[indices] - target_timestamps)
    )
    indices = np.where(use_previous, previous, indices)
    offsets = source_timestamps[indices] - target_timestamps
    return indices, offsets


def error_metrics(actual: np.ndarray, expected: np.ndarray) -> dict[str, float]:
    residual = actual - expected
    denominator = float(np.sum((expected - np.mean(expected, axis=0)) ** 2))
    return {
        "rmse_ut": float(np.sqrt(np.mean(residual**2))),
        "max_abs_ut": float(np.max(np.abs(residual))),
        "r2": (
            1.0 - float(np.sum(residual**2)) / denominator
            if denominator > 0
            else float("nan")
        ),
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    lockin_path = args.lockin_csv.resolve()
    aligned_path = args.aligned_npz.resolve()
    fit_path = args.fit_summary.resolve()
    rerun_fit_path = (
        args.rerun_fit_summary.resolve()
        if args.rerun_fit_summary is not None
        else None
    )
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    new_timestamps, new_real, new_imag = load_lockin(lockin_path)
    with np.load(aligned_path, allow_pickle=False) as archive:
        old_timestamps = np.asarray(archive["timestamp"], dtype=float)
        old_real = np.asarray(archive["complex_phasor_real_ut"], dtype=float)
        old_imag = np.asarray(archive["complex_phasor_imag_ut"], dtype=float)
    fit_summary = json.loads(fit_path.read_text(encoding="utf-8"))
    rerun_fit_summary = (
        json.loads(rerun_fit_path.read_text(encoding="utf-8"))
        if rerun_fit_path is not None
        else None
    )
    indices, offsets = nearest_indices(new_timestamps, old_timestamps)
    matched_real = new_real[indices]
    matched_imag = new_imag[indices]
    real_metrics = error_metrics(matched_real, old_real)
    imag_metrics = error_metrics(matched_imag, old_imag)
    combined_actual = np.concatenate([matched_real, matched_imag], axis=1)
    combined_expected = np.concatenate([old_real, old_imag], axis=1)
    combined_metrics = error_metrics(combined_actual, combined_expected)

    comparison_path = output_dir / "joint_lockin_comparison.csv"
    fields = [
        "timestamp",
        "time_offset_s",
        *[
            f"{axis}_{component}_{quantity}"
            for axis in AXES
            for component in ("real", "imag")
            for quantity in ("new_ut", "historical_ut", "error_ut")
        ],
    ]
    with comparison_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row_index, timestamp in enumerate(old_timestamps):
            row: dict[str, object] = {
                "timestamp": float(timestamp),
                "time_offset_s": float(offsets[row_index]),
            }
            for axis_index, axis in enumerate(AXES):
                for component, actual, expected in (
                    ("real", matched_real, old_real),
                    ("imag", matched_imag, old_imag),
                ):
                    new_value = float(actual[row_index, axis_index])
                    old_value = float(expected[row_index, axis_index])
                    row[f"{axis}_{component}_new_ut"] = new_value
                    row[f"{axis}_{component}_historical_ut"] = old_value
                    row[f"{axis}_{component}_error_ut"] = new_value - old_value
            writer.writerow(row)

    residual = combined_actual - combined_expected
    fig, ax = plt.subplots(figsize=(9.0, 4.5))
    relative_time = old_timestamps - old_timestamps[0]
    for axis_index, axis in enumerate(AXES):
        ax.plot(
            relative_time,
            residual[:, axis_index],
            label=f"{axis.upper()} real",
        )
        ax.plot(
            relative_time,
            residual[:, axis_index + 3],
            linestyle="--",
            label=f"{axis.upper()} imag",
        )
    ax.set_xlabel("Aligned time [s]")
    ax.set_ylabel("New - historical phasor [uT]")
    ax.set_title("45 Hz lock-in reproduction residual")
    ax.legend(ncol=2)
    fig.tight_layout()
    fig.savefig(output_dir / "joint_lockin_reproduction_residual.png", dpi=200)
    fig.savefig(output_dir / "joint_lockin_reproduction_residual.pdf")
    plt.close(fig)

    geometry_comparison = None
    if rerun_fit_summary is not None:
        geometry_fields = {
            "free_complex_r2": (
                fit_summary["complex_iq_free_scale"]["complex_r2"],
                rerun_fit_summary["complex_iq_free_scale"]["complex_r2"],
            ),
            "free_equivalent_current_a": (
                fit_summary["complex_iq_free_scale"]["equivalent_current_a"],
                rerun_fit_summary["complex_iq_free_scale"]["equivalent_current_a"],
            ),
            "fixed_complex_r2": (
                fit_summary["complex_iq_fixed_current"]["complex_r2"],
                rerun_fit_summary["complex_iq_fixed_current"]["complex_r2"],
            ),
            "synthetic_complex_r2": (
                fit_summary["synthetic_identifiability_check"]["complex_r2"],
                rerun_fit_summary["synthetic_identifiability_check"]["complex_r2"],
            ),
        }
        geometry_comparison = {
            name: {
                "historical": float(values[0]),
                "rerun": float(values[1]),
                "absolute_difference": abs(float(values[1]) - float(values[0])),
            }
            for name, values in geometry_fields.items()
        }
        geometry_comparison["within_tolerance_1e_9"] = all(
            item["absolute_difference"] <= 1e-9
            for item in geometry_comparison.values()
            if isinstance(item, dict)
        )

    summary: dict[str, Any] = {
        "schema_version": 1,
        "inputs": {
            "lockin_csv": str(lockin_path),
            "lockin_csv_sha256": sha256_file(lockin_path),
            "aligned_npz": str(aligned_path),
            "aligned_npz_sha256": sha256_file(aligned_path),
            "fit_summary": str(fit_path),
            "fit_summary_sha256": sha256_file(fit_path),
            "rerun_fit_summary": (
                str(rerun_fit_path) if rerun_fit_path is not None else None
            ),
            "rerun_fit_summary_sha256": (
                sha256_file(rerun_fit_path)
                if rerun_fit_path is not None
                else None
            ),
        },
        "frequency_contract": {
            "excitation_hz": 45.0,
            "reference_hz": 45.0,
            "frequency_source": "recorded_metadata",
        },
        "aligned_count": int(old_timestamps.size),
        "unique_new_window_count": int(np.unique(indices).size),
        "max_abs_timestamp_offset_s": float(np.max(np.abs(offsets))),
        "real_component": real_metrics,
        "imag_component": imag_metrics,
        "combined_complex": combined_metrics,
        "historical_geometry_results": {
            "complex_r2_free_scale": fit_summary["complex_iq_free_scale"][
                "complex_r2"
            ],
            "complex_r2_fixed_current": fit_summary[
                "complex_iq_fixed_current"
            ]["complex_r2"],
            "synthetic_complex_r2": fit_summary[
                "synthetic_identifiability_check"
            ]["complex_r2"],
        },
        "geometry_fit_recomputed": rerun_fit_summary is not None,
        "geometry_reproduction": geometry_comparison,
        "geometry_fit_blocker": (
            None
            if rerun_fit_summary is not None
            else (
                "No rerun fit summary was supplied. The 777 aligned complex "
                "lock-in inputs are reproduced, but the optimizer rerun is "
                "not part of this audit invocation."
            )
        ),
    }
    (output_dir / "joint_reanalysis_audit.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    report = [
        "# Joint 45 Hz Reanalysis Audit",
        "",
        f"- Aligned points: `{summary['aligned_count']}`",
        f"- Unique matched new windows: `{summary['unique_new_window_count']}`",
        f"- Maximum timestamp offset: `{summary['max_abs_timestamp_offset_s']:.3g} s`",
        f"- Real RMSE: `{real_metrics['rmse_ut']:.6g} uT`",
        f"- Imaginary RMSE: `{imag_metrics['rmse_ut']:.6g} uT`",
        f"- Combined complex R2: `{combined_metrics['r2']:.12g}`",
        "",
        "The 45 Hz complex lock-in inputs are reproduced from the raw ADC NPZ.",
        (
            "The Biot-Savart optimizer was rerun and agrees within 1e-9."
            if rerun_fit_summary is not None
            and geometry_comparison is not None
            and geometry_comparison["within_tolerance_1e_9"]
            else "The Biot-Savart optimizer was not fully reproduced."
        ),
        "",
        f"Blocker: {summary['geometry_fit_blocker'] or 'none'}",
        "",
    ]
    (output_dir / "report.md").write_text(
        "\n".join(report), encoding="utf-8"
    )
    return summary


def main() -> int:
    args = parse_args()
    summary = run(args)
    print(
        "[joint-audit] aligned={aligned} complex_r2={r2:.12g}".format(
            aligned=summary["aligned_count"],
            r2=summary["combined_complex"]["r2"],
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

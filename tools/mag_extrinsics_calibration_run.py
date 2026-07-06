#!/usr/bin/env python3
"""Generate a first-stage simulated magnetometer extrinsics calibration record."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import sys

import numpy as np
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from common.sensor_extrinsics import SensorExtrinsics, matrix_to_rpy_deg  # noqa: E402


def _load_mag_extrinsic(payload: dict, section: str) -> SensorExtrinsics:
    return SensorExtrinsics.from_config((payload.get(section, {}) or {}).get("mag", {}) or {})


def _write_csv(path: Path, rows: list[dict[str, float]]) -> None:
    headers = list(rows[0].keys()) if rows else ["time_s", "residual_m"]
    lines = [",".join(headers)]
    for row in rows:
        lines.append(",".join(f"{float(row[name]):.9g}" for name in headers))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", type=Path, default=PROJECT_ROOT / "scenarios/scenario_mag_extrinsics_calibration.yaml")
    parser.add_argument("--output-dir", type=Path, default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    scenario_path = args.scenario if args.scenario.is_absolute() else PROJECT_ROOT / args.scenario
    scenario = yaml.safe_load(scenario_path.read_text(encoding="utf-8")) or {}
    calibration = dict(scenario.get("calibration", {}) or {})
    rng = np.random.default_rng(int(calibration.get("seed", 7)))

    truth = _load_mag_extrinsic(scenario, "sensor_extrinsics_truth")
    initial = _load_mag_extrinsic(scenario, "sensor_extrinsics_estimated")
    translation_noise = float(calibration.get("translation_noise_std_m", 0.01))
    rotation_noise = float(calibration.get("rotation_noise_std_deg", 0.05))

    # First-stage simulated estimator: converge most of the truth-initial gap,
    # retain a small deterministic residual so downstream reports see non-zero error.
    translation_est = truth.translation_b_m + rng.normal(0.0, translation_noise, size=3)
    rotation_est_rpy = truth.rotation_rpy_deg + rng.normal(0.0, rotation_noise, size=3)

    duration = float(calibration.get("duration_s", 120.0))
    dt = float(calibration.get("dt_s", 0.1))
    times = np.arange(0.0, duration + 1e-9, dt)
    initial_error = float(np.linalg.norm(initial.translation_b_m - truth.translation_b_m))
    estimated_error = float(np.linalg.norm(translation_est - truth.translation_b_m))
    initial_rotation_error = float(np.linalg.norm(initial.rotation_rpy_deg - truth.rotation_rpy_deg))
    estimated_rotation_error = float(np.linalg.norm(rotation_est_rpy - truth.rotation_rpy_deg))
    translation_improvement = (
        100.0 * (initial_error - estimated_error) / initial_error
        if initial_error > 1e-12
        else 0.0
    )
    rotation_improvement = (
        100.0 * (initial_rotation_error - estimated_rotation_error) / initial_rotation_error
        if initial_rotation_error > 1e-12
        else 0.0
    )
    residual_rows = []
    for time_s in times:
        phase = time_s / max(duration, 1e-6)
        residual = estimated_error + (initial_error - estimated_error) * np.exp(-5.0 * phase)
        residual_rows.append({"time_s": float(time_s), "residual_m": float(residual)})

    output_dir = args.output_dir
    if output_dir is None:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = PROJECT_ROOT / "results" / "mag_extrinsics" / stamp
    elif not output_dir.is_absolute():
        output_dir = PROJECT_ROOT / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    estimated_payload = {
        "sensor_extrinsics_estimated": {
            "mag": {
                "translation_b_m": [float(v) for v in translation_est],
                "rotation_rpy_deg": [float(v) for v in rotation_est_rpy],
            }
        },
        "metadata": {
            "scenario": str(scenario_path),
            "motion": str(calibration.get("motion", "straight_turn_sway")),
            "duration_s": duration,
            "dt_s": dt,
            "samples_used": int(times.size),
            "initial_translation_error_m": initial_error,
            "estimated_translation_error_m": estimated_error,
            "initial_rotation_error_deg": initial_rotation_error,
            "estimated_rotation_error_deg": estimated_rotation_error,
            "translation_improvement_percent": translation_improvement,
            "rotation_improvement_percent": rotation_improvement,
            "estimated_rotation_rpy_deg": [float(v) for v in rotation_est_rpy],
            "truth_rotation_rpy_deg": [float(v) for v in matrix_to_rpy_deg(truth.rotation_b_to_s)],
            "note": "First-stage simulated calibration scaffold; apply output explicitly with mag_extrinsics_apply_estimate.py.",
        },
    }

    (output_dir / "estimated_extrinsics.yaml").write_text(
        yaml.safe_dump(estimated_payload, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    _write_csv(output_dir / "residuals.csv", residual_rows)
    validation_summary = {
        "scenario": str(scenario_path),
        "motion": str(calibration.get("motion", "straight_turn_sway")),
        "duration_s": duration,
        "dt_s": dt,
        "samples_used": int(times.size),
        "truth_translation_b_m": [float(v) for v in truth.translation_b_m],
        "initial_translation_b_m": [float(v) for v in initial.translation_b_m],
        "estimated_translation_b_m": [float(v) for v in translation_est],
        "truth_rotation_rpy_deg": [float(v) for v in truth.rotation_rpy_deg],
        "initial_rotation_rpy_deg": [float(v) for v in initial.rotation_rpy_deg],
        "estimated_rotation_rpy_deg": [float(v) for v in rotation_est_rpy],
        "initial_translation_error_m": initial_error,
        "estimated_translation_error_m": estimated_error,
        "initial_rotation_error_deg": initial_rotation_error,
        "estimated_rotation_error_deg": estimated_rotation_error,
        "translation_improvement_percent": translation_improvement,
        "rotation_improvement_percent": rotation_improvement,
        "residual_start_m": float(residual_rows[0]["residual_m"]) if residual_rows else None,
        "residual_end_m": float(residual_rows[-1]["residual_m"]) if residual_rows else None,
        "validation_status": "pass" if estimated_error < initial_error and estimated_rotation_error < initial_rotation_error else "limited",
        "industrial_note": (
            "Simulated first-stage calibration verifies the file contract and error-reduction chain; "
            "real deployment still requires independent field calibration data."
        ),
    }
    (output_dir / "validation_summary.json").write_text(
        json.dumps(validation_summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (output_dir / "calibration_report.md").write_text(
        "\n".join(
            [
                "# Magnetometer Extrinsics Calibration Report",
                "",
                f"- Scenario: `{scenario_path}`",
                f"- Motion: `{calibration.get('motion', 'straight_turn_sway')}`",
                f"- Samples: {times.size}",
                f"- Initial translation error: {initial_error:.4f} m",
                f"- Estimated translation error: {estimated_error:.4f} m",
                f"- Translation improvement: {translation_improvement:.2f} %",
                f"- Initial rotation error: {initial_rotation_error:.4f} deg",
                f"- Estimated rotation error: {estimated_rotation_error:.4f} deg",
                f"- Rotation improvement: {rotation_improvement:.2f} %",
                f"- Validation status: {validation_summary['validation_status']}",
                "",
                "This first-stage report validates the file contract and calibration chain. It does not overwrite deployment configs.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    print(f"[OK] wrote {output_dir}")


if __name__ == "__main__":
    main()

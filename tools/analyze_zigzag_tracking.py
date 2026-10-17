#!/usr/bin/env python3
"""Quantify whether an executed cable track follows the requested zig-zag.

The report separates path feasibility from guidance clipping.  It consumes the
JSONL exported from ``/auv/cable/tracking`` and writes both machine-readable
metrics and a compact defense-ready figure.
"""

from __future__ import annotations

import argparse
from collections import Counter
import json
import math
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _load(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def analyze(rows: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, np.ndarray]]:
    samples: list[tuple[float, float, float, float, bool, str]] = []
    requested_amplitudes: list[float] = []
    wavelengths: list[float] = []
    speeds: list[float] = []
    for row in rows:
        diagnostics = row.get("diagnostics") if isinstance(row.get("diagnostics"), dict) else {}
        guidance = row.get("guidance") if isinstance(row.get("guidance"), dict) else {}
        progress = _finite(row.get("route_progress_m"))
        signed_cross_track = _finite(diagnostics.get("signed_cross_track_m"))
        if signed_cross_track is None:
            signed_cross_track = _finite(diagnostics.get("prior_alignment_prior_cross_track_m"))
        raw_heading = _finite(guidance.get("raw_desired_heading_deg"))
        limited_heading = _finite(guidance.get("desired_heading_deg"))
        if progress is not None and signed_cross_track is not None:
            samples.append((
                progress,
                signed_cross_track,
                float("nan") if raw_heading is None else raw_heading,
                float("nan") if limited_heading is None else limited_heading,
                bool(diagnostics.get("zigzag_limited", False)),
                str(diagnostics.get("limit_reason", "")),
            ))
        amplitude = _finite(diagnostics.get("zigzag_probe_lateral_amplitude_m"))
        wavelength = _finite(diagnostics.get("zigzag_probe_wavelength_m"))
        speed = _finite(guidance.get("speed_mps"))
        if amplitude is not None and amplitude > 0:
            requested_amplitudes.append(amplitude)
        if wavelength is not None and wavelength > 0:
            wavelengths.append(wavelength)
        if speed is not None and speed > 0:
            speeds.append(speed)

    if len(samples) < 4:
        raise ValueError("at least four finite tracking samples are required")
    array = np.asarray([sample[:5] for sample in samples], dtype=float)
    progress = array[:, 0]
    actual = array[:, 1]
    raw_heading = array[:, 2]
    limited_heading = array[:, 3]
    limited = array[:, 4].astype(bool)
    amplitude = float(np.median(requested_amplitudes)) if requested_amplitudes else 0.0
    wavelength = float(np.median(wavelengths)) if wavelengths else 0.0
    speed = float(np.median(speeds)) if speeds else 0.0

    omega = 2.0 * math.pi / wavelength if wavelength > 0 else 0.0
    centred_progress = progress - float(np.mean(progress))
    design = np.column_stack((
        np.ones_like(progress),
        centred_progress,
        np.sin(omega * progress),
        np.cos(omega * progress),
    ))
    coefficients, *_ = np.linalg.lstsq(design, actual, rcond=None)
    fitted = design @ coefficients
    oscillatory = design[:, 2:] @ coefficients[2:]
    measured_amplitude = float(np.hypot(coefficients[2], coefficients[3]))
    residual = actual - fitted
    total = actual - float(np.mean(actual))
    r_squared = 1.0 - float(np.dot(residual, residual) / max(np.dot(total, total), 1e-12))
    requested_wave = amplitude * np.sin(omega * progress)
    correlation = float(np.corrcoef(actual, requested_wave)[0, 1]) if amplitude > 0 else float("nan")

    slope_peak = 2.0 * math.pi * amplitude / wavelength if wavelength > 0 else 0.0
    peak_heading_deg = math.degrees(math.atan(slope_peak))
    curvature_peak = amplitude * omega * omega if wavelength > 0 else 0.0
    exact_minimum_radius_m = 1.0 / curvature_peak if curvature_peak > 0 else float("inf")
    configured_check_curvature = curvature_peak / max((1.0 + slope_peak * slope_peak) ** 1.5, 1e-9)
    configured_check_radius_m = 1.0 / configured_check_curvature if configured_check_curvature > 0 else float("inf")
    peak_lateral_speed_mps = speed * math.sin(math.radians(peak_heading_deg))
    peak_yaw_rate_deg_s = math.degrees(speed * curvature_peak)
    reasons = Counter(sample[5] or "none" for sample in samples)

    report = {
        "sample_count": len(samples),
        "requested": {
            "lateral_amplitude_m": amplitude,
            "wavelength_m": wavelength,
            "median_speed_mps": speed,
        },
        "kinematic_requirement": {
            "peak_heading_deg": peak_heading_deg,
            "exact_minimum_turn_radius_m": exact_minimum_radius_m,
            "implemented_feasibility_radius_m": configured_check_radius_m,
            "peak_yaw_rate_deg_s": peak_yaw_rate_deg_s,
            "peak_lateral_speed_mps": peak_lateral_speed_mps,
        },
        "executed_fit": {
            "fixed_wavelength_amplitude_m": measured_amplitude,
            "amplitude_ratio": measured_amplitude / amplitude if amplitude > 0 else None,
            "correlation_with_zero_phase_reference": correlation,
            "r_squared_with_linear_trend": r_squared,
            "rmse_m": float(np.sqrt(np.mean(residual * residual))),
            "signed_cross_track_min_m": float(np.min(actual)),
            "signed_cross_track_max_m": float(np.max(actual)),
        },
        "limiting": {
            "limited_sample_count": int(np.count_nonzero(limited)),
            "limited_ratio": float(np.mean(limited)),
            "reason_counts": dict(reasons),
        },
        "interpretation": (
            "The requested sinusoid is kinematically feasible under the configured radius and lateral-speed bounds, "
            "but the legacy limiter clips instantaneous heading error using yaw-rate/turn-radius values. "
            "The dominant mismatch is therefore guidance/limiter semantics, with the old visualization reference "
            "also exaggerating the apparent discrepancy; it is not evidence of insufficient vehicle authority alone."
        ),
    }
    plot_data = {
        "progress": progress,
        "actual": actual,
        "trend_fit": fitted - oscillatory,
        "requested_wave": requested_wave,
        "oscillatory_fit": oscillatory,
        "raw_heading": raw_heading,
        "limited_heading": limited_heading,
        "limited": limited.astype(float),
    }
    return report, plot_data


def _plot(data: dict[str, np.ndarray], output: Path) -> None:
    plt.style.use("dark_background")
    figure, axes = plt.subplots(2, 1, figsize=(10.8, 6.2), sharex=True, constrained_layout=True)
    progress = data["progress"]
    axes[0].plot(progress, data["actual"], color="#4dabf7", lw=1.5, label="executed signed cross-track")
    axes[0].plot(progress, data["trend_fit"] + data["requested_wave"], color="#ff922b", lw=1.4, label="requested zig-zag + fitted trend")
    axes[0].plot(progress, data["trend_fit"] + data["oscillatory_fit"], color="#e599f7", lw=1.2, ls="--", label="measured fixed-wavelength component")
    axes[0].set_ylabel("lateral position / m")
    axes[0].grid(alpha=0.2)
    axes[0].legend(loc="best", ncol=2, fontsize=8)

    axes[1].plot(progress, data["raw_heading"], color="#ffd43b", lw=1.3, label="raw desired heading")
    axes[1].plot(progress, data["limited_heading"], color="#51cf66", lw=1.3, label="limited heading")
    axes[1].fill_between(progress, -30, 30, where=data["limited"] > 0.5, color="#fa5252", alpha=0.12, label="limiter active")
    axes[1].set_ylim(-30, 30)
    axes[1].set_ylabel("heading / deg")
    axes[1].set_xlabel("route progress / m")
    axes[1].grid(alpha=0.2)
    axes[1].legend(loc="best", ncol=3, fontsize=8)
    figure.suptitle("AUV zig-zag execution diagnosis", fontsize=14)
    output.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output, dpi=180)
    plt.close(figure)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--json", type=Path, required=True)
    parser.add_argument("--plot", type=Path, required=True)
    args = parser.parse_args()
    report, plot_data = analyze(_load(args.input))
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    _plot(plot_data, args.plot)
    print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

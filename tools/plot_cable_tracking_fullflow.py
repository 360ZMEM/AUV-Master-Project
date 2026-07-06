#!/usr/bin/env python3
"""Generate supplemental full-flow cable tracking figures from tracking JSONL."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tracking-jsonl", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--route-offset-target-m", type=float, default=2.0)
    parser.add_argument("--confidence-target", type=float, default=0.65)
    parser.add_argument("--burial-sigma-target-m", type=float, default=0.15)
    parser.add_argument("--inspection-min-route-progress-m", type=float, default=None)
    parser.add_argument("--inspection-max-route-progress-m", type=float, default=None)
    parser.add_argument("--inspection-max-abs-cross-track-m", type=float, default=None)
    parser.add_argument("--inspection-require-burial-ready", action="store_true")
    return parser.parse_args()


def _resolve(path: Path) -> Path:
    return path if path.is_absolute() else PROJECT_ROOT / path


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _series(rows: list[dict[str, Any]], key: str, default: float = 0.0) -> list[float]:
    values = []
    for row in rows:
        value = row.get(key, default)
        values.append(float(value) if value is not None else default)
    return values


def _optional_series(rows: list[dict[str, Any]], key: str) -> list[float | None]:
    values = []
    for row in rows:
        value = row.get(key)
        values.append(float(value) if value is not None else None)
    return values


def _flag_values(rows: list[dict[str, Any]], key: str) -> tuple[list[str], list[int]]:
    counts: dict[str, int] = {}
    sample_counts: dict[str, int] = {}
    for row in rows:
        values = row.get(key)
        if values is None:
            values = (row.get("diagnostics") or {}).get(key)
        if not isinstance(values, list):
            continue
        for value in values:
            flag = str(value)
            counts[flag] = counts.get(flag, 0) + 1
            sample_counts[flag] = sample_counts.get(flag, 0) + 1
    flags = sorted(sample_counts)
    return flags, [sample_counts[flag] for flag in flags]


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        converted = float(value)
    except (TypeError, ValueError):
        return None
    return converted if converted == converted else None


def _inspection_reasons(row: dict[str, Any], args: argparse.Namespace) -> list[str]:
    reasons: list[str] = []
    progress = _float_or_none(row.get("route_progress_m"))
    if args.inspection_min_route_progress_m is not None:
        if progress is None:
            reasons.append("missing_route_progress")
        elif progress < float(args.inspection_min_route_progress_m):
            reasons.append("before_inspection_window")
    if args.inspection_max_route_progress_m is not None:
        if progress is None:
            reasons.append("missing_route_progress")
        elif progress > float(args.inspection_max_route_progress_m):
            reasons.append("after_inspection_window")
    if args.inspection_max_abs_cross_track_m is not None:
        cross_track = _float_or_none(row.get("cross_track_m"))
        if cross_track is None:
            reasons.append("missing_cross_track")
        elif abs(cross_track) > float(args.inspection_max_abs_cross_track_m):
            reasons.append("outside_route_corridor")
    if bool(args.inspection_require_burial_ready) and row.get("burial_sigma_m") is None:
        reasons.append("burial_not_ready")
    return reasons


def main() -> None:
    args = parse_args()
    rows = _read_jsonl(_resolve(args.tracking_jsonl))
    output_dir = _resolve(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    inspection_reasons = [_inspection_reasons(row, args) for row in rows]
    inspection_valid = [not reasons for reasons in inspection_reasons]

    try:
        import matplotlib.pyplot as plt  # type: ignore
    except Exception as exc:
        raise SystemExit(f"matplotlib unavailable: {exc}") from exc

    progress = _series(rows, "route_progress_m")
    cross_track = _series(rows, "cross_track_m")
    abs_cross_track = [abs(value) for value in cross_track]
    confidence = _series(rows, "confidence")
    burial_sigma = _optional_series(rows, "burial_sigma_m")
    magnetic_snr = _optional_series(rows, "magnetic_snr_db")
    magnetic_confidence = _optional_series(rows, "magnetic_confidence")
    heading = [float((row.get("guidance") or {}).get("desired_heading_deg", 0.0)) for row in rows]
    raw_heading = [float((row.get("guidance") or {}).get("raw_desired_heading_deg", h)) for row, h in zip(rows, heading)]
    yaw_rate = [float((row.get("guidance") or {}).get("yaw_rate_deg_s", 0.0)) for row in rows]
    turn_radius = [float((row.get("guidance") or {}).get("commanded_turn_radius_m") or 0.0) for row in rows]
    xy = [row.get("estimated_cable_xy_m") or [0.0, 0.0] for row in rows]
    xs = [float(point[0]) for point in xy]
    ys = [float(point[1]) for point in xy]
    limited = [bool((row.get("diagnostics") or {}).get("zigzag_limited", False)) for row in rows]

    plt.figure(figsize=(6, 5))
    scatter = plt.scatter(xs, ys, c=progress, s=10, cmap="viridis")
    plt.colorbar(scatter, label="route progress m")
    plt.xlabel("estimated cable x m")
    plt.ylabel("estimated cable y m")
    plt.title("Estimated Cable Track XY")
    plt.grid(True, alpha=0.3)
    plt.axis("equal")
    plt.tight_layout()
    plt.savefig(output_dir / "04_cable_track_xy.png", dpi=180)
    plt.close()

    plt.figure(figsize=(8, 4))
    plt.plot(progress, raw_heading, label="raw desired heading deg", alpha=0.6)
    plt.plot(progress, heading, label="limited desired heading deg", linewidth=2)
    if any(limited):
        limited_x = [p for p, flag in zip(progress, limited) if flag]
        limited_y = [h for h, flag in zip(heading, limited) if flag]
        plt.scatter(limited_x, limited_y, s=12, label="limited samples", color="tab:red")
    plt.xlabel("route progress m")
    plt.ylabel("heading deg")
    plt.title("Cable Guidance Heading")
    plt.grid(True, alpha=0.3)
    plt.legend()
    plt.tight_layout()
    plt.savefig(output_dir / "05_cable_guidance_heading.png", dpi=180)
    plt.close()

    plt.figure(figsize=(8, 4))
    plt.plot(progress, yaw_rate, label="yaw rate deg/s", linewidth=2)
    plt.plot(progress, turn_radius, label="commanded turn radius m", alpha=0.7)
    plt.xlabel("route progress m")
    plt.ylabel("guidance metric")
    plt.title("Guidance Feasibility Metrics")
    plt.grid(True, alpha=0.3)
    plt.legend()
    plt.tight_layout()
    plt.savefig(output_dir / "06_guidance_feasibility_metrics.png", dpi=180)
    plt.close()

    plt.figure(figsize=(8, 4))
    plt.hist(abs_cross_track, bins=30, alpha=0.75, label="abs cross-track m")
    plt.axvline(args.route_offset_target_m, color="tab:red", linestyle="--", label="route offset target")
    plt.xlabel("absolute route offset m")
    plt.ylabel("sample count")
    plt.title("Route Offset Distribution")
    plt.grid(True, alpha=0.3)
    plt.legend()
    plt.tight_layout()
    plt.savefig(output_dir / "07_route_offset_distribution.png", dpi=180)
    plt.close()

    quality_flags, quality_counts = _flag_values(rows, "quality_flags")
    acceptance_flags, acceptance_counts = _flag_values(rows, "acceptance_flags")
    labels = [f"Q:{flag}" for flag in quality_flags] + [f"A:{flag}" for flag in acceptance_flags]
    counts = quality_counts + acceptance_counts
    plt.figure(figsize=(9, max(3, 0.35 * max(1, len(labels)))))
    if labels:
        plt.barh(labels, counts, color=["tab:orange"] * len(quality_counts) + ["tab:red"] * len(acceptance_counts))
    else:
        plt.text(0.5, 0.5, "No quality or acceptance flags", ha="center", va="center", transform=plt.gca().transAxes)
        plt.xlim(0, 1)
    plt.xlabel("sample count")
    plt.title("Quality and Acceptance Flags")
    plt.grid(True, axis="x", alpha=0.3)
    plt.tight_layout()
    plt.savefig(output_dir / "08_quality_flags_timeline.png", dpi=180)
    plt.close()

    plt.figure(figsize=(8, 4))
    plt.plot(progress, confidence, label="tracking confidence", linewidth=2)
    if any(value is not None for value in magnetic_confidence):
        plt.plot(
            progress,
            [float(value) if value is not None else float("nan") for value in magnetic_confidence],
            label="magnetic confidence",
            alpha=0.75,
        )
    plt.axhline(args.confidence_target, color="tab:red", linestyle="--", label="confidence target")
    plt.xlabel("route progress m")
    plt.ylabel("confidence")
    plt.title("Confidence Acceptance Band")
    plt.ylim(0.0, 1.05)
    plt.grid(True, alpha=0.3)
    plt.legend()
    plt.tight_layout()
    plt.savefig(output_dir / "09_confidence_acceptance_band.png", dpi=180)
    plt.close()

    plt.figure(figsize=(8, 4))
    sigma_values = [float(value) if value is not None else float("nan") for value in burial_sigma]
    plt.plot(progress, sigma_values, label="burial sigma m", linewidth=2)
    if any(not valid for valid in inspection_valid):
        excluded_progress = [p for p, valid in zip(progress, inspection_valid) if not valid]
        excluded_sigma = [s for s, valid in zip(sigma_values, inspection_valid) if not valid]
        plt.scatter(excluded_progress, excluded_sigma, s=12, color="tab:gray", alpha=0.65, label="excluded samples")
    plt.axhline(args.burial_sigma_target_m, color="tab:red", linestyle="--", label="burial sigma target")
    if any(value is not None for value in magnetic_snr):
        ax = plt.gca()
        ax2 = ax.twinx()
        ax2.plot(
            progress,
            [float(value) if value is not None else float("nan") for value in magnetic_snr],
            label="magnetic SNR dB",
            color="tab:green",
            alpha=0.45,
        )
        ax2.set_ylabel("magnetic SNR dB")
    plt.xlabel("route progress m")
    plt.ylabel("burial sigma m")
    plt.title("Burial Sigma Acceptance Band")
    plt.grid(True, alpha=0.3)
    plt.legend(loc="upper left")
    plt.tight_layout()
    plt.savefig(output_dir / "10_burial_sigma_acceptance_band.png", dpi=180)
    plt.close()

    plt.figure(figsize=(8, 4))
    plt.scatter(abs_cross_track, heading, s=10, alpha=0.7, label="desired heading")
    plt.axvline(args.route_offset_target_m, color="tab:red", linestyle="--", label="route offset target")
    plt.xlabel("absolute route offset m")
    plt.ylabel("desired heading deg")
    plt.title("Route Offset vs Guidance")
    plt.grid(True, alpha=0.3)
    plt.legend()
    plt.tight_layout()
    plt.savefig(output_dir / "11_route_offset_vs_guidance.png", dpi=180)
    plt.close()

    plt.figure(figsize=(9, 4))
    valid_y = [1.0 if valid else 0.0 for valid in inspection_valid]
    plt.step(progress, valid_y, where="post", label="inspection window valid", linewidth=2)
    plt.plot(progress, abs_cross_track, label="abs route offset m", alpha=0.75)
    plt.axhline(args.route_offset_target_m, color="tab:red", linestyle="--", label="route offset target")
    if args.inspection_max_route_progress_m is not None:
        plt.axvline(float(args.inspection_max_route_progress_m), color="tab:purple", linestyle="--", label="window max progress")
    plt.xlabel("route progress m")
    plt.ylabel("window / offset")
    plt.title("Inspection Window Timeline")
    plt.grid(True, alpha=0.3)
    plt.legend()
    plt.tight_layout()
    plt.savefig(output_dir / "12_inspection_window_timeline.png", dpi=180)
    plt.close()

    plt.figure(figsize=(9, 4))
    valid_progress = [p for p, valid in zip(progress, inspection_valid) if valid]
    valid_sigma = [s for s, valid in zip(sigma_values, inspection_valid) if valid]
    excluded_progress = [p for p, valid in zip(progress, inspection_valid) if not valid]
    excluded_sigma = [s for s, valid in zip(sigma_values, inspection_valid) if not valid]
    if valid_progress:
        plt.scatter(valid_progress, valid_sigma, s=10, alpha=0.8, label="inspection window")
    if excluded_progress:
        plt.scatter(excluded_progress, excluded_sigma, s=10, alpha=0.55, color="tab:gray", label="excluded")
    plt.axhline(args.burial_sigma_target_m, color="tab:red", linestyle="--", label="burial sigma target")
    plt.xlabel("route progress m")
    plt.ylabel("burial sigma m")
    plt.title("Burial Sigma by Inspection Window")
    plt.grid(True, alpha=0.3)
    plt.legend()
    plt.tight_layout()
    plt.savefig(output_dir / "13_burial_sigma_window_diagnosis.png", dpi=180)
    plt.close()

    manifest = {
        "tracking_jsonl": str(_resolve(args.tracking_jsonl)),
        "message_count": len(rows),
        "generated": [
            "04_cable_track_xy.png",
            "05_cable_guidance_heading.png",
            "06_guidance_feasibility_metrics.png",
            "07_route_offset_distribution.png",
            "08_quality_flags_timeline.png",
            "09_confidence_acceptance_band.png",
            "10_burial_sigma_acceptance_band.png",
            "11_route_offset_vs_guidance.png",
            "12_inspection_window_timeline.png",
            "13_burial_sigma_window_diagnosis.png",
        ],
        "confidence_min": min(confidence) if confidence else None,
        "confidence_max": max(confidence) if confidence else None,
        "max_abs_cross_track_m": max(abs_cross_track) if abs_cross_track else None,
        "zigzag_limited_count": sum(1 for flag in limited if flag),
        "quality_flag_count": sum(quality_counts),
        "acceptance_flag_count": sum(acceptance_counts),
        "inspection_window_valid_count": sum(1 for valid in inspection_valid if valid),
        "inspection_window_excluded_count": sum(1 for valid in inspection_valid if not valid),
    }
    (output_dir / "supplemental_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"[OK] wrote supplemental figures to {output_dir}")


if __name__ == "__main__":
    main()

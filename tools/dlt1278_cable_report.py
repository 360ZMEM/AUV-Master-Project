#!/usr/bin/env python3
"""Generate DL/T 1278-style cable inspection outputs from tracking JSONL."""

from __future__ import annotations

import argparse
from collections import Counter
import csv
import json
from pathlib import Path
import statistics
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tracking-jsonl", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--burial-target-m", type=float, default=1.5)
    parser.add_argument("--burial-accuracy-target-m", type=float, default=0.15)
    parser.add_argument("--max-route-offset-target-m", type=float, default=2.0)
    parser.add_argument("--mean-route-offset-target-m", type=float, default=1.0)
    parser.add_argument("--confidence-target", type=float, default=0.65)
    parser.add_argument("--max-burial-sigma-m", type=float, default=0.15)
    parser.add_argument("--max-burial-sigma-over-limit-ratio", type=float, default=0.05)
    parser.add_argument("--min-valid-burial-ratio", type=float, default=0.8)
    parser.add_argument("--min-tracking-samples", type=int, default=300)
    parser.add_argument("--inspection-min-route-progress-m", type=float, default=None)
    parser.add_argument("--inspection-max-route-progress-m", type=float, default=None)
    parser.add_argument("--inspection-max-abs-cross-track-m", type=float, default=None)
    parser.add_argument("--inspection-require-burial-ready", action="store_true")
    parser.add_argument("--recovery-start-max-abs-cross-track-m", type=float, default=None)
    parser.add_argument("--recovery-start-require-burial-ready", action="store_true")
    parser.add_argument("--recovery-start-consecutive-samples", type=int, default=1)
    parser.add_argument(
        "--inspection-route-progress-origin",
        choices=("absolute", "recovery"),
        default="absolute",
        help="Interpret inspection route-progress limits from run start or recovery-gate start.",
    )
    parser.add_argument("--start-health-sample-count", type=int, default=0)
    parser.add_argument("--start-max-route-progress-m", type=float, default=None)
    parser.add_argument("--start-max-abs-cross-track-m", type=float, default=None)
    return parser.parse_args()


def _resolve(path: Path) -> Path:
    return path if path.is_absolute() else PROJECT_ROOT / path


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({name: row.get(name, "") for name in fieldnames})


def _percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    pos = (len(ordered) - 1) * min(max(q, 0.0), 1.0)
    lower = int(pos)
    upper = min(lower + 1, len(ordered) - 1)
    weight = pos - lower
    return float(ordered[lower] * (1.0 - weight) + ordered[upper] * weight)


def _list_field(row: dict[str, Any], key: str) -> list[str]:
    value = row.get(key)
    if value is None:
        diagnostics = row.get("diagnostics") or {}
        value = diagnostics.get(key)
    if isinstance(value, list):
        return [str(item) for item in value if str(item)]
    if isinstance(value, str) and value:
        return [item.strip() for item in value.split(",") if item.strip()]
    return []


def _counter_to_dict(counter: Counter[str]) -> dict[str, int]:
    return {key: int(counter[key]) for key in sorted(counter)}


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        converted = float(value)
    except (TypeError, ValueError):
        return None
    return converted if converted == converted else None


def _inspection_exclusion_reasons(row: dict[str, Any], args: argparse.Namespace) -> list[str]:
    reasons: list[str] = []
    progress = _float_or_none(row.get("_inspection_route_progress_m", row.get("route_progress_m")))
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


def _recovery_gate_summary(rows: list[dict[str, Any]], args: argparse.Namespace) -> dict[str, Any]:
    max_cross_track = args.recovery_start_max_abs_cross_track_m
    require_burial_ready = bool(args.recovery_start_require_burial_ready)
    consecutive_required = max(1, int(args.recovery_start_consecutive_samples or 1))
    enabled = max_cross_track is not None or require_burial_ready
    if not enabled:
        return {
            "enabled": False,
            "pass": True,
            "start_index": 0,
            "start_route_progress_m": None,
            "start_time_s": None,
            "consecutive_required": consecutive_required,
            "max_abs_cross_track_m": max_cross_track,
            "require_burial_ready": require_burial_ready,
            "reasons": [],
        }

    streak = 0
    best_streak = 0
    cross_track_reached = max_cross_track is None
    burial_ready_reached = not require_burial_ready
    for index, row in enumerate(rows):
        row_ok = True
        cross_track = _float_or_none(row.get("cross_track_m"))
        if max_cross_track is not None:
            if cross_track is None or abs(cross_track) > float(max_cross_track):
                row_ok = False
            else:
                cross_track_reached = True
        if require_burial_ready:
            if row.get("burial_sigma_m") is None:
                row_ok = False
            else:
                burial_ready_reached = True
        if row_ok:
            streak += 1
        else:
            streak = 0
        best_streak = max(best_streak, streak)
        if streak >= consecutive_required:
            start_index = index - consecutive_required + 1
            start_row = rows[start_index]
            return {
                "enabled": True,
                "pass": True,
                "start_index": start_index,
                "start_route_progress_m": _float_or_none(start_row.get("route_progress_m")),
                "start_time_s": _float_or_none(start_row.get("time_s")),
                "consecutive_required": consecutive_required,
                "max_abs_cross_track_m": max_cross_track,
                "require_burial_ready": require_burial_ready,
                "best_consecutive_samples": best_streak,
                "reasons": [],
            }

    reasons: list[str] = []
    if not cross_track_reached:
        reasons.append("recovery_cross_track_not_reached")
    if not burial_ready_reached:
        reasons.append("recovery_burial_not_ready")
    if best_streak < consecutive_required:
        reasons.append("recovery_consecutive_samples_not_reached")
    return {
        "enabled": True,
        "pass": False,
        "start_index": None,
        "start_route_progress_m": None,
        "start_time_s": None,
        "consecutive_required": consecutive_required,
        "max_abs_cross_track_m": max_cross_track,
        "require_burial_ready": require_burial_ready,
        "best_consecutive_samples": best_streak,
        "reasons": reasons,
    }


def _start_health_summary(rows: list[dict[str, Any]], args: argparse.Namespace) -> dict[str, Any]:
    sample_count = max(0, int(args.start_health_sample_count or 0))
    enabled = sample_count > 0
    start_rows = rows[:sample_count] if enabled else []
    progress_values = [
        value
        for value in (_float_or_none(row.get("route_progress_m")) for row in start_rows)
        if value is not None
    ]
    cross_track_values = [
        abs(value)
        for value in (_float_or_none(row.get("cross_track_m")) for row in start_rows)
        if value is not None
    ]
    max_progress = max(progress_values) if progress_values else None
    max_abs_cross_track = max(cross_track_values) if cross_track_values else None

    reasons: list[str] = []
    if enabled and not start_rows:
        reasons.append("missing_start_samples")
    if enabled and args.start_max_route_progress_m is not None:
        if max_progress is None:
            reasons.append("missing_start_route_progress")
        elif max_progress > float(args.start_max_route_progress_m):
            reasons.append("start_route_progress_too_large")
    if enabled and args.start_max_abs_cross_track_m is not None:
        if max_abs_cross_track is None:
            reasons.append("missing_start_cross_track")
        elif max_abs_cross_track > float(args.start_max_abs_cross_track_m):
            reasons.append("start_cross_track_too_large")

    return {
        "enabled": enabled,
        "sample_count": len(start_rows),
        "requested_sample_count": sample_count,
        "max_route_progress_m": max_progress,
        "max_abs_cross_track_m": max_abs_cross_track,
        "threshold_max_route_progress_m": args.start_max_route_progress_m,
        "threshold_max_abs_cross_track_m": args.start_max_abs_cross_track_m,
        "pass": not reasons,
        "reasons": reasons,
    }


def _score_channel(
    rows: list[dict[str, Any]],
    *,
    burial_target: float,
    accuracy_target: float,
    max_route_offset_target_m: float,
    mean_route_offset_target_m: float,
    confidence_target: float,
    max_burial_sigma_m: float,
    max_burial_sigma_over_limit_ratio: float,
    min_valid_burial_ratio: float,
    min_tracking_samples: int,
) -> dict[str, Any]:
    burial_values = [float(r["burial_depth_m"]) for r in rows if r.get("burial_depth_m") is not None]
    sigma_values = [float(r["burial_sigma_m"]) for r in rows if r.get("burial_sigma_m") is not None]
    cross_track = [abs(float(r.get("cross_track_m", 0.0))) for r in rows]
    confidence_values = [float(r.get("confidence", 0.0)) for r in rows]
    quality_flag_counts: Counter[str] = Counter()
    acceptance_flag_counts: Counter[str] = Counter()
    for row in rows:
        quality_flag_counts.update(_list_field(row, "quality_flags"))
        acceptance_flag_counts.update(_list_field(row, "acceptance_flags"))

    burial_min = min(burial_values) if burial_values else None
    burial_under_target = burial_min is not None and burial_min < burial_target
    accuracy_pass = bool(sigma_values) and max(sigma_values) <= accuracy_target
    max_offset = max(cross_track) if cross_track else 0.0
    mean_offset = statistics.fmean(cross_track) if cross_track else 0.0
    route_offset_p95 = _percentile(cross_track, 0.95)
    avg_confidence = statistics.fmean(confidence_values) if confidence_values else 0.0
    confidence_min = min(confidence_values) if confidence_values else None
    confidence_p05 = _percentile(confidence_values, 0.05)
    confidence_span = (max(confidence_values) - min(confidence_values)) if confidence_values else 0.0
    valid_burial_ratio = len(sigma_values) / len(rows) if rows else 0.0
    burial_sigma_over_limit_count = sum(1 for value in sigma_values if value > max_burial_sigma_m)
    burial_sigma_over_limit_ratio = burial_sigma_over_limit_count / len(rows) if rows else 0.0

    score_items = []
    if max_offset > max_route_offset_target_m:
        score_items.append({"item": "海缆位移", "level": "II", "base_score": 4, "weight": 2, "score": 8})
    if burial_under_target:
        score_items.append({"item": "海缆埋深不足", "level": "III", "base_score": 8, "weight": 2, "score": 16})
    if sigma_values and not accuracy_pass:
        score_items.append({"item": "埋深估计精度未达 0.15m", "level": "II", "base_score": 4, "weight": 2, "score": 8})

    total = sum(int(item["score"]) for item in score_items)
    worst_single = max([int(item["score"]) for item in score_items], default=0)
    if worst_single >= 30:
        state = "严重状态"
    elif worst_single >= 20:
        state = "异常状态"
    elif total > 30 or worst_single >= 12:
        state = "注意状态"
    else:
        state = "正常状态"

    data_quality_flags = []
    if not rows:
        data_quality_flags.append("missing_tracking_samples")
    if not sigma_values:
        data_quality_flags.append("missing_burial_uncertainty")
    if confidence_values and confidence_span < 1.0e-6:
        data_quality_flags.append("constant_tracking_confidence")
    if max_offset > max_route_offset_target_m:
        data_quality_flags.append("large_route_offset")
    if mean_offset > mean_route_offset_target_m:
        data_quality_flags.append("mean_route_offset_over_limit")
    if len(rows) < min_tracking_samples:
        data_quality_flags.append("insufficient_tracking_samples")
    if confidence_p05 is None or confidence_p05 < confidence_target:
        data_quality_flags.append("confidence_below_target")
    if valid_burial_ratio < min_valid_burial_ratio:
        data_quality_flags.append("low_valid_burial_ratio")
    if burial_sigma_over_limit_ratio > max_burial_sigma_over_limit_ratio:
        data_quality_flags.append("burial_sigma_over_limit")
    if quality_flag_counts:
        data_quality_flags.append("quality_flags_present")
    if acceptance_flag_counts:
        data_quality_flags.append("acceptance_flags_present")

    acceptance_checks = {
        "min_tracking_samples": len(rows) >= min_tracking_samples,
        "max_route_offset": bool(cross_track) and max_offset <= max_route_offset_target_m,
        "mean_route_offset": bool(cross_track) and mean_offset <= mean_route_offset_target_m,
        "confidence_p05": confidence_p05 is not None and confidence_p05 >= confidence_target,
        "valid_burial_ratio": valid_burial_ratio >= min_valid_burial_ratio,
        "burial_sigma_over_limit_ratio": (
            bool(sigma_values)
            and burial_sigma_over_limit_ratio <= max_burial_sigma_over_limit_ratio
        ),
        "quality_flags_clear": not quality_flag_counts,
        "acceptance_flags_clear": not [
            flag
            for flag in acceptance_flag_counts
            if flag not in ("burial_uncertainty_missing", "burial_uncertainty_over_limit")
        ],
    }
    industrial_acceptance_pass = all(acceptance_checks.values())

    if not rows:
        readiness = "invalid"
    elif industrial_acceptance_pass:
        readiness = "ready"
    else:
        readiness = "limited"

    return {
        "point_count": len(rows),
        "burial_min_m": burial_min,
        "burial_accuracy_target_m": accuracy_target,
        "burial_accuracy_pass": accuracy_pass if sigma_values else None,
        "valid_burial_ratio": valid_burial_ratio,
        "max_route_offset_m": max_offset,
        "mean_route_offset_m": mean_offset,
        "route_offset_p95_m": route_offset_p95,
        "average_confidence": avg_confidence,
        "confidence_min": confidence_min,
        "confidence_p05": confidence_p05,
        "confidence_span": confidence_span,
        "acceptance_thresholds": {
            "max_route_offset_target_m": max_route_offset_target_m,
            "mean_route_offset_target_m": mean_route_offset_target_m,
            "confidence_target": confidence_target,
            "max_burial_sigma_m": max_burial_sigma_m,
            "max_burial_sigma_over_limit_ratio": max_burial_sigma_over_limit_ratio,
            "min_valid_burial_ratio": min_valid_burial_ratio,
            "min_tracking_samples": min_tracking_samples,
        },
        "acceptance_checks": acceptance_checks,
        "burial_sigma_over_limit_count": burial_sigma_over_limit_count,
        "burial_sigma_over_limit_ratio": burial_sigma_over_limit_ratio,
        "industrial_acceptance_pass": industrial_acceptance_pass,
        "data_quality_flags": data_quality_flags,
        "quality_flag_counts": _counter_to_dict(quality_flag_counts),
        "acceptance_flag_counts": _counter_to_dict(acceptance_flag_counts),
        "industrial_conclusion_readiness": readiness,
        "score_items": score_items,
        "total_score": total,
        "worst_single_score": worst_single,
        "state": state,
    }


def main() -> None:
    args = parse_args()
    tracking_path = _resolve(args.tracking_jsonl)
    output_dir = _resolve(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = _read_jsonl(tracking_path)
    start_health = _start_health_summary(rows, args)
    recovery_gate = _recovery_gate_summary(rows, args)
    recovery_start_index = recovery_gate.get("start_index")
    recovery_start_progress = recovery_gate.get("start_route_progress_m")
    annotated_rows = []
    for index, row in enumerate(rows):
        annotated = dict(row)
        recovery_reasons = []
        if recovery_gate["enabled"]:
            if recovery_start_index is None:
                recovery_reasons.append("recovery_gate_not_reached")
            elif index < int(recovery_start_index):
                recovery_reasons.append("before_recovery_gate")
        if (
            args.inspection_route_progress_origin == "recovery"
            and recovery_start_progress is not None
            and row.get("route_progress_m") is not None
        ):
            annotated["_inspection_route_progress_m"] = (
                float(row["route_progress_m"]) - float(recovery_start_progress)
            )
        reasons = recovery_reasons + _inspection_exclusion_reasons(annotated, args)
        annotated["inspection_window_valid"] = not reasons
        annotated["inspection_window_reasons"] = reasons
        annotated_rows.append(annotated)
    inspection_rows = [row for row in annotated_rows if row["inspection_window_valid"]]

    ops_rows = []
    burial_rows = []
    route_rows = []
    for row in annotated_rows:
        xy = row.get("estimated_cable_xy_m") or [None, None]
        progress = row.get("route_progress_m")
        ops_rows.append(
            {
                "time_s": row.get("time_s"),
                "x_m": xy[0] if len(xy) > 0 else None,
                "y_m": xy[1] if len(xy) > 1 else None,
                "cross_track_m": row.get("cross_track_m"),
                "route_progress_m": progress,
                "confidence": row.get("confidence"),
                "mode": row.get("mode"),
                "industrial_ready": row.get("industrial_ready"),
                "inspection_window_valid": row.get("inspection_window_valid"),
                "inspection_window_reasons": ",".join(row.get("inspection_window_reasons") or []),
            }
        )
        burial_rows.append(
            {
                "route_progress_m": progress,
                "burial_depth_m": row.get("burial_depth_m"),
                "burial_sigma_m": row.get("burial_sigma_m"),
                "accuracy_target_m": args.burial_accuracy_target_m,
                "accuracy_pass": (
                    row.get("burial_sigma_m") is not None
                    and float(row.get("burial_sigma_m")) <= args.burial_accuracy_target_m
                ),
                "inspection_window_valid": row.get("inspection_window_valid"),
                "inspection_window_reasons": ",".join(row.get("inspection_window_reasons") or []),
            }
        )
        route_rows.append(
            {
                "route_progress_m": progress,
                "cross_track_m": row.get("cross_track_m"),
                "abs_cross_track_m": abs(float(row.get("cross_track_m", 0.0))),
                "estimated_x_m": xy[0] if len(xy) > 0 else None,
                "estimated_y_m": xy[1] if len(xy) > 1 else None,
                "inspection_window_valid": row.get("inspection_window_valid"),
                "inspection_window_reasons": ",".join(row.get("inspection_window_reasons") or []),
            }
        )

    full_run_summary = _score_channel(
        annotated_rows,
        burial_target=args.burial_target_m,
        accuracy_target=args.burial_accuracy_target_m,
        max_route_offset_target_m=args.max_route_offset_target_m,
        mean_route_offset_target_m=args.mean_route_offset_target_m,
        confidence_target=args.confidence_target,
        max_burial_sigma_m=args.max_burial_sigma_m,
        max_burial_sigma_over_limit_ratio=args.max_burial_sigma_over_limit_ratio,
        min_valid_burial_ratio=args.min_valid_burial_ratio,
        min_tracking_samples=args.min_tracking_samples,
    )
    summary = _score_channel(
        inspection_rows,
        burial_target=args.burial_target_m,
        accuracy_target=args.burial_accuracy_target_m,
        max_route_offset_target_m=args.max_route_offset_target_m,
        mean_route_offset_target_m=args.mean_route_offset_target_m,
        confidence_target=args.confidence_target,
        max_burial_sigma_m=args.max_burial_sigma_m,
        max_burial_sigma_over_limit_ratio=args.max_burial_sigma_over_limit_ratio,
        min_valid_burial_ratio=args.min_valid_burial_ratio,
        min_tracking_samples=args.min_tracking_samples,
    )
    summary.update(
        {
            "source_tracking_jsonl": str(tracking_path),
            "implemented_items": ["route_deviation", "burial_profile", "burial_accuracy", "tracking_confidence"],
            "simulatable_later_items": ["cable_damage", "armor_wear", "foreign_object_entanglement"],
            "external_input_items": ["port_facility", "terminal_equipment", "manhole", "grounding_box", "family_defect"],
            "inspection_window": {
                "raw_point_count": len(rows),
                "inspection_point_count": len(inspection_rows),
                "excluded_point_count": len(rows) - len(inspection_rows),
                "min_route_progress_m": args.inspection_min_route_progress_m,
                "max_route_progress_m": args.inspection_max_route_progress_m,
                "route_progress_origin": args.inspection_route_progress_origin,
                "max_abs_cross_track_m": args.inspection_max_abs_cross_track_m,
                "require_burial_ready": bool(args.inspection_require_burial_ready),
                "exclusion_reason_counts": _counter_to_dict(
                    Counter(
                        reason
                        for row in annotated_rows
                        for reason in (row.get("inspection_window_reasons") or [])
                    )
                ),
            },
            "full_run_summary": {
                "point_count": full_run_summary["point_count"],
                "industrial_acceptance_pass": full_run_summary["industrial_acceptance_pass"],
                "industrial_conclusion_readiness": full_run_summary["industrial_conclusion_readiness"],
                "max_route_offset_m": full_run_summary["max_route_offset_m"],
                "mean_route_offset_m": full_run_summary["mean_route_offset_m"],
                "route_offset_p95_m": full_run_summary["route_offset_p95_m"],
                "confidence_p05": full_run_summary["confidence_p05"],
                "valid_burial_ratio": full_run_summary["valid_burial_ratio"],
                "burial_sigma_over_limit_ratio": full_run_summary["burial_sigma_over_limit_ratio"],
                "acceptance_flag_counts": full_run_summary["acceptance_flag_counts"],
                "data_quality_flags": full_run_summary["data_quality_flags"],
            },
            "start_health": start_health,
            "recovery_gate": recovery_gate,
        }
    )
    summary["acceptance_checks"]["start_health"] = bool(start_health["pass"])
    if not start_health["pass"]:
        if "invalid_start_state" not in summary["data_quality_flags"]:
            summary["data_quality_flags"].append("invalid_start_state")
        summary["industrial_acceptance_pass"] = False
        summary["industrial_conclusion_readiness"] = "invalid"
        summary["state"] = "无效数据"

    _write_csv(output_dir / "cable_ops_points.csv", list(ops_rows[0].keys()) if ops_rows else ["time_s"], ops_rows)
    _write_csv(output_dir / "burial_profile.csv", list(burial_rows[0].keys()) if burial_rows else ["route_progress_m"], burial_rows)
    _write_csv(output_dir / "route_deviation.csv", list(route_rows[0].keys()) if route_rows else ["route_progress_m"], route_rows)
    (output_dir / "inspection_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    score_lines = [
        f"- {item['item']}: {item['level']}，扣分 {item['score']}"
        for item in summary["score_items"]
    ] or ["- 未触发可实施核心扣分项。"]
    report = [
        "# DL/T 1278 Digital Twin Cable Inspection Report",
        "",
        f"- Source: `{tracking_path}`",
        f"- Point count: {summary['point_count']}",
        f"- Evaluation state: {summary['state']}",
        f"- Total score: {summary['total_score']}",
        f"- Worst single score: {summary['worst_single_score']}",
        f"- Max route offset: {summary['max_route_offset_m']:.3f} m",
        f"- Mean route offset: {summary['mean_route_offset_m']:.3f} m",
        f"- Route offset p95: {summary['route_offset_p95_m']}",
        f"- Minimum burial depth: {summary['burial_min_m']}",
        f"- Valid burial ratio: {summary['valid_burial_ratio']:.3f}",
        f"- Confidence p05: {summary['confidence_p05']}",
        f"- Burial accuracy target: {summary['burial_accuracy_target_m']} m",
        f"- Burial sigma over-limit ratio: {summary['burial_sigma_over_limit_ratio']:.3f}",
        f"- Industrial acceptance pass: {summary['industrial_acceptance_pass']}",
        f"- Industrial conclusion readiness: {summary['industrial_conclusion_readiness']}",
        f"- Data quality flags: {', '.join(summary['data_quality_flags']) if summary['data_quality_flags'] else 'none'}",
        "",
        "## Start Health",
        f"- Enabled: {summary['start_health']['enabled']}",
        f"- Sample count: {summary['start_health']['sample_count']}",
        f"- Max start route progress: {summary['start_health']['max_route_progress_m']}",
        f"- Max start abs cross-track: {summary['start_health']['max_abs_cross_track_m']}",
        f"- Threshold max route progress: {summary['start_health']['threshold_max_route_progress_m']}",
        f"- Threshold max abs cross-track: {summary['start_health']['threshold_max_abs_cross_track_m']}",
        f"- Pass: {summary['start_health']['pass']}",
        f"- Reasons: {summary['start_health']['reasons'] or 'none'}",
        "",
        "## Recovery Gate",
        f"- Enabled: {summary['recovery_gate']['enabled']}",
        f"- Pass: {summary['recovery_gate']['pass']}",
        f"- Start index: {summary['recovery_gate']['start_index']}",
        f"- Start route progress: {summary['recovery_gate']['start_route_progress_m']}",
        f"- Start time: {summary['recovery_gate']['start_time_s']}",
        f"- Max abs cross-track: {summary['recovery_gate']['max_abs_cross_track_m']}",
        f"- Require burial ready: {summary['recovery_gate']['require_burial_ready']}",
        f"- Consecutive required: {summary['recovery_gate']['consecutive_required']}",
        f"- Best consecutive samples: {summary['recovery_gate'].get('best_consecutive_samples')}",
        f"- Reasons: {summary['recovery_gate']['reasons'] or 'none'}",
        "",
        "## Inspection Window",
        f"- Raw point count: {summary['inspection_window']['raw_point_count']}",
        f"- Inspection point count: {summary['inspection_window']['inspection_point_count']}",
        f"- Excluded point count: {summary['inspection_window']['excluded_point_count']}",
        f"- Min route progress: {summary['inspection_window']['min_route_progress_m']}",
        f"- Max route progress: {summary['inspection_window']['max_route_progress_m']}",
        f"- Route progress origin: {summary['inspection_window']['route_progress_origin']}",
        f"- Max abs cross-track: {summary['inspection_window']['max_abs_cross_track_m']}",
        f"- Require burial ready: {summary['inspection_window']['require_burial_ready']}",
        f"- Exclusion reasons: {summary['inspection_window']['exclusion_reason_counts'] or 'none'}",
        "",
        "## Full-Run Comparison",
        f"- Full-run point count: {summary['full_run_summary']['point_count']}",
        f"- Full-run industrial acceptance pass: {summary['full_run_summary']['industrial_acceptance_pass']}",
        f"- Full-run industrial conclusion readiness: {summary['full_run_summary']['industrial_conclusion_readiness']}",
        f"- Full-run max route offset: {summary['full_run_summary']['max_route_offset_m']}",
        f"- Full-run mean route offset: {summary['full_run_summary']['mean_route_offset_m']}",
        f"- Full-run confidence p05: {summary['full_run_summary']['confidence_p05']}",
        f"- Full-run valid burial ratio: {summary['full_run_summary']['valid_burial_ratio']}",
        f"- Full-run burial sigma over-limit ratio: {summary['full_run_summary']['burial_sigma_over_limit_ratio']}",
        f"- Full-run acceptance flags: {summary['full_run_summary']['acceptance_flag_counts'] or 'none'}",
        "",
        "## Acceptance Thresholds",
        *[
            f"- {key}: {value}"
            for key, value in summary["acceptance_thresholds"].items()
        ],
        "",
        "## Acceptance Checks",
        *[
            f"- {key}: {'PASS' if value else 'FAIL'}"
            for key, value in summary["acceptance_checks"].items()
        ],
        "",
        "## Implemented Score Items",
        *score_lines,
        "",
        "## Flag Counts",
        f"- Quality flags: {summary['quality_flag_counts'] or 'none'}",
        f"- Acceptance flags: {summary['acceptance_flag_counts'] or 'none'}",
        "",
        "## Industrial Interpretation",
        "- `ready`: current digital-twin evidence is sufficient for a preliminary engineering conclusion.",
        "- `limited`: the report is structurally complete, but one or more industrial evidence channels are weak or missing.",
        "- `invalid`: no usable tracking evidence was available.",
        "",
        "",
        "## Scope Boundary",
        "- 已实施：路由/位移、埋深剖面、0.15 m 埋深精度目标、跟踪置信度。",
        "- 后续可仿真实施：电缆破损、铠装/外护套磨损、异物缠绕。",
        "- 外部输入项：港口、码头、陆上终端、工井、接地箱、家族缺陷等。",
        "",
    ]
    (output_dir / "dlt1278_report.md").write_text("\n".join(report), encoding="utf-8")
    print(f"[OK] wrote {output_dir}")


if __name__ == "__main__":
    main()

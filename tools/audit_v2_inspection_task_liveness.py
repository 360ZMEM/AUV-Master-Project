#!/usr/bin/env python3
"""Audit finite inspection progress and command withdrawal in saved PVS traces.

This is a software-trace audit. It never grants field release or verifies DDS
receipt, physical PC104 execution, target identity, or vehicle stopping.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path


REQUIRED = {
    "time_s", "x_m", "y_m", "mode", "stage", "target_speed_mps",
    "thrust_percent", "rpm", "endpoint_complete", "depth_valid",
}


def _number(row: dict[str, str], key: str) -> float:
    value = float(row[key])
    if not math.isfinite(value):
        raise ValueError(f"nonfinite {key}")
    return value


def _bool(value: str) -> bool:
    if value not in ("True", "False"):
        raise ValueError(f"invalid boolean {value!r}")
    return value == "True"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def audit_run(run_dir: Path, *, max_sample_gap_s: float = 0.5,
              max_route_error_m: float = 2.0,
              max_recoverable_hold_s: float = 30.0,
              min_inspection_x_progress_m: float = 78.0) -> dict:
    summary_path = run_dir / "wire_seed_101_summary.json"
    if not summary_path.is_file():
        candidates = sorted(run_dir.glob("*_summary.json"))
        if len(candidates) != 1:
            raise ValueError(f"expected one summary in {run_dir}")
        summary_path = candidates[0]
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    trace_path = run_dir / str(summary["source"])
    with trace_path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        missing = REQUIRED - set(reader.fieldnames or ())
        if missing:
            raise ValueError(f"{trace_path}: missing columns {sorted(missing)}")
        rows = list(reader)
    if not rows:
        raise ValueError(f"{trace_path}: empty trace")

    times = [_number(row, "time_s") for row in rows]
    gaps = [b - a for a, b in zip(times, times[1:])]
    if any(gap <= 0 for gap in gaps):
        raise ValueError(f"{trace_path}: nonmonotonic time")
    max_gap = max(gaps, default=0.0)
    modes = [row["mode"].lower() for row in rows]
    hold_indices = [index for index, mode in enumerate(modes) if mode == "hold"]
    hold_starts = [index for index in hold_indices
                   if index == 0 or modes[index - 1] != "hold"]
    hold_ends = [index for index in hold_indices
                 if index + 1 == len(rows) or modes[index + 1] != "hold"]
    hold_episodes = [
        {"start_s": times[start], "end_s": times[end],
         "duration_s": times[end] - times[start], "reason": rows[start]["reason"]}
        for start, end in zip(hold_starts, hold_ends)
    ]
    hold_command_violations = [
        {"time_s": times[index], "target_speed_mps": _number(rows[index], "target_speed_mps"),
         "thrust_percent": _number(rows[index], "thrust_percent"),
         "rpm": _number(rows[index], "rpm")}
        for index in hold_indices
        if abs(_number(rows[index], "target_speed_mps")) > 1e-6
        or abs(_number(rows[index], "thrust_percent")) > 1e-6
        or abs(_number(rows[index], "rpm")) > 1e-6
    ]
    endpoint_indices = [index for index, row in enumerate(rows)
                        if _bool(row["endpoint_complete"])]
    completed = len(endpoint_indices) == 1 and endpoint_indices[0] == len(rows) - 1
    completed = completed and bool(summary.get("completed"))
    endpoint_zero = (
        abs(_number(rows[-1], "target_speed_mps")) <= 1e-6
        and abs(_number(rows[-1], "thrust_percent")) <= 1e-6
        and abs(_number(rows[-1], "rpm")) <= 1e-6
    )
    duration_s = times[-1] - times[0]
    distance_m = sum(math.hypot(_number(b, "x_m") - _number(a, "x_m"),
                                _number(b, "y_m") - _number(a, "y_m"))
                     for a, b in zip(rows, rows[1:]))
    depth_published = any(_bool(row["depth_valid"]) for row in rows)
    route_max = summary.get("route_observed_lateral_max_m")
    if route_max is not None:
        route_max = float(route_max)
    inspect_rows = [row for row in rows if row["stage"] == "inspect_along_cable"]
    inspection_x_progress_m = (
        _number(inspect_rows[-1], "x_m") - _number(inspect_rows[0], "x_m")
        if len(inspect_rows) >= 2 else None
    )
    trace_reviewable = (
        max_gap <= max_sample_gap_s
        and len(rows) == int(summary["ticks"])
        and bool(summary.get("native_pvs"))
        and bool(summary.get("ros_dds"))
        and bool(summary.get("protocol_encoded"))
    )
    route_complete = (
        trace_reviewable and completed and endpoint_zero
        and "confirm" in modes and "track" in modes
        and inspection_x_progress_m is not None
        and inspection_x_progress_m >= min_inspection_x_progress_m
        and not hold_command_violations
        and all(episode["duration_s"] <= max_recoverable_hold_s
                for episode in hold_episodes)
        and route_max is not None
        and route_max <= max_route_error_m
    )
    withdrawal_trace_passed = (
        trace_reviewable and bool(hold_indices) and hold_ends[-1] == len(rows) - 1
        and not hold_command_violations and not endpoint_indices
        and bool(summary.get("recovery_status_observed"))
    )
    first_hold_displacement_m = None
    if hold_starts:
        start = rows[hold_starts[0]]
        end = rows[-1]
        first_hold_displacement_m = math.hypot(
            _number(end, "x_m") - _number(start, "x_m"),
            _number(end, "y_m") - _number(start, "y_m"),
        )
    return {
        "run": str(run_dir),
        "source_sha256": {trace_path.name: _sha256(trace_path),
                          summary_path.name: _sha256(summary_path)},
        "evidence_level": "synthetic_PVS_software_trace",
        "trace_reviewable": trace_reviewable,
        "sample_count": len(rows), "max_sample_gap_s": max_gap,
        "duration_s": duration_s, "travelled_distance_m": distance_m,
        "search_seen": "search" in modes,
        "confirm_seen": "confirm" in modes,
        "track_seen": "track" in modes,
        "endpoint_count": len(endpoint_indices),
        "endpoint_command_zero": endpoint_zero if endpoint_indices else None,
        "software_route_complete": route_complete,
        "inspection_x_progress_m": inspection_x_progress_m,
        "route_observed_lateral_max_m": route_max,
        "hold_episodes": hold_episodes,
        "hold_command_violation_count": len(hold_command_violations),
        "hold_command_violations_first": hold_command_violations[:3],
        "software_withdrawal_trace_passed": withdrawal_trace_passed,
        "first_hold_to_final_displacement_m": first_hold_displacement_m,
        "final_ground_speed_mps": summary.get("final_ground_speed_mps"),
        "depth_published": depth_published,
        "independent_ros_receipt_verified": False,
        "physical_pc104_verified": False,
        "physical_motion_verified": False,
        "field_release_authorized": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, action="append", required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--max-sample-gap-s", type=float, default=0.5)
    parser.add_argument("--max-route-error-m", type=float, default=2.0)
    parser.add_argument("--max-recoverable-hold-s", type=float, default=30.0)
    parser.add_argument("--min-inspection-x-progress-m", type=float, default=78.0)
    args = parser.parse_args()
    if min(args.max_sample_gap_s, args.max_route_error_m,
           args.max_recoverable_hold_s,
           args.min_inspection_x_progress_m) <= 0:
        parser.error("limits must be positive")
    runs = [audit_run(path, max_sample_gap_s=args.max_sample_gap_s,
                      max_route_error_m=args.max_route_error_m,
                      max_recoverable_hold_s=args.max_recoverable_hold_s,
                      min_inspection_x_progress_m=args.min_inspection_x_progress_m)
            for path in args.run]
    result = {
        "schema_version": 1,
        "scope": "historical synthetic software traces only",
        "auditor_sha256": _sha256(Path(__file__)),
        "limits": {"max_sample_gap_s": args.max_sample_gap_s,
                   "max_route_error_m": args.max_route_error_m,
                   "max_recoverable_hold_s": args.max_recoverable_hold_s,
                   "min_inspection_x_progress_m": args.min_inspection_x_progress_m},
        "run_count": len(runs),
        "software_route_complete_count": sum(r["software_route_complete"] for r in runs),
        "software_withdrawal_trace_passed_count": sum(
            r["software_withdrawal_trace_passed"] for r in runs),
        "field_release_authorized": False,
        "runs": runs,
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n",
                                encoding="utf-8")
    print(json.dumps({key: result[key] for key in
                      ("run_count", "software_route_complete_count",
                       "software_withdrawal_trace_passed_count",
                       "field_release_authorized")}, ensure_ascii=False))
    return 0 if all(r["trace_reviewable"] for r in runs) else 2


if __name__ == "__main__":
    raise SystemExit(main())

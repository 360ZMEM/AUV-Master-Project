#!/usr/bin/env python3
"""Summarize terrain CBF recheck runs from analyze_bag output and MCAP debug."""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.analyze_bag import ensure_runtime_dependencies  # noqa: E402


def parse_case(value: str) -> tuple[str, Path, Path]:
    parts = value.split(":", 2)
    if len(parts) != 3 or not all(part.strip() for part in parts):
        raise argparse.ArgumentTypeError(
            "--case must use label:summary_statistics.csv:rosbag_0.mcap"
        )
    label, summary_path, mcap_path = parts
    return label.strip(), Path(summary_path).expanduser(), Path(mcap_path).expanduser()


def load_summary(path: Path) -> dict[str, str]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        return {str(row["metric"]): str(row["value"]) for row in reader}


def as_float(value: str | None) -> float:
    if value is None:
        return float("nan")
    try:
        return float(value)
    except ValueError:
        return float("nan")


def finite_range(values: list[float]) -> tuple[float, float]:
    finite = [value for value in values if math.isfinite(value)]
    if not finite:
        return float("nan"), float("nan")
    return min(finite), max(finite)


def extract_debug_metrics(mcap_path: Path) -> dict[str, Any]:
    ensure_runtime_dependencies()
    from mcap_ros2.reader import read_ros2_messages

    count = 0
    cbf_enabled = 0
    cbf_active = 0
    speed_scales: list[float] = []
    filtered_speeds: list[float] = []
    target_depths: list[float] = []
    current_depths: list[float] = []
    reasons: dict[str, int] = {}

    for decoded in read_ros2_messages(str(mcap_path), topics={"/auv/controller/debug"}):
        payload = str(getattr(decoded.ros_msg, "data", ""))
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            continue
        terrain = data.get("terrain_cbf") or {}
        if not isinstance(terrain, dict):
            terrain = {}
        count += 1
        if terrain.get("cbf_enabled") is True:
            cbf_enabled += 1
        if terrain.get("cbf_active") is True:
            cbf_active += 1
        reason = terrain.get("cbf_reason")
        if reason:
            reasons[str(reason)] = reasons.get(str(reason), 0) + 1
        for key, target in (
            ("cbf_speed_scale", speed_scales),
            ("cbf_filtered_speed_mps", filtered_speeds),
        ):
            value = terrain.get(key)
            if isinstance(value, (int, float)) and math.isfinite(float(value)):
                target.append(float(value))
        for key, target in (
            ("target_depth_m", target_depths),
            ("current_depth_m", current_depths),
        ):
            value = data.get(key)
            if isinstance(value, (int, float)) and math.isfinite(float(value)):
                target.append(float(value))

    speed_min, speed_max = finite_range(speed_scales)
    filtered_speed_min, filtered_speed_max = finite_range(filtered_speeds)
    target_depth_min, target_depth_max = finite_range(target_depths)
    current_depth_min, current_depth_max = finite_range(current_depths)
    return {
        "controller_debug_samples": count,
        "cbf_enabled_samples": cbf_enabled,
        "cbf_active_samples": cbf_active,
        "cbf_active_ratio": (cbf_active / count) if count else float("nan"),
        "cbf_speed_scale_min": speed_min,
        "cbf_speed_scale_max": speed_max,
        "cbf_filtered_speed_min_mps": filtered_speed_min,
        "cbf_filtered_speed_max_mps": filtered_speed_max,
        "target_depth_min_m": target_depth_min,
        "target_depth_max_m": target_depth_max,
        "current_depth_min_m": current_depth_min,
        "current_depth_max_m": current_depth_max,
        "cbf_reasons_json": json.dumps(reasons, ensure_ascii=False, sort_keys=True),
    }


def build_row(label: str, summary_path: Path, mcap_path: Path) -> dict[str, Any]:
    summary = load_summary(summary_path)
    row: dict[str, Any] = {
        "run": label,
        "duration_s": as_float(summary.get("duration_s")),
        "clearance_source": summary.get("clearance_source", ""),
        "seabed_clearance_min_m": as_float(summary.get("seabed_clearance_min_m")),
        "seabed_clearance_mean_m": as_float(summary.get("seabed_clearance_mean_m")),
        "seabed_clearance_rmse_to_3m": as_float(
            summary.get("seabed_clearance_rmse_to_3m")
        ),
        "seabed_clearance_safety_violation_ratio_1p5m": as_float(
            summary.get("seabed_clearance_safety_violation_ratio_1p5m")
        ),
        "seabed_penetration_ratio": as_float(summary.get("seabed_penetration_ratio")),
        "depth_error_rmse_diag_m": as_float(summary.get("depth_error_rmse_diag_m")),
        "solve_time_p95_ms": as_float(summary.get("solve_time_p95_ms")),
        "solver_fallback_ratio": as_float(summary.get("solver_fallback_ratio")),
        "solver_status_sample_count": as_float(summary.get("solver_status_sample_count")),
        "summary_statistics_csv": str(summary_path),
        "raw_mcap": str(mcap_path),
    }
    row.update(extract_debug_metrics(mcap_path))
    return row


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_report(path: Path, rows: list[dict[str, Any]], *, title: str, boundary_note: str) -> None:
    lines = [
        f"# {title}",
        "",
        "| run | duration s | min clearance m | mean clearance m | violation <1.5 m | penetration | CBF active | speed scale | solver p95 ms | fallback |",
        "|---|---:|---:|---:|---:|---:|---:|---|---:|---:|",
    ]
    for row in rows:
        speed = f"{row['cbf_speed_scale_min']:.3f}-{row['cbf_speed_scale_max']:.3f}"
        p95 = row["solve_time_p95_ms"]
        p95_text = "n/a" if not math.isfinite(float(p95)) else f"{float(p95):.2f}"
        fallback = row["solver_fallback_ratio"]
        fallback_text = "n/a" if not math.isfinite(float(fallback)) else f"{float(fallback):.3f}"
        lines.append(
            "| {run} | {duration:.2f} | {min_clearance:.2f} | {mean_clearance:.2f} | "
            "{violation:.3f} | {penetration:.3f} | {active}/{debug} | {speed} | "
            "{p95} | {fallback} |".format(
                run=row["run"],
                duration=float(row["duration_s"]),
                min_clearance=float(row["seabed_clearance_min_m"]),
                mean_clearance=float(row["seabed_clearance_mean_m"]),
                violation=float(row["seabed_clearance_safety_violation_ratio_1p5m"]),
                penetration=float(row["seabed_penetration_ratio"]),
                active=int(row["cbf_active_samples"]),
                debug=int(row["controller_debug_samples"]),
                speed=speed,
                p95=p95_text,
                fallback=fallback_text,
            )
        )
    lines.extend(
        [
            "",
            f"Boundary: {boundary_note}",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", action="append", type=parse_case, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--report-title", default="CBF terrain 60 s summary")
    parser.add_argument(
        "--boundary-note",
        default=(
            "manual setpoint bypass and kinematic setpoint proxy; does not validate "
            "native PVS depthHeadingAutopilot or all cable extreme scenarios."
        ),
    )
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    rows = [build_row(label, summary, mcap) for label, summary, mcap in args.case]
    write_csv(args.output_dir / "cbf_terrain_recheck_summary.csv", rows)
    (args.output_dir / "cbf_terrain_recheck_summary.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    write_report(
        args.output_dir / "cbf_terrain_recheck_report.md",
        rows,
        title=args.report_title,
        boundary_note=args.boundary_note,
    )
    print(args.output_dir / "cbf_terrain_recheck_summary.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

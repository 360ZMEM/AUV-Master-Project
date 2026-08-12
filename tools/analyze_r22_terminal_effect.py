#!/usr/bin/env python3
"""Audit terminal-tail effects in R22 native cable closed-loop bundles.

Long fixed-duration R22 runs can continue after the finite cable reference path
has been exhausted.  This script recomputes lateral tracking metrics using the
same path construction as the runner, then separates active tracking samples
from terminal-tail samples.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from algorithm.native_cable_scenario import NativeCableScenario  # noqa: E402
from tools.run_native_cable_closed_loop import (  # noqa: E402
    DEFAULT_NOISE_PATH,
    build_native_path,
    factors_from_label,
    load_measured_noise,
    nearest_index,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle_dir", type=Path)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--noise-path", type=Path, default=DEFAULT_NOISE_PATH)
    parser.add_argument("--path-ds", type=float, default=0.25)
    parser.add_argument("--target-speed-mps", type=float, default=0.65)
    parser.add_argument("--minimum-reference-speed-mps", type=float, default=0.20)
    parser.add_argument("--target-altitude-m", type=float, default=3.0)
    return parser.parse_args()


def percentile(values: list[float], q: float) -> float:
    finite = np.asarray([value for value in values if math.isfinite(value)], dtype=float)
    if finite.size == 0:
        return float("nan")
    return float(np.percentile(finite, q))


def finite_max(values: list[float]) -> float:
    finite = [value for value in values if math.isfinite(value)]
    return float(max(finite)) if finite else float("nan")


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def lateral_series(rows: list[dict[str, str]], path: np.ndarray) -> list[float]:
    nearest = 0
    values: list[float] = []
    for row in rows:
        xy = np.asarray([float(row["x_m"]), float(row["y_m"])], dtype=float)
        nearest = nearest_index(path, xy, nearest)
        values.append(float(np.linalg.norm(xy - path[nearest, :2])))
    return values


def cable_distance_series(rows: list[dict[str, str]]) -> list[float]:
    return [float(row["cable_distance_m"]) for row in rows]


def first_terminal_index(rows: list[dict[str, str]], path_end_index: int) -> int | None:
    for index, row in enumerate(rows):
        if int(float(row["ref_index"])) >= path_end_index:
            return index
    return None


def summarize_part(values: list[float], prefix: str) -> dict[str, object]:
    return {
        f"{prefix}_p95_m": percentile(values, 95.0),
        f"{prefix}_max_m": finite_max(values),
    }


def audit_bundle(args: argparse.Namespace) -> tuple[list[dict[str, object]], dict[str, object]]:
    bundle_dir = args.bundle_dir
    metrics_path = bundle_dir / "native_closed_loop_metrics.csv"
    traces_dir = bundle_dir / "traces"
    if not metrics_path.exists():
        raise FileNotFoundError(metrics_path)
    if not traces_dir.exists():
        raise FileNotFoundError(traces_dir)

    noise_t, noise_rate_hz, _metadata = load_measured_noise(args.noise_path.resolve())
    rows_out: list[dict[str, object]] = []

    for metric in load_csv(metrics_path):
        run_id = metric["run_id"]
        factor_label = metric["factor_label"]
        seed = int(metric["seed"])
        trace_path = traces_dir / f"{run_id}.csv"
        trace_rows = load_csv(trace_path)

        scenario = NativeCableScenario(
            factors=factors_from_label(factor_label),
            seed=seed,
            replay_noise_t=noise_t,
            replay_rate_hz=noise_rate_hz,
        )
        path = build_native_path(
            scenario,
            ds=args.path_ds,
            target_altitude_m=args.target_altitude_m,
            target_speed_mps=args.target_speed_mps,
            min_speed_mps=args.minimum_reference_speed_mps,
        )
        terminal_index = first_terminal_index(trace_rows, len(path) - 1)
        metric_terminal_reached = bool(int(float(metric.get("terminal_reached", 0) or 0)))
        metric_terminal_exit_time = float(
            metric.get("terminal_exit_time_s", float("nan")) or float("nan")
        )
        split_index = terminal_index if terminal_index is not None else len(trace_rows)

        lateral = lateral_series(trace_rows, path)
        cable_distance = cable_distance_series(trace_rows)
        active_lateral = lateral[:split_index]
        terminal_lateral = lateral[split_index:]
        active_cable = cable_distance[:split_index]
        terminal_cable = cable_distance[split_index:]
        first_terminal_time = (
            float(trace_rows[terminal_index]["time_s"])
            if terminal_index is not None
            else metric_terminal_exit_time
        )
        terminal_reached = terminal_index is not None or metric_terminal_reached

        row: dict[str, object] = {
            "run_id": run_id,
            "factor_label": factor_label,
            "seed": seed,
            "mpc_mode": metric["mpc_mode"],
            "duration_s": metric["duration_s"],
            "terminal_policy": metric.get("terminal_policy", "continue"),
            "terminal_reached": int(terminal_reached),
            "first_terminal_time_s": first_terminal_time,
            "sample_count": len(trace_rows),
            "active_sample_count": len(active_lateral),
            "terminal_sample_count": len(terminal_lateral),
            "terminal_fraction": len(terminal_lateral) / max(1, len(trace_rows)),
            "reported_lateral_p95_m": float(metric["lateral_p95_m"]),
            "reported_lateral_max_m": float(metric["lateral_max_m"]),
        }
        row.update(summarize_part(lateral, "full_lateral"))
        row.update(summarize_part(active_lateral, "active_lateral"))
        row.update(summarize_part(terminal_lateral, "terminal_lateral"))
        row.update(summarize_part(cable_distance, "full_cable_distance"))
        row.update(summarize_part(active_cable, "active_cable_distance"))
        row.update(summarize_part(terminal_cable, "terminal_cable_distance"))
        rows_out.append(row)

    terminal_reached_count = sum(int(row["terminal_reached"]) for row in rows_out)
    terminal_lateral_p95_values = [
        float(row["terminal_lateral_p95_m"])
        for row in rows_out
        if math.isfinite(float(row["terminal_lateral_p95_m"]))
    ]
    summary = {
        "bundle_dir": str(bundle_dir),
        "run_count": len(rows_out),
        "terminal_reached_count": terminal_reached_count,
        "terminal_reached_rate": terminal_reached_count / max(1, len(rows_out)),
        "active_lateral_p95_max_m": finite_max(
            [float(row["active_lateral_p95_m"]) for row in rows_out]
        ),
        "terminal_lateral_p95_max_m": finite_max(
            [float(row["terminal_lateral_p95_m"]) for row in rows_out]
        ),
        "full_lateral_p95_max_m": finite_max(
            [float(row["full_lateral_p95_m"]) for row in rows_out]
        ),
        "active_lateral_p95_mean_m": statistics.mean(
            [float(row["active_lateral_p95_m"]) for row in rows_out]
        )
        if rows_out
        else float("nan"),
        "terminal_lateral_p95_mean_m": (
            statistics.mean(terminal_lateral_p95_values)
            if terminal_lateral_p95_values
            else float("nan")
        ),
    }
    return rows_out, summary


def write_report(path: Path, summary: dict[str, object]) -> None:
    lines = [
        "# R22 Terminal Effect Audit",
        "",
        f"- Bundle: `{summary['bundle_dir']}`",
        f"- Runs: {summary['run_count']}",
        f"- Terminal reached: {summary['terminal_reached_count']} "
        f"({float(summary['terminal_reached_rate']):.3f})",
        f"- Full-window lateral p95 max: {float(summary['full_lateral_p95_max_m']):.3f} m",
        f"- Active-tracking lateral p95 max: {float(summary['active_lateral_p95_max_m']):.3f} m",
        f"- Terminal-tail lateral p95 max: {float(summary['terminal_lateral_p95_max_m']):.3f} m",
        "",
        "Interpretation: full-window fixed-duration metrics include terminal-tail samples "
        "after the finite reference path is exhausted.  Active-tracking metrics should "
        "be used when discussing cable-following quality; terminal-tail metrics should "
        "be reported as a mission-end handling boundary.",
        "",
        "This audit is solver- and trace-postprocessing only. It does not add a native "
        "PVS or physical timing claim.",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    output_dir = args.output_dir or args.bundle_dir
    rows, summary = audit_bundle(args)
    write_csv(output_dir / "terminal_effect_audit.csv", rows)
    write_report(output_dir / "terminal_effect_report.md", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Aggregate ES-EKF sensor extrinsics benchmark results."""

from __future__ import annotations

import argparse
import csv
import math
from collections import defaultdict
from pathlib import Path
from statistics import mean, stdev


METRICS = (
    "xy_rmse",
    "z_rmse",
    "rmse_3d",
    "cep50",
    "max_drift",
    "dvl_nis_mean",
    "depth_nis_mean",
    "extrinsic_translation_error_m",
    "extrinsic_rotation_error_deg",
    "online_correction_delta_norm",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, required=True, help="Path to pure-script extrinsics results.csv")
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def to_float(value: object) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return float("nan")
    return out if math.isfinite(out) else float("nan")


def fmt(value: float) -> str:
    return "nan" if not math.isfinite(value) else f"{value:.4f}"


def write_csv(path: Path, rows: list[dict[str, object]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def add_improvements(rows: list[dict[str, str]]) -> list[dict[str, object]]:
    baselines: dict[str, float] = {}
    for row in rows:
        if row.get("estimation_mode") == "none":
            baselines[row.get("profile", "")] = to_float(row.get("rmse_3d", row.get("xy_rmse")))

    out: list[dict[str, object]] = []
    for row in rows:
        item: dict[str, object] = dict(row)
        profile = row.get("profile", "")
        baseline = baselines.get(profile, float("nan"))
        current = to_float(row.get("rmse_3d", row.get("xy_rmse")))
        if math.isfinite(baseline) and baseline > 0.0 and math.isfinite(current):
            item["improvement_vs_none_pct"] = 100.0 * (baseline - current) / baseline
        else:
            item["improvement_vs_none_pct"] = float("nan")
        out.append(item)
    return out


def summarize(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    groups: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        groups[(str(row.get("profile", "")), str(row.get("estimation_mode", "")))].append(row)

    out: list[dict[str, object]] = []
    for (profile, mode), group in sorted(groups.items()):
        item: dict[str, object] = {
            "profile": profile,
            "estimation_mode": mode,
            "run_count": len(group),
        }
        for metric in (*METRICS, "improvement_vs_none_pct"):
            values = [to_float(row.get(metric)) for row in group]
            values = [value for value in values if math.isfinite(value)]
            item[f"{metric}_mean"] = mean(values) if values else float("nan")
            item[f"{metric}_std"] = stdev(values) if len(values) > 1 else 0.0
        out.append(item)
    return out


def status_counts(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    counts: dict[tuple[str, str, str], int] = defaultdict(int)
    for row in rows:
        counts[(str(row.get("profile", "")), str(row.get("estimation_mode", "")), str(row.get("status", "")))] += 1
    return [
        {"profile": profile, "estimation_mode": mode, "status": status, "count": count}
        for (profile, mode, status), count in sorted(counts.items())
    ]


def write_report(path: Path, summary_rows: list[dict[str, object]]) -> None:
    lines = [
        "# ES-EKF Extrinsics Aggregate",
        "",
        "| profile | mode | runs | 3D RMSE | XY RMSE | Z RMSE | improvement vs none | DVL NIS | Depth NIS |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in summary_rows:
        lines.append(
            "| {profile} | {mode} | {runs} | {r3} | {xy} | {z} | {imp}% | {dvl} | {depth} |".format(
                profile=row["profile"],
                mode=row["estimation_mode"],
                runs=row["run_count"],
                r3=fmt(float(row["rmse_3d_mean"])),
                xy=fmt(float(row["xy_rmse_mean"])),
                z=fmt(float(row["z_rmse_mean"])),
                imp=fmt(float(row["improvement_vs_none_pct_mean"])),
                dvl=fmt(float(row["dvl_nis_mean_mean"])),
                depth=fmt(float(row["depth_nis_mean_mean"])),
            )
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    args = parse_args()
    rows = read_rows(args.results)
    enriched = add_improvements(rows)
    summary = summarize(enriched)
    counts = status_counts(enriched)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    by_run_fields = list(enriched[0].keys()) if enriched else []
    write_csv(args.output_dir / "extrinsics_metrics_by_run.csv", enriched, by_run_fields)
    write_csv(args.output_dir / "extrinsics_summary_by_profile_mode.csv", summary, list(summary[0].keys()) if summary else [])
    write_csv(args.output_dir / "extrinsics_status_counts.csv", counts, list(counts[0].keys()) if counts else [])
    write_report(args.output_dir / "extrinsics_aggregate_report.md", summary)
    print(f"[OK] wrote {args.output_dir / 'extrinsics_aggregate_report.md'}")


if __name__ == "__main__":
    main()

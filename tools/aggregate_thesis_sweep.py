#!/usr/bin/env python3
"""Aggregate tools/run_thesis_sweep.py results.csv into thesis-ready tables."""

from __future__ import annotations

import argparse
import csv
import math
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean, stdev


METRIC_COLUMNS = ("xy_rmse", "z_rmse", "cep50", "max_drift", "duration_s_actual")


def parse_float(value: str) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(out) or math.isinf(out):
        return None
    return out


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def metric_summary(values: list[float]) -> dict[str, float | int | str]:
    if not values:
        return {"n": 0, "mean": "", "std": "", "min": "", "max": ""}
    return {
        "n": len(values),
        "mean": mean(values),
        "std": stdev(values) if len(values) >= 2 else 0.0,
        "min": min(values),
        "max": max(values),
    }


def write_status_counts(rows: list[dict[str, str]], out_path: Path) -> None:
    counts = Counter(
        (row.get("scenario", ""), row.get("mpc_mode", ""), row.get("status", ""))
        for row in rows
    )
    with out_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f, fieldnames=["scenario", "mpc_mode", "status", "count"]
        )
        writer.writeheader()
        for (scenario, mode, status), count in sorted(counts.items()):
            writer.writerow(
                {
                    "scenario": scenario,
                    "mpc_mode": mode,
                    "status": status,
                    "count": count,
                }
            )


def write_summary(rows: list[dict[str, str]], out_path: Path) -> list[dict[str, object]]:
    groups: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        groups[(row.get("scenario", ""), row.get("mpc_mode", ""))].append(row)

    summary_rows: list[dict[str, object]] = []
    for (scenario, mode), group_rows in sorted(groups.items()):
        ok_rows = [row for row in group_rows if row.get("status") == "ok"]
        base: dict[str, object] = {
            "scenario": scenario,
            "mpc_mode": mode,
            "runs_total": len(group_rows),
            "runs_ok": len(ok_rows),
            "ok_ratio": len(ok_rows) / len(group_rows) if group_rows else 0.0,
        }
        for metric in METRIC_COLUMNS:
            values = [
                parsed
                for row in ok_rows
                if (parsed := parse_float(row.get(metric, ""))) is not None
            ]
            stats = metric_summary(values)
            for key, value in stats.items():
                base[f"{metric}_{key}"] = value
        summary_rows.append(base)

    fieldnames = [
        "scenario",
        "mpc_mode",
        "runs_total",
        "runs_ok",
        "ok_ratio",
    ]
    for metric in METRIC_COLUMNS:
        for suffix in ("n", "mean", "std", "min", "max"):
            fieldnames.append(f"{metric}_{suffix}")

    with out_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(summary_rows)
    return summary_rows


def write_report(summary_rows: list[dict[str, object]], out_path: Path, source: Path) -> None:
    lines = [
        "# Thesis Sweep 聚合报告",
        "",
        f"- source: `{source}`",
        "- 说明: 仅聚合 `status=ok` 的 run；失败 run 只进入成功率统计。",
        "",
        "## Summary By Scenario/Mode",
        "",
        "| scenario | mpc_mode | ok/total | XY RMSE mean±std | Z RMSE mean±std | CEP50 mean±std |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for row in summary_rows:
        ok_total = f"{row['runs_ok']}/{row['runs_total']}"
        xy = format_mean_std(row, "xy_rmse")
        z = format_mean_std(row, "z_rmse")
        cep = format_mean_std(row, "cep50")
        lines.append(
            f"| {row['scenario']} | {row['mpc_mode']} | {ok_total} | {xy} | {z} | {cep} |"
        )
    lines.extend(
        [
            "",
            "## 使用边界",
            "",
            "当 `runs_ok < 3` 时，结果只能写成 smoke 或低样本补充；当 `runs_ok >= 3` 时，才建议进入论文 mean±std 表格。",
        ]
    )
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def format_mean_std(row: dict[str, object], metric: str) -> str:
    n = row.get(f"{metric}_n", 0)
    if not n:
        return "NA"
    avg = float(row[f"{metric}_mean"])
    std = float(row[f"{metric}_std"])
    return f"{avg:.4f}±{std:.4f}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Aggregate thesis sweep results.csv into summary tables."
    )
    parser.add_argument("--input", required=True, type=Path, help="Path to results.csv")
    parser.add_argument(
        "--output-dir",
        required=True,
        type=Path,
        help="Directory for aggregate CSV and Markdown report",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.input.is_file():
        raise SystemExit(f"input results.csv not found: {args.input}")
    args.output_dir.mkdir(parents=True, exist_ok=True)

    rows = read_rows(args.input)
    summary_rows = write_summary(rows, args.output_dir / "summary_by_scenario_mode.csv")
    write_status_counts(rows, args.output_dir / "status_counts.csv")
    write_report(summary_rows, args.output_dir / "aggregate_report.md", args.input)
    print(f"[aggregate] wrote {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

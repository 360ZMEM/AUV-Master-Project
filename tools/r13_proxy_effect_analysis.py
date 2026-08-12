#!/usr/bin/env python3
"""Build paired UA-minus-baseline effects for the R13 proxy matrix."""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt


METRICS = (
    "lateral_error_rmse_m",
    "solver_wall_time_current_mean_ms",
    "fallback_rate",
    "control_rate_rms_per_s",
    "safety_violation_rate",
)


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_rows(path: Path, rows: list[dict[str, object]]) -> None:
    fields: list[str] = []
    for row in rows:
        for field in row:
            if field not in fields:
                fields.append(field)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metrics", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    rows = read_rows(args.metrics)
    by_key = {
        (row["scenario"], row["seed"], row["mpc_mode"]): row for row in rows
    }
    paired: list[dict[str, object]] = []
    scenarios = sorted({row["scenario"] for row in rows})
    seeds = sorted({row["seed"] for row in rows}, key=int)
    for scenario in scenarios:
        for seed in seeds:
            baseline = by_key[(scenario, seed, "baseline")]
            ua = by_key[(scenario, seed, "ua")]
            item: dict[str, object] = {"scenario": scenario, "seed": seed}
            for metric in METRICS:
                baseline_value = float(baseline[metric])
                ua_value = float(ua[metric])
                item[f"{metric}_baseline"] = baseline_value
                item[f"{metric}_ua"] = ua_value
                item[f"{metric}_ua_minus_baseline"] = ua_value - baseline_value
            paired.append(item)

    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in paired:
        grouped[str(row["scenario"])].append(row)
    summary: list[dict[str, object]] = []
    for scenario, group in sorted(grouped.items()):
        item: dict[str, object] = {"scenario": scenario, "paired_seed_count": len(group)}
        for metric in METRICS:
            baseline = np.asarray(
                [float(row[f"{metric}_baseline"]) for row in group]
            )
            ua = np.asarray([float(row[f"{metric}_ua"]) for row in group])
            difference = ua - baseline
            item[f"{metric}_baseline_mean"] = float(np.mean(baseline))
            item[f"{metric}_ua_mean"] = float(np.mean(ua))
            item[f"{metric}_effect_mean"] = float(np.mean(difference))
            item[f"{metric}_effect_std"] = float(np.std(difference, ddof=1))
        baseline_safety = float(item["safety_violation_rate_baseline_mean"])
        ua_safety = float(item["safety_violation_rate_ua_mean"])
        item["safety_violation_relative_reduction"] = (
            (baseline_safety - ua_safety) / baseline_safety
            if baseline_safety > 0.0
            else float("nan")
        )
        summary.append(item)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_rows(args.output_dir / "paired_effects.csv", paired)
    write_rows(args.output_dir / "paired_summary.csv", summary)

    labels = [str(row["scenario"]).replace("_proxy", "") for row in summary]
    x = np.arange(len(labels))
    width = 0.36
    fig, axes = plt.subplots(2, 1, figsize=(10.5, 7.0), dpi=180)
    for axis, metric, label in (
        (axes[0], "lateral_error_rmse_m", "Lateral RMSE (m)"),
        (axes[1], "safety_violation_rate", "Safety violation rate"),
    ):
        baseline = [float(row[f"{metric}_baseline_mean"]) for row in summary]
        ua = [float(row[f"{metric}_ua_mean"]) for row in summary]
        axis.bar(x - width / 2, baseline, width, label="Baseline")
        axis.bar(x + width / 2, ua, width, label="UA")
        axis.set_ylabel(label)
        axis.grid(axis="y", alpha=0.25)
    axes[1].set_xticks(x)
    axes[1].set_xticklabels(labels, rotation=18, ha="right")
    axes[0].legend(frameon=False)
    fig.tight_layout()
    fig.savefig(args.output_dir / "r13_proxy_tracking_safety.png")
    plt.close(fig)

    lines = [
        "# R13 Paired Proxy-Scenario Effects",
        "",
        "| scenario | RMSE baseline | RMSE UA | fallback baseline | fallback UA | safety baseline | safety UA |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in summary:
        lines.append(
            f"| {row['scenario']} | "
            f"{float(row['lateral_error_rmse_m_baseline_mean']):.3f} | "
            f"{float(row['lateral_error_rmse_m_ua_mean']):.3f} | "
            f"{float(row['fallback_rate_baseline_mean']):.3f} | "
            f"{float(row['fallback_rate_ua_mean']):.3f} | "
            f"{float(row['safety_violation_rate_baseline_mean']):.3f} | "
            f"{float(row['safety_violation_rate_ua_mean']):.3f} |"
        )
    lines.extend(
        [
            "",
            "UA reduces safety violations in slope and combined-extreme cases, "
            "but does not reduce lateral RMSE in any scenario. Both modes remain "
            "dominated by 50 ms solver-deadline fallback, so R14 must isolate "
            "real-time feasibility before attributing tracking effects.",
            "",
        ]
    )
    (args.output_dir / "report.md").write_text(
        "\n".join(lines),
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

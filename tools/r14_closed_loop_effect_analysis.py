#!/usr/bin/env python3
"""Consolidate the R14 combined-extreme closed-loop mechanism effects."""

from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from tools.experiment_contract import finalize_bundle, initialize_bundle  # noqa: E402


METRICS = (
    "lateral_error_rmse_m",
    "control_rate_rms_per_s",
    "safety_violation_rate",
    "solver_wall_time_current_mean_ms",
    "fallback_rate",
)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    fields: list[str] = []
    for row in rows:
        for field in row:
            if field not in fields:
                fields.append(field)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def select(
    path: Path,
    *,
    variant: str,
    mode: str,
) -> list[dict[str, object]]:
    output = []
    for row in read_csv(path):
        if row["scenario"] != "combined_cable_extreme_proxy":
            continue
        if row["mpc_mode"] != mode:
            continue
        output.append({**row, "variant": variant})
    if len(output) != 3:
        raise ValueError(f"{variant} expected 3 rows, found {len(output)}")
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--main-metrics",
        type=Path,
        default=REPO_ROOT
        / "results/control_aggregates/20260809_r14_smooth_closed_loop/"
        "control_metrics_by_run.csv",
    )
    parser.add_argument(
        "--no-control-discount-metrics",
        type=Path,
        default=REPO_ROOT
        / "results/control_aggregates/20260809_r14_no_control_discount/"
        "control_metrics_by_run.csv",
    )
    parser.add_argument(
        "--no-tracking-amplification-metrics",
        type=Path,
        default=REPO_ROOT
        / "results/control_aggregates/"
        "20260809_r14_no_tracking_amplification_authoritative/"
        "aggregate/control_metrics_by_run.csv",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPO_ROOT
        / "results/control/r14_r13_diagnosis/"
        "20260809_r14_closed_loop_effects",
    )
    args = parser.parse_args()
    rows = [
        *select(args.main_metrics, variant="baseline", mode="baseline"),
        *select(args.main_metrics, variant="ua_current", mode="ua"),
        *select(
            args.no_control_discount_metrics,
            variant="ua_no_control_discount",
            mode="ua",
        ),
        *select(
            args.no_tracking_amplification_metrics,
            variant="ua_no_tracking_amplification",
            mode="ua",
        ),
    ]
    initialize_bundle(
        args.output_dir,
        experiment_id="r14_closed_loop_mechanism_effects",
        runner="tools/r14_closed_loop_effect_analysis.py",
        argv=sys.argv,
        data_layer="pvs_proxy_closed_loop_paired_mechanism_ablation",
        matrix={
            "scenario": "combined_cable_extreme_proxy",
            "variants": sorted({str(row["variant"]) for row in rows}),
            "seeds": [0, 1, 2],
        },
        duration_s=30.0,
        config_paths=[
            Path(__file__),
            args.main_metrics,
            args.no_control_discount_metrics,
            args.no_tracking_amplification_metrics,
        ],
        extra_manifest={
            "hardware_claim": False,
            "paired_seed_design": True,
        },
    )
    contract_rows = []
    for row in rows:
        contract_rows.append(
            {
                **row,
                "run_id": f"{row['variant']}__seed{row['seed']}",
                "status": "ok",
            }
        )
    finalize_bundle(args.output_dir, contract_rows)

    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["variant"])].append(row)
    summary = []
    for variant, group in grouped.items():
        item: dict[str, object] = {"variant": variant, "run_count": len(group)}
        for metric in METRICS:
            values = np.asarray([float(row[metric]) for row in group])
            item[f"{metric}_mean"] = float(np.mean(values))
            item[f"{metric}_std"] = float(np.std(values, ddof=1))
        summary.append(item)
    order = (
        "baseline",
        "ua_current",
        "ua_no_control_discount",
        "ua_no_tracking_amplification",
    )
    summary.sort(key=lambda row: order.index(str(row["variant"])))
    write_csv(args.output_dir / "summary_by_variant.csv", summary)

    by_variant_seed = {
        (str(row["variant"]), str(row["seed"])): row for row in rows
    }
    paired = []
    for variant in order[1:]:
        for seed in ("0", "1", "2"):
            baseline = by_variant_seed[("baseline", seed)]
            candidate = by_variant_seed[(variant, seed)]
            item: dict[str, object] = {"variant": variant, "seed": seed}
            for metric in METRICS:
                item[f"{metric}_candidate_minus_baseline"] = (
                    float(candidate[metric]) - float(baseline[metric])
                )
            paired.append(item)
    write_csv(args.output_dir / "paired_effects.csv", paired)

    labels = [
        "Baseline",
        "Current UA",
        "No control discount",
        "No tracking amp.",
    ]
    x = np.arange(len(summary))
    fig, axes = plt.subplots(1, 3, figsize=(11.5, 4.0), dpi=180)
    plot_metrics = (
        ("lateral_error_rmse_m", "Lateral RMSE (m)"),
        ("control_rate_rms_per_s", "Control-rate RMS (/s)"),
        ("safety_violation_rate", "Safety violation rate"),
    )
    colors = ("#4C78A8", "#E45756", "#F58518", "#72B7B2")
    for axis, (metric, label) in zip(axes, plot_metrics):
        means = [float(row[f"{metric}_mean"]) for row in summary]
        spread = [float(row[f"{metric}_std"]) for row in summary]
        axis.bar(x, means, yerr=spread, capsize=3, color=colors)
        axis.set_ylabel(label)
        axis.set_xticks(x)
        axis.set_xticklabels(labels, rotation=24, ha="right")
        axis.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(args.output_dir / "figures/r14_closed_loop_mechanisms.png")
    plt.close(fig)

    lines = [
        "# R14 Closed-Loop Mechanism Effects",
        "",
        "| variant | RMSE m | control-rate RMS | safety violation | solve mean ms | fallback |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for row in summary:
        lines.append(
            f"| {row['variant']} | "
            f"{float(row['lateral_error_rmse_m_mean']):.4f} | "
            f"{float(row['control_rate_rms_per_s_mean']):.2f} | "
            f"{float(row['safety_violation_rate_mean']):.4f} | "
            f"{float(row['solver_wall_time_current_mean_ms_mean']):.2f} | "
            f"{float(row['fallback_rate_mean']):.3f} |"
        )
    lines.extend(
        [
            "",
            "The confidence observed by UA was nearly constant at 0.367. "
            "These variants therefore identify fixed weight effects, not "
            "online uncertainty adaptation.",
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

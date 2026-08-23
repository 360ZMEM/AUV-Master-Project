#!/usr/bin/env python3
"""Generate R13-v2 formal-matrix audit figures and summary tables."""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path
from typing import Iterable

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from mcap_ros2.reader import read_ros2_messages

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
from tools import thesis_plot_style as tps  # noqa: E402
DEFAULT_BUNDLE = (
    PROJECT_ROOT
    / "log/proxy_cable_sweep/20260810_000843_r13_v2_formal_20260810T000842"
)
DEFAULT_AGGREGATE = (
    PROJECT_ROOT / "results/control_aggregates/20260810_r13_v2_full"
)
DEFAULT_OUTPUT = DEFAULT_AGGREGATE / "r13_v2_thesis_audit"
DEFAULT_FIGURE_OUTPUT = (
    PROJECT_ROOT / "docs/thesis/figures/experiments/control"
)
SONAR_QUALITY_TOPIC = "/auv/perception/quality/sonar"
SCENARIO_ORDER = (
    "cable_s_curve_proxy",
    "cable_hairpin_proxy",
    "cable_slope_crossing_proxy",
    "cable_buried_gap_proxy",
    "cable_cross_current_proxy",
    "combined_cable_extreme_proxy",
)
SCENARIO_LABELS = {
    "cable_s_curve_proxy": "S 形弯",
    "cable_hairpin_proxy": "发卡弯",
    "cable_slope_crossing_proxy": "坡面横穿",
    "cable_buried_gap_proxy": "埋设间断",
    "cable_cross_current_proxy": "横向流",
    "combined_cable_extreme_proxy": "综合极端",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, default=DEFAULT_BUNDLE)
    parser.add_argument("--aggregate-dir", type=Path, default=DEFAULT_AGGREGATE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--figure-output-dir",
        type=Path,
        default=DEFAULT_FIGURE_OUTPUT,
    )
    parser.add_argument(
        "--p-track-csv",
        type=Path,
        default=DEFAULT_OUTPUT / "r13_v2_p_track_samples_ua.csv",
    )
    parser.add_argument(
        "--skip-mcap",
        action="store_true",
        help="Use existing p-track sample CSV instead of rereading MCAP files.",
    )
    return parser.parse_args()


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv_rows(path: Path, rows: list[dict[str, object]]) -> None:
    fields: list[str] = []
    for row in rows:
        for field in row:
            if field not in fields:
                fields.append(field)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def fval(row: dict[str, str], key: str) -> float:
    value = row.get(key, "")
    try:
        return float(value)
    except (TypeError, ValueError):
        return float("nan")


def ordered(rows: Iterable[dict[str, str]]) -> list[dict[str, str]]:
    by_scenario = {row["scenario"]: row for row in rows}
    return [by_scenario[name] for name in SCENARIO_ORDER if name in by_scenario]


def setup_style() -> None:
    tps.apply_thesis_style(layout="full")


def save_figure(fig: plt.Figure, output_dir: Path, stem: str) -> None:
    tps.save_figure(fig, output_dir / stem)
    plt.close(fig)


def opaque_legend(axis: plt.Axes, *args, **kwargs) -> None:
    kwargs.update(
        {
            "frameon": True,
            "facecolor": "white",
            "framealpha": 1.0,
            "edgecolor": "#BFBFBF",
        }
    )
    legend = axis.legend(*args, **kwargs)
    legend.get_frame().set_linewidth(0.8)


def read_pt_samples(bundle: Path, output_csv: Path, *, skip_mcap: bool) -> list[dict[str, object]]:
    if skip_mcap:
        return [dict(row) for row in read_csv_rows(output_csv)]

    rows = read_csv_rows(bundle / "results.csv")
    samples: list[dict[str, object]] = []
    for row in rows:
        if row.get("mpc_mode") != "ua":
            continue
        mcap = Path(row["mcap"])
        count = 0
        for decoded in read_ros2_messages(str(mcap), topics=[SONAR_QUALITY_TOPIC]):
            value = float(decoded.ros_msg.p_track)
            if math.isfinite(value):
                samples.append(
                    {
                        "scenario": row["scenario"],
                        "seed": int(row["seed"]),
                        "sample_index": count,
                        "p_track": value,
                    }
                )
                count += 1
        print(f"read {count:4d} sonar p_track samples from {row['scenario']} seed {row['seed']}")
    write_csv_rows(output_csv, samples)
    return samples


def percentile(values: list[float], q: float) -> float:
    if not values:
        return float("nan")
    return float(np.percentile(np.asarray(values, dtype=float), q))


def p_track_stats(samples: list[dict[str, object]]) -> dict[str, dict[str, float]]:
    by_scenario: dict[str, list[float]] = {name: [] for name in SCENARIO_ORDER}
    for sample in samples:
        scenario = str(sample["scenario"])
        if scenario in by_scenario:
            by_scenario[scenario].append(float(sample["p_track"]))
    stats: dict[str, dict[str, float]] = {}
    for scenario, values in by_scenario.items():
        stats[scenario] = {
            "count": float(len(values)),
            "min": min(values, default=float("nan")),
            "q05": percentile(values, 5.0),
            "q50": percentile(values, 50.0),
            "q95": percentile(values, 95.0),
            "max": max(values, default=float("nan")),
        }
    return stats


def plot_rmse(paired_rows: list[dict[str, str]], output_dir: Path) -> None:
    rows = ordered(paired_rows)
    labels = [SCENARIO_LABELS[row["scenario"]] for row in rows]
    x = np.arange(len(rows))
    width = 0.36
    baseline = [fval(row, "baseline_rmse_m") for row in rows]
    ua = [fval(row, "ua_rmse_m") for row in rows]
    delta = [fval(row, "rmse_delta_pct") for row in rows]

    fig, axis = plt.subplots(
        figsize=tps.figure_size("full", height=3.15),
        constrained_layout=True,
    )
    axis.bar(
        x - width / 2,
        baseline,
        width,
        color=tps.BASELINE_1,
        hatch="//",
        label="固定权重基线",
    )
    axis.bar(
        x + width / 2,
        ua,
        width,
        color=tps.PROPOSED,
        label="分源不确定性感知",
    )
    axis.set_ylabel("横向 RMSE (m)")
    axis.set_xticks(x)
    axis.set_xticklabels(labels, rotation=20, ha="right")
    opaque_legend(axis)
    for idx, value in enumerate(delta):
        axis.text(
            idx,
            max(baseline[idx], ua[idx]) + 0.35,
            f"{value:+.1f}%",
            ha="center",
            va="bottom",
            fontsize=8,
        )
    save_figure(fig, output_dir, "r13_v2_rmse_paired")


def plot_control_rate(paired_rows: list[dict[str, str]], output_dir: Path) -> None:
    rows = ordered(paired_rows)
    labels = [SCENARIO_LABELS[row["scenario"]] for row in rows]
    x = np.arange(len(rows))
    width = 0.36
    baseline = [fval(row, "baseline_control_rate_rms") for row in rows]
    ua = [fval(row, "ua_control_rate_rms") for row in rows]
    delta = [fval(row, "control_rate_delta_pct") for row in rows]

    fig, axis = plt.subplots(
        figsize=tps.figure_size("full", height=3.15),
        constrained_layout=True,
    )
    axis.bar(
        x - width / 2,
        baseline,
        width,
        color=tps.BASELINE_1,
        hatch="//",
        label="固定权重基线",
    )
    axis.bar(
        x + width / 2,
        ua,
        width,
        color=tps.PROPOSED,
        label="分源不确定性感知",
    )
    axis.set_yscale("log")
    axis.set_ylabel("控制变化率 RMS (对数轴)")
    axis.set_xticks(x)
    axis.set_xticklabels(labels, rotation=20, ha="right")
    opaque_legend(axis)
    for idx, value in enumerate(delta):
        axis.text(
            idx,
            max(baseline[idx], ua[idx]) * 1.25,
            f"{value:+.0f}%",
            ha="center",
            va="bottom",
            fontsize=8,
        )
    save_figure(fig, output_dir, "r13_v2_control_rate_paired")


def plot_authority(summary_rows: list[dict[str, str]], output_dir: Path) -> None:
    ua_rows = [row for row in summary_rows if row.get("mode") == "ua"]
    rows = ordered(ua_rows)
    labels = [SCENARIO_LABELS[row["scenario"]] for row in rows]
    hold = np.asarray([100.0 * fval(row, "hold_ratio_mean") for row in rows])
    search = np.asarray([100.0 * fval(row, "search_ratio_mean") for row in rows])
    track = np.asarray([100.0 * fval(row, "track_ratio_mean") for row in rows])
    x = np.arange(len(rows))

    fig, axis = plt.subplots(
        figsize=tps.figure_size("full", height=3.1),
        constrained_layout=True,
    )
    axis.bar(x, hold, color=tps.NEUTRAL, label="保持")
    axis.bar(
        x,
        search,
        bottom=hold,
        color=tps.BASELINE_1,
        hatch="//",
        label="搜索",
    )
    axis.bar(
        x,
        track,
        bottom=hold + search,
        color=tps.PROPOSED,
        label="跟踪",
    )
    axis.set_ylim(0.0, 100.0)
    axis.set_ylabel("授权模式占比 (%)")
    axis.set_xticks(x)
    axis.set_xticklabels(labels, rotation=20, ha="right")
    opaque_legend(axis, ncol=3, loc="upper right")
    for idx, row in enumerate(rows):
        if row["scenario"] == "combined_cable_extreme_proxy":
            axis.text(idx, 103.0, "跟踪 0%", ha="center", va="bottom")
    save_figure(fig, output_dir, "r13_v2_authority_modes_ua")


def plot_p_track(samples: list[dict[str, object]], output_dir: Path) -> None:
    grouped: list[list[float]] = []
    labels: list[str] = []
    for scenario in SCENARIO_ORDER:
        values = [
            float(sample["p_track"])
            for sample in samples
            if str(sample["scenario"]) == scenario
        ]
        grouped.append(values)
        labels.append(SCENARIO_LABELS[scenario])

    fig, axis = plt.subplots(
        figsize=tps.figure_size("full", height=3.15),
        constrained_layout=True,
    )
    axis.boxplot(
        grouped,
        tick_labels=labels,
        showfliers=False,
        patch_artist=True,
        medianprops={"color": tps.REFERENCE, "linewidth": 1.2},
        boxprops={"facecolor": "#D9EAF4", "color": tps.PROPOSED},
        whiskerprops={"color": tps.PROPOSED},
        capprops={"color": tps.PROPOSED},
    )
    axis.axhline(
        0.75,
        color=tps.WARNING,
        linestyle="--",
        linewidth=1.0,
        label="进入跟踪阈值",
    )
    axis.axhline(
        0.55,
        color=tps.BASELINE_1,
        linestyle="-.",
        linewidth=1.0,
        label="进入搜索阈值",
    )
    axis.set_ylim(0.0, 1.02)
    axis.set_ylabel(r"声呐跟踪概率 $p_{\mathrm{track}}$")
    axis.set_xticklabels(labels, rotation=20, ha="right")
    opaque_legend(axis, ncol=2, loc="lower right")
    save_figure(fig, output_dir, "r13_v2_p_track_boxplot_ua")


def claim_class(scenario: str, rmse_delta_pct: float, control_delta_pct: float, track_ratio: float) -> str:
    if scenario == "combined_cable_extreme_proxy":
        return "boundary_no_track"
    if scenario == "cable_buried_gap_proxy":
        return "primary_mechanism"
    if control_delta_pct <= -50.0:
        return "smoothness_evidence"
    if rmse_delta_pct < 0.0 and track_ratio > 0.5:
        return "weak_tracking_support"
    return "matrix_completeness"


def render_markdown_table(rows: list[dict[str, object]]) -> str:
    lines = [
        "# R13-v2 Thesis Claim Boundary Table",
        "",
        "| scenario | claim class | RMSE delta | control-rate delta | TRACK share | thesis use |",
        "|---|---|---:|---:|---:|---|",
    ]
    thesis_use = {
        "primary_mechanism": "main confidence-chain evidence",
        "smoothness_evidence": "smoothness evidence, not RMSE evidence",
        "weak_tracking_support": "secondary support only",
        "matrix_completeness": "matrix completeness and scoped result",
        "boundary_no_track": "negative boundary / SEARCH-HOLD case",
    }
    for row in rows:
        cls = str(row["claim_class"])
        lines.append(
            "| {scenario} | {cls} | {rmse:+.2f}% | {control:+.2f}% | {track:.1f}% | {use} |".format(
                scenario=SCENARIO_LABELS[str(row["scenario"])],
                cls=cls,
                rmse=float(row["rmse_delta_pct"]),
                control=float(row["control_rate_delta_pct"]),
                track=100.0 * float(row["ua_track_ratio"]),
                use=thesis_use[cls],
            )
        )
    lines.append("")
    return "\n".join(lines)


def render_latex_table(rows: list[dict[str, object]]) -> str:
    lines = [
        r"\begin{tabular}{lrrrrl}",
        r"\toprule",
        r"Scenario & RMSE$_b$ & RMSE$_{UA}$ & $\Delta$RMSE & $\Delta$rate & Claim \\",
        r"\midrule",
    ]
    for row in rows:
        lines.append(
            "{scenario} & {rb:.2f} & {ru:.2f} & {rd:+.1f}\\% & {cd:+.1f}\\% & {cls} \\\\".format(
                scenario=SCENARIO_LABELS[str(row["scenario"])],
                rb=float(row["baseline_rmse_m"]),
                ru=float(row["ua_rmse_m"]),
                rd=float(row["rmse_delta_pct"]),
                cd=float(row["control_rate_delta_pct"]),
                cls=str(row["claim_class"]).replace("_", r"\_"),
            )
        )
    lines.extend([r"\bottomrule", r"\end{tabular}", ""])
    return "\n".join(lines)


def build_summary_rows(
    paired_rows: list[dict[str, str]],
    authority_rows: list[dict[str, str]],
    pt_stats: dict[str, dict[str, float]],
) -> list[dict[str, object]]:
    authority_by_scenario = {
        row["scenario"]: row for row in authority_rows if row.get("mode") == "ua"
    }
    rows: list[dict[str, object]] = []
    for row in ordered(paired_rows):
        scenario = row["scenario"]
        authority = authority_by_scenario[scenario]
        rmse_delta = fval(row, "rmse_delta_pct")
        control_delta = fval(row, "control_rate_delta_pct")
        track_ratio = fval(authority, "track_ratio_mean")
        stats = pt_stats[scenario]
        item: dict[str, object] = {
            "scenario": scenario,
            "baseline_rmse_m": fval(row, "baseline_rmse_m"),
            "ua_rmse_m": fval(row, "ua_rmse_m"),
            "rmse_delta_pct": rmse_delta,
            "baseline_control_rate_rms": fval(row, "baseline_control_rate_rms"),
            "ua_control_rate_rms": fval(row, "ua_control_rate_rms"),
            "control_rate_delta_pct": control_delta,
            "ua_hold_ratio": fval(authority, "hold_ratio_mean"),
            "ua_search_ratio": fval(authority, "search_ratio_mean"),
            "ua_track_ratio": track_ratio,
            "p_track_sample_count": int(stats["count"]),
            "p_track_min": stats["min"],
            "p_track_q05": stats["q05"],
            "p_track_q50": stats["q50"],
            "p_track_q95": stats["q95"],
            "p_track_max": stats["max"],
        }
        item["claim_class"] = claim_class(
            scenario,
            rmse_delta,
            control_delta,
            track_ratio,
        )
        rows.append(item)
    return rows


def main() -> int:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    args.figure_output_dir.mkdir(parents=True, exist_ok=True)
    setup_style()

    paired_path = args.aggregate_dir / "r13_v2_paired_effects.csv"
    authority_path = args.bundle / "r13_v2_authority_policy_summary_by_scenario_mode.csv"
    paired_rows = read_csv_rows(paired_path)
    authority_rows = read_csv_rows(authority_path)
    pt_sample_path = args.p_track_csv if args.skip_mcap else (
        args.output_dir / "r13_v2_p_track_samples_ua.csv"
    )
    pt_samples = read_pt_samples(args.bundle, pt_sample_path, skip_mcap=args.skip_mcap)
    stats = p_track_stats(pt_samples)

    plot_rmse(paired_rows, args.figure_output_dir)
    plot_control_rate(paired_rows, args.figure_output_dir)
    plot_authority(authority_rows, args.figure_output_dir)
    plot_p_track(pt_samples, args.figure_output_dir)

    summary_rows = build_summary_rows(paired_rows, authority_rows, stats)
    write_csv_rows(args.output_dir / "r13_v2_claim_boundary_table.csv", summary_rows)
    (args.output_dir / "r13_v2_claim_boundary_table.md").write_text(
        render_markdown_table(summary_rows),
        encoding="utf-8",
    )
    (args.output_dir / "r13_v2_claim_boundary_table.tex").write_text(
        render_latex_table(summary_rows),
        encoding="utf-8",
    )

    global_summary = {
        "schema_version": "r13_v2_thesis_audit.v1",
        "inputs": {
            "paired_effects": str(paired_path.relative_to(PROJECT_ROOT)),
            "authority_summary": str(authority_path.relative_to(PROJECT_ROOT)),
            "bundle_results": str((args.bundle / "results.csv").relative_to(PROJECT_ROOT)),
            "sonar_quality_topic": SONAR_QUALITY_TOPIC,
        },
        "thresholds": {
            "track_enter_probability": 0.75,
            "search_enter_probability": 0.55,
        },
        "outputs": sorted(
            str(path.relative_to(PROJECT_ROOT))
            for path in args.output_dir.iterdir()
            if path.is_file()
        ),
        "global_mean": {
            "baseline_rmse_m": float(np.mean([row["baseline_rmse_m"] for row in summary_rows])),
            "ua_rmse_m": float(np.mean([row["ua_rmse_m"] for row in summary_rows])),
            "baseline_control_rate_rms": float(
                np.mean([row["baseline_control_rate_rms"] for row in summary_rows])
            ),
            "ua_control_rate_rms": float(
                np.mean([row["ua_control_rate_rms"] for row in summary_rows])
            ),
        },
        "claim_boundary": summary_rows,
    }
    (args.output_dir / "r13_v2_thesis_audit_manifest.json").write_text(
        json.dumps(global_summary, indent=2, ensure_ascii=False, allow_nan=False)
        + "\n",
        encoding="utf-8",
    )
    print(f"wrote R13-v2 audit figures and tables to {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

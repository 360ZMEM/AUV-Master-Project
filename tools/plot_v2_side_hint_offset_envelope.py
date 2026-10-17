#!/usr/bin/env python3
"""Show why the declared side interval needs half-maximum crossing reserve."""
from __future__ import annotations

import csv
import json
import math
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from thesis_plot_style import (BASELINE_2, PROPOSED, REFERENCE, WARNING,
                               apply_thesis_style, figure_size, save_figure)

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "AUV-Master-Mag/results/v2"
SWEEP = RESULTS / "inspection_side_hint_offset_sweep_20260926"
GATE = RESULTS / "inspection_side_hint_gate_20260926"
OUT = SWEEP


def load(folder: Path, truth_m: float) -> dict:
    name = "wire_seed_101"
    summary = json.loads((folder / f"{name}_summary.json").read_text())
    with (folder / f"{name}.csv").open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    errors = np.array([abs(float(row["y_m"]) - truth_m) for row in rows
                       if row["mode"] == "track" and float(row["x_m"]) >= 0.])
    return {
        "source": str(folder.relative_to(ROOT)),
        "truth_lateral_m": truth_m,
        "completed": bool(summary["completed"]),
        "duration_s": float(summary["duration_s"]),
        "hold_reason": summary["first_hold_reason"],
        "lateral_valid": bool(summary["lateral_valid"]),
        "depth_published": bool(summary["depth_published"]),
        "track_samples": int(len(errors)),
        "track_true_lateral_mae_m": float(np.mean(errors)) if len(errors) else None,
        "track_true_lateral_max_m": float(np.max(errors)) if len(errors) else None,
    }


def main() -> None:
    runs = {
        "+2": load(SWEEP / "south_plus2", 2.),
        "-2": load(SWEEP / "north_minus2", -2.),
        "+4": load(SWEEP / "south_plus4", 4.),
        "-4": load(SWEEP / "north_minus4", -4.),
        "+6": load(GATE / "final_code_south_plus6", 6.),
        "-6": load(GATE / "final_code_north_minus6", -6.),
        "+8": load(SWEEP / "final_south_plus8", 8.),
        "-8": load(SWEEP / "final_north_minus8", -8.),
        "+9": load(SWEEP / "south_plus9", 9.),
        "-9": load(SWEEP / "north_minus9", -9.),
        "+10": load(SWEEP / "south_plus10", 10.),
        "-10": load(SWEEP / "north_minus10", -10.),
    }
    refused_old = load(SWEEP / "old_interval_rejected", 10.)
    refused_unconfigured = load(SWEEP / "no_tail_budget_rejected", 6.)
    assert all(runs[f"{sign}{offset}"]["completed"] for sign in ("+", "-")
               for offset in (2, 4, 6, 8, 9))
    assert all(not runs[f"{sign}10"]["completed"] and
               runs[f"{sign}10"]["hold_reason"] == "flythrough_lateral_rejected"
               for sign in ("+", "-"))
    assert refused_old["hold_reason"] == "flythrough_side_hint_support_insufficient"
    assert refused_unconfigured["hold_reason"] == "flythrough_side_hint_support_unconfigured"
    assert all(not item["depth_published"] for item in runs.values())

    halfwidth = 3. * math.sqrt(3.)
    margin = 15. - 8. - halfwidth
    apply_thesis_style(base_font_size=9)
    fig, axes = plt.subplots(1, 2, figsize=figure_size(height=3.15), constrained_layout=True)

    ax = axes[0]
    lateral = np.linspace(0., 17., 650)
    for offset, color, label in ((8., PROPOSED, "+8 m：留有余量"),
                                 (9., BASELINE_2, "+9 m：余量很小"),
                                 (10., WARNING, "+10 m：交点在终点外")):
        envelope = 1. + 20. / np.sqrt(1. + ((lateral - offset) / 3.) ** 2)
        ax.plot(lateral, envelope, color=color, lw=1.2, label=label)
        ax.plot([offset + halfwidth], [11.], marker="o", color=color, markersize=3.5)
    ax.axvline(15., color=REFERENCE, ls="--", lw=.9, label="穿越终点 +15 m")
    ax.axhline(11., color="#888888", ls=":", lw=.8, label="背景修正半高")
    ax.set(xlim=(0., 17.), ylim=(0., 22.5), xlabel="相对先验横向位置 / m",
           ylabel="解析磁包络 / nT", title="(a) 端点与外侧半高交点的关系")
    ax.legend(fontsize=6.25, loc="upper left")
    ax.grid(color="#D0D0D0", lw=.45)
    ax.set_axisbelow(True)

    ax = axes[1]
    ax.axvspan(2., 8., color=PROPOSED, alpha=.10, label="收紧后声明幅值 2–8 m")
    for sign, marker, color, label in (("+", "o", PROPOSED, "南→北，正侧电缆"),
                                        ("-", "s", BASELINE_2, "北→南，负侧电缆")):
        for offset in (2, 4, 6, 8, 9, 10):
            value = runs[f"{sign}{offset}"]
            display_offset = offset + (.10 if sign == "+" else -.10)
            ax.scatter([display_offset], [1. if value["completed"] else 0.],
                       marker=marker if value["completed"] else "x",
                       s=32 if value["completed"] else 57,
                       color=color if value["completed"] else WARNING,
                       linewidth=1.25, zorder=3,
                       label=label if offset == 2 else None)
    ax.axvline(15. - halfwidth, color=REFERENCE, ls=":", lw=.9,
               label="解析交点极限约 9.80 m")
    ax.annotate("±10 m：横向证据拒绝", xy=(10., 0.), xytext=(5.3, .27),
                fontsize=6.6, color=WARNING,
                arrowprops={"arrowstyle": "->", "lw": .7, "color": WARNING})
    ax.set(xlim=(1.3, 10.7), ylim=(-.18, 1.25), xticks=(2, 4, 6, 8, 9, 10),
           yticks=(0, 1), yticklabels=("拒止", "完成"),
           xlabel="真实侧向偏差幅值 / m", title="(b) 原生 PVS 任务结果（种子 101）")
    ax.legend(fontsize=6.05, loc="lower left")
    ax.grid(axis="x", color="#D0D0D0", lw=.45)
    ax.set_axisbelow(True)

    OUT.mkdir(parents=True, exist_ok=True)
    save_figure(fig, OUT / "side_hint_offset_envelope")
    plt.close(fig)
    payload = {
        "scope": "synthetic single wire, ROS2/PID/guard/localhost UDP/native PVS; seed 101, zero current, prealigned straight prior",
        "field_model": "B(y)=1+20/sqrt(1+((y-offset)/3)^2) nT",
        "analytic_halfmaximum_distance_m": halfwidth,
        "nominal_positive_scan_end_m": 15.,
        "analytic_largest_positive_center_m": 15. - halfwidth,
        "declared_halfmaximum_tail_m": 7.,
        "remaining_margin_beyond_analytic_crossing_at_8m_m": margin,
        "runs": runs,
        "old_interval_preflight_refusal": refused_old,
        "unconfigured_tail_preflight_refusal": refused_unconfigured,
    }
    (OUT / "side_hint_offset_envelope_summary.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()

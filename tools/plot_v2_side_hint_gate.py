#!/usr/bin/env python3
"""Summarize the declared side-hint gate and matched-direction PVS runs."""
from __future__ import annotations

import csv
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from thesis_plot_style import (BASELINE_2, NEUTRAL, PROPOSED, REFERENCE, WARNING,
                               apply_thesis_style, figure_size, save_figure)

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "AUV-Master-Mag/results/v2"
GATE = RESULTS / "inspection_side_hint_gate_20260926"
ROBUST = RESULTS / "inspection_side_hint_robustness_20260926"


def run(folder: Path, seed: int, truth_m: float) -> dict:
    stem = f"wire_seed_{seed}"
    summary = json.loads((folder / f"{stem}_summary.json").read_text())
    with (folder / f"{stem}.csv").open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    errors = np.array([abs(float(row["y_m"]) - truth_m) for row in rows
                       if row["mode"] == "track" and float(row["x_m"]) >= 0.])
    return {
        "source": str(folder.relative_to(ROOT)),
        "seed": seed,
        "truth_lateral_m": truth_m,
        "completed": bool(summary["completed"]),
        "duration_s": float(summary["duration_s"]),
        "hold_reason": summary["first_hold_reason"],
        "depth_published": bool(summary["depth_published"]),
        "track_samples": int(len(errors)),
        "track_true_lateral_mae_m": float(np.mean(errors)) if len(errors) else None,
        "track_true_lateral_max_m": float(np.max(errors)) if len(errors) else None,
        "max_abs_rpm": max(abs(int(row["rpm"])) for row in rows),
        "max_abs_pid_thrust_percent": max(abs(float(row["thrust_percent"])) for row in rows),
    }


def main() -> None:
    matched = {
        "south_plus6_zero": [
            run(GATE / "final_code_south_plus6", 101, 6.),
            run(ROBUST / "south_plus6_seed102", 102, 6.),
            run(ROBUST / "south_plus6_seed103", 103, 6.),
        ],
        "north_minus6_zero": [
            run(GATE / "final_code_north_minus6", 101, -6.),
            run(ROBUST / "north_minus6_seed102", 102, -6.),
            run(ROBUST / "north_minus6_seed103", 103, -6.),
        ],
        "north_minus6_current_north": [run(ROBUST / "north_minus6_current_north", 101, -6.)],
        "north_minus6_current_south": [run(ROBUST / "north_minus6_current_south", 101, -6.)],
    }
    refused = {name: run(GATE / name, 101, 6. if name != "wrong_declared_side" else -6.)
               for name in ("missing", "invalid_type", "ambiguous", "mismatch", "outside", "wrong_declared_side")}
    wrong_side_repeats = [refused["wrong_declared_side"],
                          run(GATE / "wrong_declared_side_seed102", 102, -6.),
                          run(GATE / "wrong_declared_side_seed103", 103, -6.)]
    assert all(item["completed"] and not item["depth_published"]
               for group in matched.values() for item in group)
    assert all(not item["completed"] and not item["depth_published"] for item in refused.values())
    assert all(refused[name]["max_abs_rpm"] == 0 and refused[name]["max_abs_pid_thrust_percent"] == 0.
               for name in ("missing", "invalid_type", "ambiguous", "mismatch", "outside"))
    assert refused["wrong_declared_side"]["hold_reason"] == "flythrough_scan_timeout"
    assert all(not item["completed"] and item["hold_reason"] == "flythrough_scan_timeout"
               and not item["depth_published"] for item in wrong_side_repeats)

    apply_thesis_style(base_font_size=9)
    fig, axes = plt.subplots(1, 2, figsize=figure_size(height=3.35), constrained_layout=True)
    keys = list(matched)
    labels = ["南→北\n+6 m，零流", "北→南\n−6 m，零流",
              "北→南\n北流 0.05", "北→南\n南流 0.05"]
    colors = [PROPOSED, BASELINE_2, BASELINE_2, BASELINE_2]
    ax = axes[0]
    for i, key in enumerate(keys):
        items = matched[key]
        offsets = np.linspace(-.13, .13, len(items))
        for offset, item in zip(offsets, items):
            ax.scatter(i + offset, item["track_true_lateral_mae_m"], color=colors[i],
                       edgecolor="white", linewidth=.5, s=32, zorder=3)
        ax.text(i, max(item["track_true_lateral_mae_m"] for item in items) + .075,
                f"{len(items)}/{len(items)}", ha="center", fontsize=7, color=REFERENCE)
    ax.set(xticks=range(4), xticklabels=labels, ylim=(0, 1.5),
           ylabel="沿缆真实横偏 MAE / m", title="(a) 正确侧向配置下的完成样本")
    ax.grid(axis="y", color="#D0D0D0", lw=.5)
    ax.set_axisbelow(True)

    ax = axes[1]
    names = ["线索缺失", "区间类型错误", "区间跨线", "方向不符", "越过扫描端", "线索自洽但符号错误"]
    values = [refused[name]["duration_s"] for name in refused]
    yy = np.arange(len(names))
    ax.scatter(values[:5], yy[:5], marker="s", s=39, color=NEUTRAL, zorder=3,
               label="首周期零推力保持")
    ax.scatter(values[5], yy[5], marker="x", s=64, linewidth=1.8,
               color=WARNING, zorder=3, label="扫描超时保持")
    ax.set_xscale("log")
    ax.set(xlim=(.65, 900), ylim=(5.5, -.5), yticks=yy, yticklabels=names,
           xlabel="触发保持的任务时间 / s（对数轴）",
           title="(b) 配置门与错误线索的不同拒止时点")
    ax.grid(axis="x", color="#D0D0D0", lw=.5)
    ax.set_axisbelow(True)
    ax.legend(fontsize=6.2, loc="lower center")
    ax.annotate("不能由声明区间验证真值", xy=(values[5], 5), xytext=(5.5, 4.35),
                fontsize=6.3, color=WARNING,
                arrowprops={"arrowstyle": "->", "color": WARNING, "lw": .7})

    GATE.mkdir(parents=True, exist_ok=True)
    save_figure(fig, GATE / "side_hint_gate_and_envelope")
    plt.close(fig)
    payload = {
        "scope": "synthetic single wire, actual ROS2/PID/guard/localhost UDP/native PVS; no physical PC104; all runs use a prealigned straight corridor",
        "measurement": "true lateral MAE over every TRACK row with x>=0; each point is one seed, not a confidence interval",
        "matched": matched,
        "refused": refused,
        "wrong_declared_side_seeds": wrong_side_repeats,
    }
    (GATE / "side_hint_gate_and_envelope_summary.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()

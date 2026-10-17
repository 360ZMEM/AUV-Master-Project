#!/usr/bin/env python3
"""Explain the summit-splitting correction and the tested current/offset corners."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.ndimage import median_filter
from scipy.signal import find_peaks

from thesis_plot_style import PROPOSED, REFERENCE, WARNING, apply_thesis_style, figure_size, save_figure


ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "AUV-Master-Mag/results/v2/inspection_side_hint_corner_current_20260926"
OUT = RUNS / "current_offset_peak_gate"


def load(name: str, truth: float) -> dict:
    path = RUNS / name / "wire_seed_101_summary.json"
    summary = json.loads(path.read_text())
    with path.with_name("wire_seed_101.csv").open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    errors = [abs(float(row["y_m"]) - truth) for row in rows
              if row["mode"] == "track" and float(row["x_m"]) >= 0.]
    holds = [row for row in rows if row["mode"] == "hold"]
    return {
        "source": str(path.relative_to(ROOT)),
        "completed": bool(summary["completed"]),
        "duration_s": float(summary["duration_s"]),
        "hold_reason": summary["first_hold_reason"],
        "lateral_reason_codes": summary.get("last_lateral_reason_codes", []),
        "depth_published": bool(summary["depth_published"]),
        "track_true_lateral_mae_m": float(np.mean(errors)) if errors else None,
        "track_true_lateral_max_m": float(np.max(errors)) if errors else None,
        "track_samples": len(errors),
        "hold_samples": len(holds),
        "hold_zero_thrust_and_rpm": bool(holds) and all(
            float(row["thrust_percent"]) == 0. and int(row["rpm"]) == 0 for row in holds),
    }


def main() -> None:
    names = {
        (-8, "north"): ("north_minus8_current_north", "final_gate_minus8_current_north"),
        (-8, "south"): ("north_minus8_current_south", "final_gate_minus8_current_south"),
        (-2, "north"): ("north_minus2_current_north", "final_gate_minus2_current_north"),
        (-2, "south"): ("north_minus2_current_south", "final_gate_minus2_current_south"),
        (+2, "north"): ("south_plus2_current_north", "final_gate_plus2_current_north"),
        (+2, "south"): ("south_plus2_current_south", "final_gate_plus2_current_south"),
        (+8, "north"): ("south_plus8_current_north", "final_gate_plus8_current_north"),
        (+8, "south"): ("south_plus8_current_south", "final_gate_plus8_current_south"),
    }
    cases = {f"{offset:+d}_{current}": {
        "original": load(original, offset), "revised": load(revised, offset),
    } for (offset, current), (original, revised) in names.items()}
    assert all(case["revised"]["completed"] for case in cases.values())
    assert all(not case["revised"]["depth_published"] for case in cases.values())
    assert sum(not case["original"]["completed"] for case in cases.values()) == 4
    near = [cases[f"{offset:+d}_{current}"]["revised"]
            for offset in (-2, 2) for current in ("south", "north")]
    assert all(case["track_true_lateral_mae_m"] > 1. for case in near)
    assert sum(case["track_true_lateral_max_m"] > 2. for case in near) == 2
    wrong_side = load("wrong_sign_after_timeout", -6.)
    assert not wrong_side["completed"]
    assert wrong_side["lateral_reason_codes"] == ["side_hint_observation_inconsistent"]
    assert not wrong_side["depth_published"]
    assert wrong_side["hold_zero_thrust_and_rpm"]

    # The smoke CSV records positions but not the injected field. Regenerate
    # its deterministic input exactly from the archived path and seed 101.
    csv_path = RUNS / "bounded_plus8_current_north/wire_seed_101.csv"
    with csv_path.open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    y = np.asarray([float(row["y_m"]) for row in rows])
    rng = np.random.default_rng(101)
    field = 1. + 20. / np.sqrt(1. + ((y - 8.) / 3.) ** 2) + rng.normal(0., .03, len(y))
    order = np.argsort(y)
    sorted_y, smooth = y[order], median_filter(field[order], size=5)
    peak_indices, _ = find_peaks(smooth, prominence=4.)
    near_peak = [idx for idx in peak_indices if abs(sorted_y[idx] - 8.) < .3]
    assert len(near_peak) == 2
    first, second = near_peak
    saddle_nt = float(min(smooth[first], smooth[second]) - np.min(smooth[first:second + 1]))
    separation_m = float(sorted_y[second] - sorted_y[first])
    assert separation_m < .1 and saddle_nt < .01

    apply_thesis_style(base_font_size=9)
    fig, axes = plt.subplots(1, 2, figsize=figure_size(height=3.15), constrained_layout=True)
    ax = axes[0]
    window = (sorted_y >= 7.80) & (sorted_y <= 8.20)
    ax.plot(sorted_y[window], smooth[window], color=PROPOSED, lw=1.3, label="5 点中值后的单导线峰顶")
    ax.scatter(sorted_y[near_peak], smooth[near_peak], color=WARNING, s=20, zorder=3, label="旧判别器的两个峰")
    ax.annotate(f"间距 {separation_m:.3f} m\n鞍点仅 {saddle_nt:.4f} nT",
                xy=(sorted_y[first], smooth[first]), xytext=(7.81, 20.995),
                fontsize=6.9, color=WARNING,
                arrowprops={"arrowstyle": "->", "lw": .7, "color": WARNING})
    ax.set(xlim=(7.79, 8.21), ylim=(20.97, 21.04), xlabel="真实侧向坐标 / m",
           ylabel="磁包络 / nT", title="(a) 峰顶噪声造成的假双峰")
    ax.legend(loc="lower right", fontsize=6.3)
    ax.grid(color="#D0D0D0", lw=.45)

    ax = axes[1]
    offsets = [-8, -2, 2, 8]
    for row, offset in enumerate(offsets):
        for col, current in enumerate(("south", "north")):
            case = cases[f"{offset:+d}_{current}"]
            ax.add_patch(plt.Rectangle((col - .46, row - .42), .92, .84,
                                       facecolor=PROPOSED, alpha=.18, edgecolor=PROPOSED, lw=.6))
            ax.text(col, row + .04, "到终点", ha="center", va="center", fontsize=8, color=PROPOSED)
            if not case["original"]["completed"]:
                ax.text(col + .30, row - .22, "×", ha="center", va="center", fontsize=11,
                        fontweight="bold", color=WARNING)
    ax.set(xlim=(-.58, 1.58), ylim=(3.55, -.55), xticks=(0, 1),
           xticklabels=("南向 0.05 m/s", "北向 0.05 m/s"),
           yticks=range(4), yticklabels=[f"{offset:+d} m" for offset in offsets],
           xlabel="横流方向", ylabel="真实侧向偏差", title="(b) 修正后八组均到终点（种子 101）")
    ax.text(.5, -.48, "红 ×：原配置拒止；全组埋深未发布", ha="center",
            va="top", fontsize=6.5, color=REFERENCE)
    ax.tick_params(length=0)
    for spine in ax.spines.values():
        spine.set_visible(False)

    OUT.mkdir(parents=True, exist_ok=True)
    save_figure(fig, OUT / "current_offset_peak_gate")
    plt.close(fig)
    files = [Path(__file__), ROOT / "AUV-Master-Mag/src/auv_mag_tracking/v2/lateral.py",
             ROOT / "AUV-Master-Mag/src/auv_mag_tracking/v2/flythrough.py",
             ROOT / "brain_linux/src/auv_cable_tracking_v2/config/cable_tracking_v2_flythrough.yaml",
             ROOT / "brain_linux/src/auv_cable_tracking_v2/config/cable_tracking_v2_flythrough_north_start.yaml"]
    payload = {
        "scope": "synthetic single wire; ROS2/PID/guard/localhost UDP/native PVS; prealigned straight prior; seed 101; current magnitude 0.05 m/s",
        "profile_reconstruction": "archived y path, B=1+20/sqrt(1+((y-8)/3)^2)+N(0,0.03) nT, numpy default_rng(101)",
        "false_peak_separation_m": separation_m,
        "false_peak_saddle_nt": saddle_nt,
        "revised_parameter_changes": {"maximum_scan_duration_s": 600., "endpoint_tolerance_m": 2.},
        "revision_sha256": {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in files},
        "cases": cases,
        "wrong_side_refusal_after_longer_scan": wrong_side,
    }
    (OUT / "current_offset_peak_gate_summary.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Diagnostic figure for synthetic cross-current report bias in shallow survey."""
from __future__ import annotations

import csv
import hashlib
import json
import math
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from thesis_plot_style import (BASELINE_1, PROPOSED, REFERENCE, WARNING,
                               apply_thesis_style, figure_size, save_figure)


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "AUV-Master-Mag/results/v2/shallow_survey_current_bias_20260927"
CASES = (
    ("报告无偏", BASE / "zero_bias", BASELINE_1),
    ("低报 0.005 m/s", BASE, PROPOSED),
    ("低报 0.020 m/s", BASE / "underreport_020", WARNING),
)
PUB = ROOT / "AUV-Master-Mag/docs/v2/publication/fwhm_v2_experiment_results"
THESIS = ROOT / "docs/thesis/figures/experiments/fwhm_v2"
STEM = "53_shallow_survey_current_report_bias"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_case(directory: Path) -> tuple[dict, list[dict], Path, Path]:
    summary_path = directory / "wire_positive_seed101_summary.json"
    trajectory_path = directory / "wire_positive_seed101.csv"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert sha(trajectory_path) == summary["trajectory_sha256"]
    with trajectory_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == summary["ticks"]
    assert summary["current_y_mps"] == summary["true_plant_current_y_mps"] == .04
    assert summary["fault_injection"] == "decision_current_report_bias_y_mps"
    assert "synthetic_current_and_sonar" in summary["evidence_level"]
    assert not summary["guard_connected"] and not summary["burial_depth_published"]
    assert all(row["depth_valid"] == "False" for row in rows)
    hold = [row for row in rows if row["phase"] == "hold"]
    assert len(hold) == summary["hold_zero_ticks"]
    assert all(float(row["command_speed_mps"]) == 0.
               and float(row["thrust_percent"]) == 0.
               and float(row["udp_rpm"]) == 0. for row in hold)
    return summary, rows, summary_path, trajectory_path


def main() -> None:
    records = [(label, color, *read_case(directory))
               for label, directory, color in CASES]
    provenance = records[0][2]["source_sha256_at_start"]
    wrapper_sha = records[0][2]["fault_injection_source_sha256_at_start"]
    assert all(item[2]["source_sha256_at_start"] == provenance
               and item[2]["fault_injection_source_sha256_at_start"] == wrapper_sha
               for item in records)
    assert all(sha(ROOT / path) == digest for path, digest in provenance.items())
    assert wrapper_sha == sha(ROOT / "tools/probe_v2_shallow_survey_current_bias.py")
    assert [item[2]["terminal_reason"] for item in records] == [
        "complete", "complete", "survey_rejoin_length_exhausted"]

    apply_thesis_style(base_font_size=9)
    fig, axes = plt.subplots(3, 1, figsize=figure_size(height=7.0),
                             constrained_layout=True)
    bars = np.arange(3)
    reports = [item[2]["reported_current_y_mps"] for item in records]
    axes[0].bar(bars, reports, width=.55,
                color=[item[1] for item in records], alpha=.8)
    axes[0].errorbar(bars, reports, yerr=.008, fmt="none", color="black",
                     capsize=3, lw=.9, label="消息声明的 ±2σ")
    axes[0].axhline(.04, color=REFERENCE, ls="--", lw=1., label="PVS 真横流 0.040 m/s")
    axes[0].set(xticks=bars, xticklabels=[item[0] for item in records],
                ylim=(0., .052), ylabel="横流 / (m/s)",
                title="(a) 仅改变决策输入，PVS 中的横流保持不变")
    axes[0].legend(loc="upper right", fontsize=7)

    metrics = []
    for label, color, summary, rows, summary_path, trajectory_path in records:
        survey = [row for row in rows if row["phase"] == "survey"]
        rejoin = [row for row in rows if row["phase"] == "rejoin"]
        t_survey = np.array([float(row["time_s"]) for row in survey])
        ref = np.array([abs(float(row["y_m"]) - float(row["survey_reference_y_m"]))
                        for row in survey])
        axes[1].plot(t_survey[::12], ref[::12], color=color, lw=1., label=label)

        t_rejoin = np.array([float(row["time_s"]) - float(rejoin[0]["time_s"])
                             for row in rejoin])
        truth_error = np.array([
            abs((float(row["y_m"]) - float(row["target_y_m"]))
                / math.sqrt(1. + .02**2)) for row in rejoin])
        axes[2].plot(t_rejoin[::6], truth_error[::6], color=color, lw=1.1,
                     label=label + ("：Hold" if summary["terminal_mode"] == "hold"
                                    else "：进入 Track"))
        axes[2].plot(t_rejoin[-1], truth_error[-1], "o", color=color, ms=3.)
        metrics.append({
            "label": label,
            "reported_current_y_mps": summary["reported_current_y_mps"],
            "true_current_y_mps": summary["true_plant_current_y_mps"],
            "reported_sigma_mps": .004,
            "maximum_survey_reference_deviation_m": float(ref.max()),
            "rejoin_duration_s": float(t_rejoin[-1]),
            "last_rejoin_truth_cross_track_m": float(truth_error[-1]),
            "terminal_reason": summary["terminal_reason"],
            "track_truth_lateral_mae_m": summary["track_truth_lateral_mae_m"],
            "hold_zero_ticks": summary["hold_zero_ticks"],
            "hold_all_zero_commands": True,
            "hold_to_final_displacement_m": summary["hold_to_final_displacement_m"],
            "summary_sha256": sha(summary_path),
            "trajectory_sha256": sha(trajectory_path),
        })
    axes[1].axhline(3., color=REFERENCE, ls="--", lw=.8,
                    label="候选扫描参考偏差上限 3 m")
    axes[1].set(xlim=(0, 1370), ylim=(0, 3.2), xlabel="任务仿真时间 / s",
                ylabel="扫描参考偏差 / m",
                title="(b) 报告横流偏小会增加扫描参考偏差")
    axes[1].legend(loc="upper left", fontsize=7)
    axes[2].set(xlim=(0, 410), ylim=(0, 12), xlabel="接入开始后仿真时间 / s",
                ylabel="合成真值横偏 / m",
                title="(c) 严重低报耗尽接入长度，任务保持而不误报完成")
    axes[2].legend(loc="upper right", fontsize=7)

    figure_paths = [*save_figure(fig, PUB / "figures" / STEM),
                    *save_figure(fig, THESIS / STEM)]
    plt.close(fig)
    payload = {
        "evidence_level": "same_source_synthetic_ros_pid_native_pvs_fault_injection_no_guard_no_pc104",
        "truth_current_y_mps": .04,
        "reported_sigma_mps": .004,
        "field_release_authorized": False,
        "cases": metrics,
        "runner_source_sha256_at_start": provenance,
        "fault_injection_source_sha256_at_start": wrapper_sha,
        "figure_sha256": {str(path.relative_to(ROOT)): sha(path) for path in figure_paths},
        "plot_source_sha256": sha(Path(__file__)),
    }
    output = PUB / "data" / (STEM + "_manifest.json")
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Figure 52: accelerated PVS Hold-clock correction and uncommanded drift."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from thesis_plot_style import (BASELINE_1, PROPOSED, REFERENCE, WARNING,
                               apply_thesis_style, figure_size, save_figure)


ROOT = Path(__file__).resolve().parents[1]
OLD = ROOT / "AUV-Master-Mag/results/v2/shallow_survey_ros_pvs_long_hold_20260927/identity_dropout_positive_seed101"
NEW = ROOT / "AUV-Master-Mag/results/v2/shallow_survey_ros_pvs_clock_aligned_20260927/bridge/identity_dropout_positive_seed101"
PUB = ROOT / "AUV-Master-Mag/docs/v2/publication/fwhm_v2_experiment_results"
THESIS = ROOT / "docs/thesis/figures/experiments/fwhm_v2"
STEM = "52_shallow_survey_hold_clock_and_drift"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(base: Path) -> tuple[dict, list[dict]]:
    summary_path = base.with_name(base.name + "_summary.json")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    trajectory = base.with_suffix(".csv")
    assert summary["trajectory_sha256"] == sha(trajectory)
    with trajectory.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == summary["ticks"]
    assert summary["terminal_reason"] == "survey_identity_lost"
    assert summary["guard_connected"] and not summary["burial_depth_published"]
    assert summary["hold_zero_ticks"] == 1201
    hold = [row for row in rows if row["mode"] == "hold"]
    assert len(hold) == 1201
    assert all(float(row["command_speed_mps"]) == 0.
               and float(row["thrust_percent"]) == 0.
               and float(row["udp_rpm"]) == 0. for row in hold)
    return summary, hold


def series(rows: list[dict]) -> tuple[np.ndarray, np.ndarray, np.ndarray, float]:
    origin = np.array([float(rows[0]["x_m"]), float(rows[0]["y_m"])])
    elapsed = np.array([float(row["time_s"]) - float(rows[0]["time_s"])
                        for row in rows])
    xy = np.array([[float(row["x_m"]), float(row["y_m"])] for row in rows])
    drift = np.linalg.norm(xy - origin, axis=1)
    recovery = np.array([row["route_budget_state"] == "RECOVERY_REQUIRED"
                         for row in rows], dtype=float)
    first_recovery_s = float(elapsed[np.flatnonzero(recovery)[0]])
    return elapsed, drift, recovery, first_recovery_s


def main() -> None:
    old_summary, old_rows = read(OLD)
    new_summary, new_rows = read(NEW)
    old_t, old_drift, old_recovery, old_alarm = series(old_rows)
    new_t, new_drift, new_recovery, new_alarm = series(new_rows)
    assert old_alarm > 100. and abs(new_alarm - 30.) <= .25
    assert abs(old_t[-1] - 300.) < 1e-6 and abs(new_t[-1] - 300.) < 1e-6
    assert old_summary["source_sha256_at_start"]["brain_linux/src/auv_cable_tracking_v2/auv_cable_tracking_v2/cable_tracking_v2_node.py"] != new_summary["source_sha256_at_start"]["brain_linux/src/auv_cable_tracking_v2/auv_cable_tracking_v2/cable_tracking_v2_node.py"]
    assert all(sha(ROOT / path) == digest
               for path, digest in new_summary["source_sha256_at_start"].items())

    apply_thesis_style(base_font_size=9)
    fig, axes = plt.subplots(2, 1, figsize=figure_size(height=5.1),
                             constrained_layout=True, sharex=True)
    axes[0].step(old_t, old_recovery, where="post", color=BASELINE_1,
                 lw=1.3, label=f"修复前：{old_alarm:.0f} s 才升级")
    axes[0].step(new_t, new_recovery, where="post", color=PROPOSED,
                 lw=1.5, label=f"双时基：{new_alarm:.0f} s 升级")
    axes[0].axvline(30., color=REFERENCE, lw=.8, ls="--", label="声明的 30 s Hold 上限")
    axes[0].set(ylabel="请求上级处置", ylim=(-.08, 1.18),
                yticks=(0, 1), yticklabels=("否", "是"),
                title="(a) 加速 PVS 中的 Hold 计时")
    axes[0].legend(loc="center right", fontsize=7)

    axes[1].plot(old_t, old_drift, color=BASELINE_1, lw=1., ls="--",
                 label="修复前 PVS 滑行")
    axes[1].plot(new_t, new_drift, color=PROPOSED, lw=1.3,
                 label="双时基 PVS 滑行")
    axes[1].axvline(30., color=REFERENCE, lw=.8, ls="--")
    axes[1].plot(new_t[-1], new_drift[-1], "o", color=WARNING, ms=3.)
    axes[1].set(xlim=(0, 300), xlabel="首次 Hold 后仿真时间 / s",
                ylabel="相对 Hold 起点位移 / m",
                title="(b) 零主推后仍有流漂；本地夹具未模拟上级恢复动作")
    axes[1].legend(loc="upper left", fontsize=7)

    figure_paths = [*save_figure(fig, PUB / "figures" / STEM),
                    *save_figure(fig, THESIS / STEM)]
    plt.close(fig)
    payload = {
        "evidence_level": "same_synthetic_ros_pid_guard_udp_native_pvs_case_across_two_source_versions",
        "old_alarm_sim_elapsed_s": old_alarm,
        "new_alarm_sim_elapsed_s": new_alarm,
        "hold_duration_sim_s": 300.,
        "hold_ticks_each": 1201,
        "old_drift_300s_m": float(old_drift[-1]),
        "new_drift_300s_m": float(new_drift[-1]),
        "zero_command_all_hold_ticks": True,
        "field_release_authorized": False,
        "physical_recovery_simulated": False,
        "cases": {"before": old_summary, "after": new_summary},
        "raw_sha256": {
            "before_summary": sha(OLD.with_name(OLD.name + "_summary.json")),
            "before_trajectory": sha(OLD.with_suffix(".csv")),
            "after_summary": sha(NEW.with_name(NEW.name + "_summary.json")),
            "after_trajectory": sha(NEW.with_suffix(".csv")),
        },
        "figure_sha256": {str(path.relative_to(ROOT)): sha(path) for path in figure_paths},
        "plot_source_sha256": sha(Path(__file__)),
    }
    path = PUB / "data" / (STEM + "_manifest.json")
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(path)


if __name__ == "__main__":
    main()

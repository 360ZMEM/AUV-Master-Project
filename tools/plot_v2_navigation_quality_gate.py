#!/usr/bin/env python3
"""Plot navigation-error attribution and measured route-quality refusal."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from thesis_plot_style import BASELINE_2, PROPOSED, REFERENCE, WARNING, apply_thesis_style, figure_size, save_figure


ROOT = Path(__file__).resolve().parents[1]
OLD = ROOT / "AUV-Master-Mag/results/v2/inspection_nav_error_20260926"
NEW = ROOT / "AUV-Master-Mag/results/v2/inspection_route_quality_gate_20260926"
OUT = NEW / "publication"


def load(folder: Path) -> tuple[dict, list[dict]]:
    summary_path = folder / "wire_seed_101_summary.json"
    summary = json.loads(summary_path.read_text())
    csv_path = folder / "wire_seed_101.csv"
    with csv_path.open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    summary["source_path"] = str(summary_path.relative_to(ROOT))
    summary["csv_sha256"] = hashlib.sha256(csv_path.read_bytes()).hexdigest()
    return summary, rows


def track_errors(rows: list[dict], truth_m: float) -> tuple[np.ndarray, np.ndarray]:
    selected = [row for row in rows if row["mode"] == "track" and float(row["x_m"]) >= 0.]
    return (np.asarray([float(row["x_m"]) for row in selected]),
            np.asarray([float(row["y_m"]) - truth_m for row in selected]))


def main() -> None:
    old_stop, old_stop_rows = load(OLD / "plus2_north_pos")
    direct, direct_rows = load(OLD / "world_plus2_north_posonly")
    good, good_rows = load(NEW / "expected_accept_speed_bias_001")
    refused, refused_rows = load(NEW / "expected_reject_speed_bias_002")
    assert old_stop["first_hold_reason"] == "flythrough_current_exceeds_envelope"
    assert direct["completed"] and good["completed"] and good["route_quality_valid"]
    assert not refused["completed"] and refused["first_hold_reason"] == "flythrough_route_quality_rejected"
    assert refused_rows[-1]["rpm"] == "0" and not refused["depth_published"]

    cases = {}
    for offset in (-8, -2, 2, 8):
        for current in ("south", "north"):
            name = f"{'minus' if offset < 0 else 'plus'}{abs(offset)}_{current}"
            folder = (NEW / "expected_accept_speed_bias_001" if (offset, current) == (2, "north")
                      else NEW / f"final_seed101_{name}")
            summary, rows = load(folder)
            x, signed = track_errors(rows, offset)
            cases[f"{offset:+d}_{current}"] = {
                "source_path": summary["source_path"],
                "csv_sha256": summary["csv_sha256"],
                "completed": bool(summary["completed"]),
                "hold_reason": summary["first_hold_reason"],
                "route_quality_valid": summary["route_quality_valid"],
                "depth_published": bool(summary["depth_published"]),
                "runin_m": summary["rejoin_runin_selected_m"],
                "true_mae_m": float(np.mean(abs(signed))) if len(x) else None,
                "true_max_m": float(np.max(abs(signed))) if len(x) else None,
                "observed_mae_m": summary["route_observed_lateral_mae_m"],
                "observed_max_m": summary["route_observed_lateral_max_m"],
            }
            assert cases[f"{offset:+d}_{current}"]["completed"]
            assert cases[f"{offset:+d}_{current}"]["route_quality_valid"]
            assert not cases[f"{offset:+d}_{current}"]["depth_published"]
            assert cases[f"{offset:+d}_{current}"]["true_mae_m"] < 1.
            assert cases[f"{offset:+d}_{current}"]["true_max_m"] < 2.

    apply_thesis_style(base_font_size=8.5)
    fig, axes = plt.subplots(2, 2, figsize=figure_size(height=5.2), constrained_layout=True)
    ax = axes[0, 0]
    for rows, color, label in ((direct_rows, PROPOSED, "世界系地速：完成"),
                               (old_stop_rows, BASELINE_2, "位置差分：误停")):
        ax.plot([float(row["time_s"]) for row in rows],
                [float(row["x_m"]) for row in rows], color=color,
                lw=1.6 if rows is old_stop_rows else 1.1, label=label, zorder=3 if rows is old_stop_rows else 2)
    stopped_at = old_stop_rows[-1]
    ax.scatter([float(stopped_at["time_s"])], [float(stopped_at["x_m"])],
               marker="x", s=28, color=WARNING, zorder=4)
    ax.annotate("37.75 s 误停", xy=(float(stopped_at["time_s"]), float(stopped_at["x_m"])),
                xytext=(145., -224.), fontsize=6.5,
                arrowprops={"arrowstyle": "->", "color": WARNING, "lw": .7})
    ax.axhline(80., color=REFERENCE, ls="--", lw=.8, label="路由终点")
    ax.set(xlim=(0., 1150.), ylim=(-260., 100.), xlabel="任务时间 / s",
           ylabel="沿先验方向位置 / m", title="(a) 0.05 m 定位噪声的差分放大")
    ax.legend(loc="lower right", fontsize=6)
    ax.grid(color="#D0D0D0", lw=.45)

    ax = axes[0, 1]
    x = np.arange(2)
    observed_mean = [good["route_observed_lateral_mae_m"], refused["route_observed_lateral_mae_m"]]
    observed_max = [good["route_observed_lateral_max_m"], refused["route_observed_lateral_max_m"]]
    ax.bar(x - .18, observed_mean, .35, color=PROPOSED, label="观测均值")
    ax.bar(x + .18, observed_max, .35, color=WARNING, label="观测最大值")
    ax.axhline(1., color=REFERENCE, ls="--", lw=.75, label="均值门 1 m")
    ax.axhline(2., color=REFERENCE, ls=":", lw=.75, label="最大值门 2 m")
    ax.set(xticks=x, xticklabels=["速度偏差 0.01 m/s", "速度偏差 0.02 m/s"],
           ylim=(0., 2.55), ylabel="观测横偏 / m",
           title="(b) 同为 1° 航向偏差时的任务验收判据")
    ax.legend(fontsize=5.8, ncol=2, loc="upper left")
    ax.grid(axis="y", color="#D0D0D0", lw=.45)

    ax = axes[1, 0]
    ax.axhspan(-1., 1., color=PROPOSED, alpha=.08, label="±1 m 参考带")
    for rows, color, label in ((good_rows, PROPOSED, "有效：0.01 m/s"),
                               (refused_rows, WARNING, "拒绝：0.02 m/s")):
        xx, signed = track_errors(rows, 2.)
        ax.plot(xx, signed, color=color, lw=1.05, label=label)
    ax.axhline(0., color=REFERENCE, lw=.7)
    ax.set(xlim=(0., 82.), ylim=(-2.6, 2.6), xlabel="正向巡检进度 / m",
           ylabel="真实横偏（仅评价）/ m", title="(c) 完整沿缆轨迹与拒绝原因")
    ax.legend(loc="lower right", fontsize=6)
    ax.grid(color="#D0D0D0", lw=.45)

    ax = axes[1, 1]
    order = [f"{offset:+d}_{current}" for offset in (-8, -2, 2, 8)
             for current in ("south", "north")]
    labels = [f"{offset:+d}{'南' if current == 'south' else '北'}"
              for offset in (-8, -2, 2, 8) for current in ("south", "north")]
    yy = [cases[name]["true_mae_m"] for name in order]
    ax.bar(np.arange(8), yy, color=PROPOSED, alpha=.9)
    ax.axhline(1., color=WARNING, ls="--", lw=.8, label="示例均值门 1 m")
    ax.set(xticks=np.arange(8), xticklabels=labels, ylim=(0., 1.12),
           ylabel="沿缆真值 MAE / m", title="(d) 组合导航误差下的八个离散角点")
    ax.legend(fontsize=6, loc="upper right")
    ax.grid(axis="y", color="#D0D0D0", lw=.45)
    for ax in axes.flat:
        ax.set_axisbelow(True)
    OUT.mkdir(parents=True, exist_ok=True)
    save_figure(fig, OUT / "navigation_quality_gate")
    plt.close(fig)

    source_hashes = {}
    for path in (Path(__file__), ROOT / "AUV-Master-Mag/src/auv_mag_tracking/v2/flythrough.py",
                 ROOT / "brain_linux/src/auv_cable_tracking_v2/auv_cable_tracking_v2/cable_tracking_v2_node.py",
                 ROOT / "brain_linux/src/auv_cable_tracking_v2/config/cable_tracking_v2_flythrough.yaml"):
        source_hashes[str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
    payload = {
        "scope": "single synthetic wire, seed101, ROS2/PID/guard/localhost UDP/native PVS; 0.05m/s current; not field validation",
        "navigation_perturbation": {"position_noise_std_m": .05, "heading_bias_deg": 1.,
                                    "world_ground_velocity_bias_mps": .01},
        "misleading_speed_bias_case_mps": .02,
        "source_sha256": source_hashes,
        "position_difference_false_hold": {key: old_stop[key] for key in ("source_path", "csv_sha256", "first_hold_reason", "duration_s")},
        "world_velocity_position_noise_completed": {key: direct[key] for key in ("source_path", "csv_sha256", "completed", "duration_s")},
        "quality_pass": {key: good[key] for key in ("source_path", "csv_sha256", "completed", "route_quality_valid", "route_observed_lateral_mae_m", "route_observed_lateral_max_m")},
        "quality_refusal": {key: refused[key] for key in ("source_path", "csv_sha256", "completed", "first_hold_reason", "route_observed_lateral_mae_m", "route_observed_lateral_max_m")},
        "cases": cases,
    }
    (OUT / "navigation_quality_gate_summary.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()

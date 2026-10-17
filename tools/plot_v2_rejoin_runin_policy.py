#!/usr/bin/env python3
"""Current-conditioned route run-in: path, error, and eight-corner evidence."""
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
OLD = ROOT / "AUV-Master-Mag/results/v2/inspection_side_hint_corner_current_20260926"
NEW = ROOT / "AUV-Master-Mag/results/v2/inspection_rejoin_runin_20260926"
OUT = NEW / "adaptive_rejoin_publication"


def load(folder: Path, truth: float) -> dict:
    summary_path = folder / "wire_seed_101_summary.json"
    summary = json.loads(summary_path.read_text())
    with (folder / "wire_seed_101.csv").open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    track = [row for row in rows if row["mode"] == "track" and float(row["x_m"]) >= 0.]
    x = np.asarray([float(row["x_m"]) for row in track])
    y = np.asarray([float(row["y_m"]) for row in track])
    signed = y - truth
    rejoin = sum(row["stage"] == "rejoin_estimated_cable" for row in track)
    return {
        "summary_source": str(summary_path.relative_to(ROOT)),
        "completed": bool(summary["completed"]),
        "hold_reason": summary["first_hold_reason"],
        "depth_published": bool(summary["depth_published"]),
        "duration_s": float(summary["duration_s"]),
        "selected_runin_m": summary.get("rejoin_runin_selected_m"),
        "track_samples": len(track),
        "track_true_lateral_mae_m": float(np.mean(abs(signed))) if len(track) else None,
        "track_true_lateral_max_m": float(np.max(abs(signed))) if len(track) else None,
        "route_rejoin_fraction": rejoin / len(track) if track else None,
        "x_m": x,
        "y_m": y,
        "signed_error_m": signed,
        "rows": rows,
    }


def main() -> None:
    cases: dict[str, dict] = {}
    for offset in (-8, -2, 2, 8):
        sign = "minus" if offset < 0 else "plus"
        for current, old_current in (("south", "south"), ("north", "north")):
            old_name = f"final_gate_{sign}{abs(offset)}_current_{old_current}"
            new_name = f"adaptive_{sign}{abs(offset)}_{current}"
            name = f"{offset:+d}_{current}"
            cases[name] = {
                "baseline": load(OLD / old_name, offset),
                "adaptive": load(NEW / new_name, offset),
            }
            expected_runin = 20. if ((offset > 0 and current == "north") or
                                      (offset < 0 and current == "south")) else 5.
            after = cases[name]["adaptive"]
            assert after["completed"] and not after["depth_published"]
            assert after["selected_runin_m"] == expected_runin
            assert after["track_true_lateral_mae_m"] < 1.0
            assert after["track_true_lateral_max_m"] < 2.0

    key = "+2_north"
    old, new = cases[key]["baseline"], cases[key]["adaptive"]
    apply_thesis_style(base_font_size=8.5)
    fig, axes = plt.subplots(2, 2, figsize=figure_size(height=5.1), constrained_layout=True)
    ax = axes[0, 0]
    for item, color, label in ((old, BASELINE_2, "原路径：直返起点"),
                               (new, PROPOSED, "新路径：20 m 上游接入")):
        track = [row for row in item["rows"] if row["mode"] == "track" and float(row["x_m"]) <= 22.]
        ax.plot([float(row["x_m"]) for row in track],
                [float(row["y_m"]) for row in track], color=color, lw=1.1, label=label)
    ax.plot([-80., 22.], [2., 2.], color=REFERENCE, ls="--", lw=.8, label="真值电缆（仅评价）")
    ax.scatter([-20., 0.], [2., 2.], color=[PROPOSED, REFERENCE], s=14, zorder=3)
    ax.axvline(0., color=REFERENCE, ls=":", lw=.7)
    ax.set(xlim=(-83., 22.), ylim=(-2., 18.), xlabel="沿先验方向位置 / m",
           ylabel="侧向位置 / m", title="(a) 回归起点前的有界接入段")
    ax.legend(loc="upper right", fontsize=6)
    ax.grid(color="#D0D0D0", lw=.45)

    ax = axes[0, 1]
    ax.axhspan(-1., 1., color=PROPOSED, alpha=.08, label="±1 m 参考带")
    for item, color, label in ((old, BASELINE_2, "原路径"), (new, PROPOSED, "自适应接入")):
        ax.plot(item["x_m"], item["signed_error_m"], color=color, lw=1.05, label=label)
    ax.axhline(0., color=REFERENCE, lw=.7)
    ax.set(xlim=(0., 80.), ylim=(-2.8, 2.8), xlabel="正向巡检进度 / m",
           ylabel="真实横偏 / m", title="(b) +2 m、北向横流的完整沿缆误差")
    ax.legend(loc="upper right", fontsize=6)
    ax.grid(color="#D0D0D0", lw=.45)

    order = [f"{offset:+d}_{current}" for offset in (-8, -2, 2, 8)
             for current in ("south", "north")]
    labels = [f"{offset:+d}{'南' if current == 'south' else '北'}"
              for offset in (-8, -2, 2, 8) for current in ("south", "north")]
    xx = np.arange(len(order))
    old_mae = [cases[name]["baseline"]["track_true_lateral_mae_m"] for name in order]
    new_mae = [cases[name]["adaptive"]["track_true_lateral_mae_m"] for name in order]
    ax = axes[1, 0]
    ax.bar(xx - .18, old_mae, .35, color=BASELINE_2, alpha=.80, label="原路径")
    ax.bar(xx + .18, new_mae, .35, color=PROPOSED, alpha=.90, label="方向选择接入")
    ax.axhline(1., color=WARNING, ls="--", lw=.8, label="示例均值门 1 m")
    ax.set(xticks=xx, xticklabels=labels, ylim=(0., 1.55), ylabel="沿缆真值 MAE / m",
           title="(c) 八个离散侧偏／横流角点")
    ax.legend(fontsize=5.9, ncol=2, loc="upper center")
    ax.grid(axis="y", color="#D0D0D0", lw=.45)

    old_rejoin = [cases[name]["baseline"]["route_rejoin_fraction"] for name in order]
    new_rejoin = [cases[name]["adaptive"]["route_rejoin_fraction"] for name in order]
    ax = axes[1, 1]
    ax.bar(xx - .18, np.asarray(old_rejoin) * 100., .35, color=BASELINE_2, alpha=.80, label="原路径")
    ax.bar(xx + .18, np.asarray(new_rejoin) * 100., .35, color=PROPOSED, alpha=.90, label="方向选择接入")
    ax.set(xticks=xx, xticklabels=labels, ylim=(0., 105.), ylabel="沿缆段仍在重接入 / %",
           title="(d) 轨迹改善来自阶段切换更稳定")
    ax.grid(axis="y", color="#D0D0D0", lw=.45)
    for ax in axes.flat:
        ax.set_axisbelow(True)
    OUT.mkdir(parents=True, exist_ok=True)
    save_figure(fig, OUT / "current_conditioned_rejoin")
    plt.close(fig)

    source_hashes = {}
    for path in (Path(__file__), ROOT / "AUV-Master-Mag/src/auv_mag_tracking/v2/flythrough.py",
                 ROOT / "brain_linux/src/auv_cable_tracking_v2/config/cable_tracking_v2_flythrough.yaml",
                 ROOT / "brain_linux/src/auv_cable_tracking_v2/config/cable_tracking_v2_flythrough_north_start.yaml"):
        source_hashes[str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
    compact = {name: {phase: {key: value for key, value in data.items()
                              if key not in {"x_m", "y_m", "signed_error_m", "rows"}}
                      for phase, data in pair.items()} for name, pair in cases.items()}
    payload = {
        "scope": "ROS2/PID/guard/localhost UDP/native PVS; synthetic single wire; prealigned 390x60m corridor; seed101; current +/-0.05m/s",
        "admission_rule": "if estimated cross-current toward observed cable side >=0.02m/s choose 20m run-in, otherwise choose 5m; latch at first Track",
        "quality_reference": {"mean_route_offset_m": 1., "max_route_offset_m": 2.},
        "source_sha256": source_hashes,
        "cases": compact,
    }
    (OUT / "current_conditioned_rejoin_summary.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()

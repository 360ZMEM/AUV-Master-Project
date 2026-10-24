#!/usr/bin/env python3
"""Figure 51: multi-crossing ROS chain, target association, and Hold coast."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from thesis_plot_style import (BASELINE_1, BASELINE_2, PROPOSED,
                               REFERENCE, WARNING, apply_thesis_style,
                               figure_size, save_figure)


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "AUV-Master-Mag/results/v2/shallow_survey_ros_pvs_final_20260927"
PUB = ROOT / "AUV-Master-Mag/docs/v2/publication/fwhm_v2_experiment_results"
THESIS = ROOT / "docs/thesis/figures/experiments/fwhm_v2"
STEM = "51_shallow_survey_ros_pvs_chain"
FILES = {
    "positive": SOURCE / "bridge/wire_positive_seed101",
    "negative": SOURCE / "wire_negative_seed101",
    "fused": SOURCE / "fused_neighbor_positive_seed101",
    "dropout": SOURCE / "bridge/identity_dropout_positive_seed101",
    "no_source": SOURCE / "no_source_positive_seed101",
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(base: Path) -> tuple[dict, list[dict]]:
    summary_path = base.with_name(base.name + "_summary.json")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    with base.with_suffix(".csv").open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == summary["ticks"]
    return summary, rows


def col(rows: list[dict], name: str) -> np.ndarray:
    return np.array([float(row[name]) for row in rows])


def route(ax, rows: list[dict], title: str, *, color: str, xlim: tuple[int, int]) -> None:
    for phase, label, line_color, width in (
            ("survey", "多次横切", REFERENCE, .8),
            ("rejoin", "前向接入", BASELINE_1, 1.1),
            ("track", "80 m Track", color, 1.3)):
        part = [row for row in rows if row["phase"] == phase]
        if part:
            ax.plot(col(part, "x_m"), col(part, "y_m"),
                    color=line_color, lw=width, label=label)
    x = np.linspace(xlim[0], xlim[1], 200)
    ax.plot(x, 5.5 + .02 * x, color=REFERENCE, ls=":", lw=.9,
            label="合成目标线真值")
    ax.set(xlim=xlim, xlabel="沿先验位置 / m", ylabel="横向位置 / m", title=title)
    ax.legend(loc="upper center", bbox_to_anchor=(.5, -.30), ncol=2,
              fontsize=8.2, frameon=False, columnspacing=.8, handlelength=1.7)


def hold_coast(rows: list[dict]) -> tuple[np.ndarray, np.ndarray, int]:
    first = next(i for i, row in enumerate(rows) if row["mode"] == "hold")
    part = rows[first:]
    origin = np.array([float(rows[first]["x_m"]), float(rows[first]["y_m"])])
    xy = np.column_stack((col(part, "x_m"), col(part, "y_m")))
    return col(part, "time_s") - float(rows[first]["time_s"]), np.linalg.norm(xy - origin, axis=1), first


def main(*, allow_historical_source: bool = False,
         verify_only: bool = False) -> None:
    data = {name: load(path) for name, path in FILES.items()}
    assert data["positive"][0]["terminal_mode"] == "complete"
    assert data["negative"][0]["terminal_mode"] == "complete"
    assert data["positive"][0]["guard_connected"]
    assert data["dropout"][0]["guard_connected"]
    assert data["fused"][0]["terminal_reason"] == "survey_identity_rejected"
    assert data["fused"][0]["geometry_valid"]
    assert data["dropout"][0]["terminal_reason"] == "survey_identity_lost"
    assert data["no_source"][0]["terminal_reason"].startswith("survey_geometry_rejected")
    assert not data["no_source"][0]["geometry_valid"]
    assert all(not item[0]["burial_depth_published"] for item in data.values())
    shared_sources = [item[0]["source_sha256_at_start"] for item in data.values()]
    assert all(item["tools/smoke_v2_shallow_survey_ros_pvs.py"] ==
               shared_sources[0]["tools/smoke_v2_shallow_survey_ros_pvs.py"]
               for item in shared_sources)
    current_source_matches = all(
        sha(ROOT / path) == digest
        for item in shared_sources for path, digest in item.items())
    if not current_source_matches and not allow_historical_source:
        raise RuntimeError("figure 51 is a frozen source snapshot; pass --allow-historical-source to render archived CSV")
    for name, (summary, _) in data.items():
        assert sha(FILES[name].with_suffix(".csv")) == summary["trajectory_sha256"]
    for name in ("fused", "dropout"):
        summary, rows = data[name]
        assert summary["hold_zero_ticks"] == 61
        assert all(float(row["udp_rpm"]) == 0. and float(row["thrust_percent"]) == 0.
                   and float(row["command_speed_mps"]) == 0.
                   for row in rows if row["mode"] == "hold")

    if verify_only:
        print("figure 51 archived data verified; current source matches:", current_source_matches)
        return

    apply_thesis_style(base_font_size=10)
    fig, axes = plt.subplots(2, 2, figsize=figure_size(height=5.8), constrained_layout=True)
    route(axes[0, 0], data["positive"][1],
          "(a) 正向横流：三段\n含 ROS 守卫与 UDP", color=PROPOSED, xlim=(-5, 550))
    route(axes[0, 1], data["negative"][1],
          "(b) 反向横流：四段\nROS/PID/协议", color=BASELINE_2, xlim=(-5, 690))
    for name, label, color in (("positive", "正向三段＋守卫", PROPOSED),
                               ("negative", "反向四段", BASELINE_2)):
        part = [row for row in data[name][1] if row["phase"] == "track"]
        axes[1, 0].plot(col(part, "x_m") - float(part[0]["x_m"]),
                        np.abs(col(part, "y_m") - col(part, "target_y_m")),
                        color=color, lw=1., label=label)
    axes[1, 0].axhline(1., color=REFERENCE, ls="--", lw=.8, label="1 m 诊断线")
    axes[1, 0].set(xlim=(0, 80), ylim=(0, 1.6),
                   xlabel="进入 Track 后沿线距离 / m", ylabel="对目标真值横偏 / m",
                   title="(c) 完整 Track 横偏")
    axes[1, 0].legend(loc="upper right", fontsize=8.2)

    ax = axes[1, 1]
    for name, label, color in (("fused", "融合邻源：身份冲突", WARNING),
                               ("dropout", "线索失鲜：Track 中 Hold", BASELINE_1)):
        t, distance, _ = hold_coast(data[name][1])
        ax.plot(t, distance, color=color, lw=1.2, label=label)
        ax.plot(t[-1], distance[-1], "o", ms=2.5, color=color)
    ax.set(xlim=(0, 15), ylim=(0, 3.5), xlabel="首次 Hold 后时间 / s",
           ylabel="原生 PVS 滑行距离 / m", title="(d) 三层零命令后的滑行")
    ax.legend(loc="upper left", fontsize=8.2)

    pub = save_figure(fig, PUB / "figures" / STEM)
    thesis = save_figure(fig, THESIS / STEM)
    plt.close(fig)
    data_hashes = {name: {
        "summary_sha256": sha(path.with_name(path.name + "_summary.json")),
        "trajectory_sha256": sha(path.with_suffix(".csv")),
    } for name, path in FILES.items()}
    summary = {
        "evidence_level": "mixed_ros_pid_protocol_native_pvs_and_ros_pid_guard_udp_native_pvs",
        "guard_connected_cases": ["positive", "dropout"],
        "guard_not_connected_cases": ["negative", "fused", "no_source"],
        "synthetic_identity_and_current_fixture": True,
        "pc104_or_field_connected": False,
        "field_release_authorized": False,
        "current_source_matches_run_snapshot": current_source_matches,
        "cases": {name: item[0] for name, item in data.items()},
        "raw_hashes": data_hashes,
        "figure_paths": [str(path.relative_to(ROOT)) for path in (*pub, *thesis)],
        "figure_sha256": {str(path.relative_to(ROOT)): sha(path) for path in (*pub, *thesis)},
        "source_sha256": {str(path.relative_to(ROOT)): sha(path) for path in (
            Path(__file__).resolve(),
            ROOT / "tools/smoke_v2_shallow_survey_ros_pvs.py",
            ROOT / "AUV-Master-Mag/src/auv_mag_tracking/v2/shallow_survey.py",
            ROOT / "brain_linux/src/auv_cable_tracking_v2/auv_cable_tracking_v2/cable_tracking_v2_node.py",
            ROOT / "brain_linux/src/auv_cable_tracking_v2/auv_cable_tracking_v2/hold_budget.py",
        )},
    }
    target = PUB / "data" / (STEM + "_manifest.json")
    target.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(target)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--allow-historical-source", action="store_true")
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    main(allow_historical_source=args.allow_historical_source,
         verify_only=args.verify_only)

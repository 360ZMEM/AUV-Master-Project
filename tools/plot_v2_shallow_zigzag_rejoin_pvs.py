#!/usr/bin/env python3
"""Figure 50: PVS survey, qualified rejoin, and 80 m tracking with fail gates."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
import numpy as np

from thesis_plot_style import (BASELINE_1, BASELINE_2, GRID_COLOR, PROPOSED,
                               REFERENCE, WARNING, apply_thesis_style,
                               figure_size, save_figure)


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "AUV-Master-Mag/results/v2/shallow_zigzag_rejoin_pvs_20260927"
PUB = ROOT / "AUV-Master-Mag/docs/v2/publication/fwhm_v2_experiment_results"
THESIS = ROOT / "docs/thesis/figures/experiments/fwhm_v2"
STEM = "50_shallow_zigzag_pvs_rejoin_track"
NAMES = ("positive_three_wire", "negative_four_wire", "negative_four_intermediate",
         "negative_three_bad_exit", "negative_four_no_source", "negative_four_transient",
         "negative_four_separated", "negative_four_fused", "negative_four_no_identity")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(name: str) -> tuple[dict, list[dict]]:
    folder = SOURCE / name
    summary = json.loads((folder / "summary.json").read_text(encoding="utf-8"))
    csv_path = folder / "trajectory.csv"
    if sha(csv_path) != summary["trajectory_sha256"]:
        raise ValueError("trajectory hash mismatch: " + name)
    with csv_path.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    return summary, rows


def col(rows: list[dict], key: str) -> np.ndarray:
    return np.array([float(row[key]) for row in rows])


def draw_path(ax, rows: list[dict], label: str, survey_end_x: float, track_color: str) -> None:
    for phase, color, width, legend in (
            ("survey", REFERENCE, .8, "扫描"),
            ("rejoin", BASELINE_1, 1.1, "前向接入"),
            ("track", track_color, 1.3, "80 m 跟踪")):
        section = [row for row in rows if row["phase"] == phase]
        if section:
            ax.plot(col(section, "x_m"), col(section, "y_m"),
                    color=color, lw=width, label=legend)
    x = np.linspace(0, max(col(rows, "x_m")) + 2, 100)
    ax.plot(x, 6. + .02*x, color=REFERENCE, ls=":", lw=1., label="目标线真值")
    ax.axvline(survey_end_x, color=GRID_COLOR, lw=.8, ls="--")
    ax.set(xlabel="沿先验位置 / m", ylabel="横向位置 / m", title=label)
    ax.legend(loc="lower right", fontsize=5.7)


def main() -> None:
    data = {name: load(name) for name in NAMES}
    source = data[NAMES[0]][0]["source_sha256"]
    assert all(item[0]["source_sha256"] == source for item in data.values())
    assert all(sha(ROOT / path) == digest for path, digest in source.items())
    outcomes = {
        "positive_three_wire": "track_complete",
        "negative_four_wire": "track_complete",
        "negative_four_intermediate": "track_complete",
        "negative_three_bad_exit": "rejoin_length_exhausted",
        "negative_four_no_source": "survey_geometry_rejected",
        "negative_four_transient": "survey_geometry_rejected",
        "negative_four_separated": "survey_geometry_rejected",
        "negative_four_fused": "survey_identity_rejected",
        "negative_four_no_identity": "survey_identity_unavailable",
    }
    assert all(data[name][0]["terminal_phase"] == expected for name, expected in outcomes.items())
    assert all(data[name][0]["burial_depth_m"] is None for name in NAMES)
    assert all(data[name][0]["track_truth_lateral_mae_m"] < .4
               and data[name][0]["track_sample_count"] > 1000 for name in NAMES[:3])
    repeat = {}
    for name in ("positive_three_wire", "negative_four_wire", "negative_four_fused"):
        samples = []
        for seed in (102, 103):
            folder = SOURCE / "repeat_seeds" / f"{name}_seed{seed}"
            item = json.loads((folder / "summary.json").read_text(encoding="utf-8"))
            assert sha(folder / "trajectory.csv") == item["trajectory_sha256"]
            assert item["source_sha256"] == source
            expected = "survey_identity_rejected" if name == "negative_four_fused" else "track_complete"
            assert item["terminal_phase"] == expected
            samples.append(item)
        repeat[name] = samples

    apply_thesis_style(base_font_size=8)
    fig, axes = plt.subplots(2, 2, figsize=figure_size(height=5.5), constrained_layout=True)
    draw_path(axes[0, 0], data["positive_three_wire"][1],
              "(a) 正向流：三段扫描→接入→跟踪", 405., PROPOSED)
    axes[0, 0].set(xlim=(-5, 565), ylim=(-29, 30))
    draw_path(axes[0, 1], data["negative_four_wire"][1],
              "(b) 反向流：四段扫描→接入→跟踪", 540., BASELINE_2)
    axes[0, 1].set(xlim=(-5, 705), ylim=(-31, 32))

    ax = axes[1, 0]
    for name, label, color in (("positive_three_wire", "正向流三段", PROPOSED),
                               ("negative_four_wire", "反向流四段", BASELINE_2),
                               ("negative_four_intermediate", "中间场形四段", BASELINE_1)):
        rows = [row for row in data[name][1] if row["phase"] == "track"]
        distance = col(rows, "x_m") - float(rows[0]["x_m"])
        error = np.abs(col(rows, "y_m") - col(rows, "target_cable_y_m"))
        ax.plot(distance, error, color=color, lw=1., label=label)
    ax.axhline(1., ls="--", color=REFERENCE, lw=.8, label="1 m 诊断线")
    ax.set(xlim=(0, 80), ylim=(0, 1.6), xlabel="进入 Track 后沿线距离 / m",
           ylabel="对目标真值横偏 / m", title="(c) 全部 Track 样本的横偏")
    ax.legend(loc="upper right", fontsize=6.)

    ax = axes[1, 1]
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    ax.set_title("(d) 几何、身份与接入的分层决策", loc="left", pad=7)
    ax.text(.02, .94, "案例", weight="bold", va="center")
    ax.text(.54, .94, "停止／完成层", weight="bold", va="center")
    ax.text(.86, .94, "Track", weight="bold", va="center")
    labels = ("正向流三段单源", "反向流四段单源", "中间场形四段",
              "反向流三段错出口", "无源", "单站暂态", "可分邻源",
              "1 m 融合邻源", "无身份线索")
    stages = ("完成", "完成", "完成", "接入门", "几何门", "几何门", "几何门",
              "身份门", "身份门")
    for index, (name, label, stage) in enumerate(zip(NAMES, labels, stages)):
        y = .85 - index * .085
        accepted = data[name][0]["terminal_phase"] == "track_complete"
        ax.axhline(y + .043, xmin=.02, xmax=.98, color=GRID_COLOR, lw=.45)
        ax.text(.02, y, label, fontsize=6.5, va="center")
        ax.text(.54, y, stage, fontsize=6.6, va="center",
                color=PROPOSED if accepted else WARNING)
        ax.add_patch(Rectangle((.82, y - .027), .15, .054,
                               facecolor=PROPOSED if accepted else WARNING,
                               edgecolor="none"))
        ax.text(.895, y, "完成" if accepted else "拒绝", va="center", ha="center",
                color="white", fontsize=6.2)
    ax.text(.02, .035, "身份输入：合成独立区间；埋深：全部为空", fontsize=6.2,
            color=WARNING, va="center")

    pub_paths = save_figure(fig, PUB / "figures" / STEM)
    thesis_paths = save_figure(fig, THESIS / STEM)
    plt.close(fig)
    concise = {name: {key: item[0][key] for key in
                      ("terminal_phase", "elapsed_s", "geometry_valid",
                       "geometry_reason_codes", "identity_residual_at_admission_m",
                       "track_start_x_m", "track_sample_count",
                       "track_truth_lateral_mae_m", "track_truth_lateral_max_m",
                       "burial_depth_m", "trajectory_sha256")}
               for name, item in data.items()}
    summary = {"evidence_level": "native_pvs_protocol_synthetic_identity_survey_rejoin_track",
               "identity_source": "synthetic_truth_line_fixture_separate_from_magnetic_fit_not_physical_sonar",
               "ros_or_pc104_or_field_acceptance": False,
               "field_release_authorized": False,
               "cases": concise, "source_sha256": source,
               "raw_summary_sha256": {name: sha(SOURCE / name / "summary.json")
                                      for name in NAMES},
               "repeat_seeds_102_103": {name: [{
                   "seed": item["seed"], "terminal_phase": item["terminal_phase"],
                   "identity_residual_at_admission_m": item["identity_residual_at_admission_m"],
                   "track_truth_lateral_mae_m": item["track_truth_lateral_mae_m"],
                   "track_truth_lateral_max_m": item["track_truth_lateral_max_m"],
                   "trajectory_sha256": item["trajectory_sha256"],
                   "summary_sha256": sha(SOURCE / "repeat_seeds" / f"{name}_seed{item['seed']}" / "summary.json"),
               } for item in items] for name, items in repeat.items()}}
    summary_path = PUB / "data" / f"{STEM}_summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest = {"summary_sha256": sha(summary_path),
                "figure_sha256": {str(path.relative_to(ROOT)): sha(path)
                                  for path in (*pub_paths, *thesis_paths)},
                "plot_script_sha256": sha(Path(__file__).resolve())}
    (PUB / "data" / f"{STEM}_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"summary": str(summary_path), "case_count": len(NAMES)}))


if __name__ == "__main__":
    main()

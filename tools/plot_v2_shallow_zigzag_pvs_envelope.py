#!/usr/bin/env python3
"""Figure 47: native-PVS shallow-zigzag with a declared 3 m track envelope."""

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
SOURCE = ROOT / "AUV-Master-Mag/results/v2/shallow_zigzag_pvs_envelope_3m_20260927"
PUB = ROOT / "AUV-Master-Mag/docs/v2/publication/fwhm_v2_experiment_results"
THESIS = ROOT / "docs/thesis/figures/experiments/fwhm_v2"
STEM = "47_shallow_zigzag_pvs_envelope_3m"
NAMES = ("zero_wire", "positive_current", "negative_wrong_side", "negative_mirrored",
         "intermediate_shape", "no_source", "transient_middle",
         "separated_neighbor", "fused_neighbor")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(name: str) -> tuple[dict, list[dict]]:
    folder = SOURCE / name
    summary_path = folder / "summary.json"
    csv_path = folder / "trajectory.csv"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    if sha(csv_path) != summary["trajectory_sha256"]:
        raise ValueError(f"trajectory hash mismatch: {name}")
    with csv_path.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    return summary, rows


def col(rows: list[dict], key: str) -> np.ndarray:
    return np.array([float(row[key]) for row in rows])


def main() -> None:
    data = {name: load(name) for name in NAMES}
    code_hashes = [item[0]["source_sha256"] for item in data.values()]
    assert all(item == code_hashes[0] for item in code_hashes), "mixed source versions"
    assert all(sha(ROOT / path) == digest for path, digest in code_hashes[0].items()), \
        "current source differs from the probe source"
    assert all(item[0]["burial_depth_m"] is None for item in data.values())
    assert all(item[0]["amplitude_m"] == 24.0
               and item[0]["half_wavelength_m"] == 135.0
               and item[0]["navigation_lateral_margin_m"] == 3.0
               for item in data.values()), "mixed survey envelopes"
    assert data["zero_wire"][0]["geometry_valid"]
    assert data["positive_current"][0]["geometry_valid"]
    assert data["negative_wrong_side"][0]["terminal_phase"] == "boundary_margin_exhausted"
    assert not data["negative_wrong_side"][0]["geometry_valid"]
    assert data["negative_mirrored"][0]["geometry_valid"]
    assert data["intermediate_shape"][0]["geometry_valid"]
    assert all(not data[name][0]["geometry_valid"] for name in
               ("no_source", "transient_middle", "separated_neighbor"))
    assert data["fused_neighbor"][0]["geometry_valid"]
    assert data["fused_neighbor"][0]["center_mae_m"] > .4
    assert all(data[name][0]["reference_track_max_m"] <= 3.0 for name in
               ("zero_wire", "positive_current", "negative_mirrored"))

    length = data["zero_wire"][0]["survey_length_m"]
    halfwave = data["zero_wire"][0]["half_wavelength_m"]
    amplitude = data["zero_wire"][0]["amplitude_m"]
    margin = data["zero_wire"][0]["navigation_lateral_margin_m"]
    boundary_halfwidth = amplitude + 18.0

    apply_thesis_style(base_font_size=8)
    fig, axes = plt.subplots(2, 2, figsize=figure_size(height=5.5),
                             constrained_layout=True)
    ax = axes[0, 0]
    reference = data["zero_wire"][1]
    ax.plot(col(reference, "x_m"), col(reference, "reference_y_m"),
            color=REFERENCE, ls="--", lw=1., label="浅角参考线")
    for name, label, color in (("zero_wire", "零流", PROPOSED),
                               ("positive_current", "+0.05 m/s：负侧起步", BASELINE_2),
                               ("negative_mirrored", "−0.05 m/s：正侧起步", BASELINE_1),
                               ("negative_wrong_side", "−0.05 m/s：错侧", WARNING)):
        rows = data[name][1]
        ax.plot(col(rows, "x_m"), col(rows, "y_m"), color=color,
                lw=1.05, label=label)
    x = np.linspace(0, length, 100)
    ax.plot(x, 6. + .02 * x, color=REFERENCE, ls=":", lw=.9, label="目标线真值")
    ax.axhline(-boundary_halfwidth + 5., color=WARNING, ls=":", lw=.7)
    ax.axhline(boundary_halfwidth - 5., color=WARNING, ls=":", lw=.7)
    ax.set(xlim=(-5, length + 5), ylim=(-boundary_halfwidth - 2, boundary_halfwidth + 2),
           xlabel="沿先验位置 / m", ylabel="横向位置 / m",
           title="(a) 流向选边使连续横切留在走廊内")
    ax.legend(loc="upper right", fontsize=5.5)

    ax = axes[0, 1]
    for name, label, color in (("zero_wire", "零流", PROPOSED),
                               ("positive_current", "顺向选边", BASELINE_2),
                               ("negative_mirrored", "反向选边", BASELINE_1),
                               ("negative_wrong_side", "错侧起步", WARNING)):
        rows = data[name][1]
        ax.plot(col(rows, "x_m"), np.abs(col(rows, "y_m") - col(rows, "reference_y_m")),
                color=color, lw=1., label=label)
    ax.axhline(margin, color=REFERENCE, ls="--", lw=.8, label="声明的 3 m 余量")
    ax.set(xlim=(0, length), ylim=(0, 32), xlabel="沿先验位置 / m",
           ylabel="对参考轨迹横偏 / m", title="(b) 错侧起步导致误差增长与边界拒止")
    ax.legend(loc="upper left", fontsize=6)

    ax = axes[1, 0]
    for idx, color in enumerate((PROPOSED, BASELINE_2, BASELINE_1)):
        rows = [row for index, row in enumerate(reference)
                if index % 4 == 0 and 0 <= float(row["x_m"]) <= length
                and min(int(float(row["x_m"]) // halfwave), 2) == idx]
        ax.plot(col(rows, "y_m"), col(rows, "magnetic_envelope_nt"),
                color=color, lw=1., label=f"第 {idx + 1} 次实际横切")
    ax.set(xlim=(-amplitude - 1, amplitude + 1), xlabel="实际横切位置 / m", ylabel="磁包络 / nT",
           title="(c) 原生动力学航迹采得完整空间剖面")
    ax.legend(loc="upper left", fontsize=6.5)

    ax = axes[1, 1]
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    ax.set_title("(d) 几何可用性与目标身份分级", loc="left", pad=7)
    ax.text(.02, .94, "情形", weight="bold", va="center")
    ax.text(.43, .94, "航迹", weight="bold", va="center")
    ax.text(.62, .94, "测线", weight="bold", va="center")
    ax.text(.80, .94, "中心误差", weight="bold", va="center")
    labels = {"zero_wire": "零流单源", "positive_current": "正向流选边",
              "negative_wrong_side": "反向流错侧", "negative_mirrored": "反向流选边",
              "intermediate_shape": "中间场形", "no_source": "无磁源",
              "transient_middle": "单站暂态", "separated_neighbor": "可分邻源",
              "fused_neighbor": "近距融合邻源"}
    for idx, name in enumerate(NAMES):
        summary = data[name][0]
        y = .85 - idx * .085
        ax.axhline(y + .043, xmin=.02, xmax=.98, color=GRID_COLOR, lw=.45)
        ax.text(.02, y, labels[name], fontsize=6.7, va="center")
        finished = summary["terminal_phase"] == "survey_path_end"
        for x0, accepted, text_value in ((.43, finished, "到端" if finished else "越界"),
                                         (.62, summary["geometry_valid"],
                                          "有效" if summary["geometry_valid"] else "拒绝")):
            color = PROPOSED if accepted else WARNING
            ax.add_patch(Rectangle((x0, y - .027), .14, .054,
                                   facecolor=color, edgecolor="none"))
            ax.text(x0 + .07, y, text_value, ha="center", va="center",
                    fontsize=6.2, color="white")
        error = summary["center_mae_m"]
        ax.text(.80, y, "—" if error is None else f"{error:.3f} m",
                fontsize=6.5, va="center",
                color=WARNING if name == "fused_neighbor" else REFERENCE)
    ax.text(.02, .035, "目标身份：全部未授权；埋深：全部为空", fontsize=6.4,
            color=WARNING, va="center")
    pub_paths = save_figure(fig, PUB / "figures" / STEM)
    thesis_paths = save_figure(fig, THESIS / STEM)
    plt.close(fig)

    concise = {name: {key: summary[key] for key in
                      ("terminal_phase", "elapsed_s", "reference_track_mae_m",
                       "reference_track_max_m", "geometry_valid", "geometry_reason_codes",
                       "center_mae_m", "burial_depth_m", "trajectory_sha256")}
               for name, (summary, _) in data.items()}
    publication_summary = {"evidence_level": "native_pvs_local_protocol_geometry_probe",
                           "target_identity_verified": False,
                           "field_release_authorized": False,
                           "cases": concise,
                           "source_sha256": code_hashes[0],
                           "raw_summary_sha256": {name: sha(SOURCE / name / "summary.json")
                                                  for name in NAMES}}
    summary_path = PUB / "data/47_shallow_zigzag_pvs_envelope_3m_summary.json"
    summary_path.write_text(json.dumps(publication_summary, ensure_ascii=False, indent=2) + "\n",
                            encoding="utf-8")
    manifest = {"summary_sha256": sha(summary_path),
                "figure_sha256": {str(path.relative_to(ROOT)): sha(path)
                                  for path in (*pub_paths, *thesis_paths)},
                "plot_script_sha256": sha(Path(__file__).resolve())}
    (PUB / "data/47_shallow_zigzag_pvs_envelope_3m_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"summary": str(summary_path), "case_count": len(NAMES)},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()

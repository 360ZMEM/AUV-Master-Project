#!/usr/bin/env python3
"""Render the cross-shape FWHM audit in the thesis figure style."""

from __future__ import annotations

import csv
import json
from pathlib import Path
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import thesis_plot_style as style  # noqa: E402

MAG = ROOT / "AUV-Master-Mag"
OUT = MAG / "docs/v2/figures"


def main() -> None:
    summary = json.loads((MAG / "results/v2/cross_shape_identifiability/summary.json").read_text(encoding="utf-8"))
    cases = summary["cases"]["6.0"]
    style.apply_thesis_style()
    fig, axes = plt.subplots(1, 2, figsize=style.figure_size(height=3.2), constrained_layout=True)

    shape_names = ("power_0.7", "power_0.9", "power_1.0", "double_0.5")
    labels = ("幂律 0.7", "幂律 0.9", "偶极 1.0", "近距双线")
    locations = np.arange(len(shape_names))
    baseline = [cases[key]["static"]["published_mae_m"] or 0.0 for key in shape_names]
    adaptive = [cases[key]["adaptive"]["published_mae_m"] or 0.0 for key in shape_names]
    axes[0].bar(locations - 0.18, baseline, 0.35, label="固定偶极系数", **style.series_style(1))
    axes[0].bar(locations + 0.18, adaptive, 0.35, label="连续幂律拟合", **style.series_style(0))
    axes[0].set_xticks(locations, labels)
    axes[0].tick_params(axis="x", labelrotation=18)
    axes[0].set_ylabel("已发布垂距 MAE / m")
    axes[0].set_title("(a) 跨场形误差与拒绝")
    axes[0].set_ylim(0, 1.06)
    axes[0].annotate("固定模型拒绝", (3 - 0.18, 0.04), xytext=(2.08, 0.53),
                     arrowprops={"arrowstyle": "->", "color": style.REFERENCE}, fontsize=8)
    axes[0].legend(loc="upper right", fontsize=8)

    with (MAG / "results/v2/fwhm_model_consistency/model_consistency.csv").open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    models = (
        ("legacy_segment_formula", "有限线段近似"),
        ("physical_single_wire", "单直导线"),
        ("thesis_dipole_envelope", "偶极包络"),
    )
    for index, (model, label) in enumerate(models):
        group = sorted((row for row in rows if row["model"] == model),
                       key=lambda row: float(row["vertical_separation_m"]))
        z = np.asarray([float(row["vertical_separation_m"]) for row in group])
        factor = np.asarray([float(row["implied_shape_factor"]) for row in group])
        axes[1].plot(z, factor, label=label, **style.line_style(index))
    axes[1].set_xlabel("传感器—导线垂距 / m")
    axes[1].set_ylabel("真实系数  z / FWHM")
    axes[1].set_ylim(0.25, 0.53)
    axes[1].set_title("(b) 相似形状不保证固定系数")
    axes[1].legend(loc="lower right", fontsize=8)

    OUT.mkdir(parents=True, exist_ok=True)
    style.save_figure(fig, OUT / "14_cross_shape_identifiability")
    plt.close(fig)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Render the acoustic-magnetic cable perception pipeline method figure.

This figure is redrawn in the main-repo convention (DLIA / ES-EKF / deployment
facade), replacing the sub-repo `fig_perception_pipeline` schematic. It shows how
raw tri-axial magnetic samples become cross-track / burial observables, how the
sonar provides sparse geometric anchors, and how the two-level estimation
(vehicle-level ES-EKF + cable-geometry-level online correction) consumes them.

Output:
  docs/thesis/figures/architecture/cable_acoustic_magnetic_perception_pipeline.{png,pdf}
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import thesis_plot_style as tps  # noqa: E402

OUT_DIR = ROOT / "docs/thesis/figures/architecture"


def _setup_font() -> None:
    tps.apply_thesis_style(layout="full")


# low-saturation palette matching the draw.io architecture diagrams
FILL = {
    "sample": ("#EAF2F8", "#8AA9C4"),
    "dlia": ("#EAF6F5", "#80B4AF"),
    "geom": ("#FFF7E8", "#D8B46A"),
    "sonar": ("#EAF2F8", "#8AA9C4"),
    "fuse": ("#FFF7E8", "#D8B46A"),
    "out": ("#EEF6EF", "#8DBA98"),
    "consumer": ("#F6F7F8", "#9AA7B2"),
}


def _box(ax, xy, w, h, text, key, fontsize=10, bold=False):
    fill, edge = FILL[key]
    patch = FancyBboxPatch(
        (xy[0], xy[1]), w, h,
        boxstyle="round,pad=0.02,rounding_size=0.06",
        linewidth=1.6, edgecolor=edge, facecolor=fill, zorder=2,
    )
    ax.add_patch(patch)
    text_artist = ax.text(
        xy[0] + w / 2, xy[1] + h / 2, text,
        ha="center", va="center", fontsize=fontsize,
        color="#26323D", zorder=3,
        fontweight="bold" if bold else "normal",
    )
    text_artist._figure_node_patch = patch
    return (xy[0] + w / 2, xy[1] + h / 2, w, h)


def _arrow(ax, p0, p1, dashed=False, color="#5F7690"):
    style = "-" if not dashed else (0, (5, 3))
    arr = FancyArrowPatch(
        p0, p1, arrowstyle="-|>", mutation_scale=13,
        linewidth=1.8, color=color, zorder=1, linestyle=style,
        shrinkA=2, shrinkB=2,
    )
    ax.add_patch(arr)


def render() -> None:
    _setup_font()
    fig, ax = plt.subplots(figsize=tps.figure_size("full", height=6.1))
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    ax.axis("off")

    # (a) Magnetic acquisition and geometric observations.
    ax.text(2, 96.5, "(a) 磁采集到几何观测", ha="left", va="center",
            fontsize=10.5, fontweight="bold", color="#26323D")
    _box(ax, (2, 72), 21, 17, "TMR8637 / SK2301\n三轴采样与标定\n去趋势 · 窗函数", "sample", 8.5)
    _box(ax, (27, 72), 21, 17, "数字锁相（DLIA）\n45/50 Hz I/Q\n幅相 · 信噪比", "dlia", 8.5)
    _box(ax, (52, 72), 21, 17, "旋转不变模量\n峰值 · FWHM\n过线周期", "geom", 8.5)
    _box(ax, (77, 72), 21, 17, "几何观测与质量\n横偏 · 垂直距离\n埋深 · 质量分", "geom", 8.5)
    for x0, x1 in [(23, 27), (48, 52), (73, 77)]:
        _arrow(ax, (x0, 80.5), (x1, 80.5))
    ax.text(
        2,
        66.5,
        "采样率与特征步进由采集配置给出；正文实验示例为 2000 Hz 原始采样、10 Hz 特征步进。",
        ha="left",
        va="center",
        fontsize=8.2,
        color="#52616B",
    )

    ax.plot([1, 99], [61, 61], color="#CDD5DC", linewidth=1.0)

    # (b) Vehicle state, acoustic/magnetic observations and cable output.
    ax.text(2, 57.5, "(b) 两级估计与巡缆输出", ha="left", va="center",
            fontsize=10.5, fontweight="bold", color="#26323D")
    _box(ax, (2, 42), 23, 11, "导航观测\nIMU · DVL · 深度", "sample", 8.6)
    _box(ax, (2, 26), 23, 11, "磁几何观测\n横偏 · 垂向距离\n质量分", "geom", 8.5)
    _box(ax, (2, 10), 23, 11, "声学锚点\n稀疏几何 · 方向消歧\n质量分", "sonar", 8.3)
    _box(ax, (32, 39), 27, 14, "融合定位（ES-EKF）\nAUV 位姿与协方差", "dlia", 9.2, bold=True)
    _box(ax, (32, 15), 27, 15, "电缆几何级在线修正\n先验地图 + 声磁观测\n横偏 / 走向 / 埋深", "fuse", 8.5, bold=True)
    _box(ax, (67, 24), 31, 16, "CableTrackingOutput\n横偏 · 路由进度\n垂距 / 埋深及不确定度\n置信度 · 就绪标志", "out", 8.2, bold=True)
    _box(ax, (67, 5), 31, 11, "行为树 / 状态机\n约束控制（UA-MPC）\n内层执行链", "consumer", 8.0)

    _arrow(ax, (25, 47.5), (32, 46))
    _arrow(ax, (45.5, 39), (45.5, 30), dashed=True, color="#7E6AA2")
    _arrow(ax, (25, 31.5), (32, 25))
    _arrow(ax, (25, 15.5), (32, 20))
    _arrow(ax, (59, 22.5), (67, 32))
    _arrow(ax, (82.5, 24), (82.5, 16))

    ax.text(47.5, 34.5, "位姿 / 协方差", ha="left", va="center",
            fontsize=8.0, color="#6B578D")
    ax.text(2, 3.5, "真值仅进入离线评价，不进入在线管线", ha="left", va="center",
            fontsize=8.2, color="#8A5A5A", style="italic")
    ax.text(2, 0.2, "埋深输出另受模型、高度参考与标定许可约束", ha="left", va="center",
            fontsize=8.0, color="#8A5A5A")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    tps.save_figure(
        fig,
        OUT_DIR / "cable_acoustic_magnetic_perception_pipeline",
    )
    plt.close(fig)
    print("wrote", OUT_DIR / "cable_acoustic_magnetic_perception_pipeline.{png,pdf}")


if __name__ == "__main__":
    render()

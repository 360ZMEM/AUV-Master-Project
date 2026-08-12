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

import os
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch


OUT_DIR = Path(__file__).resolve().parents[1] / "docs/thesis/figures/architecture"


def _setup_font() -> None:
    import matplotlib.font_manager as fm

    zh_font = "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"
    if os.path.exists(zh_font):
        fm.fontManager.addfont(zh_font)
        plt.rcParams["font.family"] = fm.FontProperties(fname=zh_font).get_name()
    plt.rcParams["font.sans-serif"] = ["WenQuanYi Zen Hei", "SimHei"] + plt.rcParams["font.sans-serif"]
    plt.rcParams["axes.unicode_minus"] = False
    plt.rcParams["mathtext.fontset"] = "stix"


# low-saturation palette matching the draw.io architecture diagrams
FILL = {
    "sample": ("#EAF2F8", "#8AA9C4"),
    "dlia": ("#EEF6EF", "#8DBA98"),
    "geom": ("#FFF7E8", "#D8B46A"),
    "sonar": ("#FBEFE5", "#D4A17B"),
    "fuse": ("#F2EDF7", "#A996C0"),
    "out": ("#EAF6F5", "#80B4AF"),
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
    ax.text(
        xy[0] + w / 2, xy[1] + h / 2, text,
        ha="center", va="center", fontsize=fontsize,
        color="#26323D", zorder=3,
        fontweight="bold" if bold else "normal",
    )
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
    fig, ax = plt.subplots(figsize=(9.2, 6.4))
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    ax.axis("off")

    # ---- online magnetic chain (left column, top-down) ----
    b1 = _box(ax, (2, 82), 38, 13, "TMR8637 / SK2301 三轴采样\n（按采集配置：示例 2000 Hz 原始，\n10 Hz 特征步进）", "sample", 8.5)
    b2 = _box(ax, (2, 70), 38, 8, "标定 · 去趋势 · 窗函数", "sample", 9.5)
    b3 = _box(ax, (2, 55), 38, 10, "45/50 Hz 数字锁相放大（DLIA）\n连续 I/Q · 旋转不变模量 · SNR", "dlia", 8.8)
    b4 = _box(ax, (2, 40), 38, 10, "峰值定位 · FWHM · 过线周期", "geom", 9.5)
    b5 = _box(ax, (2, 25), 38, 10, "横偏 · 垂直距离 · 埋深及质量分", "geom", 9)

    _arrow(ax, (21, 82), (21, 78))
    _arrow(ax, (21, 70), (21, 65))
    _arrow(ax, (21, 55), (21, 50))
    _arrow(ax, (21, 40), (21, 35))

    # ---- sonar branch (right, feeds geometry anchor) ----
    s1 = _box(ax, (46, 55), 30, 12, "声呐观测\n稀疏几何锚点 · 方向消歧\n（质量分驱动，非无条件可信）", "sonar", 9)

    # ---- fuse: cable geometry level online correction ----
    f1 = _box(ax, (46, 30), 30, 12, "电缆几何级在线修正\n先验地图配准 → 横偏/走向/埋深", "fuse", 9.5)

    # magnetic observables + sonar anchors -> geometry correction
    _arrow(ax, (40, 30), (46, 34))          # mag observables -> fuse
    _arrow(ax, (61, 55), (61, 42))          # sonar -> fuse

    # ---- deployment facade output ----
    o1 = _box(ax, (39, 13), 44, 10, "CableTrackingOutput\n横偏 · 路由进度 · 埋深及不确定度 · 置信度 · 就绪标志", "out", 9)
    _arrow(ax, (61, 30), (61, 23))
    _arrow(ax, (21, 25), (21, 8))
    _arrow(ax, (21, 8), (39, 15))           # mag observables also into output aggregation path

    # ---- consumers ----
    c1 = _box(ax, (39, 1.5), 44, 8, "行为树 / FSM · UA-MPC · 内层执行链", "consumer", 9.5)
    _arrow(ax, (61, 13), (61, 9.5))

    # ---- two-level estimation callout box (upper right) ----
    lvl = FancyBboxPatch(
        (44, 74), 52, 20,
        boxstyle="round,pad=0.02,rounding_size=0.06",
        linewidth=1.4, edgecolor="#A996C0", facecolor="#F7F4FB", zorder=2,
    )
    ax.add_patch(lvl)
    ax.text(70, 91, "两级估计分层", ha="center", va="center", fontsize=10.5,
            fontweight="bold", color="#4A3B63", zorder=3)
    ax.text(70, 85, "载体级 ES-EKF：AUV 位姿 + 协方差", ha="center", va="center",
            fontsize=9, color="#26323D", zorder=3)
    _arrow(ax, (70, 83), (70, 80), color="#A996C0")
    ax.text(70, 77.5, "电缆几何级在线修正：先验地图 + 声磁观测 → 横偏/走向/埋深",
            ha="center", va="center", fontsize=8.0, color="#26323D", zorder=3)

    # link ES-EKF pose into cable geometry correction (route on the right edge to
    # avoid crossing the sonar box)
    _arrow(ax, (90, 74), (78, 38), dashed=True, color="#A996C0")

    # truth note (offline-only)
    ax.text(3, 6, "真值仅进入离线评价，不进入在线管线", ha="left", va="center",
            fontsize=8.4, color="#8A5A5A", style="italic", zorder=3)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for ext in ("png", "pdf"):
        fig.savefig(OUT_DIR / f"cable_acoustic_magnetic_perception_pipeline.{ext}",
                    dpi=200, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print("wrote", OUT_DIR / "cable_acoustic_magnetic_perception_pipeline.{png,pdf}")


if __name__ == "__main__":
    render()

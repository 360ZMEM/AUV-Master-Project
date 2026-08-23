#!/usr/bin/env python3
"""Render the active-crossing observability method figure.

A distilled redraw of the sub-repo `fig_zigzag_probe`, kept minimal for §2.3.5:
only the true cable, the AUV crossing trajectory, the over-cable peak points, the
crossing angle theta, and the estimated centerline are shown. A companion |B|
profile panel makes explicit that one crossing yields two geometric observables:
the peak instant fixes the lateral centerline (e=0), while the half-maximum full
width (FWHM) fixes the vertical distance / burial depth.

This is the *local active probe* used in TRACK/REACQUIRE, not the large-area
coverage zig-zag of SEARCH; the caption/text must keep that distinction.

Output:
  docs/thesis/figures/architecture/cable_active_crossing_observability.{png,pdf}
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Arc

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import thesis_plot_style as tps  # noqa: E402

OUT_DIR = ROOT / "docs/thesis/figures/architecture"


def _setup_font() -> None:
    tps.apply_thesis_style(layout="full")


C_CABLE = tps.REFERENCE
C_TRAJ = tps.PROPOSED
C_PEAK = tps.BASELINE_1
C_CENTER = tps.BASELINE_2


def _triangle(x, amp, period, phase=0.0):
    return amp * (2.0 / np.pi) * np.arcsin(np.sin(2 * np.pi * (x - phase) / period))


def render() -> None:
    _setup_font()
    fig = plt.figure(figsize=tps.figure_size("full", height=4.8))
    gs = fig.add_gridspec(2, 1, height_ratios=[1.45, 1.0], hspace=0.42)
    ax = fig.add_subplot(gs[0])
    axb = fig.add_subplot(gs[1])

    # ================= top: geometry (top-down view) =================
    amp, period = 0.85, 2.6
    x = np.linspace(0.4, 9.6, 800)
    y = _triangle(x, amp, period)

    # true cable
    ax.plot([0.2, 9.8], [0, 0], color=C_CABLE, lw=2.6, zorder=3)
    ax.text(9.75, 0.16, "真值电缆", color=C_CABLE, fontsize=9.5, ha="right", va="bottom")

    # AUV crossing trajectory
    ax.plot(x, y, color=C_TRAJ, lw=2.0, zorder=4)
    ax.text(1.0, amp + 0.16, "AUV 之字形横切航迹", color=C_TRAJ, fontsize=9.5,
            ha="left", va="bottom")

    # over-cable peak observation points: the trajectory crosses the true cable
    # (y=0) at x = k*period/2 (phase=0).
    zx = np.array([k * (period / 2.0) for k in range(1, 8)])
    zx = np.array([xx for xx in zx if 0.5 < xx < 9.5])
    ax.scatter(zx, np.zeros_like(zx), s=42, color=C_PEAK, edgecolor="#8A5A1E",
               linewidth=0.8, zorder=6)
    ax.text(zx[0] - 0.15, -0.5, "穿缆峰值观测点", color="#8A5A1E", fontsize=9,
            ha="left", va="top")

    # estimated centerline (weighted PCA fit through peaks) -- offset slightly to
    # distinguish it visually from the true cable
    ax.plot([0.4, 9.6], [0.07, 0.02], color=C_CENTER, lw=1.8, ls=(0, (6, 3)), zorder=5)
    ax.text(6.6, 0.55, "估计中心线（加权 PCA 拟合）", color=C_CENTER, fontsize=9,
            ha="left", va="bottom")

    # crossing angle theta at a rising edge (rising zero-crossings are at even k)
    x0 = zx[1]
    ax.add_patch(Arc((x0, 0), 1.4, 1.4, angle=0, theta1=0, theta2=48,
                     color="#7A5AA0", lw=1.6, zorder=7))
    ax.text(x0 + 0.85, 0.30, r"横切角 $\theta$", color="#7A5AA0", fontsize=9.5,
            ha="left", va="center")

    # scan pitch d between adjacent peaks
    ax.annotate("", xy=(zx[2], -0.95), xytext=(zx[3], -0.95),
                arrowprops=dict(arrowstyle="<->", color="#6B6B6B", lw=1.2))
    ax.text((zx[2] + zx[3]) / 2, -1.12, "探查周期间距 d", color="#4A4A4A",
            fontsize=8.6, ha="center", va="top")
    for xx in (zx[2], zx[3]):
        ax.plot([xx, xx], [0, -0.95], color="#9AA0A6", lw=0.7, ls=":", zorder=2)

    ax.set_xlim(0, 10)
    ax.set_ylim(-1.45, 1.55)
    ax.axis("off")
    ax.set_title("(a) 主动横切构造局部几何可观测性", loc="left")

    # ================= bottom: |B| profile of one crossing =================
    e = np.linspace(-2.2, 2.2, 500)
    z_depth = 1.0
    # rotation-invariant magnitude of a buried line current ~ 1/(e^2+z^2)
    B = 1.0 / (e ** 2 + z_depth ** 2)
    B = B / B.max()
    axb.plot(e, B, color=C_TRAJ, lw=2.2, zorder=4)

    # peak -> lateral centerline
    axb.plot([0, 0], [0, 1.0], color=C_PEAK, lw=1.4, ls="--", zorder=3)
    axb.scatter([0], [1.0], s=44, color=C_PEAK, edgecolor="#8A5A1E",
                linewidth=0.8, zorder=6)
    axb.text(0.08, 1.02, "峰值 → 横向中心线 $e=0$", color="#8A5A1E", fontsize=9,
             ha="left", va="bottom")

    # FWHM -> vertical distance
    half = 0.5
    e_half = np.sqrt(1.0 / half - z_depth ** 2)  # where B = 0.5
    axb.annotate("", xy=(-e_half, half), xytext=(e_half, half),
                 arrowprops=dict(arrowstyle="<->", color="#5C9A6B", lw=1.6))
    axb.plot([-e_half, -e_half], [0, half], color="#9AA0A6", lw=0.7, ls=":")
    axb.plot([e_half, e_half], [0, half], color="#9AA0A6", lw=0.7, ls=":")
    axb.text(0, half - 0.14, "半高全宽 FWHM → 垂直距离 / 埋深 $z$", color="#3F6B4C",
             fontsize=9, ha="center", va="top")

    axb.set_xlim(-2.4, 2.4)
    axb.set_ylim(0, 1.35)
    axb.set_xlabel("相对电缆的横向位置 $e$ (m)")
    axb.set_ylabel("旋转不变模量 $|B|$ (归一化)")
    axb.set_yticks([0, 0.5, 1.0])
    axb.spines[["top", "right"]].set_visible(False)
    axb.set_title(
        "(b) 单次横切同时给出横向中心与垂直距离",
        loc="left",
    )

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    tps.save_figure(
        fig,
        OUT_DIR / "cable_active_crossing_observability",
    )
    plt.close(fig)
    print("wrote", OUT_DIR / "cable_active_crossing_observability.{png,pdf}")


if __name__ == "__main__":
    render()

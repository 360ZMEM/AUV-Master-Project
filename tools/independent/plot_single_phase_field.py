#!/usr/bin/env python3
"""Visualize the field direction and radial decay of a single AC conductor.

This script is intentionally independent from the project simulation stack. It
uses the analytic infinite-wire solution and writes both PDF and PNG figures.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import LogNorm
from matplotlib.patches import Circle

import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import thesis_plot_style as tps  # noqa: E402


MU0 = 4.0 * np.pi * 1.0e-7


def configure_plot_style() -> None:
    tps.apply_thesis_style(layout="full")


def default_output_dir() -> Path:
    return (
        Path(__file__).resolve().parents[2]
        / "docs"
        / "thesis"
        / "figures"
        / "magnetics"
    )


def field_map(current_sign: float, extent_m: float = 1.0) -> tuple[np.ndarray, ...]:
    axis = np.linspace(-extent_m, extent_m, 161)
    x, y = np.meshgrid(axis, axis)
    radius_sq = x * x + y * y
    wire_radius = 0.08
    valid = radius_sq >= wire_radius**2

    bx = np.full_like(x, np.nan)
    by = np.full_like(y, np.nan)
    magnitude_ut = np.full_like(x, np.nan)
    bx[valid] = -current_sign * y[valid] / radius_sq[valid]
    by[valid] = current_sign * x[valid] / radius_sq[valid]
    magnitude_ut[valid] = MU0 / (2.0 * np.pi * np.sqrt(radius_sq[valid])) * 1.0e6
    return x, y, bx, by, magnitude_ut


def draw_current_symbol(ax: plt.Axes, positive: bool) -> None:
    circle = Circle((0.0, 0.0), 0.08, facecolor="white", edgecolor="black", lw=1.2, zorder=8)
    ax.add_patch(circle)
    if positive:
        ax.plot(0.0, 0.0, "k.", ms=7, zorder=9)
    else:
        ax.plot([-0.035, 0.035], [-0.035, 0.035], color="black", lw=1.2, zorder=9)
        ax.plot([-0.035, 0.035], [0.035, -0.035], color="black", lw=1.2, zorder=9)


def make_figure() -> plt.Figure:
    configure_plot_style()

    fig = plt.figure(
        figsize=tps.figure_size("full", height=4.55),
        layout="constrained",
    )
    grid = fig.add_gridspec(2, 2, height_ratios=(1.0, 0.72))
    field_axes = [fig.add_subplot(grid[0, 0]), fig.add_subplot(grid[0, 1])]
    decay_ax = fig.add_subplot(grid[1, :])

    contour = None
    for ax, sign, title in zip(
        field_axes,
        (1.0, -1.0),
        (
            r"(a) 电流流出截面 $\odot$：磁场逆时针",
            r"(b) 电流流入截面 $\otimes$：磁场顺时针",
        ),
    ):
        x, y, bx, by, magnitude_ut = field_map(sign)
        contour = ax.contourf(
            x,
            y,
            magnitude_ut,
            levels=np.geomspace(0.14, 3.0, 18),
            norm=LogNorm(vmin=0.14, vmax=3.0),
            cmap="cividis",
            extend="both",
        )
        ax.streamplot(
            x[0],
            y[:, 0],
            bx,
            by,
            color="#202020",
            density=0.72,
            linewidth=0.75,
            arrowsize=0.8,
        )
        draw_current_symbol(ax, positive=sign > 0.0)
        ax.set_aspect("equal")
        ax.set_xlim(-1.0, 1.0)
        ax.set_ylim(-1.0, 1.0)
        ax.set_xlabel(r"横向位置 $x$ (m)")
        ax.set_ylabel(r"竖向位置 $y$ (m)")
        ax.set_title(title, loc="left")

    assert contour is not None
    colorbar = fig.colorbar(contour, ax=field_axes, orientation="horizontal", shrink=0.72, pad=0.03)
    colorbar.set_ticks((0.2, 0.5, 1.0, 2.0))
    colorbar.set_ticklabels(("0.2", "0.5", "1", "2"))
    colorbar.set_label(r"磁场强度 $|\mathbf{B}|$ ($\mu$T，峰值电流 1 A)")

    radius = np.geomspace(0.08, 2.0, 240)
    magnitude_ut = MU0 / (2.0 * np.pi * radius) * 1.0e6
    decay_ax.loglog(
        radius,
        magnitude_ut,
        color=tps.PROPOSED,
        lw=1.7,
        label=r"$|\mathbf{B}|=\mu_0 I/(2\pi r)$",
    )
    sample_radius = np.array([0.1, 1.0])
    sample_field = MU0 / (2.0 * np.pi * sample_radius) * 1.0e6
    decay_ax.scatter(
        sample_radius,
        sample_field,
        s=34,
        color=tps.WARNING,
        edgecolor="white",
        linewidth=0.7,
        zorder=4,
    )
    decay_ax.text(0.1, sample_field[0] * 1.16, r"$r=0.1$ m，$|B|=2$ $\mu$T", ha="left")
    decay_ax.text(1.0, sample_field[1] * 0.78, r"$r=1$ m，$|B|=0.2$ $\mu$T", ha="right", va="top")
    decay_ax.annotate(
        "距离增大 10 倍\n场强降至 1/10",
        xy=(1.0, sample_field[1]),
        xytext=(0.31, 0.46),
        ha="center",
        arrowprops={"arrowstyle": "->", "lw": 1.0, "color": "#333333"},
        bbox={"facecolor": "white", "edgecolor": "#777777", "alpha": 0.92, "pad": 2.0},
    )
    decay_ax.set_xlabel(r"距导线中心的距离 $r$ (m)")
    decay_ax.set_ylabel(r"磁场强度 $|\mathbf{B}|$ ($\mu$T)")
    decay_ax.set_title(r"(c) 距离越远，磁场按 $1/r$ 规律减弱", loc="left")
    decay_ax.set_xticks((0.1, 1.0), labels=("0.1", "1"))
    decay_ax.set_yticks((0.1, 1.0), labels=("0.1", "1"))
    decay_ax.grid(True, which="both", alpha=0.28)
    decay_ax.legend(loc="upper right")

    return fig


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=default_output_dir())
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    figure = make_figure()
    for output in tps.save_figure(
        figure,
        args.output_dir / "single_phase_field_direction",
    ):
        print(output)
    plt.close(figure)


if __name__ == "__main__":
    main()

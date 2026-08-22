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


MU0 = 4.0 * np.pi * 1.0e-7


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
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 9,
            "axes.titlesize": 10,
            "axes.labelsize": 9,
            "legend.fontsize": 8,
            "axes.unicode_minus": False,
        }
    )

    fig = plt.figure(figsize=(7.25, 5.15), layout="constrained")
    grid = fig.add_gridspec(2, 2, height_ratios=(1.0, 0.72))
    field_axes = [fig.add_subplot(grid[0, 0]), fig.add_subplot(grid[0, 1])]
    decay_ax = fig.add_subplot(grid[1, :])

    contour = None
    for ax, sign, title in zip(
        field_axes,
        (1.0, -1.0),
        (r"(a) Positive half-cycle: $I(t)>0$", r"(b) Negative half-cycle: $I(t)<0$"),
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
        ax.set_xlabel(r"$x$ (m)")
        ax.set_ylabel(r"$y$ (m)")
        ax.set_title(title, loc="left")

    assert contour is not None
    colorbar = fig.colorbar(contour, ax=field_axes, orientation="horizontal", shrink=0.72, pad=0.03)
    colorbar.set_ticks((0.2, 0.5, 1.0, 2.0))
    colorbar.set_ticklabels(("0.2", "0.5", "1", "2"))
    colorbar.set_label(r"$|\mathbf{B}|$ ($\mu$T), $I_{\mathrm{peak}}=1$ A")

    radius = np.geomspace(0.08, 2.0, 240)
    magnitude_ut = MU0 / (2.0 * np.pi * radius) * 1.0e6
    decay_ax.loglog(
        radius,
        magnitude_ut,
        color="#1f5a85",
        lw=2.1,
        label=r"$|\mathbf{B}|=\mu_0 I/(2\pi r)$",
    )
    reference_radius = np.array([0.12, 1.2])
    reference = 0.12 / reference_radius
    decay_ax.loglog(
        reference_radius,
        reference,
        "--",
        color="#b0473c",
        lw=1.5,
        label=r"reference slope $r^{-1}$",
    )
    decay_ax.annotate(
        r"$10\times r\ \Rightarrow\ 0.1\times |\mathbf{B}|$",
        xy=(1.2, 0.1),
        xytext=(0.43, 0.33),
        arrowprops={"arrowstyle": "->", "lw": 0.9, "color": "#333333"},
    )
    decay_ax.set_xlabel(r"Radial distance $r$ (m)")
    decay_ax.set_ylabel(r"$|\mathbf{B}|$ ($\mu$T)")
    decay_ax.set_title("(c) Radial amplitude decay", loc="left")
    decay_ax.grid(True, which="both", alpha=0.28)
    decay_ax.legend(loc="upper right")

    return fig


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=default_output_dir())
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    figure = make_figure()
    for suffix in ("pdf", "png"):
        output = args.output_dir / f"single_phase_field_direction.{suffix}"
        figure.savefig(output, dpi=300, bbox_inches="tight")
        print(output)
    plt.close(figure)


if __name__ == "__main__":
    main()

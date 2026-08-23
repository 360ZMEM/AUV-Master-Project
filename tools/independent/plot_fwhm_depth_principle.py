#!/usr/bin/env python3
"""Visualize why the dipole-envelope FWHM gives twice the cable distance.

The model is B(x) = C / (x^2 + z^2). The first panel varies z to expose the
geometric width relation; the second varies C to show amplitude cancellation.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import thesis_plot_style as tps  # noqa: E402

COLORS = (tps.PROPOSED, tps.BASELINE_1, tps.BASELINE_2)
LINE_STYLES = ("-", "--", "-.")


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


def envelope(x: np.ndarray, vertical_distance: float, scale: float = 1.0) -> np.ndarray:
    return scale / (x * x + vertical_distance * vertical_distance)


def make_figure() -> plt.Figure:
    configure_plot_style()
    fig, axes = plt.subplots(
        1,
        2,
        figsize=tps.figure_size("full", height=3.15),
        layout="constrained",
    )

    # Panel (a): the normalized profile broadens linearly with vertical distance.
    x = np.linspace(-3.3, 3.3, 1001)
    distances = (0.6, 1.0, 1.4)
    for distance, color, line_style in zip(distances, COLORS, LINE_STYLES):
        values = envelope(x, distance)
        normalized = values / np.max(values)
        axes[0].plot(
            x,
            normalized,
            color=color,
            ls=line_style,
            lw=1.9,
            label=rf"距离 $z={distance:.1f}$ m $\Rightarrow W_x={2.0 * distance:.1f}$ m",
        )
        axes[0].plot(
            (-distance, distance),
            (0.5, 0.5),
            linestyle="none",
            marker="o",
            ms=4.5,
            color=color,
            markeredgecolor="white",
            markeredgewidth=0.6,
        )
    axes[0].axhline(0.5, color="#333333", lw=0.9, ls=":")
    axes[0].text(3.18, 0.52, r"半峰值 $|B|_{\max}/2$", ha="right", va="bottom")
    axes[0].set_xlim(-3.3, 3.3)
    axes[0].set_ylim(0.0, 1.06)
    axes[0].set_xlabel(r"横向偏移 $x$ (m)")
    axes[0].set_ylabel(r"归一化磁场强度 $|B(x)|/|B|_{\max}$")
    axes[0].set_title("(a) 距离越大，横切峰越宽", loc="left")
    axes[0].grid(True, alpha=0.25)
    axes[0].legend(loc="upper right")

    # Panel (b): changing current or attenuation scale changes height, not width.
    fixed_distance = 1.0
    scales = (0.55, 1.0, 1.7)
    signal_names = ("弱信号", "中等信号", "强信号")
    for scale, signal_name, color, line_style in zip(scales, signal_names, COLORS, LINE_STYLES):
        values = envelope(x, fixed_distance, scale)
        peak = scale / fixed_distance**2
        half_peak = 0.5 * peak
        axes[1].plot(
            x,
            values,
            color=color,
            ls=line_style,
            lw=1.9,
            label=rf"{signal_name}（$C={scale:.2f}$）",
        )
        axes[1].plot(
            (-fixed_distance, fixed_distance),
            (half_peak, half_peak),
            color=color,
            lw=0.8,
            ls=":",
        )
        axes[1].plot(
            (-fixed_distance, fixed_distance),
            (half_peak, half_peak),
            linestyle="none",
            marker="o",
            ms=4.5,
            color=color,
            markeredgecolor="white",
            markeredgewidth=0.6,
        )
    axes[1].axvline(-fixed_distance, color="#555555", lw=0.8, ls=":")
    axes[1].axvline(fixed_distance, color="#555555", lw=0.8, ls=":")
    axes[1].annotate(
        "",
        xy=(-fixed_distance, 0.08),
        xytext=(fixed_distance, 0.08),
        arrowprops={"arrowstyle": "<->", "lw": 1.2, "color": "#111111"},
    )
    axes[1].text(
        0.0,
        0.02,
        r"$W_x=2z$",
        ha="center",
        va="bottom",
        bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.9, "pad": 1.2},
    )
    axes[1].text(
        0.5,
        0.48,
        r"测得 $W_x$，即可由 $z=W_x/2$ 估计垂直距离",
        ha="center",
        va="center",
        transform=axes[1].transAxes,
        bbox={"facecolor": "white", "edgecolor": "#777777", "alpha": 0.92, "pad": 2.2},
    )
    axes[1].set_xlim(-3.3, 3.3)
    axes[1].set_ylim(0.0, 1.82)
    axes[1].set_xlabel(r"横向偏移 $x$ (m)")
    axes[1].set_ylabel(r"磁场强度 $|B(x)|$ (相对量)")
    axes[1].set_title("(b) 电流或屏蔽只改变峰高，不改变半高全宽", loc="left")
    axes[1].grid(True, alpha=0.25)
    axes[1].legend(loc="upper right", title=r"固定距离 $z=1$ m")

    return fig


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=default_output_dir())
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    figure = make_figure()
    for output in tps.save_figure(
        figure,
        args.output_dir / "fwhm_depth_principle",
    ):
        print(output)
    plt.close(figure)


if __name__ == "__main__":
    main()

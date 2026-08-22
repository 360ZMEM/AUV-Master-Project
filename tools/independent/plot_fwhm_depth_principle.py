#!/usr/bin/env python3
"""Visualize why the dipole-envelope FWHM gives twice the cable distance.

The model is B(x) = C / (x^2 + z^2). The first panel varies z to expose the
geometric width relation; the second varies C to show amplitude cancellation.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


COLORS = ("#2468a2", "#c95f26", "#33865b")
LINE_STYLES = ("-", "--", "-.")


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
    fig, axes = plt.subplots(1, 2, figsize=(7.25, 3.25), layout="constrained")

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
            label=rf"$z={distance:.1f}$ m, $W_x={2.0 * distance:.1f}$ m",
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
    axes[0].text(3.18, 0.52, r"$B_{\max}/2$", ha="right", va="bottom")
    axes[0].set_xlim(-3.3, 3.3)
    axes[0].set_ylim(0.0, 1.06)
    axes[0].set_xlabel(r"Cross-track offset $x$ (m)")
    axes[0].set_ylabel(r"$|B(x)|/|B|_{\max}$")
    axes[0].set_title("(a) Distance controls profile width", loc="left")
    axes[0].grid(True, alpha=0.25)
    axes[0].legend(loc="upper right")

    # Panel (b): changing current or attenuation scale changes height, not width.
    fixed_distance = 1.0
    scales = (0.55, 1.0, 1.7)
    for scale, color, line_style in zip(scales, COLORS, LINE_STYLES):
        values = envelope(x, fixed_distance, scale)
        peak = scale / fixed_distance**2
        half_peak = 0.5 * peak
        axes[1].plot(
            x,
            values,
            color=color,
            ls=line_style,
            lw=1.9,
            label=rf"$C={scale:.2f}$",
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
    axes[1].set_xlim(-3.3, 3.3)
    axes[1].set_ylim(0.0, 1.82)
    axes[1].set_xlabel(r"Cross-track offset $x$ (m)")
    axes[1].set_ylabel(r"$|B(x)|$ (arbitrary units)")
    axes[1].set_title(r"(b) Scale $C$ changes height, not FWHM", loc="left")
    axes[1].grid(True, alpha=0.25)
    axes[1].legend(loc="upper right", title=r"Fixed $z=1$ m")

    return fig


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=default_output_dir())
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    figure = make_figure()
    for suffix in ("pdf", "png"):
        output = args.output_dir / f"fwhm_depth_principle.{suffix}"
        figure.savefig(output, dpi=300, bbox_inches="tight")
        print(output)
    plt.close(figure)


if __name__ == "__main__":
    main()

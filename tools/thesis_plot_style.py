#!/usr/bin/env python3
"""ThuThesis scientific figure style.

This module is the single source of truth for active thesis plots. It does not
load or transform experiment data.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Sequence

ZH_FONT_PATH = "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"

THESIS_DPI = 600
SINGLE_COLUMN_WIDTH = 3.3
FULL_WIDTH = 6.8

PROPOSED = "#0072B2"
BASELINE_1 = "#E69F00"
BASELINE_2 = "#009E73"
BASELINE_3 = "#7E57C2"
REFERENCE = "#333333"
WARNING = "#D55E00"
NEUTRAL = "#8C8C8C"
GRID_COLOR = "#B8B8B8"

SEQUENTIAL_GRAYS: tuple[str, ...] = (
    "#262626",
    "#595959",
    "#808080",
    "#A6A6A6",
    "#CCCCCC",
    "#E6E6E6",
)

HATCHES: tuple[str, ...] = ("", "///", "...", "xxx", "\\\\\\", "ooo")
ACCENT_COLORS: tuple[str, ...] = (
    PROPOSED,
    BASELINE_1,
    BASELINE_2,
    BASELINE_3,
    REFERENCE,
    WARNING,
)

_STYLE_APPLIED = False


def _resolve_font_name() -> str | None:
    """Return the first available Chinese font family."""
    try:
        import matplotlib.font_manager as fm
    except Exception:
        return None

    if os.path.exists(ZH_FONT_PATH):
        try:
            fm.fontManager.addfont(ZH_FONT_PATH)
            return fm.FontProperties(fname=ZH_FONT_PATH).get_name()
        except Exception:
            pass

    for family in (
        "Songti SC",
        "STSong",
        "Noto Serif CJK SC",
        "Source Han Serif SC",
        "SimSun",
        "WenQuanYi Zen Hei",
        "PingFang SC",
    ):
        try:
            fm.findfont(family, fallback_to_default=False)
        except ValueError:
            continue
        return family
    return None


def figure_size(
    layout: str = "full",
    *,
    height: float | None = None,
    aspect: float = 1.6,
) -> tuple[float, float]:
    """Return a thesis-sized figure in inches.

    ``aspect`` is width divided by height. Explicit heights are accepted for
    dense multi-panel figures, but callers should keep the final aspect above
    1.4 whenever the content allows it.
    """
    if layout not in {"single", "full"}:
        raise ValueError(f"unknown layout: {layout}")
    width = SINGLE_COLUMN_WIDTH if layout == "single" else FULL_WIDTH
    return width, height if height is not None else width / aspect


def apply_thesis_style(
    base_font_size: int | None = None,
    *,
    layout: str = "full",
) -> None:
    """Apply Chinese thesis typography and restrained scientific styling."""
    global _STYLE_APPLIED
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return

    if layout not in {"single", "full"}:
        raise ValueError(f"unknown layout: {layout}")
    label_size = base_font_size or (9 if layout == "single" else 10)
    tick_size = label_size - 1

    zh_name = _resolve_font_name()
    if zh_name:
        plt.rcParams["font.family"] = zh_name
    else:
        plt.rcParams["font.sans-serif"] = (
            [
                "Songti SC",
                "STSong",
                "Noto Serif CJK SC",
                "SimSun",
                "WenQuanYi Zen Hei",
                "PingFang SC",
            ]
            + list(plt.rcParams.get("font.sans-serif", []))
        )

    plt.rcParams.update(
        {
            "axes.unicode_minus": False,
            "mathtext.fontset": "stix",
            "font.serif": ["STIXGeneral", "Times New Roman", "Times"],
            "figure.dpi": 150,
            "savefig.dpi": THESIS_DPI,
            "savefig.bbox": "tight",
            "savefig.pad_inches": 0.04,
            "font.size": label_size,
            "axes.titlesize": label_size,
            "axes.labelsize": label_size,
            "legend.fontsize": tick_size,
            "xtick.labelsize": tick_size,
            "ytick.labelsize": tick_size,
            "axes.linewidth": 0.9,
            "axes.grid": True,
            "axes.prop_cycle": plt.cycler(color=ACCENT_COLORS),
            "grid.alpha": 0.45,
            "grid.color": GRID_COLOR,
            "grid.linewidth": 0.5,
            "grid.linestyle": "-",
            "axes.axisbelow": True,
            "legend.frameon": True,
            "legend.facecolor": "white",
            "legend.framealpha": 1.0,
            "legend.edgecolor": "#BFBFBF",
            "legend.fancybox": False,
            "lines.linewidth": 1.7,
            "lines.markersize": 4.5,
            "patch.linewidth": 0.9,
        }
    )
    _STYLE_APPLIED = True


def series_style(index: int, *, colored: bool = True) -> dict[str, object]:
    """Return color- and grayscale-safe bar styling."""
    gray = SEQUENTIAL_GRAYS[index % len(SEQUENTIAL_GRAYS)]
    hatch = HATCHES[index % len(HATCHES)]
    style: dict[str, object] = {
        "facecolor": (
            ACCENT_COLORS[index % len(ACCENT_COLORS)] if colored else gray
        ),
        "hatch": hatch,
        "edgecolor": REFERENCE,
        "linewidth": 0.8,
    }
    return style


def line_style(index: int) -> dict[str, object]:
    """Return color- and grayscale-safe line styling."""
    line_kinds = ("-", "--", "-.", ":")
    markers = ("o", "s", "^", "D", "v", "P")
    return {
        "color": ACCENT_COLORS[index % len(ACCENT_COLORS)],
        "linestyle": line_kinds[index % len(line_kinds)],
        "marker": markers[index % len(markers)],
        "markersize": 4.5,
        "markeredgecolor": REFERENCE,
        "markeredgewidth": 0.4,
        "linewidth": 1.7 if index == 0 else 1.4,
    }


def add_panel_labels(
    axes,
    *,
    labels: Sequence[str] | None = None,
    x: float = 0.0,
    y: float = 1.02,
) -> None:
    """Add consistent ``(a)``, ``(b)``, ... labels to subplot axes."""
    axes_list = list(getattr(axes, "flat", axes))
    labels = labels or tuple(
        f"({chr(ord('a') + index)})" for index in range(len(axes_list))
    )
    for axis, label in zip(axes_list, labels):
        axis.text(
            x,
            y,
            label,
            transform=axis.transAxes,
            ha="left",
            va="bottom",
            fontweight="bold",
            clip_on=False,
        )


def save_figure(
    fig,
    out_base: Path,
    *,
    formats: Sequence[str] = ("pdf", "png"),
    dpi: int = THESIS_DPI,
) -> list[Path]:
    """Export a vector PDF and a high-resolution PNG."""
    out_base = Path(out_base)
    out_base.parent.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for ext in formats:
        path = out_base.with_suffix(f".{ext}")
        fig.savefig(path, dpi=dpi, bbox_inches="tight")
        written.append(path)
    return written


apply_thesis_style()

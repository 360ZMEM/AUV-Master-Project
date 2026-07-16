#!/usr/bin/env python3
"""论文图统一样式（27 号文 P1-4：中文字体 / 黑白可辨 / 300 dpi）。

单一事实源。所有为正文（thuthesis）生产 PNG/PDF 图素材的驱动脚本都应
``import`` 本模块并调用 :func:`apply_thesis_style`，以保证：

  * **中文字体**：注入容器内唯一 CJK 字体文泉驿正黑（``wqy-zenhei.ttc``），
    缺失时回退到 sans-serif 名单；负号统一用 ASCII（``axes.unicode_minus=False``），
    避免 Type-3 minus 在期刊/答辩投影上渲染为方块。
  * **黑白可辨**：提供 :data:`SEQUENTIAL_GRAYS`（灰度序列）与
    :data:`HATCHES`（填充纹理）两套通道，使柱状/分组图在\ *灰度打印*\ 下仍可区分，
    不依赖彩色；:func:`series_style` 按序号同时返回颜色与纹理。
  * **300 dpi**：``figure.dpi`` / ``savefig.dpi`` 统一 300，:func:`save_figure`
    默认同时导出 PNG（位图预览）与 PDF（矢量入稿）。

设计约束：
  * 纯样式层，**不生产任何数据**，不读写实验产物；被 import 时零副作用（除注册字体）。
  * 幂等：重复调用 :func:`apply_thesis_style` 安全。
  * 不强制颜色——彩色仅作为灰度+纹理之上的\ *增强*\，去色后信息不丢失。
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Sequence

# 容器内唯一可用 CJK 字体（见 tools/mpc_xy_yaw_extreme_benchmark.py 既有约定）。
ZH_FONT_PATH = "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"

THESIS_DPI = 300

# 灰度序列：从深到浅，供\ *有序*\ 或\ *分类*\ 柱状使用；打印去色后仍单调可辨。
SEQUENTIAL_GRAYS: tuple[str, ...] = (
    "#1a1a1a",  # near-black
    "#4d4d4d",
    "#7f7f7f",
    "#a6a6a6",
    "#cccccc",
    "#e6e6e6",
)

# 纹理：叠加在灰度之上，即便相邻灰阶接近也能靠 hatch 区分（黑白激光打印友好）。
HATCHES: tuple[str, ...] = ("", "///", "...", "xxx", "\\\\\\", "ooo")

# 彩色增强（可选）：屏幕/彩打时更醒目，去色后退化为 SEQUENTIAL_GRAYS 的单调序。
# 取自 colorbrewer 风格、对色盲相对友好的定性色。
ACCENT_COLORS: tuple[str, ...] = (
    "#4c72b0",  # blue
    "#dd8452",  # orange
    "#55a868",  # green
    "#c44e52",  # red
    "#8172b3",  # purple
    "#937860",  # brown
)

_STYLE_APPLIED = False


def _resolve_font_name() -> str | None:
    """注册文泉驿正黑并返回其 family 名；缺失时返回 None（交由回退名单）。"""
    try:
        import matplotlib.font_manager as fm
    except Exception:
        return None
    if os.path.exists(ZH_FONT_PATH):
        try:
            fm.fontManager.addfont(ZH_FONT_PATH)
            return fm.FontProperties(fname=ZH_FONT_PATH).get_name()
        except Exception:
            return None
    return None


def apply_thesis_style(base_font_size: int = 12) -> None:
    """统一 rcParams：中文字体 + ASCII 负号 + 300 dpi + 期刊级留白。幂等。"""
    global _STYLE_APPLIED
    try:
        import matplotlib
        matplotlib.use("Agg")  # 无显示环境（CI/容器）安全
        import matplotlib.pyplot as plt
    except Exception:
        return

    zh_name = _resolve_font_name()
    if zh_name:
        plt.rcParams["font.family"] = zh_name
    else:
        plt.rcParams["font.sans-serif"] = (
            ["WenQuanYi Zen Hei", "Noto Sans CJK SC", "SimHei"]
            + list(plt.rcParams.get("font.sans-serif", []))
        )

    plt.rcParams.update(
        {
            "axes.unicode_minus": False,
            "figure.dpi": THESIS_DPI,
            "savefig.dpi": THESIS_DPI,
            "savefig.bbox": "tight",
            "font.size": base_font_size,
            "axes.titlesize": base_font_size + 2,
            "axes.labelsize": base_font_size,
            "legend.fontsize": base_font_size - 1,
            "xtick.labelsize": base_font_size - 1,
            "ytick.labelsize": base_font_size - 1,
            "axes.grid": True,
            "grid.alpha": 0.3,
            "grid.linewidth": 0.6,
            "axes.axisbelow": True,
            "legend.framealpha": 0.9,
            "lines.linewidth": 1.8,
        }
    )
    _STYLE_APPLIED = True


def series_style(index: int, *, colored: bool = True) -> dict[str, object]:
    """返回第 ``index`` 个系列的绘图关键字：灰度填充 + 纹理（+ 可选彩色边/面）。

    用法（柱状图）::

        for i, arm in enumerate(arms):
            ax.bar(x + i * w, vals, w, **series_style(i), label=arm)

    去色打印时靠 ``facecolor``（灰阶）与 ``hatch``（纹理）双通道区分；``colored``
    为真时以 ``ACCENT_COLORS`` 上色边框以增强屏幕辨识，但不作为唯一区分依据。
    """
    gray = SEQUENTIAL_GRAYS[index % len(SEQUENTIAL_GRAYS)]
    hatch = HATCHES[index % len(HATCHES)]
    style: dict[str, object] = {
        "facecolor": gray,
        "hatch": hatch,
        "edgecolor": "black",
        "linewidth": 0.8,
    }
    if colored:
        style["edgecolor"] = ACCENT_COLORS[index % len(ACCENT_COLORS)]
        style["linewidth"] = 1.2
    return style


def line_style(index: int) -> dict[str, object]:
    """折线图黑白可辨关键字：线型 + marker + 灰度，配合 :data:`ACCENT_COLORS`。"""
    line_kinds = ("-", "--", "-.", ":")
    markers = ("o", "s", "^", "D", "v", "P")
    return {
        "color": ACCENT_COLORS[index % len(ACCENT_COLORS)],
        "linestyle": line_kinds[index % len(line_kinds)],
        "marker": markers[index % len(markers)],
        "markersize": 5,
        "markeredgecolor": "black",
        "markeredgewidth": 0.5,
    }


def save_figure(fig, out_base: Path, *, formats: Sequence[str] = ("png", "pdf"),
                dpi: int = THESIS_DPI) -> list[Path]:
    """把 ``fig`` 以 300 dpi 同时导出为 ``out_base.<ext>``；返回写出的路径列表。

    ``out_base`` 不含扩展名（如 ``.../figures/foo``）。父目录自动创建。
    """
    out_base = Path(out_base)
    out_base.parent.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for ext in formats:
        path = out_base.with_suffix(f".{ext}")
        fig.savefig(path, dpi=dpi)
        written.append(path)
    return written


# import 时即注册字体并套用样式，方便被动引用的脚本无需显式初始化。
apply_thesis_style()

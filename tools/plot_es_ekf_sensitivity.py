#!/usr/bin/env python3
"""从既有 ES-EKF 综合调优报告复算参数敏感性正文图（27 号文 P2-2：参数敏感性入正文）。

复用优先：不重跑调优（`tools/es_ekf_comprehensive_tuner.py`）——其源数据包为 2026-05
的单包离线回放，且 `algorithm/es_ekf.py` 分源门控已于 2026-08 细化，重跑会引入与冻结
产物不一致的漂移。本脚本只\ *读*\ 冻结报告 `results/tuning/ekf_comprehensive/tuning_report.md`
（该报告为权威 provenance），把其中的单参数灵敏度扫描与参数-RMSE 相关系数**重排版**为
期刊级正文图，统一走 `thesis_plot_style`（中文字体 / 黑白可辨 / 300 dpi）。

图的叙事（与 §5.5.5 可观性边界一致）：
  * 焦点面板（左）：四个噪声参数与水平 RMSE 的 Pearson 相关系数——只有 sigma_dvl 强相关
    （≈0.78），其余近零。这从``调参''角度独立佐证水平漂移是结构性不可观、非可整定项。
  * 支撑面板（右）：四个参数的单参数扫描下水平 RMSE 相对基线的偏移（毫米级），全程 < 25 mm、
    始终停在 9.06 m 量级，直观说明在缺绝对横向观测时任何噪声整定都无法压制漂移。

边界（诚实）：该报告为\ *单包（n=1）离线*\ 敏感性探针，仅作机制佐证，不构成多种子统计结论；
正文的多种子鲁棒性主结果仍以表 tab:ch05-eskf-robustness 为准。

用法：
    python3 tools/plot_es_ekf_sensitivity.py            # 生成 png+pdf 到 state_estimation/
    python3 tools/plot_es_ekf_sensitivity.py --check     # 只解析报告并打印摘要，不出图
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

REPORT = REPO_ROOT / "results" / "tuning" / "ekf_comprehensive" / "tuning_report.md"
OUT_BASE = (
    REPO_ROOT
    / "docs" / "thesis" / "figures" / "experiments"
    / "state_estimation" / "eskf_param_sensitivity"
)

# 四个噪声参数（与报告 §3 单参数扫描小节一一对应）及中文标签。
_PARAMS = ["sigma_dvl", "sigma_acc", "sigma_depth", "sigma_gyro"]
_PARAM_ZH = {
    "sigma_dvl": r"$\sigma_{\mathrm{DVL}}$",
    "sigma_acc": r"$\sigma_{\mathrm{acc}}$",
    "sigma_depth": r"$\sigma_{\mathrm{depth}}$",
    "sigma_gyro": r"$\sigma_{\mathrm{gyro}}$",
}


def _parse_sweep(text: str, param: str) -> tuple[list[float], list[float]]:
    """解析 §3 中某参数扫描表，返回（相对基线倍数, 水平 RMSE[m]）。

    表头形如： | 参数值 | 相对基线 | RMSE 3D (m) | RMSE XY (m) | RMSE Z (m) | 标记 |
    数据行形如： | 0.030000 | 1.00x | 9.0636 | 9.0636 | 0.0060 | 基线|
    """
    # 定位到该参数的小节（### x.y sigma_xxx），截到下一个 ### 之前。
    m = re.search(rf"^### [0-9.]+ {re.escape(param)}\b", text, flags=re.MULTILINE)
    if not m:
        raise ValueError(f"报告中未找到参数小节：{param}")
    start = m.end()
    nxt = re.search(r"^### ", text[start:], flags=re.MULTILINE)
    section = text[start : start + (nxt.start() if nxt else len(text) - start)]

    mult: list[float] = []
    rmse_xy: list[float] = []
    for line in section.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 5 or cells[0] in ("参数值", "") or set(cells[0]) <= set("-"):
            continue
        mmatch = re.match(r"([0-9.]+)x", cells[1])
        if not mmatch:
            continue
        try:
            mult.append(float(mmatch.group(1)))
            rmse_xy.append(float(cells[3]))
        except ValueError:
            continue
    if not mult:
        raise ValueError(f"参数 {param} 扫描表解析为空")
    # 按倍数升序，便于连线。
    order = sorted(range(len(mult)), key=lambda i: mult[i])
    return [mult[i] for i in order], [rmse_xy[i] for i in order]


def _parse_correlation(text: str) -> dict[str, float]:
    """解析 §6.1 参数-RMSE 相关系数表，返回 {param: pearson_r}。"""
    m = re.search(r"参数-RMSE 相关系数", text)
    if not m:
        raise ValueError("报告中未找到相关系数小节")
    section = text[m.end() :]
    out: dict[str, float] = {}
    for line in section.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 2 or cells[0] in ("参数", "") or set(cells[0]) <= set("-"):
            continue
        try:
            out[cells[0]] = float(cells[1])
        except ValueError:
            continue
        if len(out) >= len(_PARAMS):
            break
    return out


def _baseline_rmse_xy(sweeps: dict[str, tuple[list[float], list[float]]]) -> float:
    """从任一扫描的 1.00x 行取基线水平 RMSE（各扫描共享同一基线）。"""
    for mult, rmse in sweeps.values():
        for x, y in zip(mult, rmse):
            if abs(x - 1.0) < 1e-6:
                return y
    # 兜底：取所有点里最接近 9.06 的（不应触发）。
    return next(iter(sweeps.values()))[1][0]


def build_figure(sweeps, corr, baseline_xy):
    import matplotlib.pyplot as plt
    from tools.thesis_plot_style import ACCENT_COLORS, line_style, series_style

    fig, (ax_corr, ax_sweep) = plt.subplots(1, 2, figsize=(11.0, 4.2))

    # --- 焦点面板（左）：Pearson 相关系数水平条 --------------------------------
    ordered = sorted(_PARAMS, key=lambda p: abs(corr.get(p, 0.0)))
    y_pos = range(len(ordered))
    vals = [corr.get(p, 0.0) for p in ordered]
    for i, (p, v) in enumerate(zip(ordered, vals)):
        st = series_style(i)
        ax_corr.barh(i, abs(v), **st)
        ax_corr.text(
            abs(v) + 0.02, i, f"{v:+.3f}",
            va="center", ha="left", fontsize=10,
        )
    ax_corr.set_yticks(list(y_pos))
    ax_corr.set_yticklabels([_PARAM_ZH[p] for p in ordered])
    ax_corr.set_xlim(0, 1.0)
    ax_corr.set_ylim(-0.6, len(ordered) - 0.4)
    ax_corr.set_xlabel("与水平 RMSE 的 |Pearson 相关系数|")
    ax_corr.set_title("(a) 噪声参数敏感性排序（仅 DVL 强相关）")
    ax_corr.axvline(0.5, color="0.4", linestyle="--", linewidth=1.0)
    ax_corr.text(
        0.5, len(ordered) - 0.55, "强/弱阈值", color="0.4", fontsize=8,
        ha="center", va="top", rotation=90,
    )

    # --- 支撑面板（右）：单参数扫描下水平 RMSE 相对基线偏移（mm） --------------
    for i, p in enumerate(_PARAMS):
        mult, rmse = sweeps[p]
        delta_mm = [(y - baseline_xy) * 1000.0 for y in rmse]
        ax_sweep.plot(mult, delta_mm, label=_PARAM_ZH[p], **line_style(i))
    ax_sweep.axhline(0.0, color="0.4", linestyle="--", linewidth=1.0)
    ax_sweep.set_xscale("log")
    # 显式 plain 刻度，避免 mathtext 10^{-1} 触发 U+2212 缺字。
    ax_sweep.set_xticks([0.1, 0.2, 0.5, 1.0, 2.0, 5.0, 10.0])
    ax_sweep.set_xticklabels(["0.1", "0.2", "0.5", "1", "2", "5", "10"])
    ax_sweep.set_xlabel("参数相对基线倍数（对数轴）")
    ax_sweep.set_ylabel("水平 RMSE 相对基线偏移（mm）")
    ax_sweep.set_title(f"(b) 单参数扫描：始终停留在 {baseline_xy:.2f} m 量级")
    ax_sweep.legend(loc="upper left", ncol=2)

    fig.tight_layout()
    return fig


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--check", action="store_true", help="只解析报告并打印摘要，不出图")
    ap.add_argument("--output-base", type=Path, default=OUT_BASE)
    args = ap.parse_args()

    if not REPORT.is_file():
        print(f"[sensitivity][FAIL] 缺冻结报告：{REPORT}")
        return 1
    text = REPORT.read_text(encoding="utf-8")

    sweeps = {p: _parse_sweep(text, p) for p in _PARAMS}
    corr = _parse_correlation(text)
    baseline_xy = _baseline_rmse_xy(sweeps)

    print(f"[sensitivity] 基线水平 RMSE = {baseline_xy:.4f} m")
    for p in _PARAMS:
        mult, rmse = sweeps[p]
        span_mm = (max(rmse) - min(rmse)) * 1000.0
        print(
            f"[sensitivity] {p:11s} Pearson={corr.get(p, float('nan')):+.4f} "
            f"扫描点={len(mult):2d} 水平RMSE跨度={span_mm:6.2f} mm"
        )

    if args.check:
        return 0

    try:
        import matplotlib.pyplot as plt  # noqa: F401
    except Exception as exc:  # pragma: no cover
        print(f"[sensitivity][FAIL] matplotlib 不可用：{exc}")
        return 1

    fig = build_figure(sweeps, corr, baseline_xy)
    from tools.thesis_plot_style import save_figure

    written = save_figure(fig, args.output_base)
    for path in written:
        try:
            rel = path.relative_to(REPO_ROOT)
        except ValueError:
            rel = path
        print(f"[sensitivity] 写出 {rel}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

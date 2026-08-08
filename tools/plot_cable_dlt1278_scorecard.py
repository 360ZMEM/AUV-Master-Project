#!/usr/bin/env python3
"""Plot a DL/T-style cable inspection scorecard from inspection_summary.json."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", type=Path, required=True, help="inspection_summary.json")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--title", default="DL/T 风格海缆巡检评分卡")
    return parser.parse_args()


def _resolve(path: Path) -> Path:
    return path if path.is_absolute() else PROJECT_ROOT / path


def _ascii_label(value: Any) -> str:
    # 图内中文化：保留原始（中文）文本，不再强转 ASCII
    return str(value)


def _status_color(summary: dict[str, Any]) -> str:
    if bool(summary.get("industrial_acceptance_pass")):
        return "tab:green"
    readiness = str(summary.get("industrial_conclusion_readiness") or "")
    if readiness == "ready":
        return "tab:orange"
    return "tab:red"


def main() -> None:
    args = parse_args()
    summary_path = _resolve(args.summary)
    output_path = _resolve(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    summary = json.loads(summary_path.read_text(encoding="utf-8"))

    try:
        import matplotlib.pyplot as plt  # type: ignore
    except Exception as exc:
        raise SystemExit(f"matplotlib unavailable: {exc}") from exc

    # 图内统一中文：注入文泉驿正黑（容器内唯一 CJK 字体），负号用 ASCII
    import os
    import matplotlib.font_manager as fm

    _zh_font = "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"
    if os.path.exists(_zh_font):
        fm.fontManager.addfont(_zh_font)
        plt.rcParams["font.family"] = fm.FontProperties(fname=_zh_font).get_name()
    else:
        plt.rcParams["font.sans-serif"] = ["WenQuanYi Zen Hei", "SimHei"] + plt.rcParams["font.sans-serif"]
    plt.rcParams["axes.unicode_minus"] = False
    plt.rcParams.update({"font.size": 12, "axes.titlesize": 14, "axes.labelsize": 12, "legend.fontsize": 10})

    score_items = summary.get("score_items") or []
    checks = summary.get("acceptance_checks") or {}
    score_labels = [_ascii_label(item.get("item")) for item in score_items] or ["无"]
    score_values = [float(item.get("score") or 0.0) for item in score_items] or [0.0]
    check_labels = list(checks.keys()) or ["无检查项"]
    check_values = [1.0 if bool(value) else 0.0 for value in checks.values()] or [0.0]

    fig = plt.figure(figsize=(12, 7))
    grid = fig.add_gridspec(2, 2, width_ratios=[1.05, 1.3], height_ratios=[1.0, 1.1])
    ax_status = fig.add_subplot(grid[0, 0])
    ax_scores = fig.add_subplot(grid[0, 1])
    ax_checks = fig.add_subplot(grid[1, 0])
    ax_metrics = fig.add_subplot(grid[1, 1])

    fig.suptitle(args.title)

    ax_status.axis("off")
    total_score = int(summary.get("total_score") or 0)
    status_lines = [
        f"就绪度：{summary.get('industrial_conclusion_readiness', '--')}",
        f"验收通过：{bool(summary.get('industrial_acceptance_pass', False))}",
        f"DL/T 风格状态：{_ascii_label(summary.get('state', '--'))}",
        f"总分：{total_score}",
        f"最差单项得分：{summary.get('worst_single_score', '--')}",
        f"有效样本：{summary.get('point_count', '--')}",
    ]
    window = summary.get("inspection_window") or {}
    if window:
        status_lines.extend(
            [
                "",
                "巡检窗口：",
                f"  原始样本：{window.get('raw_point_count', '--')}",
                f"  有效样本：{window.get('inspection_point_count', '--')}",
                f"  剔除样本：{window.get('excluded_point_count', '--')}",
            ]
        )
    ax_status.text(
        0.02,
        0.98,
        "\n".join(status_lines),
        va="top",
        ha="left",
        fontsize=11,
        bbox={"boxstyle": "round", "facecolor": _status_color(summary), "alpha": 0.14, "edgecolor": _status_color(summary)},
    )

    ax_scores.barh(score_labels, score_values, color="tab:red" if score_items else "lightgray")
    ax_scores.set_title("扣分项")
    ax_scores.set_xlabel("扣分")
    ax_scores.grid(True, axis="x", alpha=0.3)
    for y, value in enumerate(score_values):
        ax_scores.text(value + 0.2, y, f"{value:g}", va="center", fontsize=9)

    colors = ["tab:green" if value >= 0.5 else "tab:red" for value in check_values]
    ax_checks.barh(check_labels, check_values, color=colors)
    ax_checks.set_xlim(0.0, 1.0)
    ax_checks.set_title("验收检查项")
    ax_checks.set_xlabel("通过=1 / 未通过=0")
    ax_checks.grid(True, axis="x", alpha=0.3)

    ax_metrics.axis("off")
    metric_lines = [
        "关键指标：",
        f"  最大航迹偏移（m）：{summary.get('max_route_offset_m', '--')}",
        f"  平均航迹偏移（m）：{summary.get('mean_route_offset_m', '--')}",
        f"  航迹偏移 p95（m）：{summary.get('route_offset_p95_m', '--')}",
        f"  置信度 p05：{summary.get('confidence_p05', '--')}",
        f"  有效埋深比例：{summary.get('valid_burial_ratio', '--')}",
        f"  埋深 sigma 超限比例：{summary.get('burial_sigma_over_limit_ratio', '--')}",
        "",
        "已实现的 DL/T 风格项：",
    ]
    metric_lines.extend(f"  - {_ascii_label(item)}" for item in summary.get("implemented_items") or ["--"])
    ax_metrics.text(0.02, 0.98, "\n".join(metric_lines), va="top", ha="left", fontsize=10)

    fig.tight_layout()
    fig.savefig(output_path, dpi=180)
    plt.close(fig)
    print(f"[OK] wrote scorecard: {output_path}")


if __name__ == "__main__":
    main()

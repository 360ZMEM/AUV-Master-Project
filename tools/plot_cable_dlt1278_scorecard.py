#!/usr/bin/env python3
"""Plot a DL/T-style cable inspection scorecard from inspection_summary.json."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
from tools import thesis_plot_style as tps  # noqa: E402

CHECK_LABELS = {
    "min_tracking_samples": "最少跟踪样本",
    "max_route_offset": "最大航迹偏移",
    "mean_route_offset": "平均航迹偏移",
    "confidence_p05": "置信度 5% 分位",
    "valid_burial_ratio": "有效埋深比例",
    "burial_sigma_over_limit_ratio": "埋深标准差超限比例",
    "quality_flags_clear": "质量标志正常",
    "acceptance_flags_clear": "验收标志正常",
    "start_health": "启动健康状态",
}
ITEM_LABELS = {
    "route_deviation": "航迹偏移",
    "burial_profile": "埋深剖面",
    "burial_accuracy": "埋深精度",
    "tracking_confidence": "跟踪置信度",
}


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
        return tps.BASELINE_2
    readiness = str(summary.get("industrial_conclusion_readiness") or "")
    if readiness == "ready":
        return tps.BASELINE_1
    return tps.WARNING


def _format_metric(value: Any, digits: int = 3) -> str:
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return "--"


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

    tps.apply_thesis_style(layout="full")

    score_items = summary.get("score_items") or []
    checks = summary.get("acceptance_checks") or {}
    score_labels = [_ascii_label(item.get("item")) for item in score_items] or ["无"]
    score_values = [float(item.get("score") or 0.0) for item in score_items] or [0.0]
    check_labels = [CHECK_LABELS.get(key, key) for key in checks] or ["无检查项"]
    check_values = [1.0 if bool(value) else 0.0 for value in checks.values()] or [0.0]

    fig = plt.figure(
        figsize=tps.figure_size("full", height=4.75),
        constrained_layout=True,
    )
    grid = fig.add_gridspec(2, 2, width_ratios=[1.05, 1.3], height_ratios=[1.0, 1.1])
    ax_status = fig.add_subplot(grid[0, 0])
    ax_scores = fig.add_subplot(grid[0, 1])
    ax_checks = fig.add_subplot(grid[1, 0])
    ax_metrics = fig.add_subplot(grid[1, 1])

    ax_status.axis("off")
    total_score = int(summary.get("total_score") or 0)
    status_lines = [
        "就绪度："
        + ("就绪" if summary.get("industrial_conclusion_readiness") == "ready" else "未就绪"),
        "验收通过："
        + ("是" if bool(summary.get("industrial_acceptance_pass", False)) else "否"),
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
        bbox={"boxstyle": "round", "facecolor": _status_color(summary), "alpha": 0.14, "edgecolor": _status_color(summary)},
    )

    ax_scores.barh(
        score_labels,
        score_values,
        color=tps.WARNING if score_items else "#D9D9D9",
    )
    ax_scores.set_title("扣分项")
    ax_scores.set_xlabel("扣分")
    ax_scores.grid(True, axis="x", alpha=0.3)
    for y, value in enumerate(score_values):
        ax_scores.text(value + 0.2, y, f"{value:g}", va="center", fontsize=9)

    colors = [
        tps.BASELINE_2 if value >= 0.5 else tps.WARNING
        for value in check_values
    ]
    ax_checks.barh(check_labels, check_values, color=colors)
    ax_checks.set_xlim(0.0, 1.0)
    ax_checks.set_title("验收检查项")
    ax_checks.set_xlabel("通过=1 / 未通过=0")
    ax_checks.grid(True, axis="x", alpha=0.3)

    ax_metrics.axis("off")
    metric_lines = [
        "关键指标：",
        f"  最大航迹偏移 (m)：{_format_metric(summary.get('max_route_offset_m'))}",
        f"  平均航迹偏移 (m)：{_format_metric(summary.get('mean_route_offset_m'))}",
        f"  航迹偏移 95% 分位 (m)：{_format_metric(summary.get('route_offset_p95_m'))}",
        f"  置信度 5% 分位：{_format_metric(summary.get('confidence_p05'))}",
        f"  有效埋深比例：{_format_metric(summary.get('valid_burial_ratio'))}",
        "  埋深标准差超限比例："
        + _format_metric(summary.get("burial_sigma_over_limit_ratio")),
        "",
        "已实现的 DL/T 风格项：",
    ]
    metric_lines.extend(
        f"  - {ITEM_LABELS.get(str(item), _ascii_label(item))}"
        for item in summary.get("implemented_items") or ["--"]
    )
    ax_metrics.text(0.02, 0.98, "\n".join(metric_lines), va="top", ha="left")

    tps.save_figure(fig, output_path.with_suffix(""))
    plt.close(fig)
    print(f"[OK] wrote scorecard: {output_path}")


if __name__ == "__main__":
    main()

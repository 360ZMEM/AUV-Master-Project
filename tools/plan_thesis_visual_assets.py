#!/usr/bin/env python3
"""Write a thesis visual asset closure plan for static figures and dynamic GIFs."""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
import re


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MARKDOWN_IMAGE_RE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)", re.IGNORECASE)
BARE_IMAGE_RE = re.compile(r"(?<![\w/.-])([A-Za-z0-9_./-]+\.(?:png|jpg|jpeg|svg|gif|pdf))", re.IGNORECASE)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--paper-dir", type=Path, default=Path("docs/thesis/paper"))
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(".trae/documents/论文图像与动态轨迹收口计划.md"),
    )
    parser.add_argument(
        "--latest-cable-report",
        type=Path,
        default=Path("results/cable_ops_report/acceptance_zigzag_1p5_window30_20260705_235221"),
    )
    return parser.parse_args()


def _resolve(path: Path) -> Path:
    return path if path.is_absolute() else PROJECT_ROOT / path


def _image_refs(path: Path) -> list[str]:
    refs: list[str] = []
    text = path.read_text(encoding="utf-8")
    markdown_spans: list[tuple[int, int]] = []
    for match in MARKDOWN_IMAGE_RE.finditer(text):
        ref = match.group(1)
        if ref:
            refs.append(ref.strip())
            markdown_spans.append(match.span())
    masked = list(text)
    for start, end in markdown_spans:
        masked[start:end] = " " * (end - start)
    for match in BARE_IMAGE_RE.finditer("".join(masked)):
        ref = match.group(1)
        if ref:
            refs.append(ref.strip())
    return refs


def _list_files(root: Path, patterns: tuple[str, ...]) -> list[Path]:
    files: list[Path] = []
    if not root.exists():
        return files
    for pattern in patterns:
        files.extend(root.rglob(pattern))
    return sorted(path for path in files if path.is_file())


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def main() -> None:
    args = parse_args()
    paper_dir = _resolve(args.paper_dir)
    output = _resolve(args.output)
    latest_cable_report = _resolve(args.latest_cable_report)
    output.parent.mkdir(parents=True, exist_ok=True)

    paper_files = sorted(paper_dir.glob("*.md"))
    ref_map = {path: _image_refs(path) for path in paper_files}
    static_assets = _list_files(PROJECT_ROOT / "docs/thesis/figures", ("*.png", "*.svg", "*.pdf"))
    cable_report_assets = _list_files(latest_cable_report, ("*.png", "*.csv", "*.json", "*.md"))
    visual_feedback_assets = _list_files(PROJECT_ROOT / "results/visual_feedback", ("*.png", "*.json"))

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines: list[str] = [
        "# 论文图像、动态轨迹与视频产物收口计划",
        "",
        f"- 生成时间：`{now}`",
        f"- paper 目录：`{_rel(paper_dir)}`",
        f"- 当前电缆验收报告目录：`{_rel(latest_cable_report)}`",
        "",
        "## 当前 Markdown 图片引用盘点",
        "",
        "| 文件 | 图片/动态图引用数 | 当前引用 |",
        "|---|---:|---|",
    ]
    for path in paper_files:
        refs = ref_map[path]
        ref_text = "<br>".join(f"`{ref}`" for ref in refs[:8]) if refs else "无"
        if len(refs) > 8:
            ref_text += "<br>..."
        lines.append(f"| `{_rel(path)}` | {len(refs)} | {ref_text} |")

    lines.extend(
        [
            "",
            "## 本轮工业收口图像需求",
            "",
            "这些图像用于证明第一阶段已经从单点可运行转向工业验收闭环。优先级从 P0 到 P2。",
            "",
            "| 优先级 | 建议文件名 | 来源 | 目的 | 当前处理方式 |",
            "|---|---|---|---|---|",
            "| P0 | `cable_acceptance_multirun_summary.png` | 3 次 fresh ready/pass run 聚合 | 证明工业验收不是单次偶然 | 待多 run 后生成 |",
            "| P0 | `cable_dlt1278_score_breakdown.png` | `inspection_summary.json` | 展示 DL/T 风格扣分项、总分、状态 | `tools/plot_cable_dlt1278_scorecard.py` |",
            "| P0 | `cable_tracking_dynamic.gif` | `tracking.jsonl` | 展示电缆跟踪、埋深、置信度随路由推进 | `tools/make_cable_tracking_gif.py` |",
            "| P0 | `cable_operator_map.png` | `operator_view/01_operator_cable_map.png` | 面向运维人员的电缆地图 | 已有 `plot_cable_operator_products.py` |",
            "| P0 | `cable_burial_strip.png` | `operator_view/02_operator_burial_strip.png` | 埋深与 sigma 验收带 | 已有 `plot_cable_operator_products.py` |",
            "| P1 | `zigzag_probe_feasibility.png` | zig-zag sweep report | 说明 1.5 m 幅值在动力学约束内 | 已有 fullflow 图，需论文重命名引用 |",
            "| P1 | `magnetic_quality_timeline.png` | `tracking.jsonl` | 说明 magnetic SNR/confidence 进入工业质量口径 | 扩展静态脚本 |",
            "| P1 | `runtime_topic_evidence.png` | rosbag topic count / summary | 证明 DL/T runtime topic 已发布和录包 | 表格或终端证据图 |",
            "",
            "## 旧图动态化计划",
            "",
            "旧图不是全部替换为 GIF，而是保留静态论文图，同时为答辩、演示和电子版补动态版本。",
            "",
            "| 原静态图类别 | 当前位置 | 建议动态图 | 用途 | 本次是否实施 |",
            "|---|---|---|---|---|",
            "| Terrain 3D / trajectory | `docs/thesis/figures/terrain_following/terrain_3d_pid_terrain_trajectory.png` | `terrain_following_trajectory.gif` | 展示近底跟随随时间推进 | 否，写入计划 |",
            "| 定位轨迹 XY | `results/localization/*/trajectory_xy.png` | `localization_error_evolution.gif` | 展示估计轨迹与误差收敛 | 否，写入计划 |",
            "| 磁杆臂标定误差 | `results/mag_extrinsics/*/*.png` | `mag_extrinsics_convergence.gif` | 展示标定残差下降 | 否，写入计划 |",
            "| 电缆跟踪 XY | `results/cable_ops_report/*/04_cable_track_xy.png` | `cable_tracking_dynamic.gif` | 展示巡检路由推进和质量状态 | 是，新增脚本 |",
            "| Foxglove 看板截图 | `results/visual_feedback/foxglove/*.png` | `foxglove_acceptance_walkthrough.mp4` | 展示 AI 闭环调 layout 和看板 | 本次不实施 |",
            "| PySide6 上位机截图 | `results/visual_feedback/gui_pyside6_*/*.png` | `console_operator_walkthrough.mp4` | 展示操作员面板、DL/T 卡片和报告入口 | 本次不实施 |",
            "",
            "## `docs/thesis/paper` 建议补图位置",
            "",
            "| 章节 | 需要补的图/动态图 | 插入目的 |",
            "|---|---|---|",
            "| 第 2 章系统设计 | 系统运行链路图、ROS2 topic 拓扑、AUV-Master-Mag API 边界图 | 说明主仓与专用磁探测仓库分工 |",
            "| 第 3 章状态估计 | ES-EKF 误差曲线、NIS 一致性图、磁杆臂标定残差图 | 支撑估计与标定有效性 |",
            "| 第 4 章决策控制 | zig-zag 幅值可行域、航向偏置/转弯半径动态图 | 说明探针动作不是玩具轨迹 |",
            "| 第 5 章实验讨论 | 多 run 验收聚合图、DL/T 扣分图、电缆动态轨迹 GIF、运维四联图 | 支撑工业验收结论 |",
            "| 第 5 章迁移边界 | Foxglove/上位机截图或后续视频帧 | 说明工程可运维性，但不冒充硬件实测 |",
            "",
            "## 现有可复用资产",
            "",
            f"- `docs/thesis/figures` 下静态图数量：`{len(static_assets)}`",
            f"- 当前电缆报告目录可复用文件数量：`{len(cable_report_assets)}`",
            f"- 可视化反馈截图/探针资产数量：`{len(visual_feedback_assets)}`",
            "",
            "当前电缆报告目录关键资产：",
            "",
        ]
    )
    for path in cable_report_assets[:40]:
        lines.append(f"- `{_rel(path)}`")

    lines.extend(
        [
            "",
            "## 后续视频生成计划（本次不实施）",
            "",
            "- Foxglove 视频：基于 `tools/foxglove_public_loop.py`、IndexedDB layout 注入和浏览器截图，生成 `foxglove_acceptance_walkthrough.mp4`。",
            "- 上位机视频：基于 `tools/gui_console_loop.py` / `tools/gui_console_dlt_probe.py`，录制 PySide6 操作员工作流。",
            "- 视频产物只用于答辩和演示材料；论文正文优先引用静态图，电子附录可引用 GIF。",
            "",
            "## 下一次文档收口边界",
            "",
            "- 对 `docs/thesis/`，尤其 `docs/thesis/paper/` 做彻底正文收口。",
            "- 统一 Markdown 图片引用为相对路径。",
            "- 对每张图补图题、数据来源、样本量和证据边界。",
            "- 区分论文正文图、附录图、答辩视频/GIF，不混用证据等级。",
            "",
            "## 生成命令示例",
            "",
            "```bash",
            "python3 tools/make_cable_tracking_gif.py \\",
            "  --tracking-jsonl results/cable_ops_report/acceptance_zigzag_1p5_window30_20260705_235221/tracking.jsonl \\",
            "  --output results/cable_ops_report/acceptance_zigzag_1p5_window30_20260705_235221/cable_tracking_dynamic.gif \\",
            "  --last-frame-png results/cable_ops_report/acceptance_zigzag_1p5_window30_20260705_235221/cable_tracking_dynamic_last_frame.png",
            "",
            "python3 tools/plan_thesis_visual_assets.py",
            "```",
            "",
        ]
    )

    output.write_text("\n".join(lines), encoding="utf-8")
    print(f"[OK] wrote thesis visual plan: {output}")


if __name__ == "__main__":
    main()

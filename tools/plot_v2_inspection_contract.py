#!/usr/bin/env python3
"""Render inspection process and model-mismatch capability evidence."""
from pathlib import Path
import csv
import json
import sys
import shutil
import hashlib

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import thesis_plot_style as style

MAG = ROOT / "AUV-Master-Mag"
DATA = MAG / "results/v2/inspection_contract_validation_20260926"
OUT = MAG / "docs/v2/figures"


def read(case):
    with (DATA / f"{case}_seed_101.csv").open() as stream:
        return list(csv.DictReader(stream))


def main():
    style.apply_thesis_style()
    rows = read("magnetic_dropout")
    values = lambda key: np.array([float(row[key]) for row in rows])
    t, x, y = values("time_s"), values("x_m"), values("y_m")
    modes = np.array([row["mode"] for row in rows])
    valid = np.array([row["lateral_valid"] == "True" for row in rows])
    colors = {"search": style.NEUTRAL, "confirm": style.BASELINE_1,
              "reacquire": style.BASELINE_3, "track": style.PROPOSED, "hold": style.WARNING}
    labels = {"search": "先验搜索", "confirm": "横切确认／更新", "reacquire": "重捕",
              "track": "位置引导", "hold": "输入故障保持"}
    fig = plt.figure(figsize=style.figure_size(height=6.9), constrained_layout=True)
    grid = fig.add_gridspec(3, 1, height_ratios=[1.45, 1, .65])
    ax = fig.add_subplot(grid[0])
    ax.plot([0,60], [0,0], "--", color=style.NEUTRAL, label="先验路由")
    ax.plot([0,60], [6,6], "-", color=style.REFERENCE, label="电缆真值")
    for mode in colors:
        mask = modes == mode
        if mask.any():
            ax.scatter(x[mask], y[mask], s=3, color=colors[mode], label=labels[mode], rasterized=True)
    ax.scatter([x[0], x[-1]], [y[0], y[-1]], s=35, marker="x", color=style.REFERENCE)
    ax.set(xlabel="沿先验方向 / m", ylabel="横向位置 / m", title="(a) 搜索、主动确认、观测更新与巡检轨迹")
    ax.legend(ncol=3, fontsize=7, loc="upper center", bbox_to_anchor=(.5, -.24))
    ax.set_aspect("equal", adjustable="datalim")
    ax = fig.add_subplot(grid[1])
    ax.plot(t, y, color=style.NEUTRAL, label="AUV 横向位置", linewidth=1)
    ax.plot(t, values("true_cable_y_m"), color=style.REFERENCE, label="电缆横向真值")
    estimate = values("cable_estimate_y_m")
    ax.plot(t, np.where(valid, estimate, np.nan), color=style.PROPOSED, label="获准用于跟踪的中心估计")
    hold_times = t[modes == "hold"]
    ax.axvspan(hold_times.min(), hold_times.max(), alpha=.16, color=style.WARNING)
    ax.set(xlabel="任务时间 / s", ylabel="横向位置 / m", title="(b) 故障与观测过期期间不延续定位授权")
    ax.legend(fontsize=7, ncol=3, loc="upper center", bbox_to_anchor=(.5, -.27))
    ax = fig.add_subplot(grid[2])
    ax.step(t, valid.astype(int), where="post", color=style.PROPOSED, label="横向定位有效")
    ax.plot(t, np.zeros_like(t), color=style.WARNING, linestyle="--", label="未标定埋深：始终不发布")
    ax.set(xlabel="任务时间 / s", ylabel="输出许可", ylim=(-.15,1.25), yticks=[0,1],
           title="(c) 两类输出独立门控（不是两条深度数值曲线）")
    ax.legend(fontsize=7, ncol=2, loc="upper center", bbox_to_anchor=(.5, -.4))
    style.save_figure(fig, OUT / "15_inspection_contract_process")
    plt.close(fig)

    fig, axes = plt.subplots(2, 2, figsize=style.figure_size(height=5.5), constrained_layout=True)
    xx = np.linspace(-12,12,501)
    for index, p in enumerate((.5,.7,1.)):
        line_style = style.line_style(index)
        line_style["marker"] = ""
        axes[0,0].plot(xx, (1 + (xx/3)**2)**(-p), label=f"p = {p:g}", **line_style)
    axes[0,0].axhline(.5, color=style.NEUTRAL, linestyle="--", linewidth=.8)
    axes[0,0].axvline(0, color=style.NEUTRAL, linestyle=":", linewidth=.8)
    axes[0,0].set(xlabel="距电缆中心 / m", ylabel="归一化包络", title="(a) 场形改变宽度，孤立对称中心不变")
    axes[0,0].legend(fontsize=7)
    cases = ("dipole", "wire", "intermediate", "map_slope", "magnetic_dropout", "navigation_dropout")
    names = ("偶极", "直导线", "中间形", "方向偏差", "磁故障", "导航故障")
    before = json.loads((MAG / "results/v2/inspection_closed_loop_transverse/summary.json").read_text())["runs"]
    after = json.loads((MAG / "results/v2/inspection_closed_loop_flank_follow/summary.json").read_text())["runs"]
    locations = np.arange(6)
    for offset, group, label, color in ((-.18,before,"固定检测点扩幅",style.BASELINE_1),(.18,after,"有界侧翼移心",style.PROPOSED)):
        axes[0,1].bar(locations+offset, [next(row["first_track_s"] for row in group if row["case"]==c) for c in cases], .35, label=label,color=color)
    axes[0,1].set_xticks(locations, names, rotation=30, ha="right")
    axes[0,1].set(ylabel="首次确认时间 / s", title="(b) 相同种子 100 的流程修复对照")
    axes[0,1].legend(fontsize=7)
    runs = json.loads((DATA / "summary.json").read_text())["runs"]
    for i, case in enumerate(cases):
        group = [r for r in runs if r["case"]==case]
        axes[1,0].scatter(np.full(len(group),i)-.1,[r["tracking_mae_m"] for r in group],s=16,color=style.PROPOSED,label="单次 MAE" if i==0 else None)
        axes[1,0].scatter(np.full(len(group),i)+.1,[r["tracking_p95_m"] for r in group],s=18,marker="x",color=style.BASELINE_1,label="单次 P95" if i==0 else None)
    axes[1,0].set_xticks(locations, names, rotation=30, ha="right")
    axes[1,0].set(ylabel="前向巡检段横向误差 / m", title="(c) 30 次任务的位置跟踪误差")
    axes[1,0].legend(fontsize=7)
    axes[1,1].axis("off")
    axes[1,1].set_title("(d) 完成与拒绝分别验收")
    table = axes[1,1].table(cellText=[
        ["正常／短时故障", "30 / 30", "0 / 30"],
        ["无磁源", "0 / 5", "0 / 5"],
        ["持续坏数据", "0 / 5", "0 / 5"],
    ], colLabels=["任务条件", "完成", "未标定深度发布"], bbox=[0,.25,1,.55],cellLoc="center",colWidths=[.42,.23,.35])
    table.auto_set_font_size(False); table.set_fontsize(7); table.scale(1,1.8)
    axes[1,1].text(.5,.09,"种子 101–105；运动学闭环\n负例不要求完成，要求不误报和持续响应",ha="center",va="center",fontsize=8,transform=axes[1,1].transAxes)
    style.save_figure(fig, OUT / "16_inspection_contract_insight")
    plt.close(fig)
    publication = MAG / "docs/v2/publication/fwhm_v2_experiment_results"
    artifacts = []
    for stem in ("15_inspection_contract_process", "16_inspection_contract_insight"):
        for ext in ("png", "pdf"):
            source = OUT / f"{stem}.{ext}"
            artifacts.append(source)
            for destination in (publication / "figures", ROOT / "docs/thesis/figures/experiments/fwhm_v2"):
                destination.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination / source.name)
                artifacts.append(destination / source.name)
    inputs = [Path(__file__), ROOT / "tools/thesis_plot_style.py", DATA / "summary.json",
              DATA / "magnetic_dropout_seed_101.csv",
              MAG / "results/v2/inspection_closed_loop_transverse/summary.json",
              MAG / "results/v2/inspection_closed_loop_flank_follow/summary.json"]
    manifest = {"scope": "inspection supplement only; historical figures and results retained",
                "files": [{"path": str(path.relative_to(ROOT)),
                           "sha256": hashlib.sha256(path.read_bytes()).hexdigest()} for path in inputs + artifacts]}
    (publication / "inspection_publication_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    main()

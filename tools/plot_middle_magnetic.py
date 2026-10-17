#!/usr/bin/env python3
"""Redraw four middle-defense figures from frozen magnetic experiment data.

Run from any directory: python3 tools/plot_middle_magnetic.py
Only middle/figures assets and their dedicated provenance JSON are written.
The 15 cm PDF canvas is deliberately not cropped: at 15 cm inclusion width,
every visible text item is at least 9 pt. No experiments are executed.
"""
from __future__ import annotations

import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.text import Text
from matplotlib.ticker import FixedLocator, FormatStrFormatter
import numpy as np

from thesis_plot_style import (
    apply_thesis_style, PROPOSED, BASELINE_1, BASELINE_2, BASELINE_3,
    REFERENCE, WARNING, NEUTRAL, FANDOL_SONG_REGULAR,
)

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "AUV-Master-Mag/results/v2"
OUT = ROOT / "thuthesis/middle/figures"
RECORD = ROOT / "docs/middle-defense/middle-magnetic-figures.json"
WIDTH = 15 / 2.54
SOURCES: dict[str, str] = {}
ASSETS: list[dict] = []
METHODS = ["explicit_fwhm", "free_profile_fit", "calibrated_amplitude", "absolute_half"]
METHOD_LABELS = ["显式空间 FWHM", "自由幅值拟合", "标定幅值反演", "未扣背景半高"]
COLORS = [PROPOSED, BASELINE_2, BASELINE_1, WARNING]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def relative(path: Path) -> str:
    return str(path.relative_to(ROOT))


def remember(path: Path) -> Path:
    SOURCES[relative(path)] = sha(path)
    return path


def read(path: Path) -> list[dict]:
    with remember(path).open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def json_read(path: Path):
    return json.loads(remember(path).read_text(encoding="utf-8"))


def values(rows: list[dict], key: str) -> np.ndarray:
    return np.array([float(row[key]) if row.get(key) not in (None, "") else np.nan for row in rows])


def checked_summary(directory: Path, method_key: str) -> tuple[dict, list[dict]]:
    """Recompute all displayed aggregate quantities from the per-run CSV."""
    summary = json_read(directory / "summary.json")["scenarios"]
    rows = read(directory / "per_run.csv")
    groups = defaultdict(list)
    for row in rows:
        groups[row["scenario"], row[method_key]].append(row)
    for (scenario, method), group in groups.items():
        expected = summary[scenario][method]
        valid = [row for row in group if int(row["valid"])]
        assert len(group) == expected["runs"] == 200
        error = values(valid, "abs_error_m")
        actual = {"valid_rate": len(valid) / len(group),
                  "large_error_publish_rate": float(np.count_nonzero(error > .5)) / len(group)}
        if len(error):
            mae_key = "mae_m_published" if method_key == "method" else "published_mae_m"
            actual[mae_key] = float(np.mean(error))
        for key, value in actual.items():
            assert np.isclose(value, expected[key], atol=1e-12), (scenario, method, key)
    return summary, rows


def save(fig, name: str, *, source_figure: str, adaptation: str, scope: str):
    # Override thesis helper's tight bbox: cropping would change final font size.
    fig.canvas.draw()
    text = [obj for obj in fig.findobj(Text) if obj.get_visible() and obj.get_text()]
    minimum = min(obj.get_fontsize() for obj in text)
    assert minimum >= 9, minimum
    renderer = fig.canvas.get_renderer()
    bounds = fig.bbox
    outside = []
    for obj in text:
        box = obj.get_window_extent(renderer)
        if box.x0 < bounds.x0 - 1 or box.y0 < bounds.y0 - 1 or box.x1 > bounds.x1 + 1 or box.y1 > bounds.y1 + 1:
            outside.append(obj.get_text())
    assert not outside, f"Text outside fixed canvas: {outside}"
    output = {}
    for ext in ("pdf", "png"):
        path = OUT / f"{name}.{ext}"
        kwargs = {"metadata": {"CreationDate": None, "ModDate": None}} if ext == "pdf" else {}
        fig.savefig(path, dpi=300, bbox_inches=None, **kwargs)
        output[relative(path)] = sha(path)
    ASSETS.append(dict(name=name, original_figure=source_figure,
                       original_figure_sha256=sha(ROOT / source_figure),
                       adaptation=adaptation, scope=scope,
                       width_cm=15, height_cm=float(fig.get_figheight() * 2.54),
                       minimum_text_pt=minimum, canvas_bounds_check="PASS",
                       outputs=output))
    plt.close(fig)


def stability():
    summary, rows = checked_summary(RESULTS / "stability_comparison", "method")
    scenarios = ["nominal", "gain", "background", "noise", "scan_offset", "combined"]
    labels = ["标称", "增益", "背景", "噪声", "偏心", "组合"]
    fig, axes = plt.subplots(2, 2, figsize=(WIDTH, 4.95))
    fig.subplots_adjust(left=.105, right=.975, bottom=.10, top=.82, hspace=.62, wspace=.40)
    x = np.arange(6)
    for index, (method, label, color) in enumerate(zip(METHODS, METHOD_LABELS, COLORS)):
        axes[0, 0].bar(x + (index - 1.5) * .19,
                       [summary[s][method]["mae_m_published"] for s in scenarios],
                       .19, color=color, edgecolor=REFERENCE, linewidth=.4, label=label)
        axes[0, 1].plot(x, [summary[s][method]["valid_rate"] for s in scenarios],
                        color=color, marker=["o", "s", "^", "D"][index],
                        ls=["-", "--", "-.", ":"][index], lw=1.2, ms=3.5)
        axes[1, 0].bar(np.arange(2) + (index - 1.5) * .19,
                       [summary[s][method]["large_error_publish_rate"] for s in ["combined", "model_mismatch"]],
                       .19, color=color, edgecolor=REFERENCE, linewidth=.4)
    axes[0, 0].set_yscale("log")
    axes[0, 0].yaxis.set_major_locator(FixedLocator([.01, .1, 1]))
    axes[0, 0].yaxis.set_major_formatter(FormatStrFormatter("%g"))
    axes[0, 0].set_ylabel("发布 MAE / m")
    axes[0, 0].set_title("(a) 条件精度（对数轴）", loc="left")
    axes[0, 1].set_ylim(.60, 1.03)
    axes[0, 1].set_ylabel("有效发布率")
    axes[0, 1].set_title("(b) 有效性与拒绝", loc="left")
    for axis in axes[0]:
        axis.set_xticks(x)
        axis.set_xticklabels(labels)
    axes[1, 0].set_xticks([0, 1])
    axes[1, 0].set_xticklabels(["组合扰动", "场形失配"])
    axes[1, 0].set_ylim(0, 1.08)
    axes[1, 0].set_ylabel("大误差发布比例")
    axes[1, 0].set_title("(c) 误差 > 0.5 m 仍发布", loc="left")
    distributions = [values([r for r in rows if r["scenario"] == "combined" and
                             r["method"] == method and int(r["valid"])], "error_m") for method in METHODS]
    box = axes[1, 1].boxplot(distributions, labels=["FWHM", "拟合", "幅值", "未扣\n背景"],
                            showfliers=False, patch_artist=True, widths=.6)
    for patch, color in zip(box["boxes"], COLORS):
        patch.set_facecolor(color)
        patch.set_alpha(.75)
    axes[1, 1].axhline(0, color=REFERENCE, lw=.8)
    axes[1, 1].set_ylabel("组合扰动误差 / m")
    axes[1, 1].set_title("(d) 已发布误差分布", loc="left")
    handles, labels = axes[0, 0].get_legend_handles_labels()
    fig.legend(handles, labels, ncol=2, loc="upper center", bbox_to_anchor=(.52, .995), frameon=False)
    save(fig, "magnetic_stability", source_figure="docs/thesis/figures/experiments/fwhm_v2/11_fwhm_stability_comparison.pdf",
         adaptation="保留四面板；缩短类别标签与标题，图例改为两行，全部文字至少9pt。箱线图与原图一致不显示离群点；风险面板仍计入全部大误差。",
         scope="5600次方法运行，7场景×4方法×200；MAE与箱线图仅发布结果，发布率与大误差发布率分母为全部样本。")


def shape_guard():
    summary, _ = checked_summary(RESULTS / "shape_guard_validation", "mode")
    fig, axes = plt.subplots(2, 1, figsize=(WIDTH, 4.1))
    fig.subplots_adjust(left=.115, right=.97, bottom=.12, top=.84, hspace=.66)
    groups = [[("model_mismatch", "直导线误声明为偶极"), ("dipole_as_wire", "偶极误声明为直导线")],
              [("nominal", "标称\n偶极"), ("gain", "增益"), ("background", "背景"),
               ("matched_wire", "正确\n直导线"), ("noise", "噪声"),
               ("scan_offset", "扫描\n偏心"), ("combined", "组合\n扰动")]]
    for axis, group, metric in zip(axes, groups, ["large_error_publish_rate", "valid_rate"]):
        x = np.arange(len(group))
        for index, (mode, label, color) in enumerate([
                ("before_guard", "原质量门", WARNING), ("with_guard", "场形判别门", PROPOSED)]):
            heights = [summary[key][mode][metric] for key, _ in group]
            axis.bar(x + (index - .5) * .30, heights, .30,
                     color=color, edgecolor=REFERENCE, linewidth=.5, label=label)
            if axis is axes[0]:
                for xi, yi in zip(x + (index - .5) * .30, heights):
                    axis.text(xi, yi + .035, f"{yi:.0%}", ha="center", va="bottom")
        axis.set_xticks(x)
        axis.set_xticklabels([label for _, label in group])
        axis.set_ylim(0, 1.21 if axis is axes[0] else 1.08)
        axis.set_yticks([0, .5, 1])
    axes[0].set_title("(a) 双向失配：大误差发布风险", loc="left")
    axes[0].set_ylabel("大误差发布比例")
    axes[1].set_title("(b) 正确声明模型：发布率与拒绝代价", loc="left")
    axes[1].set_ylabel("有效发布率")
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, ncol=2, loc="upper center", bbox_to_anchor=(.5, .995), frameon=False)
    save(fig, "magnetic_shape_guard", source_figure="docs/thesis/figures/experiments/fwhm_v2/13_shape_guard_held_out_validation.pdf",
         adaptation="由四面板精简为两面板：合并正确模型发布率，省略残差散点；完整保留双向失配和全部7组正确声明场景，不改变样本或统计口径。",
         scope="独立种子200–399，9场景×2质量门×200=3600次方法运行；双向失配对应400条唯一剖面。")


def mission_process():
    directory = RESULTS / "inspection_simulation_closure_20260928"
    def trace(case, seed):
        sub = "native_pvs" if seed == 101 else "native_seed102_103"
        return read(directory / sub / f"{case}_seed_{seed}.csv")
    fig = plt.figure(figsize=(WIDTH, 5.0))
    grid = fig.add_gridspec(2, 2, height_ratios=[1.13, 1],
                           left=.115, right=.98, bottom=.15, top=.85, hspace=.84, wspace=.52)
    map_ax = fig.add_subplot(grid[0, :])
    center_ax = fig.add_subplot(grid[1, 0])
    error_ax = fig.add_subplot(grid[1, 1])
    rows = trace("wire", 101)
    x, y = values(rows, "x_m"), values(rows, "y_m")
    mode = np.array([row["mode"] for row in rows])
    for mask, color, label in [
            (mode == "search", BASELINE_1, "先验搜索"),
            (mode == "confirm", PROPOSED, "主动横切"),
            ((mode == "track") & (x < 5), BASELINE_3, "前向接入"),
            ((mode == "track") & (x >= 5), BASELINE_2, "沿缆巡检")]:
        map_ax.plot(np.where(mask, x, np.nan), np.where(mask, y, np.nan), color=color, lw=1.5, label=label)
    map_ax.axhline(6, color=REFERENCE, lw=.8)
    map_ax.plot([0, 80], [0, 0], color=REFERENCE, ls="--", lw=.8)
    map_ax.axvspan(5, 75, color=BASELINE_2, alpha=.08)
    map_ax.text(-255, 7.6, "真实电缆", color=REFERENCE)
    map_ax.text(24, -5.4, "先验线", color=REFERENCE)
    map_ax.scatter([x[0]], [y[0]], c=REFERENCE, s=20, zorder=5)
    map_ax.scatter([x[-1]], [y[-1]], c=REFERENCE, marker="s", s=20, zorder=5)
    none = trace("no_source", 101)[-1]
    nx, ny = float(none["x_m"]), float(none["y_m"])
    map_ax.scatter([nx], [ny], c=WARNING, marker="x", s=35, zorder=5)
    map_ax.annotate("无源：拒绝跟踪", xy=(nx, ny), xytext=(-167, 22),
                    arrowprops={"arrowstyle": "-", "lw": .7}, ha="center")
    map_ax.set(xlim=(-265, 90), ylim=(-22, 29), xlabel="沿缆方向位置 / m", ylabel="横向位置 / m")
    map_ax.set_title("(a) 搜索、主动横切与沿缆接入", loc="left")
    map_ax.set_xticks([-250, -150, -50, 50])
    handles, labels = map_ax.get_legend_handles_labels()
    fig.legend(handles, labels, ncol=4, loc="upper center", bbox_to_anchor=(.53, .995),
               frameon=False, handlelength=1.4, columnspacing=1.1)
    center_ax.axhline(6, color=REFERENCE, lw=.8, label="真实中心")
    for case, color, ls, label in [("wire", PROPOSED, "-", "直导线"),
                                   ("dipole", BASELINE_1, "--", "偶极")]:
        released = [r for r in trace(case, 101) if r["lateral_valid"] == "True"]
        center_ax.plot(values(released, "time_s"), values(released, "estimated_cable_y_m"),
                       color=color, ls=ls, lw=1.25, label=label)
        for seed in (101, 102, 103):
            core = [r for r in trace(case, seed) if r["mode"] == "track" and float(r["x_m"]) >= 0]
            error_ax.plot(values(core, "x_m"), np.abs(values(core, "y_m") - 6),
                          color=color, ls=ls, lw=1.2 if seed == 101 else .7,
                          alpha=1 if seed == 101 else .45, label=label if seed == 101 else None)
    center_ax.set_title("(b) 发布的横向中心", loc="left")
    center_ax.set(xlabel="仿真时间 / s", ylabel="估计中心 / m", ylim=(5.96, 6.04))
    center_ax.set_yticks([5.96, 6, 6.04])
    center_ax.yaxis.set_major_formatter(FormatStrFormatter("%.2f"))
    handles, labels = center_ax.get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", bbox_to_anchor=(.54, .002),
               ncol=3, frameon=False, handlelength=1.5)
    error_ax.axvspan(5, 75, color=BASELINE_2, alpha=.08)
    error_ax.axhline(2, color=WARNING, lw=.8, ls=":")
    error_ax.text(39, 2.07, "最大横偏门 2 m", ha="center")
    error_ax.set_title("(c) 真实载体横偏", loc="left")
    error_ax.set(xlim=(0, 80), ylim=(0, 2.45), xlabel="沿缆位置 / m", ylabel="绝对横偏 / m")
    error_ax.set_xticks([0, 40, 80])
    save(fig, "magnetic_mission_process", source_figure="docs/thesis/figures/experiments/fwhm_v2/71_current_magnetic_simulation_closure.pdf",
         adaptation="完整过程地图改为通栏，其下保留横向中心与真实横偏两图；去掉图内重复埋深说明并移至图注。未按业务阶段过滤核心误差。",
         scope="地图、中心和无源终点使用种子101；横偏包含两场形×种子101/102/103的全部跟踪样本；核心[5,75]m。")


def supervision():
    directory = RESULTS / "defense_robustness_20260929/05_held_out"
    plan = json_read(directory / "plan.json")
    manifest = json_read(directory / "manifest.json")
    assert plan["split"] == "held_out"
    assert sha(directory / "plan.json") == manifest["plan_sha256"]
    summary = json_read(directory / "summary.json")
    selected = {(r["case"], r["method"]): r for r in summary if r["seed"] == 501}
    fig, axes = plt.subplots(1, 2, figsize=(WIDTH, 3.65))
    fig.subplots_adjust(left=.105, right=.98, bottom=.31, top=.88, wspace=.43)
    old_end = None
    for method, color, ls, label in [("legacy", BASELINE_1, "--", "旧链：20 m 接入"),
                                     ("supervised", PROPOSED, "-", "监督：5 m 接入")]:
        run = selected["steady_minus", method]
        path = directory / run["trace"]
        assert sha(path) == run["trace_sha256"]
        core = [r for r in read(path) if r["mode"] == "track" and 5 <= float(r["x_m"]) <= 75]
        axes[0].plot(values(core, "x_m"), values(core, "true_offset_m"), color=color, ls=ls, lw=1.3, label=label)
        if method == "legacy":
            old_end = float(max(values(core, "x_m")))
    axes[0].axvspan(old_end, 75, color=NEUTRAL, alpha=.14)
    axes[0].text((old_end + 75) / 2, .12, "旧链未覆盖", rotation=90, ha="center", va="bottom")
    axes[0].axhline(2, color=WARNING, lw=.8, ls=":", label="最大横偏门 2 m")
    axes[0].set(xlim=(5, 75), ylim=(0, 2.25), xlabel="沿缆位置 / m", ylabel="真实横偏 / m")
    axes[0].set_title("(a) 反向小流：接入收益", loc="left")
    run = selected["fused_neighbor", "legacy"]
    # Verify the archived CSV backing all three displayed summary numbers.
    path = directory / run["trace"]
    assert sha(path) == run["trace_sha256"]
    rows = read(path)
    core = [r for r in rows if r["mode"] == "track" and 5 <= float(r["x_m"]) <= 75]
    assert np.isclose(np.mean(values(core, "true_offset_m")), run["core_true_mae_m"])
    assert np.isclose(max(values(core, "true_offset_m")), run["core_true_max_m"])
    released = [r for r in rows if r["lateral_valid"] == "True"]
    assert np.isclose(max(np.abs(values(released, "estimated_cable_y_m") -
                                values(released, "true_target_y_m"))),
                      run["released_center_max_error_m"])
    errors = np.array([run["released_center_max_error_m"], run["core_true_mae_m"], run["core_true_max_m"]])
    ratios = errors / [.5, 1, 2]
    axes[1].bar(range(3), ratios, color=[WARNING, BASELINE_1, NEUTRAL], width=.55)
    for index, value in enumerate(ratios):
        axes[1].text(index, value + .07, f"{errors[index]:.3f} m", ha="center", va="bottom")
    axes[1].axhline(1, color=REFERENCE, lw=.9, ls=":")
    axes[1].set_ylim(0, 2.45)
    axes[1].set_xticks(range(3))
    axes[1].set_xticklabels(["中心最大\n门 0.5 m", "载体 MAE\n门 1 m", "载体最大\n门 2 m"])
    axes[1].set_ylabel("误差 / 对应阈值")
    axes[1].set_title("(b) 融合邻源：错误几何", loc="left")
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", bbox_to_anchor=(.52, .025), ncol=2, frameon=False)
    save(fig, "magnetic_supervision", source_figure="docs/thesis/figures/experiments/fwhm_v2/77_defense_robustness_thesis_summary.pdf",
         adaptation="保持两个案例与原数据；缩短标题，图例移至下方两行，外部参考条件与监督拒绝结论移入图注。",
         scope="独立留出种子501；steady_minus旧链/监督完整核心轨迹，fused_neighbor旧链发布几何及载体误差。监督含外部目标参考，不是等信息磁精度排名。")


def main():
    apply_thesis_style(base_font_size=9)
    plt.rcParams.update({"font.size": 9, "axes.titlesize": 9, "axes.labelsize": 9,
                         "xtick.labelsize": 9, "ytick.labelsize": 9, "legend.fontsize": 9,
                         "savefig.bbox": None})
    OUT.mkdir(parents=True, exist_ok=True)
    for name in ["tools/plot_fwhm_v2_publication.py", "tools/plot_v2_simulation_closure.py",
                 "tools/plot_v2_robustness_thesis_summary.py", "tools/thesis_plot_style.py"]:
        remember(ROOT / name)
    stability()
    shape_guard()
    mission_process()
    supervision()
    RECORD.write_text(json.dumps(dict(
        purpose="中期报告专用重绘；原学位论文、历史图片、旧脚本和实验结果保持只读",
        regenerate="python3 tools/plot_middle_magnetic.py",
        script_sha256=sha(Path(__file__)), matplotlib_version=matplotlib.__version__,
        font=dict(path=FANDOL_SONG_REGULAR, sha256=sha(Path(FANDOL_SONG_REGULAR)),
                  family="FandolSong", minimum_pt=9),
        expected_include_width_cm=15,
        original_plot_sources_and_data=SOURCES,
        figures=ASSETS,
        validation="所有聚合量由CSV重算对照；轨迹SHA核验；画布越界检查；最终排版须逐页视觉复核。",
    ), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"figures": len(ASSETS), "minimum_text_pt": 9, "record": relative(RECORD)}, ensure_ascii=False))


if __name__ == "__main__":
    main()

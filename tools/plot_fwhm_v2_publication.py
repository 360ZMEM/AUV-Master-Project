#!/usr/bin/env python3
"""Render the standalone FWHM v2 result figures in the thesis house style."""
from __future__ import annotations

import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter, NullFormatter
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
MAG = ROOT / "AUV-Master-Mag"
RESULTS = MAG / "results/v2"
OUT = MAG / "docs/v2/publication/fwhm_v2_experiment_results"
FIG = OUT / "figures"
THESIS_FIG = ROOT / "docs/thesis/figures/experiments/fwhm_v2"
sys.path.insert(0, str(ROOT))
from tools import thesis_plot_style as tps  # noqa: E402


def rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def f(row: dict[str, str], key: str) -> float:
    try:
        return float(row[key])
    except (KeyError, TypeError, ValueError):
        return float("nan")


def grouped(values: list[dict[str, str]], key: str, metric: str):
    data: dict[float, list[float]] = defaultdict(list)
    for row in values:
        x, y = f(row, key), f(row, metric)
        if np.isfinite(x) and np.isfinite(y):
            data[x].append(y)
    xx = np.asarray(sorted(data), dtype=float)
    mean = np.asarray([np.mean(data[x]) for x in xx])
    q10 = np.asarray([np.percentile(data[x], 10) for x in xx])
    q90 = np.asarray([np.percentile(data[x], 90) for x in xx])
    return xx, mean, q10, q90


def save(fig, stem: str) -> None:
    tps.save_figure(fig, FIG / stem)
    plt.close(fig)


def save_publication_and_thesis(fig, stem: str) -> None:
    tps.save_figure(fig, FIG / stem)
    tps.save_figure(fig, THESIS_FIG / stem)
    plt.close(fig)


def use_plain_log_labels(axis, which: str = "y") -> None:
    """Format log ticks without glyphs absent from the thesis Song font."""
    formatter = FuncFormatter(
        lambda value, _position: (
            f"1e{int(round(np.log10(value)))}"
            if value > 0 and np.isclose(np.log10(value), round(np.log10(value)))
            else ""
        )
    )
    target_axis = getattr(axis, f"{which}axis")
    target_axis.set_major_formatter(formatter)
    target_axis.set_minor_formatter(NullFormatter())


def integrate_panel_labels(axes) -> None:
    """Prefix subplot titles so panel labels cannot collide with titles."""
    for index, axis in enumerate(list(getattr(axes, "flat", axes))):
        title = axis.get_title(loc="center") or axis.get_title(loc="left") or axis.get_title(loc="right")
        axis.set_title("", loc="center")
        axis.set_title("", loc="left")
        axis.set_title("", loc="right")
        axis.set_title(f"({chr(ord('a') + index)}) {title}", loc="left", pad=7.0)


def plot_cases() -> None:
    a = rows(RESULTS / "cases_a_d/case_a_initial_uncertainty.csv")
    b = rows(RESULTS / "cases_a_d/case_b_burial_depth.csv")
    c = rows(RESULTS / "cases_a_d/case_c_noise.csv")
    d = rows(RESULTS / "cases_a_d/case_d_lane_spacing.csv")
    fig, axes = plt.subplots(2, 2, figsize=tps.figure_size("full", height=5.0), constrained_layout=True)

    for ax, data, key, metric, xlabel, ylabel, title in (
        (axes[0, 0], a, "true_cable_offset_m", "detection_time_s", "真实电缆相对先验偏移 (m)", "检测时间 (s)", "大初始偏差下的搜索代价"),
        (axes[0, 1], d, "lane_spacing_m", "travelled_distance_m", "搜索航线间距 (m)", "检测前航程 (m)", "航线间距与搜索效率"),
        (axes[1, 0], b, "burial_true_m", "burial_error_m", "真实埋深 (m)", "埋深绝对误差 (m)", "同源模型下的埋深敏感性"),
        (axes[1, 1], c, "noise_nt", "burial_error_m", "磁测噪声标准差 (nT)", "埋深绝对误差 (m)", "噪声增大时的 FWHM 退化"),
    ):
        x, mean, q10, q90 = grouped(data, key, metric)
        if "误差" in ylabel:
            buckets = defaultdict(list)
            for row in data:
                buckets[f(row, key)].append(abs(f(row, metric)))
            mean = np.asarray([np.mean(buckets[v]) for v in x])
            q10 = np.asarray([np.percentile(buckets[v], 10) for v in x])
            q90 = np.asarray([np.percentile(buckets[v], 90) for v in x])
        ax.plot(x, mean, label="均值", **tps.line_style(0))
        ax.fill_between(x, q10, q90, color=tps.PROPOSED, alpha=0.16, label="10%--90% 区间")
        ax.set_xlabel(xlabel); ax.set_ylabel(ylabel); ax.set_title(title)
        ax.legend(loc="best")
    axes[1, 1].axhline(0.15, color=tps.WARNING, ls="--", lw=1.2, label="0.15 m 参考线")
    axes[1, 1].legend(loc="upper left")
    integrate_panel_labels(axes)
    save(fig, "01_cases_a_d_overview")


def plot_noise_insight() -> None:
    data = rows(RESULTS / "cases_a_d/case_c_noise.csv")
    x, mae, _, q90 = grouped(
        [{**r, "abs": str(abs(f(r, "burial_error_m")))} for r in data], "noise_nt", "abs"
    )
    _, confidence, c10, c90 = grouped(data, "noise_nt", "confidence")
    errors = np.asarray([abs(f(r, "burial_error_m")) for r in data])
    conf = np.asarray([f(r, "confidence") for r in data])
    noise = np.asarray([f(r, "noise_nt") for r in data])
    correlation = float(np.corrcoef(errors, conf)[0, 1])

    fig, axes = plt.subplots(1, 2, figsize=tps.figure_size("full", height=3.25), constrained_layout=True)
    ax = axes[0]
    ax.plot(x, mae, label="MAE", **tps.line_style(0))
    ax.plot(x, q90, label="90% 分位绝对误差", **tps.line_style(1))
    ax.axhline(0.15, color=tps.WARNING, ls=":", lw=1.3, label="0.15 m 参考线")
    ax.set_xscale("log"); use_plain_log_labels(ax, "x"); ax.set_xlabel("磁测噪声标准差 (nT)"); ax.set_ylabel("埋深绝对误差 (m)")
    ax.set_title("误差随噪声单调扩大"); ax.legend(loc="upper left")

    ax = axes[1]
    scatter = ax.scatter(conf, errors, c=noise, cmap="viridis", s=22, edgecolor=tps.REFERENCE, linewidth=0.3)
    ax.axhline(0.15, color=tps.WARNING, ls=":", lw=1.3)
    ax.set_xlabel("剖面置信度"); ax.set_ylabel("埋深绝对误差 (m)")
    ax.set_title(f"高置信剖面仍可能有较大误差（相关系数 {correlation:.2f}）")
    cbar = fig.colorbar(scatter, ax=ax, pad=0.02); cbar.set_label("噪声标准差 (nT)")
    integrate_panel_labels(axes)
    save(fig, "02_noise_confidence_insight")


def plot_ablations() -> None:
    summary = json.loads((RESULTS / "ablations/summary.json").read_text(encoding="utf-8"))["comparisons"]
    fig, axes = plt.subplots(2, 2, figsize=tps.figure_size("full", height=5.05), constrained_layout=True)

    panels = [
        (axes[0, 0], "background_half_level", ["background_corrected", "absolute_peak_half"], ["背景修正半峰", "绝对峰值一半"], "垂直距离 MAE (m)", "背景处理决定系统偏差"),
        (axes[0, 1], "spatial_vs_time", ["spatial_navigation", "mean_speed_times_time_width"], ["导航空间坐标", "均速 × 时间宽度"], "垂直距离 MAE (m)", "非匀速扫描必须使用空间坐标"),
        (axes[1, 0], "inversion_fusion", ["fwhm_only", "amplitude_only", "consistency_gated_fusion"], ["FWHM", "幅值反演", "一致性门控融合"], "垂直距离 MAE (m)", "未知增益下 FWHM 更稳健"),
        (axes[1, 1], "repeat_consistency", ["single_scan", "three_scan_median"], ["单次扫描", "三次中值"], "宽度 MAE (m)", "重复一致性抑制离群值"),
    ]
    for ax, comp, methods, labels, ylabel, title in panels:
        vals = [summary[comp][m]["mean_abs_error"] for m in methods]
        bars = ax.bar(np.arange(len(vals)), vals, color=[tps.PROPOSED, tps.BASELINE_1, tps.BASELINE_2][:len(vals)], edgecolor=tps.REFERENCE, linewidth=0.8)
        ax.set_xticks(np.arange(len(vals))); ax.set_xticklabels(labels)
        ax.set_ylabel(ylabel); ax.set_title(title)
        for bar, value in zip(bars, vals):
            ax.text(bar.get_x()+bar.get_width()/2, value, f"{value:.3f}", ha="center", va="bottom", fontsize=8)
    integrate_panel_labels(axes)
    save(fig, "03_key_design_ablations")

    fig, axes = plt.subplots(1, 2, figsize=tps.figure_size("full", height=3.15), constrained_layout=True)
    valid = summary["fixed_vs_adaptive_span"]
    labels = ["固定 1.5 m", "自适应 3z"]
    vals = [valid["fixed_1p5m"]["valid_rate"], valid["adaptive_3z"]["valid_rate"]]
    axes[0].bar(labels, vals, color=[tps.BASELINE_1, tps.PROPOSED], edgecolor=tps.REFERENCE)
    axes[0].set_ylim(0, 1.12); axes[0].set_ylabel("有效剖面比例"); axes[0].set_title("扫描幅度决定能否包围双侧交点")
    for i, value in enumerate(vals): axes[0].text(i, value + 0.025, f"{value:.2f}", ha="center")
    detect = summary["detection_hysteresis"]
    labels = ["单阈值", "双阈值迟滞"]
    vals = [detect["single_threshold"]["mean_abs_error"], detect["schmitt_hysteresis"]["mean_abs_error"]]
    axes[1].bar(labels, vals, color=[tps.BASELINE_1, tps.PROPOSED], edgecolor=tps.REFERENCE)
    axes[1].set_ylabel("状态切换次数误差"); axes[1].set_title("迟滞门控抑制阈值附近抖动")
    for i, value in enumerate(vals): axes[1].text(i, value + 0.5, f"{value:.2f}", ha="center")
    integrate_panel_labels(axes)
    save(fig, "04_detection_and_scan_gates")


def plot_model_consistency() -> None:
    data = rows(RESULTS / "fwhm_model_consistency/model_consistency.csv")
    models = [
        ("thesis_dipole_envelope", "论文偶极包络", 0),
        ("physical_single_wire", "物理单直导线", 1),
        ("legacy_segment_formula", "legacy 线段公式", 2),
    ]
    fig, axes = plt.subplots(1, 2, figsize=tps.figure_size("full", height=3.5))
    for name, label, index in models:
        selected = sorted((r for r in data if r["model"] == name), key=lambda r: f(r, "vertical_separation_m"))
        x = [f(r, "vertical_separation_m") for r in selected]
        axes[0].plot(x, [f(r, "implied_shape_factor") for r in selected], label=label, **tps.line_style(index))
        axes[1].plot(x, [100*f(r, "thesis_depth_relative_error") for r in selected], label=label, **tps.line_style(index))
    axes[0].axhline(0.5, color=tps.REFERENCE, ls=":", lw=1.0)
    axes[0].axhline(1/(2*np.sqrt(3)), color=tps.NEUTRAL, ls="--", lw=1.0)
    axes[0].set_xlabel("垂直距离 (m)"); axes[0].set_ylabel(r"隐含场形系数 $\kappa_M=z/W$")
    axes[0].set_title("场形系数随磁场模型而变")
    axes[1].set_xlabel("垂直距离 (m)"); axes[1].set_ylabel("误用 $\kappa_M=0.5$ 的相对误差 (%)")
    axes[1].set_title("高质量测宽不能消除模型偏差")
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, ncol=3, loc="upper center", bbox_to_anchor=(0.5, 0.98), frameon=True)
    fig.subplots_adjust(left=0.10, right=0.98, bottom=0.18, top=0.80, wspace=0.30)
    integrate_panel_labels(axes)
    save(fig, "05_field_model_consistency")


def plot_closed_loop() -> None:
    pvs = json.loads((RESULTS / "pvs_geometry_controlled/summary.json").read_text(encoding="utf-8"))
    rejected = json.loads((RESULTS / "pvs_geometry_calibrated/summary.json").read_text(encoding="utf-8"))
    ideal_truth, ideal_est = 7.5, 7.5360
    pvs_truth = pvs["truth"]["vertical_separation_m"]
    pvs_est = pvs["estimate"]["vertical_separation_m"]
    fig, axes = plt.subplots(1, 3, figsize=tps.figure_size("full", height=3.2), constrained_layout=True)
    x = np.arange(2); w = 0.34
    axes[0].bar(x-w/2, [ideal_truth, pvs_truth], w, color=tps.REFERENCE, label="真值")
    axes[0].bar(x+w/2, [ideal_est, pvs_est], w, color=tps.PROPOSED, label="估计")
    axes[0].set_xticks(x); axes[0].set_xticklabels(["解析单直导线", "PVS 中点电流元"])
    axes[0].set_ylabel("垂直距离 (m)"); axes[0].set_title("同一 FWHM 算法\n场模型决定系统偏差"); axes[0].legend()
    for i, err in enumerate([ideal_est-ideal_truth, pvs_est-pvs_truth]):
        axes[0].text(i, max([ideal_est, pvs_est][i], [ideal_truth, pvs_truth][i])+0.12, f"误差 {err:.3f} m", ha="center", fontsize=8)

    values = [pvs["estimate"]["validity_score"], pvs["estimate"]["confidence"]]
    axes[1].bar(["有效性", "剖面置信度"], values, color=[tps.PROPOSED, tps.BASELINE_2], edgecolor=tps.REFERENCE)
    axes[1].set_ylim(0, 1.1); axes[1].set_ylabel("评分"); axes[1].set_title("高剖面质量\n不等于深度准确")
    for i, value in enumerate(values): axes[1].text(i, value+0.025, f"{value:.3f}", ha="center")

    along = rejected["cross_scan_along_track_range_m"]
    limit = rejected["maximum_allowed_along_track_range_m"]
    axes[2].bar(["24 m 单档扫描"], [along], color=tps.WARNING, edgecolor=tps.REFERENCE, label="沿缆漂移")
    axes[2].axhline(limit, color=tps.REFERENCE, ls="--", lw=1.3, label="5 m 硬门限")
    axes[2].set_ylabel("沿缆位移范围 (m)"); axes[2].set_title("大摆幅破坏横切几何")
    axes[2].text(0, along+0.35, f"{along:.2f} m\n且缺少左半高交点", ha="center", fontsize=8)
    axes[2].legend(loc="upper right")
    integrate_panel_labels(axes)
    save(fig, "06_closed_loop_evidence_boundary")


def plot_tmr_audit() -> None:
    data = rows(RESULTS / "tmr_joint_replay/legs.csv")
    ids = np.arange(len(data))
    along = np.asarray([f(r, "along_to_cross_ratio") for r in data])
    secondary = np.asarray([f(r, "secondary_to_cross_ratio") for r in data])
    geometry = np.asarray([r["geometry_valid"].lower() == "true" for r in data])
    fig, axes = plt.subplots(1, 2, figsize=tps.figure_size("full", height=3.35), constrained_layout=True)
    axes[0].scatter(ids[~geometry], along[~geometry], color=tps.WARNING, marker="x", s=38, label="几何拒绝")
    axes[0].scatter(ids[geometry], along[geometry], color=tps.PROPOSED, marker="o", s=32, edgecolor=tps.REFERENCE, linewidth=0.4, label="几何通过")
    axes[0].plot(ids, secondary, color=tps.BASELINE_2, marker="s", ls="--", label="次要方向/横切")
    axes[0].axhline(0.25, color=tps.REFERENCE, ls=":", label="沿缆比例门限 0.25")
    axes[0].axhline(0.20, color=tps.NEUTRAL, ls="--", label="非平面比例门限 0.20")
    axes[0].set_xlabel("候选扫描腿序号"); axes[0].set_ylabel("轨迹位移比"); axes[0].set_title("自由手持轨迹仅部分满足横切几何"); axes[0].legend(loc="upper right", fontsize=7)
    stages = ["候选扫描腿", "几何通过", "双侧 FWHM", "允许发布深度"]
    counts = [len(data), int(np.sum(geometry)), sum(r["fwhm_valid"].lower()=="true" for r in data), sum(r["eligible_for_depth"].lower()=="true" for r in data)]
    bars = axes[1].bar(stages, counts, color=[tps.NEUTRAL, tps.PROPOSED, tps.BASELINE_1, tps.BASELINE_2], edgecolor=tps.REFERENCE)
    axes[1].set_ylabel("扫描腿数量"); axes[1].set_title("质量门阻止不完整实测剖面发布伪深度")
    axes[1].tick_params(axis="x", rotation=16)
    for bar, count in zip(bars, counts): axes[1].text(bar.get_x()+bar.get_width()/2, count+0.15, str(count), ha="center")
    integrate_panel_labels(axes)
    save(fig, "07_tmr_quality_gate_audit")


def plot_mission_process() -> None:
    process = RESULTS / "process_visual_demo"
    search = rows(process / "search_trace.csv")
    profiles = rows(process / "cross_scan_profiles.csv")
    track = rows(process / "tracking_trace.csv")
    observations = rows(process / "cable_observations.csv")
    summary = json.loads((process / "summary.json").read_text(encoding="utf-8"))
    sx = np.asarray([f(r, "x_m") for r in search]); sy = np.asarray([f(r, "y_m") for r in search])
    tx = np.asarray([f(r, "x_m") for r in track]); ty = np.asarray([f(r, "auv_y_m") for r in track])
    detection = np.asarray(summary["detection_point_xy_m"], dtype=float)

    fig = plt.figure(figsize=tps.figure_size("full", height=5.25), constrained_layout=True)
    grid = fig.add_gridspec(2, 2, height_ratios=(1.25, 1.0))
    ax = fig.add_subplot(grid[0, :])
    ax.axhspan(-15, 15, color=tps.NEUTRAL, alpha=0.08, label="搜索边界")
    ax.plot([0, 100], [0, 0], color=tps.BASELINE_1, ls="--", lw=1.7, label="先验电缆")
    ax.plot([0, 100], [8, 8], color=tps.REFERENCE, lw=2.1, label="真实电缆")
    ax.plot(sx, sy, color=tps.PROPOSED, lw=1.35, label="Search 航迹")
    for attempt in sorted({int(f(r, "attempt")) for r in profiles}):
        selected = [r for r in profiles if int(f(r, "attempt")) == attempt]
        ax.plot(
            [f(r, "map_x_m") for r in selected], [f(r, "map_y_m") for r in selected],
            color=tps.ACCENT_COLORS[(attempt + 1) % len(tps.ACCENT_COLORS)],
            lw=1.15 + 0.15 * attempt, alpha=0.80,
            label=f"Confirm 第 {attempt} 档" if attempt in (1, len({int(f(r, 'attempt')) for r in profiles})) else None,
        )
    ax.plot(tx, ty, color=tps.BASELINE_2, lw=2.0, label="Track 航迹")
    ax.scatter(*detection, marker="*", s=95, color=tps.WARNING, edgecolor=tps.REFERENCE, linewidth=0.5, zorder=6, label="稳定检测点")
    ax.set_xlim(-2, 102); ax.set_ylim(-17, 30); ax.set_aspect("equal", adjustable="box")
    ax.set_xlabel("北向/沿缆坐标 (m)"); ax.set_ylabel("东向/横缆坐标 (m)")
    ax.set_title("从先验走廊搜索到主动确认和电缆跟踪的完整俯视过程")
    ax.legend(ncol=3, loc="upper center", fontsize=8)

    ax = fig.add_subplot(grid[1, 0])
    for attempt in sorted({int(f(r, "attempt")) for r in profiles}):
        selected = [r for r in profiles if int(f(r, "attempt")) == attempt]
        span = f(selected[0], "half_span_m")
        ax.plot(
            [f(r, "map_x_m") + 0.13 * (attempt - 2.5) for r in selected],
            [f(r, "map_y_m") for r in selected],
            label=f"第 {attempt} 档：±{span:.0f} m", **tps.line_style(attempt - 1),
        )
    ax.axhline(8.0, color=tps.REFERENCE, lw=1.6, label="真实电缆")
    ax.axhline(summary["observed_cable_y_m"], color=tps.BASELINE_2, ls="--", lw=1.4, label="FWHM 横向观测")
    ax.scatter(*detection, marker="*", s=70, color=tps.WARNING, zorder=5)
    ax.set_xlim(detection[0]-2.2, detection[0]+2.2); ax.set_ylim(-25, 30)
    ax.set_xlabel("沿缆坐标 (m，档位作微小横移以便观察)"); ax.set_ylabel("横缆坐标 (m)")
    ax.set_title("逐级扩幅直到包围完整磁峰"); ax.legend(loc="lower right", fontsize=7)

    ax = fig.add_subplot(grid[1, 1])
    progress = np.abs(tx - tx[0])
    true_error = np.asarray([f(r, "true_cross_track_error_m") for r in track])
    estimated_error = np.asarray([f(r, "estimated_cross_track_error_m") for r in track])
    ax.plot(progress, true_error, label="相对真实电缆", **tps.line_style(0))
    ax.plot(progress, estimated_error, label="相对修正后地图", **tps.line_style(2))
    ax.axhspan(-1.0, 1.0, color=tps.PROPOSED, alpha=0.10, label="±1 m 重入带")
    ax.axhline(0, color=tps.REFERENCE, lw=0.8)
    ax.set_xlabel("进入 Track 后航程 (m)"); ax.set_ylabel("带符号横向误差 (m)")
    ax.set_title("横切观测修正地图后，航迹稳定回归")
    ax.legend(loc="best", fontsize=8)
    integrate_panel_labels([fig.axes[0], fig.axes[1], fig.axes[2]])
    save(fig, "08_mission_process_plan_view")


def plot_explicit_profile() -> None:
    process = RESULTS / "process_visual_demo"
    data = rows(process / "cross_scan_profiles.csv")
    attempts = rows(process / "cross_scan_attempts.csv")
    summary = json.loads((process / "summary.json").read_text(encoding="utf-8"))
    fig, axes = plt.subplots(1, 2, figsize=tps.figure_size("full", height=3.4), constrained_layout=True)
    for index, attempt in enumerate(attempts):
        attempt_id = int(f(attempt, "attempt"))
        selected = sorted((r for r in data if int(f(r, "attempt")) == attempt_id), key=lambda r: f(r, "cross_coordinate_m"))
        label = f"±{f(attempt, 'half_span_m'):.0f} m（{'有效' if int(f(attempt, 'valid')) else '拒绝'}）"
        axes[0].plot([f(r, "cross_coordinate_m") for r in selected], [f(r, "envelope_nt") for r in selected], label=label, alpha=0.9, **tps.line_style(index))
    axes[0].axhline(summary["half_level_nt"], color=tps.REFERENCE, ls=":", lw=1.1, label="最终半高线")
    axes[0].set_xlabel("相对检测中心的横切坐标 (m)"); axes[0].set_ylabel("磁场包络 (nT)")
    axes[0].set_title("小幅扫描只看到磁峰一侧，逐级扩幅后闭合")
    axes[0].legend(loc="upper left", fontsize=7)

    final_id = int(summary["successful_cross_scan_attempt"])
    final = sorted((r for r in data if int(f(r, "attempt")) == final_id), key=lambda r: f(r, "cross_coordinate_m"))
    x = np.asarray([f(r, "cross_coordinate_m") for r in final])
    y = np.asarray([f(r, "envelope_nt") for r in final])
    window = 5; padded = np.pad(y, (window//2, window//2), mode="edge")
    smooth = np.asarray([np.median(padded[i:i+window]) for i in range(y.size)])
    ax = axes[1]
    ax.scatter(x, y, s=7, color=tps.NEUTRAL, alpha=0.42, label="原始采样")
    ax.plot(x, smooth, color=tps.PROPOSED, lw=1.9, label="中值平滑剖面")
    ax.axhline(summary["baseline_nt"], color=tps.BASELINE_2, ls="--", label="背景")
    ax.axhline(summary["half_level_nt"], color=tps.WARNING, ls=":", lw=1.5, label="背景修正半高")
    left, right = summary["left_crossing_m"], summary["right_crossing_m"]
    ax.axvline(left, color=tps.REFERENCE, ls="--", lw=1.0)
    ax.axvline(right, color=tps.REFERENCE, ls="--", lw=1.0)
    ax.annotate("", xy=(left, summary["half_level_nt"]+1.0), xytext=(right, summary["half_level_nt"]+1.0), arrowprops={"arrowstyle":"<->", "color":tps.REFERENCE, "lw":1.2})
    ax.text((left+right)/2, summary["half_level_nt"]+1.35, f"FWHM = {summary['fwhm_m']:.2f} m", ha="center")
    ax.text(0.03, 0.96, f"埋深真值 {summary['burial_true_at_detection_m']:.2f} m\n估计 {summary['burial_estimate_at_detection_m']:.2f} ± {summary['burial_sigma_at_detection_m']:.2f} m", transform=ax.transAxes, va="top", bbox={"facecolor":"white", "edgecolor":tps.GRID_COLOR, "alpha":0.92})
    ax.set_xlabel("相对检测中心的横切坐标 (m)"); ax.set_ylabel("磁场包络 (nT)")
    ax.set_title("显式标出峰值、左右交点和半高全宽")
    ax.legend(loc="upper right", fontsize=7)
    integrate_panel_labels(axes)
    save(fig, "09_explicit_fwhm_profile")


def plot_depth_reconstruction() -> None:
    process = RESULTS / "process_visual_demo"
    truth = rows(process / "depth_truth_curve.csv")
    estimates = rows(process / "depth_reconstruction.csv")
    summary = json.loads((process / "summary.json").read_text(encoding="utf-8"))
    tx = np.asarray([f(r, "progress_m") for r in truth]); td = np.asarray([f(r, "burial_true_m") for r in truth])
    x = np.asarray([f(r, "progress_m") for r in estimates])
    true = np.asarray([f(r, "burial_true_m") for r in estimates])
    estimated = np.asarray([f(r, "burial_estimate_m") for r in estimates])
    sigma = np.asarray([f(r, "burial_sigma_m") for r in estimates])
    confidence = np.asarray([f(r, "confidence") for r in estimates])
    error = estimated - true
    fig, axes = plt.subplots(2, 1, figsize=tps.figure_size("full", height=4.8), sharex=True, constrained_layout=True, gridspec_kw={"height_ratios":(1.35, 1.0)})
    axes[0].plot(tx, td, color=tps.REFERENCE, lw=2.0, label="连续埋深真值")
    axes[0].errorbar(x, estimated, yerr=sigma, fmt="o", color=tps.PROPOSED, ecolor=tps.PROPOSED, capsize=3, label="FWHM 估计 ±1σ")
    axes[0].plot(x, estimated, color=tps.PROPOSED, lw=1.0, alpha=0.65)
    axes[0].set_ylabel("海缆埋深 (m)"); axes[0].set_title("巡检过程中 FWHM 埋深估计与连续真值对比")
    axes[0].legend(loc="best")
    axes[0].text(0.02, 0.06, f"全程 MAE = {summary['mean_abs_depth_error_m']:.3f} m", transform=axes[0].transAxes, bbox={"facecolor":"white", "edgecolor":tps.GRID_COLOR})
    axes[1].axhline(0, color=tps.REFERENCE, lw=0.8)
    axes[1].fill_between(x, -sigma, sigma, color=tps.PROPOSED, alpha=0.12, label="报告的 ±1σ")
    points = axes[1].scatter(x, error, c=confidence, cmap="viridis", s=42, edgecolor=tps.REFERENCE, linewidth=0.4, label="估计误差")
    axes[1].plot(x, error, color=tps.PROPOSED, lw=0.9, alpha=0.6)
    axes[1].set_xlabel("沿缆巡检进度 (m)"); axes[1].set_ylabel("估计值 - 真值 (m)")
    axes[1].set_title("误差、报告不确定度与剖面置信度")
    cbar = fig.colorbar(points, ax=axes[1], pad=0.02); cbar.set_label("剖面置信度")
    axes[1].legend(loc="lower right")
    integrate_panel_labels(axes)
    save(fig, "10_burial_depth_reconstruction_process")


def plot_stability_comparison() -> None:
    result_dir = RESULTS / "stability_comparison"
    summary = json.loads((result_dir / "summary.json").read_text(encoding="utf-8"))["scenarios"]
    data = rows(result_dir / "per_run.csv")
    methods = ["explicit_fwhm", "free_profile_fit", "calibrated_amplitude", "absolute_half"]
    method_labels = ["显式空间 FWHM", "自由幅值剖面拟合", "标定幅值反演", "未扣背景半高"]
    scenarios = ["nominal", "gain", "background", "noise", "scan_offset", "combined"]
    scenario_labels = ["标称", "增益变化", "背景变化", "噪声", "扫描偏心", "组合扰动"]
    colors = [tps.PROPOSED, tps.BASELINE_2, tps.BASELINE_1, tps.WARNING]
    fig, axes = plt.subplots(2, 2, figsize=tps.figure_size("full", height=5.55))

    x = np.arange(len(scenarios)); width = 0.19
    for idx, (method, label, color) in enumerate(zip(methods, method_labels, colors)):
        values = [summary[s][method]["mae_m_published"] for s in scenarios]
        axes[0, 0].bar(x + (idx - 1.5) * width, values, width, color=color, edgecolor=tps.REFERENCE, linewidth=0.5, label=label)
    axes[0, 0].set_yscale("log"); use_plain_log_labels(axes[0, 0]); axes[0, 0].set_xticks(x); axes[0, 0].set_xticklabels(scenario_labels, rotation=18)
    axes[0, 0].set_ylabel("发布结果 MAE (m，对数坐标)"); axes[0, 0].set_title("不同扰动下的条件精度")

    for idx, (method, label, color) in enumerate(zip(methods, method_labels, colors)):
        values = [summary[s][method]["valid_rate"] for s in scenarios]
        axes[0, 1].plot(x, values, color=color, label=label, **{k:v for k,v in tps.line_style(idx).items() if k != "color"})
    axes[0, 1].set_xticks(x); axes[0, 1].set_xticklabels(scenario_labels, rotation=18)
    axes[0, 1].set_ylim(0.6, 1.03); axes[0, 1].set_ylabel("有效发布率")
    axes[0, 1].set_title("扫描偏心时 FWHM 选择拒绝不完整剖面")

    risk_scenarios = ["combined", "model_mismatch"]
    risk_labels = ["组合扰动", "场模型失配"]
    xx = np.arange(len(risk_scenarios)); width2 = 0.19
    for idx, (method, label, color) in enumerate(zip(methods, method_labels, colors)):
        values = [summary[s][method]["large_error_publish_rate"] for s in risk_scenarios]
        axes[1, 0].bar(xx + (idx - 1.5) * width2, values, width2, color=color, edgecolor=tps.REFERENCE, linewidth=0.5, label=label)
    axes[1, 0].set_xticks(xx); axes[1, 0].set_xticklabels(risk_labels)
    axes[1, 0].set_ylim(0, 1.08); axes[1, 0].set_ylabel("误差 > 0.5 m 仍发布的比例")
    axes[1, 0].set_title("组合压力与错误模型下的发布风险")

    combined = []
    for method in methods:
        values = [f(r, "error_m") for r in data if r["scenario"] == "combined" and r["method"] == method and int(f(r, "valid")) == 1]
        combined.append(values)
    box = axes[1, 1].boxplot(combined, tick_labels=method_labels, showfliers=False, patch_artist=True, widths=0.62)
    for patch, color in zip(box["boxes"], colors): patch.set_facecolor(color); patch.set_alpha(0.75)
    axes[1, 1].axhline(0, color=tps.REFERENCE, lw=0.8)
    axes[1, 1].set_ylabel("组合扰动下估计误差 (m)"); axes[1, 1].set_title("误差分布与离散程度")
    axes[1, 1].tick_params(axis="x", rotation=18)
    handles, labels = axes[0, 0].get_legend_handles_labels()
    fig.legend(handles, labels, ncol=4, loc="upper center", bbox_to_anchor=(0.5, 0.985), fontsize=8)
    fig.subplots_adjust(left=0.10, right=0.98, bottom=0.13, top=0.82, hspace=0.56, wspace=0.30)
    integrate_panel_labels(axes)
    save_publication_and_thesis(fig, "11_fwhm_stability_comparison")


def plot_stability_sensitivity() -> None:
    data = rows(RESULTS / "stability_comparison/per_run.csv")
    methods = ["explicit_fwhm", "free_profile_fit", "calibrated_amplitude"]
    labels = ["显式空间 FWHM", "自由幅值剖面拟合", "标定幅值反演"]
    fig, axes = plt.subplots(1, 3, figsize=tps.figure_size("full", height=3.55))

    for idx, (method, label) in enumerate(zip(methods, labels)):
        selected = [r for r in data if r["scenario"] == "gain" and r["method"] == method and int(f(r, "valid")) == 1]
        gain = np.asarray([f(r, "gain_scale") for r in selected]); ratio = np.asarray([f(r, "z_estimate_m") / f(r, "z_true_m") for r in selected])
        order = np.argsort(gain)
        style = tps.line_style(idx); style["color"] = [tps.PROPOSED, tps.BASELINE_2, tps.BASELINE_1][idx]
        axes[0].plot(gain[order], ratio[order], label=label, **style)
    axes[0].axhline(1, color=tps.REFERENCE, ls=":"); axes[0].set_xscale("log"); use_plain_log_labels(axes[0], "x")
    axes[0].set_xticks([0.6, 1.0, 2.0]); axes[0].set_xticklabels(["0.6", "1.0", "2.0"])
    axes[0].set_xlabel("未知增益尺度"); axes[0].set_ylabel("估计/真值"); axes[0].set_title("对增益变化的敏感性")

    bins = np.geomspace(0.03, 1.0, 7)
    centers = np.sqrt(bins[:-1] * bins[1:])
    for idx, (method, label) in enumerate(zip(methods, labels)):
        q90 = []
        for lo, hi in zip(bins[:-1], bins[1:]):
            values = [f(r, "abs_error_m") for r in data if r["scenario"] == "noise" and r["method"] == method and int(f(r, "valid")) == 1 and lo <= f(r, "noise_nt") < hi]
            q90.append(np.percentile(values, 90) if values else np.nan)
        style = tps.line_style(idx); style["color"] = [tps.PROPOSED, tps.BASELINE_2, tps.BASELINE_1][idx]
        axes[1].plot(centers, q90, label=label, **style)
    axes[1].set_xscale("log"); axes[1].set_yscale("log"); use_plain_log_labels(axes[1], "x"); use_plain_log_labels(axes[1], "y")
    axes[1].set_xticks([0.03, 0.1, 0.3, 1.0]); axes[1].set_xticklabels(["0.03", "0.1", "0.3", "1.0"])
    axes[1].set_xlabel("噪声标准差 (nT)"); axes[1].set_ylabel("绝对误差 90% 分位 (m)"); axes[1].set_title("噪声升高时的尾部稳定性")

    for idx, (method, label) in enumerate(zip(methods, labels)):
        selected = [r for r in data if r["scenario"] == "model_mismatch" and r["method"] == method and int(f(r, "valid")) == 1]
        truth = np.asarray([f(r, "z_true_m") for r in selected]); estimate = np.asarray([f(r, "z_estimate_m") for r in selected])
        axes[2].scatter(truth, estimate, s=12, alpha=0.45, label=label, color=[tps.PROPOSED, tps.BASELINE_2, tps.BASELINE_1][idx], edgecolor="none")
    axes[2].plot([2.4, 5.1], [2.4, 5.1], color=tps.REFERENCE, ls=":", label="理想一致")
    axes[2].set_xlabel("真实垂直距离 (m)"); axes[2].set_ylabel("估计垂直距离 (m)")
    axes[2].set_title("错误场形模型造成系统偏差")
    handles, legend_labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, legend_labels, ncol=3, loc="upper center", bbox_to_anchor=(0.5, 0.985), fontsize=8)
    fig.subplots_adjust(left=0.09, right=0.98, bottom=0.17, top=0.75, wspace=0.36)
    integrate_panel_labels(axes)
    save_publication_and_thesis(fig, "12_fwhm_stability_sensitivity")


def plot_shape_guard_validation() -> None:
    result_dir = RESULTS / "shape_guard_validation"
    summary = json.loads((result_dir / "summary.json").read_text(encoding="utf-8"))["scenarios"]
    data = rows(result_dir / "per_run.csv")
    fig, axes = plt.subplots(2, 2, figsize=tps.figure_size("full", height=4.9))
    before, after = "before_guard", "with_guard"
    pair = [("model_mismatch", "直导线→偶极"), ("dipole_as_wire", "偶极→直导线")]
    x = np.arange(len(pair))
    for idx, (mode, label, color) in enumerate(((before, "原质量门", tps.WARNING), (after, "形状判别门", tps.PROPOSED))):
        axes[0, 0].bar(x + (idx - 0.5) * 0.28,
                       [summary[key][mode]["large_error_publish_rate"] for key, _ in pair],
                       0.28, color=color, edgecolor=tps.REFERENCE, label=label)
    axes[0, 0].set_xticks(x, [label for _, label in pair])
    axes[0, 0].set_ylim(0, 1.08)
    axes[0, 0].set_ylabel("大误差仍发布的比例")
    axes[0, 0].set_title("双向失配下的发布风险")

    stable = [("nominal", "标称"), ("gain", "增益"), ("background", "背景"), ("matched_wire", "正确直导线")]
    difficult = [("noise", "噪声"), ("scan_offset", "扫描偏心"), ("combined", "组合扰动")]
    for axis, group, title in ((axes[0, 1], stable, "正确模型的常规发布率"),
                               (axes[1, 0], difficult, "困难条件下的拒绝代价")):
        xx = np.arange(len(group))
        for idx, (mode, label, color) in enumerate(((before, "原质量门", tps.WARNING), (after, "形状判别门", tps.PROPOSED))):
            axis.bar(xx + (idx - 0.5) * 0.28,
                     [summary[key][mode]["valid_rate"] for key, _ in group],
                     0.28, color=color, edgecolor=tps.REFERENCE, label=label)
        axis.set_xticks(xx, [label for _, label in group])
        axis.set_ylim(0, 1.08)
        axis.set_ylabel("有效发布率")
        axis.set_title(title)

    ax = axes[1, 1]
    for scenario, label, color in (("nominal", "正确偶极", tps.BASELINE_2),
                                    ("matched_wire", "正确直导线", tps.PROPOSED),
                                    ("model_mismatch", "直导线误报偶极", tps.WARNING),
                                    ("dipole_as_wire", "偶极误报直导线", tps.BASELINE_3)):
        selected = [r for r in data if r["scenario"] == scenario and r["mode"] == after]
        ax.scatter([f(r, "declared_residual") for r in selected],
                   [f(r, "competing_residual") for r in selected],
                   s=11, alpha=0.55, label=label, color=color, edgecolor="none")
    ax.plot([0, 0.11], [0, 0.11], color=tps.REFERENCE, ls=":", lw=1)
    ax.set_xlim(0, 0.11); ax.set_ylim(0, 0.11)
    ax.set_xlabel("声明模型残差"); ax.set_ylabel("备选模型残差")
    ax.set_title("相同峰值、中心和宽度下的形状证据")
    handles, labels = axes[0, 0].get_legend_handles_labels()
    fig.legend(handles, labels, ncol=2, loc="upper center", bbox_to_anchor=(0.5, 0.99), fontsize=8)
    fig.subplots_adjust(left=0.10, right=0.98, bottom=0.11, top=0.84, hspace=0.54, wspace=0.32)
    integrate_panel_labels(axes)
    save_publication_and_thesis(fig, "13_shape_guard_held_out_validation")


def sha256(path: Path) -> str:
    digest = hashlib.sha256(); digest.update(path.read_bytes()); return digest.hexdigest()


def write_manifest() -> None:
    sources = [
        RESULTS / "cases_a_d/manifest.json",
        RESULTS / "ablations/manifest.json",
        RESULTS / "fwhm_model_consistency/manifest.json",
        RESULTS / "tmr_joint_replay/manifest.json",
        RESULTS / "process_visual_demo/manifest.json",
        RESULTS / "stability_comparison/manifest.json",
        RESULTS / "shape_guard_validation/manifest.json",
        RESULTS / "pvs_geometry_controlled/summary.json",
        RESULTS / "pvs_geometry_calibrated/summary.json",
    ]
    assets = sorted(FIG.glob("*.*"))
    payload = {
        "generator": str(Path(__file__).relative_to(ROOT)),
        "style": "tools/thesis_plot_style.py",
        "source_artifacts": [{"path": str(p.relative_to(ROOT)), "sha256": sha256(p)} for p in sources],
        "published_figures": [{"path": str(p.relative_to(OUT)), "sha256": sha256(p)} for p in assets],
    }
    (OUT / "publication_manifest.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")


def main() -> None:
    FIG.mkdir(parents=True, exist_ok=True)
    tps.apply_thesis_style(layout="full")
    plot_cases(); plot_noise_insight(); plot_ablations(); plot_model_consistency()
    plot_closed_loop(); plot_tmr_audit(); plot_mission_process()
    plot_explicit_profile(); plot_depth_reconstruction(); plot_stability_comparison()
    plot_stability_sensitivity(); plot_shape_guard_validation(); write_manifest()
    print(f"wrote publication figures to {FIG}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Generate thesis-ready terrain-following figures.

This script centralizes all figures used by
docs/thesis/09_terrain_following_figures.md:

- PID/MPC clearance RMSE comparison.
- Clearance safety margin summary.
- PID low/mid/high terrain ablation summary.
- Benchmark command contract schematic.
- t-z terrain-following tracking curves from MCAP bags.
- 3D terrain surface with AUV trajectory from MCAP bags. If the bag does not
  contain a seabed point cloud, the surface is reconstructed from the bridge
  deterministic terrain configuration.
"""

from __future__ import annotations

import argparse
import csv
import math
import sys
from pathlib import Path

import numpy as np
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(PROJECT_ROOT))
sys.path.append(str(PROJECT_ROOT / "sim_holoocean"))

from tools import analyze_bag  # noqa: E402
from interfaces.synthetic_sensors import berlin_noise_2d  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--main-result",
        type=Path,
        default=PROJECT_ROOT / "results/control/terrain_following_20260619_222639",
        help="PID/MPC four-group terrain benchmark result directory.",
    )
    parser.add_argument(
        "--ablation-summary",
        type=Path,
        default=PROJECT_ROOT / "results/control/pid_terrain_ablation_20260610_summary.csv",
        help="PID low/mid/high terrain ablation summary CSV.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "docs/thesis/figures/terrain_following",
        help="Directory for generated PNG/PDF figures.",
    )
    parser.add_argument(
        "--target-clearance-m",
        type=float,
        default=3.0,
        help="Target seabed clearance in meters.",
    )
    parser.add_argument(
        "--warmup-skip-s",
        type=float,
        default=10.0,
        help="Warm-up/dive transient to trim from t-z curves, consistent with summary statistics.",
    )
    parser.add_argument(
        "--terrain-config",
        type=Path,
        default=PROJECT_ROOT / "config/bridge_params.protocol_udp.pvs.terrain.yaml",
        help="Full bridge YAML used to reconstruct deterministic terrain if the bag lacks point cloud data.",
    )
    return parser.parse_args()


def read_summary_csv(path: Path) -> dict[str, str]:
    with path.open(newline="", encoding="utf-8") as f:
        return {row["metric"]: row["value"] for row in csv.DictReader(f)}


def read_table_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def fval(data: dict[str, str], key: str) -> float:
    try:
        return float(data.get(key, "nan"))
    except Exception:
        return math.nan


def provenance_note(summaries: dict[str, dict[str, str]]) -> str:
    """One-line data-provenance caption shared by the bar/safety figures."""
    sources = sorted({(s.get("clearance_source", "") or "").strip() for s in summaries.values()})
    sources = [s for s in sources if s]
    pretty = {
        "real_altitude": "真实 DVL 高度",
        "terrain_cloud": "海底点云",
        "diag_constant_datum": "常值基准（旧）",
    }
    label = ", ".join(pretty.get(s, s) for s in sources) if sources else "未知"
    return f"净空来源：{label}；已裁去预热；真值 = /auv/sensors/ground_truth"


def read_digital_twin_config(path: Path) -> dict[str, float | int]:
    with path.open(encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}
    digital_twin = config.get("digital_twin", {})
    if not isinstance(digital_twin, dict):
        raise RuntimeError(f"Missing digital_twin block in terrain config: {path}")
    return digital_twin


def terrain_depth_from_config(x_value: float, y_value: float, terrain_cfg: dict[str, float | int]) -> float:
    noise = berlin_noise_2d(
        float(x_value),
        float(y_value),
        seed=int(terrain_cfg.get("terrain_seed", 7)),
        octaves=int(terrain_cfg.get("terrain_noise_octaves", 3)),
        scale=float(terrain_cfg.get("terrain_noise_scale_m", 8.0)),
    )
    slope_offset = -math.tan(math.radians(float(terrain_cfg.get("terrain_slope_deg", 0.0)))) * max(0.0, float(x_value) - 10.0)
    return float(terrain_cfg.get("seabed_z_m", 15.0)) + float(terrain_cfg.get("terrain_noise_amplitude_m", 1.0)) * noise + slope_offset


def reconstruct_terrain_grid(
    *,
    x_values: np.ndarray,
    y_values: np.ndarray,
    terrain_cfg: dict[str, float | int],
    padding_m: float = 8.0,
    max_samples_per_axis: int = 120,
    clamp_to_extent: bool = True,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    resolution = max(float(terrain_cfg.get("terrain_resolution_m", 1.0)), 0.25)
    extent = float(terrain_cfg.get("terrain_extent_m", 50.0))
    x_min = float(np.nanmin(x_values)) - padding_m
    x_max = float(np.nanmax(x_values)) + padding_m
    y_min = float(np.nanmin(y_values)) - padding_m
    y_max = float(np.nanmax(y_values)) + padding_m
    if clamp_to_extent:
        # 仿真在 AUV 移动中心 ±extent/2 采样地形，地形公式对全轨迹均有定义；
        # 仅当调用方要求时才把网格夹到静态 ±extent 世界瓦片内。
        x_min = max(x_min, -extent)
        x_max = min(x_max, extent)
        y_min = max(y_min, -extent)
        y_max = min(y_max, extent)

    nx = max(2, min(max_samples_per_axis, int(math.ceil((x_max - x_min) / resolution)) + 1))
    ny = max(2, min(max_samples_per_axis, int(math.ceil((y_max - y_min) / resolution)) + 1))
    grid_x, grid_y = np.meshgrid(np.linspace(x_min, x_max, nx), np.linspace(y_min, y_max, ny))
    depth = np.empty_like(grid_x, dtype=float)
    for row in range(grid_x.shape[0]):
        for col in range(grid_x.shape[1]):
            depth[row, col] = terrain_depth_from_config(grid_x[row, col], grid_y[row, col], terrain_cfg)
    return grid_x, grid_y, depth


def save_figure(fig, output_dir: Path, stem: str) -> None:
    for ext in ("png", "pdf"):
        fig.savefig(output_dir / f"{stem}.{ext}", bbox_inches="tight")


def setup_style() -> None:
    analyze_bag.ensure_runtime_dependencies()
    plt = analyze_bag.plt
    # 图内统一中文：注入文泉驿正黑（容器内唯一可用 CJK 字体，无思源宋体）
    import os
    import matplotlib.font_manager as fm
    _zh_font = "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"
    if os.path.exists(_zh_font):
        fm.fontManager.addfont(_zh_font)
        plt.rcParams["font.family"] = fm.FontProperties(fname=_zh_font).get_name()
    else:
        plt.rcParams["font.sans-serif"] = ["WenQuanYi Zen Hei", "SimHei"] + plt.rcParams["font.sans-serif"]
    plt.rcParams.update(
        {
            "font.size": 12,
            "axes.titlesize": 14,
            "axes.labelsize": 12,
            "xtick.labelsize": 11,
            "ytick.labelsize": 11,
            "legend.fontsize": 11,
            "figure.dpi": 160,
            "savefig.dpi": 300,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.grid": True,
            "grid.alpha": 0.25,
            "axes.unicode_minus": False,  # 负号用 ASCII，避免中文字体缺 U+2212 变方块
        }
    )


def load_bag_for_phase(main_result: Path, phase: str) -> analyze_bag.BagData:
    bag_path = (main_result / phase / "bag_path.txt").read_text(encoding="utf-8").strip()
    chunks = analyze_bag.resolve_input_chunks(Path(bag_path))
    data = analyze_bag.read_bag_data(
        chunks=chunks,
        estimated_topic=analyze_bag.DEFAULT_ESTIMATED_TOPIC,
        truth_topics=analyze_bag.DEFAULT_TRUTH_TOPICS,
        bt_status_topic=analyze_bag.DEFAULT_BT_STATUS_TOPIC,
        diagnostics_topic=analyze_bag.DEFAULT_DIAGNOSTICS_TOPIC,
        magnetic_topic=analyze_bag.DEFAULT_MAGNETIC_TOPIC,
        cable_topic=analyze_bag.DEFAULT_CABLE_MARKER_TOPIC,
        terrain_topics=(
            analyze_bag.DEFAULT_SEABED_CLOUD_TOPIC,
            analyze_bag.DEFAULT_SEABED_CLOUD_THROTTLED_TOPIC,
        ),
        altitude_topic=analyze_bag.DEFAULT_ALTITUDE_TOPIC,
        controller_debug_topic="/auv/controller/debug",
        verbose=False,
    )
    analyze_bag.synthesize_diagnostics_from_odometry(data)
    return data


def plot_clearance_rmse(output_dir: Path, main_result: Path) -> None:
    plt = analyze_bag.plt
    labels = ["pid_baseline", "pid_terrain", "mpc_baseline", "mpc_terrain"]
    display = ["PID\nBaseline", "PID\nTerrain", "MPC\nBaseline", "MPC\nTerrain"]
    colors = ["#8da0cb", "#66c2a5", "#fc8d62", "#e78ac3"]
    summaries = {
        label: read_summary_csv(main_result / label / "analysis/summary_statistics.csv")
        for label in labels
    }
    rmse = [fval(summaries[label], "seabed_clearance_rmse_to_3m") for label in labels]

    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    x = np.arange(len(labels))
    bars = ax.bar(x, rmse, color=colors, edgecolor="black", linewidth=0.7)
    pid_terrain_rmse = fval(summaries["pid_terrain"], "seabed_clearance_rmse_to_3m")
    if math.isfinite(pid_terrain_rmse):
        ax.axhline(
            pid_terrain_rmse,
            color="#2ca02c",
            linestyle="--",
            linewidth=1.2,
            label=f"PID 地形跟随基准（{pid_terrain_rmse:.3f} m）",
        )
    ax.set_ylabel("对 3 m 目标的离地净空 RMSE（m）")
    ax.set_title("地形跟随离地净空误差：PID/MPC × 基线/地形")
    ax.set_xticks(x)
    ax.set_xticklabels(display)
    ax.set_ylim(0, max(rmse) * 1.22)
    for bar, value in zip(bars, rmse):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.03, f"{value:.3f}", ha="center", va="bottom", fontsize=9)
    ax.legend(frameon=False, loc="upper right")
    fig.text(0.01, 0.005, provenance_note(summaries), fontsize=7.5, color="#555555", ha="left", va="bottom")
    fig.tight_layout()
    save_figure(fig, output_dir, "terrain_clearance_rmse_pid_mpc")
    plt.close(fig)


def plot_clearance_safety(output_dir: Path, main_result: Path) -> None:
    plt = analyze_bag.plt
    labels = ["pid_baseline", "pid_terrain", "mpc_baseline", "mpc_terrain"]
    display = ["PID\nBaseline", "PID\nTerrain", "MPC\nBaseline", "MPC\nTerrain"]
    summaries = {
        label: read_summary_csv(main_result / label / "analysis/summary_statistics.csv")
        for label in labels
    }
    mean = [fval(summaries[label], "seabed_clearance_mean_m") for label in labels]
    std = [fval(summaries[label], "seabed_clearance_std_m") for label in labels]
    minv = [fval(summaries[label], "seabed_clearance_min_m") for label in labels]

    fig, ax = plt.subplots(figsize=(7.4, 4.4))
    x = np.arange(len(labels))
    ax.errorbar(x, mean, yerr=std, fmt="o", markersize=8, color="#1f77b4", ecolor="#1f77b4", capsize=5, label="均值 ± 标准差")
    ax.scatter(x, minv, marker="v", s=75, color="#d62728", label="最小离地净空")
    ax.axhline(3.0, color="black", linestyle="--", linewidth=1.1, label="目标净空 3 m")
    ax.axhline(1.5, color="#d62728", linestyle=":", linewidth=1.2, label="安全阈值 1.5 m")
    ax.set_ylabel("海底离地净空（m）")
    ax.set_title("离地净空分布与安全裕度")
    ax.set_xticks(x)
    ax.set_xticklabels(display)
    finite_upper = [m + s for m, s in zip(mean, std) if math.isfinite(m) and math.isfinite(s)]
    finite_lower = [v for v in minv if math.isfinite(v)] + [1.5]
    y_upper = max(finite_upper + [3.0]) + 0.6 if finite_upper else 5.2
    y_lower = min(finite_lower) - 0.4
    ax.set_ylim(y_lower, y_upper)
    ax.legend(frameon=False, ncol=2, loc="upper center")
    fig.text(0.01, 0.005, provenance_note(summaries), fontsize=7.5, color="#555555", ha="left", va="bottom")
    fig.tight_layout()
    save_figure(fig, output_dir, "terrain_clearance_safety_margin")
    plt.close(fig)


def plot_ablation(output_dir: Path, ablation_summary: Path) -> None:
    plt = analyze_bag.plt
    rows = read_table_csv(ablation_summary)
    terrains = [row["terrain"] for row in rows]
    rmse = [float(row["rmse"]) for row in rows]
    mean = [float(row["mean"]) for row in rows]
    std = [float(row["std"]) for row in rows]
    minv = [float(row["min"]) for row in rows]

    fig, axes = plt.subplots(1, 2, figsize=(9.2, 4.0), gridspec_kw={"width_ratios": [1, 1.15]})
    x = np.arange(len(terrains))
    axes[0].bar(x, rmse, color=["#a6d854", "#ffd92f", "#e5c494"], edgecolor="black", linewidth=0.7)
    axes[0].set_xticks(x)
    axes[0].set_xticklabels([terrain.upper() for terrain in terrains])
    axes[0].set_ylabel("对 3 m 目标的离地净空 RMSE（m）")
    axes[0].set_title("PID 地形消融")
    for idx, value in enumerate(rmse):
        axes[0].text(idx, value + 0.008, f"{value:.3f}", ha="center", va="bottom", fontsize=9)

    axes[1].errorbar(x, mean, yerr=std, fmt="o", markersize=8, capsize=5, color="#1f77b4", label="均值 ± 标准差")
    axes[1].scatter(x, minv, marker="v", s=70, color="#d62728", label="最小值")
    axes[1].axhline(3.0, color="black", linestyle="--", linewidth=1.1, label="目标 3 m")
    axes[1].axhline(1.5, color="#d62728", linestyle=":", linewidth=1.2, label="安全 1.5 m")
    axes[1].set_xticks(x)
    axes[1].set_xticklabels([terrain.upper() for terrain in terrains])
    axes[1].set_ylabel("海底离地净空（m）")
    axes[1].set_title("不同地形等级下的安全裕度")
    axes[1].set_ylim(1.2, 3.4)
    axes[1].legend(frameon=False, loc="lower center")
    fig.tight_layout()
    save_figure(fig, output_dir, "pid_terrain_low_mid_high_ablation")
    plt.close(fig)


def plot_command_contract(output_dir: Path) -> None:
    plt = analyze_bag.plt
    fig, ax = plt.subplots(figsize=(9.2, 4.6))
    ax.axis("off")
    boxes = [
        ("控制器", "pid / mpc / both", 0.08, 0.66, "#8da0cb"),
        ("模式", "baseline / terrain / both_modes", 0.38, 0.66, "#66c2a5"),
        ("地形等级", "default / low / mid / high / yaml", 0.68, 0.66, "#ffd92f"),
        ("阶段输出", "results/control/terrain_following_<TS>", 0.22, 0.28, "#e5c494"),
        ("分析", "summary_statistics.csv + figures", 0.58, 0.28, "#fc8d62"),
    ]
    for title, body, x0, y0, color in boxes:
        rect = plt.Rectangle((x0, y0), 0.24, 0.18, facecolor=color, edgecolor="black", linewidth=1.0, transform=ax.transAxes)
        ax.add_patch(rect)
        ax.text(x0 + 0.12, y0 + 0.115, title, ha="center", va="center", fontweight="bold", transform=ax.transAxes)
        ax.text(x0 + 0.12, y0 + 0.055, body, ha="center", va="center", fontsize=9, transform=ax.transAxes)
    for start, end in [
        ((0.32, 0.75), (0.38, 0.75)),
        ((0.62, 0.75), (0.68, 0.75)),
        ((0.50, 0.66), (0.34, 0.46)),
        ((0.80, 0.66), (0.70, 0.46)),
        ((0.46, 0.37), (0.58, 0.37)),
    ]:
        ax.annotate("", xy=end, xytext=start, xycoords="axes fraction", arrowprops={"arrowstyle": "->", "lw": 1.2})
    cmd = "bash scripts/run_terrain_benchmark.sh 60 pid terrain high"
    ax.text(0.5, 0.08, cmd, ha="center", va="center", family="monospace", fontsize=11, bbox={"boxstyle": "round,pad=0.35", "facecolor": "#f7f7f7", "edgecolor": "black"}, transform=ax.transAxes)
    ax.set_title("地形基准命令契约", fontsize=14, fontweight="bold")
    fig.tight_layout()
    save_figure(fig, output_dir, "terrain_benchmark_command_contract")
    plt.close(fig)


def diagnostics_arrays(
    data: analyze_bag.BagData,
    target_clearance_m: float,
    warmup_skip_s: float = 0.0,
) -> dict[str, np.ndarray]:
    diag = data.diagnostics
    if not diag.timestamps_ns:
        raise RuntimeError("No diagnostics samples available for t-z plotting.")
    start_ns = min(diag.timestamps_ns)
    t = analyze_bag.normalize_time_ns(diag.timestamps_ns, start_ns)
    depth = np.asarray(diag.depth_m, dtype=float)
    controller_target_depth = np.asarray(diag.target_depth_m, dtype=float)
    # WP-D: clearance uses the P0-1 real-altitude / point-cloud口径 (resolve_clearance_series),
    # NOT the localization constant-datum (seabed_depth_m=15.0 - depth) which forced a flat
    # seabed and contradicted the 3D undulating surface. seabed_depth is derived as
    # depth + real_clearance, so it now tracks the true terrain relief.
    clearance, clearance_source = analyze_bag.resolve_clearance_series(data)
    if clearance.shape[0] != depth.shape[0]:
        clearance = np.asarray(diag.seabed_clearance_m, dtype=float)
        clearance_source = "diag_constant_datum"
    seabed_depth = depth + clearance
    terrain_target_depth = seabed_depth - float(target_clearance_m)
    # WP-D: trim warm-up/dive transient so the t-z curves share the same window
    # as the summary statistics (compute_steady_state_mask, time mode).
    mask = analyze_bag.compute_steady_state_mask(
        diag,
        warmup_skip_s=float(warmup_skip_s),
        mode="time" if warmup_skip_s > 0.0 else "none",
        target_clearance_m=float(target_clearance_m),
    )
    if mask.shape[0] == t.shape[0] and np.any(mask):
        t = t[mask]
        depth = depth[mask]
        controller_target_depth = controller_target_depth[mask]
        clearance = clearance[mask]
        seabed_depth = seabed_depth[mask]
        terrain_target_depth = terrain_target_depth[mask]
    return {
        "t": t,
        "depth": depth,
        "target_depth": terrain_target_depth,
        "controller_target_depth": controller_target_depth,
        "clearance": clearance,
        "seabed_depth": seabed_depth,
        "clearance_source": clearance_source,
    }


def plot_tz_tracking(output_dir: Path, main_result: Path, target_clearance_m: float, warmup_skip_s: float = 0.0) -> None:
    plt = analyze_bag.plt
    phases = [("pid_terrain", "PID 地形"), ("mpc_terrain", "MPC 地形")]
    fig, axes = plt.subplots(2, 1, figsize=(8.0, 6.2), sharex=False)
    for ax, (phase, title) in zip(axes, phases):
        arrays = diagnostics_arrays(load_bag_for_phase(main_result, phase), target_clearance_m, warmup_skip_s)
        t = arrays["t"]
        source_label = {
            "real_altitude": "真实 DVL 高度",
            "terrain_cloud": "海底点云",
            "diag_constant_datum": "常值基准（旧）",
        }.get(str(arrays.get("clearance_source", "")), str(arrays.get("clearance_source", "")))
        ax.plot(t, arrays["seabed_depth"], color="#8c564b", linewidth=1.5, label=f"海底深度（深度 + {source_label}）")
        ax.plot(t, arrays["target_depth"], color="#2ca02c", linestyle="--", linewidth=1.4, label=f"目标深度（海底 - {target_clearance_m:.0f} m）")
        ax.plot(t, arrays["depth"], color="#1f77b4", linewidth=1.7, label="AUV 深度")
        ax.fill_between(t, arrays["target_depth"] - 0.25, arrays["target_depth"] + 0.25, color="#2ca02c", alpha=0.12, label="±0.25 m 目标带")
        ax.set_title(f"{title}（净空来源：{source_label}）")
        ax.set_ylabel("深度（向下为正，m）")
        ax.invert_yaxis()
        ax.legend(frameon=False, loc="best")
    axes[-1].set_xlabel("时间（s）")
    suptitle = "地形跟随 t-z 跟踪曲线"
    if warmup_skip_s > 0.0:
        suptitle += f"（已裁去预热 {warmup_skip_s:.0f} s）"
    fig.suptitle(suptitle, y=0.995, fontsize=14, fontweight="bold")
    fig.tight_layout()
    save_figure(fig, output_dir, "terrain_tz_tracking_pid_mpc")
    plt.close(fig)


def plot_3d_terrain_trajectory(output_dir: Path, main_result: Path, terrain_config: Path, target_clearance_m: float) -> None:
    """三维海底曲面 + PID 地形跟随轨迹。

    地形曲面由本次运行所用的确定性地形配置（``terrain_config``）重建，其公式与仿真
    ``synthetic_sensors._terrain_height`` 完全一致（seed/octaves/scale/amplitude/slope 同源），
    因此覆盖 AUV 全轨迹（x∈[15.8,62]）且与运行忠实对应。相比之下，bag 中发布的
    ``seabed_cloud`` 只是围绕原点的静态显示帧快照（x∈[-25,25]），与世界系轨迹脱节，
    直接叠加会造成``轨迹悬空''的误导，故不再用于本图。为诚实标注地形可信度，另叠加
    AUV 实测 DVL 海底高度沿程离散点作为验证锚：其与重建曲面沿程相关系数约 0.91、
    均值偏差约 0.06 m、标准差约 0.33 m。
    """
    plt = analyze_bag.plt
    data = load_bag_for_phase(main_result, "pid_terrain")
    estimated = analyze_bag.sort_position_series(data.estimated)
    if not estimated.timestamps_ns:
        raise RuntimeError("Estimated trajectory is missing.")

    traj_x = np.asarray(estimated.x, dtype=float)
    traj_y = np.asarray(estimated.y, dtype=float)
    traj_z_display = np.asarray(estimated.z, dtype=float)
    valid_traj = np.isfinite(traj_x) & np.isfinite(traj_y) & np.isfinite(traj_z_display)
    traj_x = traj_x[valid_traj]
    traj_y = traj_y[valid_traj]
    traj_z_display = traj_z_display[valid_traj]
    if traj_x.size == 0:
        raise RuntimeError("Estimated trajectory has no finite samples.")

    # --- 确定性地形重建（忠实于本次运行的地形公式，覆盖全轨迹）--------------------
    terrain_cfg = read_digital_twin_config(terrain_config)
    grid_x, grid_y, seabed_depth_grid = reconstruct_terrain_grid(
        x_values=traj_x,
        y_values=traj_y,
        terrain_cfg=terrain_cfg,
        padding_m=6.0,
        clamp_to_extent=False,  # 轨迹越过静态 ±extent 瓦片，地形公式对全程有定义
    )
    seabed_z_display = -seabed_depth_grid
    seabed_depth_min = float(np.nanmin(seabed_depth_grid))
    seabed_depth_span = max(float(np.nanmax(seabed_depth_grid) - seabed_depth_min), 1e-6)
    seabed_depth_traj = np.asarray(
        [terrain_depth_from_config(x_value, y_value, terrain_cfg) for x_value, y_value in zip(traj_x, traj_y)],
        dtype=float,
    )

    fig = plt.figure(figsize=(8.6, 6.4))
    ax = fig.add_subplot(111, projection="3d")

    ax.plot_surface(
        grid_x,
        grid_y,
        seabed_z_display,
        facecolors=plt.cm.viridis((seabed_depth_grid - seabed_depth_min) / seabed_depth_span),
        linewidth=0,
        antialiased=True,
        shade=False,
        alpha=0.55,
        rstride=1,
        cstride=1,
    )

    # --- AUV 实测 DVL 海底高度验证锚点（沿程离散点）------------------------------
    dvl_note = ""
    try:
        arrays = diagnostics_arrays(data, target_clearance_m, warmup_skip_s=0.0)
        if str(arrays.get("clearance_source", "")) == "real_altitude":
            est_t = analyze_bag.normalize_time_ns(estimated.timestamps_ns, min(estimated.timestamps_ns))
            meas_t = arrays["t"]
            meas_x = np.interp(meas_t, est_t, np.asarray(estimated.x, dtype=float))
            meas_y = np.interp(meas_t, est_t, np.asarray(estimated.y, dtype=float))
            meas_seabed = np.asarray(arrays["seabed_depth"], dtype=float)
            finite = np.isfinite(meas_x) & np.isfinite(meas_y) & np.isfinite(meas_seabed)
            if np.any(finite):
                mx = meas_x[finite]
                my = meas_y[finite]
                mz = -meas_seabed[finite]
                step = max(1, mx.size // 60)  # 稀疏化到约 60 个锚点，避免遮盖曲面
                ax.scatter(
                    mx[::step], my[::step], mz[::step],
                    color="#d62728", s=16, depthshade=False, alpha=0.9,
                    label="DVL 实测海底（验证锚）",
                )
                cfg_along = np.asarray(
                    [terrain_depth_from_config(x, y, terrain_cfg) for x, y in zip(mx, my)],
                    dtype=float,
                )
                corr = float(np.corrcoef(cfg_along, meas_seabed[finite])[0, 1])
                bias = float(np.mean(cfg_along - meas_seabed[finite]))
                rms = float(np.sqrt(np.mean((cfg_along - meas_seabed[finite]) ** 2)))
                dvl_note = f"\n重建 vs 实测：r={corr:.2f}，偏差 {bias:+.2f} m，RMS {rms:.2f} m"
    except Exception:
        dvl_note = ""

    target_depth = seabed_depth_traj - target_clearance_m
    target_z_display = -target_depth

    ax.plot(traj_x, traj_y, traj_z_display, color="#1f77b4", linewidth=2.4, label="AUV 轨迹")
    valid = np.isfinite(target_z_display)
    if np.any(valid):
        ax.plot(traj_x[valid], traj_y[valid], target_z_display[valid], color="#2ca02c", linestyle="--", linewidth=1.6, label="目标深度路径")
    ax.set_xlabel("x（m）")
    ax.set_ylabel("y（m）")
    ax.set_zlabel("显示 z（m）")
    ax.set_title("三维海底曲面与 PID 地形跟随轨迹")
    ax.text2D(
        0.02, 0.02,
        f"地形来源：确定性重建 {terrain_config.name}（seed={int(terrain_cfg.get('terrain_seed', 0))}）{dvl_note}",
        transform=ax.transAxes, fontsize=8, color="#333333",
    )
    ax.view_init(elev=26, azim=-62)
    ax.legend(frameon=False, loc="upper left")
    mappable = plt.cm.ScalarMappable(cmap="viridis")
    mappable.set_array(seabed_depth_grid)
    cbar = fig.colorbar(mappable, ax=ax, shrink=0.72, pad=0.08)
    cbar.set_label("海底深度（向下为正，m）")
    fig.tight_layout()
    save_figure(fig, output_dir, "terrain_3d_pid_terrain_trajectory")
    plt.close(fig)


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    setup_style()
    plot_clearance_rmse(args.output_dir, args.main_result)
    plot_clearance_safety(args.output_dir, args.main_result)
    plot_ablation(args.output_dir, args.ablation_summary)
    plot_command_contract(args.output_dir)
    plot_tz_tracking(args.output_dir, args.main_result, args.target_clearance_m, args.warmup_skip_s)
    plot_3d_terrain_trajectory(args.output_dir, args.main_result, args.terrain_config, args.target_clearance_m)
    print(args.output_dir)


if __name__ == "__main__":
    main()

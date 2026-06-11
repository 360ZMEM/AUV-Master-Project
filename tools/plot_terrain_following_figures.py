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
        default=PROJECT_ROOT / "results/control/terrain_following_20260610_175154",
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
    max_samples_per_axis: int = 80,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    resolution = max(float(terrain_cfg.get("terrain_resolution_m", 1.0)), 0.25)
    extent = float(terrain_cfg.get("terrain_extent_m", 50.0))
    x_min = max(float(np.nanmin(x_values)) - padding_m, -extent)
    x_max = min(float(np.nanmax(x_values)) + padding_m, extent)
    y_min = max(float(np.nanmin(y_values)) - padding_m, -extent)
    y_max = min(float(np.nanmax(y_values)) + padding_m, extent)

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
    plt.rcParams.update(
        {
            "font.size": 11,
            "axes.titlesize": 13,
            "axes.labelsize": 11,
            "xtick.labelsize": 10,
            "ytick.labelsize": 10,
            "legend.fontsize": 10,
            "figure.dpi": 160,
            "savefig.dpi": 300,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.grid": True,
            "grid.alpha": 0.25,
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
    ax.axhline(0.1752, color="#2ca02c", linestyle="--", linewidth=1.2, label="PID terrain reference (0.175 m)")
    ax.set_ylabel("Clearance RMSE to 3 m (m)")
    ax.set_title("Terrain-Following Clearance Error: PID/MPC x Baseline/Terrain")
    ax.set_xticks(x)
    ax.set_xticklabels(display)
    ax.set_ylim(0, max(rmse) * 1.22)
    for bar, value in zip(bars, rmse):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.03, f"{value:.3f}", ha="center", va="bottom", fontsize=9)
    ax.legend(frameon=False, loc="upper right")
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
    ax.errorbar(x, mean, yerr=std, fmt="o", markersize=8, color="#1f77b4", ecolor="#1f77b4", capsize=5, label="Mean +/- std")
    ax.scatter(x, minv, marker="v", s=75, color="#d62728", label="Minimum clearance")
    ax.axhline(3.0, color="black", linestyle="--", linewidth=1.1, label="Target clearance 3 m")
    ax.axhline(1.5, color="#d62728", linestyle=":", linewidth=1.2, label="Safety threshold 1.5 m")
    ax.set_ylabel("Seabed clearance (m)")
    ax.set_title("Clearance Distribution and Safety Margin")
    ax.set_xticks(x)
    ax.set_xticklabels(display)
    ax.set_ylim(1.2, 5.2)
    ax.legend(frameon=False, ncol=2, loc="upper center")
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
    axes[0].set_ylabel("Clearance RMSE to 3 m (m)")
    axes[0].set_title("PID Terrain Ablation")
    for idx, value in enumerate(rmse):
        axes[0].text(idx, value + 0.008, f"{value:.3f}", ha="center", va="bottom", fontsize=9)

    axes[1].errorbar(x, mean, yerr=std, fmt="o", markersize=8, capsize=5, color="#1f77b4", label="Mean +/- std")
    axes[1].scatter(x, minv, marker="v", s=70, color="#d62728", label="Minimum")
    axes[1].axhline(3.0, color="black", linestyle="--", linewidth=1.1, label="Target 3 m")
    axes[1].axhline(1.5, color="#d62728", linestyle=":", linewidth=1.2, label="Safety 1.5 m")
    axes[1].set_xticks(x)
    axes[1].set_xticklabels([terrain.upper() for terrain in terrains])
    axes[1].set_ylabel("Seabed clearance (m)")
    axes[1].set_title("Safety Margin Across Terrain Levels")
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
        ("Controller", "pid / mpc / both", 0.08, 0.66, "#8da0cb"),
        ("Mode", "baseline / terrain / both_modes", 0.38, 0.66, "#66c2a5"),
        ("Terrain Level", "default / low / mid / high / yaml", 0.68, 0.66, "#ffd92f"),
        ("Phase Output", "results/control/terrain_following_<TS>", 0.22, 0.28, "#e5c494"),
        ("Analysis", "summary_statistics.csv + figures", 0.58, 0.28, "#fc8d62"),
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
    ax.set_title("Terrain Benchmark Command Contract", fontsize=14, fontweight="bold")
    fig.tight_layout()
    save_figure(fig, output_dir, "terrain_benchmark_command_contract")
    plt.close(fig)


def diagnostics_arrays(data: analyze_bag.BagData, target_clearance_m: float) -> dict[str, np.ndarray]:
    diag = data.diagnostics
    if not diag.timestamps_ns:
        raise RuntimeError("No diagnostics samples available for t-z plotting.")
    start_ns = min(diag.timestamps_ns)
    t = analyze_bag.normalize_time_ns(diag.timestamps_ns, start_ns)
    depth = np.asarray(diag.depth_m, dtype=float)
    controller_target_depth = np.asarray(diag.target_depth_m, dtype=float)
    clearance = np.asarray(diag.seabed_clearance_m, dtype=float)
    seabed_depth = depth + clearance
    terrain_target_depth = seabed_depth - float(target_clearance_m)
    return {
        "t": t,
        "depth": depth,
        "target_depth": terrain_target_depth,
        "controller_target_depth": controller_target_depth,
        "clearance": clearance,
        "seabed_depth": seabed_depth,
    }


def plot_tz_tracking(output_dir: Path, main_result: Path, target_clearance_m: float) -> None:
    plt = analyze_bag.plt
    phases = [("pid_terrain", "PID Terrain"), ("mpc_terrain", "MPC Terrain")]
    fig, axes = plt.subplots(2, 1, figsize=(8.0, 6.2), sharex=False)
    for ax, (phase, title) in zip(axes, phases):
        arrays = diagnostics_arrays(load_bag_for_phase(main_result, phase), target_clearance_m)
        t = arrays["t"]
        ax.plot(t, arrays["seabed_depth"], color="#8c564b", linewidth=1.5, label="Seabed depth")
        ax.plot(t, arrays["target_depth"], color="#2ca02c", linestyle="--", linewidth=1.4, label=f"Target depth (seabed - {target_clearance_m:.0f} m)")
        ax.plot(t, arrays["depth"], color="#1f77b4", linewidth=1.7, label="AUV depth")
        ax.fill_between(t, arrays["target_depth"] - 0.25, arrays["target_depth"] + 0.25, color="#2ca02c", alpha=0.12, label="+/-0.25 m target band")
        ax.set_title(title)
        ax.set_ylabel("Depth positive down (m)")
        ax.invert_yaxis()
        ax.legend(frameon=False, loc="best")
    axes[-1].set_xlabel("Time (s)")
    fig.suptitle("Terrain-Following t-z Tracking Curves", y=0.995, fontsize=14, fontweight="bold")
    fig.tight_layout()
    save_figure(fig, output_dir, "terrain_tz_tracking_pid_mpc")
    plt.close(fig)


def plot_3d_terrain_trajectory(output_dir: Path, main_result: Path, terrain_config: Path, target_clearance_m: float) -> None:
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

    fig = plt.figure(figsize=(8.2, 6.2))
    ax = fig.add_subplot(111, projection="3d")

    source_note = "bag seabed point cloud"
    if data.terrain_points_xyz is not None:
        terrain = np.asarray(data.terrain_points_xyz, dtype=float)
        if terrain.shape[0] > 4500:
            rng = np.random.default_rng(42)
            terrain = terrain[rng.choice(terrain.shape[0], size=4500, replace=False)]
        sc = ax.scatter(terrain[:, 0], terrain[:, 1], terrain[:, 2], c=-terrain[:, 2], cmap="viridis", s=5, alpha=0.45, label="Seabed cloud")
        seabed_depth = analyze_bag.nearest_terrain_depths(
            terrain_points_xyz=data.terrain_points_xyz,
            x_values=traj_x,
            y_values=traj_y,
        )
    else:
        terrain_cfg = read_digital_twin_config(terrain_config)
        grid_x, grid_y, seabed_depth_grid = reconstruct_terrain_grid(
            x_values=traj_x,
            y_values=traj_y,
            terrain_cfg=terrain_cfg,
        )
        seabed_z_display = -seabed_depth_grid
        seabed_depth_min = float(np.nanmin(seabed_depth_grid))
        seabed_depth_span = max(float(np.nanmax(seabed_depth_grid) - seabed_depth_min), 1e-6)
        sc = ax.plot_surface(
            grid_x,
            grid_y,
            seabed_z_display,
            facecolors=plt.cm.viridis((seabed_depth_grid - seabed_depth_min) / seabed_depth_span),
            linewidth=0,
            antialiased=True,
            shade=False,
            alpha=0.58,
        )
        seabed_depth = np.asarray([terrain_depth_from_config(x_value, y_value, terrain_cfg) for x_value, y_value in zip(traj_x, traj_y)], dtype=float)
        source_note = f"reconstructed terrain: {terrain_config.name}"

    target_depth = seabed_depth - target_clearance_m
    target_z_display = -target_depth

    ax.plot(traj_x, traj_y, traj_z_display, color="#1f77b4", linewidth=2.2, label="AUV trajectory")
    valid = np.isfinite(target_z_display)
    if np.any(valid):
        ax.plot(traj_x[valid], traj_y[valid], target_z_display[valid], color="#2ca02c", linestyle="--", linewidth=1.6, label="Target depth path")
    ax.set_xlabel("x (m)")
    ax.set_ylabel("y (m)")
    ax.set_zlabel("Display z (m)")
    ax.set_title("3D Terrain Surface and PID Terrain-Following Trajectory")
    ax.text2D(0.02, 0.03, f"Terrain source: {source_note}", transform=ax.transAxes, fontsize=8)
    ax.view_init(elev=24, azim=-58)
    ax.legend(frameon=False, loc="upper left")
    mappable = plt.cm.ScalarMappable(cmap="viridis")
    if data.terrain_points_xyz is not None:
        mappable.set_array(-terrain[:, 2])
    else:
        mappable.set_array(seabed_depth_grid)
    cbar = fig.colorbar(mappable, ax=ax, shrink=0.72, pad=0.08)
    cbar.set_label("Seabed depth positive down (m)")
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
    plot_tz_tracking(args.output_dir, args.main_result, args.target_clearance_m)
    plot_3d_terrain_trajectory(args.output_dir, args.main_result, args.terrain_config, args.target_clearance_m)
    print(args.output_dir)


if __name__ == "__main__":
    main()

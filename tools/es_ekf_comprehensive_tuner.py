#!/usr/bin/env python3
"""
ES-EKF 综合参数调优脚本 - 针对 20260503_144254 MCAP 数据集。

系统性搜索 EKF 噪声参数和初始协方差，在指定数据集上评估性能，
找到最优参数组合，并生成 Markdown 报告。

使用 DVL 5Hz 降采样模拟真实声学 DVL 条件。

参数范围:
  - sigma_acc: IMU 加速度噪声
  - sigma_gyro: IMU 陀螺仪噪声
  - sigma_dvl: DVL 观测噪声
  - sigma_depth: 深度传感器噪声
  - init_P_diag: 初始协方差对角线

用法:
  python3 tools/es_ekf_comprehensive_tuner.py \
    --input log/experiments/20260503_144254/rosbag/rosbag_0.mcap \
    --output-dir ./tuning_results_20260503_144254
"""

from __future__ import annotations

import argparse
import copy
import json
import math
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = PROJECT_ROOT / "tools"
SIM_DIR = PROJECT_ROOT / "sim_holoocean"
ALGO_DIR = PROJECT_ROOT / "algorithm"

for p in (str(TOOLS_DIR), str(SIM_DIR), str(ALGO_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

# =============================================================================
# Baseline configuration from params.yaml
# =============================================================================

BASELINE_CONFIG = {
    "gravity": 9.81,
    "sigma_acc": 0.08,
    "sigma_gyro": 0.01,
    "sigma_ba": 0.001,
    "sigma_bg": 0.0005,
    "sigma_dvl": 0.03,
    "sigma_depth": 0.05,
    "sigma_gps_xy": 0.5,
    "imu_acc_is_linear": True,
    "init_pos": [0.0, 0.0, 0.0],
    "init_vel": [0.0, 0.0, 0.0],
    "init_quat_wxyz": [1.0, 0.0, 0.0, 0.0],
    "init_ba": [0.0, 0.0, 0.0],
    "init_bg": [0.0, 0.0, 0.0],
    "init_P_diag": [0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.2, 0.2, 0.2, 0.05, 0.05, 0.05, 0.05, 0.05, 0.05],
}

# =============================================================================
# Parameter search ranges
# =============================================================================

PARAM_RANGES = {
    "sigma_acc": [0.01, 0.02, 0.04, 0.08, 0.12, 0.16, 0.20, 0.30, 0.50],
    "sigma_gyro": [0.001, 0.002, 0.005, 0.01, 0.02, 0.03, 0.05, 0.08, 0.10],
    "sigma_dvl": [0.005, 0.01, 0.02, 0.03, 0.05, 0.08, 0.10, 0.15, 0.20, 0.30],
    "sigma_depth": [0.01, 0.02, 0.03, 0.05, 0.08, 0.10, 0.15, 0.20, 0.30],
}

INIT_P_SCALES = [0.1, 0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 5.0]

INIT_P_LABELS = [
    "position_x", "position_y", "position_z",
    "velocity_x", "velocity_y", "velocity_z",
    "attitude_w", "attitude_x", "attitude_y",
    "accel_bias_x", "accel_bias_y", "accel_bias_z",
    "gyro_bias_x", "gyro_bias_y", "gyro_bias_z",
]


@dataclass
class TuningResult:
    """存储单次参数评估的结果。"""
    params: dict
    rmse_xy: float
    rmse_z: float
    rmse_3d: float
    cep50: float
    max_drift: float
    max_error: float
    mean_error: float
    latency_us: float
    elapsed_s: float
    duration_s: float
    num_imu: int
    num_dvl: int
    num_depth: int
    num_truth: int
    innovation_stats: dict = field(default_factory=dict)
    error_time_series: np.ndarray = field(default_factory=lambda: np.array([]))
    time_series: np.ndarray = field(default_factory=lambda: np.array([]))


def build_config(
    sigma_acc: float | None = None,
    sigma_gyro: float | None = None,
    sigma_dvl: float | None = None,
    sigma_depth: float | None = None,
    p_scale: float = 1.0,
) -> dict:
    """根据给定参数构建 EKF 配置。"""
    cfg = copy.deepcopy(BASELINE_CONFIG)
    if sigma_acc is not None:
        cfg["sigma_acc"] = sigma_acc
    if sigma_gyro is not None:
        cfg["sigma_gyro"] = sigma_gyro
    if sigma_dvl is not None:
        cfg["sigma_dvl"] = sigma_dvl
    if sigma_depth is not None:
        cfg["sigma_depth"] = sigma_depth
    if p_scale != 1.0:
        cfg["init_P_diag"] = [v * p_scale for v in cfg["init_P_diag"]]
    return cfg


def get_p_scale(cfg: dict) -> float:
    """从配置中提取 P 尺度因子。"""
    base = BASELINE_CONFIG["init_P_diag"][0]
    if base == 0:
        return 1.0
    return cfg["init_P_diag"][0] / base


def downsample_dvl(dvl_samples: list, target_hz: float) -> list:
    """对 DVL 样本进行降采样。"""
    if target_hz is None or target_hz <= 0:
        return dvl_samples
    interval_ns = int(1e9 / target_hz)
    downsampled = []
    last_ts = -int(1e18)
    for s in dvl_samples:
        if s.ts_ns - last_ts >= interval_ns:
            downsampled.append(s)
            last_ts = s.ts_ns
    return downsampled


def run_single_eval(
    cfg: dict,
    imu_samples: list,
    dvl_samples: list,
    depth_samples: list,
    truth_samples: list,
) -> TuningResult:
    """运行单次 EKF 评估，返回 TuningResult。"""
    import importlib
    import offline_ekf_benchmark as bm
    importlib.reload(bm)
    bm.ensure_runtime_dependencies()

    engine = bm.EseKfEngine(cfg)

    imu_timestamps_ns = [s.ts_ns for s in imu_samples]
    dvl_timestamps_ns = [s.ts_ns for s in dvl_samples]
    depth_timestamps_ns = [s.ts_ns for s in depth_samples]
    truth_timestamps_ns = [s.ts_ns for s in truth_samples]

    all_event_ts = sorted(set(
        imu_timestamps_ns + dvl_timestamps_ns + depth_timestamps_ns + truth_timestamps_ns
    ))

    imu_idx = 0
    dvl_idx = 0
    depth_idx = 0
    last_imu_ts = None
    perf_times = []

    t_start = time.perf_counter()

    for event_ts in all_event_ts:
        while imu_idx < len(imu_samples) and imu_samples[imu_idx].ts_ns <= event_ts:
            imu = imu_samples[imu_idx]
            dt = (imu.ts_ns - last_imu_ts) / 1e9 if last_imu_ts is not None else 0.02
            last_imu_ts = imu.ts_ns
            t0 = time.perf_counter()
            engine.predict(imu.acc, imu.gyro, dt)
            perf_times.append(time.perf_counter() - t0)
            imu_idx += 1

        while dvl_idx < len(dvl_samples) and dvl_samples[dvl_idx].ts_ns <= event_ts:
            dvl = dvl_samples[dvl_idx]
            t0 = time.perf_counter()
            engine.update_dvl(dvl.vel, dvl.ts_ns)
            perf_times.append(time.perf_counter() - t0)
            dvl_idx += 1

        while depth_idx < len(depth_samples) and depth_samples[depth_idx].ts_ns <= event_ts:
            depth = depth_samples[depth_idx]
            t0 = time.perf_counter()
            engine.update_depth(depth.depth_m, depth.ts_ns)
            perf_times.append(time.perf_counter() - t0)
            depth_idx += 1

        if event_ts in truth_timestamps_ns:
            engine.record_state(event_ts)

    elapsed = time.perf_counter() - t_start
    est_ts = np.array(engine.history_ts, dtype=np.int64)
    est_p = np.array(engine.history_p, dtype=float) if engine.history_p else np.empty((0, 3))

    duration_s = (truth_samples[-1].ts_ns - truth_samples[0].ts_ns) / 1e9 if truth_samples else 0

    if est_p.ndim != 2 or est_p.shape[0] < 2:
        return TuningResult(
            params=cfg, rmse_xy=float("nan"), rmse_z=float("nan"),
            rmse_3d=float("nan"), cep50=float("nan"), max_drift=float("nan"),
            max_error=float("nan"), mean_error=float("nan"),
            latency_us=np.mean(perf_times)*1e6 if perf_times else float("nan"),
            elapsed_s=elapsed, duration_s=duration_s,
            num_imu=len(imu_samples), num_dvl=len(dvl_samples),
            num_depth=len(depth_samples), num_truth=len(truth_samples),
            innovation_stats={},
        )

    truth_ts_arr = np.array([s.ts_ns for s in truth_samples], dtype=np.int64)
    truth_pos = np.array([s.pos for s in truth_samples], dtype=float)
    truth_at_est = bm._resample_to_truth(est_ts, truth_ts_arr, truth_pos)

    if truth_at_est.shape[0] < 2:
        return TuningResult(
            params=cfg, rmse_xy=float("nan"), rmse_z=float("nan"),
            rmse_3d=float("nan"), cep50=float("nan"), max_drift=float("nan"),
            max_error=float("nan"), mean_error=float("nan"),
            latency_us=np.mean(perf_times)*1e6 if perf_times else float("nan"),
            elapsed_s=elapsed, duration_s=duration_s,
            num_imu=len(imu_samples), num_dvl=len(dvl_samples),
            num_depth=len(depth_samples), num_truth=len(truth_samples),
            innovation_stats={},
        )

    errors_3d = np.linalg.norm(est_p - truth_at_est, axis=1)

    rmse_xy = bm.compute_rmse_xy(est_p, truth_at_est)
    rmse_z = bm.compute_rmse_z(est_p, truth_at_est)
    rmse_3d = bm.compute_rmse(est_p, truth_at_est)
    cep50 = bm.compute_cep(est_p, truth_at_est)
    max_drift = bm.compute_max_drift(est_p, truth_at_est)
    max_error = float(np.max(errors_3d))
    mean_error = float(np.mean(errors_3d))
    latency_us = np.mean(perf_times) * 1e6 if perf_times else float("nan")

    innov = np.array(engine.innovation_history, dtype=float)
    innov_stats = {}
    if innov.size > 0:
        gate = 3.0 * cfg.get("sigma_dvl", 0.03)
        innov_stats = {
            "mean": float(np.mean(innov)),
            "std": float(np.std(innov)),
            "max": float(np.max(innov)),
            "min": float(np.min(innov)),
            "within_3sigma_pct": float(np.mean(np.abs(innov) < gate) * 100),
        }

    truth_t_sec = (truth_ts_arr - truth_ts_arr[0]) / 1e9
    time_series = truth_t_sec

    return TuningResult(
        params=cfg, rmse_xy=rmse_xy, rmse_z=rmse_z, rmse_3d=rmse_3d,
        cep50=cep50, max_drift=max_drift, max_error=max_error,
        mean_error=mean_error, latency_us=latency_us, elapsed_s=elapsed,
        duration_s=duration_s, num_imu=len(imu_samples), num_dvl=len(dvl_samples),
        num_depth=len(depth_samples), num_truth=len(truth_samples),
        innovation_stats=innov_stats,
        error_time_series=errors_3d, time_series=time_series,
    )


def load_dataset(mcap_path: Path, truth_topics: list[str], dvl_downsample_hz: float = 5.0):
    """加载 MCAP 数据集，可选 DVL 降采样。"""
    import importlib
    import offline_ekf_benchmark as bm
    importlib.reload(bm)
    bm.ensure_runtime_dependencies()

    imu, dvl, depth, truth = bm.read_mcap_sensor_data(
        mcap_path=mcap_path,
        imu_topic="/auv/sensors/imu",
        dvl_topic="/auv/sensors/dvl",
        depth_topic="/auv/sensors/depth",
        truth_topics=truth_topics,
        dvl_frame="world",
        apply_coord_transform=True,
        verbose=True,
    )

    if dvl_downsample_hz is not None and dvl_downsample_hz > 0:
        original_count = len(dvl)
        dvl = downsample_dvl(dvl, dvl_downsample_hz)
        print(f"  DVL downsampled: {original_count} -> {len(dvl)} samples")

    return imu, dvl, depth, truth


def run_sensitivity_analysis(
    imu, dvl, depth, truth,
    base_cfg: dict,
    param_name: str,
    param_values: list[float],
) -> list[TuningResult]:
    """单参数灵敏度分析：一次只改变一个参数。"""
    results = []
    print(f"    Testing {param_name} with {len(param_values)} values...")
    for i, val in enumerate(param_values):
        if param_name == "init_P_diag":
            cfg = build_config(p_scale=val)
        else:
            cfg = build_config(**{param_name: val})
        r = run_single_eval(cfg, imu, dvl, depth, truth)
        r.params["_sensitivity_param"] = param_name
        r.params["_sensitivity_value"] = val
        results.append(r)
    return results


def run_combination_sweep(
    imu, dvl, depth, truth,
    param1_name: str, param1_values: list,
    param2_name: str, param2_values: list,
) -> list[TuningResult]:
    """两参数组合扫描。"""
    results = []
    total = len(param1_values) * len(param2_values)
    print(f"    Testing {param1_name} x {param2_name}: {total} combinations...")
    count = 0
    for v1 in param1_values:
        for v2 in param2_values:
            kwargs = {}
            if param1_name == "init_P_diag":
                kwargs["p_scale"] = v1
            else:
                kwargs[param1_name] = v1
            if param2_name == "init_P_diag":
                kwargs["p_scale"] = v2
            else:
                kwargs[param2_name] = v2
            cfg = build_config(**kwargs)
            r = run_single_eval(cfg, imu, dvl, depth, truth)
            r.params["_combo_param1"] = param1_name
            r.params["_combo_val1"] = v1
            r.params["_combo_param2"] = param2_name
            r.params["_combo_val2"] = v2
            results.append(r)
            count += 1
            if count % 20 == 0:
                best_so_far = min((res.rmse_3d for res in results if not math.isnan(res.rmse_3d)), default=float("inf"))
                print(f"      [{count}/{total}] Best RMSE so far: {best_so_far:.4f}")
    return results


def summarize_results(results: list[TuningResult], top_n: int = 10) -> str:
    """将结果格式化为表格字符串。"""
    lines = []
    header = (
        f"{'Rank':>4} | {'RMSE_3D':>8} | {'RMSE_XY':>8} | {'RMSE_Z':>8} | "
        f"{'CEP50':>8} | {'MaxErr':>8} | {'sigma_acc':>9} | {'sigma_gyro':>10} | "
        f"{'sigma_dvl':>9} | {'sigma_depth':>11} | {'P_scale':>7}"
    )
    lines.append(header)
    lines.append("-" * len(header))

    valid = [r for r in results if not math.isnan(r.rmse_3d)]
    valid.sort(key=lambda r: r.rmse_3d)

    for i, r in enumerate(valid[:top_n]):
        p = r.params
        sa = p.get("sigma_acc", BASELINE_CONFIG["sigma_acc"])
        sg = p.get("sigma_gyro", BASELINE_CONFIG["sigma_gyro"])
        sd = p.get("sigma_dvl", BASELINE_CONFIG["sigma_dvl"])
        sd2 = p.get("sigma_depth", BASELINE_CONFIG["sigma_depth"])
        ps = get_p_scale(p)

        marker = ""
        if "_sensitivity_param" in p:
            marker = f" ({p['_sensitivity_param']}={p['_sensitivity_value']})"
        elif "_combo_param1" in p:
            marker = f" ({p['_combo_param1']}={p['_combo_val1']}, {p['_combo_param2']}={p['_combo_val2']})"

        row = (
            f"{i + 1:4d} | {r.rmse_3d:8.4f} | {r.rmse_xy:8.4f} | {r.rmse_z:8.4f} "
            f"| {r.cep50:8.4f} | {r.max_error:8.4f} "
            f"| {sa:9.4f} | {sg:10.4f} | {sd:9.4f} | {sd2:11.4f} | {ps:7.2f}"
            f"{marker}"
        )
        lines.append(row)

    return "\n".join(lines)


def generate_plots(results: list[TuningResult], baseline: TuningResult, best: TuningResult, output_dir: Path):
    """生成可视化图表。"""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams["font.family"] = "serif"
    plt.rcParams["font.size"] = 10
    plt.rcParams["axes.grid"] = True
    plt.rcParams["grid.alpha"] = 0.3

    # 1. Sensitivity curves for each parameter
    param_names = ["sigma_acc", "sigma_gyro", "sigma_dvl", "sigma_depth"]

    for param_name in param_names:
        param_results = [r for r in results if r.params.get("_sensitivity_param") == param_name]
        if not param_results:
            continue

        param_results.sort(key=lambda r: r.params["_sensitivity_value"])
        x_vals = [r.params["_sensitivity_value"] for r in param_results]
        rmse_3d_vals = [r.rmse_3d for r in param_results]
        rmse_xy_vals = [r.rmse_xy for r in param_results]
        rmse_z_vals = [r.rmse_z for r in param_results]

        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(9, 6), sharex=True)

        ax1.plot(x_vals, rmse_3d_vals, "o-", linewidth=1.5, markersize=4, label="RMSE 3D")
        ax1.axhline(baseline.rmse_3d, color="red", linestyle="--", alpha=0.7, label=f"Baseline RMSE 3D ({baseline.rmse_3d:.4f})")
        ax1.axvline(best.params.get(param_name, BASELINE_CONFIG[param_name]), color="green", linestyle="--", alpha=0.7, label=f"Best {param_name}")
        ax1.set_ylabel("RMSE 3D (m)")
        ax1.set_title(f"Sensitivity Analysis: {param_name}")
        ax1.legend(loc="best", fontsize=8)

        ax2.plot(x_vals, rmse_xy_vals, "o-", linewidth=1.5, markersize=4, label="RMSE XY", color="tab:orange")
        ax2.plot(x_vals, rmse_z_vals, "s-", linewidth=1.5, markersize=4, label="RMSE Z", color="tab:green")
        ax2.set_xlabel(param_name)
        ax2.set_ylabel("RMSE (m)")
        ax2.legend(loc="best", fontsize=8)

        plt.tight_layout()
        fig.savefig(output_dir / f"sensitivity_{param_name}.png", dpi=200, bbox_inches="tight")
        plt.close(fig)

    # 2. P scale sensitivity
    p_scale_results = [r for r in results if r.params.get("_sensitivity_param") == "init_P_diag"]
    if p_scale_results:
        p_scale_results.sort(key=lambda r: r.params["_sensitivity_value"])
        x_vals = [r.params["_sensitivity_value"] for r in p_scale_results]
        rmse_3d_vals = [r.rmse_3d for r in p_scale_results]
        cep50_vals = [r.cep50 for r in p_scale_results]
        max_drift_vals = [r.max_drift for r in p_scale_results]

        fig, ax = plt.subplots(figsize=(9, 5))
        ax.plot(x_vals, rmse_3d_vals, "o-", linewidth=1.5, markersize=4, label="RMSE 3D")
        ax.plot(x_vals, cep50_vals, "s-", linewidth=1.5, markersize=4, label="CEP50")
        ax.plot(x_vals, max_drift_vals, "^-", linewidth=1.5, markersize=4, label="Max Drift")
        ax.axhline(baseline.rmse_3d, color="red", linestyle="--", alpha=0.7, label=f"Baseline RMSE 3D ({baseline.rmse_3d:.4f})")
        ax.set_xlabel("Init P Scale Factor")
        ax.set_ylabel("Error Metric (m)")
        ax.set_title("Sensitivity Analysis: Initial Covariance Scale")
        ax.legend(loc="best", fontsize=8)
        ax.set_xscale("log")

        plt.tight_layout()
        fig.savefig(output_dir / "sensitivity_init_P_diag.png", dpi=200, bbox_inches="tight")
        plt.close(fig)

    # 3. 2D heatmap for sigma_dvl vs sigma_acc
    combo_results = [r for r in results if "_combo_param1" in r.params]
    if combo_results:
        dvl_vs_acc = [r for r in combo_results
                      if (r.params.get("_combo_param1") == "sigma_dvl" and r.params.get("_combo_param2") == "sigma_acc")
                      or (r.params.get("_combo_param1") == "sigma_acc" and r.params.get("_combo_param2") == "sigma_dvl")]
        if dvl_vs_acc:
            # Extract unique values
            if dvl_vs_acc[0].params.get("_combo_param1") == "sigma_dvl":
                dvl_vals = sorted(set(r.params["_combo_val1"] for r in dvl_vs_acc))
                acc_vals = sorted(set(r.params["_combo_val2"] for r in dvl_vs_acc))
            else:
                dvl_vals = sorted(set(r.params["_combo_val2"] for r in dvl_vs_acc))
                acc_vals = sorted(set(r.params["_combo_val1"] for r in dvl_vs_acc))

            heatmap = np.full((len(dvl_vals), len(acc_vals)), np.nan)
            for r in dvl_vs_acc:
                if r.params.get("_combo_param1") == "sigma_dvl":
                    di = dvl_vals.index(r.params["_combo_val1"])
                    ai = acc_vals.index(r.params["_combo_val2"])
                else:
                    di = dvl_vals.index(r.params["_combo_val2"])
                    ai = acc_vals.index(r.params["_combo_val1"])
                heatmap[di, ai] = r.rmse_3d

            fig, ax = plt.subplots(figsize=(10, 7))
            im = ax.imshow(heatmap, aspect="auto", cmap="viridis", origin="lower",
                          extent=[acc_vals[0], acc_vals[-1], dvl_vals[0], dvl_vals[-1]])
            cbar = fig.colorbar(im, ax=ax)
            cbar.set_label("RMSE 3D (m)")
            ax.set_xlabel("sigma_acc")
            ax.set_ylabel("sigma_dvl")
            ax.set_title("RMSE 3D Heatmap: sigma_dvl vs sigma_acc")
            ax.set_xscale("log")
            ax.set_yscale("log")

            plt.tight_layout()
            fig.savefig(output_dir / "heatmap_dvl_vs_acc.png", dpi=200, bbox_inches="tight")
            plt.close(fig)

    # 4. dvl vs depth heatmap
    dvl_vs_depth = [r for r in combo_results
                    if (r.params.get("_combo_param1") == "sigma_dvl" and r.params.get("_combo_param2") == "sigma_depth")
                    or (r.params.get("_combo_param1") == "sigma_depth" and r.params.get("_combo_param2") == "sigma_dvl")]
    if dvl_vs_depth:
        if dvl_vs_depth[0].params.get("_combo_param1") == "sigma_dvl":
            dvl_vals = sorted(set(r.params["_combo_val1"] for r in dvl_vs_depth))
            depth_vals = sorted(set(r.params["_combo_val2"] for r in dvl_vs_depth))
        else:
            dvl_vals = sorted(set(r.params["_combo_val2"] for r in dvl_vs_depth))
            depth_vals = sorted(set(r.params["_combo_val1"] for r in dvl_vs_depth))

        heatmap = np.full((len(dvl_vals), len(depth_vals)), np.nan)
        for r in dvl_vs_depth:
            if r.params.get("_combo_param1") == "sigma_dvl":
                di = dvl_vals.index(r.params["_combo_val1"])
                depth_i = depth_vals.index(r.params["_combo_val2"])
            else:
                di = dvl_vals.index(r.params["_combo_val2"])
                depth_i = depth_vals.index(r.params["_combo_val1"])
            heatmap[di, depth_i] = r.rmse_3d

        fig, ax = plt.subplots(figsize=(10, 7))
        im = ax.imshow(heatmap, aspect="auto", cmap="viridis", origin="lower",
                      extent=[depth_vals[0], depth_vals[-1], dvl_vals[0], dvl_vals[-1]])
        cbar = fig.colorbar(im, ax=ax)
        cbar.set_label("RMSE 3D (m)")
        ax.set_xlabel("sigma_depth")
        ax.set_ylabel("sigma_dvl")
        ax.set_title("RMSE 3D Heatmap: sigma_dvl vs sigma_depth")
        ax.set_xscale("log")
        ax.set_yscale("log")

        plt.tight_layout()
        fig.savefig(output_dir / "heatmap_dvl_vs_depth.png", dpi=200, bbox_inches="tight")
        plt.close(fig)

    # 5. Error comparison bar chart (top 20 configurations)
    valid = [r for r in results if not math.isnan(r.rmse_3d)]
    valid.sort(key=lambda r: r.rmse_3d)
    top20 = valid[:20]

    fig, ax = plt.subplots(figsize=(12, 6))
    x = np.arange(len(top20))
    width = 0.35

    ax.bar(x - width/2, [r.rmse_xy for r in top20], width, label="RMSE XY", color="tab:blue", alpha=0.8)
    ax.bar(x + width/2, [r.rmse_z for r in top20], width, label="RMSE Z", color="tab:orange", alpha=0.8)
    ax.set_xticks(x)
    ax.set_xticklabels([f"{i+1}" for i in range(len(top20))], fontsize=8)
    ax.set_xlabel("Configuration Rank")
    ax.set_ylabel("RMSE (m)")
    ax.set_title("Top 20 Configurations: XY vs Z Error")
    ax.legend()

    plt.tight_layout()
    fig.savefig(output_dir / "top20_xy_vs_z.png", dpi=200, bbox_inches="tight")
    plt.close(fig)

    # 6. Correlation scatter plots
    all_valid = [r for r in results if not math.isnan(r.rmse_3d)]

    fig, axes = plt.subplots(2, 2, figsize=(12, 10))
    axes = axes.flatten()

    params_to_plot = ["sigma_acc", "sigma_gyro", "sigma_dvl", "sigma_depth"]
    for ax, param_name in zip(axes, params_to_plot):
        vals = [r.params.get(param_name, BASELINE_CONFIG[param_name]) for r in all_valid]
        rmse = [r.rmse_3d for r in all_valid]
        ax.scatter(vals, rmse, alpha=0.5, s=20)
        ax.set_xlabel(param_name)
        ax.set_ylabel("RMSE 3D (m)")
        ax.set_title(f"{param_name} vs RMSE 3D")
        ax.set_xscale("log")

    plt.tight_layout()
    fig.savefig(output_dir / "correlation_scatter.png", dpi=200, bbox_inches="tight")
    plt.close(fig)

    # 7. P scale vs RMSE
    p_results = [r for r in all_valid if get_p_scale(r.params) != 1.0 or "_sensitivity_param" in r.params]
    if p_results:
        fig, ax = plt.subplots(figsize=(9, 5))
        scales = [get_p_scale(r.params) for r in p_results]
        rmse = [r.rmse_3d for r in p_results]
        ax.scatter(scales, rmse, alpha=0.5, s=20)
        ax.axhline(baseline.rmse_3d, color="red", linestyle="--", alpha=0.7, label=f"Baseline ({baseline.rmse_3d:.4f})")
        ax.set_xlabel("Init P Scale")
        ax.set_ylabel("RMSE 3D (m)")
        ax.set_title("Initial Covariance Scale vs RMSE 3D")
        ax.set_xscale("log")
        ax.legend()
        plt.tight_layout()
        fig.savefig(output_dir / "p_scale_vs_rmse.png", dpi=200, bbox_inches="tight")
        plt.close(fig)


def generate_report(
    all_results: list[TuningResult],
    baseline: TuningResult,
    best: TuningResult,
    output_dir: Path,
    input_path: Path,
    dvl_downsample_hz: float,
    total_elapsed: float,
):
    """生成详细的 Markdown 报告。"""
    lines = []
    lines.append("# ES-EKF 综合参数调优报告")
    lines.append("")
    lines.append(f"**生成时间**: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"**数据集**: `{input_path}`")
    lines.append(f"**DVL 降采样**: {dvl_downsample_hz} Hz")
    lines.append(f"**总评估次数**: {len(all_results)}")
    lines.append(f"**总耗时**: {total_elapsed:.1f} 秒 ({total_elapsed/60:.1f} 分钟)")
    lines.append("")

    # 基线性能
    improvement = (baseline.rmse_3d - best.rmse_3d) / baseline.rmse_3d * 100 if baseline.rmse_3d > 0 else 0
    improvement_xy = (baseline.rmse_xy - best.rmse_xy) / baseline.rmse_xy * 100 if baseline.rmse_xy > 0 else 0
    improvement_z = (baseline.rmse_z - best.rmse_z) / baseline.rmse_z * 100 if baseline.rmse_z > 0 else 0

    lines.append("## 1. 性能摘要")
    lines.append("")
    lines.append("| 指标 | 基线 | 最优 | 改善 |")
    lines.append("|------|------|------|------|")
    lines.append(f"| RMSE 3D (m) | {baseline.rmse_3d:.4f} | {best.rmse_3d:.4f} | {improvement:.1f}% |")
    lines.append(f"| RMSE XY (m) | {baseline.rmse_xy:.4f} | {best.rmse_xy:.4f} | {improvement_xy:.1f}% |")
    lines.append(f"| RMSE Z (m) | {baseline.rmse_z:.4f} | {best.rmse_z:.4f} | {improvement_z:.1f}% |")
    lines.append(f"| CEP50 (m) | {baseline.cep50:.4f} | {best.cep50:.4f} | - |")
    lines.append(f"| Max Error (m) | {baseline.max_error:.4f} | {best.max_error:.4f} | - |")
    lines.append(f"| Mean Error (m) | {baseline.mean_error:.4f} | {best.mean_error:.4f} | - |")
    lines.append(f"| 平均延迟 (μs) | {baseline.latency_us:.1f} | {best.latency_us:.1f} | - |")
    lines.append("")

    # 参数对比
    lines.append("## 2. 最优参数对比")
    lines.append("")
    lines.append("| 参数 | 基线值 | 最优值 | 变化倍数 |")
    lines.append("|------|--------|--------|---------|")
    for key in ["sigma_acc", "sigma_gyro", "sigma_dvl", "sigma_depth"]:
        base_val = BASELINE_CONFIG[key]
        opt_val = best.params.get(key, base_val)
        ratio = opt_val / base_val if base_val != 0 else float("inf")
        arrow = "↓" if opt_val < base_val else ("↑" if opt_val > base_val else "=")
        lines.append(f"| {key} | {base_val} | {opt_val} | {ratio:.2f}x {arrow} |")

    base_p = BASELINE_CONFIG["init_P_diag"]
    opt_p = best.params.get("init_P_diag", base_p)
    p_scale = get_p_scale(best.params)
    lines.append(f"| init_P_diag | {base_p[0]} | {opt_p[0]} | {p_scale:.2f}x {'↓' if p_scale < 1 else ('↑' if p_scale > 1 else '=')} |")
    lines.append("")

    lines.append("### 完整最优 init_P_diag 向量")
    lines.append("")
    lines.append("```")
    for i, (label, val) in enumerate(zip(INIT_P_LABELS, opt_p)):
        base_val = base_p[i]
        change = "↓" if val < base_val else ("↑" if val > base_val else "=")
        lines.append(f"  {label:20s}: {val:8.4f}  (base: {base_val:8.4f}) {change}")
    lines.append("```")
    lines.append("")

    # 单参数灵敏度分析结果
    lines.append("## 3. 单参数灵敏度分析")
    lines.append("")

    for param_name in ["sigma_acc", "sigma_gyro", "sigma_dvl", "sigma_depth"]:
        param_results = [r for r in all_results if r.params.get("_sensitivity_param") == param_name]
        if not param_results:
            continue

        param_results.sort(key=lambda r: r.params["_sensitivity_value"])
        base_val = BASELINE_CONFIG[param_name]
        best_r = min(param_results, key=lambda r: r.rmse_3d if not math.isnan(r.rmse_3d) else float("inf"))
        best_val = best_r.params["_sensitivity_value"]

        lines.append(f"### 3.1 {param_name}")
        lines.append("")
        lines.append(f"- **基线值**: {base_val}")
        lines.append(f"- **最优值**: {best_val}")
        lines.append(f"- **最优 RMSE 3D**: {best_r.rmse_3d:.4f}m")
        lines.append(f"- **变化范围**: {param_results[0].params['_sensitivity_value']} ~ {param_results[-1].params['_sensitivity_value']}")
        lines.append("")

        # 灵敏度指标
        rmse_values = [r.rmse_3d for r in param_results if not math.isnan(r.rmse_3d)]
        if len(rmse_values) > 1:
            sensitivity = (max(rmse_values) - min(rmse_values)) / BASELINE_CONFIG[param_name]
            lines.append(f"- **绝对灵敏度**: {sensitivity:.4f} (RMSE 变化 / 参数变化)")
            cv = np.std(rmse_values) / np.mean(rmse_values) * 100
            lines.append(f"- **变异系数**: {cv:.1f}%")
        lines.append("")

        # 数据表
        lines.append("| 参数值 | 相对基线 | RMSE 3D (m) | RMSE XY (m) | RMSE Z (m) | 标记 |")
        lines.append("|--------|----------|-------------|-------------|------------|------|")
        for r in param_results:
            pval = r.params["_sensitivity_value"]
            ratio = pval / base_val if base_val != 0 else 0
            marker = ""
            if abs(r.rmse_3d - best.rmse_3d) < 0.0001:
                marker = " **最优**"
            if abs(ratio - 1.0) < 0.01:
                marker = " 基线"
            lines.append(f"| {pval:.6f} | {ratio:.2f}x | {r.rmse_3d:.4f} | {r.rmse_xy:.4f} | {r.rmse_z:.4f} |{marker}|")
        lines.append("")
        lines.append(f"![{param_name} 灵敏度曲线](sensitivity_{param_name}.png)")
        lines.append("")

    # Init P sensitivity
    p_results = [r for r in all_results if r.params.get("_sensitivity_param") == "init_P_diag"]
    if p_results:
        p_results.sort(key=lambda r: r.params["_sensitivity_value"])
        best_p_r = min(p_results, key=lambda r: r.rmse_3d if not math.isnan(r.rmse_3d) else float("inf"))
        best_p_scale = best_p_r.params["_sensitivity_value"]

        lines.append("### 3.5 init_P_diag (协方差尺度)")
        lines.append("")
        lines.append(f"- **基线尺度**: 1.0")
        lines.append(f"- **最优尺度**: {best_p_scale}")
        lines.append(f"- **最优 RMSE 3D**: {best_p_r.rmse_3d:.4f}m")
        lines.append("")

        lines.append("| P 尺度 | RMSE 3D (m) | RMSE XY (m) | RMSE Z (m) | CEP50 (m) | Max Drift (m) | 标记 |")
        lines.append("|--------|-------------|-------------|------------|-----------|---------------|------|")
        for r in p_results:
            pval = r.params["_sensitivity_value"]
            marker = " **最优**" if abs(r.rmse_3d - best.rmse_3d) < 0.0001 else ""
            if abs(pval - 1.0) < 0.01:
                marker = " 基线"
            lines.append(f"| {pval:.2f} | {r.rmse_3d:.4f} | {r.rmse_xy:.4f} | {r.rmse_z:.4f} | {r.cep50:.4f} | {r.max_drift:.4f} |{marker}|")
        lines.append("")
        lines.append("![init_P_diag 灵敏度曲线](sensitivity_init_P_diag.png)")
        lines.append("")

    # 两参数组合分析
    lines.append("## 4. 两参数组合分析")
    lines.append("")

    combos = [
        ("sigma_dvl", "sigma_acc"),
        ("sigma_dvl", "sigma_depth"),
        ("sigma_acc", "sigma_gyro"),
    ]

    for p1, p2 in combos:
        combo_results = [r for r in all_results
                        if (r.params.get("_combo_param1") == p1 and r.params.get("_combo_param2") == p2)
                        or (r.params.get("_combo_param1") == p2 and r.params.get("_combo_param2") == p1)]
        if not combo_results:
            continue

        best_combo = min(combo_results, key=lambda r: r.rmse_3d if not math.isnan(r.rmse_3d) else float("inf"))

        lines.append(f"### 4.1 {p1} x {p2}")
        lines.append("")
        lines.append(f"- **最优组合 RMSE 3D**: {best_combo.rmse_3d:.4f}m")
        if p1 == "sigma_dvl" and p2 == "sigma_acc":
            lines.append(f"![{p1} vs {p2} 热力图](heatmap_dvl_vs_acc.png)")
        elif p1 == "sigma_dvl" and p2 == "sigma_depth":
            lines.append(f"![{p1} vs {p2} 热力图](heatmap_dvl_vs_depth.png)")
        lines.append("")

        # 前 15 结果
        combo_results.sort(key=lambda r: r.rmse_3d)
        lines.append("| Rank | RMSE 3D | RMSE XY | RMSE Z | CEP50 | Max Error |")
        lines.append("|------|---------|---------|--------|-------|-----------|")
        for i, r in enumerate(combo_results[:15]):
            lines.append(f"| {i+1} | {r.rmse_3d:.4f} | {r.rmse_xy:.4f} | {r.rmse_z:.4f} | {r.cep50:.4f} | {r.max_error:.4f} |")
        lines.append("")

    # 总体 Top 20
    lines.append("## 5. 总体 Top 20 配置")
    lines.append("")
    lines.append(summarize_results(all_results, top_n=20))
    lines.append("")
    lines.append("![Top 20 XY vs Z 误差](top20_xy_vs_z.png)")
    lines.append("")

    # 相关性分析
    lines.append("## 6. 相关性分析")
    lines.append("")
    lines.append("![参数相关性散点图](correlation_scatter.png)")
    lines.append("")

    valid = [r for r in all_results if not math.isnan(r.rmse_3d)]
    if valid:
        lines.append("### 6.1 参数-RMSE 相关系数")
        lines.append("")
        lines.append("| 参数 | Pearson 相关系数 | 相关性强度 |")
        lines.append("|------|------------------|-----------|")

        for param_name in ["sigma_acc", "sigma_gyro", "sigma_dvl", "sigma_depth"]:
            vals = [r.params.get(param_name, BASELINE_CONFIG[param_name]) for r in valid]
            rmse = [r.rmse_3d for r in valid]
            if len(vals) > 2:
                corr = np.corrcoef(np.log(vals), rmse)[0, 1]
                strength = "强" if abs(corr) > 0.7 else ("中等" if abs(corr) > 0.4 else "弱")
                lines.append(f"| {param_name} | {corr:.4f} | {strength} ({'正' if corr > 0 else '负'}) |")
        lines.append("")

    # 创新统计
    lines.append("## 7. 滤波器创新统计")
    lines.append("")

    lines.append("| 配置 | 创新均值 | 创新标准差 | 创新最大值 | 3σ 内百分比 |")
    lines.append("|------|----------|-----------|-----------|-------------|")

    baseline_innov = baseline.innovation_stats
    best_innov = best.innovation_stats

    if baseline_innov:
        lines.append(
            f"| 基线 | {baseline_innov.get('mean', 0):.4f} | "
            f"{baseline_innov.get('std', 0):.4f} | "
            f"{baseline_innov.get('max', 0):.4f} | "
            f"{baseline_innov.get('within_3sigma_pct', 0):.1f}% |"
        )
    if best_innov:
        lines.append(
            f"| 最优 | {best_innov.get('mean', 0):.4f} | "
            f"{best_innov.get('std', 0):.4f} | "
            f"{best_innov.get('max', 0):.4f} | "
            f"{best_innov.get('within_3sigma_pct', 0):.1f}% |"
        )
    lines.append("")

    # 经验总结与建议
    lines.append("## 8. 经验总结与调优建议")
    lines.append("")

    lines.append("### 8.1 关键发现")
    lines.append("")

    # sigma_acc analysis
    sa_best = best.params.get("sigma_acc", BASELINE_CONFIG["sigma_acc"])
    sa_base = BASELINE_CONFIG["sigma_acc"]
    if sa_best < sa_base:
        lines.append(f"- **sigma_acc**: 最优值 {sa_best} < 基线 {sa_base}，说明 IMU 加速度数据质量较好，应给予更高信任度。")
    elif sa_best > sa_base:
        lines.append(f"- **sigma_acc**: 最优值 {sa_best} > 基线 {sa_base}，说明 IMU 加速度噪声较大。")
    else:
        lines.append(f"- **sigma_acc**: 最优值与基线相同。")

    # sigma_gyro analysis
    sg_best = best.params.get("sigma_gyro", BASELINE_CONFIG["sigma_gyro"])
    sg_base = BASELINE_CONFIG["sigma_gyro"]
    if sg_best < sg_base:
        lines.append(f"- **sigma_gyro**: 最优值 {sg_best} < 基线 {sg_base}，说明 IMU 陀螺仪数据质量较好。")
    elif sg_best > sg_base:
        lines.append(f"- **sigma_gyro**: 最优值 {sg_best} > 基线 {sg_base}，说明 IMU 陀螺仪噪声较大。")
    else:
        lines.append(f"- **sigma_gyro**: 最优值与基线相同。")

    # sigma_dvl analysis
    sd_best = best.params.get("sigma_dvl", BASELINE_CONFIG["sigma_dvl"])
    sd_base = BASELINE_CONFIG["sigma_dvl"]
    if sd_best < sd_base:
        lines.append(f"- **sigma_dvl**: 最优值 {sd_best} < 基线 {sd_base}，说明 DVL 数据质量较好（5Hz 降采样后），应给予更高信任度。")
    elif sd_best > sd_base:
        lines.append(f"- **sigma_dvl**: 最优值 {sd_best} > 基线 {sd_base}，说明 DVL 数据存在较大噪声。")
    else:
        lines.append(f"- **sigma_dvl**: 最优值与基线相同。")

    # sigma_depth analysis
    sd2_best = best.params.get("sigma_depth", BASELINE_CONFIG["sigma_depth"])
    sd2_base = BASELINE_CONFIG["sigma_depth"]
    if sd2_best < sd2_base:
        lines.append(f"- **sigma_depth**: 最优值 {sd2_best} < 基线 {sd2_base}，说明深度传感器数据质量较好。")
    elif sd2_best > sd2_base:
        lines.append(f"- **sigma_depth**: 最优值 {sd2_best} > 基线 {sd2_base}，说明深度传感器噪声较大。")
    else:
        lines.append(f"- **sigma_depth**: 最优值与基线相同。")

    # init_P analysis
    p_scale = get_p_scale(best.params)
    if p_scale < 1.0:
        lines.append(f"- **init_P_diag**: 最优 P 尺度因子 {p_scale} < 1.0，说明滤波器初始置信度应更高（更小的不确定性）。")
    elif p_scale > 1.0:
        lines.append(f"- **init_P_diag**: 最优 P 尺度因子 {p_scale} > 1.0，说明滤波器初始应更保守（更大的不确定性）。")
    else:
        lines.append(f"- **init_P_diag**: 基线值已经合适。")

    lines.append("")
    lines.append("### 8.2 调优建议")
    lines.append("")
    lines.append("1. **优先调整 sigma_dvl**：DVL 观测噪声对定位精度影响最大，是最敏感的参数。")
    lines.append("2. **sigma_gyro 对航向精度至关重要**：在转向场景下尤为明显。")
    lines.append("3. **初始协方差 P 不宜过大**：过大的 P 会导致初期发散。")
    lines.append("4. **sigma_acc 影响速度估计精度**：加速度噪声直接影响速度积分的协方差增长。")
    lines.append("5. **sigma_depth 影响 Z 轴精度**：深度观测噪声直接影响深度估计的准确性。")
    lines.append("6. **使用多数据集验证**：在不同海况、不同运动模式下验证最优参数的鲁棒性。")
    lines.append("7. **考虑在线自适应调参**：根据创新序列的统计特性动态调整噪声参数。")
    lines.append("")

    # 推荐配置
    lines.append("### 8.3 推荐参数配置")
    lines.append("")
    lines.append("```yaml")
    lines.append("ekf:")
    lines.append(f"  sigma_acc: {best.params.get('sigma_acc', BASELINE_CONFIG['sigma_acc'])}")
    lines.append(f"  sigma_gyro: {best.params.get('sigma_gyro', BASELINE_CONFIG['sigma_gyro'])}")
    lines.append(f"  sigma_dvl: {best.params.get('sigma_dvl', BASELINE_CONFIG['sigma_dvl'])}")
    lines.append(f"  sigma_depth: {best.params.get('sigma_depth', BASELINE_CONFIG['sigma_depth'])}")
    lines.append(f"  sigma_ba: {best.params.get('sigma_ba', BASELINE_CONFIG['sigma_ba'])}")
    lines.append(f"  sigma_bg: {best.params.get('sigma_bg', BASELINE_CONFIG['sigma_bg'])}")
    lines.append("  imu_acc_is_linear: true")
    lines.append(f"  init_P_diag: [{', '.join(f'{v:.6f}' for v in best.params.get('init_P_diag', BASELINE_CONFIG['init_P_diag']))}]")
    lines.append("```")
    lines.append("")

    lines.append("---")
    lines.append(f"*报告生成于 {time.strftime('%Y-%m-%d %H:%M:%S')}*")

    report_path = output_dir / "tuning_report.md"
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"  报告已保存: {report_path}")


def main():
    parser = argparse.ArgumentParser(description="ES-EKF 综合参数调优工具")
    parser.add_argument("--input", type=Path, required=True, help="输入 MCAP 文件路径")
    parser.add_argument("--output-dir", type=Path, default=None, help="输出目录")
    parser.add_argument("--truth-topics", default="/auv/sensors/ground_truth,/auv/state/truth,/auv/visual/truth_marker")
    parser.add_argument("--dvl-downsample-hz", type=float, default=5.0, help="DVL 降采样频率 (默认: 5.0 Hz)")
    parser.add_argument("--skip-plots", action="store_true", help="跳过图表生成")

    args = parser.parse_args()

    if not args.input.exists():
        raise SystemExit(f"Input file not found: {args.input}")

    output_dir = args.output_dir or Path("results/tuning")
    output_dir.mkdir(parents=True, exist_ok=True)

    truth_topic_list = [t.strip() for t in args.truth_topics.split(",") if t.strip()]

    print("=" * 70)
    print("  ES-EKF 综合参数调优")
    print("=" * 70)
    print(f"  输入文件: {args.input}")
    print(f"  输出目录: {output_dir}")
    print(f"  DVL 降采样: {args.dvl_downsample_hz} Hz")
    print()

    overall_start = time.perf_counter()

    # 加载数据集
    print("[1/6] 加载数据集 ...")
    imu, dvl, depth, truth = load_dataset(args.input, truth_topic_list, args.dvl_downsample_hz)
    duration_s = (truth[-1].ts_ns - truth[0].ts_ns) / 1e9 if truth else 0
    print(f"  时长: {duration_s:.1f}s")
    print(f"  IMU: {len(imu)} ({len(imu)/duration_s:.1f} Hz)")
    print(f"  DVL: {len(dvl)} ({len(dvl)/duration_s:.1f} Hz) [降采样后]")
    print(f"  Depth: {len(depth)}")
    print(f"  Truth: {len(truth)}")
    print()

    all_results = []

    # 运行基线
    print("[2/6] 运行基线配置 ...")
    baseline_cfg = copy.deepcopy(BASELINE_CONFIG)
    baseline = run_single_eval(baseline_cfg, imu, dvl, depth, truth)
    all_results.append(baseline)
    print(f"  基线 RMSE_3D: {baseline.rmse_3d:.4f}m")
    print(f"  基线 RMSE_XY: {baseline.rmse_xy:.4f}m")
    print(f"  基线 RMSE_Z:  {baseline.rmse_z:.4f}m")
    print()

    # 单参数灵敏度分析
    print("[3/6] 运行单参数灵敏度分析 ...")
    for param_name, param_values in PARAM_RANGES.items():
        print(f"  --- {param_name} ---")
        results = run_sensitivity_analysis(imu, dvl, depth, truth, BASELINE_CONFIG, param_name, param_values)
        all_results.extend(results)
        best_r = min(results, key=lambda r: r.rmse_3d if not math.isnan(r.rmse_3d) else float("inf"))
        print(f"  Best {param_name}: {best_r.params.get('_sensitivity_value', '?')}, RMSE_3D: {best_r.rmse_3d:.4f}m")
    print()

    # Init P scale sensitivity
    print("  --- init_P_diag ---")
    p_results = run_sensitivity_analysis(imu, dvl, depth, truth, BASELINE_CONFIG, "init_P_diag", INIT_P_SCALES)
    all_results.extend(p_results)
    best_p = min(p_results, key=lambda r: r.rmse_3d if not math.isnan(r.rmse_3d) else float("inf"))
    print(f"  Best P_scale: {best_p.params.get('_sensitivity_value', '?')}, RMSE_3D: {best_p.rmse_3d:.4f}m")
    print()

    # 两参数组合扫描
    print("[4/6] 运行两参数组合扫描 ...")
    combo_pairs = [
        ("sigma_dvl", "sigma_acc"),
        ("sigma_dvl", "sigma_depth"),
        ("sigma_acc", "sigma_gyro"),
    ]
    for p1, p2 in combo_pairs:
        print(f"  --- {p1} x {p2} ---")
        results = run_combination_sweep(
            imu, dvl, depth, truth,
            p1, PARAM_RANGES[p1],
            p2, PARAM_RANGES[p2],
        )
        all_results.extend(results)
        best_combo = min(results, key=lambda r: r.rmse_3d if not math.isnan(r.rmse_3d) else float("inf"))
        print(f"  Best combo RMSE_3D: {best_combo.rmse_3d:.4f}m")
    print()

    # 找出最优结果
    print("[5/6] 汇总结果 ...")
    valid = [r for r in all_results if not math.isnan(r.rmse_3d)]
    best = min(valid, key=lambda r: r.rmse_3d)

    print("\n" + "=" * 70)
    print("  总体 Top 10 结果")
    print("=" * 70)
    print(summarize_results(all_results, top_n=10))

    improvement = (baseline.rmse_3d - best.rmse_3d) / baseline.rmse_3d * 100 if baseline.rmse_3d > 0 else 0
    print(f"\n  基线 RMSE_3D: {baseline.rmse_3d:.4f}m")
    print(f"  最优 RMSE_3D: {best.rmse_3d:.4f}m")
    print(f"  性能提升:   {improvement:.1f}%")
    print()

    # 生成图表
    if not args.skip_plots:
        print("[6/6] 生成可视化图表 ...")
        generate_plots(all_results, baseline, best, output_dir)
        print("  图表生成完成")
    else:
        print("[6/6] 跳过图表生成 (--skip-plots)")

    # 生成报告
    total_elapsed = time.perf_counter() - overall_start
    generate_report(all_results, baseline, best, output_dir, args.input, args.dvl_downsample_hz, total_elapsed)

    # 保存 JSON 结果
    result_data = {
        "input_file": str(args.input),
        "dvl_downsample_hz": args.dvl_downsample_hz,
        "duration_s": duration_s,
        "total_evaluations": len(all_results),
        "total_elapsed_s": total_elapsed,
        "baseline": {
            "params": {k: v for k, v in baseline.params.items() if not str(k).startswith("_")},
            "rmse_xy": baseline.rmse_xy,
            "rmse_z": baseline.rmse_z,
            "rmse_3d": baseline.rmse_3d,
            "cep50": baseline.cep50,
            "max_drift": baseline.max_drift,
            "max_error": baseline.max_error,
            "mean_error": baseline.mean_error,
        },
        "best": {
            "params": {k: v for k, v in best.params.items() if not str(k).startswith("_")},
            "rmse_xy": best.rmse_xy,
            "rmse_z": best.rmse_z,
            "rmse_3d": best.rmse_3d,
            "cep50": best.cep50,
            "max_drift": best.max_drift,
            "max_error": best.max_error,
            "mean_error": best.mean_error,
            "improvement_pct": round(improvement, 2),
        },
        "top_20": [],
    }

    for r in sorted(valid, key=lambda r: r.rmse_3d)[:20]:
        result_data["top_20"].append({
            "rmse_xy": r.rmse_xy,
            "rmse_z": r.rmse_z,
            "rmse_3d": r.rmse_3d,
            "cep50": r.cep50,
            "max_error": r.max_error,
            "sigma_dvl": r.params.get("sigma_dvl"),
            "sigma_acc": r.params.get("sigma_acc"),
            "sigma_gyro": r.params.get("sigma_gyro"),
            "sigma_depth": r.params.get("sigma_depth"),
            "p_scale": get_p_scale(r.params),
        })

    with open(output_dir / "tuning_results.json", "w", encoding="utf-8") as f:
        json.dump(result_data, f, indent=2, ensure_ascii=False)
    print(f"  结果已保存: {output_dir / 'tuning_results.json'}")

    print("\n" + "=" * 70)
    print("  调优完成!")
    print("=" * 70)


if __name__ == "__main__":
    main()

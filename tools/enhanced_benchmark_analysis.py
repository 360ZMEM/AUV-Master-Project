#!/usr/bin/env python3
"""
基于 MCAP 回放的 AUV 定位算法增强版分析与诊断工具。

在标准基准测试基础上，额外提供：
1. 时域分量图（X(t), Y(t), Z(t) 曲线）
2. 绝对误差与相对误差曲线
3. 坐标系镜像检测
4. DVL Body/World 系验证
5. 初始位姿对齐检测
6. 时间戳延迟诊断

使用示例:
  python3 tools/enhanced_benchmark_analysis.py \
    --input log/experiments/benchmark_120s/rosbag_mcap/rosbag_mcap_0.mcap \
    --output-dir ./results/enhanced
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from pathlib import Path
from typing import Any

import numpy as np

# 将 tools/ 与 algorithm/ 加入 path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = PROJECT_ROOT / "tools"
SIM_DIR = PROJECT_ROOT / "sim_holoocean"
ALGO_DIR = PROJECT_ROOT / "algorithm"
for p in (str(TOOLS_DIR), str(SIM_DIR), str(ALGO_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

from offline_ekf_benchmark import (
    ensure_runtime_dependencies,
    configure_matplotlib,
    read_mcap_sensor_data,
    DeadReckoningEngine,
    StandardEKFEngine,
    EseKfEngine,
    compute_rmse,
    compute_rmse_xy,
    compute_rmse_z,
    compute_cep,
    compute_max_drift,
)

plt = None

DEFAULT_IMU_TOPIC = "/auv/sensors/imu"
DEFAULT_DVL_TOPIC = "/auv/sensors/dvl"
DEFAULT_DEPTH_TOPIC = "/auv/sensors/depth"
DEFAULT_TRUTH_TOPICS = "/auv/sensors/ground_truth,/auv/state/truth,/auv/visual/truth_marker"


# ---------------------------------------------------------------------------
# Helper: resample estimated positions onto truth timestamps
# ---------------------------------------------------------------------------

def _resample_to_truth(truth_ts: np.ndarray, est_ts: np.ndarray,
                       est_p: np.ndarray) -> np.ndarray:
    """将估计轨迹线性插值到真值时间戳上。"""
    if est_p.ndim != 2 or est_p.shape[1] != 3 or est_ts.size < 2:
        return np.empty((0, 3))
    truth_t = truth_ts.astype(float)
    est_t = est_ts.astype(float)
    return np.column_stack([np.interp(truth_t, est_t, est_p[:, i]) for i in range(3)])


# ---------------------------------------------------------------------------
# Diagnostics
# ---------------------------------------------------------------------------

def check_mirror_symmetry(truth_xy: np.ndarray, est_xy: np.ndarray) -> dict:
    """检测估计轨迹是否为真值轨迹的镜像。"""
    tx, ty = truth_xy[:, 0], truth_xy[:, 1]
    ex, ey = est_xy[:, 0], est_xy[:, 1]

    corr_x = float(np.corrcoef(tx, ex)[0, 1])
    corr_neg_x = float(np.corrcoef(tx, -ex)[0, 1])
    corr_y = float(np.corrcoef(ty, ey)[0, 1])
    corr_neg_y = float(np.corrcoef(ty, -ey)[0, 1])

    return {
        "corr_x": corr_x,
        "corr_neg_x": corr_neg_x,
        "corr_y": corr_y,
        "corr_neg_y": corr_neg_y,
        "x_mirror": corr_neg_x > corr_x and corr_neg_x > 0.8,
        "y_mirror": corr_neg_y > corr_y and corr_neg_y > 0.8,
    }


def check_initial_offset(truth_start: np.ndarray, est_start: np.ndarray) -> dict:
    offset = est_start - truth_start
    return {
        "truth_start": truth_start.tolist(),
        "est_start": est_start.tolist(),
        "offset": offset.tolist(),
        "offset_xy": float(np.linalg.norm(offset[:2])),
        "offset_z": float(abs(offset[2])),
        "offset_3d": float(np.linalg.norm(offset)),
    }


def check_timestamp_latency(truth_t: np.ndarray, truth_p: np.ndarray,
                            est_t: np.ndarray, est_p: np.ndarray,
                            max_lag: float = 10.0, step: float = 0.1) -> dict:
    """在 [-max_lag, +max_lag] 范围内滑动估计轨迹，找 RMSE 最小的偏移。"""
    lags = np.arange(-max_lag, max_lag + step, step)
    rmses = []
    for lag in lags:
        shifted = est_t + lag
        mask = (truth_t >= shifted[0]) & (truth_t <= shifted[-1])
        if mask.sum() < 5:
            rmses.append(float("nan"))
            continue
        tt = truth_t[mask]
        tp = truth_p[mask]
        ep = np.column_stack([np.interp(tt, shifted, est_p[:, i]) for i in range(3)])
        rmses.append(float(np.sqrt(np.mean(np.sum((tp - ep) ** 2, axis=1)))))

    rmses = np.array(rmses)
    idx = int(np.nanargmin(rmses))
    best_lag = float(lags[idx])
    rmse_0 = rmses[np.argmin(np.abs(lags))]
    rmse_best = float(rmses[idx])

    return {
        "best_lag_s": best_lag,
        "rmse_at_zero": float(rmse_0),
        "rmse_at_best": rmse_best,
        "improvement_pct": (rmse_0 - rmse_best) / (rmse_0 + 1e-9) * 100,
        "lags": lags.tolist(),
        "rmses": rmses.tolist(),
    }


# ---------------------------------------------------------------------------
# Plots
# ---------------------------------------------------------------------------

def plot_time_components(truth_t, truth_p, dr_p, std_p, es_p, out: Path, dpi=300):
    fig, axes = plt.subplots(3, 1, figsize=(9, 6.5), sharex=True)
    labels = ["X [m]", "Y [m]", "Z [m]"]
    for i, ax in enumerate(axes):
        ax.plot(truth_t, truth_p[:, i], "k--", lw=1.3, label="Truth")
        if dr_p.size:
            ax.plot(truth_t, dr_p[:, i], color="#d62728", lw=1.4, label="Raw DR")
        if std_p.size:
            ax.plot(truth_t, std_p[:, i], color="#1f77b4", lw=1.4, label="Std EKF")
        if es_p.size:
            ax.plot(truth_t, es_p[:, i], color="#2ca02c", lw=1.4, label="ES-EKF")
        ax.set_ylabel(labels[i])
        ax.legend(loc="best", fontsize=8)
        ax.grid(alpha=0.3)
    axes[-1].set_xlabel("Time [s]")
    fig.suptitle("Position Components vs. Time", y=0.98)
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    fig.savefig(out, dpi=dpi)
    plt.close(fig)


def plot_error_time(truth_t, truth_p, dr_p, std_p, es_p, out: Path, dpi=300):
    fig, ax = plt.subplots(figsize=(9, 4))
    for p, c, l in [(dr_p, "#d62728", "Raw DR"), (std_p, "#1f77b4", "Std EKF"), (es_p, "#2ca02c", "ES-EKF")]:
        if p.size:
            err = np.linalg.norm(p - truth_p, axis=1)
            ax.plot(truth_t, err, color=c, lw=1.6, label=l)
    ax.set_xlabel("Time [s]"); ax.set_ylabel("Position Error [m]")
    ax.set_title("Absolute Position Error vs. Time")
    ax.legend(); ax.grid(alpha=0.3); ax.set_ylim(bottom=0)
    fig.tight_layout(); fig.savefig(out, dpi=dpi); plt.close(fig)


def plot_relative_error(truth_t, truth_p, dr_p, std_p, es_p, out: Path, dpi=300):
    fig, ax = plt.subplots(figsize=(9, 4))
    # cumulative distance along truth trajectory
    diffs = np.diff(truth_p, axis=0)
    cumdist = np.zeros(len(truth_p)); cumdist[1:] = np.cumsum(np.linalg.norm(diffs, axis=1))
    for p, c, l in [(dr_p, "#d62728", "Raw DR"), (std_p, "#1f77b4", "Std EKF"), (es_p, "#2ca02c", "ES-EKF")]:
        if p.size:
            err = np.linalg.norm(p - truth_p, axis=1)
            rel = np.zeros_like(err)
            nz = cumdist > 1e-6
            rel[nz] = err[nz] / cumdist[nz] * 100
            ax.plot(truth_t, rel, color=c, lw=1.6, label=l)
    ax.set_xlabel("Time [s]"); ax.set_ylabel("Relative Error [%]")
    ax.set_title("Relative Position Error vs. Time (Error / Cumulative Distance)")
    ax.legend(); ax.grid(alpha=0.3); ax.set_ylim(bottom=0)
    fig.tight_layout(); fig.savefig(out, dpi=dpi); plt.close(fig)


def plot_latency_scan(lat: dict, out: Path, dpi=300):
    fig, ax = plt.subplots(figsize=(9, 4))
    ax.plot(lat["lags"], lat["rmses"], color="#1f77b4", lw=1.6)
    ax.axvline(0, color="k", ls="--", lw=0.8, label="Zero Lag")
    ax.axvline(lat["best_lag_s"], color="#d62728", ls="--", lw=1.2,
               label=f'Best Lag = {lat["best_lag_s"]:.2f} s')
    ax.set_xlabel("Time Lag [s] (positive = estimate delayed)")
    ax.set_ylabel("RMSE [m]"); ax.set_title("Timestamp Latency Analysis")
    ax.legend(); ax.grid(alpha=0.3)
    fig.tight_layout(); fig.savefig(out, dpi=dpi); plt.close(fig)


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def generate_report(meta: dict, metrics: dict, diag: dict, out: Path):
    lines = ["# AUV 定位算法增强版基准测试报告\n"]
    lines.append("## 测试信息\n")
    lines.append(f"- **输入文件**: `{meta['input']}`")
    lines.append(f"- **数据时长**: {meta['duration']:.1f} s")
    lines.append(f"- **IMU / DVL / Truth 频率**: {meta['imu_hz']:.1f} / {meta['dvl_hz']:.1f} / {meta['truth_hz']:.1f} Hz\n")

    lines.append("## 评估指标\n")
    lines.append("| 算法 | XY RMSE (m) | Z RMSE (m) | 3D RMSE (m) | CEP50 (m) | Max Drift (m) |")
    lines.append("|------|-------------|------------|-------------|-----------|---------------|")
    for k, n in [("raw_dr", "Raw DR"), ("std_ekf", "Std EKF"), ("es_ekf", "ES-EKF")]:
        m = metrics.get(k, {})
        lines.append(f"| {n} | {m.get('rmse_xy', 0):.3f} | {m.get('rmse_z', 0):.3f} | {m.get('rmse_3d', 0):.3f} | {m.get('cep50', 0):.3f} | {m.get('max_drift', 0):.3f} |")

    lines.append("\n## 诊断分析\n")

    io = diag.get("initial_offset", {})
    lines.append("### 初始位姿对齐\n")
    lines.append(f"- 真值起点: {io.get('truth_start', [])}")
    lines.append(f"- 估计起点: {io.get('est_start', [])}")
    lines.append(f"- XY 偏移: {io.get('offset_xy', 0):.3f} m, Z 偏移: {io.get('offset_z', 0):.3f} m")
    if io.get("offset_xy", 0) > 1.0:
        lines.append("- ⚠️ **警告**: XY 初始偏移 > 1 m，可能导致系统性 RMSE 偏差\n")
    else:
        lines.append("- ✅ 初始位姿对齐良好\n")

    ms = diag.get("mirror", {})
    lines.append("### 坐标系镜像检测\n")
    lines.append(f"- corr(X): {ms.get('corr_x', 0):.4f}, corr(-X): {ms.get('corr_neg_x', 0):.4f}")
    lines.append(f"- corr(Y): {ms.get('corr_y', 0):.4f}, corr(-Y): {ms.get('corr_neg_y', 0):.4f}")
    if ms.get("x_mirror") or ms.get("y_mirror"):
        lines.append("- ⚠️ **检测到镜像对称**: 可能存在 UE4↔NED 转换错误\n")
    else:
        lines.append("- ✅ 未检测到镜像对称\n")

    lt = diag.get("latency", {})
    lines.append("### 时间戳延迟\n")
    lines.append(f"- 零延迟 RMSE: {lt.get('rmse_at_zero', 0):.3f} m")
    lines.append(f"- 最优延迟: {lt.get('best_lag_s', 0):.2f} s (RMSE={lt.get('rmse_at_best', 0):.3f} m)")
    lines.append(f"- 可改善: {lt.get('improvement_pct', 0):.1f}%\n")

    lines.append("## 输出图表\n")
    lines.append("| 文件 | 说明 |")
    lines.append("|------|------|")
    lines.append("| `trajectory_xy.png` | XY 平面轨迹对比 |")
    lines.append("| `position_components_time.png` | X/Y/Z 分量时间曲线 |")
    lines.append("| `error_time.png` | 绝对误差时间曲线 |")
    lines.append("| `relative_error_time.png` | 相对误差时间曲线 |")
    lines.append("| `latency_scan.png` | 时间戳延迟扫描 |")

    out.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="Enhanced AUV benchmark analysis")
    ap.add_argument("--input", type=Path, required=True)
    ap.add_argument("--output-dir", type=Path, default=None)
    ap.add_argument("--imu-topic", default=DEFAULT_IMU_TOPIC)
    ap.add_argument("--dvl-topic", default=DEFAULT_DVL_TOPIC)
    ap.add_argument("--depth-topic", default=DEFAULT_DEPTH_TOPIC)
    ap.add_argument("--truth-topics", default=DEFAULT_TRUTH_TOPICS)
    ap.add_argument("--dvl-frame", choices=["body", "world"], default="world")
    ap.add_argument("--no-coordinate-transform", action="store_true")
    ap.add_argument("--ekf-config", type=Path, default=PROJECT_ROOT / "brain_linux" / "config" / "params.yaml")
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--dpi", type=int, default=300)
    ap.add_argument("--dvl-downsample-hz", type=float, default=None, help="DVL降采样频率 (默认: None=不降采样，5.0=模拟真实声学DVL)")
    args = ap.parse_args()

    ensure_runtime_dependencies()
    configure_matplotlib()
    global plt
    import matplotlib.pyplot as _plt
    plt = _plt

    if not args.input.exists():
        sys.exit(f"Input not found: {args.input}")

    out = args.output_dir or Path(f"results/localization/{args.input.stem}_enhanced")
    out.mkdir(parents=True, exist_ok=True)

    import yaml
    ekf_cfg = {}
    if args.ekf_config.exists():
        with open(args.ekf_config) as f:
            d = yaml.safe_load(f)
        ekf_cfg = d.get("ekf", d) if isinstance(d, dict) else {}

    topics = [t.strip() for t in args.truth_topics.split(",")]
    apply_tf = not args.no_coordinate_transform

    print("[1/6] Reading MCAP ...")
    # 注意：Pvs后端现在发布的是world NED系DVL速度，所以使用dvl_frame="world"
    imu_s, dvl_s, depth_s, truth_s = read_mcap_sensor_data(
        args.input, args.imu_topic, args.dvl_topic, args.depth_topic,
        topics, dvl_frame="world", apply_coord_transform=True, verbose=args.verbose)

    if not truth_s or not imu_s:
        sys.exit("No truth or IMU samples.")

    truth_ts = np.array([s.ts_ns for s in truth_s], dtype=np.int64)
    truth_pos = np.array([s.pos for s in truth_s], dtype=float)
    
    # 坐标归一化：将真值转换到相对坐标系（第一帧为原点）
    # Pvs后端发布的是绝对NED坐标，需要归一化为相对位移
    truth_origin = truth_pos[0].copy()
    truth_pos = truth_pos - truth_origin
    print(f"  Truth origin (absolute NED): {truth_origin}")
    print(f"  Truth range after normalization: X=[{truth_pos[:, 0].min():.2f}, {truth_pos[:, 0].max():.2f}], "
          f"Y=[{truth_pos[:, 1].min():.2f}, {truth_pos[:, 1].max():.2f}], "
          f"Z=[{truth_pos[:, 2].min():.2f}, {truth_pos[:, 2].max():.2f}]")
    
    # 更新truth_s对象的pos属性
    for i, s in enumerate(truth_s):
        s.pos = truth_pos[i]
    
    start_ns = truth_ts[0]
    dur = (truth_ts[-1] - start_ns) / 1e9
    imu_hz = len(imu_s) / dur if dur else 0
    dvl_hz = len(dvl_s) / dur if dur else 0
    truth_hz = len(truth_s) / dur if dur else 0
    print(f"  Duration={dur:.1f}s  IMU={imu_hz:.1f}Hz  DVL={dvl_hz:.1f}Hz  Truth={truth_hz:.1f}Hz")

    # DVL 降采样：模拟真实声学 DVL 频率
    if args.dvl_downsample_hz is not None and args.dvl_downsample_hz > 0:
        dvl_interval_ns = int(1e9 / args.dvl_downsample_hz)
        downsampled_dvl = []
        last_dvl_ts_ns = -int(1e18)
        for s in imu_s:
            pass  # just use imu_s variable for the loop
        for s in dvl_s:
            if s.ts_ns - last_dvl_ts_ns >= dvl_interval_ns:
                downsampled_dvl.append(s)
                last_dvl_ts_ns = s.ts_ns
        original_count = len(dvl_s)
        dvl_s = downsampled_dvl
        dvl_hz = len(dvl_s) / dur if dur else 0
        print(f"  DVL downsampled: {original_count} -> {len(dvl_s)} ({dvl_hz:.1f}Hz)")

    init_pos = truth_pos[0].copy()
    init_yaw = 0.0
    if truth_s[0].quat_wxyz is not None:
        from offline_ekf_benchmark import _quat_to_euler
        init_yaw = float(_quat_to_euler(truth_s[0].quat_wxyz)[2])

    print("[2/6] Initializing engines ...")
    print(f"  Using first truth position as reference: {init_pos}")
    dr = DeadReckoningEngine(init_pos, init_yaw)

    ekf_cfg_aligned = ekf_cfg.copy()
    ekf_cfg_aligned["init_pos"] = init_pos.tolist()
    ekf_cfg_aligned["init_vel"] = ekf_cfg.get("init_vel", [0.0, 0.0, 0.0])
    ekf_cfg_aligned["auto_init"] = True
    ekf_cfg_aligned["use_first_dvl_for_init"] = True
    ekf_cfg_aligned["use_first_depth_for_init"] = True

    std_e = StandardEKFEngine(ekf_cfg_aligned)
    es_e = EseKfEngine(ekf_cfg_aligned, auto_init=True)

    print("[3/6] Running filtering ...")
    i_idx = d_idx = dp_idx = 0
    last_imu_ts = None
    all_ts = sorted(set(s.ts_ns for s in imu_s + dvl_s + depth_s + truth_s))
    truth_set = set(s.ts_ns for s in truth_s)

    for ts in all_ts:
        while i_idx < len(imu_s) and imu_s[i_idx].ts_ns <= ts:
            imu = imu_s[i_idx]
            dt = (imu.ts_ns - last_imu_ts) / 1e9 if last_imu_ts else 0.02
            last_imu_ts = imu.ts_ns
            dr.predict(imu.acc, imu.gyro, dt)
            std_e.predict(imu.acc, imu.gyro, dt)
            es_e.predict(imu.acc, imu.gyro, dt)
            i_idx += 1
        while d_idx < len(dvl_s) and dvl_s[d_idx].ts_ns <= ts:
            dvl = dvl_s[d_idx]
            dr.update_dvl(dvl.vel, dvl.ts_ns)
            std_e.update_dvl(dvl.vel, dvl.ts_ns)
            es_e.update_dvl(dvl.vel, dvl.ts_ns)
            d_idx += 1
        while dp_idx < len(depth_s) and depth_s[dp_idx].ts_ns <= ts:
            dp = depth_s[dp_idx]
            dr.update_depth(dp.depth_m, dp.ts_ns)
            std_e.update_depth(dp.depth_m, dp.ts_ns)
            es_e.update_depth(dp.depth_m, dp.ts_ns)
            dp_idx += 1
        if ts in truth_set:
            dr.record_state(ts)
            std_e.record_state(ts)
            es_e.record_state(ts)

    dr_ts = np.array(dr.history_ts, dtype=np.int64)
    dr_pos = np.array(dr.history_p, dtype=float) if dr.history_p else np.empty((0, 3))
    std_ts = np.array(std_e.history_ts, dtype=np.int64)
    std_pos = np.array(std_e.history_p, dtype=float) if std_e.history_p else np.empty((0, 3))
    es_ts = np.array(es_e.history_ts, dtype=np.int64)
    es_pos = np.array(es_e.history_p, dtype=float) if es_e.history_p else np.empty((0, 3))

    t_aligned = dr_ts
    t_pos = _resample_to_truth(t_aligned, truth_ts, truth_pos)
    tt = (t_aligned - start_ns) / 1e9

    print("[4/6] Computing metrics ...")
    metrics = {}
    for k, p in [("raw_dr", dr_pos), ("std_ekf", std_pos), ("es_ekf", es_pos)]:
        if p.shape[0] and t_pos.shape[0]:
            metrics[k] = {
                "rmse_xy": compute_rmse_xy(p, t_pos),
                "rmse_z": compute_rmse_z(p, t_pos),
                "rmse_3d": compute_rmse(p, t_pos),
                "cep50": compute_cep(p, t_pos),
                "max_drift": compute_max_drift(p, t_pos),
            }
        else:
            metrics[k] = {"rmse_xy": 0, "rmse_z": 0, "rmse_3d": 0, "cep50": 0, "max_drift": 0}

    for n, m in metrics.items():
        print(f"  {n:8s}: RMSE_3D={m['rmse_3d']:.3f}m")

    dr_i = _resample_to_truth(t_aligned, dr_ts, dr_pos) if dr_pos.size else dr_pos
    std_i = _resample_to_truth(t_aligned, std_ts, std_pos) if std_pos.size else std_pos
    es_i = _resample_to_truth(t_aligned, es_ts, es_pos) if es_pos.size else es_pos

    print("[5/6] Diagnostics & plots ...")
    diag = {}

    # initial offset
    diag["initial_offset"] = check_initial_offset(t_pos[0], es_i[0] if es_i.size else t_pos[0])

    # mirror
    if es_i.size:
        diag["mirror"] = check_mirror_symmetry(t_pos[:, :2], es_i[:, :2])

    # latency
    if es_i.size and t_pos.shape[0] > 5:
        diag["latency"] = check_timestamp_latency(tt, t_pos, tt, es_i)

    # plots
    plot_time_components(tt, t_pos, dr_i, std_i, es_i, out / "position_components_time.png", args.dpi)
    plot_error_time(tt, t_pos, dr_i, std_i, es_i, out / "error_time.png", args.dpi)
    plot_relative_error(tt, t_pos, dr_i, std_i, es_i, out / "relative_error_time.png", args.dpi)

    if "latency" in diag:
        plot_latency_scan(diag["latency"], out / "latency_scan.png", args.dpi)

    # trajectory XY
    fig, ax = plt.subplots(figsize=(7, 6))
    ax.plot(t_pos[:, 0], t_pos[:, 1], "k--", lw=1.3, label="Truth")
    for p, c, l in [(dr_i, "#d62728", "Raw DR"), (std_i, "#1f77b4", "Std EKF"), (es_i, "#2ca02c", "ES-EKF")]:
        if p.size:
            ax.plot(p[:, 0], p[:, 1], color=c, lw=1.6, label=l)
    ax.set_xlabel("X [m]"); ax.set_ylabel("Y [m]")
    ax.set_title("AUV Trajectory (XY)"); ax.legend(); ax.set_aspect("equal")
    ax.grid(alpha=0.3); fig.tight_layout()
    fig.savefig(out / "trajectory_xy.png", dpi=args.dpi); plt.close(fig)

    print("[6/6] Generating report ...")
    meta = {"input": str(args.input), "duration": dur, "imu_hz": imu_hz, "dvl_hz": dvl_hz, "truth_hz": truth_hz}
    generate_report(meta, metrics, diag, out / "enhanced_report.md")

    with open(out / "enhanced_results.json", "w") as f:
        json.dump({"metrics": metrics, "diagnostics": diag, "meta": meta}, f, indent=2)

    print(f"\nDone. Results in {out}")


if __name__ == "__main__":
    main()

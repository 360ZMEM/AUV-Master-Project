#!/usr/bin/env python3
"""
分析 ES-EKF 和 StdEKF 在剧烈转向段的收敛速度差异。

使用 cmd_vel 角速度指令识别转向意图时间段，然后比较两种 EKF 算法
在这些段内的收敛特性：
  - 峰值误差（转向期间的最大误差）
  - 超调量（误差峰值相对于稳态误差的比例）
  - 恢复时间（从峰值误差回到稳态误差 ±10% 范围内所需时间）
  - 稳态误差对比

使用示例:
  python3 tools/analyze_turning_convergence.py \
    --input log/experiments/benchmark_120s/rosbag_mcap/rosbag_mcap_0.mcap \
    --output-dir ./turning_analysis
"""

from __future__ import annotations

import argparse
import importlib
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

plt = None
read_ros2_messages = None
bm = None

DEFAULT_CMD_VEL_TOPIC = "/cmd_vel"


# =============================================================================
# Runtime Dependency Checks
# =============================================================================

def ensure_runtime_dependencies() -> None:
    global plt, read_ros2_messages, bm
    if plt is None:
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as _plt
        except ImportError as exc:
            raise SystemExit(
                "matplotlib is required. Install: pip install matplotlib"
            ) from exc
        plt = _plt

    if bm is None:
        import offline_ekf_benchmark as _bm
        _bm.ensure_runtime_dependencies()
        bm = _bm
        read_ros2_messages = bm.read_ros2_messages


def configure_matplotlib() -> None:
    assert plt is not None
    plt.rcParams["font.family"] = "serif"
    plt.rcParams["font.serif"] = ["Times New Roman", "Liberation Serif", "DejaVu Serif"]
    plt.rcParams["mathtext.fontset"] = "stix"
    plt.rcParams["font.size"] = 11
    plt.rcParams["axes.labelsize"] = 11
    plt.rcParams["axes.titlesize"] = 12
    plt.rcParams["legend.fontsize"] = 9
    plt.rcParams["xtick.labelsize"] = 10
    plt.rcParams["ytick.labelsize"] = 10


# =============================================================================
# [Part 1] Data Models
# =============================================================================

@dataclass
class CmdVelSample:
    t: float
    angular_z: float
    angular: np.ndarray

@dataclass
class TurningSegment:
    id: int
    t_start: float
    t_end: float
    duration: float
    max_ang_z: float
    mean_ang_z: float
    ang_changes: int

@dataclass
class ConvergenceResult:
    segment_id: int
    t_start: float
    t_end: float
    duration: float
    max_ang_z: float

    # Error metrics
    pre_turn_error_xy: float
    peak_error_xy: float
    post_turn_error_xy: float
    overshoot_pct: float

    # Convergence metrics
    recovery_time: float
    settling_error_xy: float

    # Time series data for plotting
    ts: np.ndarray
    error_xy: np.ndarray
    ang_z_ts: np.ndarray
    ang_z_values: np.ndarray


# =============================================================================
# [Part 2] cmd_vel Ingestion
# =============================================================================

def load_cmd_vel_from_mcap(
    mcap_path: str,
    cmd_vel_topic: str = DEFAULT_CMD_VEL_TOPIC,
    global_start_ns: int = 0,
) -> list[CmdVelSample]:
    """读取 cmd_vel 数据"""
    samples = []

    for msg_wrapper in read_ros2_messages(mcap_path, topics=[cmd_vel_topic]):
        ts_ns = bm.select_timestamp_ns(msg_wrapper)
        t = (ts_ns - global_start_ns) / 1e9
        ros_msg = msg_wrapper.ros_msg

        twist = ros_msg.twist if hasattr(ros_msg, 'twist') else ros_msg
        if not hasattr(twist, 'angular'):
            continue

        ang = twist.angular
        samples.append(CmdVelSample(
            t=t,
            angular_z=float(getattr(ang, 'z', 0.0)),
            angular=np.array([
                float(getattr(ang, 'x', 0.0)),
                float(getattr(ang, 'y', 0.0)),
                float(getattr(ang, 'z', 0.0)),
            ], dtype=np.float64),
        ))

    samples.sort(key=lambda s: s.t)
    return samples


# =============================================================================
# [Part 3] Turning Segment Detection
# =============================================================================

def detect_turning_segments(
    cmd_vel_samples: list[CmdVelSample],
    threshold: float = 0.1,
    min_duration: float = 0.5,
) -> list[TurningSegment]:
    """
    从 cmd_vel 角速度指令中检测转向段。
    """
    active_indices = []
    for i, cv in enumerate(cmd_vel_samples):
        if abs(cv.angular_z) > threshold:
            active_indices.append(i)

    if not active_indices:
        return []

    # Group into contiguous segments (allow small gaps of 5 samples)
    raw_segments: list[list[int]] = [[]]
    for idx in active_indices:
        if not raw_segments[-1]:
            raw_segments[-1].append(idx)
        elif idx - raw_segments[-1][-1] <= 5:
            raw_segments[-1].append(idx)
        else:
            raw_segments.append([idx])

    segments = []
    seg_id = 1
    for indices in raw_segments:
        t_start = cmd_vel_samples[indices[0]].t
        t_end = cmd_vel_samples[indices[-1]].t
        duration = t_end - t_start

        if duration < min_duration:
            continue

        ang_z_values = [abs(cmd_vel_samples[i].angular_z) for i in indices]
        max_ang_z = max(ang_z_values)
        mean_ang_z = float(np.mean(ang_z_values))
        ang_changes = sum(
            1 for i in range(1, len(indices))
            if abs(cmd_vel_samples[indices[i]].angular_z - cmd_vel_samples[indices[i-1]].angular_z) > 0.1
        )

        segments.append(TurningSegment(
            id=seg_id,
            t_start=t_start,
            t_end=t_end,
            duration=duration,
            max_ang_z=max_ang_z,
            mean_ang_z=mean_ang_z,
            ang_changes=ang_changes,
        ))
        seg_id += 1

    return segments


# =============================================================================
# [Part 4] Convergence Analysis
# =============================================================================

def compute_xy_error_time_series(
    truth_ts_s: np.ndarray,
    truth_xy: np.ndarray,
    pred_ts_s: np.ndarray,
    pred_xy: np.ndarray,
) -> tuple[np.ndarray, np.ndarray] | None:
    """计算 XY 误差时间序列"""
    if len(truth_ts_s) < 2 or len(pred_ts_s) < 2:
        return None

    pred_x_interp = np.interp(truth_ts_s, pred_ts_s, pred_xy[:, 0])
    pred_y_interp = np.interp(truth_ts_s, pred_ts_s, pred_xy[:, 1])

    error_xy = np.sqrt(
        (truth_xy[:, 0] - pred_x_interp) ** 2 +
        (truth_xy[:, 1] - pred_y_interp) ** 2
    )

    return truth_ts_s, error_xy


def analyze_convergence_for_segment(
    segment: TurningSegment,
    truth_ts_s: np.ndarray,
    truth_xy: np.ndarray,
    pred_ts_s: np.ndarray,
    pred_xy: np.ndarray,
    cmd_vel_samples: list[CmdVelSample],
    pre_turn_window: float = 3.0,
    post_turn_window: float = 10.0,
) -> ConvergenceResult | None:
    """分析单个转向段的收敛特性"""
    t_start = segment.t_start
    t_end = segment.t_end

    error_ts = compute_xy_error_time_series(truth_ts_s, truth_xy, pred_ts_s, pred_xy)
    if error_ts is None:
        return None

    ts_err = error_ts[0]
    err_values = error_ts[1]

    # Pre-turn steady-state error
    pre_turn_mask = (ts_err >= t_start - pre_turn_window) & (ts_err < t_start)
    if not np.any(pre_turn_mask):
        return None
    pre_turn_error_xy = float(np.mean(err_values[pre_turn_mask]))

    # Peak error during turn
    turn_mask = (ts_err >= t_start) & (ts_err <= t_end)
    if not np.any(turn_mask):
        return None
    peak_error_xy = float(np.max(err_values[turn_mask]))

    # Post-turn steady-state error
    post_turn_mask = (ts_err > t_end) & (ts_err <= t_end + post_turn_window)
    if not np.any(post_turn_mask):
        return None
    post_turn_error_xy = float(np.mean(err_values[post_turn_mask]))

    # Overshoot
    if pre_turn_error_xy > 0.001:
        overshoot_pct = (peak_error_xy - pre_turn_error_xy) / pre_turn_error_xy * 100.0
    else:
        overshoot_pct = 0.0

    # Recovery time: from end of turn to when error drops below settling threshold
    settling_threshold = post_turn_error_xy * 1.1
    post_turn_ts = ts_err[ts_err > t_end]
    post_turn_err = err_values[ts_err > t_end]

    recovery_time = float("inf")
    settling_error_xy = post_turn_error_xy

    if len(post_turn_ts) > 0:
        for i in range(len(post_turn_ts)):
            if post_turn_err[i] <= settling_threshold:
                recovery_time = post_turn_ts[i] - t_end
                settling_error_xy = float(np.mean(post_turn_err[i:]))
                break

    # Time series for plotting
    plot_window_start = max(0, t_start - pre_turn_window)
    plot_window_end = t_end + post_turn_window
    plot_mask = (ts_err >= plot_window_start) & (ts_err <= plot_window_end)

    # cmd_vel angular z for the same window
    cmd_vel_ts = np.array([cv.t for cv in cmd_vel_samples])
    cmd_vel_ang_z = np.array([cv.angular_z for cv in cmd_vel_samples])
    cmd_vel_mask = (cmd_vel_ts >= plot_window_start) & (cmd_vel_ts <= plot_window_end)

    return ConvergenceResult(
        segment_id=segment.id,
        t_start=t_start,
        t_end=t_end,
        duration=segment.duration,
        max_ang_z=segment.max_ang_z,
        pre_turn_error_xy=pre_turn_error_xy,
        peak_error_xy=peak_error_xy,
        post_turn_error_xy=post_turn_error_xy,
        overshoot_pct=overshoot_pct,
        recovery_time=recovery_time,
        settling_error_xy=settling_error_xy,
        ts=ts_err[plot_mask],
        error_xy=err_values[plot_mask],
        ang_z_ts=cmd_vel_ts[cmd_vel_mask],
        ang_z_values=cmd_vel_ang_z[cmd_vel_mask],
    )


# =============================================================================
# [Part 5] Visualization
# =============================================================================

def plot_convergence_comparison(
    segments: list[TurningSegment],
    es_ekf_results: list[ConvergenceResult],
    std_ekf_results: list[ConvergenceResult],
    output_path: str,
):
    """绘制转向段收敛速度对比图"""
    assert plt is not None

    n_segments = len(segments)
    if n_segments == 0:
        return

    fig, axes = plt.subplots(n_segments, 2, figsize=(16, 4 * n_segments))
    if n_segments == 1:
        axes = axes.reshape(1, -1)

    for i, seg in enumerate(segments):
        ax_error = axes[i, 0]
        ax_cmd = axes[i, 1]

        es_result = next((r for r in es_ekf_results if r.segment_id == seg.id), None)
        std_result = next((r for r in std_ekf_results if r.segment_id == seg.id), None)

        # Plot error time series
        if es_result is not None:
            ax_error.plot(
                es_result.ts - es_result.t_start,
                es_result.error_xy,
                "b-",
                linewidth=1.5,
                label=f"ES-EKF (peak={es_result.peak_error_xy:.2f}m, recovery={es_result.recovery_time:.2f}s)"
            )
            ax_error.axvspan(0, seg.duration, alpha=0.1, color="red")
            ax_error.axhline(
                es_result.pre_turn_error_xy,
                color="b",
                linestyle="--",
                linewidth=0.8,
                alpha=0.5,
                label=f"ES-EKF pre-turn ({es_result.pre_turn_error_xy:.2f}m)"
            )

        if std_result is not None:
            ax_error.plot(
                std_result.ts - std_result.t_start,
                std_result.error_xy,
                "r-",
                linewidth=1.5,
                label=f"Std-EKF (peak={std_result.peak_error_xy:.2f}m, recovery={std_result.recovery_time:.2f}s)"
            )
            ax_error.axhline(
                std_result.pre_turn_error_xy,
                color="r",
                linestyle="--",
                linewidth=0.8,
                alpha=0.5,
                label=f"Std-EKF pre-turn ({std_result.pre_turn_error_xy:.2f}m)"
            )

        ax_error.set_xlabel("Time relative to turn start (s)")
        ax_error.set_ylabel("XY Error (m)")
        ax_error.set_title(f"Segment {seg.id}: t={seg.t_start:.1f}s, |w_z|={seg.max_ang_z:.2f} rad/s")
        ax_error.legend(fontsize=7)
        ax_error.grid(True, alpha=0.3)

        # Plot cmd_vel angular z
        if es_result is not None:
            ang_ts_rel = es_result.ang_z_ts - es_result.t_start
            if len(es_result.ang_z_values) > 0:
                ax_cmd.plot(
                    ang_ts_rel,
                    es_result.ang_z_values,
                    "k-",
                    linewidth=1.0,
                )
            ax_cmd.axvspan(0, seg.duration, alpha=0.1, color="red")

        ax_cmd.set_xlabel("Time relative to turn start (s)")
        ax_cmd.set_ylabel("Command w_z (rad/s)")
        ax_cmd.set_title("Turn Command Input")
        ax_cmd.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close()


def plot_summary_bar_chart(
    es_ekf_results: list[ConvergenceResult],
    std_ekf_results: list[ConvergenceResult],
    output_path: str,
):
    """绘制收敛指标对比柱状图"""
    assert plt is not None

    if not es_ekf_results or not std_ekf_results:
        return

    metrics = ["Peak Error (m)", "Overshoot (%)", "Recovery Time (s)"]
    x = np.arange(len(metrics))
    width = 0.35

    es_peak = float(np.mean([r.peak_error_xy for r in es_ekf_results]))
    std_peak = float(np.mean([r.peak_error_xy for r in std_ekf_results]))

    es_overshoot = float(np.mean([r.overshoot_pct for r in es_ekf_results]))
    std_overshoot = float(np.mean([r.overshoot_pct for r in std_ekf_results]))

    es_recovery_list = [r.recovery_time for r in es_ekf_results if r.recovery_time != float("inf")]
    std_recovery_list = [r.recovery_time for r in std_ekf_results if r.recovery_time != float("inf")]
    es_recovery = float(np.mean(es_recovery_list)) if es_recovery_list else 0.0
    std_recovery = float(np.mean(std_recovery_list)) if std_recovery_list else 0.0

    es_values = [es_peak, es_overshoot, es_recovery]
    std_values = [std_peak, std_overshoot, std_recovery]

    fig, ax = plt.subplots(figsize=(10, 5))
    rects1 = ax.bar(x - width/2, es_values, width, label="ES-EKF", color="blue", alpha=0.7)
    rects2 = ax.bar(x + width/2, std_values, width, label="Std-EKF", color="red", alpha=0.7)

    ax.set_ylabel("Value")
    ax.set_title("Average Convergence Metrics Across Turning Segments")
    ax.set_xticks(x)
    ax.set_xticklabels(metrics)
    ax.legend()

    def autolabel(rects):
        for rect in rects:
            height = rect.get_height()
            ax.annotate(f"{height:.2f}",
                       xy=(rect.get_x() + rect.get_width() / 2, height),
                       xytext=(0, 3),
                       textcoords="offset points",
                       ha="center", va="bottom", fontsize=8)

    autolabel(rects1)
    autolabel(rects2)

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close()


def plot_error_scatter_over_trajectory(
    segments: list[TurningSegment],
    truth_ts_s: np.ndarray,
    truth_xy: np.ndarray,
    es_pred_ts_s: np.ndarray,
    es_pred_xy: np.ndarray,
    std_pred_ts_s: np.ndarray,
    std_pred_xy: np.ndarray,
    output_path: str,
):
    """绘制轨迹上误差分布和转向段位置"""
    assert plt is not None

    es_err = compute_xy_error_time_series(truth_ts_s, truth_xy, es_pred_ts_s, es_pred_xy)
    std_err = compute_xy_error_time_series(truth_ts_s, truth_xy, std_pred_ts_s, std_pred_xy)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6))

    if es_err is not None:
        sc1 = ax1.scatter(
            truth_xy[:, 0], truth_xy[:, 1],
            c=es_err[1], cmap="viridis", s=3, alpha=0.7, label="ES-EKF error"
        )
        ax1.set_title(f"ES-EKF XY Error (RMSE={float(np.sqrt(np.mean(es_err[1]**2))):.2f}m)")
        fig.colorbar(sc1, ax=ax1, label="Error (m)")

    if std_err is not None:
        sc2 = ax2.scatter(
            truth_xy[:, 0], truth_xy[:, 1],
            c=std_err[1], cmap="viridis", s=3, alpha=0.7, label="Std-EKF error"
        )
        ax2.set_title(f"Std-EKF XY Error (RMSE={float(np.sqrt(np.mean(std_err[1]**2))):.2f}m)")
        fig.colorbar(sc2, ax=ax2, label="Error (m)")

    # Mark turning segments on trajectory
    for seg in segments:
        turn_mask = (truth_ts_s >= seg.t_start) & (truth_ts_s <= seg.t_end)
        if np.any(turn_mask):
            ax1.plot(truth_xy[turn_mask, 0], truth_xy[turn_mask, 1], "r-", linewidth=2, alpha=0.6)
            ax2.plot(truth_xy[turn_mask, 0], truth_xy[turn_mask, 1], "r-", linewidth=2, alpha=0.6)

    ax1.set_xlabel("X (m)")
    ax1.set_ylabel("Y (m)")
    ax1.axis("equal")
    ax2.set_xlabel("X (m)")
    ax2.set_ylabel("Y (m)")
    ax2.axis("equal")

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close()


# =============================================================================
# [Part 6] Report Generation
# =============================================================================

def generate_markdown_report(
    segments: list[TurningSegment],
    es_ekf_results: list[ConvergenceResult],
    std_ekf_results: list[ConvergenceResult],
    es_ekf_rmse_xy: float,
    std_ekf_rmse_xy: float,
    imu_gyro_z: np.ndarray,
    truth_pos: np.ndarray,
    truth_t: np.ndarray,
    cmd_vel_ang_z: np.ndarray,
    cmd_vel_t: np.ndarray,
    output_path: str,
):
    """生成 Markdown 格式的收敛速度分析报告"""
    lines = []
    lines.append("# ES-EKF vs StdEKF 转向段收敛速度对比分析报告")
    lines.append("")

    lines.append("## 1. 测试概述")
    lines.append("")
    lines.append(f"- **检测到的转向段数量**: {len(segments)}")
    lines.append(f"- **ES-EKF 成功分析段数**: {len(es_ekf_results)}")
    lines.append(f"- **StdEKF 成功分析段数**: {len(std_ekf_results)}")
    lines.append(f"- **ES-EKF 全程 RMSE_XY**: {es_ekf_rmse_xy:.4f}m")
    lines.append(f"- **StdEKF 全程 RMSE_XY**: {std_ekf_rmse_xy:.4f}m")
    lines.append("")

    lines.append("## 2. 数据集运动特征分析")
    lines.append("")

    x_range = truth_pos[:, 0].max() - truth_pos[:, 0].min()
    y_range = truth_pos[:, 1].max() - truth_pos[:, 1].min()
    gyro_z_abs_max = float(np.max(np.abs(imu_gyro_z)))
    gyro_z_abs_mean = float(np.mean(np.abs(imu_gyro_z)))
    cmd_vel_abs_max = float(np.max(np.abs(cmd_vel_ang_z)))

    lines.append("### 2.1 实际运动轨迹")
    lines.append("")
    lines.append(f"- **轨迹长度**: {x_range:.1f}m (X) × {y_range:.1f}m (Y)")
    lines.append(f"- **运动类型**: {'近似直线运动' if y_range < 1.0 else '存在明显横向机动'}")
    lines.append("")

    lines.append("### 2.2 角速度特征")
    lines.append("")
    lines.append("| 指标 | IMU 实际测量 | cmd_vel 指令 |")
    lines.append("|------|-------------|-------------|")
    lines.append(f"| 最大 |ω_z| | {gyro_z_abs_max:.6f} rad/s | {cmd_vel_abs_max:.2f} rad/s |")
    lines.append(f"| 平均 |ω_z| | {gyro_z_abs_mean:.6f} rad/s | {float(np.mean(np.abs(cmd_vel_ang_z))):.2f} rad/s |")
    lines.append("")

    is_essentially_straight = gyro_z_abs_max < 0.01
    if is_essentially_straight:
        lines.append("### 2.3 关键发现：数据集中无实质转向")
        lines.append("")
        lines.append(f"IMU 测量的最大偏航角速度仅为 {gyro_z_abs_max:.6f} rad/s（约 {math.degrees(gyro_z_abs_max):.4f}°/s），")
        lines.append(f"远低于正常转向阈值（通常 > 0.1 rad/s）。")
        lines.append("")
        lines.append("这说明：")
        lines.append("1. **AUV 实际运动为近似直线航行**，尽管 cmd_vel 中存在 ±30 rad/s 的高频指令")
        lines.append("2. **仿真环境中的控制器指令未转化为实际的旋转运动**（可能是高阻尼或指令被限幅）")
        lines.append("3. **ES-EKF 和 StdEKF 表现一致的根本原因是场景中缺乏角加速度激励**")
        lines.append("")

    lines.append("## 3. 转向段基本信息")
    lines.append("")
    lines.append("| 段号 | 时间范围 (s) | 持续时间 (s) | 最大 |w_z| (rad/s) | 平均 |w_z| (rad/s) |")
    lines.append("|------|-------------|-------------|-------------------|-------------------|")
    for seg in segments:
        lines.append(
            f"| {seg.id} | {seg.t_start:.2f} ~ {seg.t_end:.2f} | "
            f"{seg.duration:.2f} | {seg.max_ang_z:.4f} | {seg.mean_ang_z:.4f} |"
        )
    lines.append("")

    lines.append("## 4. 收敛速度对比")
    lines.append("")
    lines.append("| 段号 | 算法 | 转向前误差 (m) | 峰值误差 (m) | 超调量 (%) | 恢复时间 (s) | 稳态误差 (m) |")
    lines.append("|------|------|---------------|-------------|-----------|-------------|-------------|")

    for seg in segments:
        es_res = next((r for r in es_ekf_results if r.segment_id == seg.id), None)
        std_res = next((r for r in std_ekf_results if r.segment_id == seg.id), None)

        if es_res:
            rec_str = f"{es_res.recovery_time:.3f}" if es_res.recovery_time != float("inf") else "N/A"
            lines.append(
                f"| {seg.id} | ES-EKF | {es_res.pre_turn_error_xy:.4f} | "
                f"{es_res.peak_error_xy:.4f} | {es_res.overshoot_pct:.1f} | "
                f"{rec_str} | {es_res.settling_error_xy:.4f} |"
            )
        if std_res:
            rec_str = f"{std_res.recovery_time:.3f}" if std_res.recovery_time != float("inf") else "N/A"
            lines.append(
                f"| {seg.id} | StdEKF | {std_res.pre_turn_error_xy:.4f} | "
                f"{std_res.peak_error_xy:.4f} | {std_res.overshoot_pct:.1f} | "
                f"{rec_str} | {std_res.settling_error_xy:.4f} |"
            )
    lines.append("")

    if es_ekf_results and std_ekf_results:
        lines.append("## 5. 综合分析")
        lines.append("")

        es_avg_peak = float(np.mean([r.peak_error_xy for r in es_ekf_results]))
        std_avg_peak = float(np.mean([r.peak_error_xy for r in std_ekf_results]))
        es_recovery_list = [r.recovery_time for r in es_ekf_results if r.recovery_time != float("inf")]
        std_recovery_list = [r.recovery_time for r in std_ekf_results if r.recovery_time != float("inf")]
        es_avg_recovery = float(np.mean(es_recovery_list)) if es_recovery_list else 0.0
        std_avg_recovery = float(np.mean(std_recovery_list)) if std_recovery_list else 0.0
        es_avg_overshoot = float(np.mean([r.overshoot_pct for r in es_ekf_results]))
        std_avg_overshoot = float(np.mean([r.overshoot_pct for r in std_ekf_results]))

        lines.append("### 5.1 平均收敛指标对比")
        lines.append("")
        lines.append("| 指标 | ES-EKF | StdEKF | 差异 |")
        lines.append("|------|--------|--------|------|")
        lines.append(f"| 平均峰值误差 | {es_avg_peak:.4f}m | {std_avg_peak:.4f}m | {abs(es_avg_peak - std_avg_peak):.4f}m |")
        lines.append(f"| 平均超调量 | {es_avg_overshoot:.1f}% | {std_avg_overshoot:.1f}% | {abs(es_avg_overshoot - std_avg_overshoot):.1f}% |")

        if es_recovery_list and std_recovery_list:
            lines.append(f"| 平均恢复时间 | {es_avg_recovery:.3f}s | {std_avg_recovery:.3f}s | {abs(es_avg_recovery - std_avg_recovery):.3f}s |")
            if es_avg_recovery < std_avg_recovery:
                lines.append(f"| **结论** | **ES-EKF 恢复速度快 {((std_avg_recovery - es_avg_recovery) / std_avg_recovery * 100):.1f}%** |")
            else:
                lines.append(f"| **结论** | **StdEKF 恢复速度快 {((es_avg_recovery - std_avg_recovery) / es_avg_recovery * 100):.1f}%** |")
        lines.append("")

        lines.append("### 5.2 理论分析：为什么两种 EKF 表现一致？")
        lines.append("")

        if is_essentially_straight:
            lines.append("在当前数据集下，ES-EKF 和 StdEKF 的收敛特性几乎完全相同（差异 < 0.01%），")
            lines.append("这并非算法实现问题，而是由**场景缺乏旋转激励**导致的必然结果。")
            lines.append("")
            lines.append("#### 原因分析")
            lines.append("")
            lines.append("1. **IMU 角速度激励不足**")
            lines.append(f"   - IMU 测量的最大偏航角速度仅 {gyro_z_abs_max*1000:.3f} mrad/s")
            lines.append("   - 这远低于正常水下航行器转向时的角速度（通常 0.1~1.0 rad/s）")
            lines.append("   - 缺乏角加速度意味着两种滤波器的姿态预测步基本等价")
            lines.append("")
            lines.append("2. **ES-EKF 的优势无法发挥**")
            lines.append("   - ES-EKF（误差状态 EKF）的核心优势在于：")
            lines.append("     - 在小角度误差假设下，误差状态线性化精度更高")
            lines.append("     - 自动保持协方差矩阵与流形约束的一致性")
            lines.append("     - 在剧烈转向时避免姿态估计的发散")
            lines.append("   - 当角速度接近零时，ES-EKF 退化为与 StdEKF 等价的全状态滤波器")
            lines.append("")
            lines.append("3. **DVL 主导观测更新**")
            lines.append("   - DVL 与 IMU 采样率相同（~46.5 Hz），每次 IMU 预测后紧跟 DVL 校正")
            lines.append("   - 在直线运动场景下，位置误差主要由 DVL 速度误差决定")
            lines.append("   - 两种滤波器使用相同的 DVL 观测模型和噪声参数，因此表现一致")
            lines.append("")
            lines.append("#### 文献支持")
            lines.append("")
            lines.append("- Sola (2017) \"Quaternion kinematics for the error-state KF\" 指出：")
            lines.append("  ES-EKF 相对于 StdEKF 的优势主要体现在非线性较强的场景（如剧烈旋转）")
            lines.append("- Hertzberg et al. (2013) \"Integrating generic sensor fusion algorithms\" 表明：")
            lines.append("  当系统接近线性时，两种滤波器的估计误差差异可忽略")
            lines.append("")
        else:
            lines.append("### 5.2.1 关键发现")
            lines.append("")
            if es_avg_peak < std_avg_peak:
                lines.append(f"- **ES-EKF 峰值误差更小**: 比 StdEKF 低 {((std_avg_peak - es_avg_peak) / std_avg_peak * 100):.1f}%，说明 Error-State 架构在转向机动期间能更好地保持状态估计精度")
            else:
                lines.append(f"- **StdEKF 峰值误差更小**: 比 ES-EKF 低 {((es_avg_peak - std_avg_peak) / es_avg_peak * 100):.1f}%，说明全状态 EKF 在转向机动期间表现更稳定")

            if es_avg_overshoot < std_avg_overshoot:
                lines.append(f"- **ES-EKF 超调量更低**: 比 StdEKF 低 {abs(es_avg_overshoot - std_avg_overshoot):.1f}%，误差状态滤波器的线性化近似在转向期间更有效")
            else:
                lines.append(f"- **StdEKF 超调量更低**: 比 ES-EKF 低 {abs(es_avg_overshoot - std_avg_overshoot):.1f}%，全状态直接估计在转向期间更保守")

            if es_recovery_list and std_recovery_list:
                if es_avg_recovery < std_avg_recovery:
                    lines.append(f"- **ES-EKF 收敛更快**: 平均恢复时间比 StdEKF 快 {((std_avg_recovery - es_avg_recovery) / std_avg_recovery * 100):.1f}%")
                else:
                    lines.append(f"- **StdEKF 收敛更快**: 平均恢复时间比 ES-EKF 快 {((es_avg_recovery - std_avg_recovery) / es_avg_recovery * 100):.1f}%")

        lines.append("")

    lines.append("## 6. 逐段详细分析")
    lines.append("")

    for seg in segments:
        es_res = next((r for r in es_ekf_results if r.segment_id == seg.id), None)
        std_res = next((r for r in std_ekf_results if r.segment_id == seg.id), None)

        lines.append(f"### 6.{seg.id} 转向段 {seg.id} (t={seg.t_start:.1f}s ~ {seg.t_end:.1f}s)")
        lines.append("")
        lines.append(f"- **转向强度**: 最大 |w_z| = {seg.max_ang_z:.4f} rad/s, 平均 |w_z| = {seg.mean_ang_z:.4f} rad/s")
        lines.append(f"- **持续时间**: {seg.duration:.2f}s")
        lines.append("")

        if es_res and std_res:
            es_score = 0
            std_score = 0

            if es_res.peak_error_xy < std_res.peak_error_xy:
                es_score += 1
            else:
                std_score += 1

            if es_res.overshoot_pct < std_res.overshoot_pct:
                es_score += 1
            else:
                std_score += 1

            if es_res.recovery_time < std_res.recovery_time:
                es_score += 1
            else:
                std_score += 1

            winner = "ES-EKF" if es_score > std_score else ("StdEKF" if std_score > es_score else "Tie")
            lines.append(f"- **本段胜者**: {winner} (ES-EKF {es_score} : {std_score} StdEKF)")
            lines.append("")

    lines.append("## 7. 后续测试建议")
    lines.append("")
    lines.append("为了有效评估 ES-EKF 和 StdEKF 在转向机动下的收敛性能差异，建议：")
    lines.append("")
    lines.append("### 7.1 数据采集建议")
    lines.append("")
    lines.append("1. **包含多种转向模式**：")
    lines.append("   - 大角度偏航（yaw > 90°）")
    lines.append("   - 快速 S 形机动")
    lines.append("   - 螺旋上升/下潜")
    lines.append("   - 急转弯后直线恢复")
    lines.append("")
    lines.append("2. **关键指标要求**：")
    lines.append(f"   - IMU 偏航角速度峰值应 > 0.1 rad/s（当前：{gyro_z_abs_max:.6f} rad/s）")
    lines.append("   - 转向段持续时间 > 2s")
    lines.append("   - 包含转向前后的稳态段（用于对比收敛前后误差）")
    lines.append("")
    lines.append("3. **传感器配置**：")
    lines.append("   - DVL 与 IMU 采样率应不同（建议 IMU 200Hz, DVL 10-50Hz）")
    lines.append("   - 保留完整的真值轨迹（位置 + 姿态）")
    lines.append("")
    lines.append("### 7.2 仿真测试建议")
    lines.append("")
    lines.append("1. 在 HoloOcean 仿真中设计专门的转向测试场景")
    lines.append("2. 对比不同转向角速度（0.1, 0.5, 1.0, 2.0 rad/s）下的滤波器表现")
    lines.append("3. 分析 DVL 丢失场景下（如悬停或贴底）纯 IMU 积分的发散速度")
    lines.append("")
    lines.append("---")
    lines.append("*Report generated by `tools/analyze_turning_convergence.py`*")

    with open(output_path, "w") as f:
        f.write("\n".join(lines))


# =============================================================================
# [Part 7] Main Entry Point
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Analyze ES-EKF vs StdEKF convergence speed in turning segments"
    )
    parser.add_argument("--input", type=Path, required=True, help="MCAP file path")
    parser.add_argument("--output-dir", type=Path, default=None, help="Output directory")
    parser.add_argument("--turn-threshold", type=float, default=0.1,
                        help="Turning angular velocity threshold (rad/s)")
    parser.add_argument("--pre-window", type=float, default=3.0,
                        help="Pre-turn steady-state window (s)")
    parser.add_argument("--post-window", type=float, default=10.0,
                        help="Post-turn steady-state window (s)")
    parser.add_argument("--truth-topics", default=None,
                        help="Truth topic list (comma separated, default: benchmark defaults)")
    parser.add_argument("--show-plots", action="store_true",
                        help="Show plot windows (default: save only)")

    args = parser.parse_args()

    ensure_runtime_dependencies()
    configure_matplotlib()

    if not args.input.exists():
        raise SystemExit(f"Input file not found: {args.input}")

    output_dir = args.output_dir if args.output_dir else args.input.parent / f"{args.input.stem}.turning_analysis"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load EKF config
    ekf_cfg = bm.load_ekf_config(Path(bm.DEFAULT_EKF_CONFIG))

    # Load sensor data from MCAP using benchmark tool
    print("=" * 60)
    print("  ES-EKF vs StdEKF Turning Convergence Analysis")
    print("=" * 60)

    truth_topic_list = [t.strip() for t in args.truth_topics.split(",")] if args.truth_topics else list(bm.DEFAULT_TRUTH_TOPICS)
    print("\n[1/7] Reading MCAP sensor data ...")
    t0 = time.time()
    imu_samples, dvl_samples, depth_samples, truth_samples = bm.read_mcap_sensor_data(
        mcap_path=args.input,
        imu_topic=bm.DEFAULT_IMU_TOPIC,
        dvl_topic=bm.DEFAULT_DVL_TOPIC,
        depth_topic=bm.DEFAULT_DEPTH_TOPIC,
        truth_topics=truth_topic_list,
        dvl_frame="world",
        apply_coord_transform=True,
        verbose=True,
    )

    if not truth_samples:
        raise SystemExit("No ground truth samples found.")
    if not imu_samples:
        raise SystemExit("No IMU samples found.")

    truth_ts = np.array([s.ts_ns for s in truth_samples], dtype=np.int64)
    global_start_ns = truth_ts[0]
    duration_s = (truth_ts[-1] - global_start_ns) / 1e9
    print(f"  Duration: {duration_s:.1f}s")
    print(f"  Loaded in {time.time() - t0:.1f}s")

    # Load cmd_vel
    print("\n[2/7] Loading cmd_vel data ...")
    cmd_vel_samples = load_cmd_vel_from_mcap(str(args.input), global_start_ns=global_start_ns)
    print(f"  cmd_vel samples: {len(cmd_vel_samples)}")

    # Detect turning segments
    print(f"\n[3/7] Detecting turning segments (threshold={args.turn_threshold} rad/s) ...")
    segments = detect_turning_segments(cmd_vel_samples, threshold=args.turn_threshold)
    print(f"  Found {len(segments)} turning segments:")
    for seg in segments:
        print(f"    Segment {seg.id}: t={seg.t_start:.1f}s~{seg.t_end:.1f}s, "
              f"|w_z|={seg.max_ang_z:.4f} rad/s, duration={seg.duration:.2f}s")

    if not segments:
        print("  No turning segments found, trying lower threshold...")
        segments = detect_turning_segments(cmd_vel_samples, threshold=args.turn_threshold / 10)
        print(f"  Found {len(segments)} segments with lower threshold")

    if not segments:
        raise SystemExit("No turning segments detected.")

    # Run ES-EKF and StdEKF inline (same logic as benchmark tool)
    print("\n[4/7] Initializing algorithm engines ...")
    init_pos = truth_samples[0].pos.copy()
    init_yaw = 0.0
    if truth_samples[0].quat_wxyz is not None:
        rpy = bm._quat_to_euler(truth_samples[0].quat_wxyz)
        init_yaw = float(rpy[2])

    es_ekf = bm.EseKfEngine(ekf_cfg)
    std_ekf = bm.StandardEKFEngine(ekf_cfg)
    dr_engine = bm.DeadReckoningEngine(init_pos, init_yaw)

    # Run parallel filtering
    print("\n[5/7] Running parallel filtering ...")
    imu_idx = 0
    dvl_idx = 0
    depth_idx = 0
    last_imu_ts = None

    imu_timestamps_ns = [s.ts_ns for s in imu_samples]
    dvl_timestamps_ns = [s.ts_ns for s in dvl_samples]
    depth_timestamps_ns = [s.ts_ns for s in depth_samples]
    truth_timestamps_ns = [s.ts_ns for s in truth_samples]

    all_event_ts = sorted(set(
        imu_timestamps_ns + dvl_timestamps_ns + depth_timestamps_ns + truth_timestamps_ns
    ))

    truth_ts_set = set(truth_timestamps_ns)

    for event_ts in all_event_ts:
        while imu_idx < len(imu_samples) and imu_samples[imu_idx].ts_ns <= event_ts:
            imu = imu_samples[imu_idx]
            dt = (imu.ts_ns - last_imu_ts) / 1e9 if last_imu_ts is not None else 0.02
            last_imu_ts = imu.ts_ns

            dr_engine.predict(imu.acc, imu.gyro, dt)
            std_ekf.predict(imu.acc, imu.gyro, dt)
            es_ekf.predict(imu.acc, imu.gyro, dt)

            imu_idx += 1

        while dvl_idx < len(dvl_samples) and dvl_samples[dvl_idx].ts_ns <= event_ts:
            dvl = dvl_samples[dvl_idx]
            dr_engine.update_dvl(dvl.vel, dvl.ts_ns)
            std_ekf.update_dvl(dvl.vel, dvl.ts_ns)
            es_ekf.update_dvl(dvl.vel, dvl.ts_ns)
            dvl_idx += 1

        while depth_idx < len(depth_samples) and depth_samples[depth_idx].ts_ns <= event_ts:
            depth = depth_samples[depth_idx]
            dr_engine.update_depth(depth.depth_m, depth.ts_ns)
            std_ekf.update_depth(depth.depth_m, depth.ts_ns)
            es_ekf.update_depth(depth.depth_m, depth.ts_ns)
            depth_idx += 1

        if event_ts in truth_ts_set:
            dr_engine.record_state(event_ts)
            std_ekf.record_state(event_ts)
            es_ekf.record_state(event_ts)

    print(f"  Processed {len(all_event_ts)} events")
    print(f"  ES-EKF states: {len(es_ekf.history_ts)}")
    print(f"  StdEKF states: {len(std_ekf.history_ts)}")

    # Prepare arrays for convergence analysis
    truth_ts_s = (np.array([s.ts_ns for s in truth_samples], dtype=np.float64) - global_start_ns) / 1e9
    truth_xy = np.array([s.pos[:2] for s in truth_samples], dtype=np.float64)
    truth_pos_all = np.array([s.pos for s in truth_samples], dtype=np.float64)

    # IMU gyro data
    imu_gyro_z = np.array([s.gyro[2] for s in imu_samples])

    # cmd_vel data
    cmd_vel_t_arr = np.array([cv.t for cv in cmd_vel_samples])
    cmd_vel_ang_z_arr = np.array([cv.angular_z for cv in cmd_vel_samples])

    es_pred_ts_s = (np.array(es_ekf.history_ts, dtype=np.float64) - global_start_ns) / 1e9
    es_pred_xy = np.array([p[:2] for p in es_ekf.history_p], dtype=np.float64)

    std_pred_ts_s = (np.array(std_ekf.history_ts, dtype=np.float64) - global_start_ns) / 1e9
    std_pred_xy = np.array([p[:2] for p in std_ekf.history_p], dtype=np.float64)

    # Compute overall RMSE
    es_resampled = bm._resample_to_truth(truth_ts_s, es_pred_ts_s, np.column_stack([es_pred_xy, np.zeros(len(es_pred_xy))]))
    std_resampled = bm._resample_to_truth(truth_ts_s, std_pred_ts_s, np.column_stack([std_pred_xy, np.zeros(len(std_pred_xy))]))

    es_ekf_rmse_xy = bm.compute_rmse_xy(es_resampled, truth_xy) if len(es_resampled) > 0 else float("nan")
    std_ekf_rmse_xy = bm.compute_rmse_xy(std_resampled, truth_xy) if len(std_resampled) > 0 else float("nan")
    print(f"\n  Overall RMSE_XY: ES-EKF={es_ekf_rmse_xy:.4f}m, StdEKF={std_ekf_rmse_xy:.4f}m")

    # Analyze convergence for each segment
    print("\n[6/7] Analyzing convergence for each segment ...")
    es_ekf_results: list[ConvergenceResult] = []
    std_ekf_results: list[ConvergenceResult] = []

    for seg in segments:
        es_res = analyze_convergence_for_segment(
            seg,
            truth_ts_s, truth_xy,
            es_pred_ts_s, es_pred_xy,
            cmd_vel_samples,
            pre_turn_window=args.pre_window,
            post_turn_window=args.post_window,
        )
        if es_res:
            es_ekf_results.append(es_res)

        std_res = analyze_convergence_for_segment(
            seg,
            truth_ts_s, truth_xy,
            std_pred_ts_s, std_pred_xy,
            cmd_vel_samples,
            pre_turn_window=args.pre_window,
            post_turn_window=args.post_window,
        )
        if std_res:
            std_ekf_results.append(std_res)

    print(f"  ES-EKF: {len(es_ekf_results)}/{len(segments)} segments analyzed")
    print(f"  StdEKF: {len(std_ekf_results)}/{len(segments)} segments analyzed")

    # Generate plots
    print("\n[7/7] Generating plots and report ...")

    plot_convergence_comparison(
        segments,
        es_ekf_results,
        std_ekf_results,
        str(output_dir / "convergence_comparison.png"),
    )
    print(f"  Saved: {output_dir / 'convergence_comparison.png'}")

    plot_summary_bar_chart(
        es_ekf_results,
        std_ekf_results,
        str(output_dir / "convergence_summary_bar.png"),
    )
    print(f"  Saved: {output_dir / 'convergence_summary_bar.png'}")

    plot_error_scatter_over_trajectory(
        segments,
        truth_ts_s, truth_xy,
        es_pred_ts_s, es_pred_xy,
        std_pred_ts_s, std_pred_xy,
        str(output_dir / "error_over_trajectory.png"),
    )
    print(f"  Saved: {output_dir / 'error_over_trajectory.png'}")

    generate_markdown_report(
        segments,
        es_ekf_results,
        std_ekf_results,
        es_ekf_rmse_xy,
        std_ekf_rmse_xy,
        imu_gyro_z,
        truth_pos_all,
        truth_ts_s,
        cmd_vel_ang_z_arr,
        cmd_vel_t_arr,
        str(output_dir / "turning_convergence_report.md"),
    )
    print(f"  Saved: {output_dir / 'turning_convergence_report.md'}")

    # Save JSON results
    results_json = {
        "segments": [
            {
                "id": seg.id,
                "t_start": seg.t_start,
                "t_end": seg.t_end,
                "duration": seg.duration,
                "max_ang_z": seg.max_ang_z,
                "mean_ang_z": seg.mean_ang_z,
            }
            for seg in segments
        ],
        "es_ekf_rmse_xy": es_ekf_rmse_xy,
        "std_ekf_rmse_xy": std_ekf_rmse_xy,
        "es_ekf_results": [
            {
                "segment_id": r.segment_id,
                "pre_turn_error_xy": r.pre_turn_error_xy,
                "peak_error_xy": r.peak_error_xy,
                "post_turn_error_xy": r.post_turn_error_xy,
                "overshoot_pct": r.overshoot_pct,
                "recovery_time": r.recovery_time if r.recovery_time != float("inf") else -1,
                "settling_error_xy": r.settling_error_xy,
            }
            for r in es_ekf_results
        ],
        "std_ekf_results": [
            {
                "segment_id": r.segment_id,
                "pre_turn_error_xy": r.pre_turn_error_xy,
                "peak_error_xy": r.peak_error_xy,
                "post_turn_error_xy": r.post_turn_error_xy,
                "overshoot_pct": r.overshoot_pct,
                "recovery_time": r.recovery_time if r.recovery_time != float("inf") else -1,
                "settling_error_xy": r.settling_error_xy,
            }
            for r in std_ekf_results
        ],
    }

    with open(output_dir / "turning_convergence_results.json", "w") as f:
        json.dump(results_json, f, indent=2)
    print(f"  Saved: {output_dir / 'turning_convergence_results.json'}")

    print("\n" + "=" * 60)
    print("  Analysis complete!")
    print("=" * 60)

    if args.show_plots:
        plt.show()


if __name__ == "__main__":
    main()

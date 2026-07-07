#!/usr/bin/env python3
"""
分析 MCAP 数据集中的 AUV 转向特征。

从录制的 .mcap 数据包中读取 IMU 角速度数据，计算角速度幅值，
识别剧烈转向时间段，并输出详细报告。

使用示例:
  python3 tools/analyze_turning.py --input log/experiments/benchmark_120s/rosbag_mcap/rosbag_mcap_0.mcap
"""

import argparse
import math
import sys
from pathlib import Path
from dataclasses import dataclass

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = PROJECT_ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

try:
    from mcap_ros2.reader import read_ros2_messages
except ImportError as exc:
    raise SystemExit("mcap 和 mcap-ros2-support 是必需的。安装: pip install mcap mcap-ros2-support") from exc


@dataclass
class ImuSample:
    ts_ns: int
    wx: float
    wy: float
    wz: float
    magnitude: float


def select_timestamp_ns(message_wrapper) -> int:
    publish_time_ns = int(getattr(message_wrapper, "publish_time_ns", 0))
    if publish_time_ns > 0:
        return publish_time_ns
    return int(message_wrapper.log_time_ns)


def read_imu_data(mcap_path: Path, imu_topic: str) -> list[ImuSample]:
    samples = []
    for decoded in read_ros2_messages(str(mcap_path), topics=[imu_topic]):
        msg = decoded.ros_msg
        ts_ns = select_timestamp_ns(decoded)
        wx = float(msg.angular_velocity.x)
        wy = float(msg.angular_velocity.y)
        wz = float(msg.angular_velocity.z)
        magnitude = math.sqrt(wx**2 + wy**2 + wz**2)
        samples.append(ImuSample(ts_ns, wx, wy, wz, magnitude))
    samples.sort(key=lambda s: s.ts_ns)
    return samples


def find_turning_segments(
    samples: list[ImuSample],
    threshold: float,
    min_gap_ns: int = 500_000_000,
) -> list[dict]:
    """
    找出角速度超过阈值的剧烈转向时间段。

    Args:
        samples: IMU 样本列表
        threshold: 角速度幅值阈值 (rad/s)
        min_gap_ns: 合并片段的最小间隔 (纳秒)，默认 0.5s

    Returns:
        转向段列表，每个段包含 start_ns, end_ns, duration_s, max_omega, start_idx, end_idx
    """
    if not samples:
        return []

    above_mask = [s.magnitude > threshold for s in samples]

    segments = []
    in_segment = False
    seg_start_idx = 0

    for i, above in enumerate(above_mask):
        if above and not in_segment:
            in_segment = True
            seg_start_idx = i
        elif not above and in_segment:
            in_segment = False
            segments.append((seg_start_idx, i - 1))

    if in_segment:
        segments.append((seg_start_idx, len(samples) - 1))

    if not segments:
        return []

    merged = [segments[0]]
    for seg in segments[1:]:
        prev_end_ns = samples[merged[-1][1]].ts_ns
        curr_start_ns = samples[seg[0]].ts_ns
        if (curr_start_ns - prev_end_ns) <= min_gap_ns:
            merged[-1] = (merged[-1][0], seg[1])
        else:
            merged.append(seg)

    result = []
    for start_idx, end_idx in merged:
        seg_samples = samples[start_idx:end_idx + 1]
        start_ns = seg_samples[0].ts_ns
        end_ns = seg_samples[-1].ts_ns
        duration_s = (end_ns - start_ns) / 1e9
        max_omega = max(s.magnitude for s in seg_samples)
        max_omega_sample = max(seg_samples, key=lambda s: s.magnitude)

        result.append({
            "start_ns": start_ns,
            "end_ns": end_ns,
            "duration_s": duration_s,
            "max_omega": max_omega,
            "max_omega_time_ns": max_omega_sample.ts_ns,
            "max_wx": max_omega_sample.wx,
            "max_wy": max_omega_sample.wy,
            "max_wz": max_omega_sample.wz,
            "start_idx": start_idx,
            "end_idx": end_idx,
            "mean_omega": np.mean([s.magnitude for s in seg_samples]),
            "sample_count": len(seg_samples),
        })

    return result


def print_report(
    mcap_path: Path,
    samples: list[ImuSample],
    segments: list[dict],
    threshold: float,
) -> None:
    if not samples:
        print("[错误] 未找到 IMU 数据。")
        return

    global_start_ns = samples[0].ts_ns
    global_end_ns = samples[-1].ts_ns
    duration_total = (global_end_ns - global_start_ns) / 1e9

    magnitudes = [s.magnitude for s in samples]
    mag_array = np.array(magnitudes)

    print("=" * 70)
    print("  AUV 转向特征分析报告")
    print("=" * 70)
    print()
    print("数据概览:")
    print(f"  输入文件:        {mcap_path}")
    print(f"  IMU 样本数:      {len(samples)}")
    print(f"  数据时长:        {duration_total:.2f} s")
    print(f"  采样率:          {len(samples) / duration_total:.1f} Hz")
    print()
    print("角速度统计:")
    print(f"  最小 |ω|:        {mag_array.min():.4f} rad/s")
    print(f"  最大 |ω|:        {mag_array.max():.4f} rad/s")
    print(f"  平均 |ω|:        {mag_array.mean():.4f} rad/s")
    print(f"  中位数 |ω|:      {np.median(mag_array):.4f} rad/s")
    print(f"  标准差:          {mag_array.std():.4f} rad/s")
    print(f"  95% 分位数:      {np.percentile(mag_array, 95):.4f} rad/s")
    print(f"  阈值:            {threshold:.4f} rad/s")
    print()

    if not segments:
        print(f"未检测到超过阈值 ({threshold:.4f} rad/s) 的剧烈转向段。")
        return

    total_turning_time = sum(s["duration_s"] for s in segments)
    turning_ratio = total_turning_time / duration_total * 100

    print(f"检测到 {len(segments)} 个剧烈转向段:")
    print(f"  总转向时间:      {total_turning_time:.2f} s ({turning_ratio:.1f}%)")
    print()

    print("-" * 70)
    print(f"{'段号':<5} {'开始时间(s)':<14} {'结束时间(s)':<14} {'持续(s)':<10} {'最大|ω|(rad/s)':<16} {'样本数':<8}")
    print("-" * 70)

    for i, seg in enumerate(segments, 1):
        start_s = (seg["start_ns"] - global_start_ns) / 1e9
        end_s = (seg["end_ns"] - global_start_ns) / 1e9
        max_time_s = (seg["max_omega_time_ns"] - global_start_ns) / 1e9
        print(
            f"{i:<5} "
            f"{start_s:<14.3f} "
            f"{end_s:<14.3f} "
            f"{seg['duration_s']:<10.3f} "
            f"{seg['max_omega']:<16.4f} "
            f"{seg['sample_count']:<8}"
        )
        print(
            f"      最大角速度时刻: t={max_time_s:.3f}s, "
            f"ω=({seg['max_wx']:.4f}, {seg['max_wy']:.4f}, {seg['max_wz']:.4f}) rad/s, "
            f"平均|ω|={seg['mean_omega']:.4f} rad/s"
        )
    print("-" * 70)
    print()

    longest = max(segments, key=lambda s: s["duration_s"])
    strongest = max(segments, key=lambda s: s["max_omega"])
    print("关键发现:")
    print(f"  最长转向段:      第 {segments.index(longest)+1} 段, 持续 {longest['duration_s']:.2f}s")
    print(f"  最剧烈转向段:    第 {segments.index(strongest)+1} 段, 最大|ω| = {strongest['max_omega']:.4f} rad/s")
    print()
    print("=" * 70)


def main() -> None:
    parser = argparse.ArgumentParser(description="分析 MCAP 数据集中的 AUV 转向特征")
    parser.add_argument("--input", type=Path, required=True, help="输入 .mcap 文件路径")
    parser.add_argument("--imu-topic", default="/auv/sensors/imu", help="IMU topic (默认: /auv/sensors/imu)")
    parser.add_argument("--threshold", type=float, default=0.5, help="角速度阈值 rad/s (默认: 0.5)")
    parser.add_argument("--min-gap", type=float, default=0.5, help="合并片段最小间隔秒数 (默认: 0.5)")
    args = parser.parse_args()

    if not args.input.exists():
        raise SystemExit(f"输入文件不存在: {args.input}")

    print(f"[1/3] 读取 IMU 数据 (topic: {args.imu_topic}) ...")
    samples = read_imu_data(args.input, args.imu_topic)
    print(f"      共读取 {len(samples)} 个 IMU 样本")

    if not samples:
        raise SystemExit("未读取到任何 IMU 数据。请检查 topic 名称是否正确。")

    print(f"[2/3] 检测转向段 (threshold={args.threshold:.3f} rad/s) ...")
    min_gap_ns = int(args.min_gap * 1e9)
    segments = find_turning_segments(samples, args.threshold, min_gap_ns)
    print(f"      检测到 {len(segments)} 个转向段")

    print(f"[3/3] 生成报告 ...")
    print()
    print_report(args.input, samples, segments, args.threshold)


if __name__ == "__main__":
    main()

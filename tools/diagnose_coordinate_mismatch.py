#!/usr/bin/env python3
"""诊断坐标系统不匹配问题。

问题分析：
- 新MCAP中真值起点为 [620.9963, -0.0004, 13.0566]
- EKF正确对齐初始位置
- 但RMSE高达470-483米，说明估计轨迹与真值轨迹不一致

此脚本分析：
1. 真值轨迹范围
2. EKF估计轨迹范围
3. DVL速度积分是否导致漂移
4. 坐标系是否一致
"""

import sys
from pathlib import Path
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / 'tools'))

from offline_ekf_benchmark import read_mcap_sensor_data

def main():
    mcap_path = PROJECT_ROOT / "log/experiments/20260503_150449/rosbag/rosbag_0.mcap"
    if not mcap_path.exists():
        sys.exit(f"MCAP not found: {mcap_path}")

    print(f"Reading MCAP: {mcap_path}")
    imu_s, dvl_s, depth_s, truth_s = read_mcap_sensor_data(
        mcap_path, "/auv/sensors/imu", "/auv/sensors/dvl", "/auv/sensors/depth",
        ["/auv/visual/truth_marker"], dvl_frame="world", apply_coord_transform=True, verbose=True)

    if not truth_s or not imu_s:
        sys.exit("No truth or IMU samples.")

    truth_ts = np.array([s.ts_ns for s in truth_s], dtype=np.int64)
    truth_pos = np.array([s.pos for s in truth_s], dtype=float)

    start_ns = truth_ts[0]
    dur = (truth_ts[-1] - start_ns) / 1e9

    print("\n=== 真值分析 ===")
    print(f"  时长: {dur:.1f}s")
    print(f"  样本数: {len(truth_s)}")
    print(f"  起点: {truth_pos[0]}")
    print(f"  终点: {truth_pos[-1]}")
    print(f"  X范围: [{truth_pos[:, 0].min():.2f}, {truth_pos[:, 0].max():.2f}]")
    print(f"  Y范围: [{truth_pos[:, 1].min():.2f}, {truth_pos[:, 1].max():.2f}]")
    print(f"  Z范围: [{truth_pos[:, 2].min():.2f}, {truth_pos[:, 2].max():.2f}]")
    print(f"  移动距离: {np.sqrt(np.sum((truth_pos[-1] - truth_pos[0])**2)):.2f}m")

    # DVL分析
    dvl_vel = np.array([s.vel for s in dvl_s], dtype=float)
    dvl_ts = np.array([s.ts_ns for s in dvl_s], dtype=np.int64)

    print("\n=== DVL速度分析 ===")
    print(f"  样本数: {len(dvl_s)}")
    print(f"  速度范围 X: [{dvl_vel[:, 0].min():.3f}, {dvl_vel[:, 0].max():.3f}] m/s")
    print(f"  速度范围 Y: [{dvl_vel[:, 1].min():.3f}, {dvl_vel[:, 1].max():.3f}] m/s")
    print(f"  速度范围 Z: [{dvl_vel[:, 2].min():.3f}, {dvl_vel[:, 2].max():.3f}] m/s")

    # 积分DVL速度得到估计轨迹
    init_pos = truth_pos[0].copy()
    est_pos = init_pos.copy()
    est_positions = [est_pos.copy()]
    est_timestamps = [dvl_ts[0]]

    for i in range(1, len(dvl_s)):
        dt = (dvl_ts[i] - dvl_ts[i-1]) / 1e9
        est_pos = est_pos + dvl_vel[i-1] * dt
        est_positions.append(est_pos.copy())
        est_timestamps.append(dvl_ts[i])

    est_positions = np.array(est_positions)
    est_timestamps = np.array(est_timestamps)

    print("\n=== DVL积分轨迹分析 ===")
    print(f"  积分起点: {est_positions[0]}")
    print(f"  积分终点: {est_positions[-1]}")
    print(f"  终点误差: {np.sqrt(np.sum((est_positions[-1] - truth_pos[-1])**2)):.2f}m")
    print(f"  X终点差异: {est_positions[-1][0] - truth_pos[-1]:.2f}m")
    print(f"  Y终点差异: {est_positions[-1][1] - truth_pos[-1]:.2f}m")
    print(f"  Z终点差异: {est_positions[-1][2] - truth_pos[-1]:.2f}m")

    # 与真值比较（插值到相同时间）
    from scipy.interpolate import interp1d
    truth_t = truth_ts.astype(float) / 1e9
    est_t = est_timestamps.astype(float) / 1e9

    interp_x = interp1d(est_t, est_positions[:, 0], kind='linear', fill_value='extrapolate')
    interp_y = interp1d(est_t, est_positions[:, 1], kind='linear', fill_value='extrapolate')
    interp_z = interp1d(est_t, est_positions[:, 2], kind='linear', fill_value='extrapolate')

    est_at_truth = np.column_stack([
        interp_x(truth_t),
        interp_y(truth_t),
        interp_z(truth_t),
    ])

    errors = np.sqrt(np.sum((truth_pos - est_at_truth)**2, axis=1))
    rmse = np.sqrt(np.mean(errors**2))

    print(f"\n=== DVL积分 vs 真值 ===")
    print(f"  RMSE: {rmse:.3f}m")
    print(f"  最大误差: {errors.max():.3f}m")
    print(f"  平均误差: {errors.mean():.3f}m")

    print("\n=== 诊断结论 ===")
    if rmse > 10:
        print("❌ DVL积分与真值严重不匹配！")
        print("  可能原因:")
        print("  1. DVL速度坐标系错误（body vs world）")
        print("  2. 坐标系统不一致（UE4 vs NED）")
        print("  3. DVL速度方向符号错误")
    else:
        print("✅ DVL积分与真值基本一致")
        print("  问题可能出在EKF算法本身")

if __name__ == "__main__":
    main()

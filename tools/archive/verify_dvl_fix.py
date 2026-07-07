#!/usr/bin/env python3
"""
快速验证DVL坐标系修复效果

检查：
1. DVL速度方向是否与真值运动方向一致
2. DVL积分轨迹与真值轨迹的对比
"""

import struct
import numpy as np
from pathlib import Path
import mcap.reader
import sys

# 添加项目路径
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "algorithm"))

def read_mcap_data(mcap_file):
    """读取MCAP文件中的真值和DVL数据"""
    print(f"\n读取MCAP文件: {mcap_file}")
    
    truth_positions = []
    dvl_velocities = []
    
    with open(mcap_file, "rb") as f:
        reader = mcap.reader.make_reader(f)
        for schema, channel, message in reader.iter_messages():
            topic = channel.topic
            
            if topic == "/truth_marker":
                # 解析 PositionStamped: stamp(8B) + position(24B)
                stamp_sec = struct.unpack('<i', message.data[0:4])[0]
                stamp_nsec = struct.unpack('<i', message.data[4:8])[0]
                ts = stamp_sec + stamp_nsec / 1e9
                
                x = struct.unpack('<d', message.data[8:16])[0]
                y = struct.unpack('<d', message.data[16:24])[0]
                z = struct.unpack('<d', message.data[24:32])[0]
                
                truth_positions.append((ts, [x, y, z]))
                
            elif topic == "/auv/dvl":
                # 解析 DVL速度: stamp(8B) + velocity(24B)
                stamp_sec = struct.unpack('<i', message.data[0:4])[0]
                stamp_nsec = struct.unpack('<i', message.data[4:8])[0]
                ts = stamp_sec + stamp_nsec / 1e9
                
                vx = struct.unpack('<d', message.data[8:16])[0]
                vy = struct.unpack('<d', message.data[16:24])[0]
                vz = struct.unpack('<d', message.data[24:32])[0]
                
                dvl_velocities.append((ts, [vx, vy, vz]))
    
    return truth_positions, dvl_velocities

def verify_dvl_direction(truth_positions, dvl_velocities):
    """验证DVL速度方向是否与真值一致"""
    print("="*80)
    print("验证DVL速度方向")
    print("="*80)
    
    if len(truth_positions) < 10 or len(dvl_velocities) < 10:
        print("数据不足")
        return False
    
    # 计算真值的总体位移
    truth_pos_array = np.array([p[1] for p in truth_positions])
    truth_times = np.array([p[0] for p in truth_positions])
    
    total_displacement = truth_pos_array[-1] - truth_pos_array[0]
    total_time = truth_times[-1] - truth_times[0]
    avg_truth_velocity = total_displacement / total_time
    
    # 计算DVL平均速度
    dvl_vel_array = np.array([v[1] for v in dvl_velocities])
    avg_dvl_velocity = np.mean(dvl_vel_array, axis=0)
    
    print(f"\n总体统计 (时间跨度: {total_time:.2f}s):")
    print(f"  真值总位移: {total_displacement}")
    print(f"  真值平均速度: {avg_truth_velocity}")
    print(f"  DVL平均速度: {avg_dvl_velocity}")
    
    # 检查方向
    print(f"\n方向对比:")
    direction_match = True
    for i, axis in enumerate(['X(北)', 'Y(东)', 'Z(下)']):
        truth_dir = "正" if avg_truth_velocity[i] > 0 else "负"
        dvl_dir = "正" if avg_dvl_velocity[i] > 0 else "负"
        
        if avg_truth_velocity[i] * avg_dvl_velocity[i] > 0:
            match_symbol = "✓ 一致"
        else:
            match_symbol = "✗ 方向相反！"
            direction_match = False
        
        print(f"  {axis}: 真值{truth_dir}({avg_truth_velocity[i]:.3f}), DVL{dvl_dir}({avg_dvl_velocity[i]:.3f}) {match_symbol}")
    
    return direction_match

def integrate_dvl_trajectory(dvl_velocities, start_position=None):
    """积分DVL速度得到轨迹"""
    if start_position is None:
        start_position = [0.0, 0.0, 0.0]
    
    positions = [start_position.copy()]
    current_pos = np.array(start_position)
    
    for i in range(1, len(dvl_velocities)):
        dt = dvl_velocities[i][0] - dvl_velocities[i-1][0]
        vel = np.array(dvl_velocities[i-1][1])
        current_pos = current_pos + vel * dt
        positions.append(current_pos.copy())
    
    return np.array(positions)

def compare_trajectories(truth_positions, dvl_velocities):
    """对比DVL积分轨迹与真值轨迹"""
    print("\n" + "="*80)
    print("对比DVL积分轨迹与真值轨迹")
    print("="*80)
    
    # 使用第一帧真值作为DVL积分起点
    start_pos = truth_positions[0][1]
    dvl_trajectory = integrate_dvl_trajectory(dvl_velocities, start_pos=start_pos)
    
    truth_pos_array = np.array([p[1] for p in truth_positions])
    
    # 计算终点
    print(f"\n起点对比:")
    print(f"  真值起点: {truth_pos_array[0]}")
    print(f"  DVL起点: {dvl_trajectory[0]}")
    
    print(f"\n终点对比:")
    print(f"  真值终点: {truth_pos_array[-1]}")
    print(f"  DVL终点: {dvl_trajectory[-1]}")
    
    endpoint_error = np.linalg.norm(dvl_trajectory[-1] - truth_pos_array[-1])
    print(f"\n  终点误差: {endpoint_error:.3f} m")
    
    # 采样到相同长度进行RMSE计算
    n_samples = min(len(truth_pos_array), len(dvl_trajectory))
    truth_sampled = truth_pos_array[:n_samples]
    dvl_sampled = dvl_trajectory[:n_samples]
    
    rmse = np.sqrt(np.mean(np.sum((dvl_sampled - truth_sampled)**2, axis=1)))
    print(f"  RMSE (前{n_samples}个点): {rmse:.3f} m")
    
    # 最大误差
    pointwise_errors = np.sqrt(np.sum((dvl_sampled - truth_sampled)**2, axis=1))
    max_error = np.max(pointwise_errors)
    max_error_idx = np.argmax(pointwise_errors)
    print(f"  最大误差: {max_error:.3f} m (在索引 {max_error_idx})")
    
    return endpoint_error, rmse

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python3 verify_dvl_fix.py <mcap_file>")
        sys.exit(1)
    
    mcap_file = sys.argv[1]
    
    # 读取数据
    truth_positions, dvl_velocities = read_mcap_data(mcap_file)
    
    print(f"\n数据量:")
    print(f"  真值数据点: {len(truth_positions)}")
    print(f"  DVL数据点: {len(dvl_velocities)}")
    
    # 验证方向
    direction_ok = verify_dvl_direction(truth_positions, dvl_velocities)
    
    # 对比轨迹
    endpoint_error, rmse = compare_trajectories(truth_positions, dvl_velocities)
    
    # 最终结论
    print("\n" + "="*80)
    print("最终结论")
    print("="*80)
    if direction_ok and rmse < 10.0:
        print("✓ DVL坐标系修复成功！")
        print(f"  - 速度方向与真值一致")
        print(f"  - DVL积分RMSE: {rmse:.3f} m")
    else:
        if not direction_ok:
            print("✗ DVL速度方向仍不正确")
        if rmse >= 10.0:
            print(f"✗ DVL积分误差过大: {rmse:.3f} m")

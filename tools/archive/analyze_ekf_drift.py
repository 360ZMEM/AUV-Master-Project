#!/usr/bin/env python3
"""
深度分析实验#4的EKF不一致问题

实验#4 (20260503_151522) 发现了关键异常：
- TF Ground Truth: dx=+28.42m（向前）
- EKF Filtered: dx=-14.93m（向后！）
- DVL积分: 30.19m（向前，与TF一致）

这说明EKF滤波器在某些情况下会输出错误的方向。
"""

import sys
import os
os.environ['ROS_VERSION'] = '2'

import rosbag2_py
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message
import numpy as np
from pathlib import Path

MCAP_PATH = "/home/auv_user/auv_ws/AUV-Master-Project/log/experiments/20260503_151522/rosbag/rosbag_0.mcap"


def read_mcap_data(mcap_path, max_duration_s=120):
    """读取mcap数据，返回所有相关话题的时间序列"""
    storage_options = rosbag2_py.StorageOptions(uri=mcap_path, storage_id="mcap")
    converter_options = rosbag2_py.ConverterOptions(
        input_serialization_format="cdr",
        output_serialization_format="cdr",
    )

    reader = rosbag2_py.SequentialReader()
    reader.open(storage_options, converter_options)

    topics_and_types = reader.get_all_topics_and_types()
    topic_type_map = {t.name: t.type for t in topics_and_types}

    data = {
        "tf": [],
        "odom_filtered": [],
        "dvl": [],
        "cmd_vel": [],
        "imu": [],
        "depth": [],
        "setpoint": [],
        "controller_debug": [],
    }

    first_ts = None
    msg_count = 0

    while reader.has_next():
        topic, msg_data, ts = reader.read_next()
        if first_ts is None:
            first_ts = ts
        
        duration_ns = ts - first_ts
        if duration_ns > max_duration_s * 1e9:
            break

        msg_count += 1
        ts_s = ts / 1e9

        try:
            msg_type = get_message(topic_type_map[topic])
            msg = deserialize_message(msg_data, msg_type)

            # TF
            if topic == "/tf":
                if hasattr(msg, 'transforms'):
                    for transform in msg.transforms:
                        if transform.child_frame_id == "auv/base_link":
                            data["tf"].append({
                                "ts": ts_s,
                                "x": float(transform.transform.translation.x),
                                "y": float(transform.transform.translation.y),
                                "z": float(transform.transform.translation.z),
                                "qx": float(transform.transform.rotation.x),
                                "qy": float(transform.transform.rotation.y),
                                "qz": float(transform.transform.rotation.z),
                                "qw": float(transform.transform.rotation.w),
                            })

            # Filtered odometry
            elif topic == "/auv/state/filtered":
                pos = msg.pose.pose.position
                vel = msg.twist.twist.linear
                data["odom_filtered"].append({
                    "ts": ts_s,
                    "x": float(pos.x),
                    "y": float(pos.y),
                    "z": float(pos.z),
                    "vx": float(vel.x),
                    "vy": float(vel.y),
                    "vz": float(vel.z),
                })

            # DVL
            elif topic == "/auv/sensors/dvl":
                data["dvl"].append({
                    "ts": ts_s,
                    "vx": float(msg.twist.linear.x),
                    "vy": float(msg.twist.linear.y),
                    "vz": float(msg.twist.linear.z),
                })

            # cmd_vel
            elif topic == "/cmd_vel":
                data["cmd_vel"].append({
                    "ts": ts_s,
                    "linear_x": float(msg.linear.x),
                    "linear_y": float(msg.linear.y),
                    "linear_z": float(msg.linear.z),
                })

            # IMU
            elif topic == "/auv/sensors/imu":
                data["imu"].append({
                    "ts": ts_s,
                    "ax": float(msg.linear_acceleration.x),
                    "ay": float(msg.linear_acceleration.y),
                    "az": float(msg.linear_acceleration.z),
                    "gx": float(msg.angular_velocity.x),
                    "gy": float(msg.angular_velocity.y),
                    "gz": float(msg.angular_velocity.z),
                })

            # Depth
            elif topic == "/auv/sensors/depth":
                data["depth"].append({
                    "ts": ts_s,
                    "depth": float(msg.data),
                })

            # Setpoint
            elif topic == "/auv/control/setpoint":
                data["setpoint"].append({
                    "ts": ts_s,
                    "target_speed_mps": float(getattr(msg, 'target_speed_mps', 0)),
                    "target_depth_m": float(getattr(msg, 'target_depth_m', 0)),
                    "target_heading_rad": float(getattr(msg, 'target_heading_rad', 0)),
                })

            # Controller debug
            elif topic == "/auv/controller/debug":
                data["controller_debug"].append({
                    "ts": ts_s,
                    "text": str(msg.data)[:300],
                })

        except Exception as e:
            pass

    print(f"读取完成: {msg_count} 条消息")
    print(f"  TF: {len(data['tf'])}")
    print(f"  Odom: {len(data['odom_filtered'])}")
    print(f"  DVL: {len(data['dvl'])}")
    print(f"  cmd_vel: {len(data['cmd_vel'])}")
    print(f"  IMU: {len(data['imu'])}")
    print(f"  Depth: {len(data['depth'])}")
    print(f"  Setpoint: {len(data['setpoint'])}")
    print(f"  Debug: {len(data['controller_debug'])}")

    return data


def analyze_ekf_drift(data):
    """分析EKF漂移的根本原因"""
    tf_data = data["tf"]
    odom_data = data["odom_filtered"]
    dvl_data = data["dvl"]
    cmd_data = data["cmd_vel"]
    debug_data = data["controller_debug"]

    if len(tf_data) < 2 or len(odom_data) < 2:
        print("数据不足")
        return

    # 计算位置差异
    tf_start = tf_data[0]
    tf_end = tf_data[-1]
    odom_start = odom_data[0]
    odom_end = odom_data[-1]

    print(f"\n{'='*80}")
    print("位置对比:")
    print(f"{'='*80}")
    print(f"TF Ground Truth:")
    print(f"  起点: ({tf_start['x']:.2f}, {tf_start['y']:.2f}, {tf_start['z']:.2f}) @ t={tf_start['ts']:.2f}s")
    print(f"  终点: ({tf_end['x']:.2f}, {tf_end['y']:.2f}, {tf_end['z']:.2f}) @ t={tf_end['ts']:.2f}s")
    print(f"  位移: dx={tf_end['x']-tf_start['x']:.2f}m")
    
    print(f"\nEKF Filtered:")
    print(f"  起点: ({odom_start['x']:.2f}, {odom_start['y']:.2f}, {odom_start['z']:.2f}) @ t={odom_start['ts']:.2f}s")
    print(f"  终点: ({odom_end['x']:.2f}, {odom_end['y']:.2f}, {odom_end['z']:.2f}) @ t={odom_end['ts']:.2f}s")
    print(f"  位移: dx={odom_end['x']-odom_start['x']:.2f}m")

    # 检查起点是否一致
    dx_start = abs(tf_start['x'] - odom_start['x'])
    print(f"\n起点差异: {dx_start:.2f}m")
    if dx_start > 1.0:
        print(f"  ⚠️ EKF起点与GT不一致！差异{dx_start:.2f}m")

    # 分析速度符号
    print(f"\n{'='*80}")
    print("速度对比（前10个样本）:")
    print(f"{'='*80}")
    
    # 找到时间对齐的样本
    for i in range(min(10, len(dvl_data))):
        dvl_ts = dvl_data[i]['ts']
        dvl_vx = dvl_data[i]['vx']
        
        # 找到最近的odom样本
        closest_odom = min(odom_data, key=lambda x: abs(x['ts'] - dvl_ts))
        odom_vx = closest_odom['vx']
        
        if i < 5 or abs(dvl_vx - odom_vx) > 0.5:
            print(f"  t={dvl_ts:.2f}s: DVL vx={dvl_vx:.3f} m/s, EKF vx={odom_vx:.3f} m/s, 差异={abs(dvl_vx-odom_vx):.3f}")

    # 查找EKF速度符号翻转的时间点
    print(f"\n{'='*80}")
    print("EKF速度符号分析:")
    print(f"{'='*80}")
    
    dvl_vx_values = [d['vx'] for d in dvl_data]
    odom_vx_values = [o['vx'] for o in odom_data]
    
    if dvl_vx_values:
        print(f"DVL vx范围: [{min(dvl_vx_values):.3f}, {max(dvl_vx_values):.3f}] m/s")
        print(f"DVL vx平均: {np.mean(dvl_vx_values):.3f} m/s")
    
    if odom_vx_values:
        neg_count = sum(1 for v in odom_vx_values if v < 0)
        pos_count = sum(1 for v in odom_vx_values if v > 0)
        print(f"EKF vx范围: [{min(odom_vx_values):.3f}, {max(odom_vx_values):.3f}] m/s")
        print(f"EKF vx平均: {np.mean(odom_vx_values):.3f} m/s")
        print(f"EKF vx符号: 正={pos_count}, 负={neg_count}, 负占比={neg_count/len(odom_vx_values)*100:.1f}%")

    # 分析cmd_vel
    print(f"\n{'='*80}")
    print("cmd_vel分析:")
    print(f"{'='*80}")
    
    if cmd_data:
        linear_x_vals = [c['linear_x'] for c in cmd_data]
        print(f"linear.x范围: [{min(linear_x_vals):.2f}, {max(linear_x_vals):.2f}]")
        print(f"linear.x平均: {np.mean(linear_x_vals):.2f}")
        
        # 检查cmd_vel是否可能影响EKF
        neg_cmd_count = sum(1 for v in linear_x_vals if v < 0)
        print(f"负命令占比: {neg_cmd_count/len(linear_x_vals)*100:.1f}%")

    # 打印前几个debug消息
    if debug_data:
        print(f"\n{'='*80}")
        print("Controller Debug (前5条):")
        print(f"{'='*80}")
        for d in debug_data[:5]:
            print(f"  t={d['ts']:.2f}s: {d['text'][:200]}")


def main():
    print("="*80)
    print("实验#4 EKF不一致深度分析")
    print("="*80)
    print(f"文件: {MCAP_PATH}\n")

    data = read_mcap_data(MCAP_PATH, max_duration_s=120)
    analyze_ekf_drift(data)


if __name__ == "__main__":
    main()

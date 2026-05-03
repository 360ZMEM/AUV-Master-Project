#!/usr/bin/env python3
"""
AUV mcap实验数据分析工具 V3 - 使用ros2 bag API

正确解析ROS2 CDR格式的消息，提取ground_truth、DVL速度、控制命令等指标。
"""

import sys
import os
import json
import subprocess
from pathlib import Path
from datetime import datetime

# 设置ROS2环境
os.environ['ROS_VERSION'] = '2'

# 尝试导入rosbag2_py
try:
    import rosbag2_py
    from rclpy.serialization import deserialize_message
    from rosidl_runtime_py.utilities import get_message
    HAS_ROSBAG2 = True
    print("[INFO] rosbag2_py available")
except ImportError as e:
    HAS_ROSBAG2 = False
    print(f"[WARN] rosbag2_py not available: {e}")

ROOT_DIR = Path("/home/auv_user/auv_ws/AUV-Master-Project")
EXPERIMENTS_DIR = ROOT_DIR / "log" / "experiments"


def find_all_mcaps(base_dir):
    """扫描所有mcap文件并按修改时间排序"""
    mcaps = []
    for p in Path(base_dir).rglob("*.mcap"):
        stat = p.stat()
        mcaps.append({
            "path": str(p),
            "mtime": stat.st_mtime,
            "mtime_str": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
            "size_mb": stat.st_size / (1024 * 1024),
            "parent": str(p.parent.parent.name),
        })
    mcaps.sort(key=lambda x: x["mtime"], reverse=True)
    return mcaps


def get_bag_info(mcap_path):
    """使用ros2 bag info获取bag信息"""
    try:
        result = subprocess.run(
            ["ros2", "bag", "info", mcap_path],
            capture_output=True, text=True, timeout=30
        )
        info = {}
        for line in result.stdout.split('\n'):
            if ':' in line:
                key, value = line.split(':', 1)
                info[key.strip()] = value.strip()
        return info
    except:
        return {}


def read_mcap_ros2(mcap_path, max_duration_s=120):
    """使用rosbag2_py读取mcap文件，提取关键数据"""
    if not HAS_ROSBAG2:
        return None

    # 存储数据
    gt_positions = []  # ground truth from truth_marker or tf
    dvl_velocities = []
    cmd_vel_commands = []
    setpoints = []
    odom_filtered = []
    sensor_status = []
    controller_debug = []

    storage_options = rosbag2_py.StorageOptions(
        uri=mcap_path,
        storage_id="mcap",
    )
    converter_options = rosbag2_py.ConverterOptions(
        input_serialization_format="cdr",
        output_serialization_format="cdr",
    )

    reader = rosbag2_py.SequentialReader()
    reader.open(storage_options, converter_options)

    topics_and_types = reader.get_all_topics_and_types()
    topic_type_map = {t.name: t.type for t in topics_and_types}

    first_ts = None
    last_ts = None
    msg_count = 0

    print(f"  开始读取消息...")

    while reader.has_next():
        topic, data, ts = reader.read_next()
        
        if first_ts is None:
            first_ts = ts
        last_ts = ts
        
        # 限制持续时间
        duration_ns = (ts - first_ts) if first_ts else 0
        if duration_ns > max_duration_s * 1e9:
            break

        msg_count += 1
        if msg_count % 10000 == 0:
            print(f"    已读取 {msg_count} 条消息...")

        try:
            msg_type = get_message(topic_type_map[topic])
            msg = deserialize_message(data, msg_type)
            ts_s = ts / 1e9

            # 提取DVL速度 (geometry_msgs/msg/TwistStamped)
            if topic == "/auv/sensors/dvl":
                if hasattr(msg, 'twist') and msg.twist:
                    dvl_velocities.append({
                        "ts": ts_s,
                        "vx": float(msg.twist.linear.x),
                        "vy": float(msg.twist.linear.y),
                        "vz": float(msg.twist.linear.z),
                    })

            # 提取cmd_vel (geometry_msgs/msg/Twist)
            elif topic == "/cmd_vel":
                cmd_vel_commands.append({
                    "ts": ts_s,
                    "linear_x": float(msg.linear.x),
                    "linear_y": float(msg.linear.y),
                    "linear_z": float(msg.linear.z),
                    "angular_x": float(msg.angular.x),
                    "angular_y": float(msg.angular.y),
                    "angular_z": float(msg.angular.z),
                })

            # 提取filtered odometry (nav_msgs/msg/Odometry)
            elif topic == "/auv/state/filtered":
                pos = msg.pose.pose.position
                odom_filtered.append({
                    "ts": ts_s,
                    "x": float(pos.x),
                    "y": float(pos.y),
                    "z": float(pos.z),
                })

            # 提取setpoint (auv_interfaces/msg/Setpoint)
            elif topic == "/auv/control/setpoint":
                setpoints.append({
                    "ts": ts_s,
                    "target_speed_mps": float(getattr(msg, 'target_speed_mps', 0)),
                    "target_depth_m": float(getattr(msg, 'target_depth_m', 0)),
                    "target_heading_rad": float(getattr(msg, 'target_heading_rad', 0)),
                })

            # 提取sensor status (auv_interfaces/msg/SensorStatus)
            elif topic == "/auv/sensors/status":
                sensor_status.append({
                    "ts": ts_s,
                    "dvl_valid": bool(getattr(msg, 'dvl_valid', False)),
                    "depth_m": float(getattr(msg, 'depth_m', 0)),
                })

            # 提取controller debug
            elif topic == "/auv/controller/debug":
                if hasattr(msg, 'data'):
                    controller_debug.append({
                        "ts": ts_s,
                        "text": str(msg.data)[:200],
                    })

            # 提取tf (ground truth)
            elif topic == "/tf":
                if hasattr(msg, 'transforms') and msg.transforms:
                    for transform in msg.transforms:
                        if transform.child_frame_id == "auv/base_link":
                            gt_positions.append({
                                "ts": ts_s,
                                "x": float(transform.transform.translation.x),
                                "y": float(transform.transform.translation.y),
                                "z": float(transform.transform.translation.z),
                            })

        except Exception as e:
            pass

    # reader不需要close，rosbag2_py会自动清理
    # reader.close()  # removed - not available in this version

    print(f"  读取完成: {msg_count} 条消息")

    return {
        "gt_positions": gt_positions,
        "dvl_velocities": dvl_velocities,
        "cmd_vel_commands": cmd_vel_commands,
        "setpoints": setpoints,
        "odom_filtered": odom_filtered,
        "sensor_status": sensor_status,
        "controller_debug": controller_debug,
        "first_ts": first_ts,
        "last_ts": last_ts,
        "msg_count": msg_count,
        "duration_s": (last_ts - first_ts) / 1e9 if first_ts and last_ts else 0,
    }


def compute_statistics(data):
    """计算统计指标"""
    stats = {}

    # Ground truth位移 (从tf)
    gt_pos = data.get("gt_positions", [])
    if len(gt_pos) >= 2:
        first = gt_pos[0]
        last = gt_pos[-1]
        dx = last["x"] - first["x"]
        dy = last["y"] - first["y"]
        dz = last["z"] - first["z"]
        total_distance = (dx**2 + dy**2 + dz**2) ** 0.5
        duration = last["ts"] - first["ts"]

        stats["gt_start"] = first
        stats["gt_end"] = last
        stats["gt_delta"] = {"dx": dx, "dy": dy, "dz": dz}
        stats["gt_total_distance_m"] = total_distance
        stats["gt_sample_count"] = len(gt_pos)
        stats["gt_duration_s"] = duration
        stats["gt_avg_speed_mps"] = total_distance / duration if duration > 0 else 0

    # 也可以从filtered odometry计算
    odom = data.get("odom_filtered", [])
    if len(odom) >= 2:
        first = odom[0]
        last = odom[-1]
        dx = last["x"] - first["x"]
        dy = last["y"] - first["y"]
        dz = last["z"] - first["z"]
        total_distance = (dx**2 + dy**2 + dz**2) ** 0.5
        duration = last["ts"] - first["ts"]

        stats["odom_start"] = first
        stats["odom_end"] = last
        stats["odom_delta"] = {"dx": dx, "dy": dy, "dz": dz}
        stats["odom_total_distance_m"] = total_distance
        stats["odom_sample_count"] = len(odom)
        stats["odom_duration_s"] = duration
        stats["odom_avg_speed_mps"] = total_distance / duration if duration > 0 else 0

    # DVL速度统计
    dvl = data.get("dvl_velocities", [])
    if dvl:
        vx_values = [v["vx"] for v in dvl]
        stats["dvl_vx_min"] = min(vx_values)
        stats["dvl_vx_max"] = max(vx_values)
        stats["dvl_vx_avg"] = sum(vx_values) / len(vx_values)
        stats["dvl_sample_count"] = len(dvl)

        # DVL积分位移
        integrated_x = 0.0
        for i in range(1, len(dvl)):
            dt = dvl[i]["ts"] - dvl[i-1]["ts"]
            if dt > 0 and dt < 1.0:
                integrated_x += dvl[i]["vx"] * dt
        stats["dvl_integrated_dx"] = integrated_x

    # cmd_vel统计
    cmd_vel = data.get("cmd_vel_commands", [])
    if cmd_vel:
        linear_x_vals = [c["linear_x"] for c in cmd_vel]
        stats["cmd_linear_x_min"] = min(linear_x_vals)
        stats["cmd_linear_x_max"] = max(linear_x_vals)
        stats["cmd_linear_x_avg"] = sum(linear_x_vals) / len(linear_x_vals)
        stats["cmd_sample_count"] = len(cmd_vel)

    # Setpoint统计
    setpoints = data.get("setpoints", [])
    if setpoints:
        speeds = [s["target_speed_mps"] for s in setpoints]
        stats["setpoint_speed_min"] = min(speeds)
        stats["setpoint_speed_max"] = max(speeds)
        stats["setpoint_speed_avg"] = sum(speeds) / len(speeds)
        stats["setpoint_sample_count"] = len(setpoints)

    # 总持续时间
    stats["total_duration_s"] = data.get("duration_s", 0)
    stats["total_messages"] = data.get("msg_count", 0)

    return stats


def print_stats(mcap_info, stats):
    """打印统计结果"""
    print(f"\n{'='*90}")
    print(f"实验: {mcap_info['parent']}")
    print(f"文件: {mcap_info['path']}")
    print(f"时间: {mcap_info['mtime_str']} | 大小: {mcap_info['size_mb']:.1f}MB")
    print(f"{'='*90}")

    print(f"  总持续时间: {stats.get('total_duration_s', 0):.2f}s")
    print(f"  总消息数: {stats.get('total_messages', 0)}")

    # TF ground truth
    if "gt_total_distance_m" in stats:
        d = stats["gt_total_distance_m"]
        flag = "⚠️ 异常!" if d > 100 else "✅ 正常"
        print(f"\n  ── TF Ground Truth ──")
        print(f"    起点: ({stats['gt_start']['x']:.2f}, {stats['gt_start']['y']:.2f}, {stats['gt_start']['z']:.2f})")
        print(f"    终点: ({stats['gt_end']['x']:.2f}, {stats['gt_end']['y']:.2f}, {stats['gt_end']['z']:.2f})")
        print(f"    位移: dx={stats['gt_delta']['dx']:.2f}m, dy={stats['gt_delta']['dy']:.2f}m, dz={stats['gt_delta']['dz']:.2f}m")
        print(f"    总距离: {d:.2f}m {flag}")
        print(f"    持续时间: {stats.get('gt_duration_s', 0):.2f}s")
        print(f"    平均速度: {stats.get('gt_avg_speed_mps', 0):.2f} m/s")
        print(f"    采样数: {stats['gt_sample_count']}")

    # Filtered odometry
    if "odom_total_distance_m" in stats:
        d = stats["odom_total_distance_m"]
        flag = "⚠️ 异常!" if d > 100 else "✅ 正常"
        print(f"\n  ── Filtered Odometry (EKF) ──")
        print(f"    起点: ({stats['odom_start']['x']:.2f}, {stats['odom_start']['y']:.2f}, {stats['odom_start']['z']:.2f})")
        print(f"    终点: ({stats['odom_end']['x']:.2f}, {stats['odom_end']['y']:.2f}, {stats['odom_end']['z']:.2f})")
        print(f"    位移: dx={stats['odom_delta']['dx']:.2f}m, dy={stats['odom_delta']['dy']:.2f}m, dz={stats['odom_delta']['dz']:.2f}m")
        print(f"    总距离: {d:.2f}m {flag}")
        print(f"    持续时间: {stats.get('odom_duration_s', 0):.2f}s")
        print(f"    平均速度: {stats.get('odom_avg_speed_mps', 0):.2f} m/s")
        print(f"    采样数: {stats['odom_sample_count']}")

    # DVL
    if "dvl_vx_avg" in stats:
        print(f"\n  ── DVL速度 ──")
        print(f"    VX范围: [{stats['dvl_vx_min']:.3f}, {stats['dvl_vx_max']:.3f}] m/s")
        print(f"    VX平均: {stats['dvl_vx_avg']:.3f} m/s")
        print(f"    积分位移: {stats.get('dvl_integrated_dx', 0):.2f}m")
        print(f"    采样数: {stats['dvl_sample_count']}")

    # cmd_vel
    if "cmd_linear_x_avg" in stats:
        print(f"\n  ── cmd_vel (控制命令) ──")
        print(f"    linear.x范围: [{stats['cmd_linear_x_min']:.2f}, {stats['cmd_linear_x_max']:.2f}]")
        print(f"    linear.x平均: {stats['cmd_linear_x_avg']:.2f}")
        print(f"    采样数: {stats['cmd_sample_count']}")

    # Setpoint
    if "setpoint_speed_avg" in stats:
        print(f"\n  ── Setpoint (目标) ──")
        print(f"    target_speed_mps范围: [{stats['setpoint_speed_min']:.2f}, {stats['setpoint_speed_max']:.2f}]")
        print(f"    target_speed_mps平均: {stats['setpoint_speed_avg']:.2f} m/s")
        print(f"    采样数: {stats['setpoint_sample_count']}")

    # 方向一致性检查
    if "gt_delta" in stats and "dvl_vx_avg" in stats:
        gt_dx = stats["gt_delta"]["dx"]
        dvl_vx = stats["dvl_vx_avg"]
        if (gt_dx > 0 and dvl_vx < 0) or (gt_dx < 0 and dvl_vx > 0):
            print(f"\n  ⚠️ 方向不一致! GT dx={gt_dx:.1f}m, DVL vx={dvl_vx:.3f}m/s (符号相反!)")
        else:
            print(f"\n  ✅ 方向一致: GT dx={gt_dx:.1f}m, DVL vx={dvl_vx:.3f}m/s")

    # 580m异常检测
    for source in ["gt_total_distance_m", "odom_total_distance_m"]:
        if source in stats:
            d = stats[source]
            if d > 100:
                duration = stats.get("total_duration_s", 0)
                print(f"\n  🔴 检测到异常位移! ({source}): {d:.1f}m in {duration:.1f}s")
                print(f"     平均速度: {d/duration:.2f} m/s")


def main():
    print("=" * 90)
    print("AUV mcap实验数据分析工具 V3 - ROS2 API")
    print("=" * 90)

    mcaps = find_all_mcaps(EXPERIMENTS_DIR)
    print(f"找到 {len(mcaps)} 个mcap文件\n")

    if not mcaps:
        print("未找到mcap文件")
        return

    # 分析最近5个文件
    for i in range(min(5, len(mcaps))):
        mcap_info = mcaps[i]
        mcap_path = mcap_info["path"]
        
        print(f"\n{'='*90}")
        print(f"分析 #{i+1}: {mcap_info['parent']}")
        print(f"{'='*90}")
        
        # 获取bag info
        bag_info = get_bag_info(mcap_path)
        if bag_info:
            print(f"  持续时间: {bag_info.get('Duration', 'N/A')}")
            print(f"  消息数: {bag_info.get('Messages', 'N/A')}")
        
        # 读取数据
        try:
            data = read_mcap_ros2(mcap_path, max_duration_s=120)
            if data:
                stats = compute_statistics(data)
                print_stats(mcap_info, stats)
        except Exception as e:
            print(f"  [ERROR] 分析失败: {e}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    main()

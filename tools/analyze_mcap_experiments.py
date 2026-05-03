#!/usr/bin/env python3
"""
AUV mcap实验数据分析工具 - 直接使用mcap SDK

读取mcap文件中的ground_truth、DVL、cmd_vel等话题数据，分析AUV运动异常。
"""

import sys
import json
import struct
from pathlib import Path
from datetime import datetime

try:
    from mcap.reader import make_reader
    HAS_MCAP = True
except ImportError:
    print("[ERROR] mcap package not installed")
    sys.exit(1)

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


def deserialize_json(data):
    """尝试将字节数据反序列化为JSON"""
    try:
        return json.loads(data.decode('utf-8'))
    except:
        return None


def deserialize_custom_json(data):
    """尝试多种编码方式解析JSON"""
    for encoding in ['utf-8', 'utf-8-sig', 'ascii']:
        try:
            return json.loads(data.decode(encoding))
        except:
            continue
    return None


def read_mcap_topics(mcap_path):
    """读取mcap文件中所有话题名称"""
    topics = set()
    with open(mcap_path, "rb") as f:
        reader = make_reader(f)
        for schema, channel, message in reader.iter_messages():
            topics.add(channel.topic)
    return sorted(topics)


def analyze_mcap(mcap_path, max_messages_per_topic=500):
    """分析单个mcap文件，提取关键指标"""
    results = {
        "ground_truth": {"positions": [], "count": 0},
        "dvl": {"velocities": [], "count": 0},
        "cmd_vel": {"commands": [], "count": 0},
        "setpoint": {"setpoints": [], "count": 0},
        "odometry": {"odom": [], "count": 0},
        "zenoh_cmd": {"commands": [], "count": 0},
    }

    topic_counts = {}
    
    try:
        with open(mcap_path, "rb") as f:
            reader = make_reader(f)
            
            for schema, channel, message in reader.iter_messages():
                topic = channel.topic
                
                if topic not in topic_counts:
                    topic_counts[topic] = 0
                topic_counts[topic] += 1
                
                # 限制每个话题的消息数
                if topic_counts[topic] > max_messages_per_topic:
                    continue

                data = deserialize_custom_json(message.data)
                if data is None:
                    continue

                ts = message.log_time / 1e9  # 纳秒转秒

                # 提取ground truth (rt/auv/sensors/ground_truth)
                if "ground_truth" in topic.lower():
                    pos = data.get("position_ned")
                    if pos and isinstance(pos, list) and len(pos) >= 3:
                        results["ground_truth"]["positions"].append({
                            "ts": ts,
                            "x": pos[0],
                            "y": pos[1],
                            "z": pos[2],
                        })
                        results["ground_truth"]["count"] += 1

                # 提取DVL速度 (rt/auv/sensors/dvl)
                elif "dvl" in topic.lower():
                    vel = data.get("vel_ned")
                    if vel and isinstance(vel, list) and len(vel) >= 3:
                        results["dvl"]["velocities"].append({
                            "ts": ts,
                            "vx": vel[0],
                            "vy": vel[1],
                            "vz": vel[2],
                        })
                        results["dvl"]["count"] += 1

                # 提取控制命令 (rt/auv/command)
                elif "command" in topic.lower() and ("zenoh" in topic.lower() or "rt/auv" in topic):
                    cmd = data.get("control_command_5")
                    if cmd and isinstance(cmd, list) and len(cmd) >= 5:
                        results["zenoh_cmd"]["commands"].append({
                            "ts": ts,
                            "right_fin": cmd[0],
                            "top_fin": cmd[1],
                            "left_fin": cmd[2],
                            "bottom_fin": cmd[3],
                            "thrust_percent": cmd[4],
                        })
                        results["zenoh_cmd"]["count"] += 1

                # 提取ROS2 cmd_vel
                elif "cmd_vel" in topic.lower():
                    twist = data.get("twist", {})
                    linear = twist.get("linear", {})
                    angular = twist.get("angular", {})
                    results["cmd_vel"]["commands"].append({
                        "ts": ts,
                        "linear_x": linear.get("x", 0),
                        "linear_y": linear.get("y", 0),
                        "linear_z": linear.get("z", 0),
                        "angular_x": angular.get("x", 0),
                        "angular_y": angular.get("y", 0),
                        "angular_z": angular.get("z", 0),
                    })
                    results["cmd_vel"]["count"] += 1

                # 提取Setpoint
                elif "setpoint" in topic.lower():
                    results["setpoint"]["setpoints"].append({
                        "ts": ts,
                        "target_speed_mps": data.get("target_speed_mps"),
                        "target_depth_m": data.get("target_depth_m"),
                        "target_heading_rad": data.get("target_heading_rad"),
                    })
                    results["setpoint"]["count"] += 1

                # 提取Odometry
                elif "odometry" in topic.lower() or "odom" in topic.lower():
                    pose = data.get("pose", {})
                    position = pose.get("position", {})
                    results["odometry"]["odom"].append({
                        "ts": ts,
                        "x": position.get("x"),
                        "y": position.get("y"),
                        "z": position.get("z"),
                    })
                    results["odometry"]["count"] += 1

    except Exception as e:
        print(f"    [ERROR] 读取失败: {e}")
        return None, {}

    return results, topic_counts


def compute_statistics(results):
    """计算统计指标"""
    stats = {}

    # Ground truth位移统计
    gt_pos = results.get("ground_truth", {}).get("positions", [])
    if len(gt_pos) >= 2:
        first = gt_pos[0]
        last = gt_pos[-1]
        dx = last["x"] - first["x"]
        dy = last["y"] - first["y"]
        dz = last["z"] - first["z"]
        total_distance = (dx**2 + dy**2 + dz**2) ** 0.5

        stats["gt_start"] = first
        stats["gt_end"] = last
        stats["gt_delta"] = {"dx": dx, "dy": dy, "dz": dz}
        stats["gt_total_distance_m"] = total_distance
        stats["gt_sample_count"] = len(gt_pos)

        # 计算平均速度
        duration = last["ts"] - first["ts"]
        if duration > 0:
            stats["avg_speed_mps"] = total_distance / duration
            stats["duration_s"] = duration
        else:
            stats["avg_speed_mps"] = None
            stats["duration_s"] = 0

    # DVL速度统计
    dvl_vel = results.get("dvl", {}).get("velocities", [])
    if dvl_vel:
        vx_values = [v["vx"] for v in dvl_vel if v["vx"] is not None]
        if vx_values:
            stats["dvl_vx_min"] = min(vx_values)
            stats["dvl_vx_max"] = max(vx_values)
            stats["dvl_vx_avg"] = sum(vx_values) / len(vx_values)
            stats["dvl_sample_count"] = len(dvl_vel)

            # DVL积分位移（使用实际时间间隔）
            integrated_x = 0.0
            for i in range(1, len(dvl_vel)):
                dt = dvl_vel[i]["ts"] - dvl_vel[i-1]["ts"]
                if dt > 0 and dt < 1.0:  # 过滤异常dt
                    integrated_x += dvl_vel[i]["vx"] * dt
            stats["dvl_integrated_dx"] = integrated_x

    # Zenoh控制命令统计
    zenoh_cmd = results.get("zenoh_cmd", {}).get("commands", [])
    if zenoh_cmd:
        thrust_vals = [c["thrust_percent"] for c in zenoh_cmd]
        stats["zenoh_thrust_avg"] = sum(thrust_vals) / len(thrust_vals)
        stats["zenoh_thrust_max"] = max(thrust_vals)
        stats["zenoh_thrust_min"] = min(thrust_vals)
        stats["zenoh_cmd_count"] = len(zenoh_cmd)

    # cmd_vel统计
    cmd_vel = results.get("cmd_vel", {}).get("commands", [])
    if cmd_vel:
        linear_x_vals = [c["linear_x"] for c in cmd_vel]
        stats["cmd_linear_x_avg"] = sum(linear_x_vals) / len(linear_x_vals)
        stats["cmd_linear_x_max"] = max(linear_x_vals)
        stats["cmd_linear_x_min"] = min(linear_x_vals)
        stats["cmd_sample_count"] = len(cmd_vel)

    # Setpoint统计
    setpoints = results.get("setpoint", {}).get("setpoints", [])
    if setpoints:
        speeds = [s["target_speed_mps"] for s in setpoints if s["target_speed_mps"] is not None]
        if speeds:
            stats["setpoint_speed_avg"] = sum(speeds) / len(speeds)
            stats["setpoint_sample_count"] = len(setpoints)

    return stats


def print_stats(mcap_info, stats, topic_counts, index=0):
    """格式化打印统计结果"""
    print(f"\n{'='*90}")
    print(f"#{index+1}: {mcap_info['path']}")
    print(f"    时间: {mcap_info['mtime_str']} | 大小: {mcap_info['size_mb']:.1f}MB | 实验: {mcap_info['parent']}")
    print(f"{'='*90}")

    # 打印找到的话题
    if topic_counts:
        gt_topics = [t for t in topic_counts.keys() if "ground" in t.lower() or "truth" in t.lower()]
        dvl_topics = [t for t in topic_counts.keys() if "dvl" in t.lower()]
        cmd_topics = [t for t in topic_counts.keys() if "command" in t.lower() or "cmd" in t.lower()]
        setpoint_topics = [t for t in topic_counts.keys() if "setpoint" in t.lower()]
        
        print(f"    关键话题数: GT={len(gt_topics)}, DVL={len(dvl_topics)}, CMD={len(cmd_topics)}, Setpoint={len(setpoint_topics)}")
        if gt_topics: print(f"      GT topics: {gt_topics[:3]}")
        if dvl_topics: print(f"      DVL topics: {dvl_topics[:3]}")
        if cmd_topics: print(f"      CMD topics: {cmd_topics[:3]}")

    if not stats:
        print("    [ERROR] 无统计数据")
        return

    duration = stats.get("duration_s", 0)
    print(f"    持续时间: {duration:.1f}s")

    # Ground truth
    if "gt_total_distance_m" in stats:
        d = stats["gt_total_distance_m"]
        flag = "⚠️ 异常!" if d > 100 else "✅ 正常"
        print(f"    ── Ground Truth ──")
        print(f"      起点: ({stats['gt_start']['x']:.2f}, {stats['gt_start']['y']:.2f}, {stats['gt_start']['z']:.2f})")
        print(f"      终点: ({stats['gt_end']['x']:.2f}, {stats['gt_end']['y']:.2f}, {stats['gt_end']['z']:.2f})")
        print(f"      位移: dx={stats['gt_delta']['dx']:.2f}m, dy={stats['gt_delta']['dy']:.2f}m, dz={stats['gt_delta']['dz']:.2f}m")
        print(f"      总距离: {d:.1f}m {flag}")
        print(f"      平均速度: {stats.get('avg_speed_mps', 0):.2f} m/s")
        print(f"      采样数: {stats['gt_sample_count']}")

    # DVL
    if "dvl_vx_avg" in stats:
        print(f"    ── DVL速度 ──")
        print(f"      VX范围: [{stats['dvl_vx_min']:.3f}, {stats['dvl_vx_max']:.3f}] m/s")
        print(f"      VX平均: {stats['dvl_vx_avg']:.3f} m/s")
        print(f"      积分位移: {stats.get('dvl_integrated_dx', 0):.1f}m")
        print(f"      采样数: {stats['dvl_sample_count']}")

    # Zenoh控制命令
    if "zenoh_thrust_avg" in stats:
        print(f"    ── Zenoh控制命令 ──")
        print(f"      thrust_percent范围: [{stats['zenoh_thrust_min']:.2f}, {stats['zenoh_thrust_max']:.2f}]")
        print(f"      thrust_percent平均: {stats['zenoh_thrust_avg']:.2f}")
        print(f"      采样数: {stats['zenoh_cmd_count']}")

    # cmd_vel
    if "cmd_linear_x_avg" in stats:
        print(f"    ── ROS2 cmd_vel ──")
        print(f"      linear.x范围: [{stats['cmd_linear_x_min']:.2f}, {stats['cmd_linear_x_max']:.2f}]")
        print(f"      linear.x平均: {stats['cmd_linear_x_avg']:.2f}")
        print(f"      采样数: {stats['cmd_sample_count']}")

    # Setpoint
    if "setpoint_speed_avg" in stats:
        print(f"    ── Setpoint ──")
        print(f"      target_speed_mps平均: {stats['setpoint_speed_avg']:.2f} m/s")
        print(f"      采样数: {stats['setpoint_sample_count']}")

    # 方向一致性检查
    if "gt_delta" in stats and "dvl_vx_avg" in stats:
        gt_dx = stats["gt_delta"]["dx"]
        dvl_vx = stats["dvl_vx_avg"]
        if (gt_dx > 0 and dvl_vx < 0) or (gt_dx < 0 and dvl_vx > 0):
            print(f"    ⚠️ 方向不一致! GT dx={gt_dx:.1f}m, DVL vx={dvl_vx:.3f}m/s (符号相反!)")

    # 580m异常检测
    if "gt_total_distance_m" in stats:
        d = stats["gt_total_distance_m"]
        if d > 100:
            print(f"\n    🔴 检测到异常位移! {d:.1f}m in {duration:.1f}s")
            print(f"       如果这是60s实验，平均速度={stats.get('avg_speed_mps', 0):.2f} m/s")


def main():
    print("=" * 90)
    print("AUV mcap实验数据分析工具 (直接mcap SDK)")
    print("=" * 90)

    # 1. 扫描所有mcap文件
    print(f"\n正在扫描 {EXPERIMENTS_DIR} ...")
    mcaps = find_all_mcaps(EXPERIMENTS_DIR)
    print(f"找到 {len(mcaps)} 个mcap文件\n")

    if not mcaps:
        print("未找到mcap文件，退出")
        return

    # 2. 打印文件列表
    print("文件列表 (按修改时间倒序):")
    for i, m in enumerate(mcaps):
        print(f"  #{i+1}: {m['mtime_str']} | {m['size_mb']:>8.1f}MB | {m['parent']} | {m['path']}")

    # 3. 分析所有文件
    analyze_count = min(len(mcaps), 8)
    print(f"\n\n分析最近 {analyze_count} 个实验...")

    for i in range(analyze_count):
        mcap_info = mcaps[i]
        mcap_path = mcap_info["path"]

        print(f"\n{'='*90}")
        print(f"分析 #{i+1}: {mcap_path}")
        print(f"{'='*90}")

        # 先读取话题列表
        try:
            topics = read_mcap_topics(mcap_path)
            print(f"  找到 {len(topics)} 个话题:")
            for t in topics[:30]:
                print(f"    - {t}")
            if len(topics) > 30:
                print(f"    ... 还有{len(topics)-30}个话题")
        except Exception as e:
            print(f"  [ERROR] 读取话题失败: {e}")
            continue

        # 分析关键指标
        results, topic_counts = analyze_mcap(mcap_path)
        if results:
            stats = compute_statistics(results)
            print_stats(mcap_info, stats, topic_counts, i)

    # 4. 总结
    print(f"\n\n{'='*90}")
    print("分析完成")
    print(f"{'='*90}")


if __name__ == "__main__":
    main()

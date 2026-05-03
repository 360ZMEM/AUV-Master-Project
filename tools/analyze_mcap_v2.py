#!/usr/bin/env python3
"""
AUV mcap实验数据分析工具 V2 - 支持ROS2 CDR格式

这些mcap文件是由ros2 bag录制的，使用ROS2 CDR序列化格式，不是JSON。
需要检查schema并使用正确的反序列化方法。
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


def inspect_schemas(mcap_path):
    """检查mcap文件中的schema信息"""
    schemas = {}
    channels = {}
    
    try:
        with open(mcap_path, "rb") as f:
            reader = make_reader(f)
            summary = reader.get_summary()
            
            if summary:
                # 获取schema信息
                for schema_id, schema in summary.schemas.items():
                    schemas[schema_id] = {
                        "name": schema.name,
                        "encoding": schema.encoding,
                        "data_len": len(schema.data) if schema.data else 0,
                    }
                
                # 获取channel信息
                for chan_id, channel in summary.channels.items():
                    schema_name = ""
                    if channel.schema_id in schemas:
                        schema_name = schemas[channel.schema_id]["name"]
                    
                    channels[channel.topic] = {
                        "id": chan_id,
                        "message_encoding": channel.message_encoding,
                        "schema_id": channel.schema_id,
                        "schema_name": schema_name,
                        "metadata": dict(channel.metadata) if channel.metadata else {},
                    }
    except Exception as e:
        print(f"    [ERROR] 读取schema失败: {e}")
        return {}, {}
    
    return schemas, channels


def try_parse_json_from_cdr(data):
    """尝试从CDR数据中提取JSON（某些桥接可能使用JSON编码）"""
    # 跳过CDR header (4 bytes: endianness + version + options + reserved)
    if len(data) < 4:
        return None
    
    # 检查是否是纯JSON（某些zenoh_json桥接可能直接发JSON）
    try:
        return json.loads(data.decode('utf-8'))
    except:
        pass
    
    # 尝试跳过CDR header
    try:
        return json.loads(data[4:].decode('utf-8'))
    except:
        pass
    
    return None


def analyze_with_rosbag2(mcap_path):
    """使用ros2 bag命令提取信息"""
    import subprocess
    
    result = {}
    
    # 获取话题信息
    try:
        proc = subprocess.run(
            ["ros2", "bag", "info", mcap_path],
            capture_output=True, text=True, timeout=30
        )
        result["bag_info"] = proc.stdout
    except Exception as e:
        result["bag_info"] = f"[ERROR] {e}"
    
    return result


def main():
    print("=" * 90)
    print("AUV mcap实验数据分析工具 V2 - Schema检查")
    print("=" * 90)

    mcaps = find_all_mcaps(EXPERIMENTS_DIR)
    print(f"找到 {len(mcaps)} 个mcap文件\n")

    # 分析最近的3个文件
    for i in range(min(3, len(mcaps))):
        mcap_info = mcaps[i]
        mcap_path = mcap_info["path"]
        
        print(f"\n{'='*90}")
        print(f"分析 #{i+1}: {mcap_path}")
        print(f"    时间: {mcap_info['mtime_str']} | 大小: {mcap_info['size_mb']:.1f}MB")
        print(f"{'='*90}")
        
        # 1. 检查schema
        schemas, channels = inspect_schemas(mcap_path)
        
        if schemas:
            print(f"\n  Schema信息 ({len(schemas)}个):")
            for sid, sinfo in list(schemas.items())[:10]:
                print(f"    ID={sid}: name={sinfo['name']}, encoding={sinfo['encoding']}, data_len={sinfo['data_len']}")
        
        if channels:
            print(f"\n  话题信息 ({len(channels)}个):")
            # 关键话题
            key_topics = ['/auv/sensors/dvl', '/cmd_vel', '/auv/control/setpoint', 
                         '/auv/state/filtered', '/auv/sensors/status', '/auv/visual/truth_marker']
            for topic in key_topics:
                if topic in channels:
                    ch = channels[topic]
                    print(f"    {topic}:")
                    print(f"      message_encoding={ch['message_encoding']}")
                    print(f"      schema_name={ch['schema_name']}")
                    print(f"      schema_id={ch['schema_id']}")
        
        # 2. 尝试读取少量消息
        print(f"\n  尝试读取消息样本...")
        try:
            with open(mcap_path, "rb") as f:
                reader = make_reader(f)
                
                msg_count = 0
                sample_count = 0
                for schema, channel, message in reader.iter_messages():
                    msg_count += 1
                    
                    if msg_count > 1000 and sample_count < 5:
                        # 对于关键话题，尝试解析前几条消息
                        if channel.topic in ['/auv/sensors/dvl', '/cmd_vel', '/auv/control/setpoint',
                                            '/auv/state/filtered', '/auv/sensors/status']:
                            sample_count += 1
                            print(f"\n    Topic: {channel.topic}")
                            print(f"      Schema: {schema.name if schema else 'None'}")
                            print(f"      Encoding: {channel.message_encoding}")
                            print(f"      Data length: {len(message.data)} bytes")
                            print(f"      Data (hex, first 64 bytes): {message.data[:64].hex()}")
                            
                            # 尝试JSON解析
                            json_data = try_parse_json_from_cdr(message.data)
                            if json_data:
                                print(f"      JSON: {json.dumps(json_data, indent=2)[:300]}")
                            else:
                                # 尝试打印为字符串（前100字符）
                                try:
                                    text = message.data.decode('utf-8', errors='replace')[:100]
                                    print(f"      Text preview: {text}")
                                except:
                                    pass
                    
                    if msg_count > 2000:
                        break
                
                print(f"\n    总消息数读取: {msg_count}")
                
        except Exception as e:
            print(f"    [ERROR] 读取消息失败: {e}")


if __name__ == "__main__":
    main()

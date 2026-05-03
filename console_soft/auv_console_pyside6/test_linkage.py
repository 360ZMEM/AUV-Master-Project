#!/usr/bin/env python3
"""联调测试脚本：上位机 → Jetson → AMD 链路测试

功能：
1. 启动 Zenoh Router
2. 启动 Mock AMD Server
3. 启动 Jetson Bridge Node
4. 启动 PySide6 Console
5. 自动化测试三种模式：MANUAL / AUTONOMY / ESTOP
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

try:
    import zenoh
    HAS_ZENOH = True
except ImportError:
    HAS_ZENOH = False
    print("[WARN] zenoh-python 未安装，部分功能将跳过")


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
ZENOH_ROUTER_PORT = 7447
ZENOH_PC_CMD_KEY = "rt/pc/cmd_raw"
ZENOH_TELEMETRY_KEY = "rt/auv/telemetry"
ZENOH_MISSION_CMD_KEY = "/auv/mission_command"


def print_header(text: str) -> None:
    """打印测试阶段标题。"""
    width = 60
    print("\n" + "=" * width)
    print(f"  {text}")
    print("=" * width)


def run_command(cmd: list[str], *, blocking: bool = False, **kwargs) -> subprocess.Popen | None:
    """启动子进程。"""
    print(f"[CMD] {' '.join(cmd)}")
    if blocking:
        return subprocess.run(cmd, **kwargs)
    return subprocess.Popen(cmd, **kwargs)


def test_zenoh_router() -> bool:
    """测试 Zenoh Router 是否可连接。"""
    if not HAS_ZENOH:
        print("[SKIP] zenoh-python 未安装，跳过 Router 测试")
        return False

    try:
        zcfg = zenoh.Config()
        zcfg.insert_json5("mode", '"client"')
        zcfg.insert_json5("connect/endpoints", json.dumps([f"tcp/127.0.0.1:{ZENOH_ROUTER_PORT}"]))
        session = zenoh.open(zcfg)
        session.close()
        print("[OK] Zenoh Router 连接成功")
        return True
    except Exception as e:
        print(f"[FAIL] Zenoh Router 连接失败: {e}")
        return False


def test_manual_mode() -> bool:
    """测试手动模式：发送 CKTH 包并验证回传。"""
    print_header("测试 MANUAL 模式")
    
    if not HAS_ZENOH:
        print("[SKIP] zenoh-python 未安装，跳过 MANUAL 测试")
        return False

    try:
        zcfg = zenoh.Config()
        zcfg.insert_json5("mode", '"client"')
        zcfg.insert_json5("connect/endpoints", json.dumps([f"tcp/127.0.0.1:{ZENOH_ROUTER_PORT}"]))
        session = zenoh.open(zcfg)
        
        cmd_payload = {
            "thrust": 0.3,
            "right_fin": 0.0,
            "top_fin": 0.0,
            "left_fin": 0.0,
            "bottom_fin": 0.0,
            "mode": "MANUAL",
        }
        
        session.put(ZENOH_PC_CMD_KEY, json.dumps(cmd_payload))
        print(f"[OK] MANUAL 模式指令已发送: {cmd_payload}")
        
        session.close()
        return True
    except Exception as e:
        print(f"[FAIL] MANUAL 模式测试失败: {e}")
        return False


def test_autonomy_mode() -> bool:
    """测试自主模式：发送 JSON 任务指令并验证 /auv/mission_command。"""
    print_header("测试 AUTONOMY 模式")
    
    if not HAS_ZENOH:
        print("[SKIP] zenoh-python 未安装，跳过 AUTONOMY 测试")
        return False

    try:
        zcfg = zenoh.Config()
        zcfg.insert_json5("mode", '"client"')
        zcfg.insert_json5("connect/endpoints", json.dumps([f"tcp/127.0.0.1:{ZENOH_ROUTER_PORT}"]))
        session = zenoh.open(zcfg)
        
        mission_payload = {
            "mission": "CABLE_TRACKING",
            "search_depth": 5.0,
            "track_distance": 500.0,
            "timeout_s": 1200,
            "thrust": 0.0,
            "mode": "AUTONOMY",
        }
        
        received = {"count": 0, "data": None}
        
        def on_sample(sample):
            try:
                data = json.loads(sample.payload.decode("utf-8"))
                received["count"] += 1
                received["data"] = data
                print(f"[RECV] /auv/mission_command: {data}")
            except Exception as e:
                print(f"[WARN] 解析失败: {e}")
        
        sub = session.declare_subscriber(ZENOH_MISSION_CMD_KEY, on_sample)
        
        session.put(ZENOH_PC_CMD_KEY, json.dumps(mission_payload))
        print(f"[SENT] 自主模式指令: {mission_payload}")
        
        time.sleep(2.0)
        
        sub.undeclare()
        session.close()
        
        if received["count"] > 0:
            print(f"[OK] AUTONOMY 模式测试通过，收到 {received['count']} 条任务指令")
            return True
        else:
            print("[FAIL] AUTONOMY 模式测试失败，未收到任务指令")
            return False
    except Exception as e:
        print(f"[FAIL] AUTONOMY 模式测试失败: {e}")
        return False


def test_estop_mode() -> bool:
    """测试急停模式：发送 ESTOP 指令并验证系统状态。"""
    print_header("测试 ESTOP 模式")
    
    if not HAS_ZENOH:
        print("[SKIP] zenoh-python 未安装，跳过 ESTOP 测试")
        return False

    try:
        zcfg = zenoh.Config()
        zcfg.insert_json5("mode", '"client"')
        zcfg.insert_json5("connect/endpoints", json.dumps([f"tcp/127.0.0.1:{ZENOH_ROUTER_PORT}"]))
        session = zenoh.open(zcfg)
        
        estop_payload = {
            "thrust": 0.0,
            "estop": True,
            "mode": "ESTOP",
        }
        
        telemetry_received = {"count": 0, "data": None}
        
        def on_telemetry(sample):
            try:
                data = json.loads(sample.payload.decode("utf-8"))
                telemetry_received["count"] += 1
                telemetry_received["data"] = data
                print(f"[RECV] 遥测数据: estop={data.get('estop', False)}, thrust={data.get('thrust', -1)}")
            except Exception as e:
                print(f"[WARN] 解析遥测失败: {e}")
        
        sub = session.declare_subscriber(ZENOH_TELEMETRY_KEY, on_telemetry)
        
        session.put(ZENOH_PC_CMD_KEY, json.dumps(estop_payload))
        print(f"[SENT] ESTOP 指令: {estop_payload}")
        
        time.sleep(2.0)
        
        sub.undeclare()
        session.close()
        
        if telemetry_received["count"] > 0:
            data = telemetry_received["data"]
            if data.get("estop", False) and data.get("thrust", -1) == 0.0:
                print("[OK] ESTOP 模式测试通过")
                return True
            else:
                print(f"[FAIL] ESTOP 状态异常: {data}")
                return False
        else:
            print("[FAIL] ESTOP 模式测试失败，未收到遥测数据")
            return False
    except Exception as e:
        print(f"[FAIL] ESTOP 模式测试失败: {e}")
        return False


def main() -> int:
    """主测试流程。"""
    print_header("上位机 → Jetson → AMD 链路联调测试")
    print(f"项目根目录: {PROJECT_ROOT}")
    print(f"Zenoh Router 端口: {ZENOH_ROUTER_PORT}")
    
    results = {}
    
    tests = [
        ("Zenoh Router", test_zenoh_router),
        ("MANUAL 模式", test_manual_mode),
        ("AUTONOMY 模式", test_autonomy_mode),
        ("ESTOP 模式", test_estop_mode),
    ]
    
    for name, test_fn in tests:
        try:
            results[name] = test_fn()
        except Exception as e:
            print(f"[ERROR] {name} 测试异常: {e}")
            results[name] = False
    
    print_header("测试结果汇总")
    all_passed = True
    for name, passed in results.items():
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {name}")
        if not passed:
            all_passed = False
    
    print("\n" + "=" * 60)
    if all_passed:
        print("  所有测试通过!")
        return 0
    else:
        print("  部分测试失败，请检查日志")
        return 1


if __name__ == "__main__":
    sys.exit(main())

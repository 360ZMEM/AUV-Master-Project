#!/usr/bin/env python3
"""single_setpoint_driver — S4 配套：以恒定 setpoint 驱动决策栈，绕过行为树。

发布 auv_interfaces/msg/Setpoint 到 /auv/manual/setpoint，
该 topic 已在 decision_node._on_manual_setpoint 中接管为高优先级注入。

用法:
    python tools/single_setpoint_driver.py --duration 60 --csv s4.csv \\
        [depth=2.0] [heading=90] [speed=0.5]

参数（位置式 key=value）：
    depth   : 目标深度 (m), 默认 1.0
    heading : 目标航向 (deg), 默认 0.0
    speed   : 目标速度 (m/s), 默认 0.3

设计为可优雅退化：无 rclpy/auv_interfaces 时打印 SKIP 并 exit 0（dry-run 兼容）。
"""

from __future__ import annotations

import argparse
import csv
import math
import sys
import time
from pathlib import Path

try:
    import rclpy
    from rclpy.node import Node
    from auv_interfaces.msg import Setpoint
    HAVE_ROS = True
except Exception as e:  # noqa: BLE001
    HAVE_ROS = False
    _ROS_IMPORT_ERROR = str(e)


def parse_kv(extras: list[str]) -> dict:
    out = {}
    for kv in extras:
        if not kv or "=" not in kv:
            continue
        k, v = kv.split("=", 1)
        try:
            out[k.strip()] = float(v)
        except ValueError:
            pass
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--duration", type=float, default=60.0)
    ap.add_argument("--csv", required=True)
    ap.add_argument("--rate-hz", type=float, default=10.0)
    ap.add_argument("--topic", default="/auv/manual/setpoint")
    ap.add_argument("kv", nargs="*", help="depth=2.0 heading=90 speed=0.5")
    args = ap.parse_args()

    kv = parse_kv(args.kv)
    target_depth_m = float(kv.get("depth", 1.0))
    target_heading_deg = float(kv.get("heading", 0.0))
    target_speed_mps = float(kv.get("speed", 0.3))

    if not HAVE_ROS:
        print(f"[single_setpoint] rclpy/auv_interfaces missing "
              f"({_ROS_IMPORT_ERROR}); SKIP")
        return 0

    rclpy.init()
    node = Node("single_setpoint_driver")
    pub = node.create_publisher(Setpoint, args.topic, 10)

    csv_path = Path(args.csv)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    fp = csv_path.open("w", newline="")
    w = csv.DictWriter(fp, fieldnames=["t", "depth_m", "heading_deg", "speed_mps"])
    w.writeheader()

    period = 1.0 / max(args.rate_hz, 1.0)
    deadline = time.time() + args.duration
    print(f"[single_setpoint] publishing depth={target_depth_m} heading={target_heading_deg} "
          f"speed={target_speed_mps} on '{args.topic}' for {args.duration}s @ {args.rate_hz}Hz")

    try:
        while time.time() < deadline and rclpy.ok():
            now = time.time()
            msg = Setpoint()
            msg.header.frame_id = "single_setpoint_driver"
            msg.mode = "MANUAL_HOLD"
            msg.bridge_backend = "protocol_udp"
            msg.control_mode_byte = 0xEF
            msg.target_depth_m = target_depth_m
            msg.target_heading_rad = math.radians(target_heading_deg)
            msg.target_speed_mps = target_speed_mps
            msg.high_priority = True
            msg.note = "S4 single-loop closed-loop probe"
            pub.publish(msg)
            w.writerow({"t": now,
                        "depth_m": target_depth_m,
                        "heading_deg": target_heading_deg,
                        "speed_mps": target_speed_mps})
            rclpy.spin_once(node, timeout_sec=0.0)
            time.sleep(period)
    finally:
        fp.close()
        node.destroy_node()
        rclpy.shutdown()

    print("[single_setpoint] done. Inspect /auv/control/setpoint vs /auv/raw_state for "
          "overshoot / steady-state error in the bag.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""shadow_diff_recorder — S3 影子导航配套：记录 |Jetson_cmd - Human_cmd| 跟踪误差。

用法:
    python tools/shadow_diff_recorder.py --csv shadow_diff.csv --duration 60 \\
        [--shadow-cmd-topic /auv/bridge/shadow_cmd] \\
        [--shadow-tlm-topic /auv/bridge/shadow_telemetry]

订阅:
    - /auv/bridge/shadow_cmd        (Jetson 计算的虚拟下行命令; std_msgs/String JSON)
    - /auv/bridge/shadow_telemetry  (上位机/AMD 实际状态回放; std_msgs/String JSON)

输出:
    - 每秒 stdout 打一行 (t, jetson_thrust, human_thrust, dthrust, ...)
    - 全程落 CSV
    - 退出时打印每个字段 RMSE 与 阈值判定（heading deg<10、depth m<0.5）

设计为可优雅退化：无 rclpy 时仅打印 SKIP 并 exit 0（dry-run 兼容）。
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
import time
from pathlib import Path

try:
    import rclpy
    from rclpy.node import Node
    from std_msgs.msg import String
    HAVE_ROS = True
except Exception as e:  # noqa: BLE001
    HAVE_ROS = False
    _ROS_IMPORT_ERROR = str(e)


def _parse_json_payload(raw: str) -> dict | None:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def _safe_get(obj, *keys, default=None):
    cur = obj
    for k in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(k)
        if cur is None:
            return default
    return cur


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--csv", required=True)
    ap.add_argument("--duration", type=float, default=60.0)
    ap.add_argument("--shadow-cmd-topic", default="/auv/bridge/shadow_cmd")
    ap.add_argument("--shadow-tlm-topic", default="/auv/bridge/shadow_telemetry")
    args = ap.parse_args()

    if not HAVE_ROS:
        print(f"[shadow_diff] rclpy not available ({_ROS_IMPORT_ERROR}); "
              "skipping in dry-mode")
        return 0

    rclpy.init()
    node = Node("shadow_diff_recorder")

    state = {"last_cmd": None, "last_tlm": None}

    def on_cmd(msg: String):
        state["last_cmd"] = _parse_json_payload(msg.data)

    def on_tlm(msg: String):
        state["last_tlm"] = _parse_json_payload(msg.data)

    node.create_subscription(String, args.shadow_cmd_topic, on_cmd, 10)
    node.create_subscription(String, args.shadow_tlm_topic, on_tlm, 10)

    csv_path = Path(args.csv)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["t", "jet_heading", "jet_depth", "hum_heading", "hum_depth",
              "dheading_deg", "ddepth_m"]
    fp = csv_path.open("w", newline="")
    w = csv.DictWriter(fp, fieldnames=fields)
    w.writeheader()

    sums = {"sq_dh": 0.0, "sq_dd": 0.0, "n": 0}
    deadline = time.time() + args.duration
    print(f"[shadow_diff] subscribing cmd='{args.shadow_cmd_topic}' "
          f"tlm='{args.shadow_tlm_topic}' for {args.duration}s")

    try:
        while time.time() < deadline:
            rclpy.spin_once(node, timeout_sec=0.5)
            cmd = state["last_cmd"] or {}
            tlm = state["last_tlm"] or {}
            jet_h = _safe_get(cmd, "set_course") or _safe_get(cmd, "target_heading_deg") or 0.0
            jet_d = _safe_get(cmd, "set_depth") or _safe_get(cmd, "target_depth_m") or 0.0
            hum_h = _safe_get(tlm, "Real_Pose", "heading") or _safe_get(tlm, "heading_deg") or 0.0
            hum_d = _safe_get(tlm, "Real_Pose", "depth") or _safe_get(tlm, "depth_m") or 0.0

            dh = float(jet_h) - float(hum_h)
            dh = (dh + 180.0) % 360.0 - 180.0  # wrap to [-180, 180)
            dd = float(jet_d) - float(hum_d)

            row = {
                "t": time.time(),
                "jet_heading": jet_h, "jet_depth": jet_d,
                "hum_heading": hum_h, "hum_depth": hum_d,
                "dheading_deg": dh, "ddepth_m": dd,
            }
            w.writerow(row)
            sums["sq_dh"] += dh * dh
            sums["sq_dd"] += dd * dd
            sums["n"] += 1
            print(f"[shadow_diff] dh={dh:+.2f}°  dd={dd:+.3f}m  "
                  f"jet=({jet_h:.1f},{jet_d:.2f}) hum=({hum_h:.1f},{hum_d:.2f})")
    finally:
        fp.close()
        node.destroy_node()
        rclpy.shutdown()

    n = max(1, sums["n"])
    rmse_h = math.sqrt(sums["sq_dh"] / n)
    rmse_d = math.sqrt(sums["sq_dd"] / n)
    print(f"[shadow_diff] RMSE heading={rmse_h:.2f}° depth={rmse_d:.3f}m  "
          f"(threshold heading<10°, depth<0.5m)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

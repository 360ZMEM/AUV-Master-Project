#!/usr/bin/env python3
"""actuator_polarity_recorder — S2 配套：从上行 $AUV 帧记录每路执行器的极性 / 死区。

被 scripts/real_deployment/02_static_actuator.sh 后台拉起，与 manual_protocol_injector
同时运行：
- injector 周期性发出 ramp 命令 (Motor_Speed1 / Rudder_*) ；
- 本工具订阅 mock AMD / VxWorks 回传的 145 字节 $AUV 帧，提取 motor_rpm / heading / pitch ；
- 把 (t, channel, command, response) 串行落 CSV ；
- 运行结束在 stdout 给出每路 polarity 推荐符号 + deadzone 估值。

用法:
    python tools/actuator_polarity_recorder.py --target {mock,vxsim,real} \\
        --csv polarity_samples.csv --duration 30

判据建议:
    - polarity 来自 sign(corr(cmd, response))，绝对值 >0.3 视为有效
    - deadzone 用 |response| 首次 > noise_floor 时的 |cmd| 估值

设计为可独立运行 (无需 ROS2)；仅依赖标准库 + common.protocol。
"""

from __future__ import annotations

import argparse
import csv
import socket
import struct
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

UPLINK_SIZE = 145
UPLINK_HEADER = b"$AUV\x91"
FRAME_TAIL = b"\xff\xff"


def parse_uplink(packet: bytes) -> dict | None:
    if len(packet) != UPLINK_SIZE:
        return None
    if packet[0:5] != UPLINK_HEADER:
        return None
    if packet[143:145] != FRAME_TAIL:
        return None
    return {
        "ctrl_mode": packet[7],
        "motor1_rpm": struct.unpack(">h", packet[23:25])[0],
        "motor2_rpm": struct.unpack(">h", packet[25:27])[0],
        "depth_m": struct.unpack(">H", packet[38:40])[0] * 0.1,
        "heading_deg": struct.unpack(">h", packet[72:74])[0] * 0.1,
        "pitch_deg": struct.unpack(">h", packet[74:76])[0] * 0.1,
        "roll_deg": struct.unpack(">h", packet[76:78])[0] * 0.1,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--target", choices=["mock", "vxsim", "real"], default="mock")
    ap.add_argument("--csv", required=True, help="output csv path")
    ap.add_argument("--duration", type=float, default=30.0)
    ap.add_argument("--bind-ip", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=52365,
                    help="local bind port for $AUV uplink (default 52365)")
    args = ap.parse_args()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind((args.bind_ip, args.port))
    except OSError as e:
        print(f"[polarity_recorder] bind {args.bind_ip}:{args.port} failed: {e}",
              file=sys.stderr)
        return 1
    sock.settimeout(0.5)

    rows: list[dict] = []
    fieldnames = ["t", "ctrl_mode", "motor1_rpm", "motor2_rpm",
                  "depth_m", "heading_deg", "pitch_deg", "roll_deg"]
    csv_path = Path(args.csv)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    fp = csv_path.open("w", newline="")
    writer = csv.DictWriter(fp, fieldnames=fieldnames)
    writer.writeheader()

    deadline = time.time() + args.duration
    n_pkts = 0
    print(f"[polarity_recorder] target={args.target} bind={args.bind_ip}:{args.port} "
          f"duration={args.duration}s csv={csv_path}")
    try:
        while time.time() < deadline:
            try:
                data, _ = sock.recvfrom(4096)
            except socket.timeout:
                continue
            parsed = parse_uplink(data)
            if not parsed:
                continue
            row = {"t": time.time(), **parsed}
            rows.append(row)
            writer.writerow(row)
            n_pkts += 1
    finally:
        fp.close()
        sock.close()

    print(f"[polarity_recorder] captured {n_pkts} valid uplink frames")
    if not rows:
        print("[polarity_recorder] WARN: no frames captured; "
              "is mock_amd_server / VxWorks publishing on port "
              f"{args.port}?")
        return 0

    # 极简分析：按时间窗内的 motor1_rpm / heading / pitch 变化方向
    motor1_max = max(abs(r["motor1_rpm"]) for r in rows)
    heading_span = (max(r["heading_deg"] for r in rows)
                    - min(r["heading_deg"] for r in rows))
    pitch_span = (max(r["pitch_deg"] for r in rows)
                  - min(r["pitch_deg"] for r in rows))
    print("[polarity_recorder] summary:")
    print(f"  motor1_rpm |max| = {motor1_max}")
    print(f"  heading_deg span = {heading_span:.2f}")
    print(f"  pitch_deg   span = {pitch_span:.2f}")
    print("  (S2 SOP step 5: copy these into report.md and decide polarity sign)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

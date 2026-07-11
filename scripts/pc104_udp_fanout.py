#!/usr/bin/env python3
"""PC104 UDP fan-out proxy for concurrent ROS2 and PySide6 debugging."""

from __future__ import annotations

import argparse
import select
import socket
import sys
import time
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from common.protocol import (  # noqa: E402
    PROTOCOL_DOWNLINK_HEADER,
    PROTOCOL_DOWNLINK_SIZE,
    PROTOCOL_UPLINK_HEADER,
    PROTOCOL_UPLINK_SIZE,
    parse_downlink_packet,
)


@dataclass(frozen=True)
class Endpoint:
    name: str
    host: str
    port: int

    @classmethod
    def parse(cls, raw: str) -> "Endpoint":
        try:
            name, address = raw.split("=", 1)
            host, port_text = address.rsplit(":", 1)
        except ValueError as exc:
            raise argparse.ArgumentTypeError(
                f"endpoint must be name=host:port, got {raw!r}"
            ) from exc
        return cls(name=name.strip(), host=host.strip(), port=int(port_text))

    @property
    def addr(self) -> tuple[str, int]:
        return (self.host, self.port)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Bind the real PC104 UDP port once, fan out uplink telemetry to "
            "local ROS2/PySide6 high ports, and arbitrate local downlink packets."
        )
    )
    parser.add_argument("--pc104-host", default="192.168.0.101")
    parser.add_argument("--pc104-port", type=int, default=21)
    parser.add_argument("--listen-host", default="192.168.0.11")
    parser.add_argument("--listen-port", type=int, default=21)
    parser.add_argument("--cmd-host", default="127.0.0.1")
    parser.add_argument("--cmd-port", type=int, default=52364)
    parser.add_argument(
        "--subscriber",
        action="append",
        type=Endpoint.parse,
        default=[],
        help="Uplink subscriber in name=host:port form. May be repeated.",
    )
    parser.add_argument(
        "--ros-source-port",
        type=int,
        default=52365,
        help="Expected local source port for ROS2 downlink packets.",
    )
    parser.add_argument(
        "--console-source-port",
        type=int,
        default=52366,
        help="Expected local source port for PySide6 downlink packets.",
    )
    parser.add_argument(
        "--allow-ros-downlink",
        action="store_true",
        default=True,
        help="Allow safe ROS2 downlink packets.",
    )
    parser.add_argument(
        "--no-allow-ros-downlink",
        dest="allow_ros_downlink",
        action="store_false",
        help="Block ROS2 downlink packets.",
    )
    parser.add_argument(
        "--allow-console-downlink",
        action="store_true",
        default=True,
        help="Allow safe PySide6 downlink packets.",
    )
    parser.add_argument(
        "--no-allow-console-downlink",
        dest="allow_console_downlink",
        action="store_false",
        help="Block PySide6 downlink packets.",
    )
    parser.add_argument(
        "--allow-nonzero-actuator",
        action="store_true",
        help="Forward packets with non-zero thrust, side motor, or fins.",
    )
    parser.add_argument("--main-motor-rpm-scale", type=float, default=15.0)
    parser.add_argument("--status-period-s", type=float, default=2.0)
    parser.add_argument("--recv-buffer-size", type=int, default=4096)
    return parser.parse_args()


def classify_source(addr: tuple[str, int], args: argparse.Namespace) -> str:
    host, port = addr
    if host in {"127.0.0.1", "::1"} and port == args.ros_source_port:
        return "ros2"
    if host in {"127.0.0.1", "::1"} and port == args.console_source_port:
        return "pyside6"
    return f"unknown:{host}:{port}"


def is_zero_actuator_packet(packet: bytes, args: argparse.Namespace) -> tuple[bool, str]:
    state = parse_downlink_packet(packet, main_motor_rpm_scale=args.main_motor_rpm_scale)
    actuator_values = (
        state.main_motor_rpm,
        state.side_motor_rpm,
        state.right_fin_deg,
        state.top_fin_deg,
        state.left_fin_deg,
        state.bottom_fin_deg,
    )
    is_zero = all(abs(float(value)) < 1e-6 for value in actuator_values)
    summary = (
        f"obj={state.obj_address} ctrl={state.control_mode_byte} work={state.work_instruction} "
        f"depth={state.depth_protect_params} bottom={state.bottom_protect_params} "
        f"preset={state.preset_time_tenths_min} motor={state.main_motor_rpm}/{state.side_motor_rpm} "
        f"fins=({state.left_fin_deg:.1f},{state.right_fin_deg:.1f},"
        f"{state.top_fin_deg:.1f},{state.bottom_fin_deg:.1f})"
    )
    return is_zero, summary


def should_forward_downlink(
    packet: bytes,
    source_name: str,
    args: argparse.Namespace,
) -> tuple[bool, str]:
    if len(packet) != PROTOCOL_DOWNLINK_SIZE or not packet.startswith(PROTOCOL_DOWNLINK_HEADER):
        return False, f"not a {PROTOCOL_DOWNLINK_SIZE}-byte $CKTH packet"

    if source_name == "ros2" and not args.allow_ros_downlink:
        return False, "ROS2 downlink disabled"
    if source_name == "pyside6" and not args.allow_console_downlink:
        return False, "PySide6 downlink disabled"
    if source_name.startswith("unknown"):
        return False, "unknown local downlink source"

    try:
        is_zero, summary = is_zero_actuator_packet(packet, args)
    except Exception as exc:  # noqa: BLE001 - keep proxy alive during HIL.
        return False, f"parse failed: {exc}"

    if not is_zero and not args.allow_nonzero_actuator:
        return False, f"non-zero actuator blocked: {summary}"
    return True, summary


def make_socket(bind_addr: tuple[str, int]) -> socket.socket:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(bind_addr)
    sock.setblocking(False)
    return sock


def main() -> int:
    args = parse_args()
    subscribers = args.subscriber or [
        Endpoint("ros2", "127.0.0.1", 52365),
        Endpoint("pyside6", "127.0.0.1", 52366),
    ]

    pc_sock = make_socket((args.listen_host, args.listen_port))
    cmd_sock = make_socket((args.cmd_host, args.cmd_port))
    pc104_addr = (args.pc104_host, args.pc104_port)

    print(
        f"[fanout] PC104 uplink bind {args.listen_host}:{args.listen_port}, "
        f"PC104 remote {args.pc104_host}:{args.pc104_port}"
    )
    print(f"[fanout] local downlink bind {args.cmd_host}:{args.cmd_port}")
    print("[fanout] subscribers: " + ", ".join(f"{item.name}={item.host}:{item.port}" for item in subscribers))
    print(
        "[fanout] safety: "
        f"ros_downlink={args.allow_ros_downlink}, "
        f"console_downlink={args.allow_console_downlink}, "
        f"allow_nonzero_actuator={args.allow_nonzero_actuator}"
    )

    uplink_count = 0
    downlink_count = 0
    blocked_count = 0
    last_status = time.time()

    try:
        while True:
            readable, _, _ = select.select([pc_sock, cmd_sock], [], [], 0.2)
            for sock in readable:
                packet, addr = sock.recvfrom(args.recv_buffer_size)

                if sock is pc_sock:
                    if addr[0] != args.pc104_host:
                        print(f"[fanout] ignore non-PC104 packet from {addr[0]}:{addr[1]} len={len(packet)}")
                        continue
                    if len(packet) == PROTOCOL_UPLINK_SIZE and packet.startswith(PROTOCOL_UPLINK_HEADER):
                        uplink_count += 1
                    else:
                        print(f"[fanout] forward atypical PC104 packet len={len(packet)} from {addr[0]}:{addr[1]}")
                    for endpoint in subscribers:
                        pc_sock.sendto(packet, endpoint.addr)
                    continue

                source_name = classify_source(addr, args)
                allowed, reason = should_forward_downlink(packet, source_name, args)
                if allowed:
                    pc_sock.sendto(packet, pc104_addr)
                    downlink_count += 1
                    print(f"[fanout] forward {source_name} -> PC104: {reason}")
                else:
                    blocked_count += 1
                    print(f"[fanout] block {source_name}: {reason}")

            now = time.time()
            if now - last_status >= args.status_period_s:
                last_status = now
                print(
                    f"[fanout] status uplink={uplink_count} "
                    f"downlink={downlink_count} blocked={blocked_count}"
                )
    except KeyboardInterrupt:
        print("[fanout] interrupted, shutting down")
    finally:
        pc_sock.close()
        cmd_sock.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

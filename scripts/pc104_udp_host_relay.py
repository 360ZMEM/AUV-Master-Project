#!/usr/bin/env python3
"""Host-side PC104 UDP relay for Docker-published timing probes."""

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
    host: str
    port: int

    @classmethod
    def parse(cls, raw: str) -> "Endpoint":
        try:
            host, port_text = raw.rsplit(":", 1)
        except ValueError as exc:
            raise argparse.ArgumentTypeError(
                f"endpoint must be host:port, got {raw!r}"
            ) from exc
        return cls(host=host.strip(), port=int(port_text))

    @property
    def addr(self) -> tuple[str, int]:
        return (self.host, self.port)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run on the host OS. Bind the PC104-facing 21/udp socket once, "
            "forward PC104 uplink into a Docker-published container port, and "
            "forward container downlink back to PC104 from the same host 21/udp "
            "source port."
        )
    )
    parser.add_argument("--host-ip", default="192.168.0.11")
    parser.add_argument("--pc104-host", default="192.168.0.101")
    parser.add_argument("--pc104-port", type=int, default=21)
    parser.add_argument("--pc104-local-port", type=int, default=21)
    parser.add_argument(
        "--container-uplink-target",
        type=Endpoint.parse,
        default=Endpoint("127.0.0.1", 10021),
        help=(
            "Host endpoint that Docker publishes to the container probe "
            "local port, usually 127.0.0.1:10021 for host 10021 -> container 21."
        ),
    )
    parser.add_argument(
        "--disable-container-target-learning",
        action="store_true",
        help=(
            "Keep using --container-uplink-target. By default the relay learns "
            "the container's actual UDP source address from the first safe "
            "downlink packet and mirrors PC104 uplink back to that address."
        ),
    )
    parser.add_argument("--downlink-bind-host", default="0.0.0.0")
    parser.add_argument("--downlink-bind-port", type=int, default=10022)
    parser.add_argument("--log-bind-port", type=int, default=52367)
    parser.add_argument(
        "--container-log-target",
        type=Endpoint.parse,
        default=Endpoint("127.0.0.1", 62367),
    )
    parser.add_argument(
        "--disable-log-forward",
        action="store_true",
        help="Do not bind/forward PC104 UdpLogger packets.",
    )
    parser.add_argument(
        "--allow-nonzero-actuator",
        action="store_true",
        help="Forward non-zero actuator packets. Keep disabled for timing probes.",
    )
    parser.add_argument("--main-motor-rpm-scale", type=float, default=15.0)
    parser.add_argument("--status-period-s", type=float, default=2.0)
    parser.add_argument("--recv-buffer-size", type=int, default=4096)
    return parser.parse_args()


def make_udp_socket(bind_addr: tuple[str, int]) -> socket.socket:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(bind_addr)
    sock.setblocking(False)
    return sock


# /**
#  * @brief Return whether a downlink packet is safe to forward to the PC104.
#  */
def is_safe_downlink(packet: bytes, args: argparse.Namespace) -> tuple[bool, str]:
    if len(packet) != PROTOCOL_DOWNLINK_SIZE or not packet.startswith(
        PROTOCOL_DOWNLINK_HEADER
    ):
        return False, f"not a {PROTOCOL_DOWNLINK_SIZE}-byte $CKTH packet"

    try:
        state = parse_downlink_packet(
            packet,
            main_motor_rpm_scale=float(args.main_motor_rpm_scale),
        )
    except Exception as exc:  # noqa: BLE001 - keep relay alive during HIL.
        return False, f"parse failed: {exc}"

    actuator_values = (
        state.main_motor_rpm,
        state.side_motor_rpm,
        state.right_fin_deg,
        state.top_fin_deg,
        state.left_fin_deg,
        state.bottom_fin_deg,
    )
    is_zero = all(abs(float(value)) < 1.0e-6 for value in actuator_values)
    summary = (
        f"obj={state.obj_address} ctrl={state.control_mode_byte} "
        f"work={state.work_instruction} motor={state.main_motor_rpm}/"
        f"{state.side_motor_rpm} fins=({state.left_fin_deg:.1f},"
        f"{state.right_fin_deg:.1f},{state.top_fin_deg:.1f},"
        f"{state.bottom_fin_deg:.1f})"
    )
    if not is_zero and not args.allow_nonzero_actuator:
        return False, f"non-zero actuator blocked: {summary}"
    return True, summary


def main() -> int:
    args = parse_args()
    pc104_addr = (str(args.pc104_host), int(args.pc104_port))
    pc_sock = make_udp_socket((str(args.host_ip), int(args.pc104_local_port)))
    downlink_sock = make_udp_socket(
        (str(args.downlink_bind_host), int(args.downlink_bind_port))
    )
    container_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    log_sock = None
    if not args.disable_log_forward:
        log_sock = make_udp_socket((str(args.host_ip), int(args.log_bind_port)))

    sockets = [pc_sock, downlink_sock]
    if log_sock is not None:
        sockets.append(log_sock)

    print(
        "[host-relay] pc104 socket "
        f"{args.host_ip}:{args.pc104_local_port} <-> "
        f"{args.pc104_host}:{args.pc104_port}",
        flush=True,
    )
    print(
        "[host-relay] uplink target "
        f"{args.container_uplink_target.host}:{args.container_uplink_target.port}",
        flush=True,
    )
    print(
        "[host-relay] downlink ingress "
        f"{args.downlink_bind_host}:{args.downlink_bind_port}",
        flush=True,
    )
    if log_sock is not None:
        print(
            "[host-relay] log forward "
            f"{args.host_ip}:{args.log_bind_port} -> "
            f"{args.container_log_target.host}:{args.container_log_target.port}",
            flush=True,
        )

    uplink_count = 0
    downlink_count = 0
    blocked_count = 0
    log_count = 0
    last_status = time.monotonic()
    learned_container_target: tuple[str, int] | None = None

    try:
        while True:
            readable, _, _ = select.select(sockets, [], [], 0.2)
            for sock in readable:
                packet, addr = sock.recvfrom(int(args.recv_buffer_size))
                if sock is pc_sock:
                    if (
                        len(packet) == PROTOCOL_UPLINK_SIZE
                        and packet.startswith(PROTOCOL_UPLINK_HEADER)
                    ):
                        uplink_count += 1
                    if learned_container_target is not None:
                        downlink_sock.sendto(packet, learned_container_target)
                    else:
                        container_sock.sendto(packet, args.container_uplink_target.addr)
                    continue

                if sock is downlink_sock:
                    allowed, reason = is_safe_downlink(packet, args)
                    if allowed:
                        if (
                            not args.disable_container_target_learning
                            and learned_container_target != addr
                        ):
                            learned_container_target = addr
                            print(
                                "[host-relay] learned container uplink target "
                                f"{addr[0]}:{addr[1]}",
                                flush=True,
                            )
                        pc_sock.sendto(packet, pc104_addr)
                        downlink_count += 1
                        print(f"[host-relay] forward downlink: {reason}", flush=True)
                    else:
                        blocked_count += 1
                        print(
                            f"[host-relay] block downlink from {addr[0]}:{addr[1]}: "
                            f"{reason}",
                            flush=True,
                        )
                    continue

                if log_sock is not None and sock is log_sock:
                    log_count += 1
                    container_sock.sendto(packet, args.container_log_target.addr)

            now = time.monotonic()
            if now - last_status >= float(args.status_period_s):
                last_status = now
                print(
                    "[host-relay] status "
                    f"uplink={uplink_count} downlink={downlink_count} "
                    f"blocked={blocked_count} log={log_count}",
                    flush=True,
                )
    except KeyboardInterrupt:
        print("[host-relay] interrupted", flush=True)
    finally:
        pc_sock.close()
        downlink_sock.close()
        container_sock.close()
        if log_sock is not None:
            log_sock.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

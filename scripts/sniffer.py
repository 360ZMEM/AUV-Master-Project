#!/usr/bin/env python3
"""Standalone UDP sniffer for the $CKTH/$AUV binary protocol."""

from __future__ import annotations

import argparse
import signal
import socket
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
project_root_str = str(PROJECT_ROOT)
if project_root_str not in sys.path:
    sys.path.insert(0, project_root_str)

from common.protocol_debug import format_protocol_packet, format_protocol_packet_ascii, format_protocol_packet_raw


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="UDP sniffer for AUV binary protocol traffic")
    parser.add_argument("--bind-host", default="0.0.0.0", help="Local host to bind")
    parser.add_argument("--bind-port", type=int, default=52364, help="Local UDP port to bind")
    parser.add_argument("--count", type=int, default=0, help="Stop after N packets, 0 means unlimited")
    parser.add_argument("--recv-buffer-size", type=int, default=4096, help="UDP receive buffer size")
    parser.add_argument("--show-hex", action="store_true", help="Include hexadecimal preview in each line")
    parser.add_argument("--hex-bytes", type=int, default=48, help="Maximum bytes to show in hex preview")
    parser.add_argument("--ascii-format", action="store_true", help="Print detailed ASCII diagnostic blocks")
    parser.add_argument("--raw-format", action="store_true", help="Print compact CSV-style raw lines")
    parser.add_argument("--no-timestamp", action="store_true", help="Disable timestamps in ASCII mode")
    parser.add_argument("--no-color", action="store_true", help="Disable ANSI colors")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((args.bind_host, args.bind_port))

    stop_requested = {"value": False}

    def _request_stop(signum, frame) -> None:
        stop_requested["value"] = True

    signal.signal(signal.SIGINT, _request_stop)
    signal.signal(signal.SIGTERM, _request_stop)

    print(f"sniffer listening on udp://{args.bind_host}:{args.bind_port}")

    packet_count = 0
    try:
        while not stop_requested["value"]:
            packet, addr = sock.recvfrom(args.recv_buffer_size)
            packet_count += 1
            if args.ascii_format:
                print(
                    format_protocol_packet_ascii(
                        packet,
                        label="sniffer",
                        source=f"{addr[0]}:{addr[1]}",
                        include_timestamp=not args.no_timestamp,
                        color=not args.no_color,
                    )
                )
                print()
            elif args.raw_format:
                print(
                    format_protocol_packet_raw(
                        packet,
                        label="sniffer",
                        source=f"{addr[0]}:{addr[1]}",
                        color=not args.no_color,
                        include_hex=args.show_hex,
                        max_hex_bytes=args.hex_bytes,
                    )
                )
            else:
                print(
                    format_protocol_packet(
                        packet,
                        label="sniffer",
                        source=f"{addr[0]}:{addr[1]}",
                        color=not args.no_color,
                        include_hex=args.show_hex,
                        max_hex_bytes=args.hex_bytes,
                    )
                )
            if args.count > 0 and packet_count >= args.count:
                break
    finally:
        sock.close()

    print(f"sniffer stopped after {packet_count} packets")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
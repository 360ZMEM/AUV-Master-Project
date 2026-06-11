#!/usr/bin/env python3
"""VxWorks UDP 日志接收器。

监听 VxWorks UdpLogger 模块发送的 UDP 日志数据包，实时打印到终端。
配合 csd_vx6.8_lastest/UdpLogger.c 使用。

使用方式:
    python scripts/log_receiver.py                    # 默认监听 0.0.0.0:52367
    python scripts/log_receiver.py --port 52367       # 指定端口
    python scripts/log_receiver.py --save vxlog.txt   # 同时保存到文件
    python scripts/log_receiver.py --timestamps       # 每行加时间戳

网络配置:
    VxWorks UdpLogger 目标:  UDP_LOG_TARGET_IP:UDP_LOG_PORT
    默认:                    192.168.0.11:52367
    本脚本绑定:              0.0.0.0:52367 (监听所有接口)

协议:
    无帧头，纯文本 UTF-8 流。每个 UDP 包含一段日志文本 (最大 1400 字节)。
    可能包含多行 (\\n 分隔) 或不完整行 (跨包拼接)。
"""

from __future__ import annotations

import argparse
import datetime
import signal
import socket
import sys


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="VxWorks UDP log receiver (配合 UdpLogger.c 使用)"
    )
    parser.add_argument(
        "--host", default="0.0.0.0",
        help="本地绑定地址 (默认 0.0.0.0 监听所有接口)"
    )
    parser.add_argument(
        "--port", type=int, default=52367,
        help="本地绑定 UDP 端口 (默认 52367, 与 UdpLogger.h 中 UDP_LOG_PORT 一致)"
    )
    parser.add_argument(
        "--save", type=str, default=None,
        help="同时保存日志到指定文件路径"
    )
    parser.add_argument(
        "--timestamps", action="store_true",
        help="为每个接收到的 UDP 包添加本地时间戳前缀"
    )
    parser.add_argument(
        "--buffer-size", type=int, default=4096,
        help="UDP 接收缓冲区大小 (默认 4096)"
    )
    parser.add_argument(
        "--quiet-header", action="store_true",
        help="不打印启动信息头"
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((args.host, args.port))

    # 信号处理: 优雅退出
    stop = {"value": False}

    def _handle_signal(signum, frame):
        stop["value"] = True

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    # 打开日志文件 (可选)
    log_file = None
    if args.save:
        log_file = open(args.save, "a", encoding="utf-8")

    if not args.quiet_header:
        header = (
            f"╔══════════════════════════════════════════════════╗\n"
            f"║  VxWorks UDP Log Receiver                       ║\n"
            f"║  Listening on udp://{args.host}:{args.port:<5}              ║\n"
            f"║  Press Ctrl+C to stop                           ║\n"
            f"╚══════════════════════════════════════════════════╝"
        )
        print(header)
        if log_file:
            print(f"  Saving to: {args.save}")
        print()

    packet_count = 0
    total_bytes = 0

    try:
        sock.settimeout(0.5)  # 允许信号中断检查
        while not stop["value"]:
            try:
                data, addr = sock.recvfrom(args.buffer_size)
            except socket.timeout:
                continue

            packet_count += 1
            total_bytes += len(data)

            # 解码为文本 (VxWorks printf 输出为 ASCII)
            try:
                text = data.decode("utf-8", errors="replace")
            except Exception:
                text = data.decode("latin-1")

            # 输出到终端
            if args.timestamps:
                ts = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
                # 为多行内容每行加时间戳
                lines = text.rstrip("\n").split("\n")
                for line in lines:
                    output = f"[{ts}] {line}"
                    print(output)
                    if log_file:
                        log_file.write(output + "\n")
            else:
                sys.stdout.write(text)
                sys.stdout.flush()
                if log_file:
                    log_file.write(text)

            if log_file:
                log_file.flush()

    finally:
        sock.close()
        if log_file:
            log_file.close()

    print(f"\n--- log_receiver stopped: {packet_count} packets, {total_bytes} bytes ---")
    return 0


if __name__ == "__main__":
    sys.exit(main())

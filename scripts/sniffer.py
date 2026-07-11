#!/usr/bin/env python3
"""$CKTH/$AUV 二进制协议的独立 UDP 嗅探器。

用于在调试协议流量时快速查看 UDP 包内容，支持十六进制、ASCII 和
紧凑原始输出三种格式。
"""

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
    """解析嗅探器命令行参数。

    该函数为嗅探器脚本提供完整的命令行接口，支持配置网络端点（监听主机/端口）、
    输出格式（ASCII 诊断块、原始 CSV、紧凑格式）、十六进制预览和 ANSI 颜色选项。
    允许用户控制接收缓冲区大小和包计数限制。

    @return: 解析后的命令行参数命名空间，具体属性包括：
        - bind_host: 本地监听主机地址（默认 0.0.0.0 表示监听所有接口）
        - bind_port: 本地监听 UDP 端口（默认 52364）
        - count: 接收指定包数后停止（0 表示无限）
        - recv_buffer_size: UDP 接收缓冲区字节数（默认 4096）
        - show_hex: 是否在每行输出中包含十六进制预览
        - hex_bytes: 十六进制预览的最大字节数（默认 48）
        - ascii_format: 是否使用 ASCII 诊断块格式（多行详细）
        - raw_format: 是否使用原始 CSV 格式（单行机器友好）
        - no_timestamp: 是否禁用 ASCII 模式中的时间戳
        - no_color: 是否禁用 ANSI 颜色代码
    @throws SystemExit: 参数解析失败或用户请求帮助（-h）时由 argparse 抛出
    @note: 三种输出格式互斥（ASCII → 原始 → 紧凑，优先级从高到低）；
           颜色支持由 protocol_debug 模块的 supports_color() 函数进一步检查
    """
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
    """嗅探器主程序：绑定 UDP 端口、接收协议包、格式化输出。

    该函数是嗅探器脚本的核心逻辑：解析命令行参数、创建 UDP socket、
    绑定本地地址、注册信号处理器、进入接收循环、根据用户选择的格式
    调用相应的格式化函数输出、按包计数限制条件或信号中断。

    接收循环会捕获 SIGINT 和 SIGTERM 信号，设置内部标志位主动退出（finally 块清资源）。
    支持三种输出格式：ASCII 诊断块（多行详细）、原始 CSV（紧凑机器友好）、
    默认紧凑格式（推荐用于日志）。

    @return: 返回进程退出码（总是返回 0，表示正常完成）
    @throws OSError: 若网络接口绑定失败（例如端口已被占用）时抛出，导致进程异常退出
    @note: 接收缓冲区大小由 --recv-buffer-size 参数控制（默认 4096 字节）；
           若网络包大于缓冲区则会被截截；UDP 连接无状态，任何地址的包都会被接收；
           按 Ctrl-C 或 SIGTERM 信号时会正常关闭 socket；包计数在信号处理前都会检查；
           ASCII 模式默认包含时间戳和源地址缩写，可用 --no-timestamp 禁用
    """
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

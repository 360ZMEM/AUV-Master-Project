#!/usr/bin/env python3
# pyright: reportMissingImports=false
"""Smoke test that simulates GUI button presses and verifies UDP delivery."""

from __future__ import annotations

import argparse
import socket
import sys
import threading
from pathlib import Path
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

AUV_ROOT = PROJECT_ROOT.parent.parent / "AUV_Master_Project"
if str(AUV_ROOT) not in sys.path:
    sys.path.insert(0, str(AUV_ROOT))

from common.protocol_debug import format_protocol_packet_ascii, format_protocol_packet_raw
from src.data_structures import Preferences
from src.ui.main_window import MainWindow
from src.utils.config_manager import ConfigManager
from src.utils.mode_manager import ModeConfigManager


TEST_CONSOLE_IP = "127.0.0.1"
TEST_CONSOLE_PORT = 55555
TEST_AUV_IP = "127.0.0.1"
TEST_AUV_PORT = 52364

BUTTONS = {
    "task_start": {
        "label": "任务开启",
        "work_instruction": 0x01,
        "click": lambda window: window.btn_task_start.click(),
    },
    "task_cancel": {
        "label": "任务取消",
        "work_instruction": 0x02,
        "click": lambda window: window.btn_task_cancel.click(),
    },
    "clear_fault": {
        "label": "清除故障",
        "work_instruction": 0x91,
        "click": lambda window: window.btn_clear_fault.click(),
    },
    "init": {
        "label": "初始化",
        "work_instruction": 0x92,
        "click": lambda window: window.btn_init.click(),
    },
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Simulate GUI button presses and verify UDP delivery")
    parser.add_argument("--button", action="append", choices=BUTTONS.keys(), help="Button to simulate; can be repeated")
    parser.add_argument("--console-ip", default=TEST_CONSOLE_IP, help="Local console bind IP")
    parser.add_argument("--console-port", type=int, default=TEST_CONSOLE_PORT, help="Local console bind port")
    parser.add_argument("--auv-ip", default=TEST_AUV_IP, help="Target AUV IP")
    parser.add_argument("--auv-port", type=int, default=TEST_AUV_PORT, help="Target AUV UDP port")
    parser.add_argument("--timeout", type=float, default=5.0, help="UDP receive timeout in seconds")
    return parser.parse_args()


def _patch_configuration(settings: dict[str, object]) -> None:
    def load_port_config(self):
        return {
            "radio_port": "COM3",
            "beidou_port": "COM4",
            "console_ip": settings["console_ip"],
            "console_port": settings["console_port"],
            "auv_ip": settings["auv_ip"],
            "auv_port": settings["auv_port"],
        }

    def load_side_channel_config(self):
        return {
            "enabled": False,
            "pc_cmd_raw_key": "rt/pc/cmd_raw",
            "telemetry_key": "rt/auv/telemetry",
            "viz_internal_key": "rt/auv/viz/internal",
            "publish_cmd_raw": True,
            "subscribe_bridge_telemetry": False,
            "subscribe_viz_internal": False,
            "session": {},
        }

    def load_mode_config(self):
        return {"mode": "online", "online": {"enabled": True}, "offline": {}}

    ConfigManager.load_port_config = load_port_config
    ConfigManager.load_side_channel_config = load_side_channel_config
    ModeConfigManager.load_config = load_mode_config


def _recv_one_packet(sock: socket.socket, result: dict[str, object]) -> None:
    packets: list[tuple[bytes, tuple[str, int]]] = []
    errors: list[Exception] = []
    while len(packets) < 2:
        try:
            packet, addr = sock.recvfrom(4096)
            packets.append((packet, addr))
        except Exception as exc:
            errors.append(exc)
            break
    result["packets"] = packets
    result["errors"] = errors


def main() -> int:
    args = parse_args()
    button_names = args.button or ["task_start", "clear_fault"]
    settings: dict[str, object] = {
        "console_ip": args.console_ip,
        "console_port": args.console_port,
        "auv_ip": args.auv_ip,
        "auv_port": args.auv_port,
    }

    _patch_configuration(settings)

    listener = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    listener.bind((str(settings["auv_ip"]), int(settings["auv_port"])))
    listener.settimeout(args.timeout)

    result: dict[str, object] = {}
    thread = threading.Thread(target=_recv_one_packet, args=(listener, result), daemon=True)
    thread.start()

    app = QApplication.instance() or QApplication(sys.argv)
    window = MainWindow()

    window.preferences = Preferences()
    window.preferences.obj_address = 2
    window.preferences.work_mode = 2
    window.combo_address.setCurrentIndex(1)
    window.combo_mode.setCurrentIndex(2)

    for index, button_name in enumerate(button_names, start=1):
        button_spec = BUTTONS[button_name]
        print(f"click_{index}: {button_spec['label']}")
        button_spec["click"](window)
        app.processEvents()
        send_ok = window.transmit_data()
        app.processEvents()
        print(f"send_result_{index}: {send_ok}")

    thread.join(timeout=5.5)
    listener.close()

    packets = result.get("packets")
    if not isinstance(packets, list) or len(packets) < len(button_names):
        errors = result.get("errors")
        expected_count = len(button_names)
        got_count = 0 if not isinstance(packets, list) else len(packets)
        print(f"FAIL: expected {expected_count} UDP packets, got {got_count} ({errors!r})")
        window.close()
        return 1

    expected_work_instructions = [BUTTONS[name]["work_instruction"] for name in button_names]
    for index, ((packet, addr), expected_work_instruction) in enumerate(zip(packets[: len(button_names)], expected_work_instructions), start=1):
        print(f"received_{index} from: {addr}")
        print(f"packet_{index}_length: {len(packet)}")
        print(format_protocol_packet_raw(packet, label=f"button-smoke-{index}", source=str(addr), include_hex=True))
        print(format_protocol_packet_ascii(packet, label=f"button-smoke-{index}", source=str(addr), include_timestamp=False))

        if not bytes(packet[:5]) == b"$CKTH":
            print(f"FAIL: packet {index} header mismatch")
            window.close()
            return 1

        if len(packet) != 72:
            print(f"FAIL: packet {index} length mismatch")
            window.close()
            return 1

        if packet[22] != expected_work_instruction:
            print(
                f"FAIL: packet {index} work instruction mismatch "
                f"(got 0x{packet[22]:02X}, expected 0x{expected_work_instruction:02X})"
            )
            window.close()
            return 1

    print(f"PASS: {len(button_names)} GUI button presses emitted {len(button_names)} UDP $CKTH packets")

    window.close()
    app.processEvents()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
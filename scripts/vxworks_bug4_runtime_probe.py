#!/usr/bin/env python3
"""BUG-4 runtime probe for the current VxWorks image.

/**
 * @file    vxworks_bug4_runtime_probe.py
 * @brief   BUG-4 runtime-only Telnet probe without requiring a firmware reburn.
 * @date    2026-07-11
 * @author  Tsinghua AUV Research Group
 *
 * This helper is intentionally separate from vxworks_safety_hil.py. The older
 * HIL script still contains idealized VxWorks shell expressions, while this
 * probe uses the runtime lessons from PC104 HIL: lkup symbols first, calculate
 * absolute addresses in Python, and keep shell commands short.
 */
"""

from __future__ import annotations

import argparse
import re
import sys
import telnetlib
import time
from dataclasses import dataclass


DEFAULT_HOST = "192.168.0.101"


@dataclass(frozen=True)
class Offsets:
    """Runtime offsets observed on the current PC104 image."""

    current_depth: int = 0x34
    ui_ctrl_mode: int = 0x07
    ui_depth_para1: int = 0x08
    ui_motor1: int = 0x18
    ui_lh_angle: int = 0x1C
    ui_rh_angle: int = 0x1E


class VxShell:
    """Small Telnet wrapper for VxWorks shell commands."""

    def __init__(self, host: str, port: int, user: str, password: str, timeout: float):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.timeout = timeout
        self.tn: telnetlib.Telnet | None = None

    def connect(self) -> None:
        self.tn = telnetlib.Telnet(self.host, self.port, self.timeout)
        banner = self.tn.read_until(b"->", timeout=1.0)
        if b"->" in banner:
            return
        if b"login" in banner.lower() or b"username" in banner.lower():
            self.tn.write((self.user + "\n").encode("ascii"))
            banner += self.tn.read_until(b"assword", timeout=self.timeout)
        if b"assword" in banner.lower():
            self.tn.write((self.password + "\n").encode("ascii"))
        prompt = self.tn.read_until(b"->", timeout=self.timeout)
        if b"->" not in prompt:
            raise RuntimeError("Telnet connected, but VxWorks prompt '->' was not observed")

    def close(self) -> None:
        if self.tn:
            self.tn.close()
            self.tn = None

    def cmd(self, command: str, wait: float = 0.25) -> str:
        if not self.tn:
            raise RuntimeError("Telnet is not connected")
        self.tn.write((command + "\n").encode("ascii"))
        time.sleep(wait)
        try:
            return self.tn.read_very_eager().decode("ascii", errors="replace")
        except EOFError:
            return ""

    def lkup(self, symbol: str) -> int | None:
        out = self.cmd(f'lkup "{symbol}"', wait=0.35)
        for line in out.splitlines():
            parts = line.split()
            if len(parts) >= 2 and parts[0] == symbol and re.fullmatch(r"0x[0-9a-fA-F]+", parts[1]):
                return int(parts[1], 16)
        matches = re.findall(r"0x[0-9a-fA-F]+", out)
        if not matches:
            return None
        return int(matches[0], 16)

    def read_u8(self, addr: int) -> int | None:
        return _first_int(self.cmd(f'printf("V=%u\\n", *(unsigned char*)0x{addr:x})'))

    def read_u16(self, addr: int) -> int | None:
        return _first_int(self.cmd(f'printf("V=%u\\n", *(unsigned short*)0x{addr:x})'))

    def read_s16(self, addr: int) -> int | None:
        return _first_int(self.cmd(f'printf("V=%d\\n", *(short*)0x{addr:x})'))

    def read_u32(self, addr: int) -> int | None:
        return _first_hex_or_int(self.cmd(f'printf("V=0x%08x\\n", *(unsigned int*)0x{addr:x})'))

    def write_u8(self, addr: int, value: int) -> None:
        self.cmd(f"*(unsigned char*)0x{addr:x}={value & 0xff}")

    def write_u16(self, addr: int, value: int) -> None:
        self.cmd(f"*(unsigned short*)0x{addr:x}={value & 0xffff}")

    def write_s16(self, addr: int, value: int) -> None:
        self.cmd(f"*(short*)0x{addr:x}={int(value)}")

    def write_u32(self, addr: int, value: int) -> None:
        self.cmd(f"*(unsigned int*)0x{addr:x}=0x{value & 0xffffffff:08x}")

    def read_string(self, addr: int, label: str = "BUF") -> str:
        out = self.cmd(f'printf("{label}=%s\\n", (char*)0x{addr:x})', wait=0.35)
        for line in out.splitlines():
            line = line.strip()
            prefix = label + "="
            if line.startswith(prefix):
                return line[len(prefix) :]
        return ""


def _first_int(text: str) -> int | None:
    match = re.search(r"V=(-?\d+)", text)
    if match:
        return int(match.group(1))
    return None


def _first_hex_or_int(text: str) -> int | None:
    match = re.search(r"V=(0x[0-9a-fA-F]+|-?\d+)", text)
    if not match:
        return None
    raw = match.group(1)
    return int(raw, 16) if raw.startswith("0x") else int(raw)


def _fmt(value: int | None) -> str:
    return "NA" if value is None else str(value)


def _fmt_hex(value: int | None) -> str:
    return "NA" if value is None else f"0x{value:08x}"


def _print_commands(symbols: dict[str, int | None], offsets: Offsets) -> None:
    print("\n[DRY-RUN] 未使用 --execute, 不会写入板上内存。")
    print("可手动执行的关键命令模板:")
    current = symbols.get("Current_State")
    ui = symbols.get("UI_WIFI_Instruction")
    sys_abn = symbols.get("Sys_Abnorm_Inf_Judgement")
    to_mcu = symbols.get("to_MCU_buf")
    if current:
        print(f"  *(unsigned int*)0x{current + offsets.current_depth:x}=0x41200000  /* Current_Dep=10.0f */")
    if ui:
        print(f"  *(unsigned short*)0x{ui + offsets.ui_depth_para1:x}=5")
        print(f"  *(unsigned short*)0x{ui + offsets.ui_motor1:x}=300")
        print(f"  *(short*)0x{ui + offsets.ui_lh_angle:x}=-20")
        print(f"  *(short*)0x{ui + offsets.ui_rh_angle:x}=-20")
    print("  semGive(semEmergencyTask)")
    if sys_abn:
        print(f'  printf("SYS=0x%08x\\n", *(unsigned int*)0x{sys_abn:x})')
    if to_mcu:
        print(f'  printf("TOBUF=%s\\n", (char*)0x{to_mcu:x})')


def _read_observables(sh: VxShell, symbols: dict[str, int | None], offsets: Offsets, title: str) -> None:
    print(f"\n[{title}]")
    sys_addr = symbols.get("Sys_Abnorm_Inf_Judgement")
    ex_addr = symbols.get("Depth_Exceed_FromUI12_Depth_Para1")
    ui_addr = symbols.get("UI_WIFI_Instruction")
    ins_addr = symbols.get("Instruction_To_FMCU")
    to_mcu_addr = symbols.get("to_MCU_buf")

    sys_val = sh.read_u32(sys_addr) if sys_addr else None
    ex_val = sh.read_u16(ex_addr) if ex_addr else None
    print(f"  Sys_Abnorm={_fmt_hex(sys_val)}  DepthExceed={_fmt(ex_val)}")

    if ui_addr:
        print(
            "  UI_WIFI shadow:"
            f" ctrl={_fmt(sh.read_u8(ui_addr + offsets.ui_ctrl_mode))}"
            f" depth_para1={_fmt(sh.read_u16(ui_addr + offsets.ui_depth_para1))}"
            f" motor1={_fmt(sh.read_s16(ui_addr + offsets.ui_motor1))}"
            f" lh_angle={_fmt(sh.read_s16(ui_addr + offsets.ui_lh_angle))}"
            f" rh_angle={_fmt(sh.read_s16(ui_addr + offsets.ui_rh_angle))}"
        )

    if ins_addr:
        print("  Instruction_To_FMCU word scan (+0x10..+0x2a):")
        cells = []
        for off in range(0x10, 0x2C, 2):
            cells.append(f"+0x{off:02x}={_fmt(sh.read_s16(ins_addr + off))}")
        print("    " + " ".join(cells))

    if to_mcu_addr:
        tobuf = sh.read_string(to_mcu_addr, "TOBUF")
        print(f"  TOBUF={tobuf or 'NA'}")
        if ",00300," in tobuf:
            print("  判定: final frame contains Motor1=00300")
        elif ",00000," in tobuf:
            print("  判定: final frame still contains Motor1=00000")


def _trigger_bug4(sh: VxShell, symbols: dict[str, int | None], offsets: Offsets, cycles: int, suspend: bool) -> None:
    current = _require(symbols, "Current_State")
    ui = _require(symbols, "UI_WIFI_Instruction")
    ex = _require(symbols, "Depth_Exceed_FromUI12_Depth_Para1")

    if suspend:
        print("\n[SUSPEND] taskSuspend(MainCtrlTask)")
        sh.cmd('taskSuspend(taskNameToId("MainCtrlTask"))', wait=0.35)

    print("\n[TRIGGER] 注入 Current_Dep=10.0, Depth_Para1=5, 连续触发 EmergencyTask")
    sh.write_u16(ex, 0)
    sh.write_u16(ui + offsets.ui_depth_para1, 5)
    sh.write_u32(current + offsets.current_depth, 0x41200000)
    for idx in range(cycles):
        sh.cmd("semGive(semEmergencyTask)", wait=0.18)
        print(f"  semGive #{idx + 1}/{cycles}")


def _shadow_override(sh: VxShell, symbols: dict[str, int | None], offsets: Offsets) -> None:
    ui = _require(symbols, "UI_WIFI_Instruction")
    channel = symbols.get("UI_Channel_Selection_Down")

    print("\n[SHADOW] 运行时写 UI shadow, 再调用 Remote_Assignment(&Instruction_To_FMCU)")
    if channel:
        sh.write_u8(channel, 0x02)
    sh.write_u16(ui + offsets.ui_motor1, 300)
    sh.write_s16(ui + offsets.ui_lh_angle, -20)
    sh.write_s16(ui + offsets.ui_rh_angle, -20)
    sh.cmd("Remote_Assignment(&Instruction_To_FMCU)", wait=0.45)


def _require(symbols: dict[str, int | None], name: str) -> int:
    addr = symbols.get(name)
    if not addr:
        raise RuntimeError(f"required symbol not found: {name}")
    return addr


def _snapshot_runtime(sh: VxShell, symbols: dict[str, int | None], offsets: Offsets) -> dict[str, int]:
    """Capture a small set of values touched by the intrusive probe."""
    snap: dict[str, int] = {}
    current = symbols.get("Current_State")
    ui = symbols.get("UI_WIFI_Instruction")
    channel = symbols.get("UI_Channel_Selection_Down")
    ex = symbols.get("Depth_Exceed_FromUI12_Depth_Para1")

    if current:
        value = sh.read_u32(current + offsets.current_depth)
        if value is not None:
            snap["current_depth_raw"] = value
    if ui:
        fields = {
            "ui_depth_para1": sh.read_u16(ui + offsets.ui_depth_para1),
            "ui_motor1": sh.read_s16(ui + offsets.ui_motor1),
            "ui_lh_angle": sh.read_s16(ui + offsets.ui_lh_angle),
            "ui_rh_angle": sh.read_s16(ui + offsets.ui_rh_angle),
        }
        for name, value in fields.items():
            if value is not None:
                snap[name] = value
    if channel:
        value = sh.read_u8(channel)
        if value is not None:
            snap["channel"] = value
    if ex:
        value = sh.read_u16(ex)
        if value is not None:
            snap["depth_exceed"] = value
    return snap


def _restore_runtime(sh: VxShell, symbols: dict[str, int | None], offsets: Offsets, snap: dict[str, int]) -> None:
    """Best-effort restore after an intrusive probe."""
    current = symbols.get("Current_State")
    ui = symbols.get("UI_WIFI_Instruction")
    channel = symbols.get("UI_Channel_Selection_Down")
    ex = symbols.get("Depth_Exceed_FromUI12_Depth_Para1")

    print("\n[CLEANUP] best-effort restore touched runtime values")
    if current and "current_depth_raw" in snap:
        sh.write_u32(current + offsets.current_depth, snap["current_depth_raw"])
    if ui:
        if "ui_depth_para1" in snap:
            sh.write_u16(ui + offsets.ui_depth_para1, snap["ui_depth_para1"])
        if "ui_motor1" in snap:
            sh.write_u16(ui + offsets.ui_motor1, snap["ui_motor1"] & 0xFFFF)
        if "ui_lh_angle" in snap:
            sh.write_s16(ui + offsets.ui_lh_angle, snap["ui_lh_angle"])
        if "ui_rh_angle" in snap:
            sh.write_s16(ui + offsets.ui_rh_angle, snap["ui_rh_angle"])
    if channel and "channel" in snap:
        sh.write_u8(channel, snap["channel"])
    if ex and "depth_exceed" in snap:
        sh.write_u16(ex, snap["depth_exceed"])


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Runtime-only BUG-4 Telnet probe for PC104 VxWorks")
    parser.add_argument("--host", default=DEFAULT_HOST, help=f"VxWorks host (default: {DEFAULT_HOST})")
    parser.add_argument("--port", type=int, default=23, help="Telnet port (default: 23)")
    parser.add_argument("--user", default="target", help="Telnet username (default: target)")
    parser.add_argument("--password", default="password", help="Telnet password (default: password)")
    parser.add_argument("--timeout", type=float, default=5.0, help="Telnet timeout seconds")
    parser.add_argument(
        "--probe",
        choices=["trigger-bug4", "shadow-override", "both"],
        default="both",
        help="Probe to run when --execute is set",
    )
    parser.add_argument("--execute", action="store_true", help="Actually write runtime values and trigger semEmergencyTask")
    parser.add_argument("--no-suspend-main", action="store_true", help="Do not suspend MainCtrlTask during trigger-bug4")
    parser.add_argument("--cycles", type=int, default=13, help="EmergencyTask trigger cycles for BUG-4")
    parser.add_argument("--current-depth-offset", type=lambda x: int(x, 0), default=Offsets.current_depth)
    parser.add_argument("--ui-depth-para1-offset", type=lambda x: int(x, 0), default=Offsets.ui_depth_para1)
    parser.add_argument("--ui-motor1-offset", type=lambda x: int(x, 0), default=Offsets.ui_motor1)
    parser.add_argument("--ui-lh-angle-offset", type=lambda x: int(x, 0), default=Offsets.ui_lh_angle)
    parser.add_argument("--ui-rh-angle-offset", type=lambda x: int(x, 0), default=Offsets.ui_rh_angle)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    offsets = Offsets(
        current_depth=args.current_depth_offset,
        ui_depth_para1=args.ui_depth_para1_offset,
        ui_motor1=args.ui_motor1_offset,
        ui_lh_angle=args.ui_lh_angle_offset,
        ui_rh_angle=args.ui_rh_angle_offset,
    )

    sh = VxShell(args.host, args.port, args.user, args.password, args.timeout)
    try:
        sh.connect()
        names = [
            "Current_State",
            "UI_WIFI_Instruction",
            "UI_LORA_Instruction",
            "UI_Channel_Selection_Down",
            "Instruction_To_FMCU",
            "Sys_Abnorm_Inf_Judgement",
            "Depth_Exceed_FromUI12_Depth_Para1",
            "to_MCU_buf",
        ]
        symbols = {name: sh.lkup(name) for name in names}
        print("[SYMBOLS]")
        for name, addr in symbols.items():
            print(f"  {name:36s} {('NA' if addr is None else hex(addr))}")

        _read_observables(sh, symbols, offsets, "BASELINE")
        if not args.execute:
            _print_commands(symbols, offsets)
            return 0

        snap = _snapshot_runtime(sh, symbols, offsets)
        main_suspended = False
        try:
            if args.probe in ("trigger-bug4", "both"):
                main_suspended = not args.no_suspend_main
                _trigger_bug4(sh, symbols, offsets, args.cycles, suspend=main_suspended)
                _read_observables(sh, symbols, offsets, "AFTER TRIGGER-BUG4")

            if args.probe in ("shadow-override", "both"):
                _shadow_override(sh, symbols, offsets)
                _read_observables(sh, symbols, offsets, "AFTER SHADOW-OVERRIDE")
        finally:
            _restore_runtime(sh, symbols, offsets, snap)
            if main_suspended:
                print("\n[RESUME] taskResume(MainCtrlTask)")
                sh.cmd('taskResume(taskNameToId("MainCtrlTask"))', wait=0.35)

        return 0
    finally:
        sh.close()


if __name__ == "__main__":
    sys.exit(main())

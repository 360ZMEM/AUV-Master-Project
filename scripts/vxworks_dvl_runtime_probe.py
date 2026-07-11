#!/usr/bin/env python3
"""Runtime DVL grounding arbitration probe for the current PC104 image.

/**
 * @file    vxworks_dvl_runtime_probe.py
 * @brief   PC104/VxWorks DVL soft-limit, hard-limit and lost-bottom probe.
 * @date    2026-07-11
 * @author  清华 AUV 课题组
 *
 * The VxWorks shell in this target is fragile with struct expressions, so this
 * helper resolves exported symbols first, writes absolute addresses, and keeps
 * every shell command short. By default it is read-only; pass --execute to run
 * intrusive HIL injections.
 */
"""

from __future__ import annotations

import argparse
import re
import socket
import struct
import sys
import telnetlib
import time
from dataclasses import dataclass


DEFAULT_HOST = "192.168.0.101"
UPLINK_HEADER = bytes((0x24, 0x41, 0x55, 0x56, 0x91))
FRAME_TAIL = b"\xff\xff"
UPLINK_SIZE = 145
RUNTIME_TASKS = (
    "MainCtrlTask",
    "UartRecvFormDVLTask",
    "UnpackDVLDataTask",
    "NetRecvTask",
    "UnpackNetDataTask",
)


@dataclass(frozen=True)
class Offsets:
    """Runtime offsets observed or derived for the current PC104 image."""

    current_mode: int = 0x02
    current_depth: int = 0x34
    current_pitch: int = 0x6C
    current_dvl_velocity_kn: int = 0x7C

    ui_ctrl_mode: int = 0x07
    ui_depth_para1: int = 0x08

    dvl_bd_height: int = 0x18
    dvl_bd_check: int = 0x20

    ins_motor1: int = 0x18
    ins_lh_rudder: int = 0x20
    ins_rh_rudder: int = 0x22


class VxShell:
    """Tiny Telnet wrapper for short VxWorks shell commands."""

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
        try:
            return self.tn.read_until(b"->", timeout=max(wait, 1.0)).decode("ascii", errors="replace")
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
        value = _first_int(self.cmd(f'printf("V=%u\\n", *(unsigned char*)0x{addr:x})'))
        return None if value is None else value & 0xFF

    def read_u16(self, addr: int) -> int | None:
        return _first_int(self.cmd(f'printf("V=%u\\n", *(unsigned short*)0x{addr:x})'))

    def read_s16(self, addr: int) -> int | None:
        return _first_int(self.cmd(f'printf("V=%d\\n", *(short*)0x{addr:x})'))

    def read_u32(self, addr: int) -> int | None:
        return _first_hex_or_int(self.cmd(f'printf("V=0x%08x\\n", *(unsigned int*)0x{addr:x})'))

    def read_float(self, addr: int) -> float | None:
        raw = self.read_u32(addr)
        return None if raw is None else _u32_to_float(raw)

    def write_u8(self, addr: int, value: int) -> None:
        self.cmd(f"*(unsigned char*)0x{addr:x}={value & 0xFF}")

    def write_u16(self, addr: int, value: int) -> None:
        self.cmd(f"*(unsigned short*)0x{addr:x}={value & 0xFFFF}")

    def write_s16(self, addr: int, value: int) -> None:
        self.cmd(f"*(short*)0x{addr:x}={int(value)}")

    def write_u32(self, addr: int, value: int) -> None:
        self.cmd(f"*(unsigned int*)0x{addr:x}=0x{value & 0xFFFFFFFF:08x}")

    def write_float(self, addr: int, value: float) -> None:
        self.write_u32(addr, struct.unpack(">I", struct.pack(">f", float(value)))[0])


def _first_int(text: str) -> int | None:
    match = re.search(r"V=(-?\d+)", text)
    return None if not match else int(match.group(1))


def _first_hex_or_int(text: str) -> int | None:
    match = re.search(r"V=(0x[0-9a-fA-F]+|-?\d+)", text)
    if not match:
        return None
    raw = match.group(1)
    return int(raw, 16) if raw.startswith("0x") else int(raw)


def _u32_to_float(value: int) -> float:
    return struct.unpack(">f", (value & 0xFFFFFFFF).to_bytes(4, "big"))[0]


def _fmt(value: int | float | None) -> str:
    if value is None:
        return "NA"
    if isinstance(value, float):
        return f"{value:.3f}"
    return str(value)


def _fmt_hex(value: int | None) -> str:
    return "NA" if value is None else f"0x{value:08x}"


def parse_uplink(packet: bytes) -> dict[str, int | float] | None:
    if len(packet) != UPLINK_SIZE or packet[:5] != UPLINK_HEADER or packet[143:145] != FRAME_TAIL:
        return None
    if packet[142] != (sum(packet[:142]) & 0xFF):
        return None
    return {
        "ctrl_mode": packet[7],
        "motor1": struct.unpack(">h", packet[23:25])[0],
        "depth_m": struct.unpack(">H", packet[38:40])[0] * 0.1,
        "altitude_m": struct.unpack(">H", packet[84:86])[0] * 0.1,
        "sys": struct.unpack(">I", packet[126:130])[0],
    }


class UplinkCapture:
    def __init__(self, enabled: bool, bind_host: str, bind_port: int):
        self.enabled = enabled
        self.sock: socket.socket | None = None
        if enabled:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.sock.bind((bind_host, bind_port))
            self.sock.setblocking(False)

    def close(self) -> None:
        if self.sock:
            self.sock.close()
            self.sock = None

    def sample(self, duration: float = 1.2) -> dict[str, int | float] | None:
        if not self.sock:
            return None
        deadline = time.time() + duration
        last = None
        while time.time() < deadline:
            try:
                data, _addr = self.sock.recvfrom(2048)
            except BlockingIOError:
                time.sleep(0.05)
                continue
            parsed = parse_uplink(data)
            if parsed:
                last = parsed
        return last


def _require(symbols: dict[str, int | None], name: str) -> int:
    addr = symbols.get(name)
    if not addr:
        raise RuntimeError(f"required symbol not found: {name}")
    return addr


def _snapshot(sh: VxShell, symbols: dict[str, int | None], offsets: Offsets) -> dict[str, int]:
    snap: dict[str, int] = {}
    current = symbols.get("Current_State")
    ui = symbols.get("UI_WIFI_Instruction")
    dvl = symbols.get("DVL_Prase_Data")
    sys_abn = symbols.get("Sys_Abnorm_Inf_Judgement")

    if sys_abn:
        value = sh.read_u32(sys_abn)
        if value is not None:
            snap["sys"] = value
    if current:
        for key, off in (
            ("current_mode", offsets.current_mode),
            ("current_depth", offsets.current_depth),
            ("current_pitch", offsets.current_pitch),
            ("current_dvl_velocity_kn", offsets.current_dvl_velocity_kn),
        ):
            value = sh.read_u32(current + off) if key != "current_mode" else sh.read_u8(current + off)
            if value is not None:
                snap[key] = value
    if ui:
        for key, off in (("ui_ctrl", offsets.ui_ctrl_mode), ("ui_para1", offsets.ui_depth_para1)):
            value = sh.read_u16(ui + off) if key == "ui_para1" else sh.read_u8(ui + off)
            if value is not None:
                snap[key] = value
    if dvl:
        for key, off in (("dvl_height", offsets.dvl_bd_height), ("dvl_check", offsets.dvl_bd_check)):
            value = sh.read_u32(dvl + off)
            if value is not None:
                snap[key] = value
    return snap


def _restore(sh: VxShell, symbols: dict[str, int | None], offsets: Offsets, snap: dict[str, int]) -> None:
    print("\n[CLEANUP] best-effort restore touched runtime values")
    current = symbols.get("Current_State")
    ui = symbols.get("UI_WIFI_Instruction")
    dvl = symbols.get("DVL_Prase_Data")
    sys_abn = symbols.get("Sys_Abnorm_Inf_Judgement")

    if sys_abn and "sys" in snap:
        sh.write_u32(sys_abn, snap["sys"])
    if current:
        if "current_mode" in snap:
            sh.write_u8(current + offsets.current_mode, snap["current_mode"])
        for key, off in (
            ("current_depth", offsets.current_depth),
            ("current_pitch", offsets.current_pitch),
            ("current_dvl_velocity_kn", offsets.current_dvl_velocity_kn),
        ):
            if key in snap:
                sh.write_u32(current + off, snap[key])
    if ui:
        if "ui_ctrl" in snap:
            sh.write_u8(ui + offsets.ui_ctrl_mode, snap["ui_ctrl"])
        if "ui_para1" in snap:
            sh.write_u16(ui + offsets.ui_depth_para1, snap["ui_para1"])
    if dvl:
        if "dvl_height" in snap:
            sh.write_u32(dvl + offsets.dvl_bd_height, snap["dvl_height"])
        if "dvl_check" in snap:
            sh.write_u32(dvl + offsets.dvl_bd_check, snap["dvl_check"])


def _clear_dvl_bits(sh: VxShell, symbols: dict[str, int | None]) -> None:
    sys_abn = _require(symbols, "Sys_Abnorm_Inf_Judgement")
    value = sh.read_u32(sys_abn)
    if value is not None:
        sh.write_u32(sys_abn, value & ~0x00003800)


def _prepare_common(sh: VxShell, symbols: dict[str, int | None], offsets: Offsets) -> None:
    current = _require(symbols, "Current_State")
    ui = _require(symbols, "UI_WIFI_Instruction")
    sh.write_u8(current + offsets.current_mode, 0xEE)
    sh.write_u8(ui + offsets.ui_ctrl_mode, 0xEE)
    sh.write_float(current + offsets.current_depth, 15.0)
    sh.write_float(current + offsets.current_pitch, 0.0)
    sh.write_float(current + offsets.current_dvl_velocity_kn, 3.0)


def _call_arbiter(sh: VxShell, cycles: int, wait: float) -> None:
    for idx in range(cycles):
        out = sh.cmd("Seafloor_Grounding_Arbitration()", wait=wait)
        if idx == 0 and "undefined" in out.lower():
            raise RuntimeError("Seafloor_Grounding_Arbitration() was not callable from shell")


def _clean_counters(sh: VxShell, symbols: dict[str, int | None], offsets: Offsets, cycles: int) -> None:
    dvl = _require(symbols, "DVL_Prase_Data")
    sh.write_float(dvl + offsets.dvl_bd_check, 2.0)
    sh.write_float(dvl + offsets.dvl_bd_height, 5.0)
    _call_arbiter(sh, cycles, 0.08)
    _clear_dvl_bits(sh, symbols)


def _read_observables(
    sh: VxShell,
    symbols: dict[str, int | None],
    offsets: Offsets,
    title: str,
    uplink: UplinkCapture,
) -> None:
    current = symbols.get("Current_State")
    ui = symbols.get("UI_WIFI_Instruction")
    dvl = symbols.get("DVL_Prase_Data")
    ins = symbols.get("Instruction_To_FMCU")
    sys_abn = symbols.get("Sys_Abnorm_Inf_Judgement")

    print(f"\n[{title}]")
    sys_val = sh.read_u32(sys_abn) if sys_abn else None
    print(f"  Sys_Abnorm={_fmt_hex(sys_val)}")
    if dvl:
        print(
            "  DVL:"
            f" BD_Check={_fmt(sh.read_float(dvl + offsets.dvl_bd_check))}"
            f" BD_Height={_fmt(sh.read_float(dvl + offsets.dvl_bd_height))}"
        )
    if current:
        print(
            "  Current_State:"
            f" mode={_fmt(sh.read_u8(current + offsets.current_mode))}"
            f" dep={_fmt(sh.read_float(current + offsets.current_depth))}"
            f" pitch={_fmt(sh.read_float(current + offsets.current_pitch))}"
            f" dvl_kn={_fmt(sh.read_float(current + offsets.current_dvl_velocity_kn))}"
        )
    if ui:
        print(
            "  UI_WIFI:"
            f" ctrl={_fmt(sh.read_u8(ui + offsets.ui_ctrl_mode))}"
            f" para1={_fmt(sh.read_u16(ui + offsets.ui_depth_para1))}"
        )
    if ins:
        print(
            "  Instruction_To_FMCU:"
            f" motor1={_fmt(sh.read_s16(ins + offsets.ins_motor1))}"
            f" lh={_fmt(sh.read_u16(ins + offsets.ins_lh_rudder))}"
            f" rh={_fmt(sh.read_u16(ins + offsets.ins_rh_rudder))}"
        )
    sample = uplink.sample() if uplink.enabled else None
    if sample:
        print(
            "  $AUV:"
            f" ctrl=0x{int(sample['ctrl_mode']):02x}"
            f" motor1={sample['motor1']}"
            f" depth={sample['depth_m']:.1f}m"
            f" altitude={sample['altitude_m']:.1f}m"
            f" sys=0x{int(sample['sys']):08x}"
        )


def _run_soft(sh: VxShell, symbols: dict[str, int | None], offsets: Offsets, uplink: UplinkCapture) -> None:
    print("\n[CASE soft] valid lock, BD_Height=2.5m, expect Bit11")
    dvl = _require(symbols, "DVL_Prase_Data")
    _clean_counters(sh, symbols, offsets, 8)
    _prepare_common(sh, symbols, offsets)
    sh.write_float(dvl + offsets.dvl_bd_check, 2.0)
    sh.write_float(dvl + offsets.dvl_bd_height, 2.5)
    _call_arbiter(sh, 6, 0.10)
    _read_observables(sh, symbols, offsets, "AFTER SOFT", uplink)


def _run_hard(sh: VxShell, symbols: dict[str, int | None], offsets: Offsets, uplink: UplinkCapture) -> None:
    print("\n[CASE hard] valid lock, BD_Height=1.2m, expect Bit12 and Motor1=350")
    dvl = _require(symbols, "DVL_Prase_Data")
    _clean_counters(sh, symbols, offsets, 8)
    _prepare_common(sh, symbols, offsets)
    sh.write_float(dvl + offsets.dvl_bd_check, 2.0)
    sh.write_float(dvl + offsets.dvl_bd_height, 1.2)
    _call_arbiter(sh, 4, 0.10)
    _read_observables(sh, symbols, offsets, "AFTER HARD", uplink)


def _run_lost(sh: VxShell, symbols: dict[str, int | None], offsets: Offsets, uplink: UplinkCapture) -> None:
    print("\n[CASE lost] invalid lock for 21 cycles, expect Bit13, UI ctrl=0x01, Motor1=300")
    dvl = _require(symbols, "DVL_Prase_Data")
    _clean_counters(sh, symbols, offsets, 8)
    _prepare_common(sh, symbols, offsets)
    sh.write_float(dvl + offsets.dvl_bd_check, 0.0)
    sh.write_float(dvl + offsets.dvl_bd_height, 5.0)
    _call_arbiter(sh, 21, 0.08)
    _read_observables(sh, symbols, offsets, "AFTER LOST", uplink)


def _print_dry_run(symbols: dict[str, int | None], offsets: Offsets) -> None:
    print("\n[DRY-RUN] 未使用 --execute, 不会写入板上内存。")
    dvl = symbols.get("DVL_Prase_Data")
    current = symbols.get("Current_State")
    ui = symbols.get("UI_WIFI_Instruction")
    if dvl:
        print(f"  DVL_Prase_Data.BD_Height  -> 0x{dvl + offsets.dvl_bd_height:x}")
        print(f"  DVL_Prase_Data.BD_Check   -> 0x{dvl + offsets.dvl_bd_check:x}")
    if current:
        print(f"  Current_State.Current_Mode -> 0x{current + offsets.current_mode:x}")
        print(f"  Current_State.Current_Dep  -> 0x{current + offsets.current_depth:x}")
    if ui:
        print(f"  UI_WIFI ctrl/DepthPara1    -> 0x{ui + offsets.ui_ctrl_mode:x} / 0x{ui + offsets.ui_depth_para1:x}")
    print("  执行示例: /usr/bin/python3 scripts/vxworks_dvl_runtime_probe.py --execute --case soft --suspend-runtime-tasks")


def _suspend_tasks(sh: VxShell, task_names: tuple[str, ...]) -> list[str]:
    suspended: list[str] = []
    for name in task_names:
        print(f"[SUSPEND] taskSuspend({name})")
        out = sh.cmd(f'taskSuspend(taskNameToId("{name}"))', wait=0.25)
        if "value = 0" in out:
            suspended.append(name)
        else:
            print(f"  WARN: suspend may have failed for {name}: {out.strip()}")
    return suspended


def _resume_tasks(sh: VxShell, task_names: list[str]) -> None:
    for name in reversed(task_names):
        print(f"[RESUME] taskResume({name})")
        sh.cmd(f'taskResume(taskNameToId("{name}"))', wait=0.25)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Runtime DVL arbitration probe for PC104 VxWorks")
    parser.add_argument("--host", default=DEFAULT_HOST, help=f"VxWorks host (default: {DEFAULT_HOST})")
    parser.add_argument("--port", type=int, default=23, help="Telnet port (default: 23)")
    parser.add_argument("--user", default="target", help="Telnet username (default: target)")
    parser.add_argument("--password", default="password", help="Telnet password (default: password)")
    parser.add_argument("--timeout", type=float, default=5.0, help="Telnet timeout seconds")
    parser.add_argument("--execute", action="store_true", help="Actually write runtime values and call the arbiter")
    parser.add_argument("--case", choices=["soft", "hard", "lost", "all"], default="all", help="Probe case")
    parser.add_argument("--suspend-main", action="store_true", help="Suspend MainCtrlTask while probing")
    parser.add_argument(
        "--suspend-runtime-tasks",
        action="store_true",
        help="Suspend MainCtrlTask plus DVL and Net receive/unpack tasks while probing",
    )
    parser.add_argument("--capture-uplink", action="store_true", help="Also bind UDP and sample $AUV uplink frames")
    parser.add_argument("--bind-host", default="0.0.0.0", help="UDP bind host for --capture-uplink")
    parser.add_argument("--bind-port", type=int, default=21, help="UDP bind port for --capture-uplink")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    offsets = Offsets()
    uplink = UplinkCapture(args.capture_uplink, args.bind_host, args.bind_port)
    sh = VxShell(args.host, args.port, args.user, args.password, args.timeout)
    try:
        sh.connect()
        names = [
            "DVL_Prase_Data",
            "Current_State",
            "UI_WIFI_Instruction",
            "Instruction_To_FMCU",
            "Sys_Abnorm_Inf_Judgement",
            "Seafloor_Grounding_Arbitration",
        ]
        symbols = {name: sh.lkup(name) for name in names}
        print("[SYMBOLS]")
        for name, addr in symbols.items():
            print(f"  {name:36s} {('NA' if addr is None else hex(addr))}")

        _read_observables(sh, symbols, offsets, "BASELINE", uplink)
        if not args.execute:
            _print_dry_run(symbols, offsets)
            return 0

        snap = _snapshot(sh, symbols, offsets)
        suspended_tasks: list[str] = []
        try:
            if args.suspend_runtime_tasks:
                suspended_tasks = _suspend_tasks(sh, RUNTIME_TASKS)
            elif args.suspend_main:
                suspended_tasks = _suspend_tasks(sh, ("MainCtrlTask",))

            if args.case in ("soft", "all"):
                _run_soft(sh, symbols, offsets, uplink)
            if args.case in ("hard", "all"):
                _run_hard(sh, symbols, offsets, uplink)
            if args.case in ("lost", "all"):
                _run_lost(sh, symbols, offsets, uplink)
        finally:
            _restore(sh, symbols, offsets, snap)
            _resume_tasks(sh, suspended_tasks)

        return 0
    finally:
        sh.close()
        uplink.close()


if __name__ == "__main__":
    sys.exit(main())

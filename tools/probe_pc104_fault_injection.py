#!/usr/bin/env python3
"""Safe PC104/VxWorks fault-injection probe for thesis hardware evidence.

The probe uses a VxWorks telnet shell to isolate and inject runtime fault
conditions while every UDP command remains a zero-actuator command. It records
the complete host-side event timeline and the board-side watchdog, mode, fault,
and actuator state. The default mode is read-only; ``--execute`` is required
before any board memory is changed.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import heapq
import json
import math
import random
import re
import select
import socket
import struct
import sys
import telnetlib
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from common.protocol import (  # noqa: E402
    build_downlink_packet,
    parse_downlink_packet,
    parse_uplink_packet,
)
from tools.experiment_contract import finalize_bundle, initialize_bundle  # noqa: E402


BIT_SYSTEM_COMMUNICATION = 5
BIT_DVL_LOST = 13
BIT_JETSON_TIMEOUT = 14
REMOTE_MODE = 0x01
JETSON_MODE = 0xEE


@dataclass(frozen=True)
class Offsets:
    """Offsets verified against the current 32-bit VxWorks image."""

    current_mode: int = 0x02
    ui_ctrl_mode: int = 0x07
    ui_motor1: int = 0x17
    ui_motor2: int = 0x19
    ui_fin_lh: int = 0x1B
    ui_fin_rh: int = 0x1D
    ui_fin_uv: int = 0x1F
    ui_fin_lv: int = 0x21
    instruction_motor1: int = 0x18
    instruction_motor2: int = 0x1A
    dvl_bd_height: int = 0x18
    dvl_bd_check: int = 0x20
    fmcu_sys_abnorm: int = 0x24


@dataclass(frozen=True)
class Phase:
    name: str
    duration_s: float
    control_mode: int | None
    drop_rate: float = 0.0
    delay_ms: float = 0.0
    injection: str = ""
    trial: int = 0


@dataclass(frozen=True)
class BoardSymbols:
    watchdog: int
    sys_abnorm: int
    current_state: int
    ui_instruction: int
    fmcu_instruction: int
    dvl_data: int
    fmcu_feedback: int


class VxShell:
    """Minimal prompt-synchronized VxWorks telnet shell."""

    def __init__(
        self,
        host: str,
        port: int,
        username: str,
        password: str,
        timeout_s: float,
    ) -> None:
        self.host = host
        self.port = int(port)
        self.username = username
        self.password = password
        self.timeout_s = float(timeout_s)
        self._tn: telnetlib.Telnet | None = None

    def connect(self) -> None:
        self._tn = telnetlib.Telnet(self.host, self.port, self.timeout_s)
        banner = self._tn.read_until(b"->", timeout=1.0)
        if b"->" in banner:
            return
        if b"login" in banner.lower() or b"username" in banner.lower():
            self._tn.write((self.username + "\n").encode("ascii"))
            banner += self._tn.read_until(b"assword", timeout=self.timeout_s)
        if b"assword" in banner.lower():
            self._tn.write((self.password + "\n").encode("ascii"))
        prompt = self._tn.read_until(b"->", timeout=self.timeout_s)
        if b"->" not in prompt:
            raise RuntimeError("VxWorks telnet shell prompt was not observed")

    def close(self) -> None:
        if self._tn is not None:
            self._tn.close()
            self._tn = None

    def command(self, command: str) -> str:
        if self._tn is None:
            raise RuntimeError("telnet shell is not connected")
        self._tn.write((command + "\n").encode("ascii"))
        output = self._tn.read_until(b"->", timeout=self.timeout_s)
        text = output.decode("ascii", errors="replace")
        if "C interp: syntax error" in text or "undefined symbol" in text.lower():
            raise RuntimeError(f"VxWorks shell command failed: {command!r}: {text!r}")
        return text

    def lookup(self, name: str) -> int:
        text = self.command(f'lkup "{name}"')
        for line in text.splitlines():
            parts = line.split()
            if (
                len(parts) >= 2
                and parts[0] == name
                and re.fullmatch(r"0x[0-9a-fA-F]+", parts[1])
            ):
                return int(parts[1], 16)
        matches = re.findall(r"0x[0-9a-fA-F]+", text)
        if not matches:
            raise RuntimeError(f"required VxWorks symbol not found: {name}")
        return int(matches[0], 16)

    def read_u16(self, address: int) -> int:
        text = self.command(
            f'printf("V=%u\\n",*(unsigned short*)0x{address:x})'
        )
        match = re.search(r"V=(\d+)", text)
        if not match:
            raise RuntimeError(f"cannot read u16 at 0x{address:x}: {text!r}")
        return int(match.group(1))

    def read_u32(self, address: int) -> int:
        text = self.command(
            f'printf("V=0x%08x\\n",*(unsigned int*)0x{address:x})'
        )
        match = re.search(r"V=(0x[0-9a-fA-F]+)", text)
        if not match:
            raise RuntimeError(f"cannot read u32 at 0x{address:x}: {text!r}")
        return int(match.group(1), 16)

    def write_u8(self, address: int, value: int) -> None:
        self.command(f"*(unsigned char*)0x{address:x}={int(value) & 0xFF}")

    def write_u16(self, address: int, value: int) -> None:
        self.command(f"*(unsigned short*)0x{address:x}={int(value) & 0xFFFF}")

    def write_s16(self, address: int, value: int) -> None:
        self.command(f"*(short*)0x{address:x}={int(value)}")

    def write_u32(self, address: int, value: int) -> None:
        self.command(
            f"*(unsigned int*)0x{address:x}=0x{int(value) & 0xFFFFFFFF:08x}"
        )

    def write_float(self, address: int, value: float) -> None:
        bits = struct.unpack(">I", struct.pack(">f", float(value)))[0]
        self.write_u32(address, bits)

    def read_snapshot(
        self,
        symbols: BoardSymbols,
        offsets: Offsets,
    ) -> dict[str, int | float]:
        first = self.command(
            'printf("V1,%lu,%u,%08x,%u,%u\\n",'
            f"tickGet(),*(unsigned short*)0x{symbols.watchdog:x},"
            f"*(unsigned int*)0x{symbols.sys_abnorm:x},"
            f"*(unsigned char*)0x{symbols.current_state + offsets.current_mode:x},"
            f"*(unsigned char*)0x{symbols.ui_instruction + offsets.ui_ctrl_mode:x})"
        )
        second = self.command(
            'printf("V2,%d,%d,%d,%d,%08x,%08x,%08x\\n",'
            f"*(short*)0x{symbols.ui_instruction + offsets.ui_motor1:x},"
            f"*(short*)0x{symbols.ui_instruction + offsets.ui_motor2:x},"
            f"*(short*)0x{symbols.fmcu_instruction + offsets.instruction_motor1:x},"
            f"*(short*)0x{symbols.fmcu_instruction + offsets.instruction_motor2:x},"
            f"*(unsigned int*)0x{symbols.dvl_data + offsets.dvl_bd_check:x},"
            f"*(unsigned int*)0x{symbols.dvl_data + offsets.dvl_bd_height:x},"
            f"*(unsigned int*)0x{symbols.fmcu_feedback + offsets.fmcu_sys_abnorm:x})"
        )
        third = self.command(
            'printf("V3,%d,%d,%d,%d\\n",'
            f"*(short*)0x{symbols.ui_instruction + offsets.ui_fin_lh:x},"
            f"*(short*)0x{symbols.ui_instruction + offsets.ui_fin_rh:x},"
            f"*(short*)0x{symbols.ui_instruction + offsets.ui_fin_uv:x},"
            f"*(short*)0x{symbols.ui_instruction + offsets.ui_fin_lv:x})"
        )
        first_match = re.search(
            r"V1,(\d+),(\d+),([0-9a-fA-F]+),(\d+),(\d+)",
            first,
        )
        second_match = re.search(
            r"V2,(-?\d+),(-?\d+),(-?\d+),(-?\d+),"
            r"([0-9a-fA-F]+),([0-9a-fA-F]+),([0-9a-fA-F]+)",
            second,
        )
        third_match = re.search(
            r"V3,(-?\d+),(-?\d+),(-?\d+),(-?\d+)",
            third,
        )
        if not first_match or not second_match or not third_match:
            raise RuntimeError(
                "cannot parse VxWorks snapshot: "
                f"{first!r} / {second!r} / {third!r}"
            )
        dvl_check_bits = int(second_match.group(5), 16)
        dvl_height_bits = int(second_match.group(6), 16)
        return {
            "pc104_tick": int(first_match.group(1)),
            "watchdog_count": int(first_match.group(2)),
            "telnet_sys_abnorm": int(first_match.group(3), 16),
            "telnet_current_mode": int(first_match.group(4)) & 0xFF,
            "telnet_ui_mode": int(first_match.group(5)) & 0xFF,
            "telnet_ui_motor1": int(second_match.group(1)),
            "telnet_ui_motor2": int(second_match.group(2)),
            "telnet_ui_fin_lh": int(third_match.group(1)),
            "telnet_ui_fin_rh": int(third_match.group(2)),
            "telnet_ui_fin_uv": int(third_match.group(3)),
            "telnet_ui_fin_lv": int(third_match.group(4)),
            "telnet_instruction_motor1": int(second_match.group(3)),
            "telnet_instruction_motor2": int(second_match.group(4)),
            "telnet_dvl_check": _u32_to_float(dvl_check_bits),
            "telnet_dvl_height_m": _u32_to_float(dvl_height_bits),
            "telnet_fmcu_sys_abnorm": int(second_match.group(7), 16),
        }


def _u32_to_float(value: int) -> float:
    return struct.unpack(">f", int(value & 0xFFFFFFFF).to_bytes(4, "big"))[0]


def percentile(values: list[float], quantile: float) -> float:
    finite = sorted(value for value in values if math.isfinite(value))
    if not finite:
        return float("nan")
    index = round((len(finite) - 1) * quantile)
    return float(finite[max(0, min(len(finite) - 1, index))])


def utc_now() -> str:
    return dt.datetime.now(tz=dt.timezone.utc).isoformat()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--remote-host", default="192.168.65.254")
    parser.add_argument("--remote-port", type=int, default=10022)
    parser.add_argument("--local-host", default="0.0.0.0")
    parser.add_argument("--local-port", type=int, default=21)
    parser.add_argument("--telnet-host", default="192.168.0.101")
    parser.add_argument("--telnet-port", type=int, default=23)
    parser.add_argument("--telnet-user", default="target")
    parser.add_argument("--telnet-password", default="password")
    parser.add_argument("--send-rate-hz", type=float, default=10.0)
    parser.add_argument("--monitor-rate-hz", type=float, default=5.0)
    parser.add_argument("--natural-trials", type=int, default=5)
    parser.add_argument("--forced-timeout-trials", type=int, default=3)
    parser.add_argument("--loss-rate", type=float, default=0.30)
    parser.add_argument("--loss-duration-s", type=float, default=10.0)
    parser.add_argument("--delay-ms", type=float, default=200.0)
    parser.add_argument("--delay-duration-s", type=float, default=10.0)
    parser.add_argument("--seed", type=int, default=20260822)
    parser.add_argument("--output-dir", type=Path, default=None)
    return parser.parse_args()


def resolve_symbols(shell: VxShell) -> BoardSymbols:
    return BoardSymbols(
        watchdog=shell.lookup("Not_Recv_From_Jetson_No"),
        sys_abnorm=shell.lookup("Sys_Abnorm_Inf_Judgement"),
        current_state=shell.lookup("Current_State"),
        ui_instruction=shell.lookup("UI_WIFI_Instruction"),
        fmcu_instruction=shell.lookup("Instruction_To_FMCU"),
        dvl_data=shell.lookup("DVL_Prase_Data"),
        fmcu_feedback=shell.lookup("Data_From_FMCU"),
    )


def build_zero_packet(frame_number: int, control_mode: int) -> bytes:
    packet = build_downlink_packet(
        [0.0, 0.0, 0.0, 0.0, 0.0],
        frame_counter=frame_number,
        obj_address=1,
        control_mode_byte=control_mode,
        work_instruction=0,
        main_motor_rpm_scale=15.0,
        side_motor_rpm=0,
    )
    decoded = parse_downlink_packet(packet)
    actuators = (
        decoded.main_motor_rpm,
        decoded.side_motor_rpm,
        decoded.left_fin_deg,
        decoded.right_fin_deg,
        decoded.top_fin_deg,
        decoded.bottom_fin_deg,
    )
    if any(abs(float(value)) > 1.0e-9 for value in actuators):
        raise RuntimeError(f"non-zero downlink generated: {actuators}")
    return packet


def build_phases(args: argparse.Namespace) -> list[Phase]:
    phases = [
        Phase("remote_baseline", 2.0, REMOTE_MODE),
        Phase("dvl_safe_settle", 1.0, REMOTE_MODE),
        Phase("heartbeat_steady", 4.0, JETSON_MODE),
    ]
    for trial in range(1, int(args.natural_trials) + 1):
        phases.extend(
            [
                Phase(f"heartbeat_pre_{trial}", 1.5, JETSON_MODE, trial=trial),
                Phase(f"heartbeat_outage_{trial}", 2.5, None, trial=trial),
                Phase(f"heartbeat_recovery_{trial}", 2.0, JETSON_MODE, trial=trial),
            ]
        )
    phases.extend(
        [
            Phase(
                "controlled_loss",
                float(args.loss_duration_s),
                JETSON_MODE,
                drop_rate=float(args.loss_rate),
            ),
            Phase(
                "controlled_delay",
                float(args.delay_duration_s),
                JETSON_MODE,
                delay_ms=float(args.delay_ms),
            ),
            Phase("delay_drain", max(0.5, float(args.delay_ms) / 1000.0 + 0.3), JETSON_MODE),
        ]
    )
    for trial in range(1, int(args.forced_timeout_trials) + 1):
        phases.extend(
            [
                Phase(f"forced_timeout_pre_{trial}", 1.0, JETSON_MODE, trial=trial),
                Phase(f"forced_timeout_drain_{trial}", 0.6, None, trial=trial),
                Phase(
                    f"forced_timeout_{trial}",
                    1.2,
                    None,
                    injection="watchdog_threshold",
                    trial=trial,
                ),
                Phase(f"forced_timeout_recovery_{trial}", 1.5, JETSON_MODE, trial=trial),
            ]
        )
    phases.extend(
        [
            Phase("error_feedback_pre", 1.0, JETSON_MODE),
            Phase(
                "error_feedback_injected",
                3.0,
                JETSON_MODE,
                injection="system_communication_bit",
            ),
            Phase("error_feedback_clear", 2.0, JETSON_MODE),
            Phase("remote_cleanup", 2.0, REMOTE_MODE),
        ]
    )
    return phases


def event_row(
    start: float,
    event_type: str,
    phase: Phase,
    **values: Any,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "event_type": event_type,
        "elapsed_s": time.monotonic() - start,
        "wall_time_utc": utc_now(),
        "phase": phase.name,
        "trial": phase.trial,
        "logical_frame": "",
        "wire_frame": "",
        "scheduled_delay_ms": phase.delay_ms,
        "deliberately_dropped": 0,
        "uplink_frame": "",
        "control_mode_byte": "",
        "work_instruction": "",
        "main_motor_rpm": "",
        "side_motor_rpm": "",
        "left_fin_deg": "",
        "right_fin_deg": "",
        "top_fin_deg": "",
        "bottom_fin_deg": "",
        "sys_abnorm_info": "",
        "bit5_system_communication": "",
        "bit13_dvl_lost": "",
        "bit14_jetson_timeout": "",
        "pc104_uptime_ms": "",
        "pc104_downlink_echo_frame": "",
        "pc104_downlink_recv_uptime_ms": "",
        "generation_to_send_ms": "",
        "wire_to_first_echo_ms": "",
        "generation_to_first_echo_ms": "",
        "pc104_tick": "",
        "watchdog_count": "",
        "telnet_sys_abnorm": "",
        "telnet_current_mode": "",
        "telnet_ui_mode": "",
        "telnet_ui_motor1": "",
        "telnet_ui_motor2": "",
        "telnet_ui_fin_lh": "",
        "telnet_ui_fin_rh": "",
        "telnet_ui_fin_uv": "",
        "telnet_ui_fin_lv": "",
        "telnet_instruction_motor1": "",
        "telnet_instruction_motor2": "",
        "telnet_dvl_check": "",
        "telnet_dvl_height_m": "",
        "telnet_fmcu_sys_abnorm": "",
        "note": "",
    }
    row.update(values)
    return row


def run_experiment(
    args: argparse.Namespace,
    shell: VxShell,
    symbols: BoardSymbols,
    offsets: Offsets,
) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    phases = build_phases(args)
    rows: list[dict[str, Any]] = []
    phase_bounds: dict[str, dict[str, float | int | str]] = {}
    rng = random.Random(int(args.seed))
    remote = (str(args.remote_host), int(args.remote_port))
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((str(args.local_host), int(args.local_port)))
    sock.setblocking(False)

    initial = shell.read_snapshot(symbols, offsets)
    motor_keys = (
        "telnet_ui_motor1",
        "telnet_ui_motor2",
        "telnet_ui_fin_lh",
        "telnet_ui_fin_rh",
        "telnet_ui_fin_uv",
        "telnet_ui_fin_lv",
        "telnet_instruction_motor1",
        "telnet_instruction_motor2",
    )
    if any(int(initial[key]) != 0 for key in motor_keys):
        sock.close()
        raise RuntimeError(f"initial motor state is not zero: {initial}")
    if int(initial["telnet_sys_abnorm"]) != 0:
        sock.close()
        raise RuntimeError(
            "initial Sys_Abnorm_Inf_Judgement is non-zero; clear unrelated "
            f"faults before testing: 0x{int(initial['telnet_sys_abnorm']):08x}"
        )

    original = {
        "dvl_check_bits": shell.read_u32(symbols.dvl_data + offsets.dvl_bd_check),
        "dvl_height_bits": shell.read_u32(symbols.dvl_data + offsets.dvl_bd_height),
        "watchdog": shell.read_u16(symbols.watchdog),
        "sys_abnorm": shell.read_u32(symbols.sys_abnorm),
        "fmcu_sys_abnorm": shell.read_u32(
            symbols.fmcu_feedback + offsets.fmcu_sys_abnorm
        ),
    }

    start = time.monotonic()
    frame = 0
    logical_frame = 0
    pending: list[tuple[float, int, int, float, str]] = []
    latest_send_by_frame: dict[int, tuple[float, float, int]] = {}
    seen_echo: set[tuple[int, int]] = set()

    def append(event_type: str, phase: Phase, **values: Any) -> None:
        rows.append(event_row(start, event_type, phase, **values))

    def send_remote_cleanup(duration_s: float = 1.5) -> None:
        nonlocal frame
        deadline = time.monotonic() + duration_s
        while time.monotonic() < deadline:
            packet = build_zero_packet(frame, REMOTE_MODE)
            sock.sendto(packet, remote)
            frame = (frame + 1) & 0xFF
            time.sleep(0.1)

    try:
        shell.write_float(symbols.dvl_data + offsets.dvl_bd_height, 5.0)
        shell.write_float(symbols.dvl_data + offsets.dvl_bd_check, 2.0)
        shell.write_u32(symbols.sys_abnorm, original["sys_abnorm"] & ~0x7800)
        time.sleep(1.0)

        for phase in phases:
            phase_start = time.monotonic()
            phase_generated_index = 0
            phase_frame_count = max(
                0,
                int(math.ceil(phase.duration_s * float(args.send_rate_hz) - 1.0e-9)),
            )
            phase_drop_count = round(phase_frame_count * phase.drop_rate)
            phase_drop_slots = (
                set(rng.sample(range(phase_frame_count), phase_drop_count))
                if phase_drop_count > 0
                else set()
            )
            phase_bounds[phase.name] = {
                "start_s": phase_start - start,
                "duration_s": phase.duration_s,
                "trial": phase.trial,
                "injection": phase.injection,
            }
            append("phase_start", phase, note=phase.injection)

            if phase.injection == "watchdog_threshold":
                shell.write_u16(symbols.watchdog, 10)
                append(
                    "telnet_injection",
                    phase,
                    watchdog_count=10,
                    note="Not_Recv_From_Jetson_No=10",
                )

            phase_generate_end = phase_start + phase.duration_s
            phase_end = phase_generate_end + max(0.0, phase.delay_ms / 1000.0)
            next_generate = phase_start
            next_monitor = phase_start
            next_error_injection = phase_start

            while time.monotonic() < phase_end:
                now = time.monotonic()

                if (
                    phase.injection == "system_communication_bit"
                    and now >= next_error_injection
                ):
                    shell.write_u32(
                        symbols.fmcu_feedback + offsets.fmcu_sys_abnorm,
                        original["fmcu_sys_abnorm"]
                        | (1 << BIT_SYSTEM_COMMUNICATION),
                    )
                    current_sys = shell.read_u32(symbols.sys_abnorm)
                    shell.write_u32(
                        symbols.sys_abnorm,
                        current_sys | (1 << BIT_SYSTEM_COMMUNICATION),
                    )
                    append(
                        "telnet_injection",
                        phase,
                        sys_abnorm_info=current_sys
                        | (1 << BIT_SYSTEM_COMMUNICATION),
                        bit5_system_communication=1,
                        note="FMCU/system communication fault bit asserted",
                    )
                    next_error_injection += 0.1

                if (
                    phase.control_mode is not None
                    and now >= next_generate
                    and next_generate < phase_generate_end
                ):
                    generated_at = next_generate
                    current_frame = frame
                    current_logical = logical_frame
                    frame = (frame + 1) & 0xFF
                    logical_frame += 1
                    drop = phase_generated_index in phase_drop_slots
                    phase_generated_index += 1
                    if drop:
                        append(
                            "downlink_drop",
                            phase,
                            logical_frame=current_logical,
                            wire_frame=current_frame,
                            deliberately_dropped=1,
                        )
                    else:
                        due = generated_at + phase.delay_ms / 1000.0
                        heapq.heappush(
                            pending,
                            (
                                due,
                                current_logical,
                                current_frame,
                                generated_at,
                                phase.name,
                            ),
                        )
                    next_generate += 1.0 / float(args.send_rate_hz)

                while pending and pending[0][0] <= now:
                    due, packet_logical, packet_frame, generated_at, generated_phase = (
                        heapq.heappop(pending)
                    )
                    packet = build_zero_packet(packet_frame, int(phase.control_mode or JETSON_MODE))
                    sent_at = time.monotonic()
                    sock.sendto(packet, remote)
                    latest_send_by_frame[packet_frame] = (
                        sent_at,
                        generated_at,
                        packet_logical,
                    )
                    append(
                        "downlink_send",
                        phase,
                        logical_frame=packet_logical,
                        wire_frame=packet_frame,
                        generation_to_send_ms=(sent_at - generated_at) * 1000.0,
                        note=(
                            ""
                            if generated_phase == phase.name
                            else f"generated_in={generated_phase}"
                        ),
                    )

                if now >= next_monitor:
                    snapshot = shell.read_snapshot(symbols, offsets)
                    append("telnet_snapshot", phase, **snapshot)
                    next_monitor += 1.0 / float(args.monitor_rate_hz)

                wait_until = phase_end
                if phase.control_mode is not None and next_generate < phase_generate_end:
                    wait_until = min(wait_until, next_generate)
                if pending:
                    wait_until = min(wait_until, pending[0][0])
                if next_monitor < phase_end:
                    wait_until = min(wait_until, next_monitor)
                timeout = max(0.0, min(0.02, wait_until - time.monotonic()))
                readable, _, _ = select.select([sock], [], [], timeout)
                if not readable:
                    continue
                packet, addr = sock.recvfrom(4096)
                recv_at = time.monotonic()
                try:
                    telemetry = parse_uplink_packet(packet)
                except Exception as exc:
                    append(
                        "uplink_parse_error",
                        phase,
                        note=f"{addr[0]}:{addr[1]}: {exc}",
                    )
                    continue

                wire_rtt_ms: float | str = ""
                generated_rtt_ms: float | str = ""
                if telemetry.pc104_downlink_echo_valid:
                    echo_key = (
                        int(telemetry.pc104_downlink_echo_frame),
                        int(telemetry.pc104_downlink_recv_uptime_ms),
                    )
                    sent = latest_send_by_frame.get(
                        int(telemetry.pc104_downlink_echo_frame)
                    )
                    if echo_key not in seen_echo and sent is not None:
                        seen_echo.add(echo_key)
                        wire_rtt_ms = (recv_at - sent[0]) * 1000.0
                        generated_rtt_ms = (recv_at - sent[1]) * 1000.0

                sys_abnorm = int(telemetry.sys_abnorm_info)
                append(
                    "uplink_recv",
                    phase,
                    uplink_frame=int(telemetry.frame_number),
                    control_mode_byte=int(telemetry.control_mode_byte),
                    work_instruction=int(telemetry.work_instruction),
                    main_motor_rpm=int(telemetry.main_motor_rpm),
                    side_motor_rpm=int(telemetry.side_motor_rpm),
                    left_fin_deg=float(telemetry.left_fin_deg),
                    right_fin_deg=float(telemetry.right_fin_deg),
                    top_fin_deg=float(telemetry.top_fin_deg),
                    bottom_fin_deg=float(telemetry.bottom_fin_deg),
                    sys_abnorm_info=sys_abnorm,
                    bit5_system_communication=int(
                        bool(sys_abnorm & (1 << BIT_SYSTEM_COMMUNICATION))
                    ),
                    bit13_dvl_lost=int(bool(sys_abnorm & (1 << BIT_DVL_LOST))),
                    bit14_jetson_timeout=int(
                        bool(sys_abnorm & (1 << BIT_JETSON_TIMEOUT))
                    ),
                    pc104_uptime_ms=int(telemetry.pc104_uptime_ms),
                    pc104_downlink_echo_frame=(
                        int(telemetry.pc104_downlink_echo_frame)
                        if telemetry.pc104_downlink_echo_valid
                        else ""
                    ),
                    pc104_downlink_recv_uptime_ms=(
                        int(telemetry.pc104_downlink_recv_uptime_ms)
                        if telemetry.pc104_downlink_echo_valid
                        else ""
                    ),
                    wire_to_first_echo_ms=wire_rtt_ms,
                    generation_to_first_echo_ms=generated_rtt_ms,
                    note=f"size={len(packet)}",
                )

            if phase.injection == "system_communication_bit":
                shell.write_u32(
                    symbols.fmcu_feedback + offsets.fmcu_sys_abnorm,
                    original["fmcu_sys_abnorm"],
                )
                current_sys = shell.read_u32(symbols.sys_abnorm)
                shell.write_u32(
                    symbols.sys_abnorm,
                    current_sys & ~(1 << BIT_SYSTEM_COMMUNICATION),
                )
            append("phase_end", phase)

        final = shell.read_snapshot(symbols, offsets)
    finally:
        try:
            send_remote_cleanup()
        finally:
            sock.close()
            shell.write_u8(
                symbols.ui_instruction + offsets.ui_ctrl_mode,
                REMOTE_MODE,
            )
            shell.write_s16(symbols.ui_instruction + offsets.ui_motor1, 0)
            shell.write_s16(symbols.ui_instruction + offsets.ui_motor2, 0)
            shell.write_s16(symbols.ui_instruction + offsets.ui_fin_lh, 0)
            shell.write_s16(symbols.ui_instruction + offsets.ui_fin_rh, 0)
            shell.write_s16(symbols.ui_instruction + offsets.ui_fin_uv, 0)
            shell.write_s16(symbols.ui_instruction + offsets.ui_fin_lv, 0)
            shell.write_s16(
                symbols.fmcu_instruction + offsets.instruction_motor1,
                0,
            )
            shell.write_s16(
                symbols.fmcu_instruction + offsets.instruction_motor2,
                0,
            )
            shell.write_u16(symbols.watchdog, 0)
            shell.write_u32(
                symbols.fmcu_feedback + offsets.fmcu_sys_abnorm,
                original["fmcu_sys_abnorm"],
            )
            shell.write_u32(symbols.sys_abnorm, original["sys_abnorm"])
            shell.write_u32(
                symbols.dvl_data + offsets.dvl_bd_check,
                original["dvl_check_bits"],
            )
            shell.write_u32(
                symbols.dvl_data + offsets.dvl_bd_height,
                original["dvl_height_bits"],
            )
            time.sleep(0.8)
            cleanup = shell.read_snapshot(symbols, offsets)

    summary = summarize(rows, phase_bounds, args, cleanup)
    return rows, summary, {
        "initial": initial,
        "pre_cleanup_final": final,
        "post_cleanup": cleanup,
        "original_raw": original,
        "symbols": {
            key: f"0x{value:08x}"
            for key, value in vars(symbols).items()
        },
    }


def first_uplink(
    rows: list[dict[str, Any]],
    phase_name: str,
    predicate,
) -> dict[str, Any] | None:
    for row in rows:
        if (
            row["event_type"] == "uplink_recv"
            and row["phase"] == phase_name
            and predicate(row)
        ):
            return row
    return None


def summarize(
    rows: list[dict[str, Any]],
    phase_bounds: dict[str, dict[str, float | int | str]],
    args: argparse.Namespace,
    cleanup: dict[str, int | float],
) -> dict[str, Any]:
    uplinks = [row for row in rows if row["event_type"] == "uplink_recv"]
    parse_errors = [row for row in rows if row["event_type"] == "uplink_parse_error"]
    sends = [row for row in rows if row["event_type"] == "downlink_send"]
    drops = [row for row in rows if row["event_type"] == "downlink_drop"]
    snapshots = [row for row in rows if row["event_type"] == "telnet_snapshot"]

    natural_trigger_ms: list[float] = []
    natural_mode_ms: list[float] = []
    natural_recovery_ms: list[float] = []
    natural_clear_ms: list[float] = []
    for trial in range(1, int(args.natural_trials) + 1):
        outage = f"heartbeat_outage_{trial}"
        recovery = f"heartbeat_recovery_{trial}"
        outage_start = float(phase_bounds[outage]["start_s"])
        recovery_start = float(phase_bounds[recovery]["start_s"])
        bit14 = first_uplink(
            rows,
            outage,
            lambda row: int(row["bit14_jetson_timeout"]) == 1,
        )
        remote = first_uplink(
            rows,
            outage,
            lambda row: int(row["control_mode_byte"]) == REMOTE_MODE,
        )
        recovered = first_uplink(
            rows,
            recovery,
            lambda row: int(row["control_mode_byte"]) == JETSON_MODE,
        )
        cleared = first_uplink(
            rows,
            recovery,
            lambda row: int(row["bit14_jetson_timeout"]) == 0,
        )
        if bit14 is not None:
            natural_trigger_ms.append(
                (float(bit14["elapsed_s"]) - outage_start) * 1000.0
            )
        if remote is not None:
            natural_mode_ms.append(
                (float(remote["elapsed_s"]) - outage_start) * 1000.0
            )
        if recovered is not None:
            natural_recovery_ms.append(
                (float(recovered["elapsed_s"]) - recovery_start) * 1000.0
            )
        if cleared is not None:
            natural_clear_ms.append(
                (float(cleared["elapsed_s"]) - recovery_start) * 1000.0
            )

    forced_trigger_ms: list[float] = []
    forced_recovery_ms: list[float] = []
    for trial in range(1, int(args.forced_timeout_trials) + 1):
        fault = f"forced_timeout_{trial}"
        recovery = f"forced_timeout_recovery_{trial}"
        recovery_start = float(phase_bounds[recovery]["start_s"])
        injection = next(
            (
                row
                for row in rows
                if row["event_type"] == "telnet_injection"
                and row["phase"] == fault
                and row["note"] == "Not_Recv_From_Jetson_No=10"
            ),
            None,
        )
        bit14 = first_uplink(
            rows,
            fault,
            lambda row: int(row["bit14_jetson_timeout"]) == 1,
        )
        cleared = first_uplink(
            rows,
            recovery,
            lambda row: int(row["bit14_jetson_timeout"]) == 0
            and int(row["control_mode_byte"]) == JETSON_MODE,
        )
        if bit14 is not None and injection is not None:
            forced_trigger_ms.append(
                (
                    float(bit14["elapsed_s"])
                    - float(injection["elapsed_s"])
                )
                * 1000.0
            )
        if cleared is not None:
            forced_recovery_ms.append(
                (float(cleared["elapsed_s"]) - recovery_start) * 1000.0
            )

    loss_sends = [row for row in sends if row["phase"] == "controlled_loss"]
    loss_drops = [row for row in drops if row["phase"] == "controlled_loss"]
    loss_generated = len(loss_sends) + len(loss_drops)
    expected_loss_drops = round(loss_generated * float(args.loss_rate))
    delay_sends = [row for row in sends if row["phase"] == "controlled_delay"]
    delay_values = [
        float(row["generation_to_send_ms"])
        for row in delay_sends
        if str(row["generation_to_send_ms"]).strip()
    ]
    error_seen = any(
        int(row["bit5_system_communication"]) == 1
        for row in uplinks
        if row["phase"] == "error_feedback_injected"
    )
    error_cleared = any(
        int(row["bit5_system_communication"]) == 0
        for row in uplinks
        if row["phase"] == "error_feedback_clear"
    )
    nonzero_uplink = sum(
        1
        for row in uplinks
        if int(row["main_motor_rpm"]) != 0 or int(row["side_motor_rpm"]) != 0
    )
    nonzero_uplink_fin_feedback = sum(
        1
        for row in uplinks
        if any(
            abs(float(row[key])) > 1.0e-9
            for key in (
                "left_fin_deg",
                "right_fin_deg",
                "top_fin_deg",
                "bottom_fin_deg",
            )
        )
    )
    max_abs_uplink_fin_feedback = max(
        (
            abs(float(row[key]))
            for row in uplinks
            for key in (
                "left_fin_deg",
                "right_fin_deg",
                "top_fin_deg",
                "bottom_fin_deg",
            )
        ),
        default=float("nan"),
    )
    nonzero_telnet_command = sum(
        1
        for row in snapshots
        if any(
            int(row[key]) != 0
            for key in (
                "telnet_ui_motor1",
                "telnet_ui_motor2",
                "telnet_ui_fin_lh",
                "telnet_ui_fin_rh",
                "telnet_ui_fin_uv",
                "telnet_ui_fin_lv",
                "telnet_instruction_motor1",
                "telnet_instruction_motor2",
            )
        )
    )
    dvl_interference = sum(
        1
        for row in uplinks
        if int(row["bit13_dvl_lost"]) == 1
    )
    loss_timeout = sum(
        1
        for row in uplinks
        if row["phase"] == "controlled_loss"
        and int(row["bit14_jetson_timeout"]) == 1
    )
    delay_timeout = sum(
        1
        for row in uplinks
        if row["phase"] in {"controlled_delay", "delay_drain"}
        and int(row["bit14_jetson_timeout"]) == 1
    )
    cleanup_safe = (
        int(cleanup["telnet_current_mode"]) == REMOTE_MODE
        and int(cleanup["telnet_ui_mode"]) == REMOTE_MODE
        and all(
            int(cleanup[key]) == 0
            for key in (
                "telnet_ui_motor1",
                "telnet_ui_motor2",
                "telnet_ui_fin_lh",
                "telnet_ui_fin_rh",
                "telnet_ui_fin_uv",
                "telnet_ui_fin_lv",
                "telnet_instruction_motor1",
                "telnet_instruction_motor2",
            )
        )
    )

    expected_natural = int(args.natural_trials)
    expected_forced = int(args.forced_timeout_trials)
    passed = (
        bool(uplinks)
        and not parse_errors
        and len(natural_trigger_ms) == expected_natural
        and len(natural_mode_ms) == expected_natural
        and len(natural_recovery_ms) == expected_natural
        and len(natural_clear_ms) == expected_natural
        and len(forced_trigger_ms) == expected_forced
        and len(forced_recovery_ms) == expected_forced
        and bool(error_seen)
        and bool(error_cleared)
        and nonzero_uplink == 0
        and nonzero_telnet_command == 0
        and dvl_interference == 0
        and loss_timeout == 0
        and len(loss_drops) == expected_loss_drops
        and delay_timeout == 0
        and cleanup_safe
    )
    return {
        "scenario": "pc104_telnetd_fault_injection",
        "status": "ok" if passed else "failed_acceptance",
        "error": "" if passed else "one or more hardware acceptance criteria failed",
        "duration_s": max((float(row["elapsed_s"]) for row in rows), default=0.0),
        "uplink_count": len(uplinks),
        "uplink_parse_error_count": len(parse_errors),
        "downlink_send_count": len(sends),
        "controlled_loss_configured_rate": float(args.loss_rate),
        "controlled_loss_generated_count": loss_generated,
        "deliberate_drop_count": len(drops),
        "controlled_loss_actual_rate": (
            len(loss_drops) / loss_generated
            if loss_generated
            else float("nan")
        ),
        "controlled_delay_p50_ms": percentile(delay_values, 0.50),
        "controlled_delay_p95_ms": percentile(delay_values, 0.95),
        "natural_timeout_trial_count": expected_natural,
        "natural_timeout_detected_count": len(natural_trigger_ms),
        "natural_timeout_trigger_p50_ms": percentile(natural_trigger_ms, 0.50),
        "natural_timeout_trigger_p95_ms": percentile(natural_trigger_ms, 0.95),
        "natural_remote_mode_p50_ms": percentile(natural_mode_ms, 0.50),
        "natural_recovery_mode_p50_ms": percentile(natural_recovery_ms, 0.50),
        "natural_recovery_bit_clear_p50_ms": percentile(natural_clear_ms, 0.50),
        "forced_timeout_trial_count": expected_forced,
        "forced_timeout_detected_count": len(forced_trigger_ms),
        "forced_timeout_trigger_p50_ms": percentile(forced_trigger_ms, 0.50),
        "forced_recovery_p50_ms": percentile(forced_recovery_ms, 0.50),
        "error_feedback_bit5_observed": bool(error_seen),
        "error_feedback_bit5_cleared": bool(error_cleared),
        "loss_phase_timeout_frame_count": loss_timeout,
        "delay_phase_timeout_frame_count": delay_timeout,
        "dvl_interference_frame_count": dvl_interference,
        "nonzero_uplink_motor_frame_count": nonzero_uplink,
        "nonzero_uplink_fin_feedback_frame_count": nonzero_uplink_fin_feedback,
        "max_abs_uplink_fin_feedback_deg": max_abs_uplink_fin_feedback,
        "nonzero_telnet_command_snapshot_count": nonzero_telnet_command,
        "cleanup_remote_zero": bool(cleanup_safe),
        "effective_sample_count": len(uplinks),
        "failure_event_count": 0 if passed else 1,
        "capability_gate_status": "passed" if passed else "failed",
        "solver_wall_time_current_ms": "not_applicable",
        "fallback_type": "pc104_remote_zero",
    }


def write_timeline(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(event_row(0.0, "", Phase("", 0.0, None)).keys())
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_report(
    output_dir: Path,
    summary: dict[str, Any],
    state: dict[str, Any],
) -> None:
    lines = [
        "# PC104 Telnetd Fault-Injection Report",
        "",
        "## Safety boundary",
        "",
        "- Every `$CKTH` packet was decoded locally and required to contain zero main/side motor and zero fin commands before transmission.",
        "- DVL `BD_Check=2` and `BD_Height=5 m` were injected only to isolate the heartbeat watchdog from the absent-DVL Bit13 fallback.",
        "- Cleanup forced Remote mode and zero motor commands before restoring all captured runtime values.",
        "",
        "## Results",
        "",
        f"- Status: `{summary['status']}`",
        f"- Parsed `$AUV` frames: `{summary['uplink_count']}`",
        f"- Natural heartbeat timeout detections: `{summary['natural_timeout_detected_count']}/{summary['natural_timeout_trial_count']}`",
        f"- Natural timeout trigger p50/p95: `{float(summary['natural_timeout_trigger_p50_ms']):.3f}/{float(summary['natural_timeout_trigger_p95_ms']):.3f} ms`",
        f"- Recovery mode/Bit14-clear p50: `{float(summary['natural_recovery_mode_p50_ms']):.3f}/{float(summary['natural_recovery_bit_clear_p50_ms']):.3f} ms`",
        f"- Telnet-forced timeout detections: `{summary['forced_timeout_detected_count']}/{summary['forced_timeout_trial_count']}`",
        f"- Controlled loss: configured `{float(summary['controlled_loss_configured_rate']):.1%}`, generated/dropped `{summary['controlled_loss_generated_count']}/{summary['deliberate_drop_count']}`, actual `{float(summary['controlled_loss_actual_rate']):.1%}`",
        f"- Controlled queueing delay p50/p95: `{float(summary['controlled_delay_p50_ms']):.3f}/{float(summary['controlled_delay_p95_ms']):.3f} ms`",
        f"- Bit5 error feedback observed/cleared: `{summary['error_feedback_bit5_observed']}/{summary['error_feedback_bit5_cleared']}`",
        f"- Non-zero command observations (uplink motors/telnet motor+fin commands): `{summary['nonzero_uplink_motor_frame_count']}/{summary['nonzero_telnet_command_snapshot_count']}`",
        f"- Non-zero fin-feedback frames (diagnostic, not command): `{summary['nonzero_uplink_fin_feedback_frame_count']}`; maximum absolute feedback `{float(summary['max_abs_uplink_fin_feedback_deg']):.1f} deg`",
        f"- Cleanup Remote+zero verified: `{summary['cleanup_remote_zero']}`",
        "",
        "## Boundary",
        "",
        "The loss and delay profiles are injected at the container sender before the host relay. "
        "They are deterministic application-path impairments, not Ethernet PHY impairment measurements. "
        "The Bit5 case is a telnetd software fault-bit injection into the PC104 runtime state, not a physical MCU fault. "
        "Fin fields in `$AUV` are FMCU position feedback rather than PC104 command values; the zero-command "
        "gate therefore uses decoded `$CKTH` fields and telnet-observed UI command fields.",
        "",
        "Primary artifacts: `fault_timeline.csv`, `summary.json`, `board_state.json`, "
        "`metrics.csv`, and `status.json`.",
        "",
    ]
    (output_dir / "report.md").write_text("\n".join(lines), encoding="utf-8")
    (output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (output_dir / "board_state.json").write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    args = parse_args()
    if args.send_rate_hz <= 0 or args.monitor_rate_hz <= 0:
        raise SystemExit("send and monitor rates must be positive")
    if not (0.0 <= args.loss_rate < 1.0):
        raise SystemExit("--loss-rate must be in [0, 1)")
    if args.natural_trials <= 0 or args.forced_timeout_trials <= 0:
        raise SystemExit("trial counts must be positive")
    if args.loss_duration_s <= 0 or args.delay_duration_s <= 0:
        raise SystemExit("loss and delay durations must be positive")
    if args.delay_ms < 0:
        raise SystemExit("--delay-ms must be non-negative")

    shell = VxShell(
        args.telnet_host,
        args.telnet_port,
        args.telnet_user,
        args.telnet_password,
        5.0,
    )
    shell.connect()
    try:
        symbols = resolve_symbols(shell)
        offsets = Offsets()
        initial = shell.read_snapshot(symbols, offsets)
        print("[pc104-fault] symbols resolved")
        print(
            "[pc104-fault] baseline "
            f"mode=0x{int(initial['telnet_current_mode']):02x} "
            f"sys=0x{int(initial['telnet_sys_abnorm']):08x} "
            f"motors={initial['telnet_instruction_motor1']}/"
            f"{initial['telnet_instruction_motor2']}",
            flush=True,
        )
        if not args.execute:
            print("[pc104-fault] read-only preflight complete; pass --execute to inject")
            return 0

        stamp = time.strftime("%Y%m%d_%H%M%S")
        output_dir = args.output_dir or (
            REPO_ROOT / "results/control" / f"pc104_fault_injection_{stamp}"
        )
        sanitized_argv = [
            "***" if previous == "--telnet-password" else value
            for previous, value in zip(["", *sys.argv[:-1]], sys.argv)
        ]
        initialize_bundle(
            output_dir,
            experiment_id=f"pc104_fault_injection_{stamp}",
            runner="tools/probe_pc104_fault_injection.py",
            argv=sanitized_argv,
            data_layer="physical_pc104_telnetd_fault_injection",
            matrix={
                "natural_timeout_trials": args.natural_trials,
                "forced_timeout_trials": args.forced_timeout_trials,
                "loss_rate": args.loss_rate,
                "loss_duration_s": args.loss_duration_s,
                "delay_ms": args.delay_ms,
                "delay_duration_s": args.delay_duration_s,
                "seed": args.seed,
            },
            duration_s=None,
            config_paths=[
                Path(__file__),
                REPO_ROOT / "common/protocol.py",
                REPO_ROOT / "csd_vx6.8_lastest/SecurityEmergencyManage.c",
                REPO_ROOT / "csd_vx6.8_lastest/main.c",
                REPO_ROOT / "csd_vx6.8_lastest/DataProcess.c",
            ],
            extra_manifest={
                "hardware_required": True,
                "telnetd_runtime_injection": True,
                "safe_zero_actuator_downlink": True,
                "dvl_safe_isolation_injection": {
                    "BD_Check": 2.0,
                    "BD_Height_m": 5.0,
                },
                "loss_delay_injection_location": "container_sender_before_host_relay",
                "loss_sampler": "fixed_seed_random_positions_with_exact_count",
                "physical_one_way_latency_claim": False,
            },
        )
        rows, summary, state = run_experiment(args, shell, symbols, offsets)
        write_timeline(output_dir / "fault_timeline.csv", rows)
        finalize_bundle(output_dir, [summary])
        write_report(output_dir, summary, state)
        print(
            "[pc104-fault] "
            f"status={summary['status']} uplink={summary['uplink_count']} "
            f"natural={summary['natural_timeout_detected_count']}/"
            f"{summary['natural_timeout_trial_count']} "
            f"forced={summary['forced_timeout_detected_count']}/"
            f"{summary['forced_timeout_trial_count']} -> {output_dir}",
            flush=True,
        )
        return 0 if summary["status"] == "ok" else 2
    finally:
        shell.close()


if __name__ == "__main__":
    raise SystemExit(main())

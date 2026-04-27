#!/usr/bin/env python3
"""Standalone attacker station for the AUV mock AMD protocol.

The script simulates a second controller competing for the same Mock AMD
endpoint. It sends shared-protocol $CKTH packets, waits for $AUV responses,
and records latency statistics plus a CSV trace.
"""

from __future__ import annotations

import argparse
import csv
import math
import random
import signal
import socket
import statistics
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
project_root_str = str(PROJECT_ROOT)
if project_root_str not in sys.path:
    sys.path.insert(0, project_root_str)

from common.enums import ControlModeByte, WorkInstruction
from common.protocol import (
    DEFAULT_MAIN_MOTOR_RPM_SCALE,
    KEY_BOTTOM,
    KEY_CONTROL_MODE_BYTE,
    KEY_FRAME_NUMBER,
    KEY_LEFT,
    KEY_OBJ_ADDRESS,
    KEY_ORIENTATION_DEG,
    KEY_PARAMETERS,
    KEY_RIGHT,
    KEY_SIDE_MOTOR_RPM,
    KEY_THRUST,
    KEY_TOP,
    KEY_WORK_INSTRUCTION,
    build_downlink_packet_from_payload,
    parse_uplink_packet,
)


PROFILE_CHOICES = ("conflict", "sweep", "heartbeat")
SWEEP_CASES: tuple[dict[str, Any], ...] = (
    {
        "label": "zero",
        KEY_CONTROL_MODE_BYTE: int(ControlModeByte.SEND_ONLY),
        KEY_WORK_INSTRUCTION: int(WorkInstruction.NONE),
        KEY_RIGHT: 0.0,
        KEY_LEFT: 0.0,
        KEY_TOP: 0.0,
        KEY_BOTTOM: 0.0,
        KEY_THRUST: 0.0,
        KEY_SIDE_MOTOR_RPM: 0,
        KEY_ORIENTATION_DEG: 0.0,
    },
    {
        "label": "balanced",
        KEY_CONTROL_MODE_BYTE: int(ControlModeByte.REMOTE_CONTROL),
        KEY_WORK_INSTRUCTION: int(WorkInstruction.TASK_START),
        KEY_RIGHT: 35.0,
        KEY_LEFT: -35.0,
        KEY_TOP: 15.0,
        KEY_BOTTOM: -15.0,
        KEY_THRUST: 25.0,
        KEY_SIDE_MOTOR_RPM: 80,
        KEY_ORIENTATION_DEG: 45.0,
    },
    {
        "label": "max_positive",
        KEY_CONTROL_MODE_BYTE: int(ControlModeByte.AUTO_FIXED_POINT),
        KEY_WORK_INSTRUCTION: int(WorkInstruction.AUTONOMOUS_CONTROL),
        KEY_RIGHT: 100.0,
        KEY_LEFT: -100.0,
        KEY_TOP: 100.0,
        KEY_BOTTOM: -100.0,
        KEY_THRUST: 100.0,
        KEY_SIDE_MOTOR_RPM: 120,
        KEY_ORIENTATION_DEG: 90.0,
    },
    {
        "label": "overrange",
        KEY_CONTROL_MODE_BYTE: int(ControlModeByte.AUTO_DIRECTION),
        KEY_WORK_INSTRUCTION: int(WorkInstruction.HOLD_DEBUG),
        KEY_RIGHT: 120.0,
        KEY_LEFT: -120.0,
        KEY_TOP: 120.0,
        KEY_BOTTOM: -120.0,
        KEY_THRUST: 150.0,
        KEY_SIDE_MOTOR_RPM: 240,
        KEY_ORIENTATION_DEG: 180.0,
    },
    {
        "label": "reverse",
        KEY_CONTROL_MODE_BYTE: int(ControlModeByte.RETURN_HOME),
        KEY_WORK_INSTRUCTION: int(WorkInstruction.TASK_CANCEL),
        KEY_RIGHT: -50.0,
        KEY_LEFT: 50.0,
        KEY_TOP: -40.0,
        KEY_BOTTOM: 40.0,
        KEY_THRUST: -60.0,
        KEY_SIDE_MOTOR_RPM: -90,
        KEY_ORIENTATION_DEG: 270.0,
    },
)


@dataclass(frozen=True)
class AttackerStationConfig:
    mock_amd_host: str = "127.0.0.1"
    mock_amd_port: int = 52364
    listen_host: str = "0.0.0.0"
    listen_port: int = 52367
    profile: str = "conflict"
    duration_s: float = 10.0
    rate_hz: float | None = None
    response_timeout_s: float = 1.0
    report_interval_s: float = 10.0
    enable_csv: bool = True
    enable_live_report: bool = True
    obj_address: int = 1
    main_motor_rpm_scale: float = DEFAULT_MAIN_MOTOR_RPM_SCALE
    side_motor_rpm: int = 0
    seed: int | None = None
    csv_path: Path | None = None


@dataclass
class AttackSample:
    timestamp_s: float
    profile: str
    sequence_index: int
    request_packet: bytes
    response_packet: bytes | None
    response_addr: tuple[str, int] | None
    rtt_ms: float | None
    response_received: bool
    request_payload: dict[str, Any]
    request_label: str | None = None
    response_frame_number: int | None = None
    response_main_motor_rpm: int | None = None
    response_depth_m: float | None = None


@dataclass
class StationStats:
    sent: int = 0
    received: int = 0
    rtts_ms: list[float] = field(default_factory=list)

    @property
    def lost(self) -> int:
        return self.sent - self.received

    def record(self, sample: AttackSample) -> None:
        self.sent += 1
        if sample.response_received:
            self.received += 1
        if sample.rtt_ms is not None:
            self.rtts_ms.append(float(sample.rtt_ms))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Attacker station for Mock AMD traffic")
    parser.add_argument("--mock-amd-host", default="127.0.0.1", help="Mock AMD host")
    parser.add_argument("--mock-amd-port", type=int, default=52364, help="Mock AMD UDP port")
    parser.add_argument("--listen-host", default="0.0.0.0", help="Local host to bind for responses")
    parser.add_argument("--listen-port", type=int, default=52367, help="Local UDP port to bind")
    parser.add_argument("--profile", choices=PROFILE_CHOICES, default="conflict", help="Traffic profile")
    parser.add_argument("--duration", type=float, default=10.0, help="Run duration in seconds; 0 means until Ctrl-C")
    parser.add_argument("--rate-hz", type=float, default=None, help="Send rate in Hz; defaults depend on profile")
    parser.add_argument("--response-timeout-s", type=float, default=1.0, help="Wait time for each $AUV response")
    parser.add_argument("--report-interval-s", type=float, default=10.0, help="How often to print live summary")
    parser.add_argument(
        "--csv",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Enable or disable CSV trace output",
    )
    parser.add_argument(
        "--live-report",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Enable or disable periodic live summary output",
    )
    parser.add_argument("--obj-address", type=int, default=1, help="Protocol object address")
    parser.add_argument("--main-motor-rpm-scale", type=float, default=DEFAULT_MAIN_MOTOR_RPM_SCALE, help="Thrust to RPM scale")
    parser.add_argument("--side-motor-rpm", type=int, default=0, help="Side motor RPM to embed in outgoing frames")
    parser.add_argument("--seed", type=int, default=None, help="Seed for the conflict profile RNG")
    parser.add_argument("--csv-path", type=Path, default=None, help="CSV report path; defaults to log/attacker_station_<ts>.csv")
    return parser.parse_args()


def profile_default_rate_hz(profile: str) -> float:
    if profile == "heartbeat":
        return 1.0
    if profile == "sweep":
        return 1.0
    return 2.0


def _make_parameters(sequence_index: int) -> tuple[int, ...]:
    timestamp_us = int(time.time() * 1_000_000)
    return (timestamp_us, sequence_index, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)


def build_profile_payload(profile: str, sequence_index: int, rng: random.Random, config: AttackerStationConfig) -> dict[str, Any]:
    frame_number = sequence_index % 256
    payload: dict[str, Any] = {
        KEY_FRAME_NUMBER: frame_number,
        KEY_OBJ_ADDRESS: config.obj_address,
        KEY_PARAMETERS: _make_parameters(sequence_index),
        KEY_SIDE_MOTOR_RPM: config.side_motor_rpm,
    }

    if profile == "heartbeat":
        payload.update(
            {
                KEY_CONTROL_MODE_BYTE: int(ControlModeByte.SEND_ONLY),
                KEY_WORK_INSTRUCTION: int(WorkInstruction.NONE),
                KEY_RIGHT: 0.0,
                KEY_LEFT: 0.0,
                KEY_TOP: 0.0,
                KEY_BOTTOM: 0.0,
                KEY_THRUST: 0.0,
                KEY_ORIENTATION_DEG: 0.0,
            }
        )
        return payload

    if profile == "sweep":
        case = SWEEP_CASES[sequence_index % len(SWEEP_CASES)]
        payload.update({key: value for key, value in case.items() if key != "label"})
        payload[KEY_ORIENTATION_DEG] = float(case[KEY_ORIENTATION_DEG])
        payload[KEY_SIDE_MOTOR_RPM] = int(case[KEY_SIDE_MOTOR_RPM])
        payload[KEY_PARAMETERS] = (sequence_index, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
        return payload

    control_mode_byte = rng.choice(
        [
            int(ControlModeByte.REMOTE_CONTROL),
            int(ControlModeByte.AUTO_FIXED_POINT),
            int(ControlModeByte.AUTO_DIRECTION),
            int(ControlModeByte.JETSON_PROTOCOL),
        ]
    )
    right = rng.uniform(-85.0, 85.0)
    left = -right + rng.uniform(-5.0, 5.0)
    top = rng.uniform(-60.0, 60.0)
    bottom = -top + rng.uniform(-4.0, 4.0)
    thrust = rng.uniform(-100.0, 100.0)
    work_instruction = rng.choice(
        [int(WorkInstruction.NONE), int(WorkInstruction.AUTONOMOUS_CONTROL), int(WorkInstruction.TASK_START)]
    )
    payload.update(
        {
            KEY_CONTROL_MODE_BYTE: control_mode_byte,
            KEY_WORK_INSTRUCTION: work_instruction,
            KEY_RIGHT: right,
            KEY_LEFT: left,
            KEY_TOP: top,
            KEY_BOTTOM: bottom,
            KEY_THRUST: thrust,
            KEY_ORIENTATION_DEG: rng.uniform(0.0, 360.0),
            KEY_SIDE_MOTOR_RPM: int(rng.uniform(-180.0, 180.0)),
        }
    )
    return payload


def format_p99(values_ms: list[float]) -> float | None:
    if not values_ms:
        return None
    ordered = sorted(values_ms)
    index = int(math.ceil((len(ordered) - 1) * 0.99))
    index = min(max(index, 0), len(ordered) - 1)
    return ordered[index]


def format_summary(stats: StationStats, *, profile: str, elapsed_s: float) -> str:
    avg_rtt = statistics.fmean(stats.rtts_ms) if stats.rtts_ms else None
    p99_rtt = format_p99(stats.rtts_ms)
    avg_text = f"{avg_rtt:.1f}ms" if avg_rtt is not None else "n/a"
    p99_text = f"{p99_rtt:.1f}ms" if p99_rtt is not None else "n/a"
    return (
        f"[AttackerStation] Profile: {profile} | Elapsed: {elapsed_s:.1f}s | "
        f"Sent: {stats.sent} | Received: {stats.received} | Lost: {stats.lost} | "
        f"Avg RTT: {avg_text} | P99 RTT: {p99_text}"
    )


class AttackerStation:
    def __init__(self, config: AttackerStationConfig, sock: socket.socket, csv_path: Path | None = None) -> None:
        self.config = config
        self.sock = sock
        self.stats = StationStats()
        self.rng = random.Random(config.seed)
        self.csv_path = csv_path if csv_path is not None else config.csv_path
        self._csv_file: Any | None = None
        self._csv_writer: Any | None = None
        self._start_monotonic_s = time.monotonic()
        self._last_report_monotonic_s = self._start_monotonic_s
        self._send_started_perf_counter = self._start_monotonic_s

    def close(self) -> None:
        if self._csv_file is not None:
            self._csv_file.close()
            self._csv_file = None
            self._csv_writer = None

    def _ensure_csv_writer(self) -> Any | None:
        if not self.config.enable_csv or self.csv_path is None:
            return None
        if self._csv_writer is not None:
            return self._csv_writer

        self.csv_path.parent.mkdir(parents=True, exist_ok=True)
        file_exists = self.csv_path.exists()
        self._csv_file = self.csv_path.open("a", newline="", encoding="utf-8")
        fieldnames = [
            "timestamp_s",
            "profile",
            "sequence_index",
            "request_label",
            "control_mode_byte",
            "work_instruction",
            "right_deg",
            "left_deg",
            "top_deg",
            "bottom_deg",
            "thrust_percent",
            "rtt_ms",
            "response_received",
            "response_addr",
            "response_frame_number",
            "response_main_motor_rpm",
            "response_depth_m",
        ]
        self._csv_writer = csv.DictWriter(self._csv_file, fieldnames=fieldnames)
        if not file_exists:
            self._csv_writer.writeheader()
        return self._csv_writer

    def _await_response(self) -> tuple[bytes | None, tuple[str, int] | None, float | None]:
        self.sock.settimeout(self.config.response_timeout_s)
        try:
            response_packet, response_addr = self.sock.recvfrom(4096)
        except socket.timeout:
            return None, None, None
        rtt_ms = (time.perf_counter() - self._send_started_perf_counter) * 1000.0
        return response_packet, response_addr, rtt_ms

    def _log_sample(self, sample: AttackSample) -> None:
        csv_writer = self._ensure_csv_writer()
        if csv_writer is None:
            return
        csv_writer.writerow(
            {
                "timestamp_s": f"{sample.timestamp_s:.6f}",
                "profile": sample.profile,
                "sequence_index": sample.sequence_index,
                "request_label": sample.request_label or "",
                "control_mode_byte": sample.request_payload[KEY_CONTROL_MODE_BYTE],
                "work_instruction": sample.request_payload[KEY_WORK_INSTRUCTION],
                "right_deg": f"{float(sample.request_payload[KEY_RIGHT]):.3f}",
                "left_deg": f"{float(sample.request_payload[KEY_LEFT]):.3f}",
                "top_deg": f"{float(sample.request_payload[KEY_TOP]):.3f}",
                "bottom_deg": f"{float(sample.request_payload[KEY_BOTTOM]):.3f}",
                "thrust_percent": f"{float(sample.request_payload[KEY_THRUST]):.3f}",
                "rtt_ms": "timeout" if sample.rtt_ms is None else f"{sample.rtt_ms:.3f}",
                "response_received": str(sample.response_received).lower(),
                "response_addr": "" if sample.response_addr is None else f"{sample.response_addr[0]}:{sample.response_addr[1]}",
                "response_frame_number": "" if sample.response_frame_number is None else sample.response_frame_number,
                "response_main_motor_rpm": "" if sample.response_main_motor_rpm is None else sample.response_main_motor_rpm,
                "response_depth_m": "" if sample.response_depth_m is None else f"{sample.response_depth_m:.3f}",
            }
        )
        self._csv_file.flush()

    def _maybe_print_report(self, *, force: bool = False) -> None:
        if not self.config.enable_live_report:
            return
        now_monotonic_s = time.monotonic()
        elapsed_s = now_monotonic_s - self._start_monotonic_s
        if not force and (now_monotonic_s - self._last_report_monotonic_s) < self.config.report_interval_s:
            return
        self._last_report_monotonic_s = now_monotonic_s
        print(format_summary(self.stats, profile=self.config.profile, elapsed_s=elapsed_s))

    def send_one(self, sequence_index: int) -> AttackSample:
        payload = build_profile_payload(self.config.profile, sequence_index, self.rng, self.config)
        request_packet = build_downlink_packet_from_payload(payload, main_motor_rpm_scale=self.config.main_motor_rpm_scale)
        self._send_started_perf_counter = time.perf_counter()
        self.sock.sendto(request_packet, (self.config.mock_amd_host, self.config.mock_amd_port))
        response_packet, response_addr, rtt_ms = self._await_response()

        response_frame_number: int | None = None
        response_main_motor_rpm: int | None = None
        response_depth_m: float | None = None
        if response_packet is not None:
            try:
                telemetry = parse_uplink_packet(response_packet)
            except Exception:
                telemetry = None
            if telemetry is not None:
                response_frame_number = telemetry.frame_number
                response_main_motor_rpm = telemetry.main_motor_rpm
                response_depth_m = telemetry.depth_m

        sample = AttackSample(
            timestamp_s=time.time(),
            profile=self.config.profile,
            sequence_index=sequence_index,
            request_packet=request_packet,
            response_packet=response_packet,
            response_addr=response_addr,
            rtt_ms=rtt_ms,
            response_received=response_packet is not None,
            request_payload=payload,
            request_label=payload.get("label"),
            response_frame_number=response_frame_number,
            response_main_motor_rpm=response_main_motor_rpm,
            response_depth_m=response_depth_m,
        )
        self.stats.record(sample)
        self._log_sample(sample)
        return sample

    def run(self) -> StationStats:
        rate_hz = self.config.rate_hz if self.config.rate_hz is not None else profile_default_rate_hz(self.config.profile)
        interval_s = 0.0 if rate_hz <= 0 else 1.0 / rate_hz
        stop_requested = {"value": False}

        def _request_stop(signum, frame) -> None:
            stop_requested["value"] = True

        signal.signal(signal.SIGINT, _request_stop)
        signal.signal(signal.SIGTERM, _request_stop)

        sequence_index = 0
        run_forever = self.config.duration_s <= 0.0
        deadline_s = self._start_monotonic_s + self.config.duration_s

        try:
            while not stop_requested["value"]:
                if not run_forever and time.monotonic() >= deadline_s:
                    break
                loop_started_s = time.monotonic()
                self.send_one(sequence_index)
                sequence_index += 1
                self._maybe_print_report()
                elapsed_s = time.monotonic() - loop_started_s
                sleep_s = interval_s - elapsed_s
                if sleep_s > 0:
                    time.sleep(sleep_s)
        finally:
            self._maybe_print_report(force=True)
            self.close()
        return self.stats


def build_default_csv_path() -> Path:
    log_dir = PROJECT_ROOT / "log"
    log_dir.mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    return log_dir / f"attacker_station_{timestamp}.csv"


def main() -> int:
    args = parse_args()
    config = AttackerStationConfig(
        mock_amd_host=args.mock_amd_host,
        mock_amd_port=args.mock_amd_port,
        listen_host=args.listen_host,
        listen_port=args.listen_port,
        profile=args.profile,
        duration_s=args.duration,
        rate_hz=args.rate_hz,
        response_timeout_s=args.response_timeout_s,
        report_interval_s=args.report_interval_s,
        enable_csv=args.csv,
        enable_live_report=args.live_report,
        obj_address=args.obj_address,
        main_motor_rpm_scale=args.main_motor_rpm_scale,
        side_motor_rpm=args.side_motor_rpm,
        seed=args.seed,
        csv_path=None if not args.csv else (args.csv_path or build_default_csv_path()),
    )

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((config.listen_host, config.listen_port))
    print(
        f"[AttackerStation] listening on udp://{config.listen_host}:{config.listen_port}, "
        f"target udp://{config.mock_amd_host}:{config.mock_amd_port}, profile={config.profile}"
    )

    station = AttackerStation(config=config, sock=sock)
    try:
        station.run()
    finally:
        sock.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
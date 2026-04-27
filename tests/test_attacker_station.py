from __future__ import annotations

import importlib.util
import random
import socket
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ATTACKER_STATION_PATH = PROJECT_ROOT / "scripts" / "attacker_station.py"
ATTACKER_STATION_SPEC = importlib.util.spec_from_file_location("attacker_station", ATTACKER_STATION_PATH)
if ATTACKER_STATION_SPEC is None or ATTACKER_STATION_SPEC.loader is None:
    raise RuntimeError(f"Unable to load attacker_station from {ATTACKER_STATION_PATH}")
attacker_station = importlib.util.module_from_spec(ATTACKER_STATION_SPEC)
sys.modules[ATTACKER_STATION_SPEC.name] = attacker_station
ATTACKER_STATION_SPEC.loader.exec_module(attacker_station)

from common.enums import ControlModeByte
from common.protocol import (
    KEY_CONTROL_MODE_BYTE,
    KEY_FRAME_NUMBER,
    KEY_LEFT,
    KEY_RIGHT,
    KEY_THRUST,
    build_uplink_packet,
    parse_downlink_packet,
)

AttackerStation = attacker_station.AttackerStation
AttackerStationConfig = attacker_station.AttackerStationConfig
StationStats = attacker_station.StationStats
build_profile_payload = attacker_station.build_profile_payload
format_summary = attacker_station.format_summary


class FakeSocket:
    def __init__(self, responses: list[tuple[bytes, tuple[str, int]]]) -> None:
        self._responses = list(responses)
        self.sent_packets: list[tuple[bytes, tuple[str, int]]] = []
        self.timeout_s: float | None = None

    def settimeout(self, timeout_s: float) -> None:
        self.timeout_s = timeout_s

    def sendto(self, packet: bytes, addr: tuple[str, int]) -> int:
        self.sent_packets.append((packet, addr))
        return len(packet)

    def recvfrom(self, buffer_size: int):
        if not self._responses:
            raise socket.timeout()
        return self._responses.pop(0)

    def close(self) -> None:
        return None


def test_build_profile_payload_heartbeat_zeroes_controls() -> None:
    config = AttackerStationConfig(obj_address=9, side_motor_rpm=12)
    payload = build_profile_payload("heartbeat", 7, random.Random(1), config)

    assert payload[KEY_FRAME_NUMBER] == 7
    assert payload[KEY_CONTROL_MODE_BYTE] == int(ControlModeByte.SEND_ONLY)
    assert payload[KEY_RIGHT] == 0.0
    assert payload[KEY_LEFT] == 0.0
    assert payload[KEY_THRUST] == 0.0


def test_build_profile_payload_sweep_cycles_boundary_case() -> None:
    config = AttackerStationConfig(obj_address=9, side_motor_rpm=12)
    payload = build_profile_payload("sweep", 3, random.Random(1), config)

    assert payload[KEY_FRAME_NUMBER] == 3
    assert payload[KEY_RIGHT] == 120.0
    assert payload[KEY_LEFT] == -120.0
    assert payload[KEY_THRUST] == 150.0


def test_parse_args_supports_feature_switches(monkeypatch) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        ["attacker_station.py", "--no-csv", "--no-live-report", "--profile", "heartbeat"],
    )

    args = attacker_station.parse_args()

    assert args.csv is False
    assert args.live_report is False
    assert args.profile == "heartbeat"


def test_transact_once_sends_real_protocol_frame_and_parses_response(monkeypatch, tmp_path) -> None:
    response_packet = build_uplink_packet(
        frame_counter=7,
        auv_address=1,
        control_mode_byte=int(ControlModeByte.REMOTE_CONTROL),
        main_motor_rpm=42,
        depth_m=8.5,
    )
    fake_socket = FakeSocket([(response_packet, ("127.0.0.1", 52364))])
    config = AttackerStationConfig(
        mock_amd_host="127.0.0.1",
        mock_amd_port=52364,
        profile="heartbeat",
        duration_s=1.0,
        rate_hz=1.0,
        response_timeout_s=0.1,
        csv_path=tmp_path / "attacker.csv",
        seed=1,
    )
    station = AttackerStation(config=config, sock=fake_socket, csv_path=config.csv_path)

    perf_counter_values = iter([100.0, 100.025])
    monkeypatch.setattr("attacker_station.time.perf_counter", lambda: next(perf_counter_values))
    monkeypatch.setattr("attacker_station.time.time", lambda: 1234.5)

    sample = station.send_one(0)

    assert len(fake_socket.sent_packets) == 1
    request_packet, addr = fake_socket.sent_packets[0]
    assert addr == ("127.0.0.1", 52364)
    decoded = parse_downlink_packet(request_packet)
    assert decoded.frame_number == 0
    assert decoded.control_mode_byte == int(ControlModeByte.SEND_ONLY)
    assert sample.response_received is True
    assert sample.response_frame_number == 7
    assert sample.response_main_motor_rpm == 42
    assert sample.response_depth_m == 8.5


def test_transact_once_skips_csv_when_disabled(monkeypatch, tmp_path) -> None:
    response_packet = build_uplink_packet(
        frame_counter=7,
        auv_address=1,
        control_mode_byte=int(ControlModeByte.REMOTE_CONTROL),
        main_motor_rpm=42,
        depth_m=8.5,
    )
    fake_socket = FakeSocket([(response_packet, ("127.0.0.1", 52364))])
    csv_path = tmp_path / "attacker.csv"
    config = AttackerStationConfig(
        mock_amd_host="127.0.0.1",
        mock_amd_port=52364,
        profile="heartbeat",
        duration_s=1.0,
        rate_hz=1.0,
        response_timeout_s=0.1,
        csv_path=csv_path,
        enable_csv=False,
        enable_live_report=False,
        seed=1,
    )
    station = AttackerStation(config=config, sock=fake_socket, csv_path=config.csv_path)

    perf_counter_values = iter([100.0, 100.025])
    monkeypatch.setattr("attacker_station.time.perf_counter", lambda: next(perf_counter_values))
    monkeypatch.setattr("attacker_station.time.time", lambda: 1234.5)

    sample = station.send_one(0)

    assert sample.response_received is True
    assert not csv_path.exists()


def test_format_summary_reports_percentiles() -> None:
    stats = StationStats(sent=3, received=2, rtts_ms=[10.0, 30.0])

    text = format_summary(stats, profile="conflict", elapsed_s=12.3)

    assert "conflict" in text
    assert "Sent: 3" in text
    assert "Received: 2" in text
    assert "Lost: 1" in text
    assert "Avg RTT: 20.0ms" in text
    assert "P99 RTT: 30.0ms" in text
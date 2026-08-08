from __future__ import annotations

import socket
import sys
from pathlib import Path

import numpy as np

INTERFACES_DIR = Path(__file__).resolve().parents[1] / "sim_holoocean" / "interfaces"
if str(INTERFACES_DIR) not in sys.path:
    sys.path.insert(0, str(INTERFACES_DIR))

import mock_amd_server as mock_amd_server_module
from common.enums import ControlModeByte, WorkInstruction
from common.protocol import (
    KEY_BOTTOM,
    KEY_LEFT,
    KEY_RIGHT,
    KEY_TOP,
    KEY_THRUST,
    build_downlink_packet,
    parse_uplink_packet,
)
from mock_amd_server import MockAmdUdpServer


class DummyCommandGuard:
    def sanitize(self, last_cmd_msg, last_cmd, last_cmd_ts):
        return last_cmd


class FakeSocket:
    def __init__(self, packets: list[tuple[bytes, tuple[str, int]]]) -> None:
        self._packets = list(packets)
        self.sent_packets: list[tuple[bytes, tuple[str, int]]] = []

    def recvfrom(self, buffer_size: int):
        if not self._packets:
            raise socket.timeout()
        return self._packets.pop(0)

    def sendto(self, packet: bytes, addr: tuple[str, int]):
        self.sent_packets.append((packet, addr))
        return len(packet)

    def close(self) -> None:
        return None


def _make_config(mock_amd: dict | None = None) -> dict:
    return {
        "simulation": {
            "agent_name": "auv0",
            "show_viewport": False,
            "verbose": False,
        },
        "bridge": {
            "rate_hz": 50.0,
            "default_command": [0.0, 0.0, 0.0, 0.0, 0.0],
            "protocol_udp": {
                "bind_host": "127.0.0.1",
                "bind_port": 0,
                "remote_host": "127.0.0.1",
                "remote_port": 52365,
                "socket_timeout_s": 0.01,
                "recv_buffer_size": 2048,
                "main_motor_rpm_scale": 10.0,
                "side_motor_rpm": 0,
                "auv_address": 1,
                "default_control_mode_byte": int(ControlModeByte.JETSON_PROTOCOL),
                "telemetry_total_voltage_v": 48.0,
                "telemetry_total_current_a": 12.0,
                "telemetry_soc": 100,
                "telemetry_soh": 100,
                "sniffer_mirror_host": "127.0.0.1",
                "sniffer_mirror_port": 0,
                "log_packets": False,
                "log_packet_hex": False,
                "log_hex_bytes": 48,
                "log_every_n": 1,
            },
        },
        "digital_twin": {
            "seabed_z_m": 15.0,
        },
        "mock_amd": mock_amd or {},
    }


def _install_state_hooks(monkeypatch, *, heading_deg: float, dvl_speed_mps: float, depth_m: float) -> dict[str, float]:
    state_holder = {
        "heading_deg": heading_deg,
        "dvl_speed_mps": dvl_speed_mps,
        "depth_m": depth_m,
    }

    monkeypatch.setattr(
        mock_amd_server_module,
        "get_agent_state",
        lambda raw_state, agent_name: {
            "PoseSensor": np.eye(4, dtype=float),
            "DVLSensor": np.array([state_holder["dvl_speed_mps"], 0.0, 0.0], dtype=float),
            "DepthSensor": np.array([state_holder["depth_m"]], dtype=float),
        },
    )
    monkeypatch.setattr(
        mock_amd_server_module,
        "pose_matrix_ue_to_ned",
        lambda pose: {
            "position_ned": np.array([0.0, 0.0, state_holder["depth_m"]], dtype=float),
            "rpy_ned": np.radians(np.array([0.0, 0.0, state_holder["heading_deg"]], dtype=float)),
        },
    )
    monkeypatch.setattr(
        mock_amd_server_module,
        "extract_body_velocity",
        lambda dvl: np.array([state_holder["dvl_speed_mps"], 0.0, 0.0], dtype=float),
    )
    monkeypatch.setattr(
        mock_amd_server_module,
        "body_vector_ue_to_ned",
        lambda vec: np.asarray(vec, dtype=float),
    )
    monkeypatch.setattr(
        mock_amd_server_module,
        "extract_depth",
        lambda depth_sensor, pose_z: float(np.asarray(depth_sensor, dtype=float)[0]),
    )
    return state_holder


def _make_downlink_packet() -> bytes:
    return build_downlink_packet(
        {
            KEY_RIGHT: 1.5,
            KEY_TOP: -2.5,
            KEY_LEFT: 3.5,
            KEY_BOTTOM: -4.5,
            KEY_THRUST: 5.5,
        },
        frame_counter=7,
        obj_address=9,
        control_mode_byte=int(ControlModeByte.REMOTE_CONTROL),
        work_instruction=int(WorkInstruction.AUTONOMOUS_CONTROL),
        orientation_deg=12.3,
        main_motor_rpm_scale=10.0,
        side_motor_rpm=42,
        parameter_values=(0,) * 12,
    )


def test_init_enables_mock_components() -> None:
    server = MockAmdUdpServer(
        _make_config(
            {
                "transport_delay_ms": 100.0,
                "transport_jitter_ms": 0.0,
                "sensor_clocks": {"imu_hz": 1.0, "dvl_hz": 1.0, "depth_hz": 1.0, "mag_hz": 1.0},
                "chaos": {
                    "enabled": True,
                    "imu_drift_enabled": True,
                },
            }
        ),
        DummyCommandGuard(),
    )

    assert server._delay_queue is not None
    assert server._sensor_cache is not None
    assert server._chaos is not None


def test_protocol_logging_defaults_to_single_line_2hz() -> None:
    config = _make_config()
    config["bridge"]["protocol_udp"].update(
        {
            "log_ascii_format": True,
            "log_every_n": 1,
        }
    )

    server = MockAmdUdpServer(config, DummyCommandGuard())

    assert server.log_rate_hz == 2.0
    assert server.log_every_n == 25
    assert server.log_ascii_format is False
    assert server.allow_multiline_logs is False


def test_protocol_logging_allows_explicit_multiline_debug() -> None:
    config = _make_config()
    config["bridge"]["protocol_udp"].update(
        {
            "log_rate_hz": 5.0,
            "log_ascii_format": True,
            "allow_multiline_logs": True,
            "log_fixed_block_lines": 48,
        }
    )

    server = MockAmdUdpServer(config, DummyCommandGuard())

    assert server.log_every_n == 10
    assert server.log_ascii_format is True


def test_protocol_verbose_blocks_keep_fixed_line_count() -> None:
    config = _make_config()
    config["bridge"]["protocol_udp"].update(
        {
            "log_ascii_format": True,
            "allow_multiline_logs": True,
            "log_fixed_block_lines": 48,
        }
    )
    server = MockAmdUdpServer(config, DummyCommandGuard())

    uplink_packet = server._build_uplink_packet(
        {
            "auv0": {
                "PoseSensor": np.eye(4, dtype=float),
                "DVLSensor": np.zeros(3, dtype=float),
                "DepthSensor": np.array([8.0], dtype=float),
            }
        },
        1,
        np.zeros(5, dtype=float),
    )
    downlink_packet = _make_downlink_packet()

    assert len(server._format_fixed_verbose_packet(
        uplink_packet,
        label="mock-amd TX",
        source="127.0.0.1:52365",
        step=1,
        mode_tag="AUTO",
    ).splitlines()) == 48
    assert len(server._format_fixed_verbose_packet(
        downlink_packet,
        label="mock-amd RX",
        source="127.0.0.1:52365",
        step=None,
        mode_tag="RX",
    ).splitlines()) == 48


def test_protocol_rx_logging_is_rate_limited(monkeypatch) -> None:
    config = _make_config()
    config["bridge"]["protocol_udp"].update({"log_rate_hz": 2.0})
    server = MockAmdUdpServer(config, DummyCommandGuard())

    current_time = [1000.0]
    monkeypatch.setattr(mock_amd_server_module.time, "time", lambda: current_time[0])

    assert server._should_log_rx_packet() is True
    current_time[0] = 1000.1
    assert server._should_log_rx_packet() is False
    current_time[0] = 1000.5
    assert server._should_log_rx_packet() is True


def test_poll_command_packet_drains_delayed_commands(monkeypatch) -> None:
    server = MockAmdUdpServer(
        _make_config({"transport_delay_ms": 100.0, "transport_jitter_ms": 0.0}),
        DummyCommandGuard(),
    )
    server.sock = FakeSocket([(_make_downlink_packet(), ("127.0.0.1", 50123))])

    current_time = [1000.0]
    monkeypatch.setattr(mock_amd_server_module.time, "time", lambda: current_time[0])

    server._poll_command_packet()
    assert server.last_cmd_msg is None
    assert server._delay_queue is not None
    assert server._delay_queue.peek_count() == 1

    current_time[0] = 1000.2
    server._poll_command_packet()

    assert server.last_client_addr == ("127.0.0.1", 50123)
    assert server.last_cmd_msg == {
        "right": 1.5,
        "top": -2.5,
        "left": 3.5,
        "bottom": -4.5,
        "thrust": 5.5,
    }
    assert server._delay_queue.peek_count() == 0


def test_build_uplink_packet_uses_sensor_cache(monkeypatch) -> None:
    server = MockAmdUdpServer(
        _make_config({"sensor_clocks": {"imu_hz": 1.0, "dvl_hz": 1.0, "depth_hz": 1.0, "mag_hz": 1.0}}),
        DummyCommandGuard(),
    )
    state_holder = _install_state_hooks(monkeypatch, heading_deg=10.0, dvl_speed_mps=2.0, depth_m=8.0)
    server._start_time = 99.0
    monkeypatch.setattr(mock_amd_server_module.time, "time", lambda: 100.0)

    packet1 = server._build_uplink_packet({}, 1, np.array([0.0, 0.0, 0.0, 0.0, 5.0], dtype=float))
    parsed1 = parse_uplink_packet(packet1)
    assert parsed1.heading_deg == 10.0
    assert parsed1.dvl_speed_mps == 2.0
    assert parsed1.depth_m == 8.0
    assert parsed1.pc104_time_valid is True
    assert parsed1.pc104_uptime_ms == 1000
    assert parsed1.pc104_dvl_bi_time_valid is True
    assert parsed1.pc104_dvl_bi_uptime_ms == parsed1.pc104_uptime_ms

    state_holder["heading_deg"] = 90.0
    state_holder["dvl_speed_mps"] = 7.0
    state_holder["depth_m"] = 4.0
    monkeypatch.setattr(mock_amd_server_module.time, "time", lambda: 100.2)

    packet2 = server._build_uplink_packet({}, 2, np.array([0.0, 0.0, 0.0, 0.0, 5.0], dtype=float))
    parsed2 = parse_uplink_packet(packet2)
    assert parsed2.heading_deg == 10.0
    assert parsed2.dvl_speed_mps == 2.0
    assert parsed2.depth_m == 8.0
    assert parsed2.pc104_time_valid is True
    assert parsed2.pc104_uptime_ms == 1200
    assert parsed2.pc104_dvl_bi_time_valid is True
    assert parsed2.pc104_dvl_bi_uptime_ms == 1000


def test_build_uplink_packet_pc104_uptime_uses_elapsed_wall_time(monkeypatch) -> None:
    server = MockAmdUdpServer(_make_config(), DummyCommandGuard())
    _install_state_hooks(monkeypatch, heading_deg=10.0, dvl_speed_mps=2.0, depth_m=8.0)
    server._start_time = 100.0
    monkeypatch.setattr(mock_amd_server_module.time, "time", lambda: 101.25)

    packet = server._build_uplink_packet({}, 999, np.zeros(5, dtype=float))
    parsed = parse_uplink_packet(packet)

    assert parsed.pc104_time_valid is True
    assert parsed.pc104_uptime_ms == 1250
    assert parsed.pc104_uptime_ms != int(round(999.0 * server.dt * 1000.0))
    assert parsed.pc104_dvl_bi_time_valid is True
    assert parsed.pc104_dvl_bi_uptime_ms == 1250


def test_build_uplink_packet_applies_chaos(monkeypatch) -> None:
    server = MockAmdUdpServer(
        _make_config(
            {
                "chaos": {
                    "enabled": True,
                    "dvl_freeze_enabled": True,
                    "dvl_freeze_after_s": 0.0,
                    "imu_drift_enabled": True,
                    "imu_drift_rate_deg_per_s": 1.0,
                    "depth_spike_enabled": True,
                    "depth_spike_m": 2.0,
                    "depth_spike_after_s": 0.0,
                    "uplink_dropout_enabled": False,
                }
            }
        ),
        DummyCommandGuard(),
    )
    state_holder = _install_state_hooks(monkeypatch, heading_deg=10.0, dvl_speed_mps=2.0, depth_m=8.0)
    server._start_time = 95.0
    monkeypatch.setattr(mock_amd_server_module.time, "time", lambda: 100.0)

    packet1 = server._build_uplink_packet({}, 1, np.array([0.0, 0.0, 0.0, 0.0, 5.0], dtype=float))
    parsed1 = parse_uplink_packet(packet1)
    assert parsed1.heading_deg == 15.0
    assert parsed1.dvl_speed_mps == 2.0
    assert parsed1.depth_m == 10.0

    state_holder["heading_deg"] = 10.0
    state_holder["dvl_speed_mps"] = 7.0
    state_holder["depth_m"] = 5.0
    monkeypatch.setattr(mock_amd_server_module.time, "time", lambda: 102.0)

    packet2 = server._build_uplink_packet({}, 2, np.array([0.0, 0.0, 0.0, 0.0, 5.0], dtype=float))
    parsed2 = parse_uplink_packet(packet2)
    assert parsed2.heading_deg == 17.0
    assert parsed2.dvl_speed_mps == 2.0
    assert parsed2.depth_m == 7.0

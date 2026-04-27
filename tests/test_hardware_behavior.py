"""Hardware-behavior regression tests for controller and protocol mapping."""

# pyright: reportMissingImports=false

from __future__ import annotations

import math
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ALGORITHM_DIR = PROJECT_ROOT / "algorithm"
BRIDGE_SRC_DIR = PROJECT_ROOT / "brain_linux" / "src" / "auv_bridge"

for candidate in (ALGORITHM_DIR, BRIDGE_SRC_DIR):
    candidate_text = str(candidate)
    if candidate_text not in sys.path:
        sys.path.insert(0, candidate_text)

from auv_pid_controller import AUVPIDController
from auv_bridge.bridge_backends import ProtocolBridgeBackend
from common.enums import ControlModeByte, WorkInstruction
from common.protocol import (
    KEY_BOTTOM,
    KEY_CONTROL_MODE_BYTE,
    KEY_LEFT,
    KEY_MAIN_MOTOR_RPM,
    KEY_RIGHT,
    KEY_SIDE_MOTOR_RPM,
    KEY_THRUST,
    KEY_TOP,
    KEY_WORK_INSTRUCTION,
    parse_downlink_packet_to_payload,
)


def _make_controller() -> AUVPIDController:
    control_cfg = {
        "u0": 1.0,
        "u_min": 0.6,
        "target_u": 1.1,
        "feedforward_trim_deg": -1.5,
        "depth": {
            "kp": 0.30,
            "ki": 0.01,
            "kd": 0.0,
            "integral_limit": 4.0,
            "target_pitch_deg_max": 15.0,
            "target_pitch_rate_limit_deg_s": 8.0,
        },
        "pitch": {
            "kp": 6.5,
            "ki": 0.15,
            "kd": 2.2,
            "integral_limit": 45.0,
        },
        "yaw": {
            "kp": 9.0,
            "ki": 0.12,
            "kd": 1.4,
            "integral_limit": 45.0,
        },
        "speed": {
            "kp": 28.0,
            "ki": 1.4,
            "kd": 3.0,
            "integral_limit": 55.0,
            "feedforward": {"a": 2.497183, "b": 27.729751, "c": 0.546851},
        },
    }
    limits_cfg = {"fin_deg_max": 30.0, "thrust_min": -100.0, "thrust_max": 100.0}
    return AUVPIDController(control_cfg, limits_cfg)


class _FakeLogger:
    def warning(self, _message: str) -> None:
        return None


class _FakeNode:
    def get_logger(self) -> _FakeLogger:
        return _FakeLogger()


class _FakeSocket:
    def __init__(self) -> None:
        self.sent_packets: list[tuple[bytes, tuple[str, int]]] = []

    def sendto(self, packet: bytes, addr: tuple[str, int]) -> int:
        self.sent_packets.append((packet, addr))
        return len(packet)


def test_pid_depth_error_deflects_port_and_starboard_surfaces_in_opposite_directions() -> None:
    controller = _make_controller()
    state = {
        "roll": 0.0,
        "pitch": 0.0,
        "yaw": 0.0,
        "depth": 0.0,
        "u": 1.1,
        "q": 0.0,
        "r": 0.0,
    }

    command, debug = controller.compute(
        state,
        {
            "dt": 0.05,
            "target_depth": 10.0,
            "target_yaw": 0.0,
            "target_u": 1.1,
        },
    )

    assert command[0] > 0.0
    assert command[2] < 0.0
    assert math.isclose(command[0], -command[2], rel_tol=1e-6, abs_tol=1e-6)
    assert math.isclose(command[1], 0.0, abs_tol=1e-9)
    assert math.isclose(command[3], 0.0, abs_tol=1e-9)
    assert debug["target_pitch_rad"] > 0.0


def test_pid_yaw_error_deflects_horizontal_surfaces_in_opposite_directions() -> None:
    controller = _make_controller()
    state = {
        "roll": 0.0,
        "pitch": 0.0,
        "yaw": 0.0,
        "depth": 4.0,
        "u": 1.1,
        "q": 0.0,
        "r": 0.0,
    }

    command, debug = controller.compute(
        state,
        {
            "dt": 0.05,
            "target_depth": 4.0,
            "target_yaw": 0.01,
            "target_u": 1.1,
        },
    )

    assert command[1] < 0.0
    assert command[3] > 0.0
    assert math.isclose(command[1], -command[3], rel_tol=1e-6, abs_tol=1e-6)
    assert command[0] > 0.0
    assert command[2] < 0.0
    assert math.isclose(command[0], -command[2], rel_tol=1e-6, abs_tol=1e-6)
    assert debug["yaw_error"] > 0.0


def test_protocol_backend_scales_thrust_percent_to_main_motor_rpm() -> None:
    backend = ProtocolBridgeBackend(
        node=_FakeNode(),
        bridge_cfg={
            "protocol_udp": {
                "obj_address": 5,
                "main_motor_rpm_scale": 10.0,
            },
            "arbiter": {},
        },
    )
    backend._socket = _FakeSocket()

    backend.send_command(
        {
            KEY_RIGHT: 1.5,
            KEY_TOP: -2.5,
            KEY_LEFT: 3.5,
            KEY_BOTTOM: -4.5,
            KEY_THRUST: 12.0,
        },
        control_mode_byte=int(ControlModeByte.REMOTE_CONTROL),
        work_instruction=int(WorkInstruction.NONE),
        orientation_deg=12.5,
    )

    assert len(backend._socket.sent_packets) == 1
    packet, addr = backend._socket.sent_packets[0]
    assert addr == ("127.0.0.1", 52364)

    decoded = parse_downlink_packet_to_payload(packet, main_motor_rpm_scale=10.0)
    assert decoded[KEY_CONTROL_MODE_BYTE] == int(ControlModeByte.REMOTE_CONTROL)
    assert decoded[KEY_WORK_INSTRUCTION] == int(WorkInstruction.NONE)
    assert decoded[KEY_RIGHT] == 1.5
    assert decoded[KEY_TOP] == -2.5
    assert decoded[KEY_LEFT] == 3.5
    assert decoded[KEY_BOTTOM] == -4.5
    assert decoded[KEY_THRUST] == 12.0
    assert decoded[KEY_MAIN_MOTOR_RPM] == 120
    assert decoded[KEY_SIDE_MOTOR_RPM] == 0

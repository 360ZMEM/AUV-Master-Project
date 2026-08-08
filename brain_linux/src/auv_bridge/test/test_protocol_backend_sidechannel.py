from __future__ import annotations

from auv_bridge.bridge_backends import ProtocolBridgeBackend
from common.enums import ControlModeByte, WorkInstruction
from common.protocol import (
    KEY_BOTTOM,
    KEY_CONTROL_MODE_BYTE,
    KEY_LEFT,
    KEY_OBJ_ADDRESS,
    KEY_RIGHT,
    KEY_THRUST,
    KEY_TOP,
    KEY_WORK_INSTRUCTION,
    build_downlink_packet_from_payload,
    map_pc104_uptime_to_ros_seconds,
)


class _FakeLogger:
    def warning(self, _message: str) -> None:
        return None


class _FakeNode:
    def get_logger(self) -> _FakeLogger:
        return _FakeLogger()


def test_protocol_backend_decodes_raw_pc_cmd_payload() -> None:
    backend = ProtocolBridgeBackend(
        node=_FakeNode(),
        bridge_cfg={
            'protocol_udp': {
                'obj_address': 5,
                'main_motor_rpm_scale': 10.0,
            },
            'arbiter': {},
        },
    )

    packet = build_downlink_packet_from_payload(
        {
            KEY_OBJ_ADDRESS: 5,
            KEY_CONTROL_MODE_BYTE: int(ControlModeByte.REMOTE_CONTROL),
            KEY_WORK_INSTRUCTION: int(WorkInstruction.NONE),
            KEY_RIGHT: 1.5,
            KEY_TOP: -2.5,
            KEY_LEFT: 3.5,
            KEY_BOTTOM: -4.5,
            KEY_THRUST: 12.0,
        },
        main_motor_rpm_scale=10.0,
    )

    decoded = backend._decode_pc_raw_payload(packet)

    assert decoded is not None
    assert decoded[KEY_OBJ_ADDRESS] == 5
    assert decoded[KEY_CONTROL_MODE_BYTE] == int(ControlModeByte.REMOTE_CONTROL)
    assert decoded[KEY_WORK_INSTRUCTION] == int(WorkInstruction.NONE)
    assert decoded[KEY_RIGHT] == 1.5
    assert decoded[KEY_TOP] == -2.5
    assert decoded[KEY_LEFT] == 3.5
    assert decoded[KEY_BOTTOM] == -4.5
    assert decoded[KEY_THRUST] == 12.0


def test_protocol_pc104_uptime_maps_into_ros_time_domain() -> None:
    stamp_s, base_ms, base_ros_s, used = map_pc104_uptime_to_ros_seconds(
        pc104_uptime_ms=1000,
        pc104_time_valid=True,
        receive_time_s=50.0,
        base_pc104_uptime_ms=None,
        base_ros_time_s=None,
    )
    assert stamp_s == 50.0
    assert base_ms == 1000
    assert base_ros_s == 50.0
    assert used is True

    stamp_s, base_ms, base_ros_s, used = map_pc104_uptime_to_ros_seconds(
        pc104_uptime_ms=1250,
        pc104_time_valid=True,
        receive_time_s=50.9,
        base_pc104_uptime_ms=base_ms,
        base_ros_time_s=base_ros_s,
    )
    assert stamp_s == 50.25
    assert base_ms == 1000
    assert base_ros_s == 50.0
    assert used is True


def test_protocol_pc104_uptime_mapping_falls_back_for_legacy_frames() -> None:
    stamp_s, base_ms, base_ros_s, used = map_pc104_uptime_to_ros_seconds(
        pc104_uptime_ms=1250,
        pc104_time_valid=False,
        receive_time_s=50.9,
        base_pc104_uptime_ms=1000,
        base_ros_time_s=50.0,
    )
    assert stamp_s == 50.9
    assert base_ms == 1000
    assert base_ros_s == 50.0
    assert used is False


def test_protocol_pc104_uptime_mapping_allows_dvl_source_before_packet_time() -> None:
    stamp_s, base_ms, base_ros_s, used = map_pc104_uptime_to_ros_seconds(
        pc104_uptime_ms=980,
        pc104_time_valid=True,
        receive_time_s=50.9,
        base_pc104_uptime_ms=1000,
        base_ros_time_s=50.0,
        allow_before_base=True,
    )

    assert abs(stamp_s - 49.98) < 1.0e-9
    assert base_ms == 1000
    assert base_ros_s == 50.0
    assert used is True

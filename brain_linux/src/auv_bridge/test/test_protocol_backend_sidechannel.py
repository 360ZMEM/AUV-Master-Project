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
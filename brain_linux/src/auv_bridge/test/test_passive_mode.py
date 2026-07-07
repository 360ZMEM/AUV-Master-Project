from __future__ import annotations

import json
import math
from types import SimpleNamespace

from auv_bridge.arbiter import ArbiterDecision
from auv_bridge.bridge_node import AUVBridgeNode
from common.enums import ArbiterMode, ArbiterSource, BridgeBackend, ControlModeByte, WorkInstruction
from common.protocol import KEY_BOTTOM, KEY_CONTROL_MODE_BYTE, KEY_LEFT, KEY_ORIENTATION_DEG, KEY_RIGHT, KEY_THRUST, KEY_TOP, KEY_WORK_INSTRUCTION


class _DummyPublisher:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def publish(self, msg) -> None:
        self.messages.append(str(msg.data))


class _DummyTransport:
    requires_command_heartbeat = False

    def __init__(self) -> None:
        self.calls: list[tuple[dict[str, float], int, int, float]] = []

    def send_command(self, command_payload, *, control_mode_byte: int, work_instruction: int, orientation_deg: float) -> None:
        self.calls.append((dict(command_payload), control_mode_byte, work_instruction, orientation_deg))


def test_passive_mode_publishes_shadow_command_instead_of_transport() -> None:
    node = AUVBridgeNode.__new__(AUVBridgeNode)
    node.passive_mode = True
    node.backend = BridgeBackend.PROTOCOL_UDP
    node.protocol_control_mode_byte = int(ControlModeByte.JETSON_PROTOCOL)
    node.protocol_work_instruction = int(WorkInstruction.NONE)
    node.latest_setpoint = None
    node.shadow_cmd_pub = _DummyPublisher()
    node.transport = _DummyTransport()
    node._resolve_target_heading_deg = lambda: 12.5

    node._publish_command(
        {
            KEY_RIGHT: 1.0,
            KEY_TOP: 2.0,
            KEY_LEFT: 3.0,
            KEY_BOTTOM: 4.0,
            KEY_THRUST: 5.0,
        }
    )

    assert node.transport.calls == []
    assert len(node.shadow_cmd_pub.messages) == 1

    snapshot = json.loads(node.shadow_cmd_pub.messages[0])
    assert snapshot["kind"] == "command"
    assert snapshot["passive_mode"] is True
    assert snapshot["control_mode_byte"] == int(ControlModeByte.JETSON_PROTOCOL)
    assert snapshot["work_instruction"] == int(WorkInstruction.NONE)
    assert snapshot["orientation_deg"] == 12.5
    assert snapshot["payload"][KEY_RIGHT] == 1.0
    assert snapshot["payload"][KEY_THRUST] == 5.0


def test_autonomous_arbiter_uses_setpoint_heading_not_pc_heartbeat_zero() -> None:
    node = AUVBridgeNode.__new__(AUVBridgeNode)
    node.passive_mode = False
    node.backend = BridgeBackend.PROTOCOL_UDP
    node.latest_setpoint = SimpleNamespace(target_heading_rad=math.radians(-5.0))
    node.transport = _DummyTransport()
    node._publish_arbiter_status = lambda guard_decision=None: None

    decision = ArbiterDecision(
        active_arbiter=ArbiterMode.AUTONOMOUS,
        arbiter_source=ArbiterSource.JETSON_MPC,
        command_payload={
            KEY_CONTROL_MODE_BYTE: int(ControlModeByte.JETSON_PROTOCOL),
            KEY_WORK_INSTRUCTION: int(WorkInstruction.AUTONOMOUS_CONTROL),
            KEY_ORIENTATION_DEG: 0.0,
            KEY_THRUST: 10.0,
        },
        mpc_command_valid=True,
        manual_override_active=False,
    )

    node._publish_arbiter_decision(decision)

    assert len(node.transport.calls) == 1
    payload, control_mode_byte, work_instruction, orientation_deg = node.transport.calls[0]
    assert control_mode_byte == int(ControlModeByte.JETSON_PROTOCOL)
    assert work_instruction == int(WorkInstruction.AUTONOMOUS_CONTROL)
    assert orientation_deg == 355.0
    assert payload[KEY_ORIENTATION_DEG] == 355.0

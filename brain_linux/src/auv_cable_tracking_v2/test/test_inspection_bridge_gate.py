from __future__ import annotations

import time

from std_msgs.msg import Bool
from auv_interfaces.msg import Setpoint

from auv_bridge.arbiter import ArbiterDecision
from auv_cable_tracking_v2.inspection_bridge_node import InspectionBridgeNode
from common.enums import ArbiterMode, ArbiterSource, WorkInstruction
from common.protocol import (KEY_BOTTOM, KEY_LEFT, KEY_RIGHT, KEY_SIDE_MOTOR_RPM,
                             KEY_THRUST, KEY_TOP, KEY_WORK_INSTRUCTION)


class GateFixture:
    _budget_problem = InspectionBridgeNode._budget_problem
    _setpoint_problem = InspectionBridgeNode._setpoint_problem
    _inspection_authority_problem = InspectionBridgeNode._inspection_authority_problem
    _guard_autonomous_decision = InspectionBridgeNode._guard_autonomous_decision
    _on_budget_alarm = InspectionBridgeNode._on_budget_alarm

    def __init__(self):
        self._budget_timeout_s = 1.5
        self._budget_seen_wall_time_s = float('-inf')
        self._budget_latched = False
        self._setpoint_timeout_s = 0.5
        self._setpoint_seen_wall_time_s = time.monotonic()
        self.latest_setpoint = Setpoint()
        self.latest_setpoint.mode = 'CABLE_TRACKING'
        self.latest_setpoint.track_cable = True
        self.latest_setpoint.target_speed_mps = 0.3
        self.latest_setpoint.target_depth_m = 10.


def decision(mode=ArbiterMode.AUTONOMOUS):
    return ArbiterDecision(
        active_arbiter=mode, arbiter_source=ArbiterSource.JETSON_MPC,
        command_payload={KEY_THRUST: 25., KEY_LEFT: 2., KEY_RIGHT: 3.,
                         KEY_TOP: 4., KEY_BOTTOM: 5., KEY_SIDE_MOTOR_RPM: 120,
                         KEY_WORK_INSTRUCTION: 1},
        mpc_command_valid=True, manual_override_active=False,
    )


def test_missing_or_stale_budget_status_stops_autonomous_output():
    gate = GateFixture()
    stopped, reason = gate._guard_autonomous_decision(decision())
    assert reason == 'inspection_budget_status_stale'
    assert stopped.arbiter_source == ArbiterSource.SAFETY_FALLBACK
    assert not stopped.mpc_command_valid
    assert all(stopped.command_payload[key] == 0 for key in (
        KEY_THRUST, KEY_LEFT, KEY_RIGHT, KEY_TOP, KEY_BOTTOM,
        KEY_SIDE_MOTOR_RPM, KEY_WORK_INSTRUCTION))
    gate._on_budget_alarm(Bool(data=False))
    passed, reason = gate._guard_autonomous_decision(decision())
    assert reason is None and passed.command_payload[KEY_THRUST] == 25.
    gate._budget_seen_wall_time_s = time.monotonic() - 2.
    assert gate._guard_autonomous_decision(decision())[1] == 'inspection_budget_status_stale'


def test_true_alarm_latches_despite_later_false_message_and_preserves_manual():
    gate = GateFixture()
    gate._on_budget_alarm(Bool(data=True))
    gate._on_budget_alarm(Bool(data=False))
    stopped, reason = gate._guard_autonomous_decision(decision())
    assert reason == 'inspection_recovery_required'
    assert stopped.command_payload[KEY_THRUST] == 0.
    manual = decision(ArbiterMode.REMOTE)
    passed, reason = gate._guard_autonomous_decision(manual)
    assert reason is None and passed is manual


def test_independent_setpoint_freshness_and_hold_revoke_fresh_pid_command():
    gate = GateFixture()
    gate._on_budget_alarm(Bool(data=False))
    passed, reason = gate._guard_autonomous_decision(decision())
    assert reason is None and passed.command_payload[KEY_THRUST] == 25.

    gate._setpoint_seen_wall_time_s -= 0.6
    stopped, reason = gate._guard_autonomous_decision(decision())
    assert reason == 'inspection_setpoint_stale'
    assert stopped.command_payload[KEY_THRUST] == 0.
    assert not stopped.mpc_command_valid

    gate._setpoint_seen_wall_time_s = time.monotonic()
    gate.latest_setpoint.mode = 'CABLE_TRACKING_DEGRADED_HOLD'
    gate.latest_setpoint.track_cable = False
    stopped, reason = gate._guard_autonomous_decision(decision())
    assert reason == 'inspection_setpoint_hold'
    assert stopped.command_payload[KEY_THRUST] == 0.
    manual = decision(ArbiterMode.REMOTE)
    passed, reason = gate._guard_autonomous_decision(manual)
    assert reason is None and passed is manual


def test_shutdown_instruction_survives_autonomous_stop_gate():
    gate = GateFixture()
    gate._on_budget_alarm(Bool(data=True))
    cancel = decision()
    cancel.command_payload[KEY_WORK_INSTRUCTION] = int(WorkInstruction.TASK_CANCEL)
    stopped, reason = gate._guard_autonomous_decision(cancel)
    assert reason == 'inspection_recovery_required'
    assert stopped.command_payload[KEY_WORK_INSTRUCTION] == int(WorkInstruction.TASK_CANCEL)
    assert stopped.command_payload[KEY_THRUST] == 0.

'''
本文件包含了针对 AUV 桥接节点的 CommandArbiter 类的单元测试，验证了在不同输入条件下仲裁逻辑的正确性和预期行为。测试覆盖了以下场景：
- 远程模式下 PC 原始命令的正确传递
- 自主模式下 MPC 命令对控制面和推力的覆盖
- 手动覆盖时立即切换到远程模式
- 自主模式下 MPC 超时后使用安全回退命令
- 强制远程时将自主请求重写为远程控制命令
每个测试函数都创建了一个 CommandArbiter 实例，模拟输入命令并检查输出决策是否符合预期的仲裁结果和命令内容。这些测试有助于确保 CommandArbiter 的核心逻辑在各种边界条件下都能正确运行，为桥接节点的稳定性和安全性提供保障。
'''

from __future__ import annotations

from auv_bridge.arbiter import CommandArbiter
from common.enums import ArbiterMode, ArbiterSource, ControlModeByte, WorkInstruction
from common.protocol import (
    KEY_BOTTOM,
    KEY_CONTROL_MODE_BYTE,
    KEY_DEPTH_PROTECT_PARAMS,
    KEY_LEFT,
    KEY_OBJ_ADDRESS,
    KEY_ORIENTATION_DEG,
    KEY_PARAMETERS,
    KEY_RIGHT,
    KEY_SIDE_MOTOR_RPM,
    KEY_THRUST,
    KEY_TOP,
    KEY_WORK_INSTRUCTION,
)


def test_remote_mode_passthroughs_pc_raw_command() -> None:
    arbiter = CommandArbiter(mpc_timeout_s=0.5, default_obj_address=7)

    decision = arbiter.update_pc_raw_command(
        {
            KEY_CONTROL_MODE_BYTE: int(ControlModeByte.REMOTE_CONTROL),
            KEY_WORK_INSTRUCTION: int(WorkInstruction.NONE),
            KEY_RIGHT: 1.0,
            KEY_TOP: 2.0,
            KEY_LEFT: 3.0,
            KEY_BOTTOM: 4.0,
            KEY_THRUST: 5.0,
            KEY_OBJ_ADDRESS: 9,
            KEY_SIDE_MOTOR_RPM: 11,
            KEY_ORIENTATION_DEG: 12.0,
            KEY_DEPTH_PROTECT_PARAMS: (13, 14),
            KEY_PARAMETERS: (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12),
        },
        now=10.0,
    )

    assert decision.active_arbiter == ArbiterMode.REMOTE
    assert decision.arbiter_source == ArbiterSource.PC_RAW
    assert decision.command_payload[KEY_RIGHT] == 1.0
    assert decision.command_payload[KEY_TOP] == 2.0
    assert decision.command_payload[KEY_LEFT] == 3.0
    assert decision.command_payload[KEY_BOTTOM] == 4.0
    assert decision.command_payload[KEY_THRUST] == 5.0
    assert decision.command_payload[KEY_OBJ_ADDRESS] == 9
    assert decision.command_payload[KEY_SIDE_MOTOR_RPM] == 11


def test_autonomous_mode_overrides_control_surfaces_and_thrust() -> None:
    arbiter = CommandArbiter(mpc_timeout_s=0.5, default_obj_address=1)

    arbiter.update_pc_raw_command(
        {
            KEY_CONTROL_MODE_BYTE: int(ControlModeByte.JETSON_PROTOCOL),
            KEY_WORK_INSTRUCTION: int(WorkInstruction.NONE),
            KEY_RIGHT: 1.0,
            KEY_TOP: 2.0,
            KEY_LEFT: 3.0,
            KEY_BOTTOM: 4.0,
            KEY_THRUST: 5.0,
            KEY_OBJ_ADDRESS: 2,
            KEY_SIDE_MOTOR_RPM: 33,
            KEY_ORIENTATION_DEG: 15.0,
            KEY_DEPTH_PROTECT_PARAMS: (100, 200),
            KEY_PARAMETERS: (1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1),
        },
        now=20.0,
    )

    decision = arbiter.update_mpc_command(
        {
            "right_fin_deg": -6.0,
            "top_fin_deg": -7.0,
            "left_fin_deg": -8.0,
            "bottom_fin_deg": -9.0,
            "thrust_percent": 10.0,
            "valid": True,
            "healthy": True,
        },
        now=20.1,
    )

    assert decision.active_arbiter == ArbiterMode.AUTONOMOUS
    assert decision.arbiter_source == ArbiterSource.JETSON_MPC
    assert decision.command_payload[KEY_CONTROL_MODE_BYTE] == int(ControlModeByte.JETSON_PROTOCOL)
    assert decision.command_payload[KEY_WORK_INSTRUCTION] == int(WorkInstruction.AUTONOMOUS_CONTROL)
    assert decision.command_payload[KEY_RIGHT] == -6.0
    assert decision.command_payload[KEY_TOP] == -7.0
    assert decision.command_payload[KEY_LEFT] == -8.0
    assert decision.command_payload[KEY_BOTTOM] == -9.0
    assert decision.command_payload[KEY_THRUST] == 10.0
    assert decision.command_payload[KEY_OBJ_ADDRESS] == 2
    assert decision.command_payload[KEY_SIDE_MOTOR_RPM] == 33
    assert decision.command_payload[KEY_ORIENTATION_DEG] == 15.0


def test_manual_override_forces_remote_mode_immediately() -> None:
    arbiter = CommandArbiter(mpc_timeout_s=0.5)

    arbiter.update_pc_raw_command(
        {
            KEY_CONTROL_MODE_BYTE: int(ControlModeByte.JETSON_PROTOCOL),
            KEY_WORK_INSTRUCTION: int(WorkInstruction.NONE),
            KEY_RIGHT: 1.0,
            KEY_TOP: 1.0,
            KEY_LEFT: 1.0,
            KEY_BOTTOM: 1.0,
            KEY_THRUST: 1.0,
        },
        now=30.0,
    )
    arbiter.update_mpc_command(
        {
            "right_fin_deg": 5.0,
            "top_fin_deg": 5.0,
            "left_fin_deg": 5.0,
            "bottom_fin_deg": 5.0,
            "thrust_percent": 5.0,
        },
        now=30.1,
    )

    decision = arbiter.update_pc_raw_command(
        {
            KEY_CONTROL_MODE_BYTE: int(ControlModeByte.REMOTE_CONTROL),
            KEY_WORK_INSTRUCTION: int(WorkInstruction.CLEAR_FAULT),
            KEY_RIGHT: 2.0,
            KEY_TOP: 3.0,
            KEY_LEFT: 4.0,
            KEY_BOTTOM: 5.0,
            KEY_THRUST: 6.0,
        },
        now=30.2,
    )

    assert decision.active_arbiter == ArbiterMode.REMOTE
    assert decision.arbiter_source == ArbiterSource.PC_RAW
    assert decision.manual_override_active is True
    assert decision.command_payload[KEY_WORK_INSTRUCTION] == int(WorkInstruction.CLEAR_FAULT)
    assert decision.command_payload[KEY_THRUST] == 6.0


def test_autonomous_mode_uses_safety_fallback_after_timeout() -> None:
    arbiter = CommandArbiter(mpc_timeout_s=0.5)

    arbiter.update_pc_raw_command(
        {
            KEY_CONTROL_MODE_BYTE: int(ControlModeByte.JETSON_PROTOCOL),
            KEY_WORK_INSTRUCTION: int(WorkInstruction.NONE),
            KEY_RIGHT: 9.0,
            KEY_TOP: 8.0,
            KEY_LEFT: 7.0,
            KEY_BOTTOM: 6.0,
            KEY_THRUST: 5.0,
            KEY_OBJ_ADDRESS: 4,
        },
        now=40.0,
    )
    arbiter.update_mpc_command(
        {
            "right_fin_deg": 1.0,
            "top_fin_deg": 1.0,
            "left_fin_deg": 1.0,
            "bottom_fin_deg": 1.0,
            "thrust_percent": 1.0,
            "valid": True,
            "healthy": True,
        },
        now=40.1,
    )

    decision = arbiter.decide(now=40.8)

    assert decision.active_arbiter == ArbiterMode.AUTONOMOUS
    assert decision.arbiter_source == ArbiterSource.SAFETY_FALLBACK
    assert decision.mpc_command_valid is False
    assert decision.command_payload[KEY_CONTROL_MODE_BYTE] == int(ControlModeByte.JETSON_PROTOCOL)
    assert decision.command_payload[KEY_WORK_INSTRUCTION] == int(WorkInstruction.AUTONOMOUS_CONTROL)
    assert decision.command_payload[KEY_RIGHT] == 0.0
    assert decision.command_payload[KEY_TOP] == 0.0
    assert decision.command_payload[KEY_LEFT] == 0.0
    assert decision.command_payload[KEY_BOTTOM] == 0.0
    assert decision.command_payload[KEY_THRUST] == 0.0
    assert decision.command_payload[KEY_OBJ_ADDRESS] == 4


def test_force_remote_rewrites_autonomous_request_to_remote() -> None:
    arbiter = CommandArbiter(mpc_timeout_s=0.5)

    arbiter.update_pc_raw_command(
        {
            KEY_CONTROL_MODE_BYTE: int(ControlModeByte.JETSON_PROTOCOL),
            KEY_WORK_INSTRUCTION: int(WorkInstruction.AUTONOMOUS_CONTROL),
            KEY_RIGHT: 7.0,
            KEY_TOP: 6.0,
            KEY_LEFT: 5.0,
            KEY_BOTTOM: 4.0,
            KEY_THRUST: 3.0,
        },
        now=50.0,
    )

    decision = arbiter.force_remote(now=50.1)

    assert decision.active_arbiter == ArbiterMode.REMOTE
    assert decision.arbiter_source == ArbiterSource.PC_RAW
    assert decision.command_payload[KEY_CONTROL_MODE_BYTE] == int(ControlModeByte.REMOTE_CONTROL)
    assert decision.command_payload[KEY_WORK_INSTRUCTION] == int(WorkInstruction.NONE)
    assert decision.command_payload[KEY_RIGHT] == 7.0
    assert decision.command_payload[KEY_THRUST] == 3.0
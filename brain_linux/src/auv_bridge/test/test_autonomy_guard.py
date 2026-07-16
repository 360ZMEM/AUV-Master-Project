'''
本文件包含了针对 AUV 桥接节点的 AutonomyGuard 类的单元测试，验证了在不同输入条件下自治权限检查逻辑的正确性和预期行为。测试覆盖了以下场景：
- 所有检查通过时成功请求激活自动控制状态
- 电压过低时拒绝自动控制请求
- 遥测过旧时刷新后撤销自动控制状态
- 锁定时标记为手动覆盖并拒绝自动控制
每个测试函数都创建了一个 AutonomyGuard 实例，模拟输入状态并检查输出决策是否符合预期的自动状态、拒绝理由和自治允许标志。这些测试有助于确保 AutonomyGuard 的核心逻辑在各种边界条件下都能正确运行，为桥接节点的安全性和可靠性提供保障。
'''
from __future__ import annotations

from auv_bridge.autonomy_guard import AutonomyGuard
from common.enums import AutoState, DenyReason, LeakLevel
from common.protocol import KEY_CONFIDENCE, KEY_LEAK_LEVEL, KEY_TELEMETRY_FRESHNESS_MS, KEY_TOTAL_VOLTAGE_V


def test_request_activation_succeeds_when_all_checks_pass() -> None:
    guard = AutonomyGuard(min_total_voltage_v=47.0, min_confidence=0.5, max_uplink_age_ms=200.0)

    decision = guard.request_activation(
        sensor_status={KEY_LEAK_LEVEL: int(LeakLevel.NONE), KEY_CONFIDENCE: 0.9},
        telemetry_status={KEY_TOTAL_VOLTAGE_V: 48.5, KEY_TELEMETRY_FRESHNESS_MS: 20.0},
    )

    assert decision.auto_state == AutoState.ACTIVE
    assert decision.deny_reason == DenyReason.NONE
    assert decision.autonomy_allowed is True


def test_request_activation_denies_low_voltage() -> None:
    guard = AutonomyGuard(min_total_voltage_v=47.0, min_confidence=0.5, max_uplink_age_ms=200.0)

    decision = guard.request_activation(
        sensor_status={KEY_LEAK_LEVEL: int(LeakLevel.NONE), KEY_CONFIDENCE: 0.9},
        telemetry_status={KEY_TOTAL_VOLTAGE_V: 46.9, KEY_TELEMETRY_FRESHNESS_MS: 20.0},
    )

    assert decision.auto_state == AutoState.DENIED
    assert decision.deny_reason == DenyReason.LOW_VOLTAGE
    assert decision.autonomy_allowed is False


def test_refresh_revokes_active_state_when_uplink_becomes_stale() -> None:
    guard = AutonomyGuard(min_total_voltage_v=47.0, min_confidence=0.5, max_uplink_age_ms=200.0)
    guard.request_activation(
        sensor_status={KEY_LEAK_LEVEL: int(LeakLevel.NONE), KEY_CONFIDENCE: 0.9},
        telemetry_status={KEY_TOTAL_VOLTAGE_V: 48.5, KEY_TELEMETRY_FRESHNESS_MS: 20.0},
    )

    decision = guard.refresh(
        sensor_status={KEY_LEAK_LEVEL: int(LeakLevel.NONE), KEY_CONFIDENCE: 0.9},
        telemetry_status={KEY_TOTAL_VOLTAGE_V: 48.5, KEY_TELEMETRY_FRESHNESS_MS: 250.0},
    )

    assert decision.auto_state == AutoState.DENIED
    assert decision.deny_reason == DenyReason.AMD_UPLINK_STALE
    assert decision.autonomy_allowed is False


def test_lock_marks_manual_override() -> None:
    guard = AutonomyGuard()

    decision = guard.lock()

    assert decision.auto_state == AutoState.LOCKED
    assert decision.deny_reason == DenyReason.MANUAL_OVERRIDE
    assert decision.autonomy_allowed is False


def test_manual_override_lock_rejects_activation_until_cleared() -> None:
    guard = AutonomyGuard(min_total_voltage_v=47.0, min_confidence=0.5, max_uplink_age_ms=200.0)
    healthy_sensor = {KEY_LEAK_LEVEL: int(LeakLevel.NONE), KEY_CONFIDENCE: 0.9}
    healthy_telemetry = {KEY_TOTAL_VOLTAGE_V: 48.5, KEY_TELEMETRY_FRESHNESS_MS: 20.0}

    guard.lock(deny_reason=DenyReason.MANUAL_OVERRIDE)
    decision = guard.request_activation(
        sensor_status=healthy_sensor,
        telemetry_status=healthy_telemetry,
    )

    assert decision.auto_state == AutoState.LOCKED
    assert decision.deny_reason == DenyReason.MANUAL_OVERRIDE
    assert decision.autonomy_allowed is False

    clear_decision = guard.clear_manual_override()
    assert clear_decision.auto_state == AutoState.LOCKED
    assert clear_decision.deny_reason == DenyReason.NONE
    assert clear_decision.autonomy_allowed is False

    decision = guard.request_activation(
        sensor_status=healthy_sensor,
        telemetry_status=healthy_telemetry,
    )

    assert decision.auto_state == AutoState.ACTIVE
    assert decision.deny_reason == DenyReason.NONE
    assert decision.autonomy_allowed is True


def test_plain_manual_lock_does_not_clear_manual_override() -> None:
    guard = AutonomyGuard()

    guard.lock(deny_reason=DenyReason.MANUAL_OVERRIDE)
    decision = guard.lock(deny_reason=DenyReason.NONE)

    assert decision.auto_state == AutoState.LOCKED
    assert decision.deny_reason == DenyReason.MANUAL_OVERRIDE
    assert decision.autonomy_allowed is False

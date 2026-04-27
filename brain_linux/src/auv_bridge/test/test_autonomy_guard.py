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
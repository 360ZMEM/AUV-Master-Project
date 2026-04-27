from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from common.enums import AutoState, DenyReason, LeakLevel
from common.protocol import KEY_CONFIDENCE, KEY_LEAK_LEVEL, KEY_TELEMETRY_FRESHNESS_MS, KEY_TOTAL_VOLTAGE_V


@dataclass(frozen=True)
class GuardDecision:
    """Guard result snapshot shared with the bridge runtime."""

    auto_state: AutoState
    deny_reason: DenyReason
    autonomy_allowed: bool


class AutonomyGuard:
    """Pure autonomy admission and revocation checks."""

    def __init__(
        self,
        *,
        min_total_voltage_v: float = 47.0,
        min_confidence: float = 0.5,
        max_uplink_age_ms: float = 200.0,
    ) -> None:
        self.min_total_voltage_v = float(min_total_voltage_v)
        self.min_confidence = float(min_confidence)
        self.max_uplink_age_ms = float(max_uplink_age_ms)

        self._state = AutoState.LOCKED
        self._deny_reason = DenyReason.NONE

    @property
    def auto_state(self) -> AutoState:
        return self._state

    @property
    def deny_reason(self) -> DenyReason:
        return self._deny_reason

    def request_activation(
        self,
        *,
        sensor_status: dict[str, Any] | None,
        telemetry_status: dict[str, Any] | None,
    ) -> GuardDecision:
        self._state = AutoState.REQUESTING
        deny_reason = self._evaluate(sensor_status=sensor_status, telemetry_status=telemetry_status)
        if deny_reason == DenyReason.NONE:
            self._state = AutoState.ACTIVE
            self._deny_reason = DenyReason.NONE
            return GuardDecision(auto_state=self._state, deny_reason=self._deny_reason, autonomy_allowed=True)

        self._state = AutoState.DENIED
        self._deny_reason = deny_reason
        return GuardDecision(auto_state=self._state, deny_reason=self._deny_reason, autonomy_allowed=False)

    def refresh(
        self,
        *,
        sensor_status: dict[str, Any] | None,
        telemetry_status: dict[str, Any] | None,
    ) -> GuardDecision:
        if self._state != AutoState.ACTIVE:
            return GuardDecision(
                auto_state=self._state,
                deny_reason=self._deny_reason,
                autonomy_allowed=self._state == AutoState.ACTIVE,
            )

        deny_reason = self._evaluate(sensor_status=sensor_status, telemetry_status=telemetry_status)
        if deny_reason == DenyReason.NONE:
            return GuardDecision(auto_state=self._state, deny_reason=self._deny_reason, autonomy_allowed=True)

        self._state = AutoState.DENIED
        self._deny_reason = deny_reason
        return GuardDecision(auto_state=self._state, deny_reason=self._deny_reason, autonomy_allowed=False)

    def lock(self, *, deny_reason: DenyReason = DenyReason.MANUAL_OVERRIDE) -> GuardDecision:
        self._state = AutoState.LOCKED
        self._deny_reason = deny_reason
        return GuardDecision(auto_state=self._state, deny_reason=self._deny_reason, autonomy_allowed=False)

    def _evaluate(
        self,
        *,
        sensor_status: dict[str, Any] | None,
        telemetry_status: dict[str, Any] | None,
    ) -> DenyReason:
        try:
            leak_level = int((sensor_status or {}).get(KEY_LEAK_LEVEL, int(LeakLevel.NONE)))
            total_voltage_v = float((telemetry_status or {}).get(KEY_TOTAL_VOLTAGE_V, 0.0))
            confidence = float((sensor_status or {}).get(KEY_CONFIDENCE, 0.0))
            telemetry_freshness_ms = float((telemetry_status or {}).get(KEY_TELEMETRY_FRESHNESS_MS, float("inf")))
        except (TypeError, ValueError):
            return DenyReason.UNKNOWN

        if leak_level != int(LeakLevel.NONE):
            return DenyReason.LEAK_DETECTED
        if total_voltage_v <= self.min_total_voltage_v:
            return DenyReason.LOW_VOLTAGE
        if confidence <= self.min_confidence:
            return DenyReason.LOW_CONFIDENCE
        if telemetry_freshness_ms >= self.max_uplink_age_ms:
            return DenyReason.AMD_UPLINK_STALE
        return DenyReason.NONE
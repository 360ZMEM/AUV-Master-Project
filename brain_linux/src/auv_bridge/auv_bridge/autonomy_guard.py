'''
本文件定义了 AUV 桥接节点的纯自治权限检查逻辑，基于传感器状态和遥测数据评估是否允许进入或维持自动控制状态，并提供相应的决策结果供桥接运行时使用。
主要函数：
- request_activation(): 请求进入自动控制状态，评估当前状态并返回决策结果
- refresh(): 刷新当前自动控制状态，重新评估是否继续允许自动控制
- lock(): 强制锁定自动控制状态，通常用于手动干预或紧急情况
- _evaluate(): 内部评估函数，根据输入状态计算拒绝理由
如果不能纯自治，则拒绝理由会指明具体原因（如漏水、低电压、信号过旧等），并且自动状态会相应地切换到 DENIED 或 LOCKED，结合arbiter.py中的仲裁结果，桥接节点可以做出最终的控制权限决策。
'''

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from common.enums import AutoState, DenyReason, LeakLevel
from common.protocol import (
    KEY_CONFIDENCE,
    KEY_LEAK_LEVEL,
    KEY_PC104_JETSON_TIMEOUT,
    KEY_PC104_SYSTEM_COMM_FAULT,
    KEY_TELEMETRY_FRESHNESS_MS,
    KEY_TOTAL_VOLTAGE_V,
)


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
        if self._state == AutoState.LOCKED and self._deny_reason == DenyReason.MANUAL_OVERRIDE:
            return GuardDecision(auto_state=self._state, deny_reason=self._deny_reason, autonomy_allowed=False)

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
        if (
            self._state == AutoState.LOCKED
            and self._deny_reason == DenyReason.MANUAL_OVERRIDE
            and deny_reason == DenyReason.NONE
        ):
            return GuardDecision(auto_state=self._state, deny_reason=self._deny_reason, autonomy_allowed=False)

        self._state = AutoState.LOCKED
        self._deny_reason = deny_reason
        return GuardDecision(auto_state=self._state, deny_reason=self._deny_reason, autonomy_allowed=False)

    def clear_manual_override(self) -> GuardDecision:
        if self._state == AutoState.LOCKED and self._deny_reason == DenyReason.MANUAL_OVERRIDE:
            self._deny_reason = DenyReason.NONE
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
            storage_usage = float((telemetry_status or {}).get('storage_usage', 0.0))
            pc104_system_comm_fault = bool(
                (telemetry_status or {}).get(KEY_PC104_SYSTEM_COMM_FAULT, False)
            )
            pc104_jetson_timeout = bool(
                (telemetry_status or {}).get(KEY_PC104_JETSON_TIMEOUT, False)
            )
        except (TypeError, ValueError):
            return DenyReason.UNKNOWN

        if leak_level != int(LeakLevel.NONE):
            return DenyReason.LEAK_DETECTED
        if total_voltage_v <= self.min_total_voltage_v:
            return DenyReason.LOW_VOLTAGE
        if pc104_system_comm_fault or pc104_jetson_timeout:
            return DenyReason.COMM_LINK_FAILURE
        if confidence <= self.min_confidence:
            return DenyReason.LOW_CONFIDENCE
        if telemetry_freshness_ms >= self.max_uplink_age_ms:
            return DenyReason.AMD_UPLINK_STALE
        if storage_usage > 0.9:
            return DenyReason.LOW_CONFIDENCE
        return DenyReason.NONE

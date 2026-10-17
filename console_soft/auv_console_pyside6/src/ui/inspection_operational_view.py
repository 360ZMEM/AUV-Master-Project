"""Fail-closed presentation of inspection bridge authority in the console."""

from __future__ import annotations

import math
import time


_LOCALIZATION = {
    'LOCALIZED_DEPTH_PENDING': '已定位（埋深未许可）',
    'LOCALIZATION_PENDING': '定位中',
    'HOLD': '保持',
    'RECOVERY_REQUIRED': '需上级处置',
    'UNKNOWN': '未知',
}

_TASK = {
    'SOFTWARE_ROUTE_COMPLETE': '有限路线到端（软件）',
    'IN_PROGRESS': '巡检进行中',
    'SUSPENDED': '暂停／撤权',
    'UNKNOWN': '未知',
}

_REASONS = {
    'AMD_UPLINK_STALE': '上行失鲜',
    'inspection_recovery_required': '巡检请求处置',
    'inspection_budget_status_stale': '巡检预算状态失鲜',
    'mpc_command_unavailable': '自治控制指令不可用',
    'remote_mode': '遥控接管',
    'bridge_passive_mode': '桥处于观察模式',
}


class InspectionOperationalView:
    def __init__(self, timeout_s: float = 1.5):
        if not math.isfinite(timeout_s) or timeout_s <= 0:
            raise ValueError('timeout_s must be finite and positive')
        self.timeout_s = float(timeout_s)
        self._signature = None
        self._last_receive_monotonic_s = float('-inf')
        self._status = None

    def accept(self, status: dict, *, now: float | None = None) -> bool:
        if not isinstance(status, dict):
            return False
        sequence = status.get('command_sequence')
        timestamp = status.get('timestamp_s')
        authorized = status.get('autonomous_execution_authorized')
        reason = status.get('authority_reason')
        mode = status.get('arbiter_mode')
        source = status.get('arbiter_source')
        guard = status.get('guard_state')
        localization_fresh = status.get('localization_status_fresh')
        task_status = status.get('task_status')
        task_fresh = status.get('task_status_fresh')
        if (isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 0
                or isinstance(timestamp, bool) or not isinstance(timestamp, (int, float))
                or not math.isfinite(timestamp) or not isinstance(authorized, bool)
                or not isinstance(localization_fresh, bool)
                or not all(isinstance(item, str) for item in (reason, mode, source, guard))
                or (authorized and (reason != '' or mode != 'AUTONOMOUS'
                                    or source != 'JETSON_MPC' or guard != 'ACTIVE'))
                or (not authorized and not reason)):
            return False
        if ('task_status' in status or 'task_status_fresh' in status):
            if task_status not in _TASK or not isinstance(task_fresh, bool):
                return False
        signature = (sequence, float(timestamp))
        if (signature == self._signature or
                (self._signature is not None and float(timestamp) <= self._signature[1])):
            return False
        self._signature = signature
        self._status = dict(status)
        self._last_receive_monotonic_s = time.monotonic() if now is None else float(now)
        return True

    def is_fresh(self, *, now: float | None = None) -> bool:
        stamp = time.monotonic() if now is None else float(now)
        return self._status is not None and 0 <= stamp - self._last_receive_monotonic_s <= self.timeout_s

    def display(self, *, now: float | None = None) -> tuple[str, str]:
        if self._status is None:
            return '定位: -- | 自治许可: 未接入', 'normal'
        stamp = time.monotonic() if now is None else float(now)
        if stamp - self._last_receive_monotonic_s > self.timeout_s:
            return '定位: 未知 | 自治许可: 未证实（状态失鲜）', 'danger'
        status = self._status
        raw_localization = (str(status.get('localization_status', 'UNKNOWN'))
                            if status.get('localization_status_fresh') is True else 'UNKNOWN')
        localization = _LOCALIZATION.get(raw_localization, raw_localization)
        task = ''
        if 'task_status' in status:
            raw_task = status['task_status'] if status['task_status_fresh'] else 'UNKNOWN'
            task = f"任务: {_TASK[raw_task]} | "
        if status['autonomous_execution_authorized']:
            return f'{task}定位: {localization} | 自治许可: 允许', 'success'
        reason = str(status.get('authority_reason', '') or '未说明')
        return f'{task}定位: {localization} | 自治许可: 禁止（{_REASONS.get(reason, reason)}）', 'danger'

    def mission_phase_display(self, *, now: float | None = None) -> tuple[str, str] | None:
        """Override a raw TRACK mode only when a fresh v2 task outcome exists."""
        if self._status is None or 'task_status' not in self._status:
            return None
        stamp = time.monotonic() if now is None else float(now)
        if (stamp - self._last_receive_monotonic_s > self.timeout_s
                or not self._status['task_status_fresh']):
            return '任务阶段: 未知（状态失鲜）', 'danger'
        outcome = self._status['task_status']
        if outcome == 'SOFTWARE_ROUTE_COMPLETE':
            return '任务阶段: 有限路线到端（软件）', 'success'
        if outcome == 'SUSPENDED':
            return '任务阶段: 暂停／撤权', 'danger'
        if outcome == 'IN_PROGRESS':
            return '任务阶段: 巡检进行中', 'info'
        return '任务阶段: 未知', 'info'

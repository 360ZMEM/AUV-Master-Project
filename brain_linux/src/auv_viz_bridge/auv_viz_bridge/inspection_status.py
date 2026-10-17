"""Presentation only: route outcome, depth and bridge authority stay separate."""

import math


class InspectionStatus:
    def __init__(self, timeout_s=1.5):
        self.timeout_s = timeout_s
        self.status = None
        self.received_s = float('-inf')

    def accept(self, payload, now_s):
        if not isinstance(payload, dict):
            return False
        sequence, stamp = payload.get('command_sequence'), payload.get('timestamp_s')
        if (isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 0
                or isinstance(stamp, bool) or not isinstance(stamp, (float, int))
                or not math.isfinite(stamp)):
            return False
        if self.status is not None and stamp <= self.status['timestamp_s']:
            return False
        self.status, self.received_s = dict(payload), now_s
        return True

    def fresh(self, now_s):
        return self.status is not None and 0 <= now_s - self.received_s <= self.timeout_s

    def phase(self, now_s):
        if not self.fresh(now_s) or self.status.get('task_status_fresh') is not True:
            return 'STATUS_STALE'
        outcome = self.status.get('task_status')
        return (outcome if isinstance(outcome, str) and outcome in
                ('SOFTWARE_ROUTE_COMPLETE', 'SUSPENDED', 'IN_PROGRESS', 'UNKNOWN') else 'UNKNOWN')

    def text(self, geometry, now_s):
        if not self.fresh(now_s):
            task, authority = 'UNKNOWN / 未接入或失鲜', 'UNKNOWN / 未证实'
        else:
            task = self.phase(now_s)
            status = self.status
            allowed = (status.get('autonomous_execution_authorized') is True
                       and status.get('authority_reason') == ''
                       and status.get('arbiter_mode') == 'AUTONOMOUS'
                       and status.get('arbiter_source') == 'JETSON_MPC'
                       and status.get('guard_state') == 'ACTIVE')
            authority = ('ALLOWED / 桥允许自治输出' if allowed else
                         'DENIED / ' + str(status.get('authority_reason') or '未证实'))
        xy = geometry.position_ned
        position = '--' if xy is None else f'({xy[0]:.2f}, {xy[1]:.2f}) m'
        burial = ('UNAVAILABLE / 未获许可' if geometry.burial_m is None else
                  f'{geometry.burial_m:.2f} m / 已许可')
        width = '--' if geometry.width_m is None else f'{geometry.width_m:.2f} m'
        return (f'### 巡检任务与输出许可\n\n任务结果：{task}\n\n'
                f'桥执行许可：{authority}\n\n横向估计：{position}\n\n'
                f'埋深：{burial}\n\nFWHM 测宽：{width}\n\n'
                '软件路线到端 ≠ 艇体停稳。参考平面投影 ≠ 三维埋深。\n\n'
                '黄色海缆为仿真参考；紫色为估计；搜索线为计划。')

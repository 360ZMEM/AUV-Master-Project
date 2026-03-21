"""行为树装饰器定义。

说明：
- 装饰器用于“在不改变子节点主体逻辑”的前提下叠加异常语义；
- 本实现用于：当 `anomaly_detected=True` 时，自动降低并行巡检速度。
"""

from __future__ import annotations

from typing import Any, Dict

import py_trees

from .behaviors import SENSOR_STATUS_KEY, TARGET_MOTION_STATE_KEY
from .models import SensorStatusData


class AnomalySpeedLimiter(py_trees.decorators.Decorator):
    """异常降速装饰器。

    行为：
    1) 先执行子节点（通常是 `ParallelTracking`）；
    2) 若子节点成功且检测到异常，则将 `target_speed_mps` 乘以降速因子；
    3) 不改变子节点返回状态，保持行为树语义稳定。
    """

    def __init__(self, child: py_trees.behaviour.Behaviour, slow_down_factor: float = 0.4) -> None:
        super().__init__(name='AnomalySpeedLimiter', child=child)
        self.slow_down_factor = slow_down_factor
        self.blackboard = py_trees.blackboard.Client(name='AnomalySpeedLimiter')
        self.blackboard.register_key(key=SENSOR_STATUS_KEY, access=py_trees.common.Access.READ)
        self.blackboard.register_key(key=TARGET_MOTION_STATE_KEY, access=py_trees.common.Access.WRITE)

    def update(self) -> py_trees.common.Status:
        """在子节点运行结束后执行速度修正。"""
        child_status = self.decorated.status
        if child_status != py_trees.common.Status.SUCCESS:
            return child_status

        sensor: SensorStatusData | None = self.blackboard.get(SENSOR_STATUS_KEY)
        target: Dict[str, Any] | None = self.blackboard.get(TARGET_MOTION_STATE_KEY)

        if not isinstance(sensor, SensorStatusData) or not isinstance(target, dict):
            return child_status

        if sensor.anomaly_detected:
            # 注意：这里仅修改速度，不改变模式，保证“异常核查”为装饰器语义。
            raw_speed = float(target.get('target_speed_mps', 0.0))
            target['target_speed_mps'] = raw_speed * self.slow_down_factor
            note = str(target.get('note', ''))
            suffix = f' 异常装饰器触发：速度降为{self.slow_down_factor:.2f}倍。'
            target['note'] = (note + suffix).strip()
            self.blackboard.set(TARGET_MOTION_STATE_KEY, target)

        return child_status

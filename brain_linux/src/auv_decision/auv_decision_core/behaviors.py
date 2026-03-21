"""行为树节点定义。

说明：
1) 本文件仅实现业务决策逻辑，不依赖 ROS2；
2) 所有 Action 节点在 `update()` 中写入黑板键 `target_motion_state`；
3) 条件节点从黑板读取 `sensor_status`。
"""

from __future__ import annotations

from dataclasses import asdict

import py_trees

from .models import MotionGoal, SensorStatusData


SENSOR_STATUS_KEY = 'sensor_status'
TARGET_MOTION_STATE_KEY = 'target_motion_state'


class _BaseBehavior(py_trees.behaviour.Behaviour):
    """通用行为基类：统一黑板注册，减少重复代码。"""

    def __init__(self, name: str) -> None:
        super().__init__(name=name)
        self.blackboard = py_trees.blackboard.Client(name=name)
        self.blackboard.register_key(key=SENSOR_STATUS_KEY, access=py_trees.common.Access.READ)
        self.blackboard.register_key(key=TARGET_MOTION_STATE_KEY, access=py_trees.common.Access.WRITE)

    def _get_sensor_status(self) -> SensorStatusData:
        """从黑板读取传感状态。

        如果黑板尚未写入（例如系统冷启动），使用保守默认值。
        """
        data = self.blackboard.get(SENSOR_STATUS_KEY)
        if isinstance(data, SensorStatusData):
            return data
        return SensorStatusData()

    def _write_goal(self, goal: MotionGoal) -> None:
        """统一写入目标状态（dict 形式，方便跨层消费）。"""
        self.blackboard.set(TARGET_MOTION_STATE_KEY, asdict(goal))


class EmergencyCondition(_BaseBehavior):
    """紧急条件：漏水 OR 低电。"""

    def update(self) -> py_trees.common.Status:
        status = self._get_sensor_status()
        return (
            py_trees.common.Status.SUCCESS
            if (status.is_leaking() or status.battery_low)
            else py_trees.common.Status.FAILURE
        )


class ConfidenceAboveThreshold(_BaseBehavior):
    """置信度阈值条件。

    当 `confidence > threshold` 时返回 SUCCESS，表示走精准巡检分支。
    """

    def __init__(self, threshold: float = 0.7) -> None:
        super().__init__(name=f'ConfidenceAbove({threshold:.2f})')
        self.threshold = threshold

    def update(self) -> py_trees.common.Status:
        status = self._get_sensor_status()
        return (
            py_trees.common.Status.SUCCESS
            if status.confidence > self.threshold
            else py_trees.common.Status.FAILURE
        )


class EmergencySurface(_BaseBehavior):
    """紧急上浮动作（高优先级）。"""

    def __init__(self) -> None:
        super().__init__(name='EmergencySurface')

    def update(self) -> py_trees.common.Status:
        self._write_goal(
            MotionGoal(
                mode='EMERGENCY_SURFACE',
                target_depth_m=0.0,
                target_speed_mps=0.8,
                high_priority=True,
                note='检测到漏水或低电，执行紧急上浮。',
            )
        )
        return py_trees.common.Status.SUCCESS


class DiveToDepth(_BaseBehavior):
    """下潜到目标深度（默认 4m，位于 3~5m 区间）。"""

    def __init__(self, target_depth_m: float = 4.0) -> None:
        super().__init__(name='DiveToDepth')
        self.target_depth_m = target_depth_m

    def update(self) -> py_trees.common.Status:
        self._write_goal(
            MotionGoal(
                mode='DIVE_TO_DEPTH',
                target_depth_m=self.target_depth_m,
                target_speed_mps=0.5,
                note='主任务流：先下潜到巡检深度。',
            )
        )
        return py_trees.common.Status.SUCCESS


class ParallelTracking(_BaseBehavior):
    """精准巡检：并行跟踪模式。"""

    def __init__(self) -> None:
        super().__init__(name='ParallelTracking')

    def update(self) -> py_trees.common.Status:
        self._write_goal(
            MotionGoal(
                mode='PARALLEL_TRACKING',
                target_depth_m=4.0,
                target_speed_mps=0.6,
                sine_amplitude=0.15,
                sine_period_s=12.0,
                note='高置信度巡检：输出并行跟踪速度与正弦扰动参数。',
            )
        )
        return py_trees.common.Status.SUCCESS


class ZigZagSearch(_BaseBehavior):
    """低置信度搜索：之字形扫描。"""

    def __init__(self) -> None:
        super().__init__(name='ZigZagSearch')

    def update(self) -> py_trees.common.Status:
        # Implemented based on T/CSGPC 3.4 standard for magnetic survey lines
        self._write_goal(
            MotionGoal(
                mode='ZIGZAG_SEARCH',
                target_depth_m=4.0,
                target_speed_mps=0.4,
                sine_amplitude=0.35,
                sine_period_s=8.0,
                note='低置信度：切换之字形搜索以提升覆盖率。',
            )
        )
        return py_trees.common.Status.SUCCESS

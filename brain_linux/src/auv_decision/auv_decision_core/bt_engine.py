"""行为树引擎封装。

职责：
- 组装行为树结构；
- 提供统一 `tick()` 接口；
- 提供黑板写入/读取接口，供 ROS2 包装层调用。
"""

from __future__ import annotations

from typing import Dict, Optional

import py_trees

from .behaviors import (
    SENSOR_STATUS_KEY,
    TARGET_MOTION_STATE_KEY,
    ConfidenceAboveThreshold,
    DiveToDepth,
    EmergencyCondition,
    EmergencySurface,
    ParallelTracking,
    ZigZagSearch,
)
from .decorators import AnomalySpeedLimiter
from .models import SensorStatusData


class DecisionTreeEngine:
    """AUV 决策行为树引擎（纯 Python）。"""

    def __init__(self, confidence_threshold: float = 0.7) -> None:
        self.confidence_threshold = confidence_threshold
        self.root = self._build_tree(confidence_threshold)
        self.tree = py_trees.trees.BehaviourTree(self.root)

        self.blackboard = py_trees.blackboard.Client(name='DecisionTreeEngine')
        self.blackboard.register_key(key=SENSOR_STATUS_KEY, access=py_trees.common.Access.WRITE)
        self.blackboard.register_key(key=TARGET_MOTION_STATE_KEY, access=py_trees.common.Access.READ)

        # 冷启动默认值：避免首次 tick 时无输入导致节点读取异常。
        self.blackboard.set(SENSOR_STATUS_KEY, SensorStatusData())

    def _build_tree(self, confidence_threshold: float) -> py_trees.behaviour.Behaviour:
        """组装用户指定的行为树。

        Root(Selector)
        ├── 紧急自救(Sequence): EmergencyCondition -> EmergencySurface
        └── 主任务流(Sequence)
            ├── DiveToDepth
            └── 路由锁定(Selector)
                ├── 精准巡检(Sequence): ConfidenceAboveThreshold -> AnomalySpeedLimiter(ParallelTracking)
                └── ZigZagSearch
        """
        emergency_sequence = py_trees.composites.Sequence(name='EmergencySequence', memory=False)
        emergency_sequence.add_children([
            EmergencyCondition(name='EmergencyCondition'),
            EmergencySurface(),
        ])

        precise_sequence = py_trees.composites.Sequence(name='PreciseInspectionSequence', memory=False)
        precise_sequence.add_children([
            ConfidenceAboveThreshold(threshold=confidence_threshold),
            AnomalySpeedLimiter(ParallelTracking(), slow_down_factor=0.4),
        ])

        routing_selector = py_trees.composites.Selector(name='RouteSelector', memory=False)
        routing_selector.add_children([
            precise_sequence,
            ZigZagSearch(),
        ])

        main_sequence = py_trees.composites.Sequence(name='MainMissionSequence', memory=False)
        main_sequence.add_children([
            DiveToDepth(target_depth_m=4.0),
            routing_selector,
        ])

        root = py_trees.composites.Selector(name='RootSelector', memory=False)
        root.add_children([
            emergency_sequence,
            main_sequence,
        ])
        return root

    def set_sensor_status(self, status: SensorStatusData) -> None:
        """更新输入状态。"""
        self.blackboard.set(SENSOR_STATUS_KEY, status)

    def tick(self) -> None:
        """执行一次行为树 tick。"""
        self.tree.tick()

    def get_target_motion_state(self) -> Optional[Dict]:
        """读取行为树输出目标。"""
        result = self.blackboard.get(TARGET_MOTION_STATE_KEY)
        if isinstance(result, dict):
            return result
        return None

    def unicode_tree(self) -> str:
        """返回行为树 Unicode 文本，便于终端打印。"""
        return py_trees.display.unicode_tree(root=self.root, show_status=True)

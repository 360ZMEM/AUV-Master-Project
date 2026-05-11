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
    DebugLevelCondition,
    DiveToDepth,
    EmergencyCondition,
    EmergencySurface,
    HoldCurrentPoseBehavior,
    MockCableTrackingBehavior,
    ParallelTracking,
    TrackAnalyticalTrajectoryBehavior,
    Wait_For_Arbiter_Authorization,
    ZigZagSearch,
)
from .decorators import AnomalySpeedLimiter
from .decorators import SeabedSafetyLimiter
from .models import SensorStatusData


class DecisionTreeEngine:
    """AUV 决策行为树引擎（纯 Python）。

    该类负责把行为树结构、黑板状态和 tick 调度封装成一个稳定的运行时对象，
    供 ROS2 包装层直接驱动。它不依赖 ROS2 消息类型，因此可在单元测试中独立运行。
    """

    MISSION_TARGET_KEY = 'mission_target'

    def __init__(self, confidence_threshold: float = 0.7) -> None:
        """初始化行为树、黑板缓存和冷启动默认状态。"""
        self.confidence_threshold = confidence_threshold
        self.root = self._build_tree(confidence_threshold)
        self.tree = py_trees.trees.BehaviourTree(self.root)

        self.blackboard = py_trees.blackboard.Client(name='DecisionTreeEngine')
        self.blackboard.register_key(key=SENSOR_STATUS_KEY, access=py_trees.common.Access.WRITE)
        self.blackboard.register_key(key=TARGET_MOTION_STATE_KEY, access=py_trees.common.Access.READ)
        self.blackboard.register_key(key=self.MISSION_TARGET_KEY, access=py_trees.common.Access.WRITE)

        self.blackboard.set(SENSOR_STATUS_KEY, SensorStatusData())
        self.blackboard.set(self.MISSION_TARGET_KEY, {})

    def _build_tree(self, confidence_threshold: float) -> py_trees.behaviour.Behaviour:
        """组装决策行为树结构。

        树结构：
        RootSelector
        ├── EmergencySequence (EmergencyCondition → EmergencySurface)  [始终最高优先级]
        └── DebugCascadeSelector
            ├── HoldCurrentPose           [debug_level >= 1 时可激活]
            ├── TrackAnalyticalTrajectory [debug_level >= 2 时可激活]
            └── MainMissionSequence       [debug_level == 0 或 3 时激活]

        设计意图：
        1. 紧急条件永远优先于其他行为；
        2. debug_level 直接切换调试路径，方便逐层验证；
        3. 主任务流保持原始巡检逻辑不变。
        """
        # L0: 紧急序列（始终最高优先级）
        emergency_sequence = py_trees.composites.Sequence(name='EmergencySequence', memory=False)
        emergency_sequence.add_children([
            EmergencyCondition(name='EmergencyCondition'),
            EmergencySurface(),
        ])

        # L1: Hold 行为（debug_level == 1）
        # 使用 Inverter 装饰器创建 "debug_level < 2" 条件
        debug_level_not_2_or_3 = py_trees.decorators.Inverter(
            name='NotDebugLevel2Or3',
            child=DebugLevelCondition(required_level=2),
        )
        hold_sequence = py_trees.composites.Sequence(name='HoldSequence', memory=False)
        hold_sequence.add_children([
            DebugLevelCondition(required_level=1),
            debug_level_not_2_or_3,  # debug_level >= 1 且 debug_level < 2，即 debug_level == 1
            HoldCurrentPoseBehavior(),
        ])

        # L2: AnalyticalPath 行为（debug_level == 2）
        # 使用 Inverter 装饰器创建 "debug_level < 3" 条件
        debug_level_not_3 = py_trees.decorators.Inverter(
            name='NotDebugLevel3',
            child=DebugLevelCondition(required_level=3),
        )
        path_sequence = py_trees.composites.Sequence(name='AnalyticalPathSequence', memory=False)
        path_sequence.add_children([
            DebugLevelCondition(required_level=2),
            debug_level_not_3,  # debug_level >= 2 且 debug_level < 3，即 debug_level == 2
            TrackAnalyticalTrajectoryBehavior(trajectory_kind='cable_like_3d'),
        ])

        # L3: 主任务流（原有逻辑）
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

        seabed_safe_route = SeabedSafetyLimiter(routing_selector, slow_down_factor=0.5)

        main_sequence = py_trees.composites.Sequence(name='MainMissionSequence', memory=False)
        main_sequence.add_children([
            DiveToDepth(target_depth_m=4.0),
            seabed_safe_route,
        ])

        # Debug 级联选择器（L1/L2/L3 路由）
        debug_cascade_selector = py_trees.composites.Selector(
            name='DebugCascadeSelector',
            memory=False,
        )
        debug_cascade_selector.add_children([
            hold_sequence,
            path_sequence,
            main_sequence,
        ])

        # 根选择器（L0 > L1/L2/L3）
        root = py_trees.composites.Selector(name='RootSelector', memory=False)
        root.add_children([
            emergency_sequence,
            Wait_For_Arbiter_Authorization(name='StandbyCheck'),
            debug_cascade_selector,
        ])
        return root

    def set_sensor_status(self, status: SensorStatusData) -> None:
        """更新行为树的输入状态黑板值。"""
        self.blackboard.set(SENSOR_STATUS_KEY, status)

    def set_mission_target(self, mission_data: dict) -> None:
        """写入任务目标到行为树黑板。"""
        self.blackboard.set(self.MISSION_TARGET_KEY, mission_data)

    def get_mission_target(self) -> dict:
        """读取当前任务目标。"""
        result = self.blackboard.get(self.MISSION_TARGET_KEY)
        if isinstance(result, dict):
            return result
        return {}

    def tick(self) -> None:
        """执行一次行为树 tick 并推进当前决策状态。"""
        self.tree.tick()

    def get_target_motion_state(self) -> Optional[Dict]:
        """读取最近一次 tick 产出的目标运动状态。"""
        result = self.blackboard.get(TARGET_MOTION_STATE_KEY)
        if isinstance(result, dict):
            return result
        return None

    def current_behavior_name(self) -> str:
        """返回最近一次 tick 中最深层激活行为的名称。"""
        tip = self.root.tip()
        if tip is None:
            return self.root.name
        return tip.name

    def active_path(self) -> str:
        """返回当前激活分支从根节点到叶节点的路径字符串。"""
        tip = self.root.tip()
        if tip is None:
            return self.root.name

        names: list[str] = []
        node = tip
        while node is not None:
            names.append(node.name)
            node = node.parent
        return ' > '.join(reversed(names))

    def unicode_tree(self) -> str:
        """返回行为树 Unicode 文本，便于终端打印。"""
        return py_trees.display.unicode_tree(root=self.root, show_status=True)

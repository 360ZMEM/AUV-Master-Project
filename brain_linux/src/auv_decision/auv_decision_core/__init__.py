"""AUV 决策核心包（纯 Python，不依赖 rclpy）。"""

from .behaviors import (
    ConfidenceAboveThreshold,
    DebugLevelCondition,
    DiveToDepth,
    EmergencyCondition,
    EmergencySurface,
    HoldCurrentPoseBehavior,
    ParallelTracking,
    TrackAnalyticalTrajectoryBehavior,
    ZigZagSearch,
)
from .bt_engine import DecisionTreeEngine
from .fsm_baseline import FiniteStateMachineEngine
from .models import MotionGoal, SensorStatusData
from .telemetry import DecisionTelemetrySnapshot, build_bt_status_markdown, build_decision_telemetry_snapshot

__all__ = [
    'DecisionTreeEngine',
    'FiniteStateMachineEngine',
    'MotionGoal',
    'SensorStatusData',
    'DecisionTelemetrySnapshot',
    'build_bt_status_markdown',
    'build_decision_telemetry_snapshot',
    'EmergencyCondition',
    'EmergencySurface',
    'ConfidenceAboveThreshold',
    'DiveToDepth',
    'ParallelTracking',
    'ZigZagSearch',
    'HoldCurrentPoseBehavior',
    'TrackAnalyticalTrajectoryBehavior',
    'DebugLevelCondition',
]

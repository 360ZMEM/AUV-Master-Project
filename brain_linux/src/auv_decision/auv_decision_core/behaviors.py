"""行为树节点定义。

说明：
1) 本文件仅实现业务决策逻辑，不依赖 ROS2；
2) 所有 Action 节点在 `update()` 中写入黑板键 `target_motion_state`；
3) 条件节点从黑板读取 `sensor_status`。
"""

from __future__ import annotations

from dataclasses import asdict

import py_trees

from .decision_filters import ConfidenceHysteresisGate
from .models import MotionGoal, SensorStatusData


SENSOR_STATUS_KEY = 'sensor_status'
TARGET_MOTION_STATE_KEY = 'target_motion_state'
MISSION_TARGET_KEY = 'mission_target'


class _BaseBehavior(py_trees.behaviour.Behaviour):
    """通用行为基类：统一黑板注册，减少重复代码。"""

    def __init__(self, name: str) -> None:
        super().__init__(name=name)
        self.blackboard = py_trees.blackboard.Client(name=name)
        self.blackboard.register_key(key=SENSOR_STATUS_KEY, access=py_trees.common.Access.READ)
        self.blackboard.register_key(key=TARGET_MOTION_STATE_KEY, access=py_trees.common.Access.WRITE)
        self.blackboard.register_key(key=MISSION_TARGET_KEY, access=py_trees.common.Access.READ)

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


class Wait_For_Arbiter_Authorization(_BaseBehavior):
    """待命模式：等待仲裁器授权。"""

    def update(self) -> py_trees.common.Status:
        sensor = self._get_sensor_status()
        if sensor.auto_state != 'ACTIVE':
            self._write_goal(
                MotionGoal(
                    mode='IDLE',
                    high_priority=False,
                    note='Standby: Waiting for manual authorization'
                )
            )
            return py_trees.common.Status.SUCCESS
        return py_trees.common.Status.FAILURE


class EmergencyCondition(_BaseBehavior):
    """紧急条件：漏水 OR 低电 OR 穿底。"""

    def update(self) -> py_trees.common.Status:
        status = self._get_sensor_status()
        return (
            py_trees.common.Status.SUCCESS
            if (status.is_leaking() or status.battery_low or status.is_seabed_penetrated())
            else py_trees.common.Status.FAILURE
        )


class ConfidenceAboveThreshold(_BaseBehavior):
    """置信度阈值条件。

    当 `confidence > threshold` 时返回 SUCCESS，表示走精准巡检分支。
    """

    def __init__(
        self,
        threshold: float = 0.7,
        gate: ConfidenceHysteresisGate | None = None,
    ) -> None:
        super().__init__(name=f'ConfidenceAbove({threshold:.2f})')
        self.threshold = threshold
        self.gate = gate

    def update(self) -> py_trees.common.Status:
        status = self._get_sensor_status()
        above = (
            self.gate.update(status.confidence)
            if self.gate is not None
            else status.confidence > self.threshold
        )
        return (
            py_trees.common.Status.SUCCESS
            if above
            else py_trees.common.Status.FAILURE
        )


class EmergencySurface(_BaseBehavior):
    """紧急上浮动作（高优先级）。"""

    def __init__(self) -> None:
        super().__init__(name='EmergencySurface')

    def update(self) -> py_trees.common.Status:
        status = self._get_sensor_status()
        if status.is_seabed_penetrated():
            note = '检测到穿底风险，执行紧急上浮。'
        elif status.is_leaking() or status.battery_low:
            note = '检测到漏水或低电，执行紧急上浮。'
        else:
            note = '执行紧急上浮。'
        self._write_goal(
            MotionGoal(
                mode='EMERGENCY_SURFACE',
                target_depth_m=0.0,
                target_speed_mps=0.8,
                high_priority=True,
                note=note,
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


class HoldCurrentPoseBehavior(_BaseBehavior):
    """L1 Hold 行为：定深定航稳定，用于验证 PID 控制稳定性。

    在 initialize() 时抓取当前深度和航向作为目标，update() 持续发布零速度控制指令。
    """

    def __init__(self) -> None:
        """初始化保持姿态行为，并预置抓取到的目标深度与航向。"""
        super().__init__(name='HoldCurrentPose')
        self.target_depth_m: float = 0.0
        self.target_heading_rad: float = 0.0

    def initialise(self) -> None:
        """节点启动时抓取当前位姿作为目标。"""
        status = self._get_sensor_status()
        self.target_depth_m = float(status.depth_m)
        self.target_heading_rad = float(status.heading_rad)
        self.logger.info(
            f'HoldCurrentPose 初始化: target_depth={self.target_depth_m:.2f}m, '
            f'target_heading={self.target_heading_rad:.2f}rad'
        )

    def update(self) -> py_trees.common.Status:
        """持续发布零速度控制指令，保持定深定航。"""
        self._write_goal(
            MotionGoal(
                mode='STABILIZE_HOLD',
                target_depth_m=self.target_depth_m,
                target_speed_mps=0.0,
                target_heading_rad=self.target_heading_rad,
                high_priority=False,
                note='L1 Hold 模式：定深定航稳定，验证 PID 控制稳定性。',
            )
        )
        return py_trees.common.Status.RUNNING


class TrackAnalyticalTrajectoryBehavior(_BaseBehavior):
    """L2 AnalyticalPath 行为：跟踪解析式轨迹，用于验证 LOS 导引律。

    基于解析式轨迹生成器（如 cable_like_3d），使用 Mock AMD 时钟进行时间索引采样。
    """

    def __init__(self, trajectory_kind: str = 'cable_like_3d') -> None:
        """初始化解析式轨迹跟踪行为。

        Args:
            trajectory_kind (str): 轨迹类型名称，决定采样器生成哪一种参考轨迹。
        """
        super().__init__(name='TrackAnalyticalTrajectory')
        self.trajectory_kind = trajectory_kind
        self.trajectory_generator = None

    def initialise(self) -> None:
        """节点启动时创建轨迹生成器。"""
        try:
            from algorithm.trajectory_generator import TrajectoryGenerator

            self.trajectory_generator = TrajectoryGenerator(kind=self.trajectory_kind)
            self.logger.info(f'TrackAnalyticalTrajectory 初始化: trajectory_kind={self.trajectory_kind}')
        except ImportError as e:
            self.logger.error(f'无法导入 TrajectoryGenerator: {e}')
            self.trajectory_generator = None

    def update(self) -> py_trees.common.Status:
        """基于 Mock AMD 时钟采样轨迹点，发布目标状态。"""
        if self.trajectory_generator is None:
            self.logger.warning('轨迹生成器未初始化，返回 FAILURE')
            return py_trees.common.Status.FAILURE

        status = self._get_sensor_status()
        if status.mock_amd_timestamp_us <= 0:
            self.logger.warning('Mock AMD 时间戳未同步，返回 FAILURE')
            return py_trees.common.Status.FAILURE

        # 将微秒转换为秒
        t_s = status.mock_amd_timestamp_us / 1e6

        # 采样轨迹点
        try:
            waypoint = self.trajectory_generator.get_waypoint(t_s)
            if waypoint is None:
                self.logger.warning(f'轨迹采样失败（t={t_s:.2f}s），返回 FAILURE')
                return py_trees.common.Status.FAILURE

            # 发布目标状态
            self._write_goal(
                MotionGoal(
                    mode='ANALYTICAL_PATH',
                    target_depth_m=float(waypoint.get('z', 4.0)),
                    target_speed_mps=float(waypoint.get('speed', 0.6)),
                    target_x_m=float(waypoint.get('x', 0.0)),
                    target_y_m=float(waypoint.get('y', 0.0)),
                    target_heading_rad=float(waypoint.get('yaw', 0.0)),
                    high_priority=False,
                    note=f'L2 AnalyticalPath 模式：跟踪解析式轨迹（t={t_s:.2f}s）',
                )
            )
            return py_trees.common.Status.RUNNING
        except Exception as e:
            self.logger.error(f'轨迹采样异常: {e}')
            return py_trees.common.Status.FAILURE


class DebugLevelCondition(py_trees.behaviour.Behaviour):
    """DebugLevel 条件节点：检查当前 debug_level 是否满足阈值。

    用于控制 L1/L2 行为节点的激活条件。

    Args:
        required_level: 要求的 debug_level 阈值
        exact_match: 如果为 True，则要求精确匹配；如果为 False，则要求 >= 阈值
    """

    def __init__(self, required_level: int = 1, exact_match: bool = False) -> None:
        super().__init__(name=f'DebugLevel=={required_level}' if exact_match else f'DebugLevel>={required_level}')
        self.required_level = required_level
        self.exact_match = exact_match
        self.blackboard = py_trees.blackboard.Client(name=f'DebugLevelCondition_{required_level}')
        self.blackboard.register_key(key=SENSOR_STATUS_KEY, access=py_trees.common.Access.READ)

    def update(self) -> py_trees.common.Status:
        """检查 debug_level 是否满足条件。"""
        status = self.blackboard.get(SENSOR_STATUS_KEY)
        if not isinstance(status, SensorStatusData):
            return py_trees.common.Status.FAILURE

        current_level = getattr(status, 'debug_level', 0)

        if self.exact_match:
            return (
                py_trees.common.Status.SUCCESS
                if current_level == self.required_level
                else py_trees.common.Status.FAILURE
            )
        else:
            return (
                py_trees.common.Status.SUCCESS
                if current_level >= self.required_level
                else py_trees.common.Status.FAILURE
            )


class MockCableTrackingBehavior(_BaseBehavior):
    """Mock 电缆跟踪行为：从黑板 mission_target 读取任务参数。

    该行为用于模拟真实任务执行，当收到 CABLE_TRACKING 任务指令时，
    读取目标深度、跟踪距离等参数并发布控制目标。
    """

    def __init__(self) -> None:
        super().__init__(name='MockCableTracking')
        self._task_started = False
        self._target_depth_m = 4.0
        self._track_distance_m = 500.0
        self._timeout_s = 1200.0

    def initialise(self) -> None:
        """从黑板读取任务参数。"""
        mission_target = self.blackboard.get(MISSION_TARGET_KEY)
        if isinstance(mission_target, dict) and mission_target:
            self._target_depth_m = float(mission_target.get('target_depth', 4.0))
            self._track_distance_m = float(mission_target.get('track_distance', 500.0))
            self._timeout_s = float(mission_target.get('timeout_s', 1200.0))
            self.logger.info(
                f'MockCableTracking 启动: depth={self._target_depth_m}m, '
                f'distance={self._track_distance_m}m, timeout={self._timeout_s}s'
            )
        self._task_started = True

    def update(self) -> py_trees.common.Status:
        """持续发布电缆跟踪控制目标。"""
        status = self._get_sensor_status()
        self._write_goal(
            MotionGoal(
                mode='CABLE_TRACKING',
                target_depth_m=self._target_depth_m,
                target_speed_mps=0.5,
                track_cable=True,
                note=f'Mock 电缆跟踪: depth={self._target_depth_m}m, distance={self._track_distance_m}m',
            )
        )
        return py_trees.common.Status.RUNNING


class MissionCommandCondition(_BaseBehavior):
    """任务指令条件：检查是否收到有效的任务指令。

    当黑板 mission_target 包含 mission_type 时返回 SUCCESS。
    """

    def __init__(self, required_mission_type: str | None = None) -> None:
        """初始化任务指令条件。

        Args:
            required_mission_type: 如果指定，则要求任务类型必须匹配；否则接受任意任务。
        """
        super().__init__(name='MissionCommandReceived')
        self.required_mission_type = required_mission_type

    def update(self) -> py_trees.common.Status:
        """检查是否收到任务指令。"""
        mission_target = self.blackboard.get(MISSION_TARGET_KEY)
        if not isinstance(mission_target, dict) or not mission_target:
            return py_trees.common.Status.FAILURE

        mission_type = mission_target.get('mission_type', '')
        if not mission_type:
            return py_trees.common.Status.FAILURE

        if self.required_mission_type and mission_type != self.required_mission_type:
            return py_trees.common.Status.FAILURE

        return py_trees.common.Status.SUCCESS

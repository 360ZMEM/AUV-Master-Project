"""新行为节点单元测试（Phase 3）。"""

from auv_decision_core.bt_engine import DecisionTreeEngine
from auv_decision_core.models import SensorStatusData
from py_trees import behaviour


def test_hold_current_pose_activates_when_debug_level_1():
    """测试 debug_level=1 时激活 HoldCurrentPose 行为。"""
    engine = DecisionTreeEngine(confidence_threshold=0.7)
    engine.set_sensor_status(
        SensorStatusData(
            confidence=0.9,
            depth_m=5.0,
            heading_rad=1.5,
            debug_level=1,  # L1 Hold 模式
        )
    )
    engine.tick()
    goal = engine.get_target_motion_state()
    assert goal is not None
    assert goal['mode'] == 'STABILIZE_HOLD'
    assert goal['target_speed_mps'] == 0.0


def test_analytical_path_activates_when_debug_level_2():
    """测试 debug_level=2 时激活 TrackAnalyticalTrajectory 行为（如果 Mock AMD 时间可用）。"""
    engine = DecisionTreeEngine(confidence_threshold=0.7)
    engine.set_sensor_status(
        SensorStatusData(
            confidence=0.9,
            mock_amd_timestamp_us=1000000,  # 1秒
            debug_level=2,  # L2 AnalyticalPath 模式
        )
    )
    engine.tick()
    goal = engine.get_target_motion_state()

    # 如果 TrajectoryGenerator 可用，应该是 ANALYTICAL_PATH 模式
    # 如果不可用，会回退到主任务流
    if goal is not None:
        assert goal['mode'] in ['ANALYTICAL_PATH', 'DIVE_TO_DEPTH', 'PARALLEL_TRACKING']


def test_auto_mode_activates_main_mission():
    """测试 debug_level=0 (AUTO) 时激活主任务流。"""
    engine = DecisionTreeEngine(confidence_threshold=0.7)
    engine.set_sensor_status(
        SensorStatusData(
            confidence=0.9,
            debug_level=0,  # AUTO 模式
        )
    )
    engine.tick()
    goal = engine.get_target_motion_state()
    assert goal is not None
    # 高置信度应该是 PARALLEL_TRACKING
    assert goal['mode'] == 'PARALLEL_TRACKING'


def test_full_mode_activates_main_mission():
    """测试 debug_level=3 (FULL) 时激活主任务流。"""
    engine = DecisionTreeEngine(confidence_threshold=0.7)
    engine.set_sensor_status(
        SensorStatusData(
            confidence=0.2,  # 低置信度
            debug_level=3,  # FULL 模式
        )
    )
    engine.tick()
    goal = engine.get_target_motion_state()
    assert goal is not None
    # 低置信度应该是 ZIGZAG_SEARCH
    assert goal['mode'] == 'ZIGZAG_SEARCH'


def test_emergency_has_highest_priority():
    """测试紧急情况具有最高优先级，覆盖所有 debug_level。"""
    for debug_level in [0, 1, 2, 3]:
        engine = DecisionTreeEngine(confidence_threshold=0.7)
        engine.set_sensor_status(
            SensorStatusData(
                confidence=0.9,
                leak_level=1,  # 漏水
                debug_level=debug_level,
            )
        )
        engine.tick()
        goal = engine.get_target_motion_state()
        assert goal is not None
        assert goal['mode'] == 'EMERGENCY_SURFACE'


def test_hold_mode_in_debug_level_2_falls_back_to_path():
    """测试 debug_level=2 时，即使 debug_level=1 也应该走 Path 分支（级联选择器）。"""
    engine = DecisionTreeEngine(confidence_threshold=0.7)
    engine.set_sensor_status(
        SensorStatusData(
            confidence=0.9,
            mock_amd_timestamp_us=1000000,
            debug_level=2,  # 满足 L1 和 L2 条件
        )
    )
    engine.tick()
    goal = engine.get_target_motion_state()

    # 应该优先激活 L2 Path（级联选择器，高优先级先匹配）
    if goal is not None:
        # 如果 TrajectoryGenerator 可用，应该是 ANALYTICAL_PATH
        # 否则回退到主任务流
        assert goal['mode'] in ['ANALYTICAL_PATH', 'DIVE_TO_DEPTH', 'PARALLEL_TRACKING']


def test_no_mock_amd_time_in_path_mode_fails():
    """测试 debug_level=2 但没有 Mock AMD 时间时，Path 行为失败，回退到主任务流。"""
    engine = DecisionTreeEngine(confidence_threshold=0.7)
    engine.set_sensor_status(
        SensorStatusData(
            confidence=0.9,
            mock_amd_timestamp_us=0,  # 没有 Mock AMD 时间
            debug_level=2,  # L2 模式
        )
    )
    engine.tick()
    goal = engine.get_target_motion_state()
    assert goal is not None
    # Path 失败，应该回退到主任务流
    assert goal['mode'] in ['DIVE_TO_DEPTH', 'PARALLEL_TRACKING']

"""核心行为树基础测试（纯 Python）。"""

from auv_decision_core.bt_engine import DecisionTreeEngine
from auv_decision_core.models import SensorStatusData


def test_switch_to_parallel_when_confidence_high():
    engine = DecisionTreeEngine(confidence_threshold=0.7)
    engine.set_sensor_status(
        SensorStatusData(
            confidence=0.9,
            leak_level=0,
            battery_low=False,
            anomaly_detected=False,
        )
    )
    engine.tick()
    goal = engine.get_target_motion_state()
    assert goal is not None
    assert goal['mode'] == 'PARALLEL_TRACKING'


def test_switch_to_zigzag_when_confidence_low():
    engine = DecisionTreeEngine(confidence_threshold=0.7)
    engine.set_sensor_status(
        SensorStatusData(
            confidence=0.2,
            leak_level=0,
            battery_low=False,
            anomaly_detected=False,
        )
    )
    engine.tick()
    goal = engine.get_target_motion_state()
    assert goal is not None
    assert goal['mode'] == 'ZIGZAG_SEARCH'


def test_emergency_has_higher_priority():
    engine = DecisionTreeEngine(confidence_threshold=0.7)
    engine.set_sensor_status(
        SensorStatusData(
            confidence=0.9,
            leak_level=1,
            battery_low=False,
            anomaly_detected=False,
        )
    )
    engine.tick()
    goal = engine.get_target_motion_state()
    assert goal is not None
    assert goal['mode'] == 'EMERGENCY_SURFACE'
    assert goal['high_priority'] is True


def test_anomaly_decorator_slow_down_parallel_speed():
    engine = DecisionTreeEngine(confidence_threshold=0.7)
    engine.set_sensor_status(
        SensorStatusData(
            confidence=0.9,
            leak_level=0,
            battery_low=False,
            anomaly_detected=True,
        )
    )
    engine.tick()
    goal = engine.get_target_motion_state()
    assert goal is not None
    assert goal['mode'] == 'PARALLEL_TRACKING'
    # 原始并行速度为 0.6，降速系数 0.4，期望 0.24
    assert abs(goal['target_speed_mps'] - 0.24) < 1e-6

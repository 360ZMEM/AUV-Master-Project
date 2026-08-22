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
            auto_state='ACTIVE',
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
            auto_state='ACTIVE',
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


def test_seabed_penetration_triggers_emergency_surface():
    engine = DecisionTreeEngine(confidence_threshold=0.7)
    engine.set_sensor_status(
        SensorStatusData(
            confidence=0.9,
            leak_level=0,
            battery_low=False,
            anomaly_detected=False,
            depth_m=15.8,
            seabed_depth_m=15.0,
            seabed_clearance_m=-0.8,
            seabed_proximity_warning=True,
            seabed_penetration_warning=True,
        )
    )
    engine.tick()
    goal = engine.get_target_motion_state()
    assert goal is not None
    assert goal['mode'] == 'EMERGENCY_SURFACE'
    assert goal['high_priority'] is True
    assert '穿底' in goal['note']


def test_seabed_proximity_slows_down_goal():
    engine = DecisionTreeEngine(confidence_threshold=0.7)
    engine.set_sensor_status(
        SensorStatusData(
            confidence=0.9,
            leak_level=0,
            battery_low=False,
            anomaly_detected=False,
            depth_m=14.4,
            seabed_depth_m=15.0,
            seabed_clearance_m=0.6,
            seabed_proximity_warning=True,
            seabed_penetration_warning=False,
            auto_state='ACTIVE',
        )
    )
    engine.tick()
    goal = engine.get_target_motion_state()
    assert goal is not None
    assert goal['mode'] == 'PARALLEL_TRACKING'
    assert goal['target_speed_mps'] < 0.6
    assert '近底' in goal['note']


def test_anomaly_decorator_slow_down_parallel_speed():
    engine = DecisionTreeEngine(confidence_threshold=0.7)
    engine.set_sensor_status(
        SensorStatusData(
            confidence=0.9,
            leak_level=0,
            battery_low=False,
            anomaly_detected=True,
            auto_state='ACTIVE',
        )
    )
    engine.tick()
    goal = engine.get_target_motion_state()
    assert goal is not None
    assert goal['mode'] == 'PARALLEL_TRACKING'
    # 原始并行速度为 0.6，降速系数 0.4，期望 0.24
    assert abs(goal['target_speed_mps'] - 0.24) < 1e-6


def test_execution_brain_communication_fault_forces_safe_hover() -> None:
    engine = DecisionTreeEngine(confidence_threshold=0.7)
    engine.set_sensor_status(
        SensorStatusData(
            confidence=0.9,
            auto_state='ACTIVE',
            execution_fault_word=(1 << 14),
            communication_link_ok=False,
        )
    )

    engine.tick()
    goal = engine.get_target_motion_state()

    assert goal is not None
    assert goal['mode'] == 'IDLE'
    assert goal['target_speed_mps'] == 0.0
    assert 'fault_word=0x00004000' in goal['note']


def test_execution_brain_dvl_loss_routes_to_relocalization_search() -> None:
    engine = DecisionTreeEngine(confidence_threshold=0.7)
    engine.set_sensor_status(
        SensorStatusData(
            confidence=0.9,
            auto_state='ACTIVE',
            execution_fault_word=(1 << 13),
            velocity_aiding_valid=False,
        )
    )

    engine.tick()
    goal = engine.get_target_motion_state()

    assert goal is not None
    assert goal['mode'] == 'ZIGZAG_SEARCH'
    assert 'fault_word=0x00002000' in goal['note']

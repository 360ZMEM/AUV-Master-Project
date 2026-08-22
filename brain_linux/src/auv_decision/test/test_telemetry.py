"""Decision observability telemetry tests."""

from auv_decision_core.bt_engine import DecisionTreeEngine
from auv_decision_core.models import SensorStatusData
from auv_decision_core.telemetry import build_decision_telemetry_snapshot


def test_current_behavior_uses_tree_tip():
    engine = DecisionTreeEngine(confidence_threshold=0.7)
    engine.set_sensor_status(
        SensorStatusData(
            confidence=0.9,
            leak_level=0,
            battery_low=False,
            total_voltage_v=48.0,
            anomaly_detected=False,
            auto_state='ACTIVE',
        )
    )
    engine.tick()
    assert engine.current_behavior_name() == 'ParallelTracking'
    assert engine.active_path().endswith('ParallelTracking')


def test_telemetry_snapshot_marks_missing_optional_metrics():
    engine = DecisionTreeEngine(confidence_threshold=0.7)
    status = SensorStatusData(
        confidence=0.6,
        leak_level=0,
        battery_low=False,
        total_voltage_v=47.5,
        anomaly_detected=False,
        depth_m=4.2,
        speed_mps=0.3,
        seabed_clearance_m=10.8,
        auto_state='ACTIVE',
    )
    engine.set_sensor_status(status)
    engine.tick()

    snapshot = build_decision_telemetry_snapshot(
        sensor_status=status,
        goal=engine.get_target_motion_state(),
        current_behavior=engine.current_behavior_name(),
        active_path=engine.active_path(),
        tree_snapshot=engine.unicode_tree(),
        depth_error_m=0.2,
        lateral_error_m=None,
        magnetic_magnitude=None,
    )

    assert snapshot.mode == 'ZIGZAG_SEARCH'
    assert snapshot.depth_error_m == 0.2
    assert snapshot.has_lateral_error is False
    assert snapshot.has_magnetic_magnitude is False
    assert 'Behavior Tree' in snapshot.bt_status_markdown

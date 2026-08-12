from __future__ import annotations

from auv_decision_ros.tracking_authority import (
    MODE_HOLD,
    MODE_SEARCH,
    MODE_TRACK,
    QualitySignal,
    TrackingAuthorityMachine,
)


def _signal(p_detect: float, p_track: float) -> QualitySignal:
    return QualitySignal(
        source="sonar_cable",
        validity=2,
        p_detect=p_detect,
        p_track=p_track,
        detection_calibrated=True,
        track_calibrated=True,
        age_s=0.05,
    )


def test_authority_uses_debounce_and_hysteresis() -> None:
    machine = TrackingAuthorityMachine(
        enter_debounce_count=2,
        exit_debounce_count=2,
    )
    assert machine.update(
        [_signal(0.9, 0.9)],
        runtime_sensor_health_ok=True,
    ).mode == MODE_HOLD
    assert machine.update(
        [_signal(0.9, 0.9)],
        runtime_sensor_health_ok=True,
    ).mode == MODE_TRACK

    assert machine.update(
        [_signal(0.7, 0.6)],
        runtime_sensor_health_ok=True,
    ).mode == MODE_TRACK
    assert machine.update(
        [_signal(0.7, 0.4)],
        runtime_sensor_health_ok=True,
    ).mode == MODE_TRACK
    assert machine.update(
        [_signal(0.7, 0.4)],
        runtime_sensor_health_ok=True,
    ).mode == MODE_SEARCH


def test_authority_separates_detection_from_tracking() -> None:
    machine = TrackingAuthorityMachine(enter_debounce_count=1)
    signal = QualitySignal(
        source="magnetic_45hz",
        validity=1,
        p_detect=0.9,
        p_track=float("nan"),
        detection_calibrated=True,
        track_calibrated=False,
        age_s=0.05,
    )
    decision = machine.update(
        [signal],
        runtime_sensor_health_ok=True,
    )
    assert decision.mode == MODE_SEARCH
    assert decision.detection_authorized is True
    assert decision.tracking_authorized is False


def test_authority_health_loss_forces_immediate_hold() -> None:
    machine = TrackingAuthorityMachine(enter_debounce_count=1)
    assert machine.update(
        [_signal(0.9, 0.9)],
        runtime_sensor_health_ok=True,
    ).mode == MODE_TRACK
    decision = machine.update(
        [_signal(0.9, 0.9)],
        runtime_sensor_health_ok=False,
    )
    assert decision.mode == MODE_HOLD
    assert decision.sensor_health_ok is False

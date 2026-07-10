from common.protocol import (
    KEY_ALTITUDE_M,
    KEY_LOOKAHEAD_M,
    KEY_SLOPE,
    Z_PATH_ALTITUDE,
    Z_PATH_FORWARD_SONAR,
    validate_sensor_payload,
)


def test_altitude_topic_payload_is_supported() -> None:
    ok, errors = validate_sensor_payload(
        Z_PATH_ALTITUDE,
        {
            KEY_ALTITUDE_M: 3.25,
            "step": 1,
            "sim_time": 0.1,
            "ts": 123.456,
        },
    )

    assert ok
    assert errors == []


def test_forward_sonar_topic_payload_is_supported() -> None:
    ok, errors = validate_sensor_payload(
        Z_PATH_FORWARD_SONAR,
        {
            KEY_SLOPE: -0.12,
            KEY_LOOKAHEAD_M: 5.0,
            "step": 1,
            "sim_time": 0.1,
            "ts": 123.456,
        },
    )

    assert ok
    assert errors == []


def test_altitude_topic_rejects_missing_altitude() -> None:
    ok, errors = validate_sensor_payload(Z_PATH_ALTITUDE, {"step": 1})

    assert not ok
    assert "missing keys: ['altitude_m']" in errors


def test_forward_sonar_topic_rejects_non_numeric_fields() -> None:
    ok, errors = validate_sensor_payload(
        Z_PATH_FORWARD_SONAR,
        {
            KEY_SLOPE: "steep",
            KEY_LOOKAHEAD_M: None,
        },
    )

    assert not ok
    assert "slope must be a number" in errors
    assert "lookahead_m must be a number" in errors

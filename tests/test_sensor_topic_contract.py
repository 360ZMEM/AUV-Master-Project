from common.protocol import (
    KEY_ALTITUDE_M,
    KEY_LOOKAHEAD_M,
    KEY_POINT_X_M,
    KEY_POINT_Y_M,
    KEY_SAMPLE_COUNT,
    KEY_SAMPLE_RATE_HZ,
    KEY_SLOPE,
    KEY_TIME_OFFSET_S,
    KEY_X_NT,
    KEY_Y_NT,
    KEY_Z_NT,
    Z_PATH_ALTITUDE,
    Z_PATH_CABLE_SONAR_OBSERVATION,
    Z_PATH_FORWARD_SONAR,
    Z_PATH_MAGNETIC_BLOCK,
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


def test_magnetic_block_contract_checks_array_lengths() -> None:
    ok, errors = validate_sensor_payload(
        Z_PATH_MAGNETIC_BLOCK,
        {
            KEY_SAMPLE_RATE_HZ: 2000.0,
            KEY_SAMPLE_COUNT: 2,
            KEY_TIME_OFFSET_S: [-0.0005, 0.0],
            KEY_X_NT: [1.0, 2.0],
            KEY_Y_NT: [1.0, 2.0],
            KEY_Z_NT: [1.0, 2.0],
        },
    )
    assert ok
    assert errors == []

    ok, errors = validate_sensor_payload(
        Z_PATH_MAGNETIC_BLOCK,
        {
            KEY_SAMPLE_RATE_HZ: 2000.0,
            KEY_SAMPLE_COUNT: 2,
            KEY_TIME_OFFSET_S: [0.0],
            KEY_X_NT: [1.0, 2.0],
            KEY_Y_NT: [1.0, 2.0],
            KEY_Z_NT: [1.0, 2.0],
        },
    )
    assert not ok
    assert "magnetic block arrays must have equal lengths" in errors


def test_cable_sonar_observation_contract() -> None:
    ok, errors = validate_sensor_payload(
        Z_PATH_CABLE_SONAR_OBSERVATION,
        {
            KEY_POINT_X_M: [1.0, 2.0],
            KEY_POINT_Y_M: [0.1, 0.2],
            "detector_score": 2.0,
            "contrast_to_noise_ratio": 8.0,
            "visible_length_m": 1.0,
            "ambiguity_margin": 0.7,
        },
    )
    assert ok
    assert errors == []

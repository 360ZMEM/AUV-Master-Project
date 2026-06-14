from __future__ import annotations

import numpy as np

from common.sensor_extrinsics import (
    SensorExtrinsics,
    base_velocity_to_sensor,
    depth_at_sensor,
    rpy_deg_to_matrix,
    sensor_velocity_to_base,
)


def test_identity_extrinsic_preserves_velocity() -> None:
    ext = SensorExtrinsics.identity()
    v_base = np.array([1.2, -0.3, 0.4])
    omega = np.array([0.0, 0.0, 0.2])

    v_sensor = base_velocity_to_sensor(v_base, omega, ext)
    v_back = sensor_velocity_to_base(v_sensor, omega, ext)

    assert np.allclose(v_sensor, v_base)
    assert np.allclose(v_back, v_base)


def test_lever_arm_velocity_term_uses_omega_cross_r() -> None:
    ext = SensorExtrinsics(
        translation_b_m=np.array([1.0, 0.0, 0.0]),
        rotation_b_to_s=np.eye(3),
    )
    v_base = np.zeros(3)
    omega = np.array([0.0, 0.0, 2.0])

    v_sensor = base_velocity_to_sensor(v_base, omega, ext)

    assert np.allclose(v_sensor, [0.0, 2.0, 0.0])
    assert np.allclose(sensor_velocity_to_base(v_sensor, omega, ext), v_base)


def test_rotation_roundtrip_between_base_and_sensor() -> None:
    ext = SensorExtrinsics(
        translation_b_m=np.zeros(3),
        rotation_b_to_s=rpy_deg_to_matrix([0.0, 0.0, 90.0]),
    )
    v_base = np.array([1.0, 0.0, 0.0])
    omega = np.zeros(3)

    v_sensor = base_velocity_to_sensor(v_base, omega, ext)

    assert np.allclose(v_sensor, [0.0, 1.0, 0.0], atol=1e-12)
    assert np.allclose(sensor_velocity_to_base(v_sensor, omega, ext), v_base, atol=1e-12)


def test_depth_at_sensor_includes_body_frame_lever_arm() -> None:
    ext = SensorExtrinsics(
        translation_b_m=np.array([0.0, 0.0, -0.2]),
        rotation_b_to_s=np.eye(3),
    )
    p_base = np.array([0.0, 0.0, -10.0])
    r_nb = np.eye(3)

    assert depth_at_sensor(p_base, r_nb, ext) == 10.2

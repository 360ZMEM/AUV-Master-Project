from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from algorithm.es_ekf import ES_EKF, _skew, quat_multiply, quat_normalize, quat_to_rotmat, small_angle_quat
from common.sensor_extrinsics import SensorExtrinsics, base_velocity_to_sensor, depth_at_sensor, rpy_deg_to_matrix


def _cfg(**extra):
    cfg = {
        "gravity": 9.81,
        "sigma_acc": 0.08,
        "sigma_gyro": 0.01,
        "sigma_ba": 0.001,
        "sigma_bg": 0.0005,
        "sigma_dvl": 0.03,
        "sigma_depth": 0.05,
        "imu_acc_is_linear": True,
        "auto_init": False,
        "use_first_dvl_for_init": False,
        "use_first_depth_for_init": False,
        "init_pos": [0.0, 0.0, -10.0],
        "init_vel": [1.0, 0.2, 0.0],
        "init_quat_wxyz": [1.0, 0.0, 0.0, 0.0],
        "init_ba": [0.0, 0.0, 0.0],
        "init_bg": [0.0, 0.0, 0.0],
        "init_P_diag": [0.5] * 3 + [0.5] * 3 + [0.2] * 3 + [0.05] * 3 + [0.05] * 3,
    }
    cfg.update(extra)
    return cfg


def _state_tuple(filter_obj: ES_EKF) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    state = filter_obj.get_state()
    return state["p"], state["v"], state["q"]


def test_correct_dvl_sensor_matches_body_dvl_for_identity_extrinsic() -> None:
    f_body = ES_EKF(_cfg())
    f_sensor = ES_EKF(_cfg())
    measurement = np.array([1.0, 0.2, 0.0])

    f_body.correct_dvl(measurement)
    f_sensor.correct_dvl_sensor(measurement, gyro_body=np.zeros(3))

    for left, right in zip(_state_tuple(f_body), _state_tuple(f_sensor)):
        assert np.allclose(left, right)


def test_correct_depth_sensor_matches_depth_for_identity_extrinsic() -> None:
    f_depth = ES_EKF(_cfg())
    f_sensor = ES_EKF(_cfg())

    f_depth.correct_depth(10.0)
    f_sensor.correct_depth_sensor(10.0)

    for left, right in zip(_state_tuple(f_depth), _state_tuple(f_sensor)):
        assert np.allclose(left, right)


def test_matching_dvl_extrinsic_has_smaller_state_update_than_uncorrected() -> None:
    ext_cfg = {
        "dvl": {
            "translation_b_m": [0.5, 0.0, 0.0],
            "rotation_rpy_deg": [0.0, 0.0, 2.0],
        }
    }
    f_corrected = ES_EKF(_cfg(sensor_extrinsics=ext_cfg))
    f_uncorrected = ES_EKF(_cfg())
    initial_v = f_corrected.get_state()["v"].copy()
    gyro = np.array([0.0, 0.0, 0.3])
    r_nb = quat_to_rotmat(f_corrected.get_state()["q"])
    v_base_b = r_nb.T @ initial_v
    measurement = base_velocity_to_sensor(
        v_base_b,
        gyro,
        SensorExtrinsics.from_config(ext_cfg["dvl"]),
    )

    f_corrected.correct_dvl_sensor(measurement, gyro_body=gyro)
    f_uncorrected.correct_dvl_sensor(measurement, gyro_body=gyro)

    corrected_delta = np.linalg.norm(f_corrected.get_state()["v"] - initial_v)
    uncorrected_delta = np.linalg.norm(f_uncorrected.get_state()["v"] - initial_v)
    assert corrected_delta < 1e-9
    assert uncorrected_delta > corrected_delta


def test_matching_depth_extrinsic_has_smaller_state_update_than_uncorrected() -> None:
    ext_cfg = {
        "depth": {
            "translation_b_m": [0.0, 0.0, -0.25],
            "rotation_rpy_deg": [0.0, 0.0, 0.0],
        }
    }
    f_corrected = ES_EKF(_cfg(sensor_extrinsics=ext_cfg))
    f_uncorrected = ES_EKF(_cfg())
    initial_p = f_corrected.get_state()["p"].copy()
    r_nb = quat_to_rotmat(f_corrected.get_state()["q"])
    measurement = depth_at_sensor(
        initial_p,
        r_nb,
        SensorExtrinsics.from_config(ext_cfg["depth"]),
    )

    f_corrected.correct_depth_sensor(measurement)
    f_uncorrected.correct_depth_sensor(measurement)

    corrected_delta = np.linalg.norm(f_corrected.get_state()["p"] - initial_p)
    uncorrected_delta = np.linalg.norm(f_uncorrected.get_state()["p"] - initial_p)
    assert corrected_delta < 1e-9
    assert uncorrected_delta > corrected_delta


def test_dvl_sensor_attitude_jacobian_matches_left_error_finite_difference() -> None:
    q = quat_normalize(np.array([0.98, 0.05, -0.02, 0.18], dtype=float))
    v_world = np.array([0.8, -0.2, 0.1], dtype=float)
    omega = np.array([0.01, -0.02, 0.3], dtype=float)
    ext = SensorExtrinsics(
        translation_b_m=np.array([0.2, -0.1, 0.05], dtype=float),
        rotation_b_to_s=rpy_deg_to_matrix([2.0, -1.0, 5.0]),
    )
    r_nb = quat_to_rotmat(q)
    analytic = ext.rotation_b_to_s @ (r_nb.T @ _skew(v_world))

    eps = 1e-6
    numeric_cols = []
    for axis in range(3):
        delta = np.zeros(3, dtype=float)
        delta[axis] = eps
        q_plus = quat_multiply(small_angle_quat(delta), q)
        q_minus = quat_multiply(small_angle_quat(-delta), q)
        h_plus = base_velocity_to_sensor(quat_to_rotmat(q_plus).T @ v_world, omega, ext)
        h_minus = base_velocity_to_sensor(quat_to_rotmat(q_minus).T @ v_world, omega, ext)
        numeric_cols.append((h_plus - h_minus) / (2.0 * eps))
    numeric = np.column_stack(numeric_cols)

    assert np.allclose(analytic, numeric, atol=1e-8)


def test_depth_sensor_attitude_jacobian_matches_left_error_finite_difference() -> None:
    q = quat_normalize(np.array([0.98, 0.05, -0.02, 0.18], dtype=float))
    p_world = np.array([1.0, 2.0, -10.0], dtype=float)
    ext = SensorExtrinsics(
        translation_b_m=np.array([0.2, -0.1, 0.05], dtype=float),
        rotation_b_to_s=np.eye(3),
    )
    r_nb = quat_to_rotmat(q)
    lever_world = r_nb @ ext.translation_b_m
    analytic = np.array([0.0, 0.0, 1.0], dtype=float) @ _skew(lever_world)

    eps = 1e-6
    numeric = []
    for axis in range(3):
        delta = np.zeros(3, dtype=float)
        delta[axis] = eps
        q_plus = quat_multiply(small_angle_quat(delta), q)
        q_minus = quat_multiply(small_angle_quat(-delta), q)
        h_plus = depth_at_sensor(p_world, quat_to_rotmat(q_plus), ext)
        h_minus = depth_at_sensor(p_world, quat_to_rotmat(q_minus), ext)
        numeric.append((h_plus - h_minus) / (2.0 * eps))

    assert np.allclose(analytic, np.asarray(numeric), atol=1e-8)

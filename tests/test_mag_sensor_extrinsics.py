import numpy as np

from common.sensor_extrinsics import base_position_to_sensor_world, load_extrinsics_map


def test_mag_extrinsics_map_has_6d_truth_and_estimate_shape():
    truth = load_extrinsics_map(
        {
            "mag": {
                "translation_b_m": [0.30, 0.00, -0.05],
                "rotation_rpy_deg": [0.0, 0.0, 2.0],
            }
        }
    )
    estimated = load_extrinsics_map(
        {
            "mag": {
                "translation_b_m": [0.20, 0.03, -0.02],
                "rotation_rpy_deg": [0.0, 0.0, 0.5],
            }
        }
    )

    assert truth["mag"].translation_b_m.shape == (3,)
    assert truth["mag"].rotation_b_to_s.shape == (3, 3)
    assert estimated["mag"].translation_b_m.shape == (3,)
    assert estimated["mag"].rotation_b_to_s.shape == (3, 3)


def test_mag_lever_arm_changes_sensor_world_position():
    extrinsics = load_extrinsics_map(
        {
            "mag": {
                "translation_b_m": [0.30, 0.10, -0.05],
                "rotation_rpy_deg": [0.0, 0.0, 0.0],
            }
        }
    )
    base_position = np.array([10.0, 2.0, 12.0], dtype=float)
    r_nb = np.eye(3)

    sensor_position = base_position_to_sensor_world(base_position, r_nb, extrinsics["mag"])

    assert np.allclose(sensor_position, [10.30, 2.10, 11.95])

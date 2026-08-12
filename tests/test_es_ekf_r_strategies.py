"""Tests for fixed, per-source adaptive, and robust ES-EKF updates."""

from __future__ import annotations

import unittest

import numpy as np

from algorithm.es_ekf import ES_EKF


def config(**overrides) -> dict:
    payload = {
        "auto_init": False,
        "imu_acc_is_linear": True,
        "init_pos": [0.0, 0.0, -10.0],
        "init_vel": [0.0, 0.0, 0.0],
        "init_quat_wxyz": [1.0, 0.0, 0.0, 0.0],
        "nis_window_size": 3,
        "nis_threshold": 1.0,
        "adaptive_r_normalized_threshold": 1.0,
    }
    payload.update(overrides)
    return payload


class TestESEKFRStrategies(unittest.TestCase):
    def test_fixed_r_never_changes_scale(self) -> None:
        filter_obj = ES_EKF(config(adaptive_r_mode="fixed"))
        for _ in range(6):
            filter_obj.correct_depth(20.0)
        self.assertEqual(filter_obj._adaptive_r_scale, 1.0)
        self.assertEqual(filter_obj._source_adaptive_r_scale, {})
        self.assertTrue(
            all(entry["r_scale"] == 1.0 for entry in filter_obj.nis_history)
        )

    def test_per_source_adaptation_does_not_cross_contaminate(self) -> None:
        filter_obj = ES_EKF(config(adaptive_r_mode="per_source"))
        for _ in range(6):
            filter_obj.correct_depth(20.0)
        self.assertGreater(filter_obj._source_adaptive_r_scale["depth"], 1.0)
        self.assertNotIn("dvl_world", filter_obj._source_adaptive_r_scale)

    def test_huber_records_robust_downweighting(self) -> None:
        filter_obj = ES_EKF(
            config(
                adaptive_r_mode="fixed",
                robust_huber_delta=1.0,
            )
        )
        filter_obj.correct_dvl_world(np.array([10.0, 0.0, 0.0]))
        self.assertGreater(filter_obj.nis_history[-1]["robust_scale"], 1.0)

    def test_invalid_adaptive_mode_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            ES_EKF(config(adaptive_r_mode="mixed"))


if __name__ == "__main__":
    unittest.main()

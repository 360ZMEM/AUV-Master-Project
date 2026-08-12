"""Regression tests for the R18/R19 offline evidence runner."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np

from tools.es_ekf_long_horizon_replay import (
    R18_SCENARIOS,
    build_dvl_schedule,
    load_measured_noise,
)


class TestESEKFLongHorizonReplay(unittest.TestCase):
    def test_voltage_conversion_centers_axes_and_preserves_correlation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "noise.npz"
            base = np.sin(np.linspace(0.0, 8.0 * np.pi, 400))
            voltage = np.column_stack((base, 2.0 * base, -base)) * 0.001
            np.savez(
                path,
                voltage=voltage,
                sensitivity_mv_per_ut=np.array([20.0, 20.0, 20.0]),
                sample_rate_hz=np.array(2000, dtype=np.int32),
            )
            noise_t, rate_hz, metadata = load_measured_noise(path)
        np.testing.assert_allclose(np.mean(noise_t, axis=0), 0.0, atol=1e-20)
        self.assertEqual(rate_hz, 2000.0)
        self.assertGreater(metadata["axis_correlation"][0][1], 0.99)
        self.assertLess(metadata["axis_correlation"][0][2], -0.99)

    def test_dvl_schedule_is_deterministic_and_severity_ordered(self) -> None:
        baseline, baseline_diag = build_dvl_schedule(
            duration_s=300.0,
            dt=0.05,
            seed=2,
            scenario=R18_SCENARIOS["baseline"],
        )
        heavy_a, heavy_diag_a = build_dvl_schedule(
            duration_s=300.0,
            dt=0.05,
            seed=2,
            scenario=R18_SCENARIOS["dvl_dropout_60"],
        )
        heavy_b, heavy_diag_b = build_dvl_schedule(
            duration_s=300.0,
            dt=0.05,
            seed=2,
            scenario=R18_SCENARIOS["dvl_dropout_60"],
        )
        self.assertEqual(heavy_a, heavy_b)
        self.assertEqual(heavy_diag_a, heavy_diag_b)
        self.assertGreater(len(baseline), len(heavy_a))
        self.assertEqual(baseline_diag["dvl_retained_rate"], 1.0)
        self.assertAlmostEqual(heavy_diag_a["dvl_retained_rate"], 0.4, delta=0.05)


if __name__ == "__main__":
    unittest.main()

"""Contract tests for the R21 factorized native scenario generator."""

from __future__ import annotations

import unittest

import numpy as np

from algorithm.native_cable_scenario import (
    NativeCableScenario,
    NativeScenarioFactors,
)


def replay_noise() -> np.ndarray:
    phase = np.linspace(0.0, 20.0 * np.pi, 2000, endpoint=False)
    base = 1e-7 * np.sin(phase)
    return np.column_stack((base, 0.8 * base, 1.1 * base))


class TestNativeCableScenario(unittest.TestCase):
    def make(self, factors: NativeScenarioFactors) -> NativeCableScenario:
        return NativeCableScenario(
            factors=factors,
            seed=3,
            replay_noise_t=replay_noise(),
            replay_rate_hz=2000.0,
            sample_rate_hz=100.0,
        )

    def test_measurement_mode_does_not_change_truth(self) -> None:
        replay = self.make(NativeScenarioFactors(measured_noise_replay=True))
        gaussian = self.make(NativeScenarioFactors(measured_noise_replay=False))
        position = np.array([12.0, 1.0, 12.0])
        truth_replay, measurement_replay = replay.sample(
            position_ned=position,
            time_s=1.0,
            sample_index=10,
        )
        truth_gaussian, measurement_gaussian = gaussian.sample(
            position_ned=position,
            time_s=1.0,
            sample_index=10,
        )
        np.testing.assert_allclose(
            truth_replay["magnetic_field_t"],
            truth_gaussian["magnetic_field_t"],
        )
        self.assertFalse(
            np.array_equal(
                measurement_replay["magnetic_field_t"],
                measurement_gaussian["magnetic_field_t"],
            )
        )

    def test_cross_current_switch_is_orthogonal(self) -> None:
        current_on = self.make(NativeScenarioFactors(cross_current_enabled=True))
        current_off = self.make(NativeScenarioFactors(cross_current_enabled=False))
        self.assertGreater(np.linalg.norm(current_on.current_velocity_ned(10.0)), 0.0)
        np.testing.assert_allclose(current_off.current_velocity_ned(10.0), 0.0)
        np.testing.assert_allclose(current_on.cable.points, current_off.cable.points)

    def test_buried_gap_suppresses_sonar_visibility(self) -> None:
        scenario = self.make(NativeScenarioFactors(terrain_enabled=True))
        position = np.array([25.0, 0.0, 12.0])
        truth, _measurement = scenario.sample(
            position_ned=position,
            time_s=1.0,
            sample_index=0,
        )
        self.assertGreater(truth["burial_depth_m"], 0.8)
        self.assertFalse(truth["sonar_visible"])


if __name__ == "__main__":
    unittest.main()

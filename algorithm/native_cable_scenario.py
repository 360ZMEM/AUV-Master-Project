"""Factorized native cable scenario with separated truth and measurements."""

from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np

from sim_holoocean.interfaces.perception_engine import (
    CablePath,
    compute_biot_savart_hvdc,
)
from sim_holoocean.interfaces.synthetic_sensors import berlin_noise_2d


@dataclass(frozen=True)
class NativeScenarioFactors:
    curved_geometry: bool = True
    terrain_enabled: bool = True
    measured_noise_replay: bool = True
    cross_current_enabled: bool = True


class NativeCableScenario:
    """Generate paired physical truth and sensor observations.

    Measurement noise is never written into the truth payload. Factor switches
    are orthogonal so later factorial experiments can identify interactions.
    """

    def __init__(
        self,
        *,
        factors: NativeScenarioFactors,
        seed: int,
        replay_noise_t: np.ndarray,
        replay_rate_hz: float,
        sample_rate_hz: float = 100.0,
    ) -> None:
        noise = np.asarray(replay_noise_t, dtype=float)
        if noise.ndim != 2 or noise.shape[1] != 3 or noise.shape[0] < 2:
            raise ValueError("replay_noise_t must be N x 3")
        self.factors = factors
        self.seed = int(seed)
        self.replay_noise_t = noise.copy()
        self.replay_rate_hz = float(replay_rate_hz)
        self.sample_rate_hz = float(sample_rate_hz)
        self.rng = np.random.default_rng(self.seed)
        self.noise_covariance = np.cov(noise, rowvar=False)
        self.replay_phase = int(self.rng.integers(0, noise.shape[0]))
        self.cable = CablePath(self._build_cable_points())

    def terrain_depth(self, x: float, y: float) -> float:
        if not self.factors.terrain_enabled:
            return 15.0
        relief = 1.5 * berlin_noise_2d(
            x,
            y,
            seed=100 + self.seed,
            octaves=4,
            scale=7.0,
        )
        slope = 0.035 * max(0.0, x - 10.0)
        return 15.0 + relief + slope

    def burial_depth(self, x: float) -> float:
        if not self.factors.terrain_enabled:
            return 0.15
        base = 0.25 + 0.10 * math.sin(0.11 * x)
        if 22.0 <= x <= 30.0:
            return 1.40
        return base

    def _build_cable_points(self) -> np.ndarray:
        if self.factors.curved_geometry:
            xy = np.asarray(
                [
                    [0.0, 0.0],
                    [10.0, 4.0],
                    [20.0, -3.0],
                    [30.0, 5.0],
                    [40.0, -4.0],
                    [50.0, 0.0],
                ],
                dtype=float,
            )
        else:
            xy = np.column_stack((np.linspace(0.0, 50.0, 6), np.zeros(6)))
        points = []
        for x, y in xy:
            points.append(
                [
                    float(x),
                    float(y),
                    self.terrain_depth(float(x), float(y))
                    + self.burial_depth(float(x)),
                ]
            )
        return np.asarray(points, dtype=float)

    def current_velocity_ned(self, time_s: float) -> np.ndarray:
        if not self.factors.cross_current_enabled:
            return np.zeros(3, dtype=float)
        return np.array(
            [
                0.05 * math.sin(0.07 * time_s),
                0.35 + 0.08 * math.sin(0.13 * time_s),
                0.0,
            ],
            dtype=float,
        )

    def _magnetic_noise(self, sample_index: int) -> np.ndarray:
        if self.factors.measured_noise_replay:
            step = self.replay_rate_hz / self.sample_rate_hz
            index = (
                self.replay_phase + int(round(sample_index * step))
            ) % self.replay_noise_t.shape[0]
            return self.replay_noise_t[index].copy()
        return self.rng.multivariate_normal(
            np.zeros(3, dtype=float),
            self.noise_covariance,
        )

    def _sonar_observation(
        self,
        distance_m: float,
        visible: bool,
        bin_count: int = 128,
        max_range_m: float = 25.0,
    ) -> np.ndarray:
        bins = self.rng.normal(0.0, 0.02, size=bin_count)
        if visible:
            center = int(
                np.clip(
                    round(distance_m / max_range_m * (bin_count - 1)),
                    0,
                    bin_count - 1,
                )
            )
            axis = np.arange(bin_count, dtype=float)
            bins += 0.9 * np.exp(-0.5 * ((axis - center) / 3.0) ** 2)
        return bins

    def sample(
        self,
        *,
        position_ned: np.ndarray,
        time_s: float,
        sample_index: int,
    ) -> tuple[dict[str, object], dict[str, object]]:
        position = np.asarray(position_ned, dtype=float).reshape(3)
        cable_point, cable_distance = self.cable.closest_point_and_distance(position)
        burial = self.burial_depth(float(cable_point[0]))
        terrain = self.terrain_depth(float(position[0]), float(position[1]))
        magnetic_truth = compute_biot_savart_hvdc(
            position,
            self.cable,
            current_amp=500.0,
        )
        current = self.current_velocity_ned(time_s)
        sonar_visible = burial < 0.8

        truth = {
            "time_s": float(time_s),
            "position_ned": position.copy(),
            "terrain_depth_m": float(terrain),
            "cable_point_ned": cable_point.copy(),
            "cable_distance_m": float(cable_distance),
            "burial_depth_m": float(burial),
            "magnetic_field_t": magnetic_truth.copy(),
            "current_velocity_ned": current.copy(),
            "sonar_visible": bool(sonar_visible),
        }
        magnetic_measurement = magnetic_truth + self._magnetic_noise(sample_index)
        sonar = self._sonar_observation(cable_distance, sonar_visible)
        measurement = {
            "time_s": float(time_s),
            "magnetic_field_t": magnetic_measurement,
            "sonar_bins": sonar,
            "sonar_peak": float(np.max(sonar)),
            "dvl_water_velocity_bias_ned": -current.copy(),
        }
        return truth, measurement

    def transect(self, duration_s: float = 50.0) -> tuple[list[dict], list[dict]]:
        count = int(round(duration_s * self.sample_rate_hz))
        truths: list[dict] = []
        measurements: list[dict] = []
        for index in range(count):
            time_s = index / self.sample_rate_hz
            x = min(50.0, time_s)
            y = 2.0 * math.sin(0.16 * x)
            terrain = self.terrain_depth(x, y)
            position = np.array([x, y, terrain - 3.0], dtype=float)
            truth, measurement = self.sample(
                position_ned=position,
                time_s=time_s,
                sample_index=index,
            )
            truths.append(truth)
            measurements.append(measurement)
        return truths, measurements

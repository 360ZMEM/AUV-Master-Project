"""Synthetic digital-twin scene generation helpers.

This module keeps the terrain/cable generation logic reusable between the live
HoloOcean bridge and the mock visualization fallback.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any

import numpy as np

from common.physics import CABLE_SUSPENSION_HEIGHT, SEA_BOTTOM_Z
from common.protocol import (
    KEY_CENTER_NED,
    KEY_HEIGHT_M,
    KEY_POINTS_NED,
    KEY_POSITION_NED,
    KEY_RADIUS_M,
    KEY_RPY_NED,
    KEY_TRAIL_NED,
    Z_PATH_CABLE_MARKER,
    Z_PATH_HISTORY_TRAIL,
    Z_PATH_SEABED_CLOUD,
    Z_PATH_TRUTH_POSE,
    Z_PATH_VIEW_RANGE,
)


@dataclass(slots=True)
class VirtualEnvironmentConfig:
    terrain_extent_m: float = 50.0
    terrain_resolution_m: float = 1.0
    terrain_noise_amplitude_m: float = 0.08
    terrain_noise_scale_m: float = 8.0
    terrain_noise_octaves: int = 3
    terrain_seed: int = 7
    seabed_z_m: float = SEA_BOTTOM_Z
    cable_suspension_height_m: float = CABLE_SUSPENSION_HEIGHT
    cable_origin_ned: tuple[float, float, float] = (0.0, 0.0, 14.0)
    cable_direction_ned: tuple[float, float, float] = (1.0, 0.0, 0.0)
    cable_length_m: float = 60.0
    cable_step_m: float = 1.0
    view_radius_m: float = 3.0
    view_height_m: float = 0.1
    trail_limit: int = 800


def _smoothstep(value: float) -> float:
    return value * value * (3.0 - 2.0 * value)


def _value_noise_2d(x: float, y: float, seed: int) -> float:
    """Deterministic Berlin-style value noise on a unit lattice."""
    x0 = math.floor(x)
    y0 = math.floor(y)
    x1 = x0 + 1
    y1 = y0 + 1

    def _hash(ix: int, iy: int) -> float:
        value = (ix * 374761393 + iy * 668265263 + seed * 1442695040888963407) & 0xFFFFFFFFFFFFFFFF
        value ^= value >> 13
        value *= 1274126177
        value &= 0xFFFFFFFFFFFFFFFF
        return ((value >> 11) & 0xFFFF) / 0x7FFF - 1.0

    sx = _smoothstep(x - x0)
    sy = _smoothstep(y - y0)
    n00 = _hash(x0, y0)
    n10 = _hash(x1, y0)
    n01 = _hash(x0, y1)
    n11 = _hash(x1, y1)
    ix0 = n00 + sx * (n10 - n00)
    ix1 = n01 + sx * (n11 - n01)
    return ix0 + sy * (ix1 - ix0)


def berlin_noise_2d(x: float, y: float, *, seed: int = 7, octaves: int = 3, scale: float = 8.0, persistence: float = 0.5) -> float:
    """Generate a smoothed terrain noise value using layered lattice noise."""
    if octaves <= 0:
        raise ValueError("octaves must be > 0")
    total = 0.0
    amplitude = 1.0
    frequency = 1.0 / max(scale, 1e-6)
    max_amplitude = 0.0
    for octave in range(octaves):
        total += amplitude * _value_noise_2d(x * frequency, y * frequency, seed + octave * 101)
        max_amplitude += amplitude
        amplitude *= persistence
        frequency *= 2.0
    return total / max_amplitude if max_amplitude > 1e-12 else 0.0


def euler_to_quaternion(roll: float, pitch: float, yaw: float) -> tuple[float, float, float, float]:
    cr = math.cos(roll * 0.5)
    sr = math.sin(roll * 0.5)
    cp = math.cos(pitch * 0.5)
    sp = math.sin(pitch * 0.5)
    cy = math.cos(yaw * 0.5)
    sy = math.sin(yaw * 0.5)
    return (
        sr * cp * cy - cr * sp * sy,
        cr * sp * cy + sr * cp * sy,
        cr * cp * sy - sr * sp * cy,
        cr * cp * cy + sr * sp * sy,
    )


class VirtualEnvironment:
    def __init__(self, config: dict[str, Any] | None = None):
        cfg = config or {}
        self.config = VirtualEnvironmentConfig(
            terrain_extent_m=float(cfg.get("terrain_extent_m", 50.0)),
            terrain_resolution_m=float(cfg.get("terrain_resolution_m", 1.0)),
            terrain_noise_amplitude_m=float(cfg.get("terrain_noise_amplitude_m", 0.08)),
            terrain_noise_scale_m=float(cfg.get("terrain_noise_scale_m", 8.0)),
            terrain_noise_octaves=int(cfg.get("terrain_noise_octaves", 3)),
            terrain_seed=int(cfg.get("terrain_seed", 7)),
            seabed_z_m=float(cfg.get("seabed_z_m", SEA_BOTTOM_Z)),
            cable_suspension_height_m=float(cfg.get("cable_suspension_height_m", CABLE_SUSPENSION_HEIGHT)),
            cable_origin_ned=tuple(float(v) for v in cfg.get("cable_origin_ned", (0.0, 0.0, 14.0))[:3]),
            cable_direction_ned=tuple(float(v) for v in cfg.get("cable_direction_ned", (1.0, 0.0, 0.0))[:3]),
            cable_length_m=float(cfg.get("cable_length_m", 60.0)),
            cable_step_m=float(cfg.get("cable_step_m", 1.0)),
            view_radius_m=float(cfg.get("view_radius_m", 3.0)),
            view_height_m=float(cfg.get("view_height_m", 0.1)),
            trail_limit=int(cfg.get("trail_limit", 800)),
        )
        self._trail: list[list[float]] = []

    def _terrain_height(self, x: float, y: float) -> float:
        noise = berlin_noise_2d(
            x,
            y,
            seed=self.config.terrain_seed,
            octaves=self.config.terrain_noise_octaves,
            scale=self.config.terrain_noise_scale_m,
        )
        return self.config.seabed_z_m + self.config.terrain_noise_amplitude_m * noise

    def sample_seabed_points(self, center_ned: np.ndarray | list[float]) -> list[list[float]]:
        center = np.asarray(center_ned, dtype=float).reshape(3)
        half = self.config.terrain_extent_m * 0.5
        step = max(self.config.terrain_resolution_m, 0.2)
        xs = np.arange(center[0] - half, center[0] + half + 1e-6, step, dtype=float)
        ys = np.arange(center[1] - half, center[1] + half + 1e-6, step, dtype=float)
        points: list[list[float]] = []
        for x in xs:
            for y in ys:
                z = self._terrain_height(float(x), float(y))
                points.append([float(x), float(y), float(z)])
        return points

    def cable_points(self) -> list[list[float]]:
        origin = np.asarray(self.config.cable_origin_ned, dtype=float).reshape(3)
        direction = np.asarray(self.config.cable_direction_ned, dtype=float).reshape(3)
        norm = float(np.linalg.norm(direction))
        if norm <= 1e-9:
            direction = np.array([1.0, 0.0, 0.0], dtype=float)
        else:
            direction = direction / norm

        cable_height = self.config.seabed_z_m - self.config.cable_suspension_height_m
        start_z = float(origin[2]) if abs(float(origin[2])) > 1e-9 else float(cable_height)
        start = np.array([origin[0], origin[1], start_z], dtype=float)
        step = max(self.config.cable_step_m, 0.2)
        count = max(2, int(math.ceil(self.config.cable_length_m / step)) + 1)
        return [
            [float(start[0] + direction[0] * step * i), float(start[1] + direction[1] * step * i), float(start[2] + direction[2] * step * i)]
            for i in range(count)
        ]

    def update_trail(self, position_ned: np.ndarray | list[float]) -> list[list[float]]:
        point = np.asarray(position_ned, dtype=float).reshape(3).tolist()
        self._trail.append([float(point[0]), float(point[1]), float(point[2])])
        if len(self._trail) > self.config.trail_limit:
            self._trail = self._trail[-self.config.trail_limit :]
        return list(self._trail)

    def sample_mock_pose(self, sample_index: int) -> tuple[list[float], list[float]]:
        """Generate a deterministic mock AUV pose from the shared virtual scene.

        The mock visualization bridge and the Foxglove snapshot generator both
        use this helper so the AUV track stays aligned with the same terrain,
        cable, and view-range configuration.
        """
        phase = float(sample_index) * 0.1
        x = 2.5 * math.sin(0.13 * phase)
        y = 1.2 * math.sin(0.07 * phase)
        z = float(self.config.seabed_z_m) - 3.0 + 0.18 * math.sin(0.05 * phase)
        roll = 0.03 * math.sin(0.17 * phase)
        pitch = 0.05 * math.sin(0.11 * phase)
        yaw = 0.2 * math.sin(0.08 * phase)
        return [x, y, z], [roll, pitch, yaw]

    def build_truth_pose_payload(self, position_ned: np.ndarray | list[float], rpy_ned: np.ndarray | list[float]) -> dict[str, Any]:
        position = np.asarray(position_ned, dtype=float).reshape(3).tolist()
        rpy = np.asarray(rpy_ned, dtype=float).reshape(3).tolist()
        return {
            KEY_POSITION_NED: [float(v) for v in position],
            KEY_RPY_NED: [float(v) for v in rpy],
        }

    def build_view_range_payload(self, position_ned: np.ndarray | list[float]) -> dict[str, Any]:
        center = np.asarray(position_ned, dtype=float).reshape(3).tolist()
        return {
            KEY_CENTER_NED: [float(v) for v in center],
            KEY_RADIUS_M: float(self.config.view_radius_m),
            KEY_HEIGHT_M: float(self.config.view_height_m),
        }

    def build_visual_payloads(
        self,
        *,
        position_ned: np.ndarray | list[float],
        rpy_ned: np.ndarray | list[float],
        publish_terrain: bool = True,
    ) -> dict[str, dict[str, Any]]:
        position = np.asarray(position_ned, dtype=float).reshape(3)
        payloads: dict[str, dict[str, Any]] = {
            Z_PATH_CABLE_MARKER: {KEY_POINTS_NED: self.cable_points()},
            Z_PATH_TRUTH_POSE: self.build_truth_pose_payload(position, rpy_ned),
            Z_PATH_HISTORY_TRAIL: {KEY_TRAIL_NED: self.update_trail(position)},
            Z_PATH_VIEW_RANGE: self.build_view_range_payload(position),
        }
        if publish_terrain:
            payloads[Z_PATH_SEABED_CLOUD] = {KEY_POINTS_NED: self.sample_seabed_points(position)}
        return payloads

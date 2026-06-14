"""Sensor extrinsics helpers shared by ES-EKF, simulation, and benchmarks.

Conventions:
  - ``translation_b_m`` is the sensor origin relative to ``base_link`` in the
    base body frame, meters.
  - ``rotation_rpy_deg`` describes the sensor frame relative to the base body
    frame. The derived matrix maps base-frame vectors into sensor-frame vectors.
  - ``R_nb`` maps base body-frame vectors into the navigation/world frame.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Mapping

import numpy as np


def _as_vec3(value: object, default: tuple[float, float, float] = (0.0, 0.0, 0.0)) -> np.ndarray:
    if value is None:
        return np.asarray(default, dtype=float)
    if isinstance(value, str):
        parts = [part.strip() for part in value.split(",") if part.strip()]
        if len(parts) >= 3:
            return np.asarray([float(parts[0]), float(parts[1]), float(parts[2])], dtype=float)
        return np.asarray(default, dtype=float)
    try:
        values = list(value)  # type: ignore[arg-type]
    except TypeError:
        return np.asarray(default, dtype=float)
    if len(values) < 3:
        return np.asarray(default, dtype=float)
    return np.asarray([float(values[0]), float(values[1]), float(values[2])], dtype=float)


def rpy_deg_to_matrix(rpy_deg: object) -> np.ndarray:
    """Return Rz(yaw) * Ry(pitch) * Rx(roll) for degrees input."""
    roll_deg, pitch_deg, yaw_deg = _as_vec3(rpy_deg)
    roll = math.radians(float(roll_deg))
    pitch = math.radians(float(pitch_deg))
    yaw = math.radians(float(yaw_deg))

    cr, sr = math.cos(roll), math.sin(roll)
    cp, sp = math.cos(pitch), math.sin(pitch)
    cy, sy = math.cos(yaw), math.sin(yaw)

    rx = np.array(
        [[1.0, 0.0, 0.0], [0.0, cr, -sr], [0.0, sr, cr]],
        dtype=float,
    )
    ry = np.array(
        [[cp, 0.0, sp], [0.0, 1.0, 0.0], [-sp, 0.0, cp]],
        dtype=float,
    )
    rz = np.array(
        [[cy, -sy, 0.0], [sy, cy, 0.0], [0.0, 0.0, 1.0]],
        dtype=float,
    )
    return rz @ ry @ rx


def matrix_to_rpy_deg(rot: np.ndarray) -> np.ndarray:
    """Return roll/pitch/yaw degrees from a Rz*Ry*Rx rotation matrix."""
    r = np.asarray(rot, dtype=float).reshape(3, 3)
    pitch = math.atan2(-float(r[2, 0]), math.sqrt(float(r[0, 0]) ** 2 + float(r[1, 0]) ** 2))
    cp = math.cos(pitch)
    if abs(cp) > 1e-9:
        roll = math.atan2(float(r[2, 1]), float(r[2, 2]))
        yaw = math.atan2(float(r[1, 0]), float(r[0, 0]))
    else:
        roll = 0.0
        yaw = math.atan2(-float(r[0, 1]), float(r[1, 1]))
    return np.degrees(np.asarray([roll, pitch, yaw], dtype=float))


def skew(v: object) -> np.ndarray:
    x, y, z = _as_vec3(v)
    return np.array([[0.0, -z, y], [z, 0.0, -x], [-y, x, 0.0]], dtype=float)


@dataclass(frozen=True)
class SensorExtrinsics:
    """Rigid transform from base body frame to one sensor frame."""

    translation_b_m: np.ndarray
    rotation_b_to_s: np.ndarray

    @classmethod
    def identity(cls) -> "SensorExtrinsics":
        return cls(np.zeros(3, dtype=float), np.eye(3, dtype=float))

    @classmethod
    def from_config(cls, cfg: Mapping[str, Any] | None) -> "SensorExtrinsics":
        if not cfg:
            return cls.identity()
        translation = _as_vec3(
            cfg.get("translation_b_m", cfg.get("translation", cfg.get("offset_xyz"))),
        )
        if "rotation_matrix_b_to_s" in cfg:
            rotation = np.asarray(cfg["rotation_matrix_b_to_s"], dtype=float).reshape(3, 3)
        else:
            rotation = rpy_deg_to_matrix(
                cfg.get("rotation_rpy_deg", cfg.get("rotation", cfg.get("rpy_deg"))),
            )
        return cls(translation, rotation)

    @property
    def rotation_s_to_b(self) -> np.ndarray:
        return self.rotation_b_to_s.T

    @property
    def rotation_rpy_deg(self) -> np.ndarray:
        return matrix_to_rpy_deg(self.rotation_b_to_s)

    def is_identity(self, atol: float = 1e-12) -> bool:
        return bool(
            np.allclose(self.translation_b_m, 0.0, atol=atol)
            and np.allclose(self.rotation_b_to_s, np.eye(3), atol=atol)
        )


def load_sensor_extrinsics(cfg: Mapping[str, Any] | None, sensor_name: str) -> SensorExtrinsics:
    """Load one sensor extrinsic from a config mapping."""
    if not cfg:
        return SensorExtrinsics.identity()
    sensor_cfg = cfg.get(sensor_name, {}) if isinstance(cfg, Mapping) else {}
    return SensorExtrinsics.from_config(sensor_cfg if isinstance(sensor_cfg, Mapping) else {})


def load_extrinsics_map(cfg: Mapping[str, Any] | None) -> dict[str, SensorExtrinsics]:
    """Load known AUV sensor extrinsics with identity defaults."""
    names = ("imu", "dvl", "depth", "mag", "sonar", "camera")
    return {name: load_sensor_extrinsics(cfg, name) for name in names}


def base_velocity_to_sensor(
    v_base_b: object,
    omega_b: object,
    extrinsic: SensorExtrinsics,
) -> np.ndarray:
    """Predict sensor-frame linear velocity at the sensor origin."""
    v_b = _as_vec3(v_base_b)
    w_b = _as_vec3(omega_b)
    v_at_sensor_b = v_b + np.cross(w_b, extrinsic.translation_b_m)
    return extrinsic.rotation_b_to_s @ v_at_sensor_b


def sensor_velocity_to_base(
    v_sensor_s: object,
    omega_b: object,
    extrinsic: SensorExtrinsics,
) -> np.ndarray:
    """Convert sensor-frame linear velocity into base-origin body velocity."""
    v_sensor_b = extrinsic.rotation_s_to_b @ _as_vec3(v_sensor_s)
    return v_sensor_b - np.cross(_as_vec3(omega_b), extrinsic.translation_b_m)


def base_position_to_sensor_world(
    p_base_n: object,
    r_nb: np.ndarray,
    extrinsic: SensorExtrinsics,
) -> np.ndarray:
    """Return sensor origin position in world/navigation coordinates."""
    p = _as_vec3(p_base_n)
    return p + np.asarray(r_nb, dtype=float).reshape(3, 3) @ extrinsic.translation_b_m


def depth_at_sensor(
    p_base_n: object,
    r_nb: np.ndarray,
    extrinsic: SensorExtrinsics,
) -> float:
    """Return positive-down depth measured at a sensor origin.

    The main ES-EKF runtime keeps position.z in ROS-up convention, where an AUV
    below the surface has negative z. Therefore depth is ``-sensor_z``.
    """
    p_sensor = base_position_to_sensor_world(p_base_n, r_nb, extrinsic)
    return float(-p_sensor[2])


def apply_small_angle_error(
    extrinsic: SensorExtrinsics,
    *,
    delta_translation_b_m: object | None = None,
    delta_rotation_rpy_deg: object | None = None,
) -> SensorExtrinsics:
    """Return an extrinsic perturbed by small translation/rotation errors."""
    translation = extrinsic.translation_b_m + _as_vec3(delta_translation_b_m)
    rotation_delta = rpy_deg_to_matrix(delta_rotation_rpy_deg)
    return SensorExtrinsics(translation, rotation_delta @ extrinsic.rotation_b_to_s)

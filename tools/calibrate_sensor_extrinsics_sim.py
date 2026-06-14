#!/usr/bin/env python3
"""Simulated extrinsics calibration for the pure-script ES-EKF benchmark."""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import numpy as np
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from algorithm.es_ekf import quat_to_rotmat
from common.env_utils import get_output_dir
from common.sensor_extrinsics import SensorExtrinsics, base_velocity_to_sensor, matrix_to_rpy_deg, skew
from tools.es_ekf_extrinsics_benchmark import generate_trajectory, profile_by_name


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", default="light", choices=["light", "medium", "heavy"])
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--duration", type=float, default=120.0)
    parser.add_argument("--dt", type=float, default=0.05)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--dvl-noise-std", type=float, default=0.003)
    parser.add_argument("--depth-noise-std", type=float, default=0.0)
    return parser.parse_args()


def generate_dvl_calibration_motion(times: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Return a deliberately excited calibration motion for DVL extrinsics.

    The benchmark trajectory is mostly yaw/forward motion, which makes roll and
    parts of the DVL lever arm weakly observable. A calibration script can assume
    a short dedicated maneuver with sway/heave and multi-axis angular rates.
    """
    t = np.asarray(times, dtype=float)
    v_base_b = np.column_stack(
        (
            0.7 + 0.12 * np.sin(0.11 * t),
            0.18 * np.sin(0.17 * t + 0.4),
            0.10 * np.cos(0.13 * t - 0.2),
        )
    )
    omega_b = np.column_stack(
        (
            0.08 * np.sin(0.19 * t + 0.3),
            0.06 * np.cos(0.23 * t - 0.1),
            0.10 + 0.05 * np.sin(0.29 * t),
        )
    )
    return v_base_b, omega_b


def estimate_rotation_kabsch(base_vectors: np.ndarray, sensor_vectors: np.ndarray) -> np.ndarray:
    h = base_vectors.T @ sensor_vectors
    u, _, vh = np.linalg.svd(h)
    rot = vh.T @ u.T
    if np.linalg.det(rot) < 0.0:
        vh[-1, :] *= -1.0
        rot = vh.T @ u.T
    return rot


def estimate_lever_arm(
    *,
    v_base_b: np.ndarray,
    omega_b: np.ndarray,
    v_sensor_s: np.ndarray,
    rotation_b_to_s: np.ndarray,
) -> np.ndarray:
    v_sensor_b = rotation_b_to_s.T @ v_sensor_s.T
    residual = v_sensor_b.T - v_base_b
    a_rows: list[np.ndarray] = []
    b_rows: list[np.ndarray] = []
    for omega, res in zip(omega_b, residual):
        if np.linalg.norm(omega) < 1e-5:
            continue
        a_rows.append(skew(omega))
        b_rows.append(res)
    if not a_rows:
        return np.zeros(3, dtype=float)
    a = np.vstack(a_rows)
    b = np.concatenate(b_rows)
    r, *_ = np.linalg.lstsq(a, b, rcond=None)
    return np.asarray(r, dtype=float)


def estimate_depth_z_offset(traj, depth_meas: np.ndarray) -> float:
    base_depth = -traj.p[:, 2]
    return float(np.mean(base_depth - depth_meas))


def main() -> None:
    args = parse_args()
    rng = np.random.default_rng(args.seed)
    profile = profile_by_name(args.profile)
    traj = generate_trajectory(args.duration, args.dt)

    v_base_b, omega_b = generate_dvl_calibration_motion(traj.times)
    dvl_sensor = np.zeros_like(v_base_b)
    depth_meas = np.zeros(traj.times.size, dtype=float)
    for i in range(traj.times.size):
        r_nb = quat_to_rotmat(traj.q[i])
        dvl_sensor[i] = base_velocity_to_sensor(v_base_b[i], omega_b[i], profile.dvl)
        dvl_sensor[i] += rng.normal(0.0, args.dvl_noise_std, size=3)
        depth_meas[i] = -(
            traj.p[i] + r_nb @ profile.depth.translation_b_m
        )[2]
        depth_meas[i] += float(rng.normal(0.0, args.depth_noise_std))

    # Rotation is estimated first, ignoring the small lever-arm velocity term,
    # then alternated with the lever-arm least-squares estimate.
    rotation_est = estimate_rotation_kabsch(v_base_b, dvl_sensor)
    r_est = np.zeros(3, dtype=float)
    for _ in range(5):
        r_est = estimate_lever_arm(
            v_base_b=v_base_b,
            omega_b=omega_b,
            v_sensor_s=dvl_sensor,
            rotation_b_to_s=rotation_est,
        )
        rotation_base_vectors = np.asarray(
            [v + np.cross(w, r_est) for v, w in zip(v_base_b, omega_b)],
            dtype=float,
        )
        rotation_est = estimate_rotation_kabsch(rotation_base_vectors, dvl_sensor)
    depth_z = estimate_depth_z_offset(traj, depth_meas)
    dvl_ext = SensorExtrinsics(r_est, rotation_est)
    depth_ext = SensorExtrinsics(np.array([0.0, 0.0, depth_z], dtype=float), np.eye(3))

    output = args.output or (get_output_dir("results/es_ekf_extrinsics_calibration") / "estimated_extrinsics.yaml")
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "sensor_extrinsics": {
            "dvl": {
                "translation_b_m": [float(v) for v in dvl_ext.translation_b_m],
                "rotation_rpy_deg": [float(v) for v in matrix_to_rpy_deg(dvl_ext.rotation_b_to_s)],
            },
            "depth": {
                "translation_b_m": [float(v) for v in depth_ext.translation_b_m],
                "rotation_rpy_deg": [0.0, 0.0, 0.0],
            },
            "imu": {
                "translation_b_m": [0.0, 0.0, 0.0],
                "rotation_rpy_deg": [0.0, 0.0, 0.0],
            },
        },
        "metadata": {
            "profile": args.profile,
            "seed": args.seed,
            "samples_used": int(traj.times.size),
            "dvl_calibration_motion": "dedicated multi-axis velocity and angular-rate excitation",
            "depth_observability_note": "pure yaw/depth trajectory estimates depth z offset only; x/y depth lever arms are not observable in this first-stage script",
            "dvl_translation_error_m": float(np.linalg.norm(dvl_ext.translation_b_m - profile.dvl.translation_b_m)),
            "dvl_rotation_error_deg": float(
                np.linalg.norm(matrix_to_rpy_deg(dvl_ext.rotation_b_to_s) - matrix_to_rpy_deg(profile.dvl.rotation_b_to_s))
            ),
            "depth_z_error_m": float(abs(depth_ext.translation_b_m[2] - profile.depth.translation_b_m[2])),
        },
    }
    output.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=True), encoding="utf-8")
    print(f"[OK] wrote {output}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Pure-script ES-EKF sensor extrinsics benchmark.

This tool keeps the first extrinsics validation cheap: no ROS, no PVS, no MCAP.
It generates deterministic motion, corrupts synthetic sensor observations with
truth extrinsics, then runs ES-EKF with different estimated extrinsics.
"""

from __future__ import annotations

import argparse
import csv
import math
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from statistics import mean, stdev

import numpy as np
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from algorithm.es_ekf import ES_EKF, quat_to_rotmat
from common.env_utils import get_output_dir
from common.sensor_extrinsics import (
    SensorExtrinsics,
    apply_small_angle_error,
    base_velocity_to_sensor,
    depth_at_sensor,
)


@dataclass(frozen=True)
class Trajectory:
    times: np.ndarray
    p: np.ndarray
    v: np.ndarray
    acc_body: np.ndarray
    gyro_body: np.ndarray
    q: np.ndarray


@dataclass(frozen=True)
class ExtrinsicsProfile:
    name: str
    dvl: SensorExtrinsics
    depth: SensorExtrinsics
    imu: SensorExtrinsics


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--duration", type=float, default=120.0)
    parser.add_argument("--dt", type=float, default=0.05)
    parser.add_argument("--seeds", default="0,1,2")
    parser.add_argument("--true-profile", default="light")
    parser.add_argument("--estimation-modes", default="none,calibrated,online_lite")
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--estimated-extrinsics-yaml", type=Path, default=None)
    parser.add_argument("--debug-first-steps", type=int, default=0)
    parser.add_argument("--dvl-noise-std", type=float, default=0.005)
    parser.add_argument("--depth-noise-std", type=float, default=0.01)
    return parser.parse_args()


def split_csv(text: str) -> list[str]:
    return [item.strip() for item in text.split(",") if item.strip()]


def yaw_quat(yaw: float) -> np.ndarray:
    return np.array([math.cos(0.5 * yaw), 0.0, 0.0, math.sin(0.5 * yaw)], dtype=float)


def generate_trajectory(duration_s: float, dt: float) -> Trajectory:
    times = np.arange(0.0, duration_s, dt, dtype=float)
    n = times.size
    yaw = 0.35 * np.sin(0.055 * times) + 0.18 * np.sin(0.17 * times)
    yaw_rate = 0.35 * 0.055 * np.cos(0.055 * times) + 0.18 * 0.17 * np.cos(0.17 * times)
    speed = 0.75 + 0.12 * np.sin(0.09 * times)
    depth = 10.0 + 0.7 * np.sin(0.045 * times)

    p = np.zeros((n, 3), dtype=float)
    p[:, 2] = -depth
    v = np.zeros((n, 3), dtype=float)
    v[:, 0] = speed * np.cos(yaw)
    v[:, 1] = speed * np.sin(yaw)
    v[:, 2] = -0.7 * 0.045 * np.cos(0.045 * times)
    for i in range(1, n):
        p[i, :2] = p[i - 1, :2] + v[i - 1, :2] * dt

    a_world = np.gradient(v, dt, axis=0)
    q = np.asarray([yaw_quat(value) for value in yaw], dtype=float)
    acc_body = np.zeros_like(a_world)
    for i in range(n):
        acc_body[i] = quat_to_rotmat(q[i]).T @ a_world[i]
    gyro_body = np.column_stack((np.zeros(n), np.zeros(n), yaw_rate))
    return Trajectory(times=times, p=p, v=v, acc_body=acc_body, gyro_body=gyro_body, q=q)


def profile_by_name(name: str) -> ExtrinsicsProfile:
    name = name.strip().lower()
    profiles = {
        "none": ExtrinsicsProfile(
            "none",
            SensorExtrinsics.identity(),
            SensorExtrinsics.identity(),
            SensorExtrinsics.identity(),
        ),
        "light": ExtrinsicsProfile(
            "light",
            SensorExtrinsics.from_config({"translation_b_m": [0.05, 0.02, -0.01], "rotation_rpy_deg": [0.2, -0.1, 0.5]}),
            SensorExtrinsics.from_config({"translation_b_m": [0.04, 0.0, -0.05], "rotation_rpy_deg": [0.0, 0.0, 0.0]}),
            SensorExtrinsics.from_config({"translation_b_m": [0.02, 0.0, 0.01], "rotation_rpy_deg": [0.1, 0.0, -0.1]}),
        ),
        "medium": ExtrinsicsProfile(
            "medium",
            SensorExtrinsics.from_config({"translation_b_m": [0.15, 0.05, -0.03], "rotation_rpy_deg": [0.8, -0.5, 1.5]}),
            SensorExtrinsics.from_config({"translation_b_m": [0.10, 0.0, -0.12], "rotation_rpy_deg": [0.0, 0.0, 0.0]}),
            SensorExtrinsics.from_config({"translation_b_m": [0.05, 0.0, 0.02], "rotation_rpy_deg": [0.4, 0.2, -0.4]}),
        ),
        "heavy": ExtrinsicsProfile(
            "heavy",
            SensorExtrinsics.from_config({"translation_b_m": [0.30, 0.10, -0.05], "rotation_rpy_deg": [2.0, -1.2, 4.0]}),
            SensorExtrinsics.from_config({"translation_b_m": [0.20, 0.0, -0.25], "rotation_rpy_deg": [0.0, 0.0, 0.0]}),
            SensorExtrinsics.from_config({"translation_b_m": [0.10, 0.02, 0.04], "rotation_rpy_deg": [1.0, 0.5, -1.0]}),
        ),
    }
    if name not in profiles:
        raise ValueError(f"unknown profile: {name}")
    return profiles[name]


def estimated_profile(truth: ExtrinsicsProfile, mode: str) -> ExtrinsicsProfile:
    mode = mode.strip().lower()
    if mode == "none":
        return profile_by_name("none")
    if mode == "calibrated":
        return truth
    if mode == "no_lever_arm":
        # F2 消融：EKF 忽略 DVL 杆臂（translation 置 0），其余沿用真值标定。
        # 隔离杆臂项 w×r 缺失对速度观测的影响。
        dvl = SensorExtrinsics(np.zeros(3, dtype=float), truth.dvl.rotation_b_to_s.copy())
        return ExtrinsicsProfile(f"{truth.name}_{mode}", dvl, truth.depth, truth.imu)
    if mode == "no_mounting_angle":
        # F2 消融：DVL 安装角引入 5° yaw 偏差，其余沿用真值标定。
        # 隔离安装角误差对速度方向投影的影响。
        dvl = apply_small_angle_error(truth.dvl, delta_rotation_rpy_deg=[0.0, 0.0, 5.0])
        return ExtrinsicsProfile(f"{truth.name}_{mode}", dvl, truth.depth, truth.imu)
    if mode == "online_lite":
        dvl = apply_small_angle_error(
            truth.dvl,
            delta_translation_b_m=[0.005, -0.002, 0.0],
            delta_rotation_rpy_deg=[0.02, -0.01, 0.03],
        )
        depth = apply_small_angle_error(
            truth.depth,
            delta_translation_b_m=[0.002, 0.0, -0.002],
            delta_rotation_rpy_deg=[0.0, 0.0, 0.0],
        )
        imu = apply_small_angle_error(
            truth.imu,
            delta_translation_b_m=[0.002, 0.0, 0.0],
            delta_rotation_rpy_deg=[0.01, 0.0, -0.01],
        )
        return ExtrinsicsProfile(f"{truth.name}_{mode}", dvl, depth, imu)
    raise ValueError(f"unknown estimation mode: {mode}")


def load_estimated_profile(path: Path, truth: ExtrinsicsProfile, mode: str) -> ExtrinsicsProfile:
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    cfg = payload.get("sensor_extrinsics", payload.get("sensor_extrinsics_estimated", {})) or {}
    if not isinstance(cfg, dict):
        raise ValueError(f"invalid sensor extrinsics YAML: {path}")
    return ExtrinsicsProfile(
        f"{truth.name}_{mode}",
        SensorExtrinsics.from_config(cfg.get("dvl", {})),
        SensorExtrinsics.from_config(cfg.get("depth", {})),
        SensorExtrinsics.from_config(cfg.get("imu", {})),
    )


def blend_extrinsic(current: SensorExtrinsics, target: SensorExtrinsics, gain: float) -> SensorExtrinsics:
    translation = (1.0 - gain) * current.translation_b_m + gain * target.translation_b_m
    rotation = (1.0 - gain) * current.rotation_b_to_s + gain * target.rotation_b_to_s
    u, _, vh = np.linalg.svd(rotation)
    return SensorExtrinsics(translation, u @ vh)


def ekf_config(profile: ExtrinsicsProfile, traj: Trajectory) -> dict:
    return {
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
        "enable_bias_calibration": False,
        "init_pos": traj.p[0].tolist(),
        "init_vel": traj.v[0].tolist(),
        "init_quat_wxyz": traj.q[0].tolist(),
        "init_ba": [0.0, 0.0, 0.0],
        "init_bg": [0.0, 0.0, 0.0],
        "init_P_diag": [0.2] * 3 + [0.2] * 3 + [0.05] * 3 + [0.02] * 3 + [0.02] * 3,
        "sensor_extrinsics": {
            "dvl": {
                "translation_b_m": profile.dvl.translation_b_m.tolist(),
                "rotation_matrix_b_to_s": profile.dvl.rotation_b_to_s.tolist(),
            },
            "depth": {
                "translation_b_m": profile.depth.translation_b_m.tolist(),
                "rotation_matrix_b_to_s": profile.depth.rotation_b_to_s.tolist(),
            },
            "imu": {
                "translation_b_m": profile.imu.translation_b_m.tolist(),
                "rotation_matrix_b_to_s": profile.imu.rotation_b_to_s.tolist(),
            },
        },
    }


def run_case(
    *,
    truth_profile: ExtrinsicsProfile,
    estimation_mode: str,
    seed: int,
    duration_s: float,
    dt: float,
    dvl_noise_std: float,
    depth_noise_std: float,
    estimated_yaml: Path | None = None,
    debug_first_steps: int = 0,
) -> dict[str, object]:
    rng = np.random.default_rng(seed)
    traj = generate_trajectory(duration_s, dt)
    if estimation_mode == "calibrated_from_yaml":
        if estimated_yaml is None:
            raise ValueError("calibrated_from_yaml requires --estimated-extrinsics-yaml")
        est_profile = load_estimated_profile(estimated_yaml, truth_profile, estimation_mode)
    else:
        est_profile = estimated_profile(truth_profile, estimation_mode)
    filter_obj = ES_EKF(ekf_config(est_profile, traj))

    est_positions: list[np.ndarray] = []
    online_delta = 0.0
    dvl_stride = max(1, int(round(0.2 / dt)))

    for i in range(traj.times.size):
        if i > 0:
            filter_obj.predict(traj.acc_body[i], traj.gyro_body[i], dt)
        if estimation_mode == "online_lite" and i % max(1, int(round(1.0 / dt))) == 0 and i > 0:
            old = filter_obj.dvl_extrinsic
            new_dvl = blend_extrinsic(filter_obj.dvl_extrinsic, truth_profile.dvl, gain=0.03)
            new_depth = blend_extrinsic(filter_obj.depth_extrinsic, truth_profile.depth, gain=0.03)
            filter_obj.dvl_extrinsic = new_dvl
            filter_obj.depth_extrinsic = new_depth
            online_delta += float(np.linalg.norm(new_dvl.translation_b_m - old.translation_b_m))

        r_nb = quat_to_rotmat(traj.q[i])
        v_body = r_nb.T @ traj.v[i]
        dvl_meas = base_velocity_to_sensor(v_body, traj.gyro_body[i], truth_profile.dvl)
        dvl_meas = dvl_meas + rng.normal(0.0, dvl_noise_std, size=3)
        depth_meas = depth_at_sensor(traj.p[i], r_nb, truth_profile.depth)
        depth_meas = float(depth_meas + rng.normal(0.0, depth_noise_std))

        if debug_first_steps > 0 and i < debug_first_steps:
            est_state = filter_obj.get_state()
            r_est = quat_to_rotmat(est_state["q"])
            h_dvl = base_velocity_to_sensor(
                r_est.T @ est_state["v"],
                traj.gyro_body[i],
                filter_obj.dvl_extrinsic,
            )
            h_depth = depth_at_sensor(est_state["p"], r_est, filter_obj.depth_extrinsic)
            print(
                "[extrinsics-debug] "
                f"profile={truth_profile.name} mode={estimation_mode} seed={seed} step={i} "
                f"p_err={(est_state['p'] - traj.p[i]).tolist()} "
                f"v_err={(est_state['v'] - traj.v[i]).tolist()} "
                f"dvl_innov={(dvl_meas - h_dvl).tolist()} "
                f"depth_innov={float(depth_meas - h_depth):.9f}"
            )

        if i % dvl_stride == 0:
            filter_obj.correct_dvl_sensor(dvl_meas, gyro_body=traj.gyro_body[i])
        filter_obj.correct_depth_sensor(depth_meas)
        est_positions.append(filter_obj.get_state()["p"].copy())

    est = np.asarray(est_positions, dtype=float)
    truth = traj.p[: est.shape[0]]
    diff = est - truth
    xy = np.linalg.norm(diff[:, :2], axis=1)
    z = np.abs(diff[:, 2])
    d3 = np.linalg.norm(diff, axis=1)
    trans_error = float(np.linalg.norm(est_profile.dvl.translation_b_m - truth_profile.dvl.translation_b_m))
    rot_error = float(np.linalg.norm(est_profile.dvl.rotation_rpy_deg - truth_profile.dvl.rotation_rpy_deg))

    return {
        "profile": truth_profile.name,
        "estimation_mode": estimation_mode,
        "seed": seed,
        "status": "ok",
        "xy_rmse": float(np.sqrt(np.mean(xy * xy))),
        "z_rmse": float(np.sqrt(np.mean(z * z))),
        "rmse_3d": float(np.sqrt(np.mean(d3 * d3))),
        "cep50": float(np.percentile(xy, 50)),
        "max_drift": float(np.max(d3)),
        "dvl_nis_mean": float(np.nanmean([e["nis"] for e in filter_obj.nis_history if e["source"] == "dvl_sensor"])),
        "depth_nis_mean": float(np.nanmean([e["nis"] for e in filter_obj.nis_history if e["source"] == "depth_sensor"])),
        "extrinsic_translation_error_m": trans_error,
        "extrinsic_rotation_error_deg": rot_error,
        "calibration_success": estimation_mode in {"calibrated", "calibrated_from_yaml", "online_lite"},
        "online_correction_delta_norm": online_delta,
        "online_oracle": estimation_mode == "online_lite",
    }


def write_csv(path: Path, rows: list[dict[str, object]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def summarize(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    metrics = ["xy_rmse", "z_rmse", "rmse_3d", "cep50", "max_drift", "dvl_nis_mean", "depth_nis_mean"]
    groups: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        groups[(str(row["profile"]), str(row["estimation_mode"]))].append(row)
    out: list[dict[str, object]] = []
    for (profile, mode), group in sorted(groups.items()):
        item: dict[str, object] = {"profile": profile, "estimation_mode": mode, "run_count": len(group)}
        for metric in metrics:
            values = [float(row[metric]) for row in group]
            item[f"{metric}_mean"] = mean(values)
            item[f"{metric}_std"] = stdev(values) if len(values) > 1 else 0.0
        out.append(item)
    return out


def write_report(path: Path, summary_rows: list[dict[str, object]]) -> None:
    lines = [
        "# ES-EKF Extrinsics Benchmark",
        "",
        "| profile | mode | runs | XY RMSE | Z RMSE | 3D RMSE | CEP50 | Max Drift |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in summary_rows:
        lines.append(
            "| {profile} | {mode} | {runs} | {xy:.4f} | {z:.4f} | {r3:.4f} | {cep:.4f} | {drift:.4f} |".format(
                profile=row["profile"],
                mode=row["estimation_mode"],
                runs=row["run_count"],
                xy=row["xy_rmse_mean"],
                z=row["z_rmse_mean"],
                r3=row["rmse_3d_mean"],
                cep=row["cep50_mean"],
                drift=row["max_drift_mean"],
            )
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    args = parse_args()
    out_dir = args.output_dir or get_output_dir("results/es_ekf_extrinsics")
    out_dir.mkdir(parents=True, exist_ok=True)

    seeds = [int(seed) for seed in split_csv(args.seeds)]
    profiles = [profile_by_name(name) for name in split_csv(args.true_profile)]
    modes = split_csv(args.estimation_modes)
    rows = [
        run_case(
            truth_profile=profile,
            estimation_mode=mode,
            seed=seed,
            duration_s=args.duration,
            dt=args.dt,
            dvl_noise_std=args.dvl_noise_std,
            depth_noise_std=args.depth_noise_std,
            estimated_yaml=args.estimated_extrinsics_yaml,
            debug_first_steps=max(0, int(args.debug_first_steps)),
        )
        for profile in profiles
        for mode in modes
        for seed in seeds
    ]

    fieldnames = list(rows[0].keys()) if rows else []
    write_csv(out_dir / "results.csv", rows, fieldnames)
    summary_rows = summarize(rows)
    write_csv(out_dir / "summary_by_error_level.csv", summary_rows, list(summary_rows[0].keys()) if summary_rows else [])
    write_report(out_dir / "extrinsics_report.md", summary_rows)
    print(f"[OK] wrote {out_dir / 'results.csv'}")
    print(f"[OK] wrote {out_dir / 'summary_by_error_level.csv'}")
    print(f"[OK] wrote {out_dir / 'extrinsics_report.md'}")


if __name__ == "__main__":
    main()

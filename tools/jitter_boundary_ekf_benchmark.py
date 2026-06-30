#!/usr/bin/env python3
"""F3 — network jitter boundary test for ES-EKF DVL aiding (thesis §2.5.1 / §3.2.1).

This offline experiment injects transport-layer delay + jitter onto the DVL
stream feeding the ES-EKF, then sweeps the jitter magnitude to find the boundary
beyond which the filter degrades. For each jitter level it records the DVL NIS
(measurement consistency), the Kalman gain norm (newly exposed via ES_EKF.last_K),
and the velocity RMSE — three independent witnesses of filter health. The critical
jitter is reported as the first level where DVL NIS exceeds a multiple of the
nominal (no-jitter) NIS. NIS (not state RMSE) is the boundary metric because the
adaptive-R ES-EKF down-weights inconsistent DVL (gain norm falls with jitter) and
falls back on IMU dead-reckoning + depth, keeping the state bounded; NIS climbs
monotonically and exposes the moment the DVL stream can no longer be trusted.

Reuses TransportDelayQueue (mock_amd_delay) for delay/jitter and ES_EKF for state
estimation, with a deterministic synthetic trajectory.
"""

from __future__ import annotations

import argparse
import csv
import math
import random
import sys
from dataclasses import dataclass
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from algorithm.es_ekf import ES_EKF, quat_to_rotmat  # noqa: E402
from common.env_utils import get_output_dir  # noqa: E402
from sim_holoocean.interfaces.mock_amd_delay import TransportDelayQueue  # noqa: E402


@dataclass(frozen=True)
class Trajectory:
    times: np.ndarray
    p: np.ndarray
    v: np.ndarray
    acc_body: np.ndarray
    gyro_body: np.ndarray
    q: np.ndarray


def yaw_quat(yaw: float) -> np.ndarray:
    return np.array([math.cos(0.5 * yaw), 0.0, 0.0, math.sin(0.5 * yaw)], dtype=float)


def generate_trajectory(duration_s: float, dt: float) -> Trajectory:
    times = np.arange(0.0, duration_s, dt, dtype=float)
    n = times.size
    # Aggressive dynamics on purpose: DVL aids body velocity, so a stale/jittered
    # DVL packet only hurts when velocity changes appreciably within the delay
    # window. Fast yaw + speed modulation makes a 0.1-0.5 s lag genuinely wrong.
    yaw = 0.8 * np.sin(0.30 * times) + 0.25 * np.sin(0.95 * times)
    yaw_rate = 0.8 * 0.30 * np.cos(0.30 * times) + 0.25 * 0.95 * np.cos(0.95 * times)
    speed = 1.2 + 0.6 * np.sin(0.50 * times)
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


def ekf_config(traj: Trajectory) -> dict:
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
    }


def run_jitter_case(
    *,
    traj: Trajectory,
    dt: float,
    base_delay_ms: float,
    jitter_ms: float,
    dvl_noise_std: float,
    seed: int,
) -> dict[str, float]:
    """Run one EKF pass with DVL delivered through a delay/jitter queue.

    The DVL is corrected using the *stale* measurement released by the queue while
    the filter time advances, emulating a network that reorders/ages DVL packets.
    """
    rng = np.random.default_rng(seed)
    filter_obj = ES_EKF(ekf_config(traj))
    queue = TransportDelayQueue(
        base_delay_ms=base_delay_ms,
        jitter_ms=jitter_ms,
        max_queue_depth=256,
        _rng=random.Random(seed),
    )
    dvl_stride = max(1, int(round(0.2 / dt)))

    est_positions: list[np.ndarray] = []
    est_velocities: list[np.ndarray] = []
    gain_norms: list[float] = []

    for i in range(traj.times.size):
        now = float(traj.times[i])
        if i > 0:
            filter_obj.predict(traj.acc_body[i], traj.gyro_body[i], dt)

        # Generate a fresh DVL packet on stride and enqueue it with its capture time.
        if i % dvl_stride == 0:
            r_nb = quat_to_rotmat(traj.q[i])
            v_body = r_nb.T @ traj.v[i]
            dvl_meas = v_body + rng.normal(0.0, dvl_noise_std, size=3)
            queue.enqueue((dvl_meas, traj.gyro_body[i].copy()), now)

        # Release whatever DVL packets the network has delivered by now and apply.
        for (meas, gyro), _recv_ts in queue.dequeue(now):
            filter_obj.correct_dvl_sensor(meas, gyro_body=gyro)
            if filter_obj.last_K is not None:
                gain_norms.append(float(np.linalg.norm(filter_obj.last_K)))

        filter_obj.correct_depth(float(-traj.p[i, 2]))
        state = filter_obj.get_state()
        est_positions.append(state["p"].copy())
        est_velocities.append(state["v"].copy())

    est = np.asarray(est_positions, dtype=float)
    est_v = np.asarray(est_velocities, dtype=float)
    truth = traj.p[: est.shape[0]]
    truth_v = traj.v[: est_v.shape[0]]
    diff = est - truth
    vel_diff = est_v - truth_v
    xy = np.linalg.norm(diff[:, :2], axis=1)
    d3 = np.linalg.norm(diff, axis=1)
    vel_err = np.linalg.norm(vel_diff, axis=1)
    dvl_nis = [e["nis"] for e in filter_obj.nis_history if e["source"] == "dvl_sensor"]
    return {
        "base_delay_ms": base_delay_ms,
        "jitter_ms": jitter_ms,
        "seed": seed,
        "vel_rmse_mps": float(np.sqrt(np.mean(vel_err * vel_err))),
        "xy_rmse_m": float(np.sqrt(np.mean(xy * xy))),
        "rmse_3d_m": float(np.sqrt(np.mean(d3 * d3))),
        "max_drift_m": float(np.max(d3)),
        "gain_norm_mean": float(np.mean(gain_norms)) if gain_norms else float("nan"),
        "gain_norm_max": float(np.max(gain_norms)) if gain_norms else float("nan"),
        "dvl_nis_mean": float(np.nanmean(dvl_nis)) if dvl_nis else float("nan"),
        "pending_overflow": int(queue.peek_count()),
    }


def aggregate(rows: list[dict[str, float]]) -> list[dict[str, float]]:
    """Average across seeds per jitter level."""
    by_jitter: dict[float, list[dict[str, float]]] = {}
    for row in rows:
        by_jitter.setdefault(row["jitter_ms"], []).append(row)
    metrics = ["vel_rmse_mps", "xy_rmse_m", "rmse_3d_m", "max_drift_m",
               "gain_norm_mean", "gain_norm_max", "dvl_nis_mean"]
    out: list[dict[str, float]] = []
    for jitter in sorted(by_jitter):
        group = by_jitter[jitter]
        item: dict[str, float] = {"jitter_ms": jitter, "run_count": len(group)}
        for metric in metrics:
            vals = [r[metric] for r in group if math.isfinite(r[metric])]
            item[f"{metric}_mean"] = float(np.mean(vals)) if vals else float("nan")
        out.append(item)
    return out


def find_critical_jitter(summary: list[dict[str, float]], rmse_multiple: float) -> float:
    """First jitter level where mean DVL NIS exceeds rmse_multiple x nominal.

    DVL NIS (normalized innovation squared) is the boundary metric because it
    measures measurement-prediction consistency directly — exactly what network
    jitter destroys when stale/reordered DVL packets disagree with the predicted
    body velocity. The state RMSE (velocity/XY position) is a poor boundary metric
    here: the adaptive-R ES-EKF down-weights inconsistent DVL (gain norm falls with
    jitter) and falls back on IMU dead-reckoning + depth, so the state estimate
    stays bounded while NIS climbs monotonically. NIS therefore reveals the moment
    the DVL stream can no longer be trusted, even before the state visibly diverges.
    """
    if not summary:
        return float("nan")
    nominal = summary[0]["dvl_nis_mean_mean"]
    threshold = rmse_multiple * nominal
    for item in summary:
        if item["dvl_nis_mean_mean"] > threshold:
            return item["jitter_ms"]
    return float("nan")


def write_csv(path: Path, rows: list[dict[str, float]], fieldnames: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def plot_boundary(path: Path, summary: list[dict[str, float]], critical: float) -> None:
    jitter = [s["jitter_ms"] for s in summary]
    nis = [s["dvl_nis_mean_mean"] for s in summary]
    gain = [s["gain_norm_mean_mean"] for s in summary]
    vel = [s["vel_rmse_mps_mean"] for s in summary]

    fig, axes = plt.subplots(3, 1, figsize=(8.2, 8.4), sharex=True)
    axes[0].plot(jitter, nis, "^-", color="#55a868")
    axes[0].set_ylabel("DVL NIS mean (boundary metric)")
    axes[0].set_title("ES-EKF DVL aiding under network jitter")
    axes[1].plot(jitter, gain, "s-", color="#4c72b0")
    axes[1].set_ylabel("mean |K| (Kalman gain norm)")
    axes[2].plot(jitter, vel, "o-", color="#c44e52")
    axes[2].set_ylabel("velocity RMSE (m/s)")
    axes[2].set_xlabel("jitter (ms)")
    for ax in axes:
        ax.grid(True, alpha=0.3)
        if math.isfinite(critical):
            ax.axvline(critical, color="#444444", linestyle="--", linewidth=1.0,
                       label=f"critical jitter {critical:.0f} ms")
    if math.isfinite(critical):
        axes[0].legend(frameon=False, loc="upper left")
    fig.tight_layout()
    for ext in ("png", "pdf"):
        fig.savefig(path.with_suffix(f".{ext}"), bbox_inches="tight")
    plt.close(fig)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--duration", type=float, default=120.0)
    parser.add_argument("--dt", type=float, default=0.05)
    parser.add_argument("--base-delay-ms", type=float, default=20.0)
    parser.add_argument("--jitter-ms", default="0,50,100,150,200,300,400,500")
    parser.add_argument("--seeds", default="0,1,2")
    parser.add_argument("--dvl-noise-std", type=float, default=0.005)
    parser.add_argument("--rmse-multiple", type=float, default=2.0)
    parser.add_argument("--output-dir", type=Path, default=None)
    args = parser.parse_args()

    out = args.output_dir or get_output_dir("results/es_ekf_jitter_boundary")
    out.mkdir(parents=True, exist_ok=True)

    jitters = [float(j) for j in args.jitter_ms.split(",") if j.strip()]
    seeds = [int(s) for s in args.seeds.split(",") if s.strip()]
    traj = generate_trajectory(args.duration, args.dt)

    rows: list[dict[str, float]] = []
    for jitter in jitters:
        for seed in seeds:
            print(f"[RUN] jitter={jitter:.0f}ms seed={seed}", flush=True)
            rows.append(run_jitter_case(
                traj=traj,
                dt=args.dt,
                base_delay_ms=args.base_delay_ms,
                jitter_ms=jitter,
                dvl_noise_std=args.dvl_noise_std,
                seed=seed,
            ))

    write_csv(out / "jitter_results.csv", rows, list(rows[0].keys()))
    summary = aggregate(rows)
    write_csv(out / "jitter_summary.csv", summary, list(summary[0].keys()))
    critical = find_critical_jitter(summary, args.rmse_multiple)
    plot_boundary(out / "jitter_boundary", summary, critical)

    with (out / "critical_jitter.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["metric", "value"])
        writer.writerow(["base_delay_ms", args.base_delay_ms])
        writer.writerow(["rmse_multiple", args.rmse_multiple])
        writer.writerow(["nominal_dvl_nis_mean", summary[0]["dvl_nis_mean_mean"]])
        writer.writerow(["nominal_vel_rmse_mps", summary[0]["vel_rmse_mps_mean"]])
        writer.writerow(["nominal_xy_rmse_m", summary[0]["xy_rmse_m_mean"]])
        writer.writerow(["critical_jitter_ms", critical])

    print(f"[OK] output: {out}")
    print(f"[OK] nominal DVL NIS={summary[0]['dvl_nis_mean_mean']:.5f}; "
          f"critical jitter={critical} ms (>{args.rmse_multiple}x nominal NIS)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

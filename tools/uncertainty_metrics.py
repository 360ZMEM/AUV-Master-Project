#!/usr/bin/env python3
"""Uncertainty / innovation post-processor for thesis chapter §3.4.

Consumes a single mcap (already produced by `start_experiment.sh`) and
re-runs the ES-EKF in playback mode to extract:

  - innovation magnitude time series (DVL, depth)
  - normalized innovation squared (NIS) proxy via innovation/gate ratio
  - covariance trace P(t) (xy, z)

Outputs:
  - <out>/uncertainty_timeseries.csv
  - <out>/uncertainty_innovation.png
  - <out>/uncertainty_nis.png
  - <out>/uncertainty_covariance.png

This is intentionally lighter than offline_ekf_benchmark.py: it does NOT
compare ES-EKF vs Std-EKF vs Raw DR; it only profiles the ES-EKF's
internal uncertainty signals so §3.4 (NIS whiteness check) and §4.4.2
(EKF→MPC coupling) can cite real numbers.
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import offline_ekf_benchmark as _bench  # noqa: E402

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
except Exception:
    plt = None


def _rolling_mean(arr: np.ndarray, window: int) -> np.ndarray:
    if arr.size == 0 or window <= 1:
        return arr
    a = np.asarray(arr, dtype=float)
    valid = ~np.isnan(a)
    a_filled = np.where(valid, a, 0.0)
    cs = np.cumsum(np.insert(a_filled, 0, 0.0))
    win = (cs[window:] - cs[:-window]) / float(window)
    pad = window // 2
    head = np.full(pad, win[0] if win.size else np.nan)
    tail = np.full(a.size - win.size - pad, win[-1] if win.size else np.nan)
    return np.concatenate([head, win, tail])[: a.size]


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Extract ES-EKF innovation/NIS/P-trace from an mcap.",
    )
    p.add_argument("--input", type=Path, required=True,
                   help="rosbag directory or .mcap file")
    p.add_argument("--output-dir", type=Path, required=True)
    p.add_argument("--ekf-config", type=Path,
                   default=Path(_bench.DEFAULT_EKF_CONFIG))
    p.add_argument("--imu-topic", default=_bench.DEFAULT_IMU_TOPIC)
    p.add_argument("--dvl-topic", default=_bench.DEFAULT_DVL_TOPIC)
    p.add_argument("--depth-topic", default=_bench.DEFAULT_DEPTH_TOPIC)
    p.add_argument("--dvl-frame", choices=["body", "world"], default="world")
    p.add_argument("--no-coordinate-transform", action="store_true")
    p.add_argument("--nis-window", type=int, default=50)
    p.add_argument("--dpi", type=int, default=300)
    args = p.parse_args(argv)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    _bench.ensure_runtime_dependencies()

    print(f"[uncertainty] reading {args.input}")
    imu, dvl, depth, _truth = _bench.read_mcap_sensor_data(
        mcap_path=args.input,
        imu_topic=args.imu_topic,
        dvl_topic=args.dvl_topic,
        depth_topic=args.depth_topic,
        truth_topics=[],
        dvl_frame=args.dvl_frame,
        apply_coord_transform=not args.no_coordinate_transform,
        verbose=True,
    )
    if not imu:
        print("[uncertainty][FATAL] no IMU samples; abort.", file=sys.stderr)
        return 2

    cfg = _bench.load_ekf_config(args.ekf_config)
    engine = _bench.EseKfEngine(cfg, auto_init=True)

    # Merge timeline ---------------------------------------------------------
    events: list[tuple[int, str, object]] = []
    events.extend((s.ts_ns, "imu", s) for s in imu)
    events.extend((s.ts_ns, "dvl", s) for s in dvl)
    events.extend((s.ts_ns, "depth", s) for s in depth)
    events.sort(key=lambda e: e[0])

    rows: list[dict[str, float]] = []
    last_dvl_innov = float("nan")
    last_depth_innov = float("nan")
    last_dvl_gate = float("nan")
    last_depth_gate = float("nan")
    last_imu_ts: int | None = None

    t0_ns = events[0][0] if events else 0

    for ts_ns, kind, payload in events:
        if kind == "imu":
            dt = 0.005 if last_imu_ts is None else max(
                (ts_ns - last_imu_ts) * 1e-9, 1e-4
            )
            last_imu_ts = ts_ns
            engine.predict(payload.acc, payload.gyro, dt=dt)
        elif kind == "dvl":
            engine.update_dvl(payload.vel, ts_ns=ts_ns)
            if engine.innovation_history:
                last_dvl_innov = engine.innovation_history[-1]
                last_dvl_gate = engine.innovation_gate_history[-1]
        elif kind == "depth":
            engine.update_depth(payload.depth_m, ts_ns=ts_ns)
            if engine.innovation_history:
                last_depth_innov = engine.innovation_history[-1]
                last_depth_gate = engine.innovation_gate_history[-1]

        # P trace via filter introspection
        try:
            P = getattr(engine.filter, "P", None)
            if P is not None:
                P = np.asarray(P)
                p_xy = float(np.trace(P[0:2, 0:2])) if P.shape[0] >= 2 else float("nan")
                p_z = float(P[2, 2]) if P.shape[0] >= 3 else float("nan")
            else:
                p_xy = p_z = float("nan")
        except Exception:
            p_xy = p_z = float("nan")

        # NIS proxy: (innov / gate)^2 — gate already accounts for sigma scale.
        nis_dvl = (last_dvl_innov / last_dvl_gate) ** 2 if last_dvl_gate and not np.isnan(last_dvl_gate) and last_dvl_gate > 0 else float("nan")
        nis_depth = (last_depth_innov / last_depth_gate) ** 2 if last_depth_gate and not np.isnan(last_depth_gate) and last_depth_gate > 0 else float("nan")

        # Real NIS from inner ES_EKF (E2). Falls back to NaN if attr missing.
        nis_real = float("nan")
        r_scale = 1.0
        try:
            inner = engine.filter
            if getattr(inner, "nis_history", None):
                nis_real = float(inner.nis_history[-1]["nis"])
            if hasattr(inner, "_adaptive_r_scale"):
                r_scale = float(inner._adaptive_r_scale)
        except Exception:
            pass

        rows.append({
            "t_s": (ts_ns - t0_ns) * 1e-9,
            "innov_dvl": last_dvl_innov,
            "innov_depth": last_depth_innov,
            "nis_dvl": nis_dvl,
            "nis_depth": nis_depth,
            "nis_real": nis_real,
            "r_scale": r_scale,
            "p_trace_xy": p_xy,
            "p_trace_z": p_z,
        })

    csv_path = args.output_dir / "uncertainty_timeseries.csv"
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        fns = ["t_s", "innov_dvl", "innov_depth", "nis_dvl",
               "nis_depth", "nis_real", "r_scale", "p_trace_xy", "p_trace_z"]
        w = csv.DictWriter(f, fieldnames=fns)
        w.writeheader()
        for r in rows:
            w.writerow(r)
    print(f"[uncertainty] saved: {csv_path}")

    if plt is None or not rows:
        return 0

    ts = np.array([r["t_s"] for r in rows])

    fig, ax = plt.subplots(1, 1, figsize=(9.0, 4.5), dpi=args.dpi)
    ax.plot(ts, [r["innov_dvl"] for r in rows], label="DVL innov", color="#1f77b4")
    ax.plot(ts, [r["innov_depth"] for r in rows], label="Depth innov", color="#d62728")
    ax.set_xlabel("Time [s]"); ax.set_ylabel("Innovation magnitude [m]")
    ax.set_title("ES-EKF Innovation Magnitude"); ax.legend()
    fig.savefig(args.output_dir / "uncertainty_innovation.png", dpi=args.dpi)
    plt.close(fig)

    nis_dvl = np.array([r["nis_dvl"] for r in rows], dtype=float)
    nis_depth = np.array([r["nis_depth"] for r in rows], dtype=float)
    nis_real = np.array([r["nis_real"] for r in rows], dtype=float)
    fig, ax = plt.subplots(1, 1, figsize=(9.0, 4.5), dpi=args.dpi)
    ax.plot(ts, _rolling_mean(nis_dvl, args.nis_window),
            label=f"NIS_DVL proxy (rolling {args.nis_window})", color="#1f77b4", alpha=0.6)
    ax.plot(ts, _rolling_mean(nis_depth, args.nis_window),
            label=f"NIS_Depth proxy (rolling {args.nis_window})", color="#d62728", alpha=0.6)
    if np.any(np.isfinite(nis_real)):
        ax.plot(ts, _rolling_mean(nis_real, args.nis_window),
                label=f"NIS_real (rolling {args.nis_window})", color="#2ca02c", lw=1.4)
    ax.axhline(1.0, color="k", ls="--", lw=0.8, label="ideal=1")
    ax.set_xlabel("Time [s]"); ax.set_ylabel("NIS")
    ax.set_title("Normalized Innovation Squared"); ax.legend()
    fig.savefig(args.output_dir / "uncertainty_nis.png", dpi=args.dpi)
    plt.close(fig)

    fig, ax = plt.subplots(1, 1, figsize=(9.0, 4.5), dpi=args.dpi)
    ax.plot(ts, [r["p_trace_xy"] for r in rows], label="trace(P_xy)", color="#1f77b4")
    ax.plot(ts, [r["p_trace_z"] for r in rows], label="P_z", color="#d62728")
    ax.set_xlabel("Time [s]"); ax.set_ylabel("Variance [m²]")
    ax.set_title("ES-EKF Covariance Trace"); ax.legend()
    fig.savefig(args.output_dir / "uncertainty_covariance.png", dpi=args.dpi)
    plt.close(fig)
    print(f"[uncertainty] saved 3 PNGs under {args.output_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Uncertainty / innovation post-processor for thesis chapter §3.4.

Consumes a single mcap (already produced by `start_experiment.sh`) and
re-runs the ES-EKF in playback mode to extract:

  - innovation magnitude time series (DVL, depth)
  - standard internal NIS events with source and measurement dimension
  - innovation/gate proxy diagnostics kept separate from standard NIS
  - covariance trace P(t) (xy, z)

Outputs:
  - <out>/uncertainty_timeseries.csv
  - <out>/nis_events.csv
  - <out>/nis_semantics.json
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
import json
import math
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


CHI2_TWO_SIDED_95 = {
    1: (0.000982069, 5.02388619),
    2: (0.050635616, 7.37775891),
    3: (0.215795283, 9.34840360),
}


def _chi2_two_sided_95(dim: int) -> tuple[float, float]:
    if dim in CHI2_TWO_SIDED_95:
        return CHI2_TWO_SIDED_95[dim]
    # Wilson-Hilferty approximation, sufficient for dimensions not used by
    # the current DVL/depth playback. Exact values are fixed above for m=1,3.
    z = 1.959963984540054
    center = 1.0 - 2.0 / (9.0 * dim)
    spread = math.sqrt(2.0 / (9.0 * dim))
    lower = dim * max(center - z * spread, 0.0) ** 3
    upper = dim * (center + z * spread) ** 3
    return lower, upper


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

    rows: list[dict[str, float | str | int]] = []
    nis_events: list[dict[str, float | str | int | bool]] = []
    last_imu_ts: int | None = None

    t0_ns = events[0][0] if events else 0

    for ts_ns, kind, payload in events:
        dvl_innov = float("nan")
        depth_innov = float("nan")
        dvl_gate = float("nan")
        depth_gate = float("nan")
        nis_real = float("nan")
        nis_source = ""
        nis_dim = 0
        nis_per_dof = float("nan")
        before_nis_count = len(getattr(engine.filter, "nis_history", []))
        if kind == "imu":
            dt = 0.005 if last_imu_ts is None else max(
                (ts_ns - last_imu_ts) * 1e-9, 1e-4
            )
            last_imu_ts = ts_ns
            engine.predict(payload.acc, payload.gyro, dt=dt)
        elif kind == "dvl":
            engine.update_dvl(payload.vel, ts_ns=ts_ns)
            if engine.innovation_history:
                dvl_innov = engine.innovation_history[-1]
                dvl_gate = engine.innovation_gate_history[-1]
        elif kind == "depth":
            engine.update_depth(payload.depth_m, ts_ns=ts_ns)
            if engine.innovation_history:
                depth_innov = engine.innovation_history[-1]
                depth_gate = engine.innovation_gate_history[-1]

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

        # Proxy values are event-local diagnostics, not standard NIS.
        nis_dvl = (dvl_innov / dvl_gate) ** 2 if dvl_gate and not np.isnan(dvl_gate) and dvl_gate > 0 else float("nan")
        nis_depth = (depth_innov / depth_gate) ** 2 if depth_gate and not np.isnan(depth_gate) and depth_gate > 0 else float("nan")

        r_scale = 1.0
        try:
            inner = engine.filter
            if hasattr(inner, "_adaptive_r_scale"):
                r_scale = float(inner._adaptive_r_scale)
            history = getattr(inner, "nis_history", [])
            if len(history) > before_nis_count:
                entry = history[-1]
                nis_real = float(entry["nis"])
                nis_source = str(entry["source"])
                nis_dim = int(entry["dim"])
                nis_per_dof = nis_real / nis_dim if nis_dim > 0 else float("nan")
                lower, upper = _chi2_two_sided_95(nis_dim)
                nis_events.append(
                    {
                        "t_s": (ts_ns - t0_ns) * 1e-9,
                        "source": nis_source,
                        "dimension": nis_dim,
                        "nis": nis_real,
                        "nis_per_dof": nis_per_dof,
                        "chi2_lower_95": lower,
                        "chi2_upper_95": upper,
                        "in_two_sided_95": lower <= nis_real <= upper,
                        "above_upper_95": nis_real > upper,
                        "r_scale_after_update": r_scale,
                    }
                )
        except Exception:
            pass

        rows.append({
            "t_s": (ts_ns - t0_ns) * 1e-9,
            "event_type": kind,
            "innov_dvl": dvl_innov,
            "innov_depth": depth_innov,
            "nis_dvl": nis_dvl,
            "nis_depth": nis_depth,
            "nis_real": nis_real,
            "nis_source": nis_source,
            "nis_dim": nis_dim,
            "nis_per_dof": nis_per_dof,
            "r_scale": r_scale,
            "p_trace_xy": p_xy,
            "p_trace_z": p_z,
        })

    csv_path = args.output_dir / "uncertainty_timeseries.csv"
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        fns = ["t_s", "event_type", "innov_dvl", "innov_depth", "nis_dvl",
               "nis_depth", "nis_real", "nis_source", "nis_dim",
               "nis_per_dof", "r_scale", "p_trace_xy", "p_trace_z"]
        w = csv.DictWriter(f, fieldnames=fns)
        w.writeheader()
        for r in rows:
            w.writerow(r)
    print(f"[uncertainty] saved: {csv_path}")

    nis_path = args.output_dir / "nis_events.csv"
    nis_fields = [
        "t_s",
        "source",
        "dimension",
        "nis",
        "nis_per_dof",
        "chi2_lower_95",
        "chi2_upper_95",
        "in_two_sided_95",
        "above_upper_95",
        "r_scale_after_update",
    ]
    with nis_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=nis_fields)
        writer.writeheader()
        writer.writerows(nis_events)
    semantics = {
        "schema_version": 1,
        "standard_nis": {
            "file": "nis_events.csv",
            "definition": "innovation.T @ S^-1 @ innovation",
            "event_sampling": "one row per ES-EKF measurement correction",
            "expected_mean": "measurement dimension",
            "confidence_interval": "chi-square two-sided 95 percent",
        },
        "proxy_diagnostics": {
            "columns": ["nis_dvl", "nis_depth"],
            "definition": "(innovation_magnitude / three_sigma_gate)^2",
            "standard_nis": False,
        },
        "adaptive_r_warning": (
            "The current ES-EKF adaptation window mixes NIS values from "
            "different measurement dimensions and compares their raw mean "
            "with one threshold (nis_threshold=9.0). This is not a valid "
            "chi-square calibration test and remains a negative result."
        ),
    }
    (args.output_dir / "nis_semantics.json").write_text(
        json.dumps(semantics, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"[uncertainty] saved: {nis_path}")

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

    fig, ax = plt.subplots(1, 1, figsize=(9.0, 4.5), dpi=args.dpi)
    colors = {"dvl_world": "#1f77b4", "depth": "#d62728"}
    for source in sorted({str(event["source"]) for event in nis_events}):
        selected = [event for event in nis_events if event["source"] == source]
        ax.scatter(
            [event["t_s"] for event in selected],
            [event["nis_per_dof"] for event in selected],
            s=8,
            alpha=0.55,
            label=f"{source} NIS/dof",
            color=colors.get(source),
        )
    ax.axhline(1.0, color="k", ls="--", lw=0.8, label="expected mean=1")
    ax.set_xlabel("Time [s]"); ax.set_ylabel("NIS / dof")
    ax.set_title("Standard NIS by Measurement Source"); ax.legend()
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

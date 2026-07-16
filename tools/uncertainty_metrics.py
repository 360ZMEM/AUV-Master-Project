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

When (and only when) a truth topic is supplied via ``--truth-topics``, this
runner additionally computes the position **NEES** (normalized estimation error
squared) against the ground-truth trajectory and emits:
  - <out>/nees_events.csv
  - <out>/nees_semantics.json
  - <out>/uncertainty_nees.png
NEES needs a truth trajectory, so with the default (empty) ``--truth-topics``
the tool behaves exactly as before and the NIS/timeseries artifacts stay
byte-for-byte identical (this preserves the covariance-A/B baseline口径).

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
    # E-3 分源协方差整定 A/B 覆盖开关（对应 24 号文档 O-3/O-4）。
    # 缺省一律为 None，此时不改写从 --ekf-config 读入的默认值，NIS 逐字节复现
    # 论文 §5.5.5 引用口径（深度 7.205 / DVL 0.119）；仅在显式传入时覆盖，作为
    # 独立实验对照，不改动 es_ekf.py / params.yaml 默认。
    p.add_argument("--sigma-dvl", type=float, default=None,
                   help="覆盖 ES-EKF DVL 速度观测标准差 sigma_dvl（缺省=不改）")
    p.add_argument("--sigma-depth", type=float, default=None,
                   help="覆盖 ES-EKF 深度观测标准差 sigma_depth（缺省=不改）")
    p.add_argument("--adaptive-r-mode", choices=["fixed", "global", "per_source"],
                   default=None,
                   help="覆盖自适应 R 模式（缺省=不改，默认口径为 global）")
    p.add_argument("--adaptive-r-normalized-threshold", type=float, default=None,
                   help="per_source 模式下按 NIS/自由度归一化的触发门限（缺省=不改）")
    # NEES（位置归一化估计误差平方）需要真值轨迹；缺省不读真值，行为与历史逐字节
    # 一致，保证 covariance-A/B baseline 的 nis_events/timeseries 不受影响。
    p.add_argument("--truth-topics", default="",
                   help="逗号分隔的真值位姿 topic；留空=不算 NEES（缺省，兼容旧口径）")
    p.add_argument("--truth-frame", default="auto",
                   help="真值坐标系（auto/ned/ue），透传给 read_mcap_sensor_data")
    args = p.parse_args(argv)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    _bench.ensure_runtime_dependencies()

    print(f"[uncertainty] reading {args.input}")
    truth_topic_list = [t.strip() for t in str(args.truth_topics).split(",") if t.strip()]
    imu, dvl, depth, truth = _bench.read_mcap_sensor_data(
        mcap_path=args.input,
        imu_topic=args.imu_topic,
        dvl_topic=args.dvl_topic,
        depth_topic=args.depth_topic,
        truth_topics=truth_topic_list,
        dvl_frame=args.dvl_frame,
        apply_coord_transform=not args.no_coordinate_transform,
        truth_frame=args.truth_frame,
        verbose=True,
    )
    if not imu:
        print("[uncertainty][FATAL] no IMU samples; abort.", file=sys.stderr)
        return 2

    cfg = _bench.load_ekf_config(args.ekf_config)
    # E-3 覆盖：仅在显式传参时改写协方差/自适应口径，缺省完全沿用配置文件默认，
    # 保证 baseline arm 与论文 §5.5.5 引用口径逐字节一致。
    overrides: dict[str, object] = {}
    if args.sigma_dvl is not None:
        overrides["sigma_dvl"] = float(args.sigma_dvl)
    if args.sigma_depth is not None:
        overrides["sigma_depth"] = float(args.sigma_depth)
    if args.adaptive_r_mode is not None:
        overrides["adaptive_r_mode"] = str(args.adaptive_r_mode)
    if args.adaptive_r_normalized_threshold is not None:
        overrides["adaptive_r_normalized_threshold"] = float(
            args.adaptive_r_normalized_threshold
        )
    if overrides:
        cfg = dict(cfg)
        cfg.update(overrides)
        print(f"[uncertainty] covariance overrides applied: {overrides}")
    engine = _bench.EseKfEngine(cfg, auto_init=True)

    # Merge timeline ---------------------------------------------------------
    events: list[tuple[int, str, object]] = []
    events.extend((s.ts_ns, "imu", s) for s in imu)
    events.extend((s.ts_ns, "dvl", s) for s in dvl)
    events.extend((s.ts_ns, "depth", s) for s in depth)
    events.sort(key=lambda e: e[0])

    rows: list[dict[str, float | str | int]] = []
    nis_events: list[dict[str, float | str | int | bool]] = []
    # NEES 快照：仅在提供真值时采集，(ts_ns, 估计位置[ROS-up], 位置协方差 3x3)。
    # 采集本身不写任何既有产物文件，故不影响 baseline 复现。
    nees_snapshots: list[tuple[int, np.ndarray, np.ndarray]] = []
    have_truth = bool(truth)
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

        # NEES 快照（仅在有真值时）：抓取 measurement-update 之后的滤波位置估计与
        # 3x3 位置协方差；预测步不采样（NEES 检验滤波一致性，按量测更新时刻取样）。
        if have_truth and kind in ("dvl", "depth"):
            try:
                P_arr = np.asarray(getattr(engine.filter, "P", None))
                p_est = np.asarray(engine.filter.get_state()["p"], dtype=float).reshape(3)
                if P_arr.shape[0] >= 3:
                    nees_snapshots.append((ts_ns, p_est.copy(), P_arr[0:3, 0:3].copy()))
            except Exception:
                pass

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
                # applied_r_scale：本次更新实际乘到 R 上的自适应比例（per_source
                # 模式下为该观测源自己的比例；global/fixed 下退化为全局比例/1.0）。
                # r_scale_after_update 只读全局累加器，在 per_source 模式会恒为
                # 1.0 而低估分源缩放，故此处补一个如实反映"实际生效"的列（纯新增，
                # 不改动既有列，baseline arm 既有列数值逐字节不变）。
                applied_r_scale = float(entry.get("r_scale", 1.0))
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
                        "applied_r_scale": applied_r_scale,
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
        "applied_r_scale",
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

    # ------------------------------------------------------------------ #
    # NEES（位置归一化估计误差平方）——仅在提供真值 topic 时计算。         #
    # NEES = e^T P^{-1} e，e = p_est - p_truth（同一 ROS-up 坐标系），      #
    # dim=3。ES-EKF 内部状态 p 为 ROS-up（z=-depth），真值以 NED 读入，     #
    # 通过 z 翻转（正交变换，NEES 不变）对齐到 ROS-up。                     #
    # ------------------------------------------------------------------ #
    nees_events: list[dict[str, float | int | bool]] = []
    if have_truth and nees_snapshots:
        truth_ts = np.array([s.ts_ns for s in truth], dtype=float)
        # NED -> ROS-up：x,y 不变，z 取反（与 _bench._ros_up_to_ned 互逆）。
        truth_p_rosup = np.array(
            [[s.pos[0], s.pos[1], -s.pos[2]] for s in truth], dtype=float
        )
        order = np.argsort(truth_ts)
        truth_ts = truth_ts[order]
        truth_p_rosup = truth_p_rosup[order]
        t_lo, t_hi = float(truth_ts[0]), float(truth_ts[-1])
        lower3, upper3 = _chi2_two_sided_95(3)

        def _truth_at(ts_ns: int) -> np.ndarray:
            return np.array(
                [np.interp(float(ts_ns), truth_ts, truth_p_rosup[:, i]) for i in range(3)]
            )

        # 水平原点对齐（规范自由度 gauge freedom）：ES-EKF 无持续绝对水平观测，
        # 其 x,y 原点由首帧自初始化（本工具锁 [0,0,0]），与真值坐标系原点相差一个
        # 常量偏置（本例 ~16.5 m）。该常量属坐标系差异、非滤波不一致，若不扣除会
        # 淹没真正的 DR 漂移一致性。故在首个可评估快照处取 x,y 常量偏置并对全程
        # 扣除；z 由深度计直接观测、真值同系，保持绝对不平移。这样全 3D NEES 检验
        # 的是"扣除不可观原点后的水平漂移 + 绝对深度"的协方差一致性。
        xy_gauge = np.zeros(2, dtype=float)
        for ts_ns, p_est, _P in nees_snapshots:
            if t_lo <= ts_ns <= t_hi:
                xy_gauge = (p_est[:2] - _truth_at(ts_ns)[:2]).astype(float)
                break

        for ts_ns, p_est, P_pos in nees_snapshots:
            if ts_ns < t_lo or ts_ns > t_hi:
                continue  # 不外推：只在真值时间覆盖区内评估
            truth_xyz = _truth_at(ts_ns)
            err = p_est - truth_xyz
            err[:2] -= xy_gauge  # 扣除不可观水平原点偏置（z 保持绝对）
            try:
                P_inv = np.linalg.inv(P_pos)
            except np.linalg.LinAlgError:
                continue
            nees_val = float(err @ P_inv @ err)
            # 深度子空间（dim=1）NEES：z 通道由深度计直接观测，可观，其
            # NEES 检验的是"可观子空间"的协方差一致性；与全 3D NEES 并列，
            # 后者仍受水平（x）可观性下界主导（见 semantics.boundary）。
            p_zz = float(P_pos[2, 2])
            nees_z = float(err[2] ** 2 / p_zz) if p_zz > 0 else float("nan")
            nees_events.append(
                {
                    "t_s": (ts_ns - t0_ns) * 1e-9,
                    "dimension": 3,
                    "nees": nees_val,
                    "nees_per_dof": nees_val / 3.0,
                    "nees_depth": nees_z,
                    "err_x": float(err[0]),
                    "err_y": float(err[1]),
                    "err_z": float(err[2]),
                    "chi2_lower_95": lower3,
                    "chi2_upper_95": upper3,
                    "in_two_sided_95": lower3 <= nees_val <= upper3,
                    "above_upper_95": nees_val > upper3,
                }
            )

        nees_path = args.output_dir / "nees_events.csv"
        nees_fields = [
            "t_s", "dimension", "nees", "nees_per_dof", "nees_depth",
            "err_x", "err_y", "err_z",
            "chi2_lower_95", "chi2_upper_95", "in_two_sided_95", "above_upper_95",
        ]
        with nees_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=nees_fields)
            writer.writeheader()
            writer.writerows(nees_events)

        # 聚合 ANEES（average NEES）与大样本一致性区间：N 个独立 dim=3 样本的
        # 平均 NEES 落在 [chi2_{0.025}(3N)/N, chi2_{0.975}(3N)/N] 内即一致。
        n = len(nees_events)
        anees = (sum(e["nees"] for e in nees_events) / n) if n else float("nan")
        cover = (sum(1 for e in nees_events if e["in_two_sided_95"]) / n) if n else float("nan")
        dof_total = 3 * n
        if n:
            lo_agg, hi_agg = _chi2_two_sided_95(dof_total)
            anees_lo, anees_hi = lo_agg / n, hi_agg / n
        else:
            anees_lo = anees_hi = float("nan")
        # 深度子空间（可观通道）ANEES：dim=1，落在 [chi2_{0.025}(N)/N,
        # chi2_{0.975}(N)/N] 内即一致。z 由深度计直接观测，这是唯一具备持续
        # 绝对量测的位置通道，故其 NEES 才真正检验标定质量而非可观性下界。
        nees_z_vals = [e["nees_depth"] for e in nees_events
                       if isinstance(e["nees_depth"], float) and e["nees_depth"] == e["nees_depth"]]
        n_z = len(nees_z_vals)
        anees_z = (sum(nees_z_vals) / n_z) if n_z else float("nan")
        if n_z:
            lo_z_agg, hi_z_agg = _chi2_two_sided_95(n_z)
            anees_z_lo, anees_z_hi = lo_z_agg / n_z, hi_z_agg / n_z
            lo1, hi1 = _chi2_two_sided_95(1)
            cover_z = sum(1 for v in nees_z_vals if lo1 <= v <= hi1) / n_z
        else:
            anees_z_lo = anees_z_hi = cover_z = float("nan")
        nees_semantics = {
            "schema_version": 2,
            "definition": "e^T P^{-1} e, e = p_est - p_truth (ROS-up), dim=3",
            "sample_count": n,
            "truth_topics": truth_topic_list,
            "event_sampling": "one row per DVL/depth measurement update within truth time span",
            "expected_mean_per_event": 3,
            "horizontal_gauge_alignment": (
                "x,y 原点在首个可评估量测处对齐（扣除不可观水平原点常量偏置）；"
                "z 保持绝对（深度计直接观测）。full-3D NEES 因此检验的是漂移一致性"
                "而非坐标系差异。"
            ),
            "anees": anees,
            "anees_consistency_interval": [anees_lo, anees_hi],
            "anees_consistent": bool(n and anees_lo <= anees <= anees_hi),
            "per_event_coverage_95": cover,
            "depth_subspace_nees": {
                "definition": "err_z^2 / P_zz, dim=1（深度计直接观测的可观通道）",
                "sample_count": n_z,
                "anees": anees_z,
                "anees_consistency_interval": [anees_z_lo, anees_z_hi],
                "anees_consistent": bool(n_z and anees_z_lo <= anees_z <= anees_z_hi),
                "per_event_coverage_95": cover_z,
            },
            "boundary": (
                "NEES 检验的是滤波协方差相对真值误差的一致性（乐观/保守/一致）；"
                "本口径为离线回放、单 bag，水平原点已按 gauge 对齐（扣除不可观常量"
                "偏置），全 3D NEES 仍受沿航向 DR 漂移主导；深度子空间 "
                "(depth_subspace_nees) 才是可观通道的一致性检验。"
            ),
        }
        (args.output_dir / "nees_semantics.json").write_text(
            json.dumps(nees_semantics, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(
            f"[uncertainty] saved: {nees_path} "
            f"(N={n}, 全3D ANEES={anees:.3f}/一致={nees_semantics['anees_consistent']}; "
            f"深度子空间 ANEES={anees_z:.3f}/一致={nees_semantics['depth_subspace_nees']['anees_consistent']})"
        )
    elif have_truth:
        print("[uncertainty][warn] 提供了真值 topic 但未采到 NEES 快照（无量测更新？）")

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
    png_count = 3

    if nees_events:
        nees_ts = np.array([e["t_s"] for e in nees_events])
        nees_pd = np.array([e["nees_per_dof"] for e in nees_events])
        nees_z = np.array([e["nees_depth"] for e in nees_events], dtype=float)
        lower3 = float(nees_events[0]["chi2_lower_95"]) / 3.0
        upper3 = float(nees_events[0]["chi2_upper_95"]) / 3.0
        lo1, hi1 = _chi2_two_sided_95(1)
        fig, (ax0, ax1) = plt.subplots(
            2, 1, figsize=(9.0, 7.2), dpi=args.dpi, sharex=True
        )
        # 上：全 3D NEES/dof（被水平可观性下界主导）。
        ax0.scatter(nees_ts, nees_pd, s=8, alpha=0.55, color="#2ca02c",
                    label="full 3D NEES/dof")
        ax0.axhline(1.0, color="k", ls="--", lw=0.8, label="expected mean=1")
        ax0.axhspan(lower3, upper3, color="#2ca02c", alpha=0.10,
                    label="per-event 95% χ²(3) band")
        ax0.set_ylabel("NEES / dof (3D)")
        ax0.set_title("ES-EKF Position NEES vs Ground Truth "
                      "(full 3D dominated by along-track observability floor)")
        ax0.legend(fontsize=8)
        # 下：深度子空间 NEES（dim=1，可观通道，检验标定一致性）。
        ax1.scatter(nees_ts, nees_z, s=8, alpha=0.55, color="#1f77b4",
                    label="depth-subspace NEES (dim=1)")
        ax1.axhline(1.0, color="k", ls="--", lw=0.8, label="expected mean=1")
        ax1.axhspan(lo1, hi1, color="#1f77b4", alpha=0.10,
                    label="per-event 95% χ²(1) band")
        ax1.set_xlabel("Time [s]"); ax1.set_ylabel("NEES (depth, dim=1)")
        ax1.set_title("Depth-subspace NEES (observable channel: consistency check)")
        ax1.legend(fontsize=8)
        fig.tight_layout()
        fig.savefig(args.output_dir / "uncertainty_nees.png", dpi=args.dpi)
        plt.close(fig)
        png_count += 1

    print(f"[uncertainty] saved {png_count} PNGs under {args.output_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

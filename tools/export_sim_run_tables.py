#!/usr/bin/env python3
"""Derived-table exporter for pure-simulation thesis experiments (27 号文 §1).

Reads a single recorded run (an ``.mcap`` file or a rosbag directory produced by
``start_experiment.sh`` / ``run_thesis_sweep.py``) and derives the structured
per-run tables requested in the experiment-upgrade plan:

  - ``trajectory.csv``     truth vs estimate positions/yaw + cross-track / depth error
  - ``estimator.csv``      ES-EKF covariance trace (xy, z, total); NIS/NEES kept as
                           explicit ``not_observed`` (filled by uncertainty_metrics.py / P1)
  - ``controller.csv``     MPC fin/thrust commands + solver solve_time / status
  - ``behavior_tree.csv``  active state, previous state, trigger, confidence,
                           fault_type, recovery_mode
  - ``sensor_status.csv``  confidence / leak / battery / anomaly / depth / speed / clearance
  - ``events.csv``         derived discrete events (BT transitions, first warnings)
  - ``metrics.json``       run-level summary + provenance + observed/missing topics

Design contract (aligned with 27 号文 §1):
  * This is a **read-only derived exporter**. It does not re-run any estimator or
    controller, does not touch ``es_ekf.py`` / ``params.yaml`` defaults, and does
    not modify the sweep main flow. Every column comes directly from a recorded
    topic; a column is emitted as ``not_observed`` when the source topic/field is
    absent, never fabricated.
  * Parsing conventions (timestamp selection, xyz/quaternion extraction, BT
    markdown parsing, controller-debug JSON) are reused from ``tools/analyze_bag.py``
    so this exporter stays consistent with the existing figure pipeline.

Usage:
    python3 tools/export_sim_run_tables.py \
        --input /auv_data/bags/20260612_170618/rosbag \
        --output-dir results/sim_baseline_patrol/<run>/tables \
        --run-id baseline_seed0
"""
from __future__ import annotations

import argparse
import bisect
import csv
import json
import math
from pathlib import Path
from typing import Any, Sequence

import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import analyze_bag as ab  # noqa: E402  (reuse parsing conventions)

NOT_OBSERVED = "not_observed"
NAN = float("nan")

# Topics consumed. Names mirror the runtime graph recorded by start_experiment.sh.
TRUTH_TOPIC = "/auv/sensors/ground_truth"
TRUTH_FALLBACKS = ("/auv/visual/truth_marker", "/auv/state/truth")
ESTIMATED_TOPIC = "/auv/state/filtered"
COVARIANCE_TOPIC = "/auv/state/covariance"
LATERAL_ERROR_TOPIC = "/auv/metrics/lateral_error"
DEPTH_ERROR_TOPIC = "/auv/metrics/depth_error"
MPC_CMD_TOPIC = "/auv/control/mpc_cmd"
CONTROLLER_DEBUG_TOPIC = "/auv/controller/debug"
SETPOINT_TOPIC = "/auv/control/setpoint"
BT_STATUS_TOPIC = "/auv/bt_status"
SENSOR_STATUS_TOPIC = "/auv/sensors/status"
DIAGNOSTICS_TOPIC = "/auv/diagnostics"


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------
def _quat_to_yaw(qw: float, qx: float, qy: float, qz: float) -> float:
    """Yaw (rad) from a wxyz quaternion."""
    siny_cosp = 2.0 * (qw * qz + qx * qy)
    cosy_cosp = 1.0 - 2.0 * (qy * qy + qz * qz)
    return math.atan2(siny_cosp, cosy_cosp)


def _extract_yaw(msg: Any) -> float:
    for path in (("pose", "pose", "orientation"), ("pose", "orientation"), ("orientation",)):
        try:
            ori = ab.nested_attr(msg, path)
        except AttributeError:
            continue
        if all(hasattr(ori, axis) for axis in ("w", "x", "y", "z")):
            return _quat_to_yaw(float(ori.w), float(ori.x), float(ori.y), float(ori.z))
    return NAN


def _fmt(value: Any) -> Any:
    """CSV cell formatter: keep sentinels, render finite floats compactly."""
    if value is None:
        return NOT_OBSERVED
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, float):
        if math.isnan(value):
            return "nan"
        return f"{value:.6g}"
    return value


def _write_csv(path: Path, fieldnames: Sequence[str], rows: Sequence[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fieldnames), extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: _fmt(row.get(key, NOT_OBSERVED)) for key in fieldnames})


class NearestLookup:
    """Nearest-neighbour scalar lookup keyed on sorted timestamps (ns)."""

    def __init__(self, timestamps_ns: Sequence[int], values: Sequence[float]) -> None:
        pairs = sorted(zip(timestamps_ns, values), key=lambda item: item[0])
        self._ts = [int(ts) for ts, _ in pairs]
        self._vals = [val for _, val in pairs]

    def __bool__(self) -> bool:
        return bool(self._ts)

    def at(self, query_ns: int, max_gap_ns: int | None = None) -> float:
        if not self._ts:
            return NAN
        idx = bisect.bisect_left(self._ts, query_ns)
        candidates = []
        if idx < len(self._ts):
            candidates.append(idx)
        if idx > 0:
            candidates.append(idx - 1)
        best = min(candidates, key=lambda i: abs(self._ts[i] - query_ns))
        if max_gap_ns is not None and abs(self._ts[best] - query_ns) > max_gap_ns:
            return NAN
        return self._vals[best]


def _rmse(values: list[float]) -> float:
    finite = [v for v in values if math.isfinite(v)]
    if not finite:
        return NAN
    return math.sqrt(sum(v * v for v in finite) / len(finite))


def _mean(values: list[float]) -> float:
    finite = [v for v in values if math.isfinite(v)]
    return sum(finite) / len(finite) if finite else NAN


def _max_abs(values: list[float]) -> float:
    finite = [abs(v) for v in values if math.isfinite(v)]
    return max(finite) if finite else NAN


def _percentile(values: list[float], pct: float) -> float:
    finite = sorted(v for v in values if math.isfinite(v))
    if not finite:
        return NAN
    if len(finite) == 1:
        return finite[0]
    rank = pct / 100.0 * (len(finite) - 1)
    lo = math.floor(rank)
    hi = math.ceil(rank)
    if lo == hi:
        return finite[lo]
    return finite[lo] + (finite[hi] - finite[lo]) * (rank - lo)


# ---------------------------------------------------------------------------
# Single-pass bag reader
# ---------------------------------------------------------------------------
class RunRecords:
    def __init__(self) -> None:
        self.truth: list[tuple[int, float, float, float, float]] = []  # ts,x,y,z,yaw
        self.estimate: list[tuple[int, float, float, float, float]] = []
        self.covariance: list[tuple[int, list[float]]] = []
        self.lateral_error: list[tuple[int, float]] = []
        self.depth_error: list[tuple[int, float]] = []
        self.mpc_cmd: list[tuple[int, dict[str, Any]]] = []
        self.solve_time: list[tuple[int, float]] = []
        self.solve_status: list[tuple[int, str]] = []
        self.setpoint: list[tuple[int, dict[str, Any]]] = []
        self.bt_status: list[tuple[int, str]] = []
        self.sensor_status: list[tuple[int, dict[str, Any]]] = []
        self.diagnostics: list[tuple[int, dict[str, Any]]] = []
        self.observed_topics: set[str] = set()


def read_records(chunks: Sequence[Path], truth_topics: Sequence[str], verbose: bool) -> RunRecords:
    rec = RunRecords()
    truth_priority = {topic: rank for rank, topic in enumerate(truth_topics)}
    truth_by_topic: dict[str, list[tuple[int, float, float, float, float]]] = {t: [] for t in truth_topics}
    topics_to_read = {
        ESTIMATED_TOPIC, COVARIANCE_TOPIC, LATERAL_ERROR_TOPIC, DEPTH_ERROR_TOPIC,
        MPC_CMD_TOPIC, CONTROLLER_DEBUG_TOPIC, SETPOINT_TOPIC, BT_STATUS_TOPIC,
        SENSOR_STATUS_TOPIC, DIAGNOSTICS_TOPIC, *truth_topics,
    }

    for chunk in chunks:
        for decoded in ab.read_ros2_messages(str(chunk), topics=topics_to_read):
            topic = decoded.channel.topic
            msg = decoded.ros_msg
            ts = ab.select_timestamp_ns(decoded)
            rec.observed_topics.add(topic)

            if topic == ESTIMATED_TOPIC:
                x, y, z = ab.extract_xyz_from_message(msg)
                rec.estimate.append((ts, x, y, z, _extract_yaw(msg)))
            elif topic in truth_by_topic:
                x, y, z = ab.extract_xyz_from_message(msg)
                truth_by_topic[topic].append((ts, x, y, z, _extract_yaw(msg)))
            elif topic == COVARIANCE_TOPIC:
                data = [float(v) for v in getattr(msg, "data", [])]
                rec.covariance.append((ts, data))
            elif topic == LATERAL_ERROR_TOPIC:
                rec.lateral_error.append((ts, float(getattr(msg, "data", NAN))))
            elif topic == DEPTH_ERROR_TOPIC:
                rec.depth_error.append((ts, float(getattr(msg, "data", NAN))))
            elif topic == MPC_CMD_TOPIC:
                rec.mpc_cmd.append((ts, {
                    "source": str(getattr(msg, "source", "")),
                    "valid": bool(getattr(msg, "valid", False)),
                    "healthy": bool(getattr(msg, "healthy", False)),
                    "right_fin_deg": float(getattr(msg, "right_fin_deg", NAN)),
                    "top_fin_deg": float(getattr(msg, "top_fin_deg", NAN)),
                    "left_fin_deg": float(getattr(msg, "left_fin_deg", NAN)),
                    "bottom_fin_deg": float(getattr(msg, "bottom_fin_deg", NAN)),
                    "thrust_percent": float(getattr(msg, "thrust_percent", NAN)),
                    "target_depth_m": float(getattr(msg, "target_depth_m", NAN)),
                    "work_instruction": int(getattr(msg, "work_instruction", 0)),
                }))
            elif topic == CONTROLLER_DEBUG_TOPIC:
                payload = ab.parse_json_payload(str(getattr(msg, "data", "")))
                solve = payload.get("solve_time_ms")
                if solve is not None:
                    try:
                        rec.solve_time.append((ts, float(solve)))
                    except (TypeError, ValueError):
                        pass
                status = payload.get("solver_status")
                if status:
                    rec.solve_status.append((ts, str(status)))
            elif topic == SETPOINT_TOPIC:
                rec.setpoint.append((ts, {
                    "mode": str(getattr(msg, "mode", "")),
                    "target_depth_m": float(getattr(msg, "target_depth_m", NAN)),
                    "target_heading_rad": float(getattr(msg, "target_heading_rad", NAN)),
                    "target_speed_mps": float(getattr(msg, "target_speed_mps", NAN)),
                    "track_cable": bool(getattr(msg, "track_cable", False)),
                }))
            elif topic == BT_STATUS_TOPIC:
                rec.bt_status.append((ts, ab.parse_bt_markdown(str(getattr(msg, "data", "")))))
            elif topic == SENSOR_STATUS_TOPIC:
                rec.sensor_status.append((ts, {
                    "confidence": float(getattr(msg, "confidence", NAN)),
                    "leak_level": int(getattr(msg, "leak_level", 0)),
                    "battery_low": bool(getattr(msg, "battery_low", False)),
                    "total_voltage_v": float(getattr(msg, "total_voltage_v", NAN)),
                    "anomaly_detected": bool(getattr(msg, "anomaly_detected", False)),
                    "depth_m": float(getattr(msg, "depth_m", NAN)),
                    "speed_mps": float(getattr(msg, "speed_mps", NAN)),
                    "seabed_depth_m": float(getattr(msg, "seabed_depth_m", NAN)),
                    "seabed_clearance_m": float(getattr(msg, "seabed_clearance_m", NAN)),
                }))
            elif topic == DIAGNOSTICS_TOPIC:
                rec.diagnostics.append((ts, {
                    "mode": str(getattr(msg, "mode", "")),
                    "current_behavior": str(getattr(msg, "current_behavior", "")),
                    "anomaly_detected": bool(getattr(msg, "anomaly_detected", False)),
                    "battery_low": bool(getattr(msg, "battery_low", False)),
                    "seabed_penetration_warning": bool(getattr(msg, "seabed_penetration_warning", False)),
                    "seabed_proximity_warning": bool(getattr(msg, "seabed_proximity_warning", False)),
                    "high_priority": bool(getattr(msg, "high_priority", False)),
                }))

    # Pick the single highest-priority truth source that actually carried samples.
    for topic in sorted(truth_by_topic, key=lambda t: truth_priority.get(t, 1_000_000)):
        samples = truth_by_topic[topic]
        if samples:
            rec.truth = sorted(samples, key=lambda item: item[0])
            break

    for attr in ("estimate", "covariance", "lateral_error", "depth_error", "mpc_cmd",
                 "solve_time", "solve_status", "setpoint", "bt_status",
                 "sensor_status", "diagnostics"):
        getattr(rec, attr).sort(key=lambda item: item[0])

    if verbose:
        print(f"[export] truth={len(rec.truth)} est={len(rec.estimate)} "
              f"cov={len(rec.covariance)} lat_err={len(rec.lateral_error)} "
              f"mpc={len(rec.mpc_cmd)} solve={len(rec.solve_time)} "
              f"bt={len(rec.bt_status)} sensor={len(rec.sensor_status)}")
    return rec


# ---------------------------------------------------------------------------
# Table builders
# ---------------------------------------------------------------------------
def _t0_ns(rec: RunRecords) -> int:
    candidates = [seq[0][0] for seq in (
        rec.estimate, rec.truth, rec.covariance, rec.sensor_status,
        rec.mpc_cmd, rec.bt_status,
    ) if seq]
    return min(candidates) if candidates else 0


def build_trajectory(rec: RunRecords, t0: int) -> tuple[list[str], list[dict[str, Any]], dict[str, float]]:
    truth_x = NearestLookup([ts for ts, *_ in rec.truth], [x for _, x, _y, _z, _yaw in rec.truth])
    truth_y = NearestLookup([ts for ts, *_ in rec.truth], [y for _, _x, y, _z, _yaw in rec.truth])
    truth_z = NearestLookup([ts for ts, *_ in rec.truth], [z for _, _x, _y, z, _yaw in rec.truth])
    truth_yaw = NearestLookup([ts for ts, *_ in rec.truth], [yaw for _, _x, _y, _z, yaw in rec.truth])
    lat_err = NearestLookup([ts for ts, _ in rec.lateral_error], [v for _, v in rec.lateral_error])
    dep_err = NearestLookup([ts for ts, _ in rec.depth_error], [v for _, v in rec.depth_error])
    gap = 500_000_000  # 0.5 s association gate

    fields = ["t_s", "est_x", "est_y", "est_z", "est_yaw_rad",
              "truth_x", "truth_y", "truth_z", "truth_yaw_rad",
              "cross_track_error_m", "depth_error_m"]
    rows: list[dict[str, Any]] = []
    lat_series: list[float] = []
    dep_series: list[float] = []
    for ts, x, y, z, yaw in rec.estimate:
        lat = lat_err.at(ts, gap) if lat_err else NAN
        dep = dep_err.at(ts, gap) if dep_err else NAN
        lat_series.append(lat)
        dep_series.append(dep)
        rows.append({
            "t_s": (ts - t0) * 1e-9,
            "est_x": x, "est_y": y, "est_z": z, "est_yaw_rad": yaw,
            "truth_x": truth_x.at(ts, gap) if truth_x else None,
            "truth_y": truth_y.at(ts, gap) if truth_y else None,
            "truth_z": truth_z.at(ts, gap) if truth_z else None,
            "truth_yaw_rad": truth_yaw.at(ts, gap) if truth_yaw else None,
            "cross_track_error_m": lat if lat_err else None,
            "depth_error_m": dep if dep_err else None,
        })
    summary = {
        "cross_track_error_mean_m": _mean(lat_series),
        "cross_track_error_rmse_m": _rmse(lat_series),
        "cross_track_error_max_m": _max_abs(lat_series),
        "depth_error_mean_m": _mean(dep_series),
        "depth_error_rmse_m": _rmse(dep_series),
        "depth_error_max_m": _max_abs(dep_series),
    }
    return fields, rows, summary


def _cov_traces(data: list[float]) -> tuple[float, float, float]:
    """Recover diag(P) trace fragments from a flattened square covariance matrix."""
    n = len(data)
    dim = int(round(math.sqrt(n)))
    if dim * dim != n or dim < 3:
        return NAN, NAN, NAN
    diag = [data[i * dim + i] for i in range(dim)]
    p_xy = diag[0] + diag[1]
    p_z = diag[2]
    return p_xy, p_z, sum(diag)


def build_estimator(rec: RunRecords, t0: int) -> tuple[list[str], list[dict[str, Any]]]:
    est_x = NearestLookup([ts for ts, *_ in rec.estimate], [x for _, x, _y, _z, _yaw in rec.estimate])
    est_y = NearestLookup([ts for ts, *_ in rec.estimate], [y for _, _x, y, _z, _yaw in rec.estimate])
    est_z = NearestLookup([ts for ts, *_ in rec.estimate], [z for _, _x, _y, z, _yaw in rec.estimate])
    gap = 500_000_000
    fields = ["t_s", "cov_trace_xy", "cov_trace_z", "cov_trace_total",
              "est_x", "est_y", "est_z", "nis", "nees"]
    rows: list[dict[str, Any]] = []
    for ts, data in rec.covariance:
        p_xy, p_z, p_tot = _cov_traces(data)
        rows.append({
            "t_s": (ts - t0) * 1e-9,
            "cov_trace_xy": p_xy, "cov_trace_z": p_z, "cov_trace_total": p_tot,
            "est_x": est_x.at(ts, gap) if est_x else None,
            "est_y": est_y.at(ts, gap) if est_y else None,
            "est_z": est_z.at(ts, gap) if est_z else None,
            # NIS/NEES require an event-level replay (uncertainty_metrics.py) or a
            # truth-aligned error covariance; both are out of scope for this raw
            # exporter and are filled by group-B tooling / P1.
            "nis": NOT_OBSERVED,
            "nees": NOT_OBSERVED,
        })
    return fields, rows


def build_controller(rec: RunRecords, t0: int) -> tuple[list[str], list[dict[str, Any]], dict[str, float]]:
    solve = NearestLookup([ts for ts, _ in rec.solve_time], [v for _, v in rec.solve_time])
    status_lookup = {ts: s for ts, s in rec.solve_status}
    status_ts = sorted(status_lookup)
    gap = 500_000_000
    fields = ["t_s", "source", "valid", "healthy", "right_fin_deg", "top_fin_deg",
              "left_fin_deg", "bottom_fin_deg", "thrust_percent", "target_depth_m",
              "work_instruction", "solve_time_ms", "solver_status"]
    rows: list[dict[str, Any]] = []
    for ts, cmd in rec.mpc_cmd:
        s_val = solve.at(ts, gap) if solve else NAN
        solver_status = NOT_OBSERVED
        if status_ts:
            idx = bisect.bisect_right(status_ts, ts) - 1
            if idx >= 0:
                solver_status = status_lookup[status_ts[idx]]
        rows.append({
            "t_s": (ts - t0) * 1e-9,
            **cmd,
            "solve_time_ms": s_val if solve else None,
            "solver_status": solver_status,
        })
    all_solve = [v for _, v in rec.solve_time]
    summary = {
        "solve_time_ms_p50": _percentile(all_solve, 50),
        "solve_time_ms_p95": _percentile(all_solve, 95),
        "solve_time_ms_max": _max_abs(all_solve),
        "mpc_cmd_count": len(rec.mpc_cmd),
    }
    return fields, rows, summary


def build_behavior_tree(rec: RunRecords, t0: int) -> tuple[list[str], list[dict[str, Any]], dict[str, float]]:
    conf = NearestLookup([ts for ts, _ in rec.sensor_status],
                         [d["confidence"] for _, d in rec.sensor_status])
    gap = 1_000_000_000
    fields = ["t_s", "state", "previous_state", "trigger", "confidence",
              "fault_type", "recovery_mode"]
    rows: list[dict[str, Any]] = []
    previous = ""
    switches = 0
    for ts, state in rec.bt_status:
        changed = bool(previous) and state != previous
        if changed:
            switches += 1
        rows.append({
            "t_s": (ts - t0) * 1e-9,
            "state": state,
            "previous_state": previous or NOT_OBSERVED,
            # trigger/fault_type/recovery_mode are not carried on /auv/bt_status
            # (markdown status only). Group-D fault injection tooling writes these
            # explicitly; here they stay honest sentinels.
            "trigger": "state_change" if changed else "steady",
            "confidence": conf.at(ts, gap) if conf else None,
            "fault_type": NOT_OBSERVED,
            "recovery_mode": NOT_OBSERVED,
        })
        previous = state
    summary = {"bt_switch_count": switches, "bt_sample_count": len(rec.bt_status)}
    return fields, rows, summary


def build_sensor_status(rec: RunRecords, t0: int) -> tuple[list[str], list[dict[str, Any]]]:
    fields = ["t_s", "confidence", "leak_level", "battery_low", "total_voltage_v",
              "anomaly_detected", "depth_m", "speed_mps", "seabed_depth_m",
              "seabed_clearance_m"]
    rows = [{"t_s": (ts - t0) * 1e-9, **d} for ts, d in rec.sensor_status]
    return fields, rows


def build_events(rec: RunRecords, t0: int) -> tuple[list[str], list[dict[str, Any]]]:
    """Derive discrete events: BT transitions + first-onset warnings."""
    fields = ["t_s", "event_type", "detail"]
    rows: list[dict[str, Any]] = []

    previous = ""
    for ts, state in rec.bt_status:
        if previous and state != previous:
            rows.append({"t_s": (ts - t0) * 1e-9, "event_type": "bt_transition",
                         "detail": f"{previous}->{state}"})
        previous = state

    # First-onset boolean warnings from sensor status / diagnostics.
    onset_flags = {
        "battery_low": False,
        "anomaly_detected": False,
        "seabed_penetration_warning": False,
        "seabed_proximity_warning": False,
    }
    combined: list[tuple[int, dict[str, Any]]] = (
        [(ts, d) for ts, d in rec.sensor_status] + [(ts, d) for ts, d in rec.diagnostics]
    )
    combined.sort(key=lambda item: item[0])
    for ts, payload in combined:
        for flag in onset_flags:
            if not onset_flags[flag] and bool(payload.get(flag, False)):
                onset_flags[flag] = True
                rows.append({"t_s": (ts - t0) * 1e-9, "event_type": f"{flag}_onset",
                             "detail": "first_true"})

    rows.sort(key=lambda r: (r["t_s"] if isinstance(r["t_s"], (int, float)) else 0.0))
    return fields, rows


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------
def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input", type=Path, required=True,
                        help="录制的 .mcap 文件或 rosbag 目录")
    parser.add_argument("--output-dir", type=Path, required=True,
                        help="派生表输出目录（建议 results/<exp>/<run>/tables）")
    parser.add_argument("--run-id", default=None,
                        help="运行标识（缺省用输入路径推断）")
    parser.add_argument("--truth-topic", default=TRUTH_TOPIC)
    parser.add_argument("--truth-fallbacks", default=",".join(TRUTH_FALLBACKS))
    parser.add_argument("--quiet", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    ab.ensure_runtime_dependencies()

    chunks = ab.resolve_input_chunks(args.input)
    truth_topics = ab.candidate_truth_topics(args.truth_topic, args.truth_fallbacks)
    verbose = not args.quiet

    rec = read_records(chunks, truth_topics, verbose)
    t0 = _t0_ns(rec)
    run_id = args.run_id or args.input.resolve().parent.name

    out = args.output_dir
    out.mkdir(parents=True, exist_ok=True)

    traj_fields, traj_rows, traj_summary = build_trajectory(rec, t0)
    est_fields, est_rows = build_estimator(rec, t0)
    ctrl_fields, ctrl_rows, ctrl_summary = build_controller(rec, t0)
    bt_fields, bt_rows, bt_summary = build_behavior_tree(rec, t0)
    sensor_fields, sensor_rows = build_sensor_status(rec, t0)
    event_fields, event_rows = build_events(rec, t0)

    _write_csv(out / "trajectory.csv", traj_fields, traj_rows)
    _write_csv(out / "estimator.csv", est_fields, est_rows)
    _write_csv(out / "controller.csv", ctrl_fields, ctrl_rows)
    _write_csv(out / "behavior_tree.csv", bt_fields, bt_rows)
    _write_csv(out / "sensor_status.csv", sensor_fields, sensor_rows)
    _write_csv(out / "events.csv", event_fields, event_rows)

    duration_s = NAN
    if rec.estimate and len(rec.estimate) >= 2:
        duration_s = (rec.estimate[-1][0] - rec.estimate[0][0]) * 1e-9

    expected_topics = {
        TRUTH_TOPIC, ESTIMATED_TOPIC, COVARIANCE_TOPIC, LATERAL_ERROR_TOPIC,
        DEPTH_ERROR_TOPIC, MPC_CMD_TOPIC, CONTROLLER_DEBUG_TOPIC, SETPOINT_TOPIC,
        BT_STATUS_TOPIC, SENSOR_STATUS_TOPIC, DIAGNOSTICS_TOPIC, *truth_topics,
    }
    missing = sorted(expected_topics - rec.observed_topics)

    metrics = {
        "schema_version": 1,
        "run_id": run_id,
        "source_input": str(args.input),
        "source_chunks": [str(c) for c in chunks],
        "duration_s": None if math.isnan(duration_s) else round(duration_s, 3),
        "sample_counts": {
            "trajectory": len(traj_rows),
            "estimator": len(est_rows),
            "controller": len(ctrl_rows),
            "behavior_tree": len(bt_rows),
            "sensor_status": len(sensor_rows),
            "events": len(event_rows),
            "truth": len(rec.truth),
        },
        "trajectory_metrics": {k: (None if isinstance(v, float) and math.isnan(v) else v)
                               for k, v in traj_summary.items()},
        "controller_metrics": {k: (None if isinstance(v, float) and math.isnan(v) else v)
                               for k, v in ctrl_summary.items()},
        "behavior_tree_metrics": bt_summary,
        "observed_topics": sorted(rec.observed_topics),
        "missing_topics": missing,
        "not_observed_fields": ["estimator.nis", "estimator.nees",
                                "behavior_tree.fault_type", "behavior_tree.recovery_mode"],
        "notes": "Read-only derived export; NIS/NEES and BT fault_type/recovery_mode "
                 "come from group-B/D tooling. Missing topics reflect the recorded bag, "
                 "not fabricated columns.",
    }
    (out / "metrics.json").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if verbose:
        print(f"[export] wrote 6 tables + metrics.json -> {out}")
        if missing:
            print(f"[export] missing topics (recorded bag lacks them): {missing}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

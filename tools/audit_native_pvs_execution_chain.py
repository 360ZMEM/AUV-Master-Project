#!/usr/bin/env python3
"""Audit native PVS depthHeadingAutopilot execution-chain evidence.

This tool is intentionally conservative.  It verifies that a PVS/protocol_udp
run was configured for the native PVS autopilot path, then inspects logs and
MCAP topics for the command/telemetry chain:

ROS setpoint/controller -> protocol_udp downlink -> Mock AMD AUTO dispatch ->
PVSSimWrapper.depthHeadingAutopilot -> PVS state/uplink -> ROS bag.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

AUTONOMY_MOTION_PROXY_MODES = {"kinematic_setpoint", "kinematic", "lightweight"}

SETPOINT_TOPIC = "/auv/control/setpoint"
DEBUG_TOPIC = "/auv/controller/debug"
ARB_STATUS_TOPIC = "/auv/arbiter/status"
MPC_CMD_TOPIC = "/auv/control/mpc_cmd"
CMD_VEL_TOPIC = "/cmd_vel"
GROUND_TRUTH_TOPIC = "/auv/sensors/ground_truth"
FILTERED_STATE_TOPIC = "/auv/state/filtered"
RAW_DR_TOPIC = "/auv/state/raw_dr"
DEPTH_TOPIC = "/auv/sensors/depth"
DVL_TOPIC = "/auv/sensors/dvl"
IMU_TOPIC = "/auv/sensors/imu"

TOPICS_OF_INTEREST = {
    SETPOINT_TOPIC,
    DEBUG_TOPIC,
    ARB_STATUS_TOPIC,
    MPC_CMD_TOPIC,
    CMD_VEL_TOPIC,
    GROUND_TRUTH_TOPIC,
    FILTERED_STATE_TOPIC,
    RAW_DR_TOPIC,
    DEPTH_TOPIC,
    DVL_TOPIC,
    IMU_TOPIC,
}


def finite(value: Any, default: float = float("nan")) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    return result if math.isfinite(result) else default


def span(values: Iterable[float]) -> float:
    filtered = [float(v) for v in values if math.isfinite(float(v))]
    if not filtered:
        return float("nan")
    return max(filtered) - min(filtered)


def percentile(values: list[float], pct: float) -> float:
    filtered = sorted(v for v in values if math.isfinite(v))
    if not filtered:
        return float("nan")
    index = int(round((pct / 100.0) * (len(filtered) - 1)))
    index = max(0, min(len(filtered) - 1, index))
    return float(filtered[index])


def json_safe(value: Any) -> Any:
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [json_safe(v) for v in value]
    return value


def load_yaml(path: Path) -> dict[str, Any]:
    try:
        import yaml
    except ImportError as exc:
        raise SystemExit("PyYAML is required for native PVS config audit") from exc
    with path.open("r", encoding="utf-8") as handle:
        loaded = yaml.safe_load(handle) or {}
    if not isinstance(loaded, dict):
        raise SystemExit(f"config root must be a mapping: {path}")
    return loaded


def find_mcaps(path: Path | None) -> list[Path]:
    if path is None:
        return []
    if path.is_file() and path.suffix == ".mcap":
        return [path]
    if path.is_dir():
        return sorted(path.glob("**/*.mcap"))
    return []


def find_default_mcaps(run_dir: Path | None) -> list[Path]:
    if run_dir is None:
        return []
    return find_mcaps(run_dir / "rosbag")


def load_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def parse_logs(run_dir: Path | None) -> dict[str, Any]:
    if run_dir is None or not run_dir.exists():
        return {
            "log_files": [],
            "auto_mode_log_count": 0,
            "manual_mode_log_count": 0,
            "native_autopilot_open_log_count": 0,
            "kinematic_log_count": 0,
            "autonomy_guard_rejection_count": 0,
            "protocol_control_mode_counts": {},
        }

    log_files = sorted(path for path in run_dir.glob("**/*.log") if path.is_file())
    text = "\n".join(load_text(path) for path in log_files)
    mode_counts = Counter(re.findall(r"Control Mode Byte:\s*(0x[0-9A-Fa-f]{2})", text))
    mode_counts.update(re.findall(r"control_mode_byte[=:]\s*(\d+)", text))
    return {
        "log_files": [str(path) for path in log_files],
        "auto_mode_log_count": len(re.findall(r"\b[Mm]ode[:=]\s*AUTO\b", text)),
        "manual_mode_log_count": len(re.findall(r"\b[Mm]ode[:=]\s*MANUAL\b", text)),
        "native_autopilot_open_log_count": text.count("mode=depthHeadingAutopilot"),
        "kinematic_log_count": text.count("kinematic_setpoint") + text.count("_step_kinematic"),
        "autonomy_guard_rejection_count": text.count("Autonomy guard rejected"),
        "protocol_control_mode_counts": dict(sorted(mode_counts.items())),
    }


def raw_mcap_topic_stats(mcaps: list[Path]) -> tuple[list[dict[str, Any]], str | None]:
    try:
        from mcap.reader import make_reader
    except ImportError:
        return [], "mcap package is not installed"

    counts: Counter[str] = Counter()
    periods: dict[str, list[float]] = defaultdict(list)
    last_time: dict[str, int] = {}
    first_seen: dict[str, int] = {}
    last_seen: dict[str, int] = {}

    try:
        for mcap_path in mcaps:
            with mcap_path.open("rb") as handle:
                reader = make_reader(handle)
                for _, channel, message in reader.iter_messages():
                    topic = channel.topic
                    if topic not in TOPICS_OF_INTEREST:
                        continue
                    t_ns = int(message.log_time)
                    counts[topic] += 1
                    first_seen.setdefault(topic, t_ns)
                    last_seen[topic] = t_ns
                    previous = last_time.get(topic)
                    if previous is not None:
                        dt_ms = (t_ns - previous) / 1.0e6
                        if 0.0 < dt_ms < 10000.0:
                            periods[topic].append(dt_ms)
                    last_time[topic] = t_ns
    except Exception as exc:  # noqa: BLE001
        return [], f"raw MCAP topic scan failed: {exc}"

    rows: list[dict[str, Any]] = []
    for topic in sorted(TOPICS_OF_INTEREST):
        n = int(counts.get(topic, 0))
        duration_s = (
            (last_seen[topic] - first_seen[topic]) / 1.0e9
            if topic in first_seen and topic in last_seen and last_seen[topic] > first_seen[topic]
            else 0.0
        )
        values = periods.get(topic, [])
        rows.append(
            {
                "topic": topic,
                "msg_count": n,
                "duration_s": duration_s,
                "rate_hz": n / duration_s if duration_s > 0.0 else 0.0,
                "period_ms_median": statistics.median(values) if values else float("nan"),
                "period_ms_p95": percentile(values, 95.0),
                "period_ms_p99": percentile(values, 99.0),
                "period_ms_max": max(values) if values else float("nan"),
            }
        )
    return rows, None


def select_timestamp_ns(decoded: Any) -> int:
    for name in ("log_time_ns", "publish_time_ns"):
        value = getattr(decoded, name, None)
        if value is not None:
            return int(value)
    message = getattr(decoded, "message", None)
    if message is not None:
        for name in ("log_time", "publish_time"):
            value = getattr(message, name, None)
            if value is not None:
                return int(value)
    return 0


def parse_json_payload(raw: str) -> dict[str, Any]:
    try:
        loaded = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def quaternion_to_yaw_deg(q: Any) -> float:
    x = finite(getattr(q, "x", 0.0), 0.0)
    y = finite(getattr(q, "y", 0.0), 0.0)
    z = finite(getattr(q, "z", 0.0), 0.0)
    w = finite(getattr(q, "w", 1.0), 1.0)
    siny_cosp = 2.0 * (w * z + x * y)
    cosy_cosp = 1.0 - 2.0 * (y * y + z * z)
    return math.degrees(math.atan2(siny_cosp, cosy_cosp))


def extract_pose(msg: Any) -> tuple[float, float, float, float]:
    pose = getattr(msg, "pose", None)
    if pose is not None and hasattr(pose, "pose"):
        pose = pose.pose
    if pose is None:
        return (float("nan"), float("nan"), float("nan"), float("nan"))
    position = getattr(pose, "position", None)
    orientation = getattr(pose, "orientation", None)
    if position is None:
        return (float("nan"), float("nan"), float("nan"), float("nan"))
    return (
        finite(getattr(position, "x", float("nan"))),
        finite(getattr(position, "y", float("nan"))),
        finite(getattr(position, "z", float("nan"))),
        quaternion_to_yaw_deg(orientation) if orientation is not None else float("nan"),
    )


def ros2_series(mcaps: list[Path]) -> tuple[dict[str, Any], list[dict[str, Any]], str | None]:
    try:
        from mcap_ros2.reader import read_ros2_messages
    except ImportError:
        return {}, [], "mcap_ros2_support is not installed"

    setpoints: list[dict[str, Any]] = []
    debug_rows: list[dict[str, Any]] = []
    state_by_topic: dict[str, list[dict[str, Any]]] = defaultdict(list)
    arbiter_modes: list[int] = []
    mpc_cmd_count = 0
    cmd_vel_count = 0

    try:
        for mcap_path in mcaps:
            for decoded in read_ros2_messages(str(mcap_path), topics=TOPICS_OF_INTEREST):
                topic = decoded.channel.topic
                msg = decoded.ros_msg
                t_ns = select_timestamp_ns(decoded)
                t_s = t_ns / 1.0e9

                if topic == SETPOINT_TOPIC:
                    setpoints.append(
                        {
                            "t_s": t_s,
                            "control_mode_byte": int(getattr(msg, "control_mode_byte", 0)),
                            "target_depth_m": finite(getattr(msg, "target_depth_m", float("nan"))),
                            "target_heading_deg": math.degrees(
                                finite(getattr(msg, "target_heading_rad", float("nan")))
                            ),
                            "target_speed_mps": finite(getattr(msg, "target_speed_mps", float("nan"))),
                            "high_priority": bool(getattr(msg, "high_priority", False)),
                            "mode": str(getattr(msg, "mode", "")),
                        }
                    )
                elif topic == DEBUG_TOPIC:
                    payload = parse_json_payload(str(getattr(msg, "data", "")))
                    debug_rows.append(
                        {
                            "t_s": t_s,
                            "current_depth_m": finite(payload.get("current_depth_m")),
                            "target_depth_m": finite(payload.get("target_depth_m")),
                            "depth_error_m": finite(payload.get("depth_error_m")),
                            "current_yaw_deg": finite(payload.get("current_yaw_deg")),
                            "target_yaw_deg": finite(payload.get("target_yaw_deg")),
                            "yaw_error_deg": finite(payload.get("yaw_error_deg")),
                            "current_speed_mps": finite(payload.get("current_speed_mps")),
                            "target_speed_mps": finite(payload.get("target_speed_mps")),
                            "requested_target_speed_mps": finite(
                                payload.get("requested_target_speed_mps")
                            ),
                            "applied_target_speed_mps": finite(payload.get("applied_target_speed_mps")),
                            "solver_status": str(payload.get("solver_status", "")),
                            "solver_wall_time_current_ms": finite(
                                payload.get("solver_wall_time_current_ms")
                            ),
                            "control_mode_byte": int(finite(payload.get("control_mode_byte"), 0.0)),
                        }
                    )
                elif topic in {GROUND_TRUTH_TOPIC, FILTERED_STATE_TOPIC, RAW_DR_TOPIC}:
                    x, y, z, yaw_deg = extract_pose(msg)
                    state_by_topic[topic].append(
                        {
                            "t_s": t_s,
                            "x_m": x,
                            "y_m": y,
                            "z_m": z,
                            "yaw_deg": yaw_deg,
                        }
                    )
                elif topic == ARB_STATUS_TOPIC:
                    arbiter_modes.append(int(getattr(msg, "effective_control_mode_byte", 0)))
                elif topic == MPC_CMD_TOPIC:
                    mpc_cmd_count += 1
                elif topic == CMD_VEL_TOPIC:
                    cmd_vel_count += 1
    except Exception as exc:  # noqa: BLE001
        return {}, [], f"ROS2 MCAP decode failed: {exc}"

    debug_wall_times = [row["solver_wall_time_current_ms"] for row in debug_rows]
    summary = {
        "setpoint_count": len(setpoints),
        "setpoint_control_mode_counts": dict(
            sorted(Counter(row["control_mode_byte"] for row in setpoints).items())
        ),
        "setpoint_target_depth_span_m": span(row["target_depth_m"] for row in setpoints),
        "setpoint_target_heading_span_deg": span(row["target_heading_deg"] for row in setpoints),
        "setpoint_target_speed_span_mps": span(row["target_speed_mps"] for row in setpoints),
        "debug_count": len(debug_rows),
        "debug_current_depth_span_m": span(row["current_depth_m"] for row in debug_rows),
        "debug_current_yaw_span_deg": span(row["current_yaw_deg"] for row in debug_rows),
        "debug_current_speed_span_mps": span(row["current_speed_mps"] for row in debug_rows),
        "debug_solver_wall_time_p95_ms": percentile(debug_wall_times, 95.0),
        "debug_solver_wall_time_max_ms": (
            max(v for v in debug_wall_times if math.isfinite(v))
            if any(math.isfinite(v) for v in debug_wall_times)
            else float("nan")
        ),
        "debug_solver_status_counts": dict(
            sorted(Counter(row["solver_status"] for row in debug_rows).items())
        ),
        "arbiter_effective_control_mode_counts": dict(sorted(Counter(arbiter_modes).items())),
        "mpc_cmd_count": mpc_cmd_count,
        "cmd_vel_count": cmd_vel_count,
        "state_topics": {},
    }
    for topic, rows in sorted(state_by_topic.items()):
        summary["state_topics"][topic] = {
            "sample_count": len(rows),
            "x_span_m": span(row["x_m"] for row in rows),
            "y_span_m": span(row["y_m"] for row in rows),
            "z_span_m": span(row["z_m"] for row in rows),
            "yaw_span_deg": span(row["yaw_deg"] for row in rows),
        }
    return summary, debug_rows, None


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames = list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(json_safe(row))


def determine_status(
    *,
    config_summary: dict[str, Any],
    log_summary: dict[str, Any],
    mcap_count: int,
    topic_rows: list[dict[str, Any]],
    ros_summary: dict[str, Any],
    errors: list[str],
) -> tuple[str, list[str]]:
    failed: list[str] = []
    warnings: list[str] = []

    if errors:
        warnings.extend(errors)
    if not config_summary.get("bridge_backend_is_protocol_udp", False):
        failed.append("bridge backend is not protocol_udp")
    if not config_summary.get("pvs_control_mode_is_native_autopilot", False):
        failed.append("pvs.control_mode is not depthHeadingAutopilot")
    if config_summary.get("pvs_uses_kinematic_proxy", False):
        failed.append("pvs.autonomy_motion_model uses a kinematic proxy")
    if mcap_count <= 0:
        failed.append("no MCAP file found")

    topic_counts = {row["topic"]: int(row["msg_count"]) for row in topic_rows}
    if mcap_count > 0 and topic_counts.get(SETPOINT_TOPIC, 0) <= 0:
        failed.append("no /auv/control/setpoint samples in MCAP")
    if mcap_count > 0 and topic_counts.get(DEBUG_TOPIC, 0) <= 0:
        warnings.append("no /auv/controller/debug samples in MCAP")
    if mcap_count > 0 and not any(
        topic_counts.get(topic, 0) > 0
        for topic in (GROUND_TRUTH_TOPIC, FILTERED_STATE_TOPIC, RAW_DR_TOPIC)
    ):
        failed.append("no PVS-derived state topic samples in MCAP")

    if (
        log_summary.get("auto_mode_log_count", 0) <= 0
        and not any(
            str(mode) in {"238", "239", "0xEE", "0xEF"}
            and count > 0
            for mode, count in log_summary.get("protocol_control_mode_counts", {}).items()
        )
    ):
        warnings.append("AUTO protocol mode was not observed in launcher logs")

    state_topics = ros_summary.get("state_topics", {}) if ros_summary else {}
    motion_observed = False
    for metrics in state_topics.values():
        if (
            finite(metrics.get("x_span_m"), 0.0) > 0.05
            or finite(metrics.get("y_span_m"), 0.0) > 0.05
            or finite(metrics.get("z_span_m"), 0.0) > 0.05
            or finite(metrics.get("yaw_span_deg"), 0.0) > 0.5
        ):
            motion_observed = True
            break
    if mcap_count > 0 and ros_summary and not motion_observed:
        failed.append("no observable PVS state motion in decoded state topics")

    if failed:
        return "failed", failed + warnings
    if warnings or not ros_summary:
        return "partial", warnings
    return "passed", []


def build_config_summary(config_path: Path) -> dict[str, Any]:
    cfg = load_yaml(config_path)
    bridge = cfg.get("bridge", {}) if isinstance(cfg.get("bridge"), dict) else {}
    pvs = cfg.get("pvs", {}) if isinstance(cfg.get("pvs"), dict) else {}
    control_mode = str(pvs.get("control_mode", "")).strip()
    motion_model = str(pvs.get("autonomy_motion_model", "native")).strip()
    return {
        "config_path": str(config_path),
        "stage_name": str((cfg.get("stage") or {}).get("name", "")),
        "simulation_backend": str((cfg.get("simulation") or {}).get("backend", "")),
        "bridge_backend": str(bridge.get("backend", "")),
        "bridge_backend_is_protocol_udp": str(bridge.get("backend", "")).strip() == "protocol_udp",
        "pvs_control_mode": control_mode,
        "pvs_control_mode_is_native_autopilot": control_mode.lower()
        in {"depthheadingautopilot", "depth_heading_autopilot", "autopilot", "reference"},
        "pvs_autonomy_motion_model": motion_model,
        "pvs_uses_kinematic_proxy": motion_model.lower() in AUTONOMY_MOTION_PROXY_MODES,
        "pvs_current_speed_mps": finite(pvs.get("current_speed_mps")),
        "pvs_reference_rpm_min": finite(pvs.get("reference_rpm_min")),
    }


def render_report(summary: dict[str, Any]) -> str:
    lines = [
        "# Native PVS Execution-Chain Audit",
        "",
        f"- Status: `{summary['status']}`",
        f"- MCAP files: `{summary['mcap_count']}`",
        f"- Config: `{summary['config']['config_path']}`",
        f"- PVS mode: `{summary['config']['pvs_control_mode']}`; "
        f"autonomy motion model: `{summary['config']['pvs_autonomy_motion_model']}`",
        f"- Setpoint samples: `{summary.get('ros2', {}).get('setpoint_count', 0)}`; "
        f"controller debug samples: `{summary.get('ros2', {}).get('debug_count', 0)}`",
        f"- AUTO log count: `{summary['logs'].get('auto_mode_log_count', 0)}`; "
        f"native open log count: `{summary['logs'].get('native_autopilot_open_log_count', 0)}`",
    ]
    reasons = summary.get("status_reasons", [])
    if reasons:
        lines.append("")
        lines.append("## Reasons")
        lines.extend(f"- {reason}" for reason in reasons)
    lines.extend(
        [
            "",
            "Boundary: this audit can only support a native PVS/protocol_udp "
            "simulation execution-chain claim. It is not a PC104/VxWorks physical "
            "latency measurement, sea-trial result, or full R22 native-factor "
            "performance matrix.",
        ]
    )
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, default=None)
    parser.add_argument("--mcap", type=Path, default=None, help="MCAP file or rosbag directory")
    parser.add_argument(
        "--bridge-config",
        type=Path,
        default=Path("config/bridge_params.protocol_udp.pvs.native_autopilot.yaml"),
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config_summary = build_config_summary(args.bridge_config)
    mcaps = find_mcaps(args.mcap) if args.mcap else find_default_mcaps(args.run_dir)

    log_summary = parse_logs(args.run_dir)
    topic_rows, topic_error = raw_mcap_topic_stats(mcaps)
    ros_summary, debug_rows, ros_error = ros2_series(mcaps) if mcaps else ({}, [], None)

    errors = [item for item in (topic_error, ros_error) if item]
    status, reasons = determine_status(
        config_summary=config_summary,
        log_summary=log_summary,
        mcap_count=len(mcaps),
        topic_rows=topic_rows,
        ros_summary=ros_summary,
        errors=errors,
    )

    summary = {
        "status": status,
        "status_reasons": reasons,
        "run_dir": str(args.run_dir) if args.run_dir else None,
        "mcap_files": [str(path) for path in mcaps],
        "mcap_count": len(mcaps),
        "config": config_summary,
        "logs": log_summary,
        "topic_error": topic_error,
        "ros_decode_error": ros_error,
        "ros2": ros_summary,
    }

    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "native_pvs_execution_chain_summary.json").write_text(
        json.dumps(json_safe(summary), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    write_csv(args.output_dir / "topic_rates.csv", topic_rows)
    write_csv(args.output_dir / "setpoint_to_state_tracking.csv", debug_rows)
    (args.output_dir / "report.md").write_text(render_report(summary), encoding="utf-8")

    print(f"[native-pvs-audit] status={status} mcaps={len(mcaps)} out={args.output_dir}")
    if reasons:
        for reason in reasons:
            print(f"[native-pvs-audit] {reason}")
    return 0 if status in {"passed", "partial", "failed"} else 1


if __name__ == "__main__":
    raise SystemExit(main())

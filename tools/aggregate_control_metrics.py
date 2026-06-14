#!/usr/bin/env python3
"""
Aggregate control-side metrics from MCAP bags or thesis sweep results.

The tool is intentionally separate from tools/run_thesis_sweep.py: localization
metrics remain in the original sweep results, while this command builds a
control aggregate table from recorded diagnostics and controller topics.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import subprocess
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from statistics import mean, stdev
from typing import Iterable, Sequence

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(PROJECT_ROOT))

from common.env_utils import get_output_dir
from tools.analyze_bag import resolve_input_chunks


DEFAULT_DEBUG_TOPIC = "/auv/controller/debug"
DEFAULT_MPC_CMD_TOPIC = "/auv/control/mpc_cmd"
DEFAULT_CMD_VEL_TOPIC = "/cmd_vel"
NAN = "nan"


CONTROL_METRIC_COLUMNS = [
    "lateral_error_rmse_m",
    "lateral_error_mean_abs_m",
    "mpc_solve_time_mean_ms",
    "mpc_solve_time_p95_ms",
    "mpc_solve_time_max_ms",
    "fallback_rate",
    "state_source_fallback_rate",
    "control_rate_rms_per_s",
    "control_rate_mean_abs_per_s",
    "control_effort_mean",
    "safety_violation_rate",
    "seabed_clearance_safety_violation_ratio_1p5m",
    "seabed_proximity_ratio",
    "seabed_penetration_ratio",
    "high_priority_ratio",
]


RUN_FIELDNAMES = [
    "scenario",
    "seed",
    "mpc_mode",
    "status",
    "mcap",
    "analysis_dir",
    "control_parse_status",
    "error",
    "diagnostics_available",
    "debug_available",
    "control_topic",
    "control_available",
    "mpc_solve_sample_count",
    "fallback_sample_count",
    "control_sample_count",
    *CONTROL_METRIC_COLUMNS,
]


@dataclass
class ControlTopicMetrics:
    debug_available: bool = False
    control_available: bool = False
    control_topic: str = ""
    solve_times_ms: list[float] = field(default_factory=list)
    fallback_flags: list[bool] = field(default_factory=list)
    state_source_fallback_flags: list[bool] = field(default_factory=list)
    control_timestamps_ns: list[int] = field(default_factory=list)
    control_vectors: list[list[float]] = field(default_factory=list)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Aggregate lateral RMSE, MPC solve time, fallback rate, control variation, and safety rates.",
    )
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument(
        "--sweep-results",
        type=Path,
        help="Path to a run_thesis_sweep.py results.csv file. The mcap column is used as input.",
    )
    input_group.add_argument(
        "--bag",
        type=Path,
        help="Path to a single .mcap file or rosbag2 directory.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Directory for aggregate outputs. Defaults to a timestamped results/control_aggregates directory.",
    )
    parser.add_argument(
        "--analysis-root",
        type=Path,
        default=None,
        help="Directory for per-bag analyze_bag.py statistics. Defaults to <output-dir>/bag_analysis.",
    )
    parser.add_argument(
        "--reuse-analysis",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Reuse existing summary_statistics.csv under the per-run analysis directory when present.",
    )
    parser.add_argument(
        "--skip-analyze-bag",
        action="store_true",
        help="Do not call tools/analyze_bag.py; only consume existing summary_statistics.csv and control topics.",
    )
    parser.add_argument("--topic-debug", default=DEFAULT_DEBUG_TOPIC, help="Controller debug JSON String topic.")
    parser.add_argument("--topic-mpc-cmd", default=DEFAULT_MPC_CMD_TOPIC, help="MpcCmd control topic.")
    parser.add_argument("--topic-cmd-vel", default=DEFAULT_CMD_VEL_TOPIC, help="Twist fallback control topic.")
    parser.add_argument(
        "--merged-results-name",
        default="merged_control_results.csv",
        help="Filename for source sweep rows joined with control metrics.",
    )
    return parser.parse_args()


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv_rows(path: Path, fieldnames: Sequence[str], rows: Sequence[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: format_csv_value(row.get(key, "")) for key in fieldnames})


def format_csv_value(value: object) -> object:
    if value is None:
        return ""
    if isinstance(value, float):
        if math.isnan(value):
            return NAN
        return f"{value:.6g}"
    return value


def to_float(value: object, default: float = float("nan")) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def bool_text(value: bool) -> str:
    return "true" if value else "false"


def safe_stdev(values: Sequence[float]) -> float:
    return stdev(values) if len(values) >= 2 else 0.0


def percentile(values: Sequence[float], q: float) -> float:
    if not values:
        return float("nan")
    return float(np.percentile(np.asarray(values, dtype=float), q))


def make_input_rows(args: argparse.Namespace) -> list[dict[str, str]]:
    if args.sweep_results:
        rows = read_csv_rows(args.sweep_results)
        if not rows:
            raise SystemExit(f"No rows found in sweep results: {args.sweep_results}")
        return rows

    bag = args.bag.resolve()
    return [
        {
            "scenario": "single_bag",
            "seed": "",
            "mpc_mode": "",
            "status": "ok",
            "mcap": str(bag),
            "run_dir": str(bag.parent),
        }
    ]


def analysis_dir_for_row(row: dict[str, str], analysis_root: Path, index: int) -> Path:
    scenario = sanitize_component(row.get("scenario") or "scenario")
    seed = sanitize_component(row.get("seed") or f"row{index}")
    mode = sanitize_component(row.get("mpc_mode") or "mode")
    return analysis_root / f"{scenario}__seed{seed}__{mode}"


def sanitize_component(value: str) -> str:
    clean = "".join(ch if ch.isalnum() or ch in ("-", "_", ".") else "_" for ch in str(value).strip())
    return clean.strip("_") or "item"


def ensure_summary_statistics(
    *,
    bag_path: Path,
    analysis_dir: Path,
    reuse_analysis: bool,
    skip_analyze_bag: bool,
) -> tuple[Path | None, str]:
    summary_path = analysis_dir / "summary_statistics.csv"
    if reuse_analysis and summary_path.exists():
        return summary_path, "reused"
    if skip_analyze_bag:
        return summary_path if summary_path.exists() else None, "missing_skipped"

    analysis_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable,
        str(PROJECT_ROOT / "tools" / "analyze_bag.py"),
        str(bag_path),
        "--output-dir",
        str(analysis_dir),
        "--stats-only",
        "--allow-missing-truth",
    ]
    result = subprocess.run(cmd, cwd=str(PROJECT_ROOT), text=True, capture_output=True)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip().splitlines()
        raise RuntimeError(detail[-1] if detail else f"analyze_bag.py failed for {bag_path}")
    return summary_path if summary_path.exists() else None, "generated"


def read_summary_metrics(summary_path: Path | None) -> dict[str, float]:
    if summary_path is None or not summary_path.exists():
        return {}
    metrics: dict[str, float] = {}
    with summary_path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            metric = row.get("metric", "")
            if metric:
                metrics[metric] = to_float(row.get("value"))
    return metrics


def ensure_mcap_reader():
    try:
        from mcap_ros2.reader import read_ros2_messages
    except ImportError as exc:  # pragma: no cover - dependency guard
        raise SystemExit(
            "mcap and mcap-ros2-support are required. Install them with: "
            "pip install mcap mcap-ros2-support"
        ) from exc
    return read_ros2_messages


def select_timestamp_ns(message_wrapper) -> int:
    publish_time_ns = int(getattr(message_wrapper, "publish_time_ns", 0))
    if publish_time_ns > 0:
        return publish_time_ns
    return int(message_wrapper.log_time_ns)


def parse_control_topics(
    *,
    bag_path: Path,
    debug_topic: str,
    mpc_cmd_topic: str,
    cmd_vel_topic: str,
) -> ControlTopicMetrics:
    read_ros2_messages = ensure_mcap_reader()
    chunks = resolve_input_chunks(bag_path)
    topics = {debug_topic, mpc_cmd_topic, cmd_vel_topic}
    metrics = ControlTopicMetrics()

    mpc_samples: list[tuple[int, list[float]]] = []
    cmd_vel_samples: list[tuple[int, list[float]]] = []

    for chunk in chunks:
        for decoded in read_ros2_messages(str(chunk), topics=topics):
            topic = decoded.channel.topic
            msg = decoded.ros_msg
            timestamp_ns = select_timestamp_ns(decoded)

            if topic == debug_topic:
                metrics.debug_available = True
                payload = parse_debug_payload(str(getattr(msg, "data", "")))
                solve_time = to_float(payload.get("solve_time_ms"))
                if math.isfinite(solve_time):
                    metrics.solve_times_ms.append(solve_time)
                metrics.fallback_flags.append(is_fallback_payload(payload))
                if "state_source_fallback" in payload:
                    metrics.state_source_fallback_flags.append(bool(payload.get("state_source_fallback")))
                continue

            if topic == mpc_cmd_topic:
                vector = [
                    to_float(getattr(msg, "right_fin_deg", float("nan"))),
                    to_float(getattr(msg, "top_fin_deg", float("nan"))),
                    to_float(getattr(msg, "left_fin_deg", float("nan"))),
                    to_float(getattr(msg, "bottom_fin_deg", float("nan"))),
                    to_float(getattr(msg, "thrust_percent", float("nan"))),
                ]
                if all(math.isfinite(value) for value in vector):
                    mpc_samples.append((timestamp_ns, vector))
                continue

            if topic == cmd_vel_topic:
                linear = getattr(msg, "linear", None)
                angular = getattr(msg, "angular", None)
                if linear is None or angular is None:
                    continue
                vector = [
                    to_float(getattr(linear, "x", float("nan"))),
                    to_float(getattr(linear, "z", float("nan"))),
                    to_float(getattr(angular, "x", float("nan"))),
                    to_float(getattr(angular, "y", float("nan"))),
                    to_float(getattr(angular, "z", float("nan"))),
                ]
                if all(math.isfinite(value) for value in vector):
                    cmd_vel_samples.append((timestamp_ns, vector))

    selected_topic = ""
    selected_samples: list[tuple[int, list[float]]] = []
    if mpc_samples:
        selected_topic = mpc_cmd_topic
        selected_samples = mpc_samples
    elif cmd_vel_samples:
        selected_topic = cmd_vel_topic
        selected_samples = cmd_vel_samples

    if selected_samples:
        selected_samples.sort(key=lambda item: item[0])
        metrics.control_available = True
        metrics.control_topic = selected_topic
        metrics.control_timestamps_ns = [item[0] for item in selected_samples]
        metrics.control_vectors = [item[1] for item in selected_samples]

    return metrics


def parse_debug_payload(payload: str) -> dict[str, object]:
    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError:
        return {}
    if isinstance(parsed, dict):
        return parsed
    return {}


def is_fallback_payload(payload: dict[str, object]) -> bool:
    if bool(payload.get("state_source_fallback")):
        return True
    status = str(payload.get("solver_status", "")).upper()
    reason = str(payload.get("fallback_reason", "")).upper()
    note = str(payload.get("note", "")).upper()
    return "FALLBACK" in status or bool(reason) or "FALLBACK" in note


def compute_control_rate_metrics(timestamps_ns: Sequence[int], vectors: Sequence[Sequence[float]]) -> dict[str, float]:
    if len(timestamps_ns) < 2 or len(vectors) < 2:
        return {
            "control_rate_rms_per_s": float("nan"),
            "control_rate_mean_abs_per_s": float("nan"),
            "control_effort_mean": compute_control_effort(vectors),
        }

    times = np.asarray(timestamps_ns, dtype=float) / 1e9
    values = np.asarray(vectors, dtype=float)
    order = np.argsort(times)
    times = times[order]
    values = values[order]
    dt = np.diff(times)
    dv = np.diff(values, axis=0)
    valid = dt > 1e-6
    if not np.any(valid):
        return {
            "control_rate_rms_per_s": float("nan"),
            "control_rate_mean_abs_per_s": float("nan"),
            "control_effort_mean": compute_control_effort(vectors),
        }

    rates = dv[valid] / dt[valid, None]
    rate_norm = np.linalg.norm(rates, axis=1)
    return {
        "control_rate_rms_per_s": float(np.sqrt(np.mean(rate_norm * rate_norm))),
        "control_rate_mean_abs_per_s": float(np.mean(np.abs(rates))),
        "control_effort_mean": compute_control_effort(vectors),
    }


def compute_control_effort(vectors: Sequence[Sequence[float]]) -> float:
    if not vectors:
        return float("nan")
    values = np.asarray(vectors, dtype=float)
    if values.size == 0:
        return float("nan")
    return float(np.mean(np.linalg.norm(values, axis=1)))


def build_run_metrics(
    *,
    source_row: dict[str, str],
    bag_path: Path,
    analysis_dir: Path,
    summary_metrics: dict[str, float],
    summary_status: str,
    control_metrics: ControlTopicMetrics,
) -> dict[str, object]:
    solve_times = control_metrics.solve_times_ms
    control_rate = compute_control_rate_metrics(
        control_metrics.control_timestamps_ns,
        control_metrics.control_vectors,
    )
    fallback_rate = (
        float(np.mean(control_metrics.fallback_flags))
        if control_metrics.fallback_flags
        else float("nan")
    )
    state_source_fallback_rate = (
        float(np.mean(control_metrics.state_source_fallback_flags))
        if control_metrics.state_source_fallback_flags
        else float("nan")
    )
    safety_violation = composite_safety_violation_rate(summary_metrics)

    return {
        "scenario": source_row.get("scenario", ""),
        "seed": source_row.get("seed", ""),
        "mpc_mode": source_row.get("mpc_mode", ""),
        "status": source_row.get("status", ""),
        "mcap": str(bag_path),
        "analysis_dir": str(analysis_dir),
        "control_parse_status": summary_status,
        "error": "",
        "diagnostics_available": bool_text(bool(summary_metrics)),
        "debug_available": bool_text(control_metrics.debug_available),
        "control_topic": control_metrics.control_topic,
        "control_available": bool_text(control_metrics.control_available),
        "mpc_solve_sample_count": len(solve_times),
        "fallback_sample_count": len(control_metrics.fallback_flags),
        "control_sample_count": len(control_metrics.control_vectors),
        "lateral_error_rmse_m": summary_metrics.get("lateral_error_rmse_m", float("nan")),
        "lateral_error_mean_abs_m": summary_metrics.get("lateral_error_mean_abs_m", float("nan")),
        "mpc_solve_time_mean_ms": mean(solve_times) if solve_times else float("nan"),
        "mpc_solve_time_p95_ms": percentile(solve_times, 95.0),
        "mpc_solve_time_max_ms": max(solve_times) if solve_times else float("nan"),
        "fallback_rate": fallback_rate,
        "state_source_fallback_rate": state_source_fallback_rate,
        "control_rate_rms_per_s": control_rate["control_rate_rms_per_s"],
        "control_rate_mean_abs_per_s": control_rate["control_rate_mean_abs_per_s"],
        "control_effort_mean": control_rate["control_effort_mean"],
        "safety_violation_rate": safety_violation,
        "seabed_clearance_safety_violation_ratio_1p5m": summary_metrics.get(
            "seabed_clearance_safety_violation_ratio_1p5m",
            float("nan"),
        ),
        "seabed_proximity_ratio": summary_metrics.get("seabed_proximity_ratio", float("nan")),
        "seabed_penetration_ratio": summary_metrics.get("seabed_penetration_ratio", float("nan")),
        "high_priority_ratio": summary_metrics.get("high_priority_ratio", float("nan")),
    }


def composite_safety_violation_rate(summary_metrics: dict[str, float]) -> float:
    candidates = [
        summary_metrics.get("seabed_clearance_safety_violation_ratio_1p5m", float("nan")),
        summary_metrics.get("seabed_penetration_ratio", float("nan")),
    ]
    valid = [value for value in candidates if math.isfinite(value)]
    if not valid:
        return float("nan")
    return float(max(valid))


def build_error_row(source_row: dict[str, str], bag_path: Path, analysis_dir: Path, error: str) -> dict[str, object]:
    row: dict[str, object] = {
        "scenario": source_row.get("scenario", ""),
        "seed": source_row.get("seed", ""),
        "mpc_mode": source_row.get("mpc_mode", ""),
        "status": source_row.get("status", ""),
        "mcap": str(bag_path),
        "analysis_dir": str(analysis_dir),
        "control_parse_status": "error",
        "error": error,
        "diagnostics_available": "false",
        "debug_available": "false",
        "control_topic": "",
        "control_available": "false",
        "mpc_solve_sample_count": 0,
        "fallback_sample_count": 0,
        "control_sample_count": 0,
    }
    for metric in CONTROL_METRIC_COLUMNS:
        row[metric] = float("nan")
    return row


def write_summary(rows: Sequence[dict[str, object]], out_path: Path) -> list[dict[str, object]]:
    groups: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        groups[(str(row.get("scenario", "")), str(row.get("mpc_mode", "")))].append(row)

    fieldnames = ["scenario", "mpc_mode", "run_count", "ok_count"]
    for metric in CONTROL_METRIC_COLUMNS:
        fieldnames.extend([f"{metric}_mean", f"{metric}_std", f"{metric}_available_count"])

    summary_rows: list[dict[str, object]] = []
    for (scenario, mode), group_rows in sorted(groups.items()):
        summary: dict[str, object] = {
            "scenario": scenario,
            "mpc_mode": mode,
            "run_count": len(group_rows),
            "ok_count": sum(1 for row in group_rows if str(row.get("control_parse_status", "")).startswith(("generated", "reused"))),
        }
        for metric in CONTROL_METRIC_COLUMNS:
            values = [to_float(row.get(metric)) for row in group_rows]
            values = [value for value in values if math.isfinite(value)]
            summary[f"{metric}_mean"] = mean(values) if values else float("nan")
            summary[f"{metric}_std"] = safe_stdev(values) if values else float("nan")
            summary[f"{metric}_available_count"] = len(values)
        summary_rows.append(summary)

    write_csv_rows(out_path, fieldnames, summary_rows)
    return summary_rows


def write_status_counts(rows: Sequence[dict[str, object]], out_path: Path) -> None:
    counter = Counter(str(row.get("control_parse_status", "")) for row in rows)
    status_rows = [{"control_parse_status": key, "count": value} for key, value in sorted(counter.items())]
    write_csv_rows(out_path, ["control_parse_status", "count"], status_rows)


def write_merged_results(
    *,
    source_rows: Sequence[dict[str, str]],
    run_rows: Sequence[dict[str, object]],
    out_path: Path,
) -> None:
    source_fieldnames: list[str] = []
    for row in source_rows:
        for key in row.keys():
            if key not in source_fieldnames:
                source_fieldnames.append(key)
    control_fieldnames = [key for key in RUN_FIELDNAMES if key not in source_fieldnames]
    fieldnames = [*source_fieldnames, *control_fieldnames]

    merged_rows: list[dict[str, object]] = []
    for source, control in zip(source_rows, run_rows):
        merged = dict(source)
        for key in control_fieldnames:
            merged[key] = control.get(key, "")
        merged_rows.append(merged)
    write_csv_rows(out_path, fieldnames, merged_rows)


def write_markdown_report(
    *,
    out_path: Path,
    run_rows: Sequence[dict[str, object]],
    summary_rows: Sequence[dict[str, object]],
    paths: dict[str, Path],
) -> None:
    lines = [
        "# Control Metrics Aggregate Report",
        "",
        "## Outputs",
        "",
        f"- Per-run table: `{paths['run_csv']}`",
        f"- Scenario/mode summary: `{paths['summary_csv']}`",
        f"- Status counts: `{paths['status_csv']}`",
        f"- Merged source rows: `{paths['merged_csv']}`",
        "",
        "## Parse Status",
        "",
    ]
    status_counter = Counter(str(row.get("control_parse_status", "")) for row in run_rows)
    lines.extend([f"- `{status}`: {count}" for status, count in sorted(status_counter.items())])

    lines.extend(
        [
            "",
            "## Scenario / Mode Summary",
            "",
            "| scenario | mode | ok/total | lateral RMSE m | solve mean ms | fallback rate | control rate RMS | safety violation |",
            "|---|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for row in summary_rows:
        total = int(row.get("run_count", 0))
        ok = int(row.get("ok_count", 0))
        lines.append(
            "| {scenario} | {mode} | {ok}/{total} | {lat} | {solve} | {fallback} | {control} | {safety} |".format(
                scenario=row.get("scenario", ""),
                mode=row.get("mpc_mode", ""),
                ok=ok,
                total=total,
                lat=format_mean_std(row, "lateral_error_rmse_m"),
                solve=format_mean_std(row, "mpc_solve_time_mean_ms"),
                fallback=format_mean_std(row, "fallback_rate"),
                control=format_mean_std(row, "control_rate_rms_per_s"),
                safety=format_mean_std(row, "safety_violation_rate"),
            )
        )

    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- `lateral_error_*` and seabed safety metrics come from `tools/analyze_bag.py` summary statistics.",
            "- `mpc_solve_time_*` and `fallback_rate` come from `/auv/controller/debug` when that topic is present.",
            "- `control_rate_*` prefers `/auv/control/mpc_cmd`; it falls back to `/cmd_vel` for PID runs.",
            "- Missing topics are represented as `nan` with availability columns in the per-run table.",
            "",
        ]
    )
    out_path.write_text("\n".join(lines), encoding="utf-8")


def format_mean_std(row: dict[str, object], metric: str) -> str:
    value = to_float(row.get(f"{metric}_mean"))
    spread = to_float(row.get(f"{metric}_std"))
    count = int(to_float(row.get(f"{metric}_available_count"), 0.0))
    if not math.isfinite(value):
        return "nan"
    if count <= 1 or not math.isfinite(spread):
        return f"{value:.4g}"
    return f"{value:.4g}+/-{spread:.4g}"


def main() -> None:
    args = parse_args()
    output_dir = args.output_dir or get_output_dir("results/control_aggregates")
    output_dir.mkdir(parents=True, exist_ok=True)
    analysis_root = args.analysis_root or (output_dir / "bag_analysis")
    analysis_root.mkdir(parents=True, exist_ok=True)

    source_rows = make_input_rows(args)
    run_rows: list[dict[str, object]] = []

    for index, source_row in enumerate(source_rows):
        bag_value = source_row.get("mcap") or source_row.get("bag") or ""
        bag_path = Path(bag_value).expanduser()
        if not bag_path.is_absolute():
            bag_path = (PROJECT_ROOT / bag_path).resolve()
        analysis_dir = analysis_dir_for_row(source_row, analysis_root, index)
        try:
            if not bag_value:
                raise RuntimeError("missing mcap column")
            if not bag_path.exists():
                raise RuntimeError(f"bag path does not exist: {bag_path}")
            summary_path, summary_status = ensure_summary_statistics(
                bag_path=bag_path,
                analysis_dir=analysis_dir,
                reuse_analysis=args.reuse_analysis,
                skip_analyze_bag=args.skip_analyze_bag,
            )
            summary_metrics = read_summary_metrics(summary_path)
            topic_metrics = parse_control_topics(
                bag_path=bag_path,
                debug_topic=args.topic_debug,
                mpc_cmd_topic=args.topic_mpc_cmd,
                cmd_vel_topic=args.topic_cmd_vel,
            )
            run_rows.append(
                build_run_metrics(
                    source_row=source_row,
                    bag_path=bag_path,
                    analysis_dir=analysis_dir,
                    summary_metrics=summary_metrics,
                    summary_status=summary_status,
                    control_metrics=topic_metrics,
                )
            )
        except Exception as exc:  # noqa: BLE001 - keep batch aggregation moving.
            run_rows.append(build_error_row(source_row, bag_path, analysis_dir, str(exc)))

    run_csv = output_dir / "control_metrics_by_run.csv"
    summary_csv = output_dir / "control_summary_by_scenario_mode.csv"
    status_csv = output_dir / "control_status_counts.csv"
    merged_csv = output_dir / args.merged_results_name
    report_md = output_dir / "control_aggregate_report.md"

    write_csv_rows(run_csv, RUN_FIELDNAMES, run_rows)
    summary_rows = write_summary(run_rows, summary_csv)
    write_status_counts(run_rows, status_csv)
    write_merged_results(source_rows=source_rows, run_rows=run_rows, out_path=merged_csv)
    write_markdown_report(
        out_path=report_md,
        run_rows=run_rows,
        summary_rows=summary_rows,
        paths={
            "run_csv": run_csv,
            "summary_csv": summary_csv,
            "status_csv": status_csv,
            "merged_csv": merged_csv,
        },
    )

    print(f"[OK] Wrote per-run control metrics: {run_csv}")
    print(f"[OK] Wrote scenario/mode summary: {summary_csv}")
    print(f"[OK] Wrote status counts: {status_csv}")
    print(f"[OK] Wrote merged results: {merged_csv}")
    print(f"[OK] Wrote report: {report_md}")


if __name__ == "__main__":
    main()

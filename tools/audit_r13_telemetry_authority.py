#!/usr/bin/env python3
"""Audit R13-v2 applied-speed and authority telemetry from MCAP bundles."""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable

from mcap_ros2.reader import read_ros2_messages


DEBUG_TOPIC = "/auv/controller/debug"
AUTHORITY_TOPIC = "/auv/perception/cable_tracking_authority_shadow"
SONAR_QUALITY_TOPIC = "/auv/perception/quality/sonar"
TOPICS = {DEBUG_TOPIC, AUTHORITY_TOPIC, SONAR_QUALITY_TOPIC}
MODE_NAMES = {
    0: "hold",
    1: "search",
    2: "track",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path, help="Proxy cable sweep bundle directory.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Output directory. Defaults to <bundle>/r13_telemetry_authority_audit.",
    )
    return parser.parse_args()


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv_rows(path: Path, rows: list[dict[str, object]]) -> None:
    fields: list[str] = []
    for row in rows:
        for field in row:
            if field not in fields:
                fields.append(field)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def to_float(value: object) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return float("nan")
    return result if math.isfinite(result) else float("nan")


def finite(values: Iterable[float]) -> list[float]:
    return [float(value) for value in values if math.isfinite(float(value))]


def percentile(values: list[float], q: float) -> float:
    data = sorted(finite(values))
    if not data:
        return float("nan")
    if len(data) == 1:
        return data[0]
    position = (len(data) - 1) * q / 100.0
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return data[lower]
    weight = position - lower
    return data[lower] * (1.0 - weight) + data[upper] * weight


def stats(values: list[float]) -> dict[str, float | int]:
    data = finite(values)
    if not data:
        return {
            "count": 0,
            "min": float("nan"),
            "q05": float("nan"),
            "mean": float("nan"),
            "q50": float("nan"),
            "q95": float("nan"),
            "max": float("nan"),
            "span": float("nan"),
        }
    return {
        "count": len(data),
        "min": min(data),
        "q05": percentile(data, 5.0),
        "mean": statistics.mean(data),
        "q50": percentile(data, 50.0),
        "q95": percentile(data, 95.0),
        "max": max(data),
        "span": max(data) - min(data),
    }


def mode_ratios(modes: list[int]) -> dict[str, float]:
    total = len(modes)
    counts = Counter(modes)
    return {
        f"{name}_ratio": (counts.get(mode, 0) / total if total else float("nan"))
        for mode, name in MODE_NAMES.items()
    }


def prefixed(prefix: str, payload: dict[str, object]) -> dict[str, object]:
    return {f"{prefix}_{key}": value for key, value in payload.items()}


def parse_debug_payload(value: object) -> dict[str, object]:
    try:
        parsed = json.loads(str(value))
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def json_safe(value: object) -> object:
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_safe(item) for item in value]
    return value


def read_run(row: dict[str, str]) -> dict[str, object]:
    mcap_path = Path(row.get("mcap", ""))
    payloads: dict[str, list[float]] = defaultdict(list)
    debug_modes: list[int] = []
    topic_modes: list[int] = []
    accepted: list[bool] = []
    reasons: Counter[str] = Counter()
    debug_samples = 0
    applied_samples = 0
    authority_snapshot_samples = 0
    topic_authority_samples = 0
    sonar_samples = 0

    if not mcap_path.is_file():
        return {
            "scenario": row.get("scenario", ""),
            "seed": row.get("seed", ""),
            "mpc_mode": row.get("mpc_mode", ""),
            "status": "missing_mcap",
            "mcap": str(mcap_path),
        }

    for decoded in read_ros2_messages(str(mcap_path), topics=TOPICS):
        topic = decoded.channel.topic
        msg = decoded.ros_msg
        if topic == DEBUG_TOPIC:
            payload = parse_debug_payload(getattr(msg, "data", ""))
            if not payload:
                continue
            debug_samples += 1
            requested = to_float(payload.get("requested_target_speed_mps"))
            if not math.isfinite(requested):
                requested = to_float(payload.get("target_speed_mps"))
            if math.isfinite(requested):
                payloads["requested_speed"].append(requested)

            policy = payload.get("quality_control_policy")
            policy = policy if isinstance(policy, dict) else {}
            input_speed = to_float(policy.get("input_target_speed_mps"))
            applied = to_float(policy.get("applied_target_speed_mps"))
            if not math.isfinite(applied):
                applied = to_float(payload.get("applied_target_speed_mps"))
            if math.isfinite(input_speed):
                payloads["policy_input_speed"].append(input_speed)
            if math.isfinite(applied):
                applied_samples += 1
                payloads["applied_speed"].append(applied)
            speed_scale = to_float(policy.get("speed_scale"))
            if not math.isfinite(speed_scale) and math.isfinite(input_speed) and math.isfinite(applied):
                if abs(input_speed) > 1.0e-9:
                    speed_scale = applied / input_speed
                elif abs(applied) <= 1.0e-9:
                    speed_scale = 0.0
            if math.isfinite(speed_scale):
                payloads["speed_scale"].append(speed_scale)

            accepted.append(bool(policy.get("accepted", False)))
            reason = str(policy.get("reason", "")).strip()
            if reason:
                reasons[reason] += 1
            confidence = to_float(policy.get("confidence"))
            if not math.isfinite(confidence):
                confidence = to_float(payload.get("confidence"))
            if math.isfinite(confidence):
                payloads["confidence"].append(confidence)
            delta_penalty = to_float(policy.get("delta_u_penalty_scale"))
            if math.isfinite(delta_penalty):
                payloads["delta_u_penalty_scale"].append(delta_penalty)

            authority = policy.get("authority_snapshot")
            if isinstance(authority, dict):
                authority_snapshot_samples += 1
                mode_value = to_float(authority.get("mode"))
                if math.isfinite(mode_value):
                    debug_modes.append(int(mode_value))
                for key in ("p_track", "age_s"):
                    value = to_float(authority.get(key))
                    if math.isfinite(value):
                        payloads[f"authority_{key}"].append(value)
            continue

        if topic == AUTHORITY_TOPIC:
            topic_authority_samples += 1
            topic_modes.append(int(getattr(msg, "mode", -1)))
            p_track = to_float(getattr(msg, "p_track", float("nan")))
            if math.isfinite(p_track):
                payloads["topic_authority_p_track"].append(p_track)
            continue

        if topic == SONAR_QUALITY_TOPIC:
            sonar_samples += 1
            p_track = to_float(getattr(msg, "p_track", float("nan")))
            if math.isfinite(p_track):
                payloads["sonar_p_track"].append(p_track)

    accepted_rate = (
        sum(1 for value in accepted if value) / len(accepted)
        if accepted
        else float("nan")
    )
    result: dict[str, object] = {
        "scenario": row.get("scenario", ""),
        "seed": row.get("seed", ""),
        "mpc_mode": row.get("mpc_mode", ""),
        "status": row.get("status", ""),
        "mcap": str(mcap_path),
        "debug_sample_count": debug_samples,
        "applied_speed_sample_count": applied_samples,
        "authority_snapshot_sample_count": authority_snapshot_samples,
        "topic_authority_sample_count": topic_authority_samples,
        "sonar_quality_sample_count": sonar_samples,
        "quality_accept_rate": accepted_rate,
        "quality_reasons_json": json.dumps(dict(reasons), sort_keys=True),
        "missing_applied_speed": applied_samples == 0,
        "missing_debug_authority_snapshot": authority_snapshot_samples == 0,
    }
    for key in (
        "requested_speed",
        "policy_input_speed",
        "applied_speed",
        "speed_scale",
        "confidence",
        "delta_u_penalty_scale",
        "authority_p_track",
        "authority_age_s",
        "topic_authority_p_track",
        "sonar_p_track",
    ):
        result.update(prefixed(key, stats(payloads[key])))
    result.update(prefixed("debug_authority", mode_ratios(debug_modes)))
    result.update(prefixed("topic_authority", mode_ratios(topic_modes)))
    return result


def finite_field(rows: list[dict[str, object]], field: str) -> list[float]:
    return finite(to_float(row.get(field)) for row in rows)


def summarize_by_scenario_mode(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[(str(row["scenario"]), str(row["mpc_mode"]))].append(row)

    out: list[dict[str, object]] = []
    for (scenario, mode), group in sorted(grouped.items()):
        applied_runs = sum(
            int(to_float(row.get("applied_speed_sample_count")) > 0)
            for row in group
        )
        missing_applied = sum(bool(row.get("missing_applied_speed")) for row in group)
        item: dict[str, object] = {
            "scenario": scenario,
            "mpc_mode": mode,
            "run_count": len(group),
            "applied_speed_available_runs": applied_runs,
            "missing_applied_speed_runs": missing_applied,
            "quality_accept_rate_mean": statistics.mean(
                finite_field(group, "quality_accept_rate")
            )
            if finite_field(group, "quality_accept_rate")
            else float("nan"),
            "speed_scale_min_min": min(
                finite_field(group, "speed_scale_min"), default=float("nan")
            ),
            "speed_scale_q05_min": min(
                finite_field(group, "speed_scale_q05"), default=float("nan")
            ),
            "speed_scale_mean_mean": statistics.mean(
                finite_field(group, "speed_scale_mean")
            )
            if finite_field(group, "speed_scale_mean")
            else float("nan"),
            "applied_speed_span_max": max(
                finite_field(group, "applied_speed_span"), default=float("nan")
            ),
            "confidence_span_mean": statistics.mean(
                finite_field(group, "confidence_span")
            )
            if finite_field(group, "confidence_span")
            else float("nan"),
            "delta_u_penalty_scale_span_mean": statistics.mean(
                finite_field(group, "delta_u_penalty_scale_span")
            )
            if finite_field(group, "delta_u_penalty_scale_span")
            else float("nan"),
            "debug_track_ratio_mean": statistics.mean(
                finite_field(group, "debug_authority_track_ratio")
            )
            if finite_field(group, "debug_authority_track_ratio")
            else float("nan"),
            "topic_track_ratio_mean": statistics.mean(
                finite_field(group, "topic_authority_track_ratio")
            )
            if finite_field(group, "topic_authority_track_ratio")
            else float("nan"),
        }
        out.append(item)
    return out


def render_report(
    *,
    bundle: Path,
    output_dir: Path,
    run_rows: list[dict[str, object]],
    summary_rows: list[dict[str, object]],
) -> str:
    ua_rows = [row for row in run_rows if row.get("mpc_mode") == "ua"]
    ua_speed_min = min(finite_field(ua_rows, "speed_scale_min"), default=float("nan"))
    ua_accept = finite_field(ua_rows, "quality_accept_rate")
    missing = sum(bool(row.get("missing_applied_speed")) for row in run_rows)
    authority_missing = sum(
        bool(row.get("missing_debug_authority_snapshot")) for row in run_rows
    )
    lines = [
        "# R13-v2 Telemetry / Authority Audit",
        "",
        f"- Bundle: `{bundle}`",
        f"- Runs audited: `{len(run_rows)}`",
        f"- Applied-speed missing runs: `{missing}`",
        f"- Debug authority snapshot missing runs: `{authority_missing}`",
        f"- UA quality accept-rate mean: `{statistics.mean(ua_accept) if ua_accept else float('nan'):.3f}`",
        f"- UA global minimum speed scale: `{ua_speed_min:.3f}`",
        "",
        "## Scenario / Mode Summary",
        "",
        "| scenario | mode | runs | applied runs | accept mean | min speed scale | TRACK mean | confidence span mean |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in summary_rows:
        lines.append(
            "| {scenario} | {mode} | {runs} | {applied} | {accept:.3f} | {scale:.3f} | {track:.3f} | {conf:.3f} |".format(
                scenario=row["scenario"],
                mode=row["mpc_mode"],
                runs=int(row["run_count"]),
                applied=int(row["applied_speed_available_runs"]),
                accept=to_float(row["quality_accept_rate_mean"]),
                scale=to_float(row["speed_scale_min_min"]),
                track=to_float(row["debug_track_ratio_mean"]),
                conf=to_float(row["confidence_span_mean"]),
            )
        )
    lines.extend(
        [
            "",
            "## Outputs",
            "",
            f"- Per-run CSV: `{output_dir / 'r13_telemetry_authority_by_run.csv'}`",
            f"- Scenario/mode CSV: `{output_dir / 'r13_telemetry_authority_by_scenario_mode.csv'}`",
            f"- JSON summary: `{output_dir / 'r13_telemetry_authority_summary.json'}`",
            "",
            "Boundary: this audit only proves telemetry observability and policy application inside the proxy/PVS run. It does not replace the full R13 formal 36-run matrix or physical hardware evidence.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    bundle = args.bundle.resolve()
    output_dir = (
        args.output_dir.resolve()
        if args.output_dir
        else bundle / "r13_telemetry_authority_audit"
    )
    rows = read_csv_rows(bundle / "results.csv")
    run_rows = [read_run(row) for row in rows]
    summary_rows = summarize_by_scenario_mode(run_rows)
    output_dir.mkdir(parents=True, exist_ok=True)
    write_csv_rows(output_dir / "r13_telemetry_authority_by_run.csv", run_rows)
    write_csv_rows(
        output_dir / "r13_telemetry_authority_by_scenario_mode.csv",
        summary_rows,
    )
    payload = {
        "schema_version": "r13_telemetry_authority_audit.v1",
        "bundle": str(bundle),
        "outputs": {
            "by_run": str(output_dir / "r13_telemetry_authority_by_run.csv"),
            "by_scenario_mode": str(
                output_dir / "r13_telemetry_authority_by_scenario_mode.csv"
            ),
            "report": str(output_dir / "report.md"),
        },
        "run_count": len(run_rows),
        "missing_applied_speed_runs": sum(
            bool(row.get("missing_applied_speed")) for row in run_rows
        ),
        "missing_debug_authority_snapshot_runs": sum(
            bool(row.get("missing_debug_authority_snapshot")) for row in run_rows
        ),
        "summary_by_scenario_mode": summary_rows,
    }
    (output_dir / "r13_telemetry_authority_summary.json").write_text(
        json.dumps(json_safe(payload), indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    (output_dir / "report.md").write_text(
        render_report(
            bundle=bundle,
            output_dir=output_dir,
            run_rows=run_rows,
            summary_rows=summary_rows,
        ),
        encoding="utf-8",
    )
    print(f"wrote R13 telemetry/authority audit to {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

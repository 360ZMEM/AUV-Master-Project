#!/usr/bin/env python3
"""Audit the paired source-specific R13-v2 pilot MCAPs."""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path

from mcap_ros2.reader import read_ros2_messages


QUALITY_MAGNETIC = "/auv/perception/quality/magnetic"
QUALITY_SONAR = "/auv/perception/quality/sonar"
AUTHORITY = "/auv/perception/cable_tracking_authority_shadow"
CONTROLLER_DEBUG = "/auv/controller/debug"
TOPICS = {
    QUALITY_MAGNETIC,
    QUALITY_SONAR,
    AUTHORITY,
    CONTROLLER_DEBUG,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("bundle", type=Path)
    return parser.parse_args()


def finite_range(values: list[float]) -> dict[str, float | int | None]:
    finite = [value for value in values if math.isfinite(value)]
    return {
        "count": len(finite),
        "min": min(finite, default=None),
        "max": max(finite, default=None),
        "span": max(finite) - min(finite) if finite else None,
    }


def read_run(row: dict[str, str]) -> dict[str, object]:
    data: dict[str, list] = {
        "magnetic_p_detect": [],
        "magnetic_p_track": [],
        "sonar_p_detect": [],
        "sonar_p_track": [],
        "authority_modes": [],
        "authority_sources": [],
        "debug": [],
    }
    for decoded in read_ros2_messages(row["mcap"], topics=TOPICS):
        topic = decoded.channel.topic
        msg = decoded.ros_msg
        if topic == QUALITY_MAGNETIC:
            data["magnetic_p_detect"].append(float(msg.p_detect))
            data["magnetic_p_track"].append(float(msg.p_track))
        elif topic == QUALITY_SONAR:
            data["sonar_p_detect"].append(float(msg.p_detect))
            data["sonar_p_track"].append(float(msg.p_track))
        elif topic == AUTHORITY:
            data["authority_modes"].append(int(msg.mode))
            data["authority_sources"].append(list(msg.contributing_sources))
        elif topic == CONTROLLER_DEBUG:
            try:
                data["debug"].append(json.loads(str(msg.data)))
            except json.JSONDecodeError:
                pass

    debug = data["debug"]
    quality_decisions = [
        item.get("quality_control_policy", {})
        for item in debug
        if isinstance(item.get("quality_control_policy"), dict)
    ]
    return {
        "scenario": row["scenario"],
        "seed": int(row["seed"]),
        "mpc_mode": row["mpc_mode"],
        "mcap": row["mcap"],
        "exogenous_input_sha256": row.get("exogenous_input_sha256", ""),
        "magnetic_p_detect": finite_range(data["magnetic_p_detect"]),
        "magnetic_p_track": finite_range(data["magnetic_p_track"]),
        "sonar_p_detect": finite_range(data["sonar_p_detect"]),
        "sonar_p_track": finite_range(data["sonar_p_track"]),
        "authority_message_count": len(data["authority_modes"]),
        "authority_modes": sorted(set(data["authority_modes"])),
        "authority_source_sets": sorted(
            {tuple(item) for item in data["authority_sources"]}
        ),
        "controller_debug_count": len(debug),
        "confidence_values": finite_range(
            [
                float(item.get("confidence", float("nan")))
                for item in debug
            ]
        ),
        "confidence_policies": sorted(
            {
                str(item.get("confidence_policy", ""))
                for item in debug
            }
        ),
        "quality_policy_accepted": sorted(
            {bool(item.get("accepted", False)) for item in quality_decisions}
        ),
        "delta_u_penalty_scale": finite_range(
            [
                float(item.get("delta_u_penalty_scale", float("nan")))
                for item in quality_decisions
            ]
        ),
        "previous_control_available_rate": (
            sum(
                bool(item.get("delta_u_previous_control_available", False))
                for item in debug
            )
            / len(debug)
            if debug
            else None
        ),
        "fallback_count": sum(
            str(item.get("fallback_type", "none")) != "none"
            for item in debug
        ),
        "blocked_count": sum(
            bool(item.get("control_period_blocked", False))
            for item in debug
        ),
    }


def main() -> int:
    args = parse_args()
    results_path = args.bundle / "results.csv"
    with results_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    by_mode = {row["mpc_mode"]: read_run(row) for row in rows}
    baseline = by_mode.get("baseline")
    ua = by_mode.get("ua")
    checks = {
        "paired_modes_present": baseline is not None and ua is not None,
        "same_scenario_seed": bool(
            baseline
            and ua
            and (baseline["scenario"], baseline["seed"])
            == (ua["scenario"], ua["seed"])
        ),
        "same_exogenous_input_hash": bool(
            baseline
            and ua
            and baseline["exogenous_input_sha256"]
            and baseline["exogenous_input_sha256"]
            == ua["exogenous_input_sha256"]
        ),
        "both_sources_observed": all(
            run
            and int(run["magnetic_p_detect"]["count"]) > 0
            and int(run["sonar_p_track"]["count"]) > 0
            for run in (baseline, ua)
        ),
        "sonar_p_track_nonconstant": all(
            run
            and float(run["sonar_p_track"]["span"] or 0.0) > 1.0e-3
            for run in (baseline, ua)
        ),
        "magnetic_does_not_claim_p_track": all(
            run and int(run["magnetic_p_track"]["count"]) == 0
            for run in (baseline, ua)
        ),
        "track_authority_observed": all(
            run
            and 2 in run["authority_modes"]
            and ("magnetic_45hz", "sonar_cable")
            in run["authority_source_sets"]
            for run in (baseline, ua)
        ),
        "baseline_quality_control_disabled": bool(
            baseline
            and baseline["quality_policy_accepted"] == [False]
        ),
        "ua_quality_control_accepted": bool(
            ua and ua["quality_policy_accepted"] == [True]
        ),
        "ua_conservative_policy_recorded": bool(
            ua and ua["confidence_policies"] == ["conservative"]
        ),
        "ua_dynamic_confidence_recorded": bool(
            ua and float(ua["confidence_values"]["span"] or 0.0) > 1.0e-3
        ),
        "ua_dynamic_delta_penalty_recorded": bool(
            ua
            and float(ua["delta_u_penalty_scale"]["min"] or 0.0) > 1.0
            and float(ua["delta_u_penalty_scale"]["span"] or 0.0) > 1.0e-3
        ),
        "ua_previous_control_anchor_used": bool(
            ua and float(ua["previous_control_available_rate"] or 0.0) > 0.0
        ),
        "no_controller_fallback": all(
            run and int(run["fallback_count"]) == 0
            for run in (baseline, ua)
        ),
        "no_control_period_block": all(
            run and int(run["blocked_count"]) == 0
            for run in (baseline, ua)
        ),
    }
    payload = {
        "schema_version": "r13_source_specific_pilot_audit.v1",
        "passed": all(checks.values()),
        "checks": checks,
        "runs": by_mode,
    }
    output = args.bundle / "pilot_audit.json"
    output.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False)
        + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False))
    return 0 if payload["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

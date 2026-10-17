#!/usr/bin/env python3
"""Inject a bounded current-report bias into the frozen shallow-survey PVS loop.

The plant keeps its true synthetic current. Only the ROS decision callback
sees the biased value. This is a fault-injection fixture, not a current sensor.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from std_msgs.msg import String

from smoke_v2_shallow_survey_ros_pvs import run
from auv_cable_tracking_v2.cable_tracking_v2_node import CableTrackingV2Node


ROOT = Path(__file__).resolve().parents[1]


def biased_message(msg: String, bias_mps: float) -> String:
    payload = json.loads(msg.data)
    if payload.get("source") != "synthetic_current_fixture":
        raise ValueError("only the synthetic current fixture may be biased")
    velocity = list(payload["velocity_xy_mps"])
    velocity[1] = float(velocity[1]) + bias_mps
    payload["velocity_xy_mps"] = velocity
    return String(data=json.dumps(payload))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=101)
    parser.add_argument("--true-current-y-mps", type=float, default=.04)
    parser.add_argument("--report-bias-mps", type=float, default=-.005)
    parser.add_argument("--output-dir", type=Path, default=ROOT /
                        "AUV-Master-Mag/results/v2/shallow_survey_current_bias_20260927")
    args = parser.parse_args()
    if abs(args.report_bias_mps) > .02:
        raise ValueError("bias injection is limited to 0.02 m/s")
    script_hash = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    original = CableTrackingV2Node._on_survey_current_evidence

    def receive_biased(self: CableTrackingV2Node, msg: String) -> None:
        original(self, biased_message(msg, args.report_bias_mps))

    CableTrackingV2Node._on_survey_current_evidence = receive_biased
    try:
        summary = run("wire", args.seed, args.output_dir,
                      current_y_mps=args.true_current_y_mps)
    finally:
        CableTrackingV2Node._on_survey_current_evidence = original
    summary.update({
        "fault_injection": "decision_current_report_bias_y_mps",
        "reported_current_y_mps": args.true_current_y_mps + args.report_bias_mps,
        "true_plant_current_y_mps": args.true_current_y_mps,
        "reported_current_bias_y_mps": args.report_bias_mps,
        "publisher_source_string_unchanged": True,
        "fault_injection_source_sha256_at_start": script_hash,
    })
    path = args.output_dir / f"wire_{'positive' if args.true_current_y_mps > 0 else 'negative'}_seed{args.seed}_summary.json"
    path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: summary[key] for key in (
        "terminal_reason", "track_samples", "track_truth_lateral_mae_m",
        "reported_current_y_mps", "true_plant_current_y_mps")}, indent=2))


if __name__ == "__main__":
    main()

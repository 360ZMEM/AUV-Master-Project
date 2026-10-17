#!/usr/bin/env python3
"""Record a compact, reviewable acceptance summary for the defense demo."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import time

import rclpy
from rclpy.node import Node
from std_msgs.msg import String


def _finite_or_none(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number and abs(number) != float("inf") else None


class AssuranceMonitor(Node):
    def __init__(self) -> None:
        super().__init__("auv_defense_assurance_monitor")
        self.transitions: list[dict[str, object]] = []
        self.latest: dict[str, object] = {}
        self.best: dict[str, object] = {}
        self._last_phase: str | None = None
        self.create_subscription(String, "/auv/cable/diagnostics", self._on_diagnostics, 20)

    def _on_diagnostics(self, msg: String) -> None:
        try:
            payload = json.loads(msg.data)
        except (TypeError, json.JSONDecodeError):
            return
        if not isinstance(payload, dict):
            return
        self.latest = payload
        phase = str(payload.get("mission_phase", "unknown")).upper()
        if phase != self._last_phase:
            self.transitions.append(
                {
                    "elapsed_s": round(time.monotonic() - START_MONOTONIC, 3),
                    "phase": phase,
                    "reason_codes": payload.get("fwhm_reason_codes", []),
                    "scan_attempt": payload.get("cross_scan_attempt"),
                }
            )
            self._last_phase = phase
        score = _finite_or_none(payload.get("fwhm_validity_score")) or 0.0
        best_score = _finite_or_none(self.best.get("fwhm_validity_score")) or -1.0
        if score >= best_score and payload.get("fwhm_width_m") is not None:
            keys = (
                "mission_phase", "fwhm_valid", "fwhm_width_m",
                "fwhm_vertical_separation_m", "fwhm_burial_depth_m",
                "fwhm_burial_depth_sigma_m", "fwhm_validity_score",
                "fwhm_confidence", "fwhm_model_residual", "fwhm_reason_codes",
                "fwhm_prominence_nt", "fwhm_snr_db", "fwhm_symmetry_score",
                "fwhm_coverage_score",
                "fwhm_peak_value_nt", "fwhm_baseline_nt", "fwhm_half_level_nt",
                "fwhm_left_x_m", "fwhm_right_x_m", "cross_scan_attempt",
                "cross_scan_center_strategy", "cross_scan_along_track_range_m",
                "cross_scan_completion_reason", "signed_cross_track_m",
                "cross_scan_return_distance_m",
            )
            self.best = {key: payload.get(key) for key in keys}


START_MONOTONIC = time.monotonic()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--duration", type=float, default=180.0)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expected-burial-m", type=float, default=1.0)
    parser.add_argument("--burial-tolerance-m", type=float, default=0.5)
    parser.add_argument("--post-track-hold-s", type=float, default=8.0)
    args = parser.parse_args()

    rclpy.init()
    node = AssuranceMonitor()
    deadline = time.monotonic() + max(args.duration, 1.0)
    track_seen_at: float | None = None
    try:
        while rclpy.ok() and time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=0.25)
            if any(item["phase"] == "TRACK" for item in node.transitions) and track_seen_at is None:
                track_seen_at = time.monotonic()
            if track_seen_at is not None and time.monotonic() - track_seen_at >= args.post_track_hold_s:
                break
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()

    burial = _finite_or_none(node.best.get("fwhm_burial_depth_m"))
    saw_track = any(item["phase"] == "TRACK" for item in node.transitions)
    burial_ok = burial is not None and abs(burial - args.expected_burial_m) <= args.burial_tolerance_m
    passed = bool(saw_track and node.best.get("fwhm_valid") is True and burial_ok)
    report = {
        "schema": "auv.defense_assurance.v1",
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "passed": passed,
        "acceptance": {
            "saw_track": saw_track,
            "fwhm_valid": node.best.get("fwhm_valid") is True,
            "expected_burial_m": args.expected_burial_m,
            "burial_tolerance_m": args.burial_tolerance_m,
            "burial_within_tolerance": burial_ok,
        },
        "phase_transitions": node.transitions,
        "best_fwhm": node.best,
        "latest_diagnostics": node.latest,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["acceptance"], ensure_ascii=False))
    print(args.output)
    return 0 if passed else 3


if __name__ == "__main__":
    raise SystemExit(main())

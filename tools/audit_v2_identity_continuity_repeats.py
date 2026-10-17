#!/usr/bin/env python3
"""Audit independent-seed, synthetic ROS/PVS identity-continuity runs."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "AUV-Master-Mag/results/v2/inspection_identity_continuity_20260927"
OUT = ROOT / ("AUV-Master-Mag/docs/v2/publication/"
              "fwhm_v2_experiment_results/data/30_identity_continuity_three_seed_audit.json")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def paths(seed: int, condition: str) -> tuple[Path, Path]:
    if seed == 101:
        name = {"clean": "true_clean", "dropout": "true_dropout",
                "switch": "true_switch", "navigation_perturbed": "true_nav_perturbed"}[condition]
    else:
        name = f"seed{seed}_" + {"clean": "none", "dropout": "dropout",
                                 "switch": "switch", "navigation_perturbed": "nav_perturbed"}[condition]
    directory = RUNS / name
    return directory / f"wire_seed_{seed}_summary.json", directory / f"wire_seed_{seed}.csv"


def inspect(seed: int, condition: str) -> dict:
    summary_path, csv_path = paths(seed, condition)
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    with csv_path.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    last = rows[-1]
    truth_errors = [abs(float(row["y_m"]) - 6.) for row in rows
                    if row["mode"] == "track" and float(row["x_m"]) >= 0.]
    actual_reason = summary["first_hold_reason"]
    expected_reason = {"dropout": "flythrough_runtime_identity_lost",
                       "switch": "flythrough_runtime_identity_diverged"}.get(condition)
    expected_complete = condition in {"clean", "navigation_perturbed"}
    passed = (summary["completed"] is expected_complete
              and actual_reason == expected_reason
              and summary["ever_track"]
              and not summary["depth_published"]
              and summary["sonar_fixture_uses_true_plant_pose"]
              and summary["ros_dds"] and summary["protocol_encoded"]
              and summary["bridge_and_guard_connected"]
              and not summary["hardware_connected"]
              and float(last["thrust_percent"]) == 0.
              and int(last["rpm"]) == 0)
    if expected_complete:
        passed = (passed and len(truth_errors) >= 200
                  and sum(truth_errors) / len(truth_errors) < 1.
                  and max(truth_errors) < 2.)
    else:
        passed = passed and last["mode"] == "hold" and last["lateral_valid"] == "False"
    return {
        "seed": seed,
        "condition": condition,
        "passed_synthetic_envelope": bool(passed),
        "completed": summary["completed"],
        "hold_reason": actual_reason,
        "first_track_s": summary["first_track_s"],
        "end_time_s": float(last["time_s"]),
        "true_positive_track_samples": len(truth_errors),
        "true_positive_track_mae_m": (sum(truth_errors) / len(truth_errors)
                                      if truth_errors else None),
        "true_positive_track_max_m": max(truth_errors) if truth_errors else None,
        "last_pid_thrust_percent": float(last["thrust_percent"]),
        "last_udp_rpm": int(last["rpm"]),
        "depth_published": summary["depth_published"],
        "summary_path": str(summary_path.relative_to(ROOT)),
        "summary_sha256": digest(summary_path),
        "csv_path": str(csv_path.relative_to(ROOT)),
        "csv_sha256": digest(csv_path),
    }


def main() -> None:
    cases = [inspect(seed, condition) for seed in (101, 102, 103)
             for condition in ("clean", "navigation_perturbed", "dropout", "switch")]
    payload = {
        "role": "synthetic_identity_continuity_three_seed_audit",
        "scope": "Three magnetic/noise seeds; direct synthetic sonar/quality fixture; no physical sonar or PC104.",
        "example_route_mae_limit_m": 1.,
        "example_route_max_limit_m": 2.,
        "all_passed_synthetic_envelope": all(item["passed_synthetic_envelope"] for item in cases),
        "cases": cases,
        "audit_script_sha256": digest(Path(__file__)),
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"all_passed": payload["all_passed_synthetic_envelope"],
                      "case_count": len(cases),
                      "failures": [(item["seed"], item["condition"], item["hold_reason"])
                                   for item in cases if not item["passed_synthetic_envelope"]]},
                     ensure_ascii=False))
    if not payload["all_passed_synthetic_envelope"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

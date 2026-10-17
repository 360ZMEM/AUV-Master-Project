#!/usr/bin/env python3
"""Archive and assert the native-PVS static-side-hint bias counterexample."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "AUV-Master-Mag/results/v2/inspection_static_hint_bias_20260927"
OUTPUT = (ROOT / "AUV-Master-Mag/docs/v2/publication/fwhm_v2_experiment_results"
          / "data/54_static_hint_bias_closed_loop.json")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    configuration = INPUT / "biased_hint_config.yaml"
    cases = []
    for name, with_neighbor in (("biased_clean", False), ("biased_double", True)):
        folder = INPUT / name
        summary_file = folder / "wire_seed_101_summary.json"
        csv_file = folder / "wire_seed_101.csv"
        summary = json.loads(summary_file.read_text())
        with csv_file.open(newline="") as stream:
            rows = list(csv.DictReader(stream))
        true_errors = [abs(float(row["y_m"]) - 6.) for row in rows
                       if row["mode"] == "track" and float(row["x_m"]) >= 0.]
        assert summary["seed"] == 101 and summary["cable_lateral_m"] == 6.
        assert summary["secondary_cable_gain_nt"] == (10. if with_neighbor else 0.)
        assert not summary["depth_published"] and all(row["depth_valid"] == "False" for row in rows)
        if with_neighbor:
            assert summary["completed"] and summary["ever_track"] and summary["route_quality_valid"]
            assert sum(true_errors) / len(true_errors) > 1. and max(true_errors) > 2.
        else:
            assert not summary["completed"] and not summary["ever_track"]
            assert "side_hint_observation_inconsistent" in summary["last_lateral_reason_codes"]
            assert float(rows[-1]["thrust_percent"]) == 0. and int(rows[-1]["rpm"]) == 0
        cases.append({
            "case": name,
            "summary_source": str(summary_file.relative_to(ROOT)),
            "csv_source": str(csv_file.relative_to(ROOT)),
            "summary_sha256": digest(summary_file),
            "csv_sha256": digest(csv_file),
            "duration_s": summary["duration_s"],
            "completed": summary["completed"],
            "ever_track": summary["ever_track"],
            "magnetic_center_m": summary["last_fwhm_center_m"],
            "lateral_valid": summary["lateral_valid"],
            "last_lateral_reason_codes": summary["last_lateral_reason_codes"],
            "online_track_mae_m": summary["route_observed_lateral_mae_m"],
            "target_true_track_mae_m": sum(true_errors) / len(true_errors) if true_errors else None,
            "target_true_track_max_m": max(true_errors) if true_errors else None,
            "target_true_track_samples": len(true_errors),
            "depth_published": summary["depth_published"],
            "final_pid_thrust_percent": float(rows[-1]["thrust_percent"]),
            "final_udp_rpm": int(rows[-1]["rpm"]),
        })
    result = {
        "role": "native_pvs_ros_pid_guard_udp_static_hint_bias_counterexample",
        "source_script_sha256": digest(Path(__file__)),
        "harness_sha256": digest(ROOT / "tools/smoke_v2_flythrough_ros_pvs.py"),
        "biased_config_source": str(configuration.relative_to(ROOT)),
        "biased_config_sha256": digest(configuration),
        "hint_m": [6.6, 7.5],
        "target_y_m": 6.,
        "neighbor_y_m": 9.,
        "neighbor_gain_nt": 10.,
        "seed": 101,
        "caveat": "Synthetic scalar-envelope superposition and native PVS; no physical target, sonar, or PC104 input.",
        "cases": cases,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({c["case"]: {"completed": c["completed"],
                                   "magnetic_center_m": c["magnetic_center_m"],
                                   "target_true_track_mae_m": c["target_true_track_mae_m"]}
                      for c in cases}, ensure_ascii=False))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Archive the installed-ROS near-neighbor target corridor causal experiment."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
import statistics

import yaml


ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "AUV-Master-Mag/results/v2/inspection_target_exclusive_corridor_20260927"
OLD_CONFIG = ROOT / "AUV-Master-Mag/results/v2/inspection_joint_wrong_target_20260927/sonar_with_independent_anchor_sim.yaml"
NEW_CONFIG = RESULTS / "sonar_with_exclusive_corridor_sim.yaml"
OUTPUT = ROOT / "AUV-Master-Mag/docs/v2/publication/fwhm_v2_experiment_results/data/58_target_exclusive_corridor_ros_pvs_audit.json"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(name: str) -> dict:
    directory = RESULTS / name
    summary_path = directory / "wire_seed_101_summary.json"
    csv_path = directory / "wire_seed_101.csv"
    log_path = RESULTS / f"{name}.log"
    summary = json.loads(summary_path.read_text())
    with csv_path.open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    decision = next(row for row in rows if row["mode"] in {"track", "hold"})
    true_errors = [abs(float(row["y_m"]) - 6.) for row in rows
                   if row["mode"] == "track" and float(row["x_m"]) >= 0.]
    installed = Path(summary["v2_node_loaded_path"])
    assert summary["installed_v2_node_mode"] and "/install/" in str(installed)
    assert digest(installed) == digest(ROOT / "brain_linux/src/auv_cable_tracking_v2/auv_cable_tracking_v2/cable_tracking_v2_node.py")
    return {
        "case": name,
        "summary_path": str(summary_path.relative_to(ROOT)),
        "summary_sha256": digest(summary_path),
        "csv_path": str(csv_path.relative_to(ROOT)),
        "csv_sha256": digest(csv_path),
        "log_path": str(log_path.relative_to(ROOT)),
        "log_sha256": digest(log_path),
        "installed_node_path": str(installed),
        "installed_node_sha256": digest(installed),
        "completed": summary["completed"],
        "ever_track": summary["ever_track"],
        "duration_s": summary["duration_s"],
        "magnetic_center_m": summary["last_fwhm_center_m"],
        "lateral_reason_codes": summary["last_lateral_reason_codes"],
        "target_magnetic_gain_nt": summary["primary_cable_gain_nt"],
        "neighbor_magnetic_gain_nt": summary["secondary_cable_gain_nt"],
        "neighbor_lateral_m": summary["secondary_cable_lateral_m"],
        "confirm_sonar_center_m": float(decision["runtime_identity_center_m"]),
        "confirm_sonar_half_width_m": float(decision["runtime_identity_half_width_m"]),
        "confirm_mode": decision["mode"],
        "target_true_track_mae_m": statistics.mean(true_errors) if true_errors else None,
        "target_true_track_max_m": max(true_errors) if true_errors else None,
        "target_true_track_samples": len(true_errors),
        "depth_published": summary["depth_published"],
        "final_target_speed_mps": float(rows[-1]["target_speed_mps"]),
        "final_pid_thrust_percent": float(rows[-1]["thrust_percent"]),
        "final_udp_rpm": int(rows[-1]["rpm"]),
    }


def main() -> None:
    old_config = yaml.safe_load(OLD_CONFIG.read_text())
    new_config = yaml.safe_load(NEW_CONFIG.read_text())
    new_fly = new_config["cable_tracking"]["v2"]["flythrough"]
    assert (new_fly.pop("runtime_target_exclusive_min_m"),
            new_fly.pop("runtime_target_exclusive_max_m")) == (5.45, 6.55)
    assert old_config == new_config, "causal configs differ beyond the corridor interval"

    cases = {name: load(name) for name in (
        "old_anchor_near_neighbor", "new_corridor_near_neighbor",
        "new_corridor_true_target")}
    old, rejected, correct = cases.values()
    assert old["target_magnetic_gain_nt"] == rejected["target_magnetic_gain_nt"] == 0.
    assert old["neighbor_magnetic_gain_nt"] == rejected["neighbor_magnetic_gain_nt"] == 20.
    assert old["neighbor_lateral_m"] == rejected["neighbor_lateral_m"] == 6.6
    assert old["completed"] and old["ever_track"]
    assert not rejected["completed"] and not rejected["ever_track"]
    assert "runtime_target_exclusive_corridor_inconsistent" in rejected["lateral_reason_codes"]
    assert rejected["final_target_speed_mps"] == rejected["final_pid_thrust_percent"] == rejected["final_udp_rpm"] == 0.
    assert correct["completed"] and correct["ever_track"]
    assert correct["target_magnetic_gain_nt"] == 20. and correct["neighbor_magnetic_gain_nt"] == 0.
    assert all(not case["depth_published"] for case in cases.values())
    assert abs(old["magnetic_center_m"] - rejected["magnetic_center_m"]) < 1e-9
    assert abs(old["confirm_sonar_half_width_m"] - rejected["confirm_sonar_half_width_m"]) < 1e-9
    assert old["confirm_sonar_center_m"] == rejected["confirm_sonar_center_m"] == 6.6
    assert old["confirm_sonar_center_m"] - old["confirm_sonar_half_width_m"] <= 6.2
    assert rejected["confirm_sonar_center_m"] + rejected["confirm_sonar_half_width_m"] > 6.55
    assert 5.45 <= correct["confirm_sonar_center_m"] - correct["confirm_sonar_half_width_m"]
    assert correct["confirm_sonar_center_m"] + correct["confirm_sonar_half_width_m"] <= 6.55

    payload = {
        "role": "installed_ros_near_neighbor_exclusive_target_corridor_causal_experiment",
        "scope": "three separate seed-101 ROS/PID/guard/localhost-UDP/native-PVS runs; synthetic magnetic/sonar/corridor; target magnetic gain zero only in wrong-line groups; not physical target association or success probability",
        "target_lateral_m": 6.,
        "neighbor_lateral_m": 6.6,
        "target_anchor_m": [5.8, 6.2],
        "exclusive_corridor_m": [5.45, 6.55],
        "cases": cases,
        "source_script_sha256": digest(Path(__file__)),
        "harness_sha256": digest(ROOT / "tools/smoke_v2_flythrough_ros_pvs.py"),
        "flythrough_sha256": digest(ROOT / "AUV-Master-Mag/src/auv_mag_tracking/v2/flythrough.py"),
        "ros_node_sha256": digest(ROOT / "brain_linux/src/auv_cable_tracking_v2/auv_cable_tracking_v2/cable_tracking_v2_node.py"),
        "anchor_validator_sha256": digest(ROOT / "brain_linux/src/auv_cable_tracking_v2/auv_cable_tracking_v2/runtime_target_anchor.py"),
        "old_config_sha256": digest(OLD_CONFIG),
        "new_config_sha256": digest(NEW_CONFIG),
    }
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({name: {"completed": case["completed"],
                             "reason_codes": case["lateral_reason_codes"],
                             "true_track_mae_m": case["target_true_track_mae_m"]}
                      for name, case in cases.items()}, ensure_ascii=False))


if __name__ == "__main__":
    main()

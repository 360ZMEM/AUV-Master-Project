#!/usr/bin/env python3
"""Audit the two isolated native-PVS runs for the opt-in wide corridor."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "AUV-Master-Mag/results/v2/route_hold_admission"
OUT = ROOT / "AUV-Master-Mag/docs/v2/publication/fwhm_v2_experiment_results/data"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_case(name: str, case: str = "wire"):
    directory = RUN / name
    csv_path = directory / f"{case}_seed_101.csv"
    summary_path = directory / f"{case}_seed_101_summary.json"
    with csv_path.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert rows and len(rows) == summary["ticks"]
    return rows, summary, {"csv": str(csv_path.relative_to(ROOT)), "csv_sha256": sha(csv_path),
                           "summary": str(summary_path.relative_to(ROOT)),
                           "summary_sha256": sha(summary_path)}


def main() -> None:
    normal_rows, normal, normal_files = read_case("normal")
    fault_rows, fault, fault_files = read_case("fault")
    _, guard_loss, guard_loss_files = read_case("guard_loss", "wire_guard_telemetry_loss")
    assert normal["completed"] and normal["ever_track"] and not normal["depth_published"]
    assert not normal["recovery_status_observed"]
    assert normal["bridge_and_guard_connected"] and normal["protocol_encoded"]
    assert not fault["completed"] and fault["ever_track"] and not fault["depth_published"]
    assert fault["first_hold_reason"] == "flythrough_runtime_identity_diverged"
    assert fault["mission_retransmission_rejections"] == 2
    assert fault["post_hold_nonzero_rpm_ticks"] == 0
    held = [row for row in fault_rows if row["mode"] == "hold"]
    assert len(held) == 41 and all(int(row["rpm"]) == 0 for row in held)
    assert all(row["hold_budget_state"] == "WITHIN_BUDGET" for row in held)
    assert min(float(row["hold_budget_remaining_m"]) for row in held) > 0
    assert all(row["arbiter_source"] == "SAFETY_FALLBACK" for row in held)
    assert not guard_loss["completed"] and not guard_loss["depth_published"]
    guard_ticks = guard_loss["guard_telemetry_loss_ticks"]
    assert guard_ticks == 241
    assert guard_loss["guard_telemetry_loss_zero_pid_ticks"] == guard_ticks
    assert guard_loss["guard_telemetry_loss_zero_udp_ticks"] == guard_ticks
    payload = {
        "role": "synthetic_route_hold_admission_ros_pid_bridge_udp_native_pvs",
        "normal": {"completed": normal["completed"], "duration_s": normal["duration_s"],
                   "depth_published": normal["depth_published"],
                   "recovery_status_observed": normal["recovery_status_observed"],
                   "route_observed_lateral_mae_m": normal["route_observed_lateral_mae_m"],
                   "files": normal_files},
        "identity_switch": {"first_hold_s": fault["first_hold_s"],
                            "first_hold_reason": fault["first_hold_reason"],
                            "hold_ticks": len(held), "post_hold_nonzero_rpm_ticks": 0,
                            "minimum_hold_remaining_budget_m": min(
                                float(row["hold_budget_remaining_m"]) for row in held),
                            "mission_retransmission_rejections": 2,
                            "hold_to_final_displacement_m": fault["hold_to_final_displacement_m"],
                            "final_ground_speed_mps": fault["final_ground_speed_mps"],
                            "files": fault_files},
        "guard_telemetry_loss": {"duration_s": guard_loss["duration_s"],
                                 "affected_ticks": guard_ticks,
                                 "zero_pid_ticks": guard_ticks,
                                 "zero_udp_ticks": guard_ticks,
                                 "files": guard_loss_files},
        "caveat": "Synthetic sonar and PVS; no physical stop/current envelope or PC104 recovery acceptance.",
    }
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / "35_route_hold_admission_runs.json"
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

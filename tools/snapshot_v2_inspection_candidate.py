#!/usr/bin/env python3
"""Pin the reviewable v2 inspection candidate without claiming field release."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "AUV-Master-Mag/docs/v2/publication/fwhm_v2_experiment_results/data"
FILES = (
    "AUV-Master-Mag/src/auv_mag_tracking/v2/flythrough.py",
    "brain_linux/src/auv_cable_tracking_v2/auv_cable_tracking_v2/identity_cue.py",
    "brain_linux/src/auv_cable_tracking_v2/auv_cable_tracking_v2/field_identity_calibration.py",
    "brain_linux/src/auv_cable_tracking_v2/auv_cable_tracking_v2/cable_tracking_v2_node.py",
    "brain_linux/src/auv_cable_tracking_v2/launch/flythrough_nodes.launch.py",
    "brain_linux/src/auv_cable_tracking_v2/config/cable_tracking_v2_flythrough_sonar_identity_sim.yaml",
    "tools/smoke_v2_flythrough_ros_pvs.py",
    "tools/plot_v2_identity_continuity.py",
)
EVIDENCE = (
    "30_runtime_identity_continuity_summary.json",
    "30_runtime_identity_continuity_manifest.json",
    "30_identity_continuity_three_seed_audit.json",
    "field_sonar_evidence_inventory.json",
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    repeats = json.loads((DATA / EVIDENCE[2]).read_text(encoding="utf-8"))
    inventory = json.loads((DATA / EVIDENCE[3]).read_text(encoding="utf-8"))
    if not repeats["all_passed_synthetic_envelope"] or len(repeats["cases"]) != 12:
        raise SystemExit("three-seed synthetic audit is not complete")
    field_ready = (
        inventory["cable_sonar_observation_messages"] > 0
        and inventory["sonar_quality_messages"] > 0
        and inventory["physically_approved_sonar_calibrations"] > 0
    )
    payload = {
        "candidate": "inspection_v2_identity_continuity_with_field_calibration_preflight",
        "release_level": "synthetic_software_candidate",
        "field_identity_input_evidence_present": field_ready,
        "field_release_authorized": False,
        "scope": "ROS/PID/guard/local UDP/native PVS with synthetic magnetic and sonar input; no physical sonar, field cable or PC104 actuation.",
        "source_sha256": {path: digest(ROOT / path) for path in FILES},
        "evidence_sha256": {
            str((DATA / name).relative_to(ROOT)): digest(DATA / name) for name in EVIDENCE
        },
        "remaining_field_gates": [
            "physical cable-sonar observation and quality records with acquisition timestamps",
            "held-out physical probability and geometric calibration with target association",
            "parallel-cable and false-line refusal audit",
            "measured AUV turn/stop envelope and PC104 command-to-motion audit",
            "independent magnetic width-to-distance and altitude calibration before burial release",
        ],
        "snapshot_script_sha256": digest(Path(__file__)),
    }
    path = DATA / "inspection_v2_candidate_snapshot_20260927.json"
    if path.exists():
        pinned = json.loads(path.read_text(encoding="utf-8"))
        changed_sources = [name for name, digest_value in payload["source_sha256"].items()
                           if pinned.get("source_sha256", {}).get(name) != digest_value]
        changed_evidence = [name for name, digest_value in payload["evidence_sha256"].items()
                            if pinned.get("evidence_sha256", {}).get(name) != digest_value]
        if changed_sources or changed_evidence:
            print(json.dumps({"pinned_snapshot_changed": True,
                              "changed_sources": changed_sources,
                              "changed_evidence": changed_evidence}, ensure_ascii=False))
            raise SystemExit(1)
        print(json.dumps({"pinned_snapshot_changed": False,
                          "candidate": pinned["candidate"]}, ensure_ascii=False))
        return
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"candidate": payload["candidate"],
                      "software_file_count": len(FILES),
                      "field_release_authorized": payload["field_release_authorized"]},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()

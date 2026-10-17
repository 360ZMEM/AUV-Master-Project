#!/usr/bin/env python3
"""Inventory recorded cable-sonar input and approved quality calibration evidence."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / ("AUV-Master-Mag/docs/v2/publication/"
              "fwhm_v2_experiment_results/data/field_sonar_evidence_inventory.json")
RELEVANT = ("/auv/sensors/cable_sonar_observation", "/auv/perception/quality/sonar")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    bags = []
    for directory in (".auv_data/bags", "log", "results"):
        for path in (ROOT / directory).rglob("metadata.yaml"):
            try:
                payload = yaml.safe_load(path.read_text(encoding="utf-8"))
                info = payload["rosbag2_bagfile_information"]
                topics = {item["topic_metadata"]["name"]: int(item["message_count"])
                          for item in info.get("topics_with_message_count", [])}
            except (OSError, KeyError, TypeError, ValueError, yaml.YAMLError):
                continue
            bags.append({
                "metadata": str(path.relative_to(ROOT)),
                "metadata_sha256": digest(path),
                "cable_sonar_observation_count": topics.get(RELEVANT[0], 0),
                "sonar_quality_count": topics.get(RELEVANT[1], 0),
                "other_nonzero_sonar_topics": {
                    name: count for name, count in topics.items()
                    if "sonar" in name.lower() and name not in RELEVANT and count > 0
                },
            })
    bags.sort(key=lambda item: item["metadata"])
    calibrations = []
    for path in (ROOT / "brain_linux/config").glob("*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if ("calibration_id" not in payload or "track" not in payload
                or "sonar" not in (path.name + str(payload["calibration_id"])).lower()):
            continue
        calibrations.append({
            "path": str(path.relative_to(ROOT)),
            "sha256": digest(path),
            "calibration_id": payload.get("calibration_id"),
            "domain": payload.get("calibration_domain"),
            "deployment_approved": payload.get("deployment_approved"),
            "physical_deployment_approved": payload.get("physical_deployment_approved"),
        })
    calibrations.sort(key=lambda item: item["path"])
    report = {
        "scope": "Local ROS bag metadata under .auv_data/bags, log, results; quality-calibration JSON under brain_linux/config.",
        "metadata_files_inspected": len(bags),
        "cable_sonar_observation_messages": sum(
            item["cable_sonar_observation_count"] for item in bags),
        "sonar_quality_messages": sum(item["sonar_quality_count"] for item in bags),
        "physically_approved_sonar_calibrations": sum(
            item["domain"] == "physical"
            and item["deployment_approved"] is True
            and item["physical_deployment_approved"] is True
            for item in calibrations),
        "bags": bags,
        "calibrations": calibrations,
        "audit_script_sha256": digest(Path(__file__)),
    }
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in (
        "metadata_files_inspected", "cable_sonar_observation_messages",
        "sonar_quality_messages", "physically_approved_sonar_calibrations")},
        ensure_ascii=False))


if __name__ == "__main__":
    main()

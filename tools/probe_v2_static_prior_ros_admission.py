#!/usr/bin/env python3
"""Exercise the installed v2 node's non-sim static-prior DDS admission gate.

All review files are synthetic fixtures. No navigation, sonar, PC104, or
vehicle motion is supplied; this probe cannot authorize a field mission.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "AUV-Master-Mag/src")]

import rclpy
from rclpy.executors import SingleThreadedExecutor
from rclpy.node import Node
from std_msgs.msg import String
import yaml

import auv_cable_tracking_v2.cable_tracking_v2_node as node_module
import auv_cable_tracking_v2.static_target_prior as prior_module
from auv_cable_tracking_v2.cable_tracking_v2_node import CableTrackingV2Node
from auv_cable_tracking_v2.static_target_prior import (
    mission_config_sha256, prior_points_sha256,
)


SOURCE_CONFIG = (ROOT / "brain_linux/src/auv_cable_tracking_v2/config/"
                 "cable_tracking_v2_flythrough_narrow_cue.yaml")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def wait_for(executor: SingleThreadedExecutor, predicate, *, timeout_s: float = 5.) -> None:
    deadline = time.monotonic() + timeout_s
    while not predicate():
        if time.monotonic() >= deadline:
            raise AssertionError("DDS admission observation timed out")
        executor.spin_once(timeout_sec=.02)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT /
                        "AUV-Master-Mag/results/v2/static_target_prior_ros_admission_20260927")
    args = parser.parse_args()
    if os.environ.get("ROS_LOCALHOST_ONLY") != "1" or not os.environ.get("ROS_DOMAIN_ID"):
        raise RuntimeError("set ROS_LOCALHOST_ONLY=1 and an isolated ROS_DOMAIN_ID")
    installed_package = (ROOT / "brain_linux/install/auv_cable_tracking_v2/lib/"
                         "python3.10/site-packages/auv_cable_tracking_v2")
    assert Path(node_module.__file__).resolve() == installed_package / "cable_tracking_v2_node.py"
    assert Path(prior_module.__file__).resolve() == installed_package / "static_target_prior.py"
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)

    config = yaml.safe_load(SOURCE_CONFIG.read_text(encoding="utf-8"))
    mission = config["cable_tracking"]
    mission["v2"]["flythrough"]["side_hint_source"] = "survey_map"
    source_path = out / "synthetic_target_line.json"
    source_path.write_text(json.dumps({
        "fixture_only": True, "target_id": "synthetic_cable_A",
        "points_xy_m": [[0., 6.], [80., 6.]],
    }, sort_keys=True) + "\n", encoding="utf-8")
    now = datetime.now(timezone.utc)
    review = {
        "schema_version": 2, "source_kind": "survey_map",
        "mission_id": "synthetic_dds_trial", "target_id": "synthetic_cable_A",
        "reviewer": "software_fixture_only", "reviewed_for_mission": True,
        "reviewed_at_utc": (now - timedelta(minutes=1)).isoformat(),
        "valid_until_utc": (now + timedelta(hours=1)).isoformat(),
        "frame": mission["prior"]["frame"],
        "prior_points_sha256": prior_points_sha256(mission["prior"]),
        "mission_config_sha256": mission_config_sha256(mission),
        "side_hint_min_m": mission["v2"]["flythrough"]["side_hint_min_m"],
        "side_hint_max_m": mission["v2"]["flythrough"]["side_hint_max_m"],
        "source_file": str(source_path), "source_sha256": sha(source_path),
    }
    review_path = out / "synthetic_review_schema_v2.json"
    review_path.write_text(json.dumps(review, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    mission["v2"]["static_target_prior"] = {
        "evidence_file": str(review_path), "evidence_sha256": sha(review_path),
    }
    config_path = out / "static_trial.yaml"
    config_path.write_text(yaml.safe_dump(config, allow_unicode=True), encoding="utf-8")

    rclpy.init(args=["--ros-args", "-p", f"config_file:={config_path}",
                     "-p", "use_sim_time:=false"])
    decision = None
    peer = None
    try:
        decision = CableTrackingV2Node()
        assert decision._static_target_prior_evidence is not None
        assert decision.get_parameter("use_sim_time").value is False
        peer = Node("static_prior_dds_admission_probe")
        executor = SingleThreadedExecutor()
        executor.add_node(decision)
        executor.add_node(peer)
        statuses: list[str] = []
        peer.create_subscription(String, "/auv/cable/inspection_status",
                                 lambda msg: statuses.append(msg.data), 10)
        publisher = peer.create_publisher(String, "/auv/cable/mission_command", 10)
        wait_for(executor, lambda: publisher.get_subscription_count() > 0)
        command = {
            "mission_type": "CABLE_INSPECTION",
            "mission_id": review["mission_id"], "target_id": review["target_id"],
            "target_depth": mission["control"]["default_depth_m"],
            "target_speed_mps": mission["control"]["default_speed_mps"],
        }
        bad = {**command, "target_speed_mps": .2}
        publisher.publish(String(data=json.dumps(bad)))
        wait_for(executor, lambda: "STATIC_TARGET_PRIOR_COMMAND_MISMATCH" in statuses)
        assert decision.latest_mission is None
        wrong_statuses = list(statuses)
        publisher.publish(String(data=json.dumps(command)))
        wait_for(executor, lambda: decision.latest_mission is not None)
        assert not decision._hold_budget.recovery_required
        matched_accepted = True
    finally:
        if peer is not None:
            peer.destroy_node()
        if decision is not None:
            decision.destroy_node()
        rclpy.shutdown()

    changed = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    changed["cable_tracking"]["v2"]["search_boundary_xy_m"][0][0] += 1.
    changed_path = out / "static_trial_changed_boundary.yaml"
    changed_path.write_text(yaml.safe_dump(changed, allow_unicode=True), encoding="utf-8")
    rclpy.init(args=["--ros-args", "-p", f"config_file:={changed_path}",
                     "-p", "use_sim_time:=false"])
    rejected_reason = None
    try:
        unexpectedly_created = None
        try:
            unexpectedly_created = CableTrackingV2Node()
        except ValueError as exc:
            rejected_reason = str(exc)
        finally:
            if unexpectedly_created is not None:
                unexpectedly_created.destroy_node()
        assert rejected_reason is not None and "mission config hash mismatch" in rejected_reason
    finally:
        rclpy.shutdown()

    source_paths = [
        Path(__file__),
        ROOT / "brain_linux/install/auv_cable_tracking_v2/lib/python3.10/site-packages/"
               "auv_cable_tracking_v2/cable_tracking_v2_node.py",
        ROOT / "brain_linux/install/auv_cable_tracking_v2/lib/python3.10/site-packages/"
               "auv_cable_tracking_v2/static_target_prior.py",
    ]
    summary = {
        "evidence_level": "non_sim_wall_clock_ros_dds_synthetic_static_review_no_navigation_or_vehicle",
        "ros_domain_id": os.environ["ROS_DOMAIN_ID"],
        "use_sim_time": False,
        "ros_package_loaded_from_install": True,
        "bad_speed_rejected_via_dds": "STATIC_TARGET_PRIOR_COMMAND_MISMATCH" in wrong_statuses,
        "matching_mission_accepted_via_dds": matched_accepted,
        "changed_boundary_rejected_at_node_start": rejected_reason,
        "physical_target_connected": False,
        "navigation_connected": False,
        "controller_or_pc104_connected": False,
        "field_release_authorized": False,
        "file_sha256": {str(path.relative_to(ROOT)) if path.is_relative_to(ROOT)
                        else str(path): sha(path)
                        for path in [source_path, review_path, config_path, changed_path,
                                     *source_paths]},
    }
    path = out / "summary.json"
    path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")
    print(path)


if __name__ == "__main__":
    main()

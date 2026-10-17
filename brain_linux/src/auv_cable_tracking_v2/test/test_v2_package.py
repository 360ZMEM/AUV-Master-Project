from __future__ import annotations

from pathlib import Path
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import yaml


PACKAGE_ROOT = Path(__file__).resolve().parents[1]


class V2RosPackageTests(unittest.TestCase):
    def test_flythrough_sim_hold_counts_plant_time_with_wall_fallback(self) -> None:
        from auv_cable_tracking_v2.cable_tracking_v2_node import CableTrackingV2Node
        import rclpy

        config = PACKAGE_ROOT / "config" / "cable_tracking_v2_flythrough_sonar_identity_corridor_budget_sim.yaml"
        rclpy.init(args=["--ros-args", "-p", f"config_file:={config}",
                         "-p", "use_sim_time:=true"])
        try:
            node = CableTrackingV2Node()
            try:
                with patch.object(node._hold_budget, "evaluate", return_value={}) as evaluate:
                    node._hold_budget_snapshot("hold")
                kwargs = evaluate.call_args.kwargs
                self.assertEqual(kwargs["now_s"], node.get_clock().now().nanoseconds * 1e-9)
                self.assertIsInstance(kwargs["fallback_now_s"], float)
                self.assertTrue(kwargs["hold"])
            finally:
                node.destroy_node()
        finally:
            rclpy.shutdown()

    def test_non_sim_inspection_rejects_uncalibrated_depth_override(self) -> None:
        from auv_cable_tracking_v2.cable_tracking_v2_node import CableTrackingV2Node
        import rclpy
        import tempfile

        fixture = yaml.safe_load((PACKAGE_ROOT / "config" /
            "cable_tracking_v2_inspection.yaml").read_text())
        fixture["cable_tracking"]["v2"]["inspection"]["allow_uncalibrated_depth"] = True
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "unsafe_depth.yaml"
            path.write_text(yaml.safe_dump(fixture))
            rclpy.init(args=["--ros-args", "-p", f"config_file:={path}"])
            try:
                with self.assertRaisesRegex(ValueError, "uncalibrated FWHM depth"):
                    CableTrackingV2Node()
            finally:
                rclpy.shutdown()

    def test_route_hold_admission_rejects_narrow_corridor_and_monitors_wide_one(self) -> None:
        from auv_cable_tracking_v2.cable_tracking_v2_node import CableTrackingV2Node
        from nav_msgs.msg import Odometry
        from std_msgs.msg import String
        import json
        import rclpy
        import tempfile
        import time

        command = String(data=json.dumps({"mission_type": "CABLE_INSPECTION",
            "target_depth": 10., "target_speed_mps": .3}))
        narrow = yaml.safe_load((PACKAGE_ROOT / "config" /
            "cable_tracking_v2_flythrough_sonar_identity_sim.yaml").read_text())
        narrow["cable_tracking"]["v2"]["route_hold_admission"] = {
            "enabled": True, "route_deviation_bound_m": 2.0}
        with tempfile.TemporaryDirectory() as directory:
            narrow_path = Path(directory) / "narrow.yaml"
            narrow_path.write_text(yaml.safe_dump(narrow))
            wide_path = PACKAGE_ROOT / "config" / "cable_tracking_v2_flythrough_sonar_identity_corridor_budget_sim.yaml"
            for filename, admitted in ((narrow_path, False), (wide_path, True)):
                rclpy.init(args=["--ros-args", "-p", f"config_file:={filename}",
                                 "-p", "use_sim_time:=true"])
                try:
                    node = CableTrackingV2Node()
                    try:
                        node._on_mission_command(String(data=json.dumps({"mission_type": "SURVEY"})))
                        self.assertFalse(node._hold_budget.recovery_required)
                        self.assertIsNone(node.latest_mission)
                        node._on_mission_command(command)
                        self.assertEqual(node.latest_mission is not None, admitted)
                        self.assertEqual(node._route_hold_admission_result["admitted"], admitted)
                        if admitted:
                            odom = Odometry()
                            odom.pose.pose.position.x = -100.
                            odom.pose.pose.position.y = 15.
                            node.latest_odom = odom
                            node.latest_odom_wall_time_s = time.monotonic()
                            node._latest_nav_uncertainty = (.2, 1., .01)
                            node._latest_nav_uncertainty_wall_time_s = time.monotonic()
                            self.assertEqual(node._hold_budget_snapshot("track")["state"], "MOTION_BUDGET_OK")
                            odom.pose.pose.position.y = 23.
                            self.assertEqual(node._hold_budget_snapshot("track")["reason"],
                                             "motion_hold_budget_insufficient")
                            self.assertTrue(node._hold_budget.recovery_required)
                            import numpy as np
                            node.pipeline.core._last_navigation = SimpleNamespace(
                                position_ned_m=np.array([-100., 23., -10.]), heading_deg=0.)
                            published = []
                            original_publisher = node.pub_setpoint
                            node.pub_setpoint = SimpleNamespace(publish=published.append)
                            try:
                                tracking = SimpleNamespace(mode="track", estimated_cable_xy_m=np.array([0., 0.]))
                                guidance = SimpleNamespace(safe_lock_active=False, target_depth_m=10.,
                                                           desired_heading_deg=0., speed_mps=.3,
                                                           guidance_source="test")
                                limited = SimpleNamespace(desired_heading_deg=0., speed_mps=.3)
                                node._publish_setpoint(tracking, guidance, limited, 10.)
                                self.assertEqual(published[-1].target_speed_mps, 0.)
                                self.assertFalse(published[-1].track_cable)
                            finally:
                                node.pub_setpoint = original_publisher
                        else:
                            self.assertEqual(node._hold_budget.reason, "route_hold_budget_insufficient")
                    finally:
                        node.destroy_node()
                finally:
                    rclpy.shutdown()

    def test_config_disables_legacy_probe_and_declares_pvs_model(self) -> None:
        payload = yaml.safe_load(
            (PACKAGE_ROOT / "config" / "cable_tracking_v2.yaml").read_text(encoding="utf-8")
        )["cable_tracking"]
        self.assertFalse(payload["zigzag_probe"]["enabled"])
        self.assertEqual(payload["v2"]["fwhm"]["shape_model"], "legacy_segment")
        self.assertAlmostEqual(payload["v2"]["fwhm"]["shape_factor"], 0.47203575)
        self.assertGreaterEqual(max(payload["v2"]["cross_scan"]["half_span_levels_m"]), 20.0)
        self.assertTrue(payload["v2"]["tracking"]["stop_at_endpoint"])

    def test_console_entry_module_imports(self) -> None:
        from auv_cable_tracking_v2.cable_tracking_v2_node import CableTrackingV2Node

        self.assertEqual(CableTrackingV2Node.__name__, "CableTrackingV2Node")

    def test_budget_alarm_latches_zero_setpoint_and_acceptance_rejection(self) -> None:
        from auv_cable_tracking_v2.cable_tracking_v2_node import CableTrackingV2Node
        import numpy as np
        import rclpy

        filename = PACKAGE_ROOT / "config" / "cable_tracking_v2_inspection.yaml"
        rclpy.init(args=["--ros-args", "-p", f"config_file:={filename}"])
        try:
            node = CableTrackingV2Node()
            try:
                node.pipeline.core._last_navigation = SimpleNamespace(
                    position_ned_m=np.array([0., 0., -10.]), heading_deg=0.)
                from std_msgs.msg import String
                import json
                command = {"mission_type": "CABLE_INSPECTION", "target_depth": 10.,
                           "target_speed_mps": .3, "source": "cable_mission_autostart_node"}
                node._on_mission_command(String(data=json.dumps(command)))
                accepted = node.latest_mission
                self.assertIsNotNone(accepted)
                node._hold_budget.evaluate(hold=True, now_s=1.)
                self.assertTrue(node._hold_budget.recovery_required)
                node._on_mission_command(String(data=json.dumps(command)))
                self.assertIs(node.latest_mission, accepted)
                self.assertTrue(node._hold_budget.recovery_required)
                command["target_speed_mps"] = .2
                node._on_mission_command(String(data=json.dumps(command)))
                self.assertIs(node.latest_mission, accepted)
                self.assertTrue(node._hold_budget.recovery_required)
                published = []
                original_publisher = node.pub_setpoint
                node.pub_setpoint = SimpleNamespace(publish=published.append)
                try:
                    tracking = SimpleNamespace(estimated_cable_xy_m=np.array([0., 0.]),
                                               cross_track_m=0., confidence=1., burial_sigma_m=0.)
                    guidance = SimpleNamespace(safe_lock_active=False, target_depth_m=10.,
                                               desired_heading_deg=0., speed_mps=.3,
                                               guidance_source="v2_test")
                    limited = SimpleNamespace(desired_heading_deg=0., speed_mps=.3)
                    node._publish_setpoint(tracking, guidance, limited, 10.)
                    self.assertEqual(len(published), 1)
                    self.assertEqual(published[0].mode, "CABLE_TRACKING_DEGRADED_HOLD")
                    self.assertEqual(published[0].target_speed_mps, 0.)
                    self.assertFalse(published[0].track_cable)
                    self.assertIn("hold_budget_recovery_required", node._acceptance_flags(tracking))
                finally:
                    node.pub_setpoint = original_publisher
            finally:
                node.destroy_node()
        finally:
            rclpy.shutdown()

    def test_es_ekf_covariance_contract_for_field_navigation(self) -> None:
        import math
        import numpy as np
        from auv_cable_tracking_v2.cable_tracking_v2_node import _navigation_uncertainty_from_covariance

        covariance = np.eye(15) * .01
        covariance[0, 0], covariance[1, 1] = .04, .09
        covariance[3, 3], covariance[4, 4] = .0001, .0004
        covariance[8, 8] = math.radians(1.) ** 2
        result = _navigation_uncertainty_from_covariance(covariance.reshape(-1))
        self.assertIsNotNone(result)
        for measured, expected in zip(result, (.3, 1., .02)):
            self.assertAlmostEqual(measured, expected)
        self.assertIsNone(_navigation_uncertainty_from_covariance(np.zeros(225)))
        self.assertIsNone(_navigation_uncertainty_from_covariance([float("nan")] * 225))

    def test_imu_heading_covariance_must_match_navigation_pose(self) -> None:
        import math
        from nav_msgs.msg import Odometry
        from sensor_msgs.msg import Imu
        from auv_cable_tracking_v2.cable_tracking_v2_node import _matched_imu_heading_sigma_deg

        imu = Imu()
        imu.header.stamp.sec = 100
        imu.orientation.w = math.cos(math.radians(5.))
        imu.orientation.z = math.sin(math.radians(5.))
        imu.orientation_covariance = [.0001, 0., 0., 0., .0001, 0., 0., 0., .0001]
        odom = Odometry()
        odom.header.stamp.sec = 100
        odom.pose.pose.orientation.w = imu.orientation.w
        odom.pose.pose.orientation.z = imu.orientation.z
        check = lambda: _matched_imu_heading_sigma_deg(
            imu, odom, receipt_age_s=.1, maximum_age_s=1.5)
        self.assertAlmostEqual(check(), math.degrees(.01))
        self.assertIsNone(_matched_imu_heading_sigma_deg(
            imu, odom, receipt_age_s=2., maximum_age_s=1.5))
        odom.header.stamp.sec = 101
        self.assertIsNone(check())
        odom.header.stamp.sec = 100
        odom.pose.pose.orientation.w = 1.
        odom.pose.pose.orientation.z = 0.
        self.assertIsNone(check())
        odom.pose.pose.orientation.w = imu.orientation.w
        odom.pose.pose.orientation.z = imu.orientation.z
        imu.orientation_covariance = [0.] * 9
        self.assertIsNone(check())
        imu.orientation_covariance[0] = -1.
        self.assertIsNone(check())

    def test_flythrough_config_is_explicit_and_instantiates_only_when_selected(self) -> None:
        from auv_mag_tracking.v2 import FlythroughInspectionPipelineV2
        from auv_cable_tracking_v2.cable_tracking_v2_node import CableTrackingV2Node
        import rclpy

        filename = PACKAGE_ROOT / "config" / "cable_tracking_v2_flythrough.yaml"
        payload = yaml.safe_load(filename.read_text(encoding="utf-8"))["cable_tracking"]
        self.assertEqual(payload["v2"]["mission_geometry"], "flythrough")
        self.assertEqual(payload["v2"]["navigation_ground_velocity_frame"], "world_ned")
        self.assertFalse(payload["v2"]["inspection"]["allow_uncalibrated_depth"])
        self.assertFalse(payload["zigzag_probe"]["enabled"])
        ordinary = yaml.safe_load((PACKAGE_ROOT / "config" / "cable_tracking_v2_inspection.yaml").read_text())["cable_tracking"]
        self.assertNotIn("mission_geometry", ordinary["v2"])
        rclpy.init(args=["--ros-args", "-p", f"config_file:={filename}"])
        try:
            node = CableTrackingV2Node()
            try:
                self.assertIsInstance(node.pipeline.core, FlythroughInspectionPipelineV2)
                self.assertEqual(node.pipeline.core._fly_start.tolist(), [-250., -15.])
                self.assertEqual(node.pipeline.core._fly_end.tolist(), [-80., 15.])
                self.assertTrue(node.pipeline.core.flythrough_config.side_hint_required)
                self.assertEqual(node.pipeline.core.flythrough_config.side_hint_source,
                                 "synthetic_test_fixture")
                self.assertFalse(node.pipeline.core.flythrough_config.allow_synthetic_side_hint)
                self.assertEqual(node.pipeline.core.flythrough_config.maximum_side_hint_width_m, 1.)
                self.assertEqual(node.pipeline.core.flythrough_config.side_hint_max_m, 8.)
                self.assertEqual(node.pipeline.core.flythrough_config.minimum_halfmax_tail_m, 7.)
                self.assertEqual(node.pipeline.core.flythrough_config.rejoin_runin_m, 20.)
                self.assertEqual(node.pipeline.core.flythrough_config.rejoin_opposed_runin_m, 5.)
                from auv_mag_tracking.api import MagneticInput, NavigationInput
                from nav_msgs.msg import Odometry
                from std_msgs.msg import Float32MultiArray
                import math
                import numpy as np

                core = node.pipeline.core
                heading = math.degrees(math.atan2(
                    core._fly_end[1] - core._fly_start[1],
                    core._fly_end[0] - core._fly_start[0],
                ))
                nav = NavigationInput(0., np.array([*core._fly_start, -10.]),
                                      heading, speed_mps=.3, position_std_m=.1)
                mag = MagneticInput(0., np.tile([1., 0., 0.], (4, 1)), 50.)
                output, guidance = core.step_with_guidance(nav, mag)
                self.assertEqual(output.mode, "hold")
                self.assertEqual(output.diagnostics["continuity_reason"],
                                 "flythrough_side_hint_simulation_only")
                self.assertEqual(guidance.speed_mps, 0.)
                from dataclasses import replace
                core.flythrough_config = replace(
                    core.flythrough_config, side_hint_source="survey_map")
                core.reset()
                wide_output, wide_guidance = core.step_with_guidance(nav, mag)
                self.assertEqual(wide_output.mode, "hold")
                self.assertEqual(wide_output.diagnostics["continuity_reason"],
                                 "flythrough_side_hint_too_wide")
                self.assertEqual(wide_guidance.speed_mps, 0.)
                core.flythrough_config = replace(
                    core.flythrough_config, side_hint_min_m=5.5,
                    side_hint_max_m=6.4)
                core.reset()
                narrow_output, narrow_guidance = core.step_with_guidance(nav, mag)
                self.assertEqual(narrow_output.mode, "search")
                self.assertGreater(narrow_guidance.speed_mps, 0.)
                odom = Odometry()
                odom.header.frame_id = "world"
                odom.pose.pose.orientation.w = 1.
                odom.twist.twist.linear.x = .3
                node.latest_odom = odom
                node.mag_block = [[1., 0., 0.]] * 4
                missing_cov_nav, _ = node._build_inputs()
                self.assertGreater(missing_cov_nav.position_std_m,
                                   core.v2_config.inspection.maximum_navigation_sigma_m)
                covariance = np.eye(15) * .01
                covariance[0, 0], covariance[1, 1] = .04, .09
                covariance[3, 3], covariance[4, 4] = .0001, .0004
                covariance[8, 8] = math.radians(1.) ** 2
                node._on_covariance(Float32MultiArray(data=covariance.reshape(-1).tolist()))
                fresh_nav, _ = node._build_inputs()
                self.assertAlmostEqual(fresh_nav.position_std_m, .3)
                self.assertAlmostEqual(fresh_nav.heading_std_deg, 1.)
                self.assertAlmostEqual(fresh_nav.ground_velocity_std_mps, .02)
                self.assertEqual(fresh_nav.ground_velocity_ned_mps.tolist(), [.3, 0., 0.])
                odom.header.frame_id = "base_link"
                wrong_frame_nav, _ = node._build_inputs()
                fresh_mag = MagneticInput(wrong_frame_nav.time_s,
                                          np.tile([1., 0., 0.], (4, 1)), 50.)
                self.assertEqual(core._input_problem(wrong_frame_nav, fresh_mag),
                                 "navigation_velocity_frame_mismatch")
                odom.header.frame_id = "world"
                node._latest_nav_uncertainty_wall_time_s = 0.
                stale_nav, _ = node._build_inputs()
                self.assertGreater(stale_nav.position_std_m,
                                   core.v2_config.inspection.maximum_navigation_sigma_m)
            finally:
                node.destroy_node()
        finally:
            rclpy.shutdown()

    def test_launch_description_builds(self) -> None:
        import importlib.util

        for module_name, filename, minimum_entities in (
            ("cable_tracking_v2_launch", "cable_tracking_v2.launch.py", 2),
            ("auv_stack_v2_launch", "auv_stack_v2.launch.py", 3),
            ("inspection_nodes_launch", "inspection_nodes.launch.py", 3),
            ("flythrough_nodes_launch", "flythrough_nodes.launch.py", 4),
            ("shallow_survey_nodes_launch", "shallow_survey_nodes.launch.py", 4),
        ):
            launch_path = PACKAGE_ROOT / "launch" / filename
            spec = importlib.util.spec_from_file_location(module_name, launch_path)
            module = importlib.util.module_from_spec(spec)
            assert spec.loader is not None
            spec.loader.exec_module(module)
            description = module.generate_launch_description()
            self.assertGreaterEqual(len(description.entities), minimum_entities)
            if module_name == "flythrough_nodes_launch":
                from launch_ros.actions import Node
                sonar_nodes = [entity for entity in description.entities
                               if isinstance(entity, Node)
                               and entity.node_executable == "perception_quality_node"]
                self.assertEqual(len(sonar_nodes), 1)
                self.assertIsNotNone(sonar_nodes[0].condition)

    def test_non_sim_runtime_identity_requires_non_synthetic_calibration(self) -> None:
        from auv_cable_tracking_v2.cable_tracking_v2_node import CableTrackingV2Node
        import rclpy
        import tempfile

        fixture = yaml.safe_load((PACKAGE_ROOT / "config" /
            "cable_tracking_v2_flythrough_sonar_identity_sim.yaml").read_text())
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "runtime_identity.yaml"
            path.write_text(yaml.safe_dump(fixture))
            rclpy.init(args=["--ros-args", "-p", f"config_file:={path}"])
            try:
                with self.assertRaisesRegex(ValueError, "synthetic sonar calibration"):
                    CableTrackingV2Node()
            finally:
                rclpy.shutdown()

            fixture["cable_tracking"]["v2"]["runtime_identity"]["calibration_id"] = "physical_test_01"
            fixture["cable_tracking"]["v2"]["flythrough"]["side_hint_source"] = "survey_map"
            path.write_text(yaml.safe_dump(fixture))
            rclpy.init(args=["--ros-args", "-p", f"config_file:={path}"])
            try:
                with self.assertRaisesRegex(ValueError, "requires calibration_file"):
                    CableTrackingV2Node()
            finally:
                rclpy.shutdown()

            import hashlib
            import json
            calibration_path = Path(directory) / "physical_quality_test_fixture.json"
            calibration_path.write_text(json.dumps({
                "calibration_id": "physical_test_01",
                "calibration_domain": "physical",
                "deployment_approved": True,
                "physical_deployment_approved": True,
                "detection": {"score": [0, 1], "probability": [0.1, 0.9]},
                "track": {"score": [0, 1], "probability": [0.1, 0.9]},
            }))
            fixture["cable_tracking"]["v2"]["runtime_identity"]["calibration_file"] = str(calibration_path)
            fixture["cable_tracking"]["v2"]["runtime_identity"]["calibration_sha256"] = hashlib.sha256(
                calibration_path.read_bytes()).hexdigest()
            path.write_text(yaml.safe_dump(fixture))
            rclpy.init(args=["--ros-args", "-p", f"config_file:={path}"])
            try:
                with self.assertRaisesRegex(ValueError, "runtime target anchor evidence"):
                    CableTrackingV2Node()
            finally:
                rclpy.shutdown()

            from datetime import datetime, timedelta, timezone
            from auv_cable_tracking_v2.runtime_target_anchor import runtime_anchor_mission_sha256
            from auv_cable_tracking_v2.static_target_prior import prior_points_sha256
            source_path = Path(directory) / "synthetic_survey_fixture.csv"
            source_path.write_text("software fixture, no physical survey\n")
            mission = fixture["cable_tracking"]
            now = datetime.now(timezone.utc)
            reviewed_anchor = {
                "schema_version": 3, "source_kind": "survey_tie_point",
                "evidence_domain": "physical", "reviewed_for_mission": True,
                "mission_id": "software_mission", "target_id": "software_target",
                "reviewer": "software_fixture",
                "reviewed_at_utc": (now - timedelta(days=1)).isoformat(),
                "valid_until_utc": (now + timedelta(days=1)).isoformat(),
                "frame": "local_ned",
                "prior_points_sha256": prior_points_sha256(mission["prior"]),
                "mission_config_sha256": runtime_anchor_mission_sha256(mission),
                "lateral_min_m": 5.8, "lateral_max_m": 6.2,
                "exclusive_lateral_min_m": 5.45, "exclusive_lateral_max_m": 6.55,
                "along_min_m": -90., "along_max_m": -70.,
                "exclusive_along_min_m": -90., "exclusive_along_max_m": 85.,
                "source_file": str(source_path),
                "source_sha256": hashlib.sha256(source_path.read_bytes()).hexdigest(),
            }
            anchor_path = Path(directory) / "target_anchor.json"
            anchor_path.write_text(json.dumps(reviewed_anchor))
            mission["v2"]["runtime_target_anchor"] = {
                "evidence_file": str(anchor_path),
                "evidence_sha256": hashlib.sha256(anchor_path.read_bytes()).hexdigest(),
            }
            path.write_text(yaml.safe_dump(fixture))
            rclpy.init(args=["--ros-args", "-p", f"config_file:={path}"])
            try:
                node = CableTrackingV2Node()
                try:
                    self.assertTrue(node.pipeline.core.flythrough_config.require_runtime_identity_cue)
                    self.assertIsNone(node.pipeline.core.flythrough_config.maximum_side_hint_width_m)
                    self.assertIsNone(node.pipeline.core._runtime_identity_cue)
                    self.assertEqual(node.pipeline.core.flythrough_config.runtime_target_anchor_min_m, 5.8)
                    self.assertEqual(node.pipeline.core.flythrough_config.runtime_target_exclusive_max_m, 6.55)
                    self.assertEqual(node._runtime_target_anchor_evidence.target_id, "software_target")
                    from std_msgs.msg import String
                    command = {"mission_type": "CABLE_INSPECTION",
                               "mission_id": "software_mission", "target_id": "software_target",
                               "target_depth": 10., "target_speed_mps": .3}
                    for changed in ({"target_id": "other"}, {"target_speed_mps": .4}):
                        node._on_mission_command(String(data=json.dumps({**command, **changed})))
                        self.assertIsNone(node.latest_mission)
                    source_path.write_text("tampered after startup")
                    node._on_mission_command(String(data=json.dumps(command)))
                    self.assertIsNone(node.latest_mission)
                    source_path.write_text("software fixture, no physical survey\n")
                    node._on_mission_command(String(data=json.dumps(command)))
                    self.assertIsNotNone(node.latest_mission)
                    from dataclasses import replace
                    node._runtime_target_anchor_evidence = replace(
                        node._runtime_target_anchor_evidence,
                        valid_until_utc=now - timedelta(seconds=1),
                    )
                    node._check_target_evidence_lifetime()
                    self.assertTrue(node._hold_budget.recovery_required)
                finally:
                    node.destroy_node()
            finally:
                rclpy.shutdown()

    def test_non_sim_static_survey_requires_pinned_current_review(self) -> None:
        from auv_cable_tracking_v2.cable_tracking_v2_node import CableTrackingV2Node
        from auv_cable_tracking_v2.static_target_prior import (
            mission_config_sha256, prior_points_sha256,
        )
        from datetime import datetime, timedelta, timezone
        import hashlib
        import json
        import rclpy
        import tempfile

        fixture = yaml.safe_load((PACKAGE_ROOT / "config" /
            "cable_tracking_v2_flythrough_narrow_cue.yaml").read_text())
        config = fixture["cable_tracking"]
        fly = config["v2"]["flythrough"]
        fly["side_hint_source"] = "survey_map"
        now = datetime.now(timezone.utc)
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            config_path = directory / "survey_mission.yaml"

            def construct():
                config_path.write_text(yaml.safe_dump(fixture))
                rclpy.init(args=["--ros-args", "-p", f"config_file:={config_path}"])
                try:
                    return CableTrackingV2Node()
                except Exception:
                    rclpy.shutdown()
                    raise

            with self.assertRaisesRegex(ValueError, "evidence SHA-256"):
                construct()
            source = directory / "reviewed_track.json"
            source.write_text(json.dumps({"target_id": "isolated_test_target",
                                          "points": [[0, 0], [80, 0]]}))
            evidence = {
                "schema_version": 2, "source_kind": "survey_map",
                "mission_id": "software_fixture", "target_id": "isolated_test_target",
                "reviewer": "test only", "reviewed_for_mission": True,
                "reviewed_at_utc": (now - timedelta(days=1)).isoformat(),
                "valid_until_utc": (now + timedelta(days=1)).isoformat(),
                "frame": config["prior"]["frame"],
                "prior_points_sha256": prior_points_sha256(config["prior"]),
                "mission_config_sha256": mission_config_sha256(config),
                "side_hint_min_m": fly["side_hint_min_m"],
                "side_hint_max_m": fly["side_hint_max_m"],
                "source_file": str(source),
                "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            }
            review = directory / "review.json"
            review.write_text(json.dumps(evidence))
            config["v2"]["static_target_prior"] = {
                "evidence_file": str(review),
                "evidence_sha256": hashlib.sha256(review.read_bytes()).hexdigest(),
            }
            evidence["schema_version"] = 1
            review.write_text(json.dumps(evidence))
            config["v2"]["static_target_prior"]["evidence_sha256"] = hashlib.sha256(
                review.read_bytes()).hexdigest()
            with self.assertRaisesRegex(ValueError, "schema_version 2 required"):
                construct()
            evidence["schema_version"] = 2
            review.write_text(json.dumps(evidence))
            config["v2"]["static_target_prior"]["evidence_sha256"] = hashlib.sha256(
                review.read_bytes()).hexdigest()
            node = construct()
            try:
                self.assertIsNotNone(node._static_target_prior_evidence)
                from std_msgs.msg import String
                for ids in ({}, {"mission_id": "wrong", "target_id": "isolated_test_target"},
                            {"mission_id": "software_fixture", "target_id": "wrong"}):
                    node._on_mission_command(String(data=json.dumps({
                        "mission_type": "CABLE_INSPECTION", "target_depth": 10.,
                        "target_speed_mps": .3, **ids,
                    })))
                    self.assertIsNone(node.latest_mission)
                reviewed_command = {
                    "mission_type": "CABLE_INSPECTION", "target_depth": 10.,
                    "target_speed_mps": .3, "mission_id": "software_fixture",
                    "target_id": "isolated_test_target",
                }
                command_rejections = []
                original_status_publisher = node.pub_inspection_status
                node.pub_inspection_status = SimpleNamespace(publish=command_rejections.append)
                try:
                    for changed in (
                        {"target_depth": 11.}, {"target_speed_mps": .2},
                        {"target_depth": True},
                    ):
                        node._on_mission_command(String(data=json.dumps({**reviewed_command, **changed})))
                        self.assertIsNone(node.latest_mission)
                    for omitted in ("target_depth", "target_speed_mps"):
                        candidate = dict(reviewed_command)
                        candidate.pop(omitted)
                        node._on_mission_command(String(data=json.dumps(candidate)))
                        self.assertIsNone(node.latest_mission)
                    self.assertEqual([status.data for status in command_rejections],
                                     ["STATIC_TARGET_PRIOR_COMMAND_MISMATCH"] * 5)
                finally:
                    node.pub_inspection_status = original_status_publisher
                matching = String(data=json.dumps({
                    "mission_type": "CABLE_INSPECTION", "target_depth": 10.,
                    "target_speed_mps": .3, "mission_id": "software_fixture",
                    "target_id": "isolated_test_target",
                }))
                source.write_text("modified after node startup")
                node._on_mission_command(matching)
                self.assertIsNone(node.latest_mission)
                source.write_text(json.dumps({"target_id": "isolated_test_target",
                                              "points": [[0, 0], [80, 0]]}))
                node._on_mission_command(matching)
                self.assertIsNotNone(node.latest_mission)
                from dataclasses import replace
                import numpy as np
                node._static_target_prior_evidence = replace(
                    node._static_target_prior_evidence,
                    valid_until_utc=now - timedelta(seconds=1),
                )
                node.pipeline.core._last_navigation = SimpleNamespace(
                    position_ned_m=np.array([0., 0., -10.]), heading_deg=0.)
                published = []
                original_publisher = node.pub_setpoint
                node.pub_setpoint = SimpleNamespace(publish=published.append)
                try:
                    tracking = SimpleNamespace(mode="track", estimated_cable_xy_m=np.array([0., 0.]))
                    guidance = SimpleNamespace(safe_lock_active=False, target_depth_m=10.,
                                               desired_heading_deg=0., speed_mps=.3,
                                               guidance_source="test")
                    limited = SimpleNamespace(desired_heading_deg=0., speed_mps=.3)
                    node._publish_setpoint(tracking, guidance, limited, 10.)
                    self.assertTrue(node._hold_budget.recovery_required)
                    self.assertEqual(node._hold_budget.reason, "static_target_prior_expired")
                    self.assertEqual(published[-1].target_speed_mps, 0.)
                    self.assertFalse(published[-1].track_cable)
                finally:
                    node.pub_setpoint = original_publisher
            finally:
                node.destroy_node()
                rclpy.shutdown()
            fly["side_hint_max_m"] = 6.3
            with self.assertRaisesRegex(ValueError, "mission config hash mismatch"):
                construct()
            fly["side_hint_max_m"] = evidence["side_hint_max_m"]
            source.write_text("changed after review")
            with self.assertRaisesRegex(ValueError, "source hash mismatch"):
                construct()
            source.write_text(json.dumps({"target_id": "isolated_test_target",
                                          "points": [[0, 0], [80, 0]]}))
            config["prior"]["yaml_points_ned"][0][0] = 0.1
            with self.assertRaisesRegex(ValueError, "route hash mismatch"):
                construct()
            config["prior"]["yaml_points_ned"][0][0] = 0.0
            for container, key, changed in (
                (config["v2"], "search_boundary_xy_m", [[-300., -40.], [100., -40.],
                                                        [100., 40.], [-300., 40.]]),
                (fly, "end_along_m", -79.),
                (config["control"], "max_speed_mps", .2),
            ):
                original = container[key]
                container[key] = changed
                try:
                    with self.assertRaisesRegex(ValueError, "mission config hash mismatch"):
                        construct()
                finally:
                    container[key] = original
            evidence["valid_until_utc"] = (now - timedelta(hours=1)).isoformat()
            review.write_text(json.dumps(evidence))
            config["v2"]["static_target_prior"]["evidence_sha256"] = hashlib.sha256(
                review.read_bytes()).hexdigest()
            with self.assertRaisesRegex(ValueError, "expired or not yet valid"):
                construct()

    def test_adapter_injects_fresh_altitude_without_overriding_speed_policy(self) -> None:
        from auv_cable_tracking_v2.cable_tracking_v2_node import _RosV2PipelineAdapter

        class Core:
            def __init__(self):
                self.sonar = None

            def step_with_guidance(self, navigation, magnetic, sonar, **kwargs):
                self.sonar = sonar
                return (
                    SimpleNamespace(mode="confirm"),
                    SimpleNamespace(speed_mps=0.3, guidance_source="v2_cross_scan_waypoint"),
                )

        core = Core()
        adapter = _RosV2PipelineAdapter(
            core,
            altitude_provider=lambda: 6.75,
        )
        _, guidance = adapter.step_with_guidance(
            SimpleNamespace(time_s=12.0),
            object(),
            speed_mps=1.0,
        )
        self.assertTrue(core.sonar.valid)
        self.assertEqual(core.sonar.altitude_m, 6.75)
        self.assertEqual(guidance.speed_mps, 0.3)


if __name__ == "__main__":
    unittest.main()

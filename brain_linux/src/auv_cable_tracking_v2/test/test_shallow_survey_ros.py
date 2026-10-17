"""Opt-in ROS admission checks; dynamics are covered by the native PVS probe."""
from __future__ import annotations

import json
from pathlib import Path
import unittest
from unittest.mock import patch

import rclpy
from std_msgs.msg import String

from auv_cable_tracking_v2.cable_tracking_v2_node import CableTrackingV2Node
from auv_mag_tracking.v2 import ShallowSurveyInspectionPipelineV2


CONFIG = (Path(__file__).resolve().parents[1] / "config" /
          "cable_tracking_v2_shallow_survey_sim.yaml")


class ShallowSurveyRosTest(unittest.TestCase):
    def test_non_sim_launch_refuses_before_mission(self):
        rclpy.init(args=["--ros-args", "-p", f"config_file:={CONFIG}"])
        try:
            with self.assertRaisesRegex(ValueError, "simulation-only"):
                CableTrackingV2Node()
        finally:
            rclpy.shutdown()

    def test_sim_node_requires_current_and_identity_and_uses_dedicated_geometry(self):
        rclpy.init(args=["--ros-args", "-p", f"config_file:={CONFIG}",
                         "-p", "use_sim_time:=true"])
        try:
            node = CableTrackingV2Node()
            try:
                core = node.pipeline.core
                self.assertIsInstance(core, ShallowSurveyInspectionPipelineV2)
                self.assertIsNotNone(node._runtime_identity_policy)
                self.assertTrue(node._route_hold_admission_enabled)
                self.assertIsNone(core._survey_current_evidence)
                with patch.object(node._hold_budget, "evaluate", return_value={}) as evaluate:
                    node._hold_budget_snapshot("hold")
                kwargs = evaluate.call_args.kwargs
                self.assertEqual(kwargs["now_s"], node.get_clock().now().nanoseconds * 1e-9)
                self.assertIsInstance(kwargs["fallback_now_s"], float)
                self.assertTrue(kwargs["hold"])
                node._on_survey_current_evidence(String(data=json.dumps({
                    "time_s": 1., "velocity_xy_mps": [0., .04],
                    "sigma_mps": .004, "source": "synthetic_current_fixture",
                    "frame": "world",
                })))
                self.assertAlmostEqual(core._survey_current_evidence.velocity_xy_mps[1], .04)
                node._on_survey_current_evidence(String(data=json.dumps({
                    "time_s": 1., "velocity_xy_mps": [0., .04],
                    "sigma_mps": .004, "source": "unapproved_current",
                    "frame": "world",
                })))
                self.assertIsNone(core._survey_current_evidence)
            finally:
                node.destroy_node()
        finally:
            rclpy.shutdown()


if __name__ == "__main__":
    unittest.main()

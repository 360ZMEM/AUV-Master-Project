"""DDS contract from the real quality adapter to the opt-in v2 identity gate."""

from __future__ import annotations

import json
import math
from pathlib import Path
import tempfile
import time
import unittest

import numpy as np
import rclpy
from nav_msgs.msg import Odometry
from rclpy.executors import SingleThreadedExecutor
from rclpy.node import Node
from rosgraph_msgs.msg import Clock
from sensor_msgs.msg import MagneticField
from std_msgs.msg import Float32MultiArray

from auv_interfaces.msg import SonarCableObservation
from auv_cable_tracking_v2.cable_tracking_v2_node import CableTrackingV2Node
from auv_decision_ros.perception_quality_node import PerceptionQualityNode


ROOT = Path(__file__).resolve().parents[1]


class RuntimeIdentityDdsTests(unittest.TestCase):
    def test_synthetic_quality_node_line_reaches_v2_with_calibrated_probability(self):
        calibration = {
            "calibration_id": "synthetic_identity_fixture_20260927",
            "calibration_domain": "synthetic",
            "deployment_approved": True,
            "physical_deployment_approved": False,
            "detection": {"score": [0., 5., 10., 20.],
                          "probability": [0., .5, .95, 1.]},
            "track": {"score": [0., 5., 10., 20.],
                      "probability": [0., .5, .95, 1.]},
        }
        with tempfile.TemporaryDirectory() as directory:
            calibration_path = Path(directory) / "synthetic_sonar_calibration.json"
            calibration_path.write_text(json.dumps(calibration))
            config_path = ROOT / "config" / "cable_tracking_v2_flythrough_sonar_identity_sim.yaml"
            rclpy.init(args=["--ros-args", "-p", f"config_file:={config_path}",
                             "-p", "use_sim_time:=true", "-p",
                             f"sonar_calibration_file:={calibration_path}",
                             "-p", "calibration_domain:=synthetic"])
            decision = quality = peer = executor = None
            try:
                decision = CableTrackingV2Node()
                decision.timer.cancel()
                quality = PerceptionQualityNode()
                peer = Node("runtime_identity_dds_test_peer")
                executor = SingleThreadedExecutor()
                for node in (decision, quality, peer):
                    executor.add_node(node)

                clock_pub = peer.create_publisher(Clock, "/clock", 10)
                odom_pub = peer.create_publisher(Odometry, "/auv/state/filtered", 10)
                mag_pub = peer.create_publisher(MagneticField, "/auv/sensors/magnetic", 10)
                cov_pub = peer.create_publisher(Float32MultiArray, "/auv/state/covariance", 10)
                sonar_pub = peer.create_publisher(SonarCableObservation,
                                                  "/auv/sensors/cable_sonar_observation", 10)
                deadline = time.monotonic() + 10.
                while (sonar_pub.get_subscription_count() < 2
                       or clock_pub.get_subscription_count() < 2):
                    self.assertLess(time.monotonic(), deadline, "DDS discovery timeout")
                    executor.spin_once(timeout_sec=.01)

                clock = Clock()
                clock.clock.sec = 100
                clock_pub.publish(clock)
                while decision.get_clock().now().nanoseconds < 100_000_000_000:
                    self.assertLess(time.monotonic(), deadline, "simulation clock timeout")
                    executor.spin_once(timeout_sec=.01)

                odom = Odometry()
                odom.header.stamp = clock.clock
                odom.header.frame_id = "world"
                odom.pose.pose.position.x = -80.
                odom.pose.pose.position.y = 15.
                odom.pose.pose.position.z = -10.
                odom.pose.pose.orientation.w = 1.
                odom.twist.twist.linear.x = .3
                mag = MagneticField()
                mag.header.stamp = clock.clock
                mag.magnetic_field.x = 20e-9
                covariance = np.eye(15) * .0004
                covariance[0, 0] = covariance[1, 1] = .01
                covariance[8, 8] = math.radians(1.) ** 2
                sonar = SonarCableObservation()
                sonar.header.stamp = clock.clock
                sonar.header.frame_id = "sonar_link"
                sonar.valid = True
                sonar.detector_score = 12.
                sonar.point_x_m = np.linspace(-5., 5., 20).tolist()
                sonar.point_y_m = [-9.] * 20
                sonar.point_weight = [1.] * 20
                sonar.contrast_to_noise_ratio = 10.
                sonar.visible_length_m = 10.
                sonar.ambiguity_margin = 5.
                sonar.detector_id = "synthetic_identity_fixture"
                odom_pub.publish(odom)
                mag_pub.publish(mag)
                cov_pub.publish(Float32MultiArray(data=covariance.reshape(-1).tolist()))
                sonar_pub.publish(sonar)
                while (decision._latest_sonar_quality is None or decision.latest_odom is None
                       or not decision.mag_block or decision._latest_nav_uncertainty is None):
                    self.assertLess(time.monotonic(), deadline, "quality/odometry delivery timeout")
                    executor.spin_once(timeout_sec=.01)

                message = decision._latest_sonar_quality
                self.assertEqual(message.source, "sonar_cable")
                self.assertTrue(message.track_probability_calibrated)
                self.assertGreaterEqual(message.p_track, .9)
                self.assertEqual(message.calibration_id, calibration["calibration_id"])
                navigation, _ = decision._build_inputs()
                self.assertIsNotNone(navigation)
                cue = decision.pipeline.core._runtime_identity_cue
                self.assertEqual(decision._latest_identity_reason, "accepted")
                self.assertAlmostEqual(cue.lateral_center_m, 6., places=2)
                self.assertLess(cue.half_width_m, .5)
            finally:
                if executor is not None:
                    for node in (decision, quality, peer):
                        if node is not None:
                            executor.remove_node(node)
                for node in (decision, quality, peer):
                    if node is not None:
                        node.destroy_node()
                if executor is not None:
                    executor.shutdown()
                rclpy.shutdown()


if __name__ == "__main__":
    unittest.main()

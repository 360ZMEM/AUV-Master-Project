from __future__ import annotations

from dataclasses import replace
import math
from types import SimpleNamespace
import unittest

import numpy as np

from auv_cable_tracking_v2.identity_cue import SonarIdentityPolicy, sonar_identity_cue


def stamped(time_s: float, frame: str):
    second = int(time_s)
    return SimpleNamespace(frame_id=frame, stamp=SimpleNamespace(
        sec=second, nanosec=round((time_s - second) * 1e9)))


class SonarIdentityCueTests(unittest.TestCase):
    def setUp(self):
        self.policy = SonarIdentityPolicy(
            sonar_frame_id="sonar_link", world_frame_id="world",
            calibration_id="controlled_holdout_01", lever_arm_body_xy_m=(0., 0.),
            yaw_sonar_in_body_deg=0., extrinsic_position_sigma_m=.03,
            extrinsic_yaw_sigma_deg=.2,
        )
        self.observation = SimpleNamespace(
            header=stamped(100., "sonar_link"), valid=True,
            field_of_view_truncated=False, quality_flags=[], detector_id="test_detector",
            point_x_m=np.linspace(-10., 10., 20).tolist(),
            point_y_m=[-9.] * 20,
        )
        covariance = np.full((3, 3), float("nan"))
        covariance[0, 0] = .01
        covariance[1, 1] = .0001
        self.quality = SimpleNamespace(
            header=stamped(100., "sonar_link"), source="sonar_cable", validity=2,
            reason_codes=[], track_probability_calibrated=True,
            calibration_id="controlled_holdout_01", p_track=.95,
            sample_count=20, estimate=[-9., 0., float("nan")],
            age_s=0.,
            covariance=covariance.reshape(-1).tolist(),
        )
        self.navigation = SimpleNamespace(
            time_s=100.1, heading_deg=0., position_ned_m=np.array([-80., 15., -10.]),
            position_std_m=.1, heading_std_deg=1.,
        )
        self.odometry = SimpleNamespace(header=stamped(100., "world"))

    def evaluate(self, **overrides):
        return sonar_identity_cue(
            overrides.get("observation", self.observation),
            overrides.get("quality", self.quality),
            overrides.get("navigation", self.navigation),
            overrides.get("odometry", self.odometry),
            np.array([0., 0.]), np.array([1., 0.]),
            overrides.get("policy", self.policy),
        )

    def test_fresh_calibrated_line_yields_bounded_world_offset(self):
        cue, reason = self.evaluate()
        self.assertEqual(reason, "accepted")
        self.assertAlmostEqual(cue.lateral_center_m, 6.)
        self.assertLess(cue.half_width_m, .5)
        self.assertEqual(cue.calibration_id, "controlled_holdout_01")

    def test_navigation_bias_is_visible_in_world_cue(self):
        biased_navigation = SimpleNamespace(**{**vars(self.navigation),
            "position_ned_m": np.array([-80., 15.3, -10.])})
        cue, reason = self.evaluate(navigation=biased_navigation)
        self.assertEqual(reason, "accepted")
        self.assertAlmostEqual(cue.lateral_center_m, 6.3)

    def test_probability_and_age_domains_reject_then_accept_fresh_evidence(self):
        # A corrupt but "calibrated" score must not grant target identity.
        # Refusal has no persistent state: the next healthy line is usable.
        for field, invalid_values in (
            ("p_track", (-1., 1.01, float("nan"), float("inf"))),
            ("age_s", (-.1, self.policy.maximum_age_s + .01,
                       float("nan"), float("inf"))),
        ):
            for value in invalid_values:
                with self.subTest(field=field, value=value):
                    quality = SimpleNamespace(**{**vars(self.quality), field: value})
                    cue, reason = self.evaluate(quality=quality)
                    self.assertIsNone(cue)
                    self.assertEqual(reason, "sonar_identity_quality_unqualified")
                    recovered, recovered_reason = self.evaluate()
                    self.assertIsNotNone(recovered)
                    self.assertEqual(recovered_reason, "accepted")

    def test_probability_and_age_boundary_values_are_usable(self):
        for probability in (self.policy.minimum_track_probability, 1.):
            for age in (0., self.policy.maximum_age_s):
                with self.subTest(probability=probability, age=age):
                    quality = SimpleNamespace(**{**vars(self.quality),
                                               "p_track": probability, "age_s": age})
                    cue, reason = self.evaluate(quality=quality)
                    self.assertIsNotNone(cue)
                    self.assertEqual(reason, "accepted")

    def test_unobserved_depth_nan_remains_compatible(self):
        # PerceptionQuality explicitly permits NaN for unobserved depth and
        # covariance entries. Domain rejection must not disable lateral use.
        self.assertTrue(math.isnan(self.quality.estimate[2]))
        self.assertTrue(math.isnan(self.quality.covariance[8]))
        cue, reason = self.evaluate()
        self.assertIsNotNone(cue)
        self.assertEqual(reason, "accepted")

    def test_stale_skewed_uncalibrated_and_uncertain_evidence_rejects(self):
        variants = (
            ({"observation": SimpleNamespace(**{**vars(self.observation),
                "header": stamped(98., "sonar_link")})}, "sonar_identity_not_synchronized"),
            ({"quality": SimpleNamespace(**{**vars(self.quality),
                "calibration_id": "other"})}, "sonar_identity_quality_unqualified"),
            ({"quality": SimpleNamespace(**{**vars(self.quality),
                "track_probability_calibrated": False})}, "sonar_identity_quality_unqualified"),
            ({"observation": SimpleNamespace(**{**vars(self.observation),
                "point_y_m": [-6.] * 20})}, "sonar_identity_raw_quality_disagree"),
            ({"observation": SimpleNamespace(**{**vars(self.observation),
                "point_x_m": np.linspace(10., 20., 20).tolist()})},
             "sonar_identity_raw_support_insufficient"),
            ({"odometry": SimpleNamespace(header=stamped(100., "base_link"))},
             "sonar_identity_frame_mismatch"),
            ({"navigation": SimpleNamespace(**{**vars(self.navigation),
                "time_s": 101.})}, "sonar_identity_stale"),
            ({"policy": replace(self.policy, maximum_half_width_m=.1)},
             "sonar_identity_uncertainty_excessive"),
            ({"quality": SimpleNamespace(**{**vars(self.quality),
                "estimate": [-9., math.radians(30.), float("nan")]}),
              "observation": SimpleNamespace(**{**vars(self.observation),
                "point_x_m": (4.5 + np.linspace(-10., 10., 20) * math.cos(math.radians(30.))).tolist(),
                "point_y_m": (-9. * math.cos(math.radians(30.))
                              + np.linspace(-10., 10., 20) * math.sin(math.radians(30.))).tolist()})},
             "sonar_identity_heading_mismatch"),
        )
        for setting, expected in variants:
            with self.subTest(expected=expected):
                cue, reason = self.evaluate(**setting)
                self.assertIsNone(cue)
                self.assertEqual(reason, expected)


if __name__ == "__main__":
    unittest.main()

"""Conservative conversion from calibrated sonar line evidence to a prior offset."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any

import numpy as np


@dataclass(frozen=True)
class SonarIdentityPolicy:
    sonar_frame_id: str
    world_frame_id: str
    calibration_id: str
    lever_arm_body_xy_m: tuple[float, float]
    yaw_sonar_in_body_deg: float
    extrinsic_position_sigma_m: float
    extrinsic_yaw_sigma_deg: float
    maximum_age_s: float = 0.5
    maximum_stamp_skew_s: float = 0.1
    maximum_half_width_m: float = 0.5
    minimum_track_probability: float = 0.9
    maximum_prior_heading_error_deg: float = 15.
    maximum_sonar_range_m: float = 30.

    def validate(self) -> None:
        if not self.sonar_frame_id or not self.world_frame_id or not self.calibration_id:
            raise ValueError("sonar identity requires frame names and a calibration ID")
        if len(self.lever_arm_body_xy_m) != 2:
            raise ValueError("sonar identity lever arm must have two body-frame components")
        values = (*self.lever_arm_body_xy_m, self.yaw_sonar_in_body_deg,
                  self.extrinsic_position_sigma_m, self.extrinsic_yaw_sigma_deg,
                  self.maximum_age_s, self.maximum_stamp_skew_s,
                  self.maximum_half_width_m, self.minimum_track_probability,
                  self.maximum_prior_heading_error_deg, self.maximum_sonar_range_m)
        if not all(math.isfinite(float(value)) for value in values):
            raise ValueError("sonar identity policy must be finite")
        if (self.extrinsic_position_sigma_m < 0 or self.extrinsic_yaw_sigma_deg < 0
                or self.maximum_age_s <= 0 or self.maximum_stamp_skew_s < 0
                or self.maximum_half_width_m <= 0 or self.maximum_sonar_range_m <= 0
                or not 0. < self.minimum_track_probability <= 1.
                or not 0. < self.maximum_prior_heading_error_deg <= 90.):
            raise ValueError("invalid sonar identity quality limits")


@dataclass(frozen=True)
class SonarIdentityCue:
    time_s: float
    lateral_center_m: float
    half_width_m: float
    source: str
    calibration_id: str


def _stamp_seconds(header: Any) -> float:
    return float(header.stamp.sec) + float(header.stamp.nanosec) * 1e-9


def _rotate(vector: np.ndarray, angle_rad: float) -> np.ndarray:
    c, s = math.cos(angle_rad), math.sin(angle_rad)
    return np.array([c * vector[0] - s * vector[1],
                     s * vector[0] + c * vector[1]], dtype=float)


def sonar_identity_cue(
    observation: Any,
    quality: Any,
    navigation: Any,
    odometry: Any,
    prior_origin_xy_m: np.ndarray,
    prior_tangent_xy: np.ndarray,
    policy: SonarIdentityPolicy,
) -> tuple[SonarIdentityCue | None, str]:
    """Return a two-sigma lateral interval, or an explicit refusal reason.

    The quality message is assumed to fit a line in the same sonar frame as
    the raw observation. A configured lever arm and yaw map that line into
    body coordinates, then time-aligned navigation maps it into world NED.
    This checks evidence consistency; it cannot authenticate the upstream
    detector or prove a physical calibration was performed.
    """
    policy.validate()
    try:
        if (observation.header.frame_id != policy.sonar_frame_id
                or quality.header.frame_id != policy.sonar_frame_id
                or odometry.header.frame_id != policy.world_frame_id):
            return None, "sonar_identity_frame_mismatch"
        stamp = _stamp_seconds(observation.header)
        quality_stamp = _stamp_seconds(quality.header)
        pose_stamp = _stamp_seconds(odometry.header)
        nav_time = float(navigation.time_s)
        if not all(math.isfinite(t) for t in (stamp, quality_stamp, pose_stamp, nav_time)):
            return None, "sonar_identity_timestamp_invalid"
        if (abs(stamp - quality_stamp) > policy.maximum_stamp_skew_s
                or abs(stamp - pose_stamp) > policy.maximum_stamp_skew_s):
            return None, "sonar_identity_not_synchronized"
        if not 0. <= nav_time - stamp <= policy.maximum_age_s:
            return None, "sonar_identity_stale"
        if (not observation.valid or observation.field_of_view_truncated
                or observation.quality_flags or not observation.detector_id):
            return None, "sonar_identity_detection_unqualified"
        if (quality.source != "sonar_cable" or int(quality.validity) != 2
                or quality.reason_codes or not quality.track_probability_calibrated
                or quality.calibration_id != policy.calibration_id
                or not math.isfinite(float(quality.age_s))
                or not 0. <= float(quality.age_s) <= policy.maximum_age_s
                or not math.isfinite(float(quality.p_track))
                or not policy.minimum_track_probability <= float(quality.p_track) <= 1.
                or int(quality.sample_count) < 8):
            return None, "sonar_identity_quality_unqualified"
        estimate = np.asarray(quality.estimate, dtype=float)
        covariance = np.asarray(quality.covariance, dtype=float).reshape(3, 3)
        if estimate.size < 2:
            return None, "sonar_identity_geometry_invalid"
        cross_track, line_heading = map(float, estimate[:2])
        cross_track_variance = float(covariance[0, 0])
        line_heading_variance = float(covariance[1, 1])
        if (not math.isfinite(cross_track) or not math.isfinite(line_heading)
                or not math.isfinite(cross_track_variance)
                or cross_track_variance <= 0. or not math.isfinite(line_heading_variance)
                or line_heading_variance <= 0.):
            return None, "sonar_identity_geometry_invalid"
        if abs(cross_track) > policy.maximum_sonar_range_m:
            return None, "sonar_identity_out_of_range"
        normal_sonar = np.array([-math.sin(line_heading), math.cos(line_heading)])
        points_x = np.asarray(observation.point_x_m, dtype=float)
        points_y = np.asarray(observation.point_y_m, dtype=float)
        if (points_x.size < 8 or points_x.size != points_y.size
                or not np.isfinite(points_x).all() or not np.isfinite(points_y).all()):
            return None, "sonar_identity_raw_points_invalid"
        if np.max(np.hypot(points_x, points_y)) > policy.maximum_sonar_range_m:
            return None, "sonar_identity_out_of_range"
        tangent_sonar = np.array([math.cos(line_heading), math.sin(line_heading)])
        along = tangent_sonar[0] * points_x + tangent_sonar[1] * points_y
        if not float(np.min(along)) <= 0. <= float(np.max(along)):
            return None, "sonar_identity_raw_support_insufficient"
        raw_residual = np.abs(-math.sin(line_heading) * points_x
                              + math.cos(line_heading) * points_y - cross_track)
        if float(np.median(raw_residual)) > max(0.25, 3. * math.sqrt(cross_track_variance)):
            return None, "sonar_identity_raw_quality_disagree"
        closest_sonar = cross_track * normal_sonar
        sonar_yaw = math.radians(policy.yaw_sonar_in_body_deg)
        closest_body = np.asarray(policy.lever_arm_body_xy_m) + _rotate(closest_sonar, sonar_yaw)
        heading_world = math.radians(float(navigation.heading_deg))
        position_world = np.asarray(navigation.position_ned_m, dtype=float)[:2]
        tangent_world = _rotate(np.array([math.cos(line_heading), math.sin(line_heading)]),
                                heading_world + sonar_yaw)
        prior_tangent = np.array(prior_tangent_xy, dtype=float, copy=True)
        prior_tangent /= np.linalg.norm(prior_tangent)
        line_alignment = abs(float(np.dot(tangent_world, prior_tangent)))
        line_error_deg = math.degrees(math.acos(min(1., max(-1., line_alignment))))
        if line_error_deg > policy.maximum_prior_heading_error_deg:
            return None, "sonar_identity_heading_mismatch"
        prior_normal = np.array([-prior_tangent[1], prior_tangent[0]])
        center_world = position_world + _rotate(closest_body, heading_world)
        lateral = float(np.dot(center_world - prior_origin_xy_m, prior_normal))
        normal_world = _rotate(normal_sonar, heading_world + sonar_yaw)
        sonar_sigma = abs(float(np.dot(prior_normal, normal_world))) * math.sqrt(cross_track_variance)
        position_sigma = float(navigation.position_std_m)
        heading_sigma_deg = float(navigation.heading_std_deg)
        if (not np.isfinite(position_world).all() or not math.isfinite(lateral)
                or not math.isfinite(position_sigma) or position_sigma <= 0
                or not math.isfinite(heading_sigma_deg) or heading_sigma_deg <= 0):
            return None, "sonar_identity_navigation_invalid"
        rotation_sigma = (np.linalg.norm(closest_body) * math.radians(
            math.sqrt(heading_sigma_deg ** 2 + policy.extrinsic_yaw_sigma_deg ** 2
                      + math.degrees(math.sqrt(line_heading_variance)) ** 2)))
        sigma = math.hypot(sonar_sigma, position_sigma,
                           policy.extrinsic_position_sigma_m, rotation_sigma)
        half_width = 2. * sigma
        if not math.isfinite(half_width) or half_width > policy.maximum_half_width_m:
            return None, "sonar_identity_uncertainty_excessive"
        return SonarIdentityCue(stamp, lateral, half_width, "sonar_cable", policy.calibration_id), "accepted"
    except (AttributeError, TypeError, ValueError, OverflowError, ZeroDivisionError, IndexError):
        return None, "sonar_identity_input_invalid"

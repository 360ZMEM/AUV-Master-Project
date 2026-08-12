"""Source-specific, deployment-facing perception quality estimators."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import math
from pathlib import Path
from typing import Sequence

import numpy as np


INVALID = 0
DEGRADED = 1
VALID = 2


@dataclass(frozen=True)
class QualityEstimate:
    source: str
    validity: int
    reason_codes: tuple[str, ...]
    detection_score: float
    p_detect: float
    p_track: float
    detection_probability_calibrated: bool
    track_probability_calibrated: bool
    estimate: np.ndarray
    covariance: np.ndarray
    age_s: float
    sample_count: int
    data_completeness: float
    calibration_id: str = ""
    diagnostics: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class PiecewiseCalibration:
    x: np.ndarray
    y: np.ndarray

    def evaluate(self, value: float) -> float:
        if not math.isfinite(value) or self.x.size == 0:
            return float("nan")
        return float(np.clip(np.interp(value, self.x, self.y), 0.0, 1.0))


@dataclass(frozen=True)
class SourceCalibration:
    calibration_id: str
    detection: PiecewiseCalibration
    track: PiecewiseCalibration
    deployment_approved: bool = False
    calibration_domain: str = "physical"
    physical_deployment_approved: bool = False

    @classmethod
    def from_json(cls, path: str | Path) -> "SourceCalibration":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))

        def curve(name: str) -> PiecewiseCalibration:
            item = dict(payload[name])
            x = np.asarray(item["score"], dtype=float)
            y = np.asarray(item["probability"], dtype=float)
            if x.ndim != 1 or y.ndim != 1 or x.size != y.size or x.size < 2:
                raise ValueError(f"invalid calibration curve: {name}")
            if np.any(~np.isfinite(x)) or np.any(~np.isfinite(y)):
                raise ValueError(f"non-finite calibration curve: {name}")
            if np.any(np.diff(x) <= 0.0) or np.any(np.diff(y) < 0.0):
                raise ValueError(f"calibration curve must be monotonic: {name}")
            return PiecewiseCalibration(x=x, y=np.clip(y, 0.0, 1.0))

        return cls(
            calibration_id=str(payload["calibration_id"]),
            detection=curve("detection"),
            track=curve("track"),
            deployment_approved=bool(payload.get("deployment_approved", False)),
            calibration_domain=str(
                payload.get("calibration_domain", "physical")
            ),
            physical_deployment_approved=bool(
                payload.get(
                    "physical_deployment_approved",
                    payload.get("deployment_approved", False)
                    and payload.get("calibration_domain", "physical")
                    == "physical",
                )
            ),
        )


def _empty_quality(
    source: str,
    reasons: Sequence[str],
    *,
    age_s: float,
    sample_count: int,
    completeness: float,
) -> QualityEstimate:
    return QualityEstimate(
        source=source,
        validity=INVALID,
        reason_codes=tuple(reasons),
        detection_score=float("-inf"),
        p_detect=float("nan"),
        p_track=float("nan"),
        detection_probability_calibrated=False,
        track_probability_calibrated=False,
        estimate=np.full(3, np.nan),
        covariance=np.full((3, 3), np.nan),
        age_s=max(float(age_s), 0.0),
        sample_count=max(int(sample_count), 0),
        data_completeness=float(np.clip(completeness, 0.0, 1.0)),
    )


def _track_score(
    detection_score: float,
    sigma: float,
    tolerance: float,
) -> float:
    if not all(math.isfinite(value) for value in (detection_score, sigma)):
        return float("-inf")
    normalized_sigma = max(sigma, 0.0) / max(tolerance, 1e-9)
    return float(detection_score - math.log1p(normalized_sigma * normalized_sigma))


def _calibrated_probabilities(
    calibration: SourceCalibration | None,
    detection_score: float,
    track_score: float,
) -> tuple[float, float, bool, bool, str]:
    if calibration is None or not calibration.deployment_approved:
        return float("nan"), float("nan"), False, False, ""
    p_detect = calibration.detection.evaluate(detection_score)
    p_track = calibration.track.evaluate(track_score)
    return (
        p_detect,
        p_track,
        math.isfinite(p_detect),
        math.isfinite(p_track),
        calibration.calibration_id,
    )


class MagneticQualityEstimator:
    """Coherent target-frequency evidence and cable-relative uncertainty."""

    def __init__(
        self,
        *,
        target_frequency_hz: float = 45.0,
        min_cycles: float = 8.0,
        max_age_s: float = 0.5,
        cross_track_tolerance_m: float = 2.0,
        calibration: SourceCalibration | None = None,
    ) -> None:
        self.target_frequency_hz = float(target_frequency_hz)
        self.min_cycles = float(min_cycles)
        self.max_age_s = float(max_age_s)
        self.cross_track_tolerance_m = float(cross_track_tolerance_m)
        self.calibration = calibration

    def evaluate(
        self,
        *,
        samples_nt: np.ndarray,
        time_s: np.ndarray,
        age_s: float,
        data_completeness: float,
        clipping_ratio: float,
        calibration_valid: bool,
        cable_heading_rad: float | None = None,
        vertical_separation_m: float | None = None,
        external_reasons: Sequence[str] = (),
    ) -> QualityEstimate:
        samples = np.asarray(samples_nt, dtype=float)
        times = np.asarray(time_s, dtype=float)
        reasons = [str(reason) for reason in external_reasons if str(reason)]
        if samples.ndim != 2 or samples.shape[1] != 3:
            return _empty_quality(
                "magnetic_45hz",
                [*reasons, "invalid_sample_shape"],
                age_s=age_s,
                sample_count=samples.shape[0] if samples.ndim else 0,
                completeness=data_completeness,
            )
        count = samples.shape[0]
        if times.shape != (count,) or count < 8:
            return _empty_quality(
                "magnetic_45hz",
                [*reasons, "insufficient_samples"],
                age_s=age_s,
                sample_count=count,
                completeness=data_completeness,
            )
        finite = np.isfinite(times) & np.all(np.isfinite(samples), axis=1)
        samples = samples[finite]
        times = times[finite]
        count = samples.shape[0]
        if count < 8 or np.any(np.diff(times) <= 0.0):
            return _empty_quality(
                "magnetic_45hz",
                [*reasons, "invalid_timestamps"],
                age_s=age_s,
                sample_count=count,
                completeness=data_completeness,
            )
        duration_s = float(times[-1] - times[0])
        if duration_s * self.target_frequency_hz < self.min_cycles:
            reasons.append("insufficient_target_cycles")
        if age_s > self.max_age_s:
            reasons.append("stale")
        if data_completeness < 0.95:
            reasons.append("incomplete_block")
        if clipping_ratio > 0.0:
            reasons.append("clipped")
        if not calibration_valid:
            reasons.append("calibration_invalid")

        centered_time = times - float(np.mean(times))
        phase = 2.0 * np.pi * self.target_frequency_hz * times
        window = np.hanning(count) if count > 2 else np.ones(count)
        design = np.column_stack(
            (
                np.ones(count),
                centered_time,
                np.cos(phase),
                np.sin(phase),
            )
        )
        weighted_design = design * np.sqrt(window)[:, None]
        weighted_samples = samples * np.sqrt(window)[:, None]
        coefficients, _, rank, _ = np.linalg.lstsq(
            weighted_design,
            weighted_samples,
            rcond=None,
        )
        if rank < 4:
            return _empty_quality(
                "magnetic_45hz",
                [*reasons, "rank_deficient_demodulation"],
                age_s=age_s,
                sample_count=count,
                completeness=data_completeness,
            )
        fitted = design @ coefficients
        residual = samples - fitted
        dof = max(count - design.shape[1], 1)
        residual_variance = np.sum(window[:, None] * residual * residual, axis=0) / dof
        normal_inverse = np.linalg.pinv(weighted_design.T @ weighted_design)
        phasor = coefficients[2:4, :].T
        phasor_covariance = np.zeros((6, 6), dtype=float)
        coefficient_block = normal_inverse[2:4, 2:4]
        for axis in range(3):
            indices = (2 * axis, 2 * axis + 1)
            phasor_covariance[np.ix_(indices, indices)] = (
                max(float(residual_variance[axis]), 1e-12) * coefficient_block
            )
        phasor_vector = phasor.reshape(-1)
        inverse_covariance = np.linalg.pinv(phasor_covariance)
        statistic = float(phasor_vector @ inverse_covariance @ phasor_vector)
        half_statistic = max(statistic, 0.0) / 2.0
        false_alarm_probability = math.exp(-half_statistic) * (
            1.0 + half_statistic + 0.5 * half_statistic * half_statistic
        )
        false_alarm_probability = float(
            np.clip(false_alarm_probability, 1e-300, 1.0)
        )
        detection_score = -math.log10(false_alarm_probability)

        estimate = np.full(3, np.nan)
        covariance = np.full((3, 3), np.nan)
        cross_track_sigma = float("inf")
        if cable_heading_rad is not None and vertical_separation_m is not None:
            cross_track, cross_track_variance = self._cross_track_and_variance(
                phasor_vector,
                phasor_covariance,
                float(cable_heading_rad),
                float(vertical_separation_m),
            )
            if math.isfinite(cross_track) and math.isfinite(cross_track_variance):
                estimate[0] = cross_track
                covariance[0, 0] = max(cross_track_variance, 0.0)
                cross_track_sigma = math.sqrt(max(cross_track_variance, 0.0))
            else:
                reasons.append("cross_track_unobservable")
        else:
            reasons.append("geometry_context_missing")

        track_score = _track_score(
            detection_score,
            cross_track_sigma,
            self.cross_track_tolerance_m,
        )
        (
            p_detect,
            p_track,
            detection_calibrated,
            track_calibrated,
            calibration_id,
        ) = _calibrated_probabilities(
            self.calibration,
            detection_score,
            track_score,
        )
        severe = {
            "invalid_sample_shape",
            "insufficient_samples",
            "invalid_timestamps",
            "rank_deficient_demodulation",
            "stale",
            "clipped",
            "calibration_invalid",
        }
        validity = VALID
        if severe.intersection(reasons):
            validity = INVALID
        elif reasons or not detection_calibrated or not track_calibrated:
            validity = DEGRADED
            if not detection_calibrated:
                reasons.append("probability_calibration_missing")
            elif not track_calibrated:
                reasons.append("track_probability_unavailable")
        return QualityEstimate(
            source="magnetic_45hz",
            validity=validity,
            reason_codes=tuple(dict.fromkeys(reasons)),
            detection_score=detection_score,
            p_detect=p_detect,
            p_track=p_track,
            detection_probability_calibrated=detection_calibrated,
            track_probability_calibrated=track_calibrated,
            estimate=estimate,
            covariance=covariance,
            age_s=max(float(age_s), 0.0),
            sample_count=count,
            data_completeness=float(np.clip(data_completeness, 0.0, 1.0)),
            calibration_id=calibration_id,
            diagnostics={
                "false_alarm_probability_model": false_alarm_probability,
                "target_frequency_hz": self.target_frequency_hz,
                "duration_s": duration_s,
                "phasor_cos_sin_nt": phasor.tolist(),
                "residual_std_nt": np.sqrt(np.maximum(residual_variance, 0.0)).tolist(),
                "track_score": track_score,
            },
        )

    @staticmethod
    def _cross_track_and_variance(
        phasor_vector: np.ndarray,
        covariance: np.ndarray,
        heading_rad: float,
        vertical_separation_m: float,
    ) -> tuple[float, float]:
        def estimate(vector: np.ndarray) -> float:
            phasor = np.asarray(vector, dtype=float).reshape(3, 2)
            normal = np.array([-math.sin(heading_rad), math.cos(heading_rad)])
            perpendicular = normal @ phasor[:2, :]
            down = phasor[2, :]
            denominator = float(perpendicular @ perpendicular)
            if denominator <= 1e-15:
                return float("nan")
            slope = float(perpendicular @ down) / denominator
            return slope * vertical_separation_m

        value = estimate(phasor_vector)
        if not math.isfinite(value):
            return float("nan"), float("nan")
        gradient = np.zeros(6, dtype=float)
        for index in range(6):
            step = max(abs(float(phasor_vector[index])) * 1e-5, 1e-6)
            upper = phasor_vector.copy()
            lower = phasor_vector.copy()
            upper[index] += step
            lower[index] -= step
            upper_value = estimate(upper)
            lower_value = estimate(lower)
            if not math.isfinite(upper_value) or not math.isfinite(lower_value):
                return value, float("nan")
            gradient[index] = (upper_value - lower_value) / (2.0 * step)
        variance = float(gradient @ covariance @ gradient)
        return value, max(variance, 0.0)


class SonarQualityEstimator:
    """Robust cable-line fit with explicit geometric covariance."""

    def __init__(
        self,
        *,
        min_points: int = 8,
        max_age_s: float = 0.5,
        cross_track_tolerance_m: float = 2.0,
        calibration: SourceCalibration | None = None,
    ) -> None:
        self.min_points = max(int(min_points), 3)
        self.max_age_s = float(max_age_s)
        self.cross_track_tolerance_m = float(cross_track_tolerance_m)
        self.calibration = calibration

    def evaluate(
        self,
        *,
        points_body_m: np.ndarray,
        point_weight: np.ndarray | None,
        detector_score: float,
        contrast_to_noise_ratio: float,
        visible_length_m: float,
        ambiguity_margin: float,
        field_of_view_truncated: bool,
        age_s: float,
        external_reasons: Sequence[str] = (),
    ) -> QualityEstimate:
        points = np.asarray(points_body_m, dtype=float)
        reasons = [str(reason) for reason in external_reasons if str(reason)]
        if points.ndim != 2 or points.shape[1] != 2:
            return _empty_quality(
                "sonar_cable",
                [*reasons, "invalid_point_shape"],
                age_s=age_s,
                sample_count=points.shape[0] if points.ndim else 0,
                completeness=0.0,
            )
        finite = np.all(np.isfinite(points), axis=1)
        points = points[finite]
        count = points.shape[0]
        if count < self.min_points:
            return _empty_quality(
                "sonar_cable",
                [*reasons, "insufficient_inliers"],
                age_s=age_s,
                sample_count=count,
                completeness=count / max(self.min_points, 1),
            )
        if point_weight is None or np.asarray(point_weight).size == 0:
            weights = np.ones(count, dtype=float)
        else:
            raw_weights = np.asarray(point_weight, dtype=float)
            if raw_weights.shape != finite.shape:
                return _empty_quality(
                    "sonar_cable",
                    [*reasons, "invalid_weight_shape"],
                    age_s=age_s,
                    sample_count=count,
                    completeness=1.0,
                )
            weights = np.maximum(raw_weights[finite], 0.0)
        if float(np.sum(weights)) <= 1e-12:
            return _empty_quality(
                "sonar_cable",
                [*reasons, "zero_point_weight"],
                age_s=age_s,
                sample_count=count,
                completeness=1.0,
            )
        tangent, normal, center, residual, robust_weights = self._robust_line(
            points,
            weights,
        )
        if tangent[0] < 0.0:
            tangent = -tangent
            normal = -normal
            residual = -residual
        inlier = np.abs(residual) <= 2.5 * max(
            1.4826 * float(np.median(np.abs(residual - np.median(residual)))),
            1e-4,
        )
        inlier_ratio = float(np.mean(inlier))
        residual_sigma = max(
            1.4826 * float(np.median(np.abs(residual - np.median(residual)))),
            1e-4,
        )
        along = (points - center) @ tangent
        effective_count = max(
            float(np.sum(robust_weights)) ** 2
            / max(float(np.sum(robust_weights * robust_weights)), 1e-12),
            1.0,
        )
        cross_track_variance = residual_sigma * residual_sigma / effective_count
        heading_variance = residual_sigma * residual_sigma / max(
            float(np.sum(robust_weights * along * along)),
            1e-12,
        )
        cross_track = float(center @ normal)
        heading = math.atan2(float(tangent[1]), float(tangent[0]))
        if age_s > self.max_age_s:
            reasons.append("stale")
        if field_of_view_truncated:
            reasons.append("field_of_view_truncated")
        if inlier_ratio < 0.6:
            reasons.append("low_inlier_ratio")
        if visible_length_m <= 0.0:
            visible_length_m = float(np.ptp(along))
        evidence = (
            math.log1p(max(count, 0))
            + math.log1p(max(contrast_to_noise_ratio, 0.0))
            + math.log1p(max(visible_length_m, 0.0))
            + math.log1p(max(ambiguity_margin, 0.0))
            + math.log1p(max(detector_score, 0.0))
            - math.log1p(residual_sigma / 0.1)
        )
        if field_of_view_truncated:
            evidence -= 1.0
        track_score = _track_score(
            evidence,
            math.sqrt(cross_track_variance),
            self.cross_track_tolerance_m,
        )
        (
            p_detect,
            p_track,
            detection_calibrated,
            track_calibrated,
            calibration_id,
        ) = _calibrated_probabilities(
                self.calibration,
                evidence,
                track_score,
            )
        if not detection_calibrated:
            reasons.append("probability_calibration_missing")
        elif not track_calibrated:
            reasons.append("track_probability_unavailable")
        severe = {"stale", "low_inlier_ratio", "detector_invalid"}
        validity = INVALID if severe.intersection(reasons) else (
            DEGRADED if reasons else VALID
        )
        estimate = np.array([cross_track, heading, np.nan], dtype=float)
        covariance = np.full((3, 3), np.nan)
        covariance[0, 0] = cross_track_variance
        covariance[1, 1] = heading_variance
        return QualityEstimate(
            source="sonar_cable",
            validity=validity,
            reason_codes=tuple(dict.fromkeys(reasons)),
            detection_score=evidence,
            p_detect=p_detect,
            p_track=p_track,
            detection_probability_calibrated=detection_calibrated,
            track_probability_calibrated=track_calibrated,
            estimate=estimate,
            covariance=covariance,
            age_s=max(float(age_s), 0.0),
            sample_count=count,
            data_completeness=inlier_ratio,
            calibration_id=calibration_id,
            diagnostics={
                "residual_sigma_m": residual_sigma,
                "inlier_ratio": inlier_ratio,
                "visible_length_m": visible_length_m,
                "effective_sample_count": effective_count,
                "track_score": track_score,
            },
        )

    @staticmethod
    def _robust_line(
        points: np.ndarray,
        base_weights: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        weights = np.asarray(base_weights, dtype=float).copy()
        for _ in range(6):
            weight_sum = max(float(np.sum(weights)), 1e-12)
            center = np.sum(points * weights[:, None], axis=0) / weight_sum
            centered = points - center
            scatter = (centered * weights[:, None]).T @ centered / weight_sum
            eigenvalues, eigenvectors = np.linalg.eigh(scatter)
            tangent = eigenvectors[:, int(np.argmax(eigenvalues))]
            normal = np.array([-tangent[1], tangent[0]])
            residual = centered @ normal
            scale = max(
                1.4826
                * float(np.median(np.abs(residual - np.median(residual)))),
                1e-4,
            )
            normalized = np.abs(residual) / (1.5 * scale)
            huber = np.ones_like(normalized)
            mask = normalized > 1.0
            huber[mask] = 1.0 / normalized[mask]
            weights = base_weights * huber
        return tangent, normal, center, residual, weights

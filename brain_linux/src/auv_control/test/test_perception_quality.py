"""Tests for source-specific perception quality estimators."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from auv_decision_ros.perception_quality import (
    DEGRADED,
    INVALID,
    MagneticQualityEstimator,
    SonarQualityEstimator,
    SourceCalibration,
)


def _calibration(tmp_path: Path) -> SourceCalibration:
    path = tmp_path / "calibration.json"
    path.write_text(
        json.dumps(
            {
                "calibration_id": "test-cal-v1",
                "deployment_approved": True,
                "detection": {
                    "score": [-2.0, 0.0, 3.0, 20.0],
                    "probability": [0.01, 0.05, 0.8, 0.99],
                },
                "track": {
                    "score": [-2.0, 0.0, 3.0, 20.0],
                    "probability": [0.01, 0.05, 0.75, 0.98],
                },
            }
        ),
        encoding="utf-8",
    )
    return SourceCalibration.from_json(path)


def test_magnetic_45hz_evidence_and_cross_track(tmp_path: Path) -> None:
    rng = np.random.default_rng(4)
    rate_hz = 2000.0
    time_s = np.arange(2000, dtype=float) / rate_hz
    phase = 2.0 * np.pi * 45.0 * time_s
    samples = np.column_stack(
        (
            0.2 * np.cos(phase),
            10.0 * np.cos(phase),
            5.0 * np.cos(phase),
        )
    )
    samples += rng.normal(0.0, 0.05, size=samples.shape)
    estimator = MagneticQualityEstimator(
        calibration=_calibration(tmp_path),
    )

    result = estimator.evaluate(
        samples_nt=samples,
        time_s=time_s,
        age_s=0.01,
        data_completeness=1.0,
        clipping_ratio=0.0,
        calibration_valid=True,
        cable_heading_rad=0.0,
        vertical_separation_m=7.5,
    )

    assert result.detection_score > 10.0
    assert result.detection_probability_calibrated is True
    assert result.track_probability_calibrated is True
    assert result.p_detect > 0.9
    assert abs(result.estimate[0] - 3.75) < 0.1
    assert 0.0 < result.covariance[0, 0] < 0.1


def test_magnetic_target_frequency_rejects_50hz_background() -> None:
    rate_hz = 2000.0
    time_s = np.arange(2000, dtype=float) / rate_hz
    phase = 2.0 * np.pi * 50.0 * time_s
    samples = np.column_stack(
        (
            50.0 * np.cos(phase),
            40.0 * np.cos(phase),
            30.0 * np.cos(phase),
        )
    )
    result = MagneticQualityEstimator().evaluate(
        samples_nt=samples,
        time_s=time_s,
        age_s=0.01,
        data_completeness=1.0,
        clipping_ratio=0.0,
        calibration_valid=True,
    )

    assert result.detection_score < 1.0
    assert result.validity == DEGRADED
    assert np.isnan(result.p_detect)
    assert "probability_calibration_missing" in result.reason_codes


def test_detection_can_be_calibrated_without_track_geometry(
    tmp_path: Path,
) -> None:
    rate_hz = 2000.0
    time_s = np.arange(1000, dtype=float) / rate_hz
    phase = 2.0 * np.pi * 45.0 * time_s
    samples = np.column_stack([np.cos(phase)] * 3)
    result = MagneticQualityEstimator(
        calibration=_calibration(tmp_path),
    ).evaluate(
        samples_nt=samples,
        time_s=time_s,
        age_s=0.0,
        data_completeness=1.0,
        clipping_ratio=0.0,
        calibration_valid=True,
    )

    assert result.detection_probability_calibrated is True
    assert result.track_probability_calibrated is False
    assert np.isfinite(result.p_detect)
    assert np.isnan(result.p_track)
    assert "track_probability_unavailable" in result.reason_codes


def test_magnetic_clipping_is_invalid() -> None:
    time_s = np.arange(1000, dtype=float) / 2000.0
    samples = np.zeros((1000, 3), dtype=float)
    result = MagneticQualityEstimator().evaluate(
        samples_nt=samples,
        time_s=time_s,
        age_s=0.01,
        data_completeness=1.0,
        clipping_ratio=0.02,
        calibration_valid=True,
    )

    assert result.validity == INVALID
    assert "clipped" in result.reason_codes


def test_unapproved_calibration_does_not_emit_probabilities(
    tmp_path: Path,
) -> None:
    path = tmp_path / "fit_only.json"
    path.write_text(
        json.dumps(
            {
                "calibration_id": "fit-only",
                "deployment_approved": False,
                "detection": {
                    "score": [0.0, 1.0],
                    "probability": [0.1, 0.9],
                },
                "track": {
                    "score": [0.0, 1.0],
                    "probability": [0.1, 0.9],
                },
            }
        ),
        encoding="utf-8",
    )
    calibration = SourceCalibration.from_json(path)
    time_s = np.arange(1000, dtype=float) / 2000.0
    phase = 2.0 * np.pi * 45.0 * time_s
    samples = np.column_stack([np.cos(phase)] * 3)

    result = MagneticQualityEstimator(calibration=calibration).evaluate(
        samples_nt=samples,
        time_s=time_s,
        age_s=0.0,
        data_completeness=1.0,
        clipping_ratio=0.0,
        calibration_valid=True,
    )

    assert result.detection_probability_calibrated is False
    assert result.track_probability_calibrated is False
    assert np.isnan(result.p_detect)
    assert np.isnan(result.p_track)


def test_sonar_robust_line_covariance_and_outlier_rejection(
    tmp_path: Path,
) -> None:
    rng = np.random.default_rng(7)
    x = np.linspace(-5.0, 5.0, 80)
    y = 1.2 + rng.normal(0.0, 0.04, size=x.size)
    points = np.column_stack((x, y))
    points[:4] += np.array([0.0, 5.0])
    estimator = SonarQualityEstimator(
        calibration=_calibration(tmp_path),
    )
    result = estimator.evaluate(
        points_body_m=points,
        point_weight=None,
        detector_score=0.9,
        contrast_to_noise_ratio=8.0,
        visible_length_m=10.0,
        ambiguity_margin=0.8,
        field_of_view_truncated=False,
        age_s=0.02,
    )

    assert abs(result.estimate[0] - 1.2) < 0.1
    assert abs(result.estimate[1]) < 0.05
    assert result.covariance[0, 0] > 0.0
    assert result.p_detect > 0.8
    assert float(result.diagnostics["inlier_ratio"]) > 0.9


def test_sonar_invalid_detector_cannot_be_valid() -> None:
    x = np.linspace(-2.0, 2.0, 20)
    points = np.column_stack((x, np.zeros_like(x)))
    result = SonarQualityEstimator().evaluate(
        points_body_m=points,
        point_weight=None,
        detector_score=1.0,
        contrast_to_noise_ratio=10.0,
        visible_length_m=4.0,
        ambiguity_margin=1.0,
        field_of_view_truncated=False,
        age_s=0.0,
        external_reasons=("detector_invalid",),
    )

    assert result.validity == INVALID

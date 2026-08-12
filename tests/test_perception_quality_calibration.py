"""Tests for probability calibration and deployment approval gates."""

from __future__ import annotations

import numpy as np

from tools.calibrate_perception_quality import (
    evaluate_curve,
    fit_isotonic,
    probability_metrics,
)


def test_isotonic_curve_is_monotonic() -> None:
    scores = np.array([0, 1, 2, 3, 4, 5], dtype=float)
    labels = np.array([0, 1, 0, 1, 1, 1], dtype=float)
    curve = fit_isotonic(scores, labels)

    assert np.all(np.diff(curve["score"]) > 0.0)
    assert np.all(np.diff(curve["probability"]) >= 0.0)


def test_probability_metrics_detect_miscalibration() -> None:
    labels = np.array([0, 0, 0, 1, 1, 1], dtype=float)
    calibrated = np.array([0.05, 0.1, 0.2, 0.8, 0.9, 0.95])
    inverted = 1.0 - calibrated

    good = probability_metrics(calibrated, labels)
    bad = probability_metrics(inverted, labels)

    assert good["brier"] < bad["brier"]
    assert good["ece"] < bad["ece"]


def test_curve_evaluation_clips_outside_fit_range() -> None:
    curve = {
        "score": [0.0, 1.0, 2.0],
        "probability": [0.1, 0.5, 0.9],
    }
    probability = evaluate_curve(curve, np.array([-5.0, 0.5, 9.0]))

    assert np.allclose(probability, [0.1, 0.3, 0.9])

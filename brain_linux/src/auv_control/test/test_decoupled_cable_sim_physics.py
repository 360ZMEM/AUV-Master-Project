from __future__ import annotations

import math

import numpy as np
import pytest

from auv_decision_ros.decoupled_cable_sim_node import _infinite_straight_wire_field_t


def test_infinite_wire_magnitude_and_fwhm_geometry() -> None:
    current_a = 600.0
    vertical_m = 4.0
    centre = _infinite_straight_wire_field_t(
        np.array([0.0, 0.0, 12.0]),
        cable_y_m=0.0,
        cable_depth_m=16.0,
        current_amp_a=current_a,
    )
    expected_centre_t = 4.0e-7 * math.pi * current_a / (2.0 * math.pi * vertical_m)
    assert np.linalg.norm(centre) == pytest.approx(expected_centre_t)

    half_crossing_y_m = math.sqrt(3.0) * vertical_m
    half = _infinite_straight_wire_field_t(
        np.array([0.0, half_crossing_y_m, 12.0]),
        cable_y_m=0.0,
        cable_depth_m=16.0,
        current_amp_a=current_a,
    )
    assert np.linalg.norm(half) == pytest.approx(0.5 * expected_centre_t)

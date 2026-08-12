from __future__ import annotations

from pathlib import Path
import sys

import numpy as np


INTERFACES = (
    Path(__file__).resolve().parents[1]
    / "sim_holoocean"
    / "interfaces"
)
if str(INTERFACES) not in sys.path:
    sys.path.insert(0, str(INTERFACES))

from cable_quality_sim import (  # noqa: E402
    build_magnetic_block_payload,
    build_sonar_observation_payload,
)


def test_magnetic_block_has_verified_2khz_45hz_measurement() -> None:
    payload = build_magnetic_block_payload(
        field_amplitude_t=np.array([0.0, 10.0e-9, 5.0e-9]),
        block_end_time_s=2.0,
        magnetic_sigma_t=np.full(3, 0.1e-9),
        config={},
        rng=np.random.default_rng(1),
    )
    assert payload["sample_rate_hz"] == 2000.0
    assert payload["sample_count"] >= 360
    assert len(payload["x_nt"]) == payload["sample_count"]
    assert payload["sample_clock_verified"] is True
    assert payload["measurement_domain"] == "simulation_proxy"


def test_sonar_observation_is_body_frame_measurement_not_probability() -> None:
    payload = build_sonar_observation_payload(
        cable_points_ned=np.array(
            [[-10.0, 2.0, 15.0], [30.0, 2.0, 15.0]]
        ),
        position_ned=np.array([0.0, 0.0, 12.0]),
        heading_rad=0.0,
        sonar_config={
            "max_range_m": 30.0,
            "base_noise_sigma": 0.01,
            "peak_gain": 0.9,
        },
        quality_config={},
        rng=np.random.default_rng(2),
    )
    assert payload["valid"] is True
    assert len(payload["point_x_m"]) >= 8
    assert abs(float(np.median(payload["point_y_m"])) - 2.0) < 0.2
    assert "p_track" not in payload
    assert "confidence" not in payload


def test_sonar_local_branch_selection_for_curved_visible_cable() -> None:
    cable_points = np.array(
        [
            [0.0, 0.0, 12.0],
            [10.0, 7.0, 12.0],
            [20.0, 7.0, 12.0],
            [26.0, 0.0, 12.0],
            [20.0, -7.0, 12.0],
            [8.0, -7.0, 12.0],
            [0.0, 0.0, 12.0],
        ]
    )
    common = dict(
        cable_points_ned=cable_points,
        position_ned=np.array([8.0, 0.0, 12.0]),
        heading_rad=0.0,
        sonar_config={
            "max_range_m": 30.0,
            "base_noise_sigma": 0.01,
            "peak_gain": 0.9,
        },
    )
    all_visible = build_sonar_observation_payload(
        **common,
        quality_config={},
        rng=np.random.default_rng(3),
    )
    local_branch = build_sonar_observation_payload(
        **common,
        quality_config={
            "local_line_max_arc_m": 10.0,
            "local_line_min_points": 10,
        },
        rng=np.random.default_rng(3),
    )

    def residual_sigma(payload: dict[str, object]) -> float:
        points = np.column_stack(
            (
                np.asarray(payload["point_x_m"], dtype=float),
                np.asarray(payload["point_y_m"], dtype=float),
            )
        )
        center = np.mean(points, axis=0)
        scatter = (points - center).T @ (points - center) / points.shape[0]
        _, vectors = np.linalg.eigh(scatter)
        tangent = vectors[:, -1]
        normal = np.array([-tangent[1], tangent[0]])
        residual = (points - center) @ normal
        return 1.4826 * float(
            np.median(np.abs(residual - np.median(residual)))
        )

    assert local_branch["valid"] is True
    assert len(local_branch["point_x_m"]) >= 10
    assert len(local_branch["point_x_m"]) < len(all_visible["point_x_m"])
    assert residual_sigma(local_branch) < residual_sigma(all_visible) * 0.35
    assert "p_track" not in local_branch
    assert "confidence" not in local_branch

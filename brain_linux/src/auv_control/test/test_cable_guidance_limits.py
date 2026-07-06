import math

from auv_decision_ros.cable_guidance_limits import (
    GuidanceLimitConfig,
    ZigzagProbeConfig,
    apply_zigzag_probe,
    limit_guidance,
    wrap_deg,
)


def test_wrap_deg_keeps_heading_in_signed_range():
    assert wrap_deg(181.0) == -179.0
    assert wrap_deg(-181.0) == 179.0


def test_guidance_limits_heading_and_yaw_rate():
    limited = limit_guidance(
        desired_heading_deg=90.0,
        current_heading_deg=0.0,
        speed_mps=0.8,
        config=GuidanceLimitConfig(
            max_heading_delta_deg=25.0,
            max_yaw_rate_deg_s=12.0,
            min_turn_radius_m=0.0,
            max_lateral_speed_mps=0.0,
        ),
    )

    assert limited.desired_heading_deg == 12.0
    assert limited.yaw_rate_deg_s == 12.0
    assert limited.zigzag_limited is True
    assert "max_heading_delta_deg" in limited.limit_reasons
    assert "max_yaw_rate_deg_s" in limited.limit_reasons


def test_guidance_limits_turn_radius_and_lateral_speed():
    limited = limit_guidance(
        desired_heading_deg=40.0,
        current_heading_deg=0.0,
        speed_mps=1.0,
        config=GuidanceLimitConfig(
            max_heading_delta_deg=40.0,
            max_yaw_rate_deg_s=40.0,
            min_turn_radius_m=10.0,
            max_lateral_speed_mps=0.05,
        ),
    )

    assert abs(limited.yaw_rate_deg_s) <= math.degrees(1.0 / 10.0) + 1e-9
    assert abs(math.sin(math.radians(limited.yaw_rate_deg_s))) <= 0.05 + 1e-9
    assert limited.zigzag_limited is True
    assert "min_turn_radius_m" in limited.limit_reasons
    assert "max_lateral_speed_mps" in limited.limit_reasons


def test_guidance_limits_can_be_disabled():
    limited = limit_guidance(
        desired_heading_deg=30.0,
        current_heading_deg=0.0,
        speed_mps=0.8,
        config=GuidanceLimitConfig(auto_limit=False),
    )

    assert limited.desired_heading_deg == 30.0
    assert limited.yaw_rate_deg_s == 30.0
    assert limited.zigzag_limited is False


def test_zigzag_probe_converts_amplitude_to_heading_bias():
    command = apply_zigzag_probe(
        base_heading_deg=0.0,
        route_progress_m=0.0,
        speed_mps=0.8,
        probe_config=ZigzagProbeConfig(lateral_amplitude_m=1.2, wavelength_m=24.0),
        limit_config=GuidanceLimitConfig(),
    )

    assert command.active is True
    assert command.dynamics_feasible is True
    assert 17.0 < command.heading_bias_deg < 18.0
    assert math.isclose(command.desired_heading_deg, command.heading_bias_deg, abs_tol=1e-9)


def test_zigzag_probe_reports_infeasible_large_amplitude():
    command = apply_zigzag_probe(
        base_heading_deg=0.0,
        route_progress_m=0.0,
        speed_mps=0.8,
        probe_config=ZigzagProbeConfig(lateral_amplitude_m=2.0, wavelength_m=24.0),
        limit_config=GuidanceLimitConfig(max_heading_delta_deg=25.0),
    )

    assert command.active is True
    assert command.dynamics_feasible is False
    assert command.heading_bias_deg == 25.0
    assert "max_probe_heading_deg" in command.feasibility_reasons
    assert "max_heading_delta_deg" in command.feasibility_reasons

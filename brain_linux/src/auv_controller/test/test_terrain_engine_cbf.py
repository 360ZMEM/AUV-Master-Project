from __future__ import annotations

from pathlib import Path
import sys

PROJECT_SRC = Path(__file__).resolve().parents[1]
project_src_text = str(PROJECT_SRC)
if project_src_text not in sys.path:
    sys.path.insert(0, project_src_text)

from auv_controller.terrain_engine import TerrainFollower
from auv_controller.terrain_perception import BaseTerrainPerception


class _FakeTerrainPerception(BaseTerrainPerception):
    def __init__(
        self,
        *,
        depth: float,
        altitude: float,
        forward_velocity: float = 1.0,
        sonar_slope: float = 0.0,
    ) -> None:
        super().__init__()
        self._depth = float(depth)
        self._altitude = float(altitude)
        self._forward_velocity = float(forward_velocity)
        self._sonar_slope = float(sonar_slope)
        self._update_seafloor_estimate(self._depth, self._altitude)

    def get_altitude(self) -> float:
        return self._altitude

    def get_current_depth(self) -> float:
        return self._depth

    def get_forward_velocity(self) -> float:
        return self._forward_velocity

    def get_sonar_slope(self) -> float:
        return self._sonar_slope


def test_preview_cbf_limits_depth_before_shallowing_terrain() -> None:
    follower = TerrainFollower(
        lookahead_time_s=2.0,
        lpf_alpha=1.0,
        min_clearance_m=1.8,
        cbf_alpha=1.0,
        max_descend_rate_mps=20.0,
    )
    perception = _FakeTerrainPerception(
        depth=10.0,
        altitude=5.0,
        forward_velocity=2.0,
        sonar_slope=-1.0,
    )

    z_target, debug = follower.compute(perception, target_altitude_m=0.5)

    assert debug["slope_source"] == "sonar"
    assert debug["cbf_active"] is True
    assert debug["cbf_speed_scale"] == 0.0
    assert z_target <= 9.2 + 1.0e-9


def test_cbf_rate_constraint_limits_safe_but_fast_descent() -> None:
    follower = TerrainFollower(
        lookahead_time_s=2.0,
        lpf_alpha=1.0,
        min_clearance_m=1.8,
        cbf_alpha=1.0,
        cbf_dt_s=0.2,
        max_descend_rate_mps=0.5,
        slowdown_clearance_margin_m=5.0,
    )
    perception = _FakeTerrainPerception(depth=10.0, altitude=5.0)

    z_target, debug = follower.compute(perception, target_altitude_m=1.0)

    assert debug["cbf_active"] is True
    assert debug["cbf_reason"] == "barrier_or_descend_rate"
    assert abs(debug["cbf_speed_scale"] - 0.64) < 1.0e-9
    assert abs(z_target - 10.1) < 1.0e-9


def test_cbf_does_not_hold_shallow_depth_when_clearance_is_large() -> None:
    follower = TerrainFollower(
        lookahead_time_s=2.0,
        lpf_alpha=1.0,
        min_clearance_m=1.8,
        cbf_alpha=0.7,
        max_descend_rate_mps=0.4,
        slowdown_clearance_margin_m=1.5,
    )
    perception = _FakeTerrainPerception(depth=0.0, altitude=15.0)

    z_target, debug = follower.compute(perception, target_altitude_m=3.0)

    assert debug["cbf_active"] is False
    assert debug["cbf_descend_rate_limited"] is False
    assert abs(z_target - 12.0) < 1.0e-9


def test_cbf_emergency_clearance_commands_rise() -> None:
    follower = TerrainFollower(
        lookahead_time_s=2.0,
        lpf_alpha=1.0,
        min_clearance_m=1.8,
        emergency_clearance_m=1.2,
        emergency_rise_m=1.0,
        max_descend_rate_mps=20.0,
    )
    perception = _FakeTerrainPerception(depth=14.0, altitude=1.0)

    z_target, debug = follower.compute(perception, target_altitude_m=0.5)

    assert debug["cbf_active"] is True
    assert debug["cbf_reason"] == "emergency_clearance"
    assert debug["cbf_speed_scale"] == 0.0
    assert z_target <= 13.0 + 1.0e-9

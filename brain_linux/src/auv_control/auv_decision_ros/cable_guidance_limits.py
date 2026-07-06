"""Cable-tracking guidance limit helpers.

The cable tracking node publishes high-level setpoints, but the heading and
zig-zag request must still respect the vehicle dynamics envelope before the
controller/arbiter chain sees them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Any


def wrap_deg(angle_deg: float) -> float:
    return (float(angle_deg) + 180.0) % 360.0 - 180.0


def smallest_angle_error_deg(target_deg: float, current_deg: float) -> float:
    return wrap_deg(float(target_deg) - float(current_deg))


@dataclass(frozen=True)
class GuidanceLimitConfig:
    auto_limit: bool = True
    max_heading_delta_deg: float = 25.0
    max_yaw_rate_deg_s: float = 12.0
    min_turn_radius_m: float = 6.0
    max_lateral_speed_mps: float = 0.45

    @classmethod
    def from_mapping(cls, data: dict[str, Any] | None) -> "GuidanceLimitConfig":
        data = data or {}
        return cls(
            auto_limit=bool(data.get("auto_limit", True)),
            max_heading_delta_deg=float(data.get("max_heading_delta_deg", 25.0)),
            max_yaw_rate_deg_s=float(data.get("max_yaw_rate_deg_s", 12.0)),
            min_turn_radius_m=float(data.get("min_turn_radius_m", 6.0)),
            max_lateral_speed_mps=float(data.get("max_lateral_speed_mps", 0.45)),
        )


@dataclass(frozen=True)
class ZigzagProbeConfig:
    enabled: bool = True
    lateral_amplitude_m: float = 1.2
    wavelength_m: float = 24.0
    phase_offset_deg: float = 0.0
    max_probe_heading_deg: float = 25.0

    @classmethod
    def from_mapping(cls, data: dict[str, Any] | None) -> "ZigzagProbeConfig":
        data = data or {}
        return cls(
            enabled=bool(data.get("enabled", True)),
            lateral_amplitude_m=float(data.get("lateral_amplitude_m", 1.2)),
            wavelength_m=float(data.get("wavelength_m", 24.0)),
            phase_offset_deg=float(data.get("phase_offset_deg", 0.0)),
            max_probe_heading_deg=float(data.get("max_probe_heading_deg", 25.0)),
        )


@dataclass
class ZigzagProbeCommand:
    desired_heading_deg: float
    heading_bias_deg: float
    phase_rad: float
    requested_lateral_amplitude_m: float
    wavelength_m: float
    required_peak_heading_deg: float
    required_min_turn_radius_m: float
    required_peak_lateral_speed_mps: float
    dynamics_feasible: bool
    active: bool = False
    feasibility_reasons: list[str] = field(default_factory=list)


@dataclass
class LimitedGuidance:
    desired_heading_deg: float
    speed_mps: float
    yaw_rate_deg_s: float
    commanded_turn_radius_m: float
    zigzag_limited: bool = False
    limit_reasons: list[str] = field(default_factory=list)


def _sine_probe_requirements(
    *,
    lateral_amplitude_m: float,
    wavelength_m: float,
    speed_mps: float,
) -> tuple[float, float, float]:
    amplitude = abs(float(lateral_amplitude_m))
    wavelength = float(wavelength_m)
    if amplitude <= 0.0 or wavelength <= 0.0:
        return 0.0, float("inf"), 0.0
    k = 2.0 * math.pi / wavelength
    slope = amplitude * k
    heading_deg = math.degrees(math.atan(slope))
    curvature = amplitude * k * k / max((1.0 + slope * slope) ** 1.5, 1e-9)
    min_radius = 1.0 / curvature if curvature > 1e-9 else float("inf")
    lateral_speed = max(float(speed_mps), 0.0) * math.sin(math.radians(heading_deg))
    return heading_deg, min_radius, lateral_speed


def apply_zigzag_probe(
    *,
    base_heading_deg: float,
    route_progress_m: float,
    speed_mps: float,
    probe_config: ZigzagProbeConfig,
    limit_config: GuidanceLimitConfig,
) -> ZigzagProbeCommand:
    amplitude = float(probe_config.lateral_amplitude_m)
    wavelength = float(probe_config.wavelength_m)
    required_heading, required_radius, required_lateral_speed = _sine_probe_requirements(
        lateral_amplitude_m=amplitude,
        wavelength_m=wavelength,
        speed_mps=speed_mps,
    )
    reasons: list[str] = []
    if required_heading > probe_config.max_probe_heading_deg:
        reasons.append("max_probe_heading_deg")
    if required_heading > limit_config.max_heading_delta_deg:
        reasons.append("max_heading_delta_deg")
    if limit_config.min_turn_radius_m > 0.0 and required_radius < limit_config.min_turn_radius_m:
        reasons.append("min_turn_radius_m")
    if limit_config.max_lateral_speed_mps > 0.0 and required_lateral_speed > limit_config.max_lateral_speed_mps:
        reasons.append("max_lateral_speed_mps")

    active = bool(probe_config.enabled) and abs(amplitude) > 1e-9 and wavelength > 1e-9
    if not active:
        return ZigzagProbeCommand(
            desired_heading_deg=float(base_heading_deg),
            heading_bias_deg=0.0,
            phase_rad=0.0,
            requested_lateral_amplitude_m=amplitude,
            wavelength_m=wavelength,
            required_peak_heading_deg=required_heading,
            required_min_turn_radius_m=required_radius,
            required_peak_lateral_speed_mps=required_lateral_speed,
            dynamics_feasible=not reasons,
            active=False,
            feasibility_reasons=reasons,
        )

    k = 2.0 * math.pi / wavelength
    phase = k * float(route_progress_m) + math.radians(float(probe_config.phase_offset_deg))
    heading_bias = math.degrees(math.atan(amplitude * k * math.cos(phase)))
    max_heading = max(0.0, min(float(probe_config.max_probe_heading_deg), float(limit_config.max_heading_delta_deg)))
    if max_heading > 0.0 and abs(heading_bias) > max_heading:
        heading_bias = math.copysign(max_heading, heading_bias)
    return ZigzagProbeCommand(
        desired_heading_deg=wrap_deg(float(base_heading_deg) + heading_bias),
        heading_bias_deg=heading_bias,
        phase_rad=phase,
        requested_lateral_amplitude_m=amplitude,
        wavelength_m=wavelength,
        required_peak_heading_deg=required_heading,
        required_min_turn_radius_m=required_radius,
        required_peak_lateral_speed_mps=required_lateral_speed,
        dynamics_feasible=not reasons,
        active=True,
        feasibility_reasons=reasons,
    )


def limit_guidance(
    *,
    desired_heading_deg: float,
    current_heading_deg: float,
    speed_mps: float,
    config: GuidanceLimitConfig,
) -> LimitedGuidance:
    speed = max(float(speed_mps), 1e-6)
    heading_error = smallest_angle_error_deg(desired_heading_deg, current_heading_deg)
    reasons: list[str] = []

    if not config.auto_limit:
        yaw_rate = heading_error
        turn_radius = speed / max(math.radians(abs(yaw_rate)), 1e-9) if abs(yaw_rate) > 1e-9 else float("inf")
        return LimitedGuidance(float(desired_heading_deg), speed, yaw_rate, turn_radius)

    limited_error = heading_error
    if abs(limited_error) > config.max_heading_delta_deg:
        limited_error = math.copysign(config.max_heading_delta_deg, limited_error)
        reasons.append("max_heading_delta_deg")

    if abs(limited_error) > config.max_yaw_rate_deg_s:
        limited_error = math.copysign(config.max_yaw_rate_deg_s, limited_error)
        reasons.append("max_yaw_rate_deg_s")

    if config.min_turn_radius_m > 0.0:
        max_radius_yaw_rate = math.degrees(speed / config.min_turn_radius_m)
        if abs(limited_error) > max_radius_yaw_rate:
            limited_error = math.copysign(max_radius_yaw_rate, limited_error)
            reasons.append("min_turn_radius_m")

    lateral_speed = speed * abs(math.sin(math.radians(limited_error)))
    if config.max_lateral_speed_mps > 0.0 and lateral_speed > config.max_lateral_speed_mps:
        max_angle = math.degrees(math.asin(min(config.max_lateral_speed_mps / speed, 1.0)))
        limited_error = math.copysign(min(abs(limited_error), max_angle), limited_error)
        reasons.append("max_lateral_speed_mps")

    heading = wrap_deg(float(current_heading_deg) + limited_error)
    yaw_rate = limited_error
    turn_radius = speed / max(math.radians(abs(yaw_rate)), 1e-9) if abs(yaw_rate) > 1e-9 else float("inf")
    return LimitedGuidance(
        desired_heading_deg=heading,
        speed_mps=speed,
        yaw_rate_deg_s=yaw_rate,
        commanded_turn_radius_m=turn_radius,
        zigzag_limited=bool(reasons),
        limit_reasons=reasons,
    )

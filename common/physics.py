"""Shared physical constants for AUV simulation and decision systems.

This module is standard-library only and intentionally middleware-agnostic.
"""

from __future__ import annotations

# Cable magnetic baseline noise floor used by synthetic magnetometer generation.
# Unit: nT
CABLE_MAG_NOISE_FLOOR_NT: float = 0.05

# Standard gravity acceleration.
# Unit: m/s^2
GRAVITY_MPS2: float = 9.81

# Underactuated AUV actuator limits.
# Unit: percent and degree
MAX_THRUST_PERCENT: float = 100.0
MAX_RUDDER_DEG: float = 45.0

# Backward-compatible simulation default (legacy stack often uses 30 deg).
SIM_DEFAULT_MAX_RUDDER_DEG: float = 30.0

# DLT 1278-related engineering check example: buried depth error bound.
# This constant is for validation/reporting, not a hard control law.
BURIED_DEPTH_ERROR_LIMIT_M: float = 0.2


def clamp(value: float, low: float, high: float) -> float:
    """Clamp value to [low, high]."""
    return max(low, min(high, value))


def clamp_rudder_deg(value_deg: float, *, max_rudder_deg: float = MAX_RUDDER_DEG) -> float:
    """Clamp rudder angle in degrees."""
    return clamp(value_deg, -max_rudder_deg, max_rudder_deg)


def clamp_thrust_percent(value_percent: float) -> float:
    """Clamp thrust percentage."""
    return clamp(value_percent, -MAX_THRUST_PERCENT, MAX_THRUST_PERCENT)

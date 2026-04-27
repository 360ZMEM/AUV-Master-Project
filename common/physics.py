"""Shared physical constants for AUV simulation and decision systems.

This module is standard-library only and intentionally middleware-agnostic.
"""

from __future__ import annotations

# 电缆磁噪声底限，基于 DLT 1278 相关测试数据。
# Unit: nT
CABLE_MAG_NOISE_FLOOR_NT: float = 0.05

# 重力加速度常数，适用于地球表面附近的物理计算。
# Unit: m/s^2
GRAVITY_MPS2: float = 9.81

# 控制输入的物理限制常数。
# Unit: percent and degree
MAX_THRUST_PERCENT: float = 100.0
MAX_RUDDER_DEG: float = 45.0

# 仿真环境中的默认物理限制，可能与实际系统不同。
SIM_DEFAULT_MAX_RUDDER_DEG: float = 30.0

# AUV 在水下的最大安全深度，超过该深度可能导致结构损坏。
BURIED_DEPTH_ERROR_LIMIT_M: float = 0.2

# 环境边界和安全距离常数，确保 AUV 在仿真环境中保持安全操作。
SEA_BOTTOM_Z: float = 15.0
CABLE_SUSPENSION_HEIGHT: float = 1.0 # 电缆悬挂高度，单位米


def clamp(value: float, low: float, high: float) -> float:
    """Clamp value to [low, high]."""
    return max(low, min(high, value))


def clamp_rudder_deg(value_deg: float, *, max_rudder_deg: float = MAX_RUDDER_DEG) -> float:
    """Clamp rudder angle in degrees."""
    return clamp(value_deg, -max_rudder_deg, max_rudder_deg)


def clamp_thrust_percent(value_percent: float) -> float:
    """Clamp thrust percentage."""
    return clamp(value_percent, -MAX_THRUST_PERCENT, MAX_THRUST_PERCENT)

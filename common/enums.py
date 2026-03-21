"""Shared enums for behavior and fault states."""

from __future__ import annotations

from enum import Enum, IntEnum


class BehaviorMode(str, Enum):
    """Unified behavior states across simulation and ROS2 domains."""

    IDLE = "IDLE"
    DIVING = "DIVING"
    ZIGZAG_SEARCH = "ZIGZAG_SEARCH"
    PARALLEL_TRACK = "PARALLEL_TRACK"
    EMERGENCY_SURFACE = "EMERGENCY_SURFACE"


class FaultCode(str, Enum):
    """High-level fault classification for cross-module checks."""

    LEAK_DETECTED = "LEAK_DETECTED"
    LOW_VOLTAGE = "LOW_VOLTAGE"


class LeakLevel(IntEnum):
    """Leak levels aligned with current ROS2 SensorStatus conventions."""

    NONE = 0
    INTERNAL = 1
    EXTERNAL = 2
    BOTH = 3

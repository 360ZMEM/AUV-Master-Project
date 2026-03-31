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


class BridgeBackend(str, Enum):
    """Communication backends supported by the bridge layer."""

    ZENOH_JSON = "zenoh_json"
    PROTOCOL_UDP = "protocol_udp"


class ControlModeByte(IntEnum):
    """Byte-level control authority values used by the binary protocol."""

    SEND_ONLY = 0x00
    REMOTE_CONTROL = 0x01
    AUTO_FIXED_POINT = 0x02
    AUTO_DIRECTION = 0x03
    RETURN_HOME = 0x04
    JETSON_PROTOCOL = 0xEE


class WorkInstruction(IntEnum):
    """Common work instruction bytes reused by bridge implementations."""

    NONE = 0x00
    TASK_START = 0x01
    TASK_CANCEL = 0x02
    MAIN_THRUSTER_ON = 0x11
    MAIN_THRUSTER_OFF = 0x12
    SIDE_THRUSTER_ON = 0x13
    SIDE_THRUSTER_OFF = 0x14
    HORIZONTAL_RUDDER_ON = 0x15
    HORIZONTAL_RUDDER_OFF = 0x16
    VERTICAL_RUDDER_ON = 0x17
    VERTICAL_RUDDER_OFF = 0x18
    DVL_ON = 0x21
    DVL_OFF = 0x22
    COMPASS_ON = 0x23
    COMPASS_OFF = 0x24
    DIRECTIONAL_NAV_ON = 0x71
    DIRECTIONAL_NAV_OFF = 0x72
    CLEAR_FAULT = 0x91
    INITIALIZE = 0x92


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

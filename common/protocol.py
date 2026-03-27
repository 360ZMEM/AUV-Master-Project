"""Shared protocol constants and boundary validators.

All symbols in this file are standard-library only and can be imported by
simulation-side and ROS2-side code without introducing runtime coupling.
"""

from __future__ import annotations

import time
from typing import Any, Iterable

from .physics import clamp_rudder_deg, clamp_thrust_percent

# -----------------------------------------------------------------------------
# Zenoh topic paths (single source of truth)
# -----------------------------------------------------------------------------

Z_PATH_CMD_VEL = "rt/auv/control/cmd_vel"

Z_PATH_GROUND_TRUTH = "rt/auv/sensors/ground_truth"
Z_PATH_IMU = "rt/auv/sensors/imu"
Z_PATH_DVL = "rt/auv/sensors/dvl"
Z_PATH_DEPTH = "rt/auv/sensors/depth"
Z_PATH_MAGNETIC = "rt/auv/sensors/magnetic"
Z_PATH_SONAR = "rt/auv/sensors/sonar"

Z_PATH_SEABED_CLOUD = "rt/auv/visual/seabed_cloud"
Z_PATH_CABLE_MARKER = "rt/auv/visual/cable_marker"
Z_PATH_TRUTH_POSE = "rt/auv/visual/truth_pose"
Z_PATH_HISTORY_TRAIL = "rt/auv/visual/history_trail"
Z_PATH_VIEW_RANGE = "rt/auv/visual/view_range"

# -----------------------------------------------------------------------------
# Common metadata keys
# -----------------------------------------------------------------------------

KEY_STEP = "step"
KEY_SIM_TIME = "sim_time"
KEY_TS = "ts"

# -----------------------------------------------------------------------------
# Payload keys
# -----------------------------------------------------------------------------

KEY_POSITION_NED = "position_ned"
KEY_RPY_NED = "rpy_ned"
KEY_CABLE_CLOSEST_NED = "cable_closest_ned"
KEY_CABLE_DISTANCE_M = "cable_distance_m"

KEY_ACCEL_NED = "accel_ned"
KEY_GYRO_NED = "gyro_ned"

KEY_VEL_NED = "vel_ned"

KEY_DEPTH_M = "depth_m"

KEY_B_NED = "B_ned"
KEY_B_NORM = "B_norm"

KEY_SONAR_BINS = "bins"
KEY_POINTS_NED = "points_ned"
KEY_TRAIL_NED = "trail_ned"
KEY_CENTER_NED = "center_ned"
KEY_RADIUS_M = "radius_m"
KEY_HEIGHT_M = "height_m"

# Control command keys
KEY_COMMAND = "command"
KEY_RIGHT = "right"
KEY_TOP = "top"
KEY_LEFT = "left"
KEY_BOTTOM = "bottom"
KEY_THRUST = "thrust"

CONTROL_KEYS = (KEY_RIGHT, KEY_TOP, KEY_LEFT, KEY_BOTTOM, KEY_THRUST)

REQUIRED_BY_TOPIC: dict[str, tuple[str, ...]] = {
    Z_PATH_GROUND_TRUTH: (KEY_POSITION_NED, KEY_RPY_NED, KEY_CABLE_CLOSEST_NED, KEY_CABLE_DISTANCE_M),
    Z_PATH_IMU: (KEY_ACCEL_NED, KEY_GYRO_NED),
    Z_PATH_DVL: (KEY_VEL_NED,),
    Z_PATH_DEPTH: (KEY_DEPTH_M,),
    Z_PATH_MAGNETIC: (KEY_B_NED, KEY_B_NORM),
    Z_PATH_SONAR: (KEY_SONAR_BINS,),
    Z_PATH_SEABED_CLOUD: (KEY_POINTS_NED,),
    Z_PATH_CABLE_MARKER: (KEY_POINTS_NED,),
    Z_PATH_TRUTH_POSE: (KEY_POSITION_NED, KEY_RPY_NED),
    Z_PATH_HISTORY_TRAIL: (KEY_TRAIL_NED,),
    Z_PATH_VIEW_RANGE: (KEY_CENTER_NED, KEY_RADIUS_M, KEY_HEIGHT_M),
}


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_number_list(value: Any, *, length: int | None = None) -> bool:
    if not isinstance(value, list):
        return False
    if length is not None and len(value) != length:
        return False
    return all(_is_number(v) for v in value)


def _is_point_list(value: Any) -> bool:
    if not isinstance(value, list):
        return False
    return all(_is_number_list(point, length=3) for point in value)


def _missing_keys(payload: dict[str, Any], required: Iterable[str]) -> list[str]:
    return [k for k in required if k not in payload]


def enrich_meta(payload: dict[str, Any], *, step: int, sim_time: float, ts: float | None = None) -> dict[str, Any]:
    """Attach common metadata fields and return the same dict."""
    payload[KEY_STEP] = int(step)
    payload[KEY_SIM_TIME] = float(sim_time)
    payload[KEY_TS] = float(time.time() if ts is None else ts)
    return payload


def validate_sensor_payload(topic: str, payload: Any) -> tuple[bool, list[str]]:
    """Validate sensor payload shape and value types at communication boundary.

    Returns (ok, errors). Keep this function lightweight for runtime use.
    """
    errors: list[str] = []

    if not isinstance(payload, dict):
        return False, ["payload must be a dict"]

    required = REQUIRED_BY_TOPIC.get(topic)
    if required is None:
        return False, [f"unsupported topic: {topic}"]

    # DLT 1278-oriented traceability: critical telemetry fields must be explicit.
    missing = _missing_keys(payload, required)
    if missing:
        errors.append(f"missing keys: {missing}")

    if topic == Z_PATH_GROUND_TRUTH:
        if KEY_POSITION_NED in payload and not _is_number_list(payload[KEY_POSITION_NED], length=3):
            errors.append("position_ned must be list[3] of numbers")
        if KEY_RPY_NED in payload and not _is_number_list(payload[KEY_RPY_NED], length=3):
            errors.append("rpy_ned must be list[3] of numbers")
        if KEY_CABLE_CLOSEST_NED in payload and not _is_number_list(payload[KEY_CABLE_CLOSEST_NED], length=3):
            errors.append("cable_closest_ned must be list[3] of numbers")
        if KEY_CABLE_DISTANCE_M in payload and not _is_number(payload[KEY_CABLE_DISTANCE_M]):
            errors.append("cable_distance_m must be a number")

    elif topic == Z_PATH_IMU:
        if KEY_ACCEL_NED in payload and not _is_number_list(payload[KEY_ACCEL_NED], length=3):
            errors.append("accel_ned must be list[3] of numbers")
        if KEY_GYRO_NED in payload and not _is_number_list(payload[KEY_GYRO_NED], length=3):
            errors.append("gyro_ned must be list[3] of numbers")

    elif topic == Z_PATH_DVL:
        if KEY_VEL_NED in payload and not _is_number_list(payload[KEY_VEL_NED], length=3):
            errors.append("vel_ned must be list[3] of numbers")

    elif topic == Z_PATH_DEPTH:
        if KEY_DEPTH_M in payload and not _is_number(payload[KEY_DEPTH_M]):
            errors.append("depth_m must be a number")

    elif topic == Z_PATH_MAGNETIC:
        if KEY_B_NED in payload and not _is_number_list(payload[KEY_B_NED], length=3):
            errors.append("B_ned must be list[3] of numbers")
        if KEY_B_NORM in payload and not _is_number(payload[KEY_B_NORM]):
            errors.append("B_norm must be a number")

    elif topic == Z_PATH_SONAR:
        if KEY_SONAR_BINS in payload and not _is_number_list(payload[KEY_SONAR_BINS]):
            errors.append("bins must be list of numbers")

    elif topic == Z_PATH_SEABED_CLOUD:
        if KEY_POINTS_NED in payload and not _is_point_list(payload[KEY_POINTS_NED]):
            errors.append("points_ned must be list[list[3] of numbers]")

    elif topic == Z_PATH_CABLE_MARKER:
        if KEY_POINTS_NED in payload and not _is_point_list(payload[KEY_POINTS_NED]):
            errors.append("points_ned must be list[list[3] of numbers]")

    elif topic == Z_PATH_TRUTH_POSE:
        if KEY_POSITION_NED in payload and not _is_number_list(payload[KEY_POSITION_NED], length=3):
            errors.append("position_ned must be list[3] of numbers")
        if KEY_RPY_NED in payload and not _is_number_list(payload[KEY_RPY_NED], length=3):
            errors.append("rpy_ned must be list[3] of numbers")

    elif topic == Z_PATH_HISTORY_TRAIL:
        if KEY_TRAIL_NED in payload and not _is_point_list(payload[KEY_TRAIL_NED]):
            errors.append("trail_ned must be list[list[3] of numbers]")

    elif topic == Z_PATH_VIEW_RANGE:
        if KEY_CENTER_NED in payload and not _is_number_list(payload[KEY_CENTER_NED], length=3):
            errors.append("center_ned must be list[3] of numbers")
        if KEY_RADIUS_M in payload and not _is_number(payload[KEY_RADIUS_M]):
            errors.append("radius_m must be a number")
        if KEY_HEIGHT_M in payload and not _is_number(payload[KEY_HEIGHT_M]):
            errors.append("height_m must be a number")

    if KEY_STEP in payload and not isinstance(payload[KEY_STEP], int):
        errors.append("step must be int")
    if KEY_SIM_TIME in payload and not _is_number(payload[KEY_SIM_TIME]):
        errors.append("sim_time must be a number")
    if KEY_TS in payload and not _is_number(payload[KEY_TS]):
        errors.append("ts must be a number")

    return len(errors) == 0, errors


def normalize_control_command(payload: Any) -> dict[str, float]:
    """Normalize supported control command forms to a canonical dict.

    Supported inputs:
    - {"command": [right, top, left, bottom, thrust]}
    - {"right": ..., "top": ..., "left": ..., "bottom": ..., "thrust": ...}
    - [right, top, left, bottom, thrust]
    """
    cmd: Any

    if isinstance(payload, dict) and KEY_COMMAND in payload:
        cmd = payload[KEY_COMMAND]
    else:
        cmd = payload

    if isinstance(cmd, (list, tuple)):
        if len(cmd) != 5:
            raise ValueError("command list length must be 5")
        right, top, left, bottom, thrust = cmd
    elif isinstance(cmd, dict):
        missing = _missing_keys(cmd, CONTROL_KEYS)
        if missing:
            raise ValueError(f"missing control keys: {missing}")
        right = cmd[KEY_RIGHT]
        top = cmd[KEY_TOP]
        left = cmd[KEY_LEFT]
        bottom = cmd[KEY_BOTTOM]
        thrust = cmd[KEY_THRUST]
    else:
        raise ValueError("unsupported control payload format")

    values = [right, top, left, bottom, thrust]
    if not all(_is_number(v) for v in values):
        raise ValueError("control values must be numeric")

    return {
        KEY_RIGHT: float(clamp_rudder_deg(float(right))),
        KEY_TOP: float(clamp_rudder_deg(float(top))),
        KEY_LEFT: float(clamp_rudder_deg(float(left))),
        KEY_BOTTOM: float(clamp_rudder_deg(float(bottom))),
        KEY_THRUST: float(clamp_thrust_percent(float(thrust))),
    }


def validate_control_payload(payload: Any) -> tuple[bool, list[str]]:
    """Validate and normalize control payload for safe actuation boundary."""
    try:
        normalize_control_command(payload)
    except Exception as exc:  # broad by design to keep caller lightweight
        return False, [str(exc)]
    return True, []

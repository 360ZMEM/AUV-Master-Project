"""Shared protocol constants and boundary validators.

All symbols in this file are standard-library only and can be imported by
simulation-side and ROS2-side code without introducing runtime coupling.
"""

from __future__ import annotations

import struct
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable, Sequence

from .enums import ArbiterMode, ArbiterSource, AutoState, DenyReason
from .physics import clamp_rudder_deg, clamp_thrust_percent

# -----------------------------------------------------------------------------
# Zenoh topic paths (single source of truth)
# -----------------------------------------------------------------------------

Z_PATH_CMD_VEL = "rt/auv/control/cmd_vel"
Z_PATH_PC_CMD_RAW = "rt/pc/cmd_raw"
Z_PATH_AUV_TELEMETRY = "rt/auv/telemetry"
Z_PATH_AUV_VIZ_INTERNAL = "rt/auv/viz/internal"
Z_PATH_AUV_STATE_RAW_DR = "rt/auv/state/raw_dr"

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
Z_PATH_MOCK_AMD_TIME = "rt/auv/mock_amd/time"

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
KEY_CONFIDENCE = "confidence"
KEY_LEAK_LEVEL = "leak_level"
KEY_TOTAL_VOLTAGE_V = "total_voltage_v"

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
KEY_SOURCE = "source"
KEY_VALID = "valid"
KEY_HEALTHY = "healthy"
KEY_NOTE = "note"
KEY_RIGHT = "right"
KEY_TOP = "top"
KEY_LEFT = "left"
KEY_BOTTOM = "bottom"
KEY_THRUST = "thrust"
KEY_FRAME_NUMBER = "frame_number"
KEY_OBJ_ADDRESS = "obj_address"
KEY_AUV_ADDRESS = "auv_address"
KEY_CONTROL_MODE_BYTE = "control_mode_byte"
KEY_WORK_INSTRUCTION = "work_instruction"
KEY_ORIENTATION_DEG = "orientation_deg"
KEY_MAIN_MOTOR_RPM = "main_motor_rpm"
KEY_SIDE_MOTOR_RPM = "side_motor_rpm"
KEY_DEPTH_PROTECT_PARAMS = "depth_protect_params"
KEY_BOTTOM_PROTECT_PARAMS = "bottom_protect_params"
KEY_PRESET_TIME_TENTHS_MIN = "preset_time_tenths_min"
KEY_SPARE_PARAMS = "spare_params"
KEY_PARAMETERS = "parameters"
KEY_ACTIVE_ARBITER = "active_arbiter"
KEY_ARBITER_SOURCE = "arbiter_source"
KEY_AUTO_STATE = "auto_state"
KEY_DENY_REASON = "deny_reason"
KEY_TELEMETRY_FRESHNESS_MS = "telemetry_freshness_ms"
KEY_STATE_SOURCE = "state_source"
KEY_MOCK_AMD_TIMESTAMP = "mock_amd_timestamp_us"

# -----------------------------------------------------------------------------
# Binary protocol byte offsets for Para1-12 (reserved tuning fields)
# -----------------------------------------------------------------------------

PROTOCOL_DOWNLINK_PARA1_OFFSET = 37
PROTOCOL_DOWNLINK_PARA2_OFFSET = 41
PROTOCOL_DOWNLINK_PARA3_OFFSET = 45
PROTOCOL_DOWNLINK_PARA4_OFFSET = 49
PROTOCOL_DOWNLINK_PARA5_OFFSET = 53
PROTOCOL_DOWNLINK_PARA6_OFFSET = 55
PROTOCOL_DOWNLINK_PARA7_OFFSET = 57
PROTOCOL_DOWNLINK_PARA8_OFFSET = 59
PROTOCOL_DOWNLINK_PARA9_OFFSET = 61
PROTOCOL_DOWNLINK_PARA10_OFFSET = 63
PROTOCOL_DOWNLINK_PARA11_OFFSET = 65
PROTOCOL_DOWNLINK_PARA12_OFFSET = 67

PROTOCOL_UPLINK_PARA1_OFFSET = 40
PROTOCOL_UPLINK_PARA2_OFFSET = 44
PROTOCOL_UPLINK_PARA3_OFFSET = 48
PROTOCOL_UPLINK_PARA4_OFFSET = 52
PROTOCOL_UPLINK_PARA5_OFFSET = 56
PROTOCOL_UPLINK_PARA6_OFFSET = 58
PROTOCOL_UPLINK_PARA7_OFFSET = 60
PROTOCOL_UPLINK_PARA8_OFFSET = 62
PROTOCOL_UPLINK_PARA9_OFFSET = 64
PROTOCOL_UPLINK_PARA10_OFFSET = 66
PROTOCOL_UPLINK_PARA11_OFFSET = 68
PROTOCOL_UPLINK_PARA12_OFFSET = 70

CONTROL_KEYS = (KEY_RIGHT, KEY_TOP, KEY_LEFT, KEY_BOTTOM, KEY_THRUST)

# -----------------------------------------------------------------------------
# Binary AUV protocol constants
# -----------------------------------------------------------------------------

PROTOCOL_DOWNLINK_HEADER = b"$CKTH"
PROTOCOL_UPLINK_HEADER = bytes((0x24, 0x41, 0x55, 0x56, 0x91))
PROTOCOL_FRAME_TAIL = bytes((0xFF, 0xFF))

PROTOCOL_DOWNLINK_SIZE = 72
PROTOCOL_UPLINK_SIZE = 145

PROTOCOL_DOWNLINK_CHECKSUM_INDEX = 69
PROTOCOL_UPLINK_CHECKSUM_INDEX = 142

DEFAULT_MAIN_MOTOR_RPM_SCALE = 15.0
DEFAULT_SIDE_MOTOR_RPM_SCALE = 1.0


@dataclass(frozen=True)
class ProtocolDownlinkState:
    """Decoded $CKTH downlink state in engineering units."""

    frame_number: int
    obj_address: int
    control_mode_byte: int
    work_instruction: int
    right_fin_deg: float
    top_fin_deg: float
    left_fin_deg: float
    bottom_fin_deg: float
    thrust_percent: float
    main_motor_rpm: int
    side_motor_rpm: int
    orientation_deg: float
    depth_protect_params: tuple[int, int]
    bottom_protect_params: tuple[int, int]
    preset_time_tenths_min: int
    spare_params: tuple[int, int]
    parameters: tuple[int, ...]
    mock_amd_timestamp_us: int = 0


@dataclass(frozen=True)
class ProtocolUplinkTelemetry:
    """Decoded $AUV telemetry in engineering units."""

    frame_number: int
    auv_address: int
    control_mode_byte: int
    work_instruction: int
    main_motor_rpm: int
    side_motor_rpm: int
    right_fin_deg: float
    top_fin_deg: float
    left_fin_deg: float
    bottom_fin_deg: float
    orientation_deg: float
    internal_pressure_psi: float
    internal_temp_c: int
    depth_m: float
    heading_deg: float
    pitch_deg: float
    roll_deg: float
    gps_heading_deg: float
    gps_speed_mps: float
    dvl_speed_mps: float
    altitude_m: float
    dead_reckoning_lon_deg: float
    dead_reckoning_lat_deg: float
    gps_lon_deg: float
    gps_lat_deg: float
    total_voltage_v: float
    total_current_a: float
    soc: int
    soh: int
    device_power_status: int
    operation_feedback: int
    task_status: int
    system_alarm: int
    depth_alarm: int
    bottom_alarm: int

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


def _enum_value(value: Enum | str | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, Enum):
        return str(value.value)
    return str(value)


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


def downlink_state_to_payload(state: ProtocolDownlinkState) -> dict[str, Any]:
    """Convert decoded $CKTH state into a canonical dict for arbitration."""
    return {
        KEY_FRAME_NUMBER: int(state.frame_number),
        KEY_OBJ_ADDRESS: int(state.obj_address),
        KEY_CONTROL_MODE_BYTE: int(state.control_mode_byte),
        KEY_WORK_INSTRUCTION: int(state.work_instruction),
        KEY_RIGHT: float(state.right_fin_deg),
        KEY_TOP: float(state.top_fin_deg),
        KEY_LEFT: float(state.left_fin_deg),
        KEY_BOTTOM: float(state.bottom_fin_deg),
        KEY_THRUST: float(state.thrust_percent),
        KEY_MAIN_MOTOR_RPM: int(state.main_motor_rpm),
        KEY_SIDE_MOTOR_RPM: int(state.side_motor_rpm),
        KEY_ORIENTATION_DEG: float(state.orientation_deg),
        KEY_DEPTH_PROTECT_PARAMS: tuple(state.depth_protect_params),
        KEY_BOTTOM_PROTECT_PARAMS: tuple(state.bottom_protect_params),
        KEY_PRESET_TIME_TENTHS_MIN: int(state.preset_time_tenths_min),
        KEY_SPARE_PARAMS: tuple(state.spare_params),
        KEY_PARAMETERS: tuple(state.parameters),
    }


def parse_downlink_packet_to_payload(
    packet: bytes,
    *,
    main_motor_rpm_scale: float = DEFAULT_MAIN_MOTOR_RPM_SCALE,
) -> dict[str, Any]:
    """Decode raw $CKTH bytes into the shared arbitration payload shape."""
    return downlink_state_to_payload(parse_downlink_packet(packet, main_motor_rpm_scale=main_motor_rpm_scale))


def build_downlink_packet_from_payload(
    payload: Any,
    *,
    main_motor_rpm_scale: float = DEFAULT_MAIN_MOTOR_RPM_SCALE,
) -> bytes:
    """Build $CKTH bytes from the shared arbitration payload shape."""
    if not isinstance(payload, dict):
        return build_downlink_packet(payload, main_motor_rpm_scale=main_motor_rpm_scale)

    return build_downlink_packet(
        payload,
        frame_counter=int(payload.get(KEY_FRAME_NUMBER, 0)),
        obj_address=int(payload.get(KEY_OBJ_ADDRESS, 1)),
        control_mode_byte=int(payload.get(KEY_CONTROL_MODE_BYTE, 0x01)),
        work_instruction=int(payload.get(KEY_WORK_INSTRUCTION, 0x00)),
        orientation_deg=float(payload.get(KEY_ORIENTATION_DEG, 0.0)),
        depth_protect_params=payload.get(KEY_DEPTH_PROTECT_PARAMS),
        bottom_protect_params=payload.get(KEY_BOTTOM_PROTECT_PARAMS),
        preset_time_tenths_min=int(payload.get(KEY_PRESET_TIME_TENTHS_MIN, 0)),
        spare_params=payload.get(KEY_SPARE_PARAMS),
        parameter_values=payload.get(KEY_PARAMETERS),
        main_motor_rpm_scale=main_motor_rpm_scale,
        side_motor_rpm=int(payload.get(KEY_SIDE_MOTOR_RPM, 0)),
    )


def build_bridge_telemetry_payload(
    telemetry: ProtocolUplinkTelemetry,
    *,
    ts: float | None = None,
    active_arbiter: ArbiterMode | str | None = None,
    arbiter_source: ArbiterSource | str | None = None,
    auto_state: AutoState | str | None = None,
    deny_reason: DenyReason | str | None = None,
    telemetry_freshness_ms: float | None = None,
) -> dict[str, Any]:
    """Convert decoded $AUV telemetry into the shared bridge feedback payload."""
    payload = {
        KEY_TS: float(time.time() if ts is None else ts),
        KEY_FRAME_NUMBER: int(telemetry.frame_number),
        KEY_AUV_ADDRESS: int(telemetry.auv_address),
        KEY_CONTROL_MODE_BYTE: int(telemetry.control_mode_byte),
        KEY_WORK_INSTRUCTION: int(telemetry.work_instruction),
        KEY_MAIN_MOTOR_RPM: int(telemetry.main_motor_rpm),
        KEY_SIDE_MOTOR_RPM: int(telemetry.side_motor_rpm),
        KEY_RIGHT: float(telemetry.right_fin_deg),
        KEY_TOP: float(telemetry.top_fin_deg),
        KEY_LEFT: float(telemetry.left_fin_deg),
        KEY_BOTTOM: float(telemetry.bottom_fin_deg),
        KEY_ORIENTATION_DEG: float(telemetry.orientation_deg),
        "internal_pressure_psi": float(telemetry.internal_pressure_psi),
        "internal_temp_c": int(telemetry.internal_temp_c),
        KEY_DEPTH_M: float(telemetry.depth_m),
        "heading_deg": float(telemetry.heading_deg),
        "pitch_deg": float(telemetry.pitch_deg),
        "roll_deg": float(telemetry.roll_deg),
        "gps_heading_deg": float(telemetry.gps_heading_deg),
        "gps_speed_mps": float(telemetry.gps_speed_mps),
        "dvl_speed_mps": float(telemetry.dvl_speed_mps),
        "altitude_m": float(telemetry.altitude_m),
        "dead_reckoning_lon_deg": float(telemetry.dead_reckoning_lon_deg),
        "dead_reckoning_lat_deg": float(telemetry.dead_reckoning_lat_deg),
        "gps_lon_deg": float(telemetry.gps_lon_deg),
        "gps_lat_deg": float(telemetry.gps_lat_deg),
        KEY_TOTAL_VOLTAGE_V: float(telemetry.total_voltage_v),
        "total_current_a": float(telemetry.total_current_a),
        "soc": int(telemetry.soc),
        "soh": int(telemetry.soh),
        "device_power_status": int(telemetry.device_power_status),
        "operation_feedback": int(telemetry.operation_feedback),
        "task_status": int(telemetry.task_status),
        "system_alarm": int(telemetry.system_alarm),
        "depth_alarm": int(telemetry.depth_alarm),
        "bottom_alarm": int(telemetry.bottom_alarm),
    }

    active_arbiter_value = _enum_value(active_arbiter)
    if active_arbiter_value is not None:
        payload[KEY_ACTIVE_ARBITER] = active_arbiter_value

    arbiter_source_value = _enum_value(arbiter_source)
    if arbiter_source_value is not None:
        payload[KEY_ARBITER_SOURCE] = arbiter_source_value

    auto_state_value = _enum_value(auto_state)
    if auto_state_value is not None:
        payload[KEY_AUTO_STATE] = auto_state_value

    deny_reason_value = _enum_value(deny_reason)
    if deny_reason_value is not None:
        payload[KEY_DENY_REASON] = deny_reason_value

    if telemetry_freshness_ms is not None:
        payload[KEY_TELEMETRY_FRESHNESS_MS] = float(telemetry_freshness_ms)

    return payload


def calculate_byte_sum_checksum(data: bytes | bytearray) -> int:
    """Return the protocol checksum as low 8 bits of the byte sum."""
    return sum(data) & 0xFF


def _clamp_int(value: int, low: int, high: int) -> int:
    return max(low, min(high, int(value)))


def _coerce_pair(values: Sequence[int] | None, *, low: int, high: int) -> tuple[int, int]:
    if values is None:
        return 0, 0
    if len(values) != 2:
        raise ValueError("expected exactly 2 values")
    return (_clamp_int(values[0], low, high), _clamp_int(values[1], low, high))


def _coerce_parameters(values: Sequence[int] | None) -> tuple[int, ...]:
    if values is None:
        return (0,) * 12
    if len(values) != 12:
        raise ValueError("expected exactly 12 parameter values")
    packed = [
        _clamp_int(values[0], -2147483648, 2147483647),
        _clamp_int(values[1], -2147483648, 2147483647),
        _clamp_int(values[2], -2147483648, 2147483647),
        _clamp_int(values[3], -2147483648, 2147483647),
    ]
    packed.extend(_clamp_int(value, -32768, 32767) for value in values[4:])
    return tuple(packed)


def _validate_frame(packet: bytes | bytearray, *, expected_size: int, header: bytes, checksum_index: int) -> None:
    if len(packet) != expected_size:
        raise ValueError(f"packet length must be {expected_size}, got {len(packet)}")
    if bytes(packet[: len(header)]) != header:
        raise ValueError("packet header mismatch")
    if bytes(packet[-2:]) != PROTOCOL_FRAME_TAIL:
        raise ValueError("packet tail mismatch")
    checksum = calculate_byte_sum_checksum(packet[:checksum_index])
    if int(packet[checksum_index]) != checksum:
        raise ValueError(
            f"checksum mismatch: expected 0x{checksum:02X}, got 0x{int(packet[checksum_index]):02X}"
        )


def build_downlink_packet(
    command_payload: Any,
    *,
    frame_counter: int = 0,
    obj_address: int = 1,
    control_mode_byte: int = 0x01,
    work_instruction: int = 0x00,
    orientation_deg: float = 0.0,
    depth_protect_params: Sequence[int] | None = None,
    bottom_protect_params: Sequence[int] | None = None,
    preset_time_tenths_min: int = 0,
    spare_params: Sequence[int] | None = None,
    parameter_values: Sequence[int] | None = None,
    main_motor_rpm_scale: float = DEFAULT_MAIN_MOTOR_RPM_SCALE,
    side_motor_rpm: int = 0,
) -> bytes:
    """Build a 72-byte $CKTH command frame from canonical control payload."""
    normalized = normalize_control_command(command_payload)
    depth_pair = _coerce_pair(depth_protect_params, low=0, high=65535)
    bottom_pair = _coerce_pair(bottom_protect_params, low=0, high=65535)
    spare_pair = _coerce_pair(spare_params, low=-32768, high=32767)
    parameters = _coerce_parameters(parameter_values)

    packet = bytearray(PROTOCOL_DOWNLINK_SIZE)
    packet[0:5] = PROTOCOL_DOWNLINK_HEADER
    packet[5] = frame_counter & 0xFF
    packet[6] = obj_address & 0xFF
    packet[7] = control_mode_byte & 0xFF

    struct.pack_into(">H", packet, 8, depth_pair[0])
    struct.pack_into(">H", packet, 10, depth_pair[1])
    struct.pack_into(">H", packet, 12, bottom_pair[0])
    struct.pack_into(">H", packet, 14, bottom_pair[1])
    struct.pack_into(">H", packet, 16, _clamp_int(preset_time_tenths_min, 0, 65535))
    struct.pack_into(">h", packet, 18, spare_pair[0])
    struct.pack_into(">h", packet, 20, spare_pair[1])
    packet[22] = work_instruction & 0xFF

    main_motor_rpm = _clamp_int(round(normalized[KEY_THRUST] * main_motor_rpm_scale), -32768, 32767)
    struct.pack_into(">h", packet, 23, main_motor_rpm)
    struct.pack_into(">h", packet, 25, _clamp_int(side_motor_rpm, -32768, 32767))
    struct.pack_into(">h", packet, 27, _clamp_int(round(normalized[KEY_LEFT] * 10.0), -32768, 32767))
    struct.pack_into(">h", packet, 29, _clamp_int(round(normalized[KEY_RIGHT] * 10.0), -32768, 32767))
    struct.pack_into(">h", packet, 31, _clamp_int(round(normalized[KEY_TOP] * 10.0), -32768, 32767))
    struct.pack_into(">h", packet, 33, _clamp_int(round(normalized[KEY_BOTTOM] * 10.0), -32768, 32767))
    struct.pack_into(">H", packet, 35, _clamp_int(round(orientation_deg * 10.0), 0, 65535))

    struct.pack_into(">i", packet, 37, parameters[0])
    struct.pack_into(">i", packet, 41, parameters[1])
    struct.pack_into(">i", packet, 45, parameters[2])
    struct.pack_into(">i", packet, 49, parameters[3])
    struct.pack_into(">h", packet, 53, parameters[4])
    struct.pack_into(">h", packet, 55, parameters[5])
    struct.pack_into(">h", packet, 57, parameters[6])
    struct.pack_into(">h", packet, 59, parameters[7])
    struct.pack_into(">h", packet, 61, parameters[8])
    struct.pack_into(">h", packet, 63, parameters[9])
    struct.pack_into(">h", packet, 65, parameters[10])
    struct.pack_into(">h", packet, 67, parameters[11])

    packet[PROTOCOL_DOWNLINK_CHECKSUM_INDEX] = calculate_byte_sum_checksum(packet[:PROTOCOL_DOWNLINK_CHECKSUM_INDEX])
    packet[-2:] = PROTOCOL_FRAME_TAIL
    return bytes(packet)


def parse_downlink_packet(
    packet: bytes,
    *,
    main_motor_rpm_scale: float = DEFAULT_MAIN_MOTOR_RPM_SCALE,
) -> ProtocolDownlinkState:
    """Decode a 72-byte $CKTH frame into engineering units."""
    _validate_frame(
        packet,
        expected_size=PROTOCOL_DOWNLINK_SIZE,
        header=PROTOCOL_DOWNLINK_HEADER,
        checksum_index=PROTOCOL_DOWNLINK_CHECKSUM_INDEX,
    )

    main_motor_rpm = struct.unpack(">h", packet[23:25])[0]
    mock_amd_timestamp_us = struct.unpack(">i", packet[PROTOCOL_DOWNLINK_PARA1_OFFSET:PROTOCOL_DOWNLINK_PARA1_OFFSET + 4])[0]
    return ProtocolDownlinkState(
        frame_number=int(packet[5]),
        obj_address=int(packet[6]),
        control_mode_byte=int(packet[7]),
        work_instruction=int(packet[22]),
        right_fin_deg=struct.unpack(">h", packet[29:31])[0] * 0.1,
        top_fin_deg=struct.unpack(">h", packet[31:33])[0] * 0.1,
        left_fin_deg=struct.unpack(">h", packet[27:29])[0] * 0.1,
        bottom_fin_deg=struct.unpack(">h", packet[33:35])[0] * 0.1,
        thrust_percent=(main_motor_rpm / main_motor_rpm_scale) if main_motor_rpm_scale else 0.0,
        main_motor_rpm=main_motor_rpm,
        side_motor_rpm=struct.unpack(">h", packet[25:27])[0],
        orientation_deg=struct.unpack(">H", packet[35:37])[0] * 0.1,
        depth_protect_params=(struct.unpack(">H", packet[8:10])[0], struct.unpack(">H", packet[10:12])[0]),
        bottom_protect_params=(struct.unpack(">H", packet[12:14])[0], struct.unpack(">H", packet[14:16])[0]),
        preset_time_tenths_min=struct.unpack(">H", packet[16:18])[0],
        spare_params=(struct.unpack(">h", packet[18:20])[0], struct.unpack(">h", packet[20:22])[0]),
        parameters=(
            mock_amd_timestamp_us,
            struct.unpack(">i", packet[41:45])[0],
            struct.unpack(">i", packet[45:49])[0],
            struct.unpack(">i", packet[49:53])[0],
            struct.unpack(">h", packet[53:55])[0],
            struct.unpack(">h", packet[55:57])[0],
            struct.unpack(">h", packet[57:59])[0],
            struct.unpack(">h", packet[59:61])[0],
            struct.unpack(">h", packet[61:63])[0],
            struct.unpack(">h", packet[63:65])[0],
            struct.unpack(">h", packet[65:67])[0],
            struct.unpack(">h", packet[67:69])[0],
        ),
        mock_amd_timestamp_us=mock_amd_timestamp_us,
    )


def build_uplink_packet(
    *,
    frame_counter: int = 0,
    auv_address: int = 1,
    control_mode_byte: int = 0x01,
    work_instruction: int = 0x00,
    main_motor_rpm: int = 0,
    side_motor_rpm: int = 0,
    left_fin_deg: float = 0.0,
    right_fin_deg: float = 0.0,
    top_fin_deg: float = 0.0,
    bottom_fin_deg: float = 0.0,
    orientation_deg: float = 0.0,
    depth_m: float = 0.0,
    heading_deg: float = 0.0,
    pitch_deg: float = 0.0,
    roll_deg: float = 0.0,
    gps_heading_deg: float = 0.0,
    gps_speed_mps: float = 0.0,
    dvl_speed_mps: float = 0.0,
    altitude_m: float = 0.0,
    dead_reckoning_lon_deg: float = 0.0,
    dead_reckoning_lat_deg: float = 0.0,
    gps_lon_deg: float = 0.0,
    gps_lat_deg: float = 0.0,
    total_voltage_v: float = 48.0,
    total_current_a: float = 0.0,
    soc: int = 100,
    soh: int = 100,
    internal_pressure_psi: float = 0.0,
    internal_temp_c: int = 20,
    device_power_status: int = 0,
    operation_feedback: int = 0,
    task_status: int = 0,
    system_alarm: int = 0,
    depth_alarm: int = 0,
    bottom_alarm: int = 0,
    parameter_values: Sequence[int] | None = None,
) -> bytes:
    """Build a 145-byte $AUV telemetry frame."""
    parameters = _coerce_parameters(parameter_values)
    packet = bytearray(PROTOCOL_UPLINK_SIZE)
    packet[0:5] = PROTOCOL_UPLINK_HEADER
    packet[5] = frame_counter & 0xFF
    packet[6] = auv_address & 0xFF
    packet[7] = control_mode_byte & 0xFF

    struct.pack_into(">H", packet, 8, 0)
    struct.pack_into(">H", packet, 10, 0)
    struct.pack_into(">H", packet, 12, 0)
    struct.pack_into(">H", packet, 14, 0)
    struct.pack_into(">H", packet, 16, 0)
    struct.pack_into(">h", packet, 18, 0)
    struct.pack_into(">h", packet, 20, 0)
    packet[22] = work_instruction & 0xFF

    struct.pack_into(">h", packet, 23, _clamp_int(main_motor_rpm, -32768, 32767))
    struct.pack_into(">h", packet, 25, _clamp_int(side_motor_rpm, -32768, 32767))
    struct.pack_into(">h", packet, 27, _clamp_int(round(left_fin_deg * 10.0), -32768, 32767))
    struct.pack_into(">h", packet, 29, _clamp_int(round(right_fin_deg * 10.0), -32768, 32767))
    struct.pack_into(">h", packet, 31, _clamp_int(round(top_fin_deg * 10.0), -32768, 32767))
    struct.pack_into(">h", packet, 33, _clamp_int(round(bottom_fin_deg * 10.0), -32768, 32767))
    struct.pack_into(">H", packet, 35, _clamp_int(round(orientation_deg * 10.0), 0, 65535))

    struct.pack_into(">i", packet, 40, parameters[0])
    struct.pack_into(">i", packet, 44, parameters[1])
    struct.pack_into(">i", packet, 48, parameters[2])
    struct.pack_into(">i", packet, 52, parameters[3])
    struct.pack_into(">h", packet, 56, parameters[4])
    struct.pack_into(">h", packet, 58, parameters[5])
    struct.pack_into(">h", packet, 60, parameters[6])
    struct.pack_into(">h", packet, 62, parameters[7])
    struct.pack_into(">h", packet, 64, parameters[8])
    struct.pack_into(">h", packet, 66, parameters[9])
    struct.pack_into(">h", packet, 68, parameters[10])
    struct.pack_into(">h", packet, 70, parameters[11])

    struct.pack_into(">h", packet, 35, _clamp_int(round(internal_pressure_psi * 1000.0), -32768, 32767))
    packet[37] = _clamp_int(internal_temp_c, -128, 127) & 0xFF
    struct.pack_into(">H", packet, 38, _clamp_int(round(depth_m * 10.0), 0, 65535))
    struct.pack_into(">h", packet, 72, _clamp_int(round(heading_deg * 10.0), -32768, 32767))
    struct.pack_into(">h", packet, 74, _clamp_int(round(pitch_deg * 10.0), -32768, 32767))
    struct.pack_into(">h", packet, 76, _clamp_int(round(roll_deg * 10.0), -32768, 32767))
    struct.pack_into(">H", packet, 78, _clamp_int(round(gps_heading_deg * 10.0), 0, 65535))
    struct.pack_into(">H", packet, 80, _clamp_int(round(gps_speed_mps * 10.0), 0, 65535))
    struct.pack_into(">h", packet, 82, _clamp_int(round(dvl_speed_mps * 10.0), -32768, 32767))
    struct.pack_into(">H", packet, 84, _clamp_int(round(altitude_m * 10.0), 0, 65535))
    struct.pack_into(">i", packet, 86, _clamp_int(round(dead_reckoning_lon_deg * 1_000_000.0), -2147483648, 2147483647))
    struct.pack_into(">i", packet, 90, _clamp_int(round(dead_reckoning_lat_deg * 1_000_000.0), -2147483648, 2147483647))
    struct.pack_into(">i", packet, 94, _clamp_int(round(gps_lon_deg * 1_000_000.0), -2147483648, 2147483647))
    struct.pack_into(">i", packet, 98, _clamp_int(round(gps_lat_deg * 1_000_000.0), -2147483648, 2147483647))
    struct.pack_into(">H", packet, 102, _clamp_int(round(total_voltage_v * 10.0), 0, 65535))
    struct.pack_into(">H", packet, 104, _clamp_int(round(total_current_a * 10.0), 0, 65535))
    packet[106] = _clamp_int(soc, 0, 100) & 0xFF
    packet[107] = _clamp_int(soh, 0, 100) & 0xFF
    struct.pack_into(">H", packet, 108, 0)
    struct.pack_into(">H", packet, 110, 0)
    packet[112] = 0
    packet[113] = 0
    struct.pack_into(">I", packet, 114, _clamp_int(device_power_status, 0, 0xFFFFFFFF))
    struct.pack_into(">I", packet, 118, _clamp_int(operation_feedback, 0, 0xFFFFFFFF))
    struct.pack_into(">I", packet, 122, _clamp_int(task_status, 0, 0xFFFFFFFF))
    packet[127] = system_alarm & 0xFF
    packet[128] = depth_alarm & 0xFF
    packet[129] = bottom_alarm & 0xFF

    packet[PROTOCOL_UPLINK_CHECKSUM_INDEX] = calculate_byte_sum_checksum(packet[:PROTOCOL_UPLINK_CHECKSUM_INDEX])
    packet[-2:] = PROTOCOL_FRAME_TAIL
    return bytes(packet)


def parse_uplink_packet(packet: bytes) -> ProtocolUplinkTelemetry:
    """Decode a 145-byte $AUV telemetry frame."""
    _validate_frame(
        packet,
        expected_size=PROTOCOL_UPLINK_SIZE,
        header=PROTOCOL_UPLINK_HEADER,
        checksum_index=PROTOCOL_UPLINK_CHECKSUM_INDEX,
    )

    return ProtocolUplinkTelemetry(
        frame_number=int(packet[5]),
        auv_address=int(packet[6]),
        control_mode_byte=int(packet[7]),
        work_instruction=int(packet[22]),
        main_motor_rpm=struct.unpack(">h", packet[23:25])[0],
        side_motor_rpm=struct.unpack(">h", packet[25:27])[0],
        right_fin_deg=struct.unpack(">h", packet[29:31])[0] * 0.1,
        top_fin_deg=struct.unpack(">h", packet[31:33])[0] * 0.1,
        left_fin_deg=struct.unpack(">h", packet[27:29])[0] * 0.1,
        bottom_fin_deg=struct.unpack(">h", packet[33:35])[0] * 0.1,
        orientation_deg=struct.unpack(">H", packet[35:37])[0] * 0.1,
        internal_pressure_psi=struct.unpack(">h", packet[35:37])[0] * 0.001,
        internal_temp_c=struct.unpack("b", bytes((packet[37],)))[0],
        depth_m=struct.unpack(">H", packet[38:40])[0] * 0.1,
        heading_deg=struct.unpack(">h", packet[72:74])[0] * 0.1,
        pitch_deg=struct.unpack(">h", packet[74:76])[0] * 0.1,
        roll_deg=struct.unpack(">h", packet[76:78])[0] * 0.1,
        gps_heading_deg=struct.unpack(">H", packet[78:80])[0] * 0.1,
        gps_speed_mps=struct.unpack(">H", packet[80:82])[0] * 0.1,
        dvl_speed_mps=struct.unpack(">h", packet[82:84])[0] * 0.1,
        altitude_m=struct.unpack(">H", packet[84:86])[0] * 0.1,
        dead_reckoning_lon_deg=struct.unpack(">i", packet[86:90])[0] * 1.0e-6,
        dead_reckoning_lat_deg=struct.unpack(">i", packet[90:94])[0] * 1.0e-6,
        gps_lon_deg=struct.unpack(">i", packet[94:98])[0] * 1.0e-6,
        gps_lat_deg=struct.unpack(">i", packet[98:102])[0] * 1.0e-6,
        total_voltage_v=struct.unpack(">H", packet[102:104])[0] * 0.1,
        total_current_a=struct.unpack(">H", packet[104:106])[0] * 0.1,
        soc=int(packet[106]),
        soh=int(packet[107]),
        device_power_status=struct.unpack(">I", packet[114:118])[0],
        operation_feedback=struct.unpack(">I", packet[118:122])[0],
        task_status=struct.unpack(">I", packet[122:126])[0],
        system_alarm=int(packet[127]),
        depth_alarm=int(packet[128]),
        bottom_alarm=int(packet[129]),
    )

"""Shared protocol debug formatting helpers for CLI tools and mock AMD logs."""

from __future__ import annotations

import os
from datetime import datetime
import sys
import time

from .enums import ControlModeByte, WorkInstruction
from .protocol import (
    DEFAULT_MAIN_MOTOR_RPM_SCALE,
    PROTOCOL_DOWNLINK_CHECKSUM_INDEX,
    PROTOCOL_DOWNLINK_HEADER,
    PROTOCOL_DOWNLINK_SIZE,
    PROTOCOL_UPLINK_HEADER,
    PROTOCOL_UPLINK_CHECKSUM_INDEX,
    PROTOCOL_UPLINK_SIZE,
    PROTOCOL_FRAME_TAIL,
    downlink_state_to_payload,
    parse_downlink_packet,
    parse_uplink_packet,
)

_ANSI = {
    "cyan": "\033[36m",
    "green": "\033[32m",
    "yellow": "\033[33m",
    "red": "\033[31m",
    "reset": "\033[0m",
}


def supports_color(stream=None) -> bool:
    """Return whether ANSI colors should be emitted for the given stream."""
    target = sys.stdout if stream is None else stream
    if os.environ.get("NO_COLOR"):
        return False
    return bool(getattr(target, "isatty", lambda: False)())


def colorize(text: str, color: str, *, enabled: bool) -> str:
    """Wrap text in ANSI colors when enabled and supported by the terminal."""
    if not enabled or color not in _ANSI:
        return text
    return f"{_ANSI[color]}{text}{_ANSI['reset']}"


def detect_protocol_direction(packet: bytes) -> str:
    """Classify protocol packets as downlink, uplink, or unknown."""
    if bytes(packet[: len(PROTOCOL_DOWNLINK_HEADER)]) == PROTOCOL_DOWNLINK_HEADER:
        return "downlink"
    if bytes(packet[: len(PROTOCOL_UPLINK_HEADER)]) == PROTOCOL_UPLINK_HEADER:
        return "uplink"
    return "unknown"


def hex_preview(packet: bytes, *, max_bytes: int = 48) -> str:
    """Return a trimmed hexadecimal preview suitable for single-line logs."""
    clipped = packet[: max(1, int(max_bytes))]
    preview = clipped.hex(" ")
    if len(packet) > len(clipped):
        return f"{preview} ..."
    return preview


def _enum_label(enum_cls, value: int) -> str:
    try:
        return enum_cls(value).name
    except Exception:
        return f"0x{int(value) & 0xFF:02X}"


def _control_mode_label(value: int) -> str:
    try:
        mode = ControlModeByte(value)
    except Exception:
        return f"UNKNOWN (0x{int(value) & 0xFF:02X})"

    labels = {
        ControlModeByte.SEND_ONLY: "SEND_ONLY (仅发送)",
        ControlModeByte.REMOTE_CONTROL: "REMOTE_CONTROL (遥控)",
        ControlModeByte.AUTO_FIXED_POINT: "AUTO_FIXED_POINT (定点)",
        ControlModeByte.AUTO_DIRECTION: "AUTO_DIRECTION (定向)",
        ControlModeByte.RETURN_HOME: "RETURN_HOME (回航)",
        ControlModeByte.JETSON_PROTOCOL: "AUTONOMOUS (自主模式)",
    }
    return labels.get(mode, f"UNKNOWN (0x{int(value) & 0xFF:02X})")


def _work_instruction_label(value: int) -> str:
    try:
        instruction = WorkInstruction(value)
    except Exception:
        return f"0x{int(value) & 0xFF:02X}"
    return instruction.name


def _checksum_status(packet: bytes, checksum_index: int) -> tuple[bool, int, int]:
    expected = sum(packet[:checksum_index]) & 0xFF
    actual = int(packet[checksum_index]) if checksum_index < len(packet) else -1
    return expected == actual, expected, actual


def _tail_status(packet: bytes) -> tuple[bool, bytes, bytes]:
    expected = PROTOCOL_FRAME_TAIL
    actual = bytes(packet[-2:]) if len(packet) >= 2 else b""
    return actual == expected, expected, actual


def _format_timestamp(include_timestamp: bool) -> str | None:
    if not include_timestamp:
        return None
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def _format_block(title: str, lines: list[str]) -> str:
    body = ["=" * 50, title, "-" * 50]
    body.extend(lines)
    body.append("=" * 50)
    return "\n".join(body)


def format_protocol_packet_raw(
    packet: bytes,
    *,
    label: str = "protocol",
    source: str | None = None,
    color: bool = True,
    include_hex: bool = False,
    max_hex_bytes: int = 48,
    main_motor_rpm_scale: float = DEFAULT_MAIN_MOTOR_RPM_SCALE,
) -> str:
    """Format packets as compact CSV-style raw lines.

    The raw representation intentionally stays machine-friendly and mirrors the
    documented CSV layout used by the protocol logging guide.
    """
    direction = detect_protocol_direction(packet)

    if direction == "downlink":
        state = parse_downlink_packet(packet, main_motor_rpm_scale=main_motor_rpm_scale)
        values = [
            "$CKTH",
            str(state.frame_number),
            str(state.obj_address),
            str(state.control_mode_byte),
            str(state.work_instruction),
            f"{state.right_fin_deg:.1f}",
            f"{state.top_fin_deg:.1f}",
            f"{state.left_fin_deg:.1f}",
            f"{state.bottom_fin_deg:.1f}",
            f"{state.thrust_percent:.1f}",
            str(state.main_motor_rpm),
            str(state.side_motor_rpm),
            f"{state.orientation_deg:.1f}",
        ]
    elif direction == "uplink":
        telemetry = parse_uplink_packet(packet)
        values = [
            "$AUV",
            str(telemetry.frame_number),
            str(telemetry.auv_address),
            str(telemetry.control_mode_byte),
            str(telemetry.work_instruction),
            f"{telemetry.depth_m:.2f}",
            f"{telemetry.heading_deg:.1f}",
            f"{telemetry.pitch_deg:.1f}",
            f"{telemetry.roll_deg:.1f}",
            f"{telemetry.gps_lon_deg:.6f}",
            f"{telemetry.gps_lat_deg:.6f}",
            f"{telemetry.total_voltage_v:.1f}",
            f"{telemetry.total_current_a:.1f}",
            str(telemetry.main_motor_rpm),
            f"{telemetry.right_fin_deg:.1f}",
            f"{telemetry.top_fin_deg:.1f}",
            f"{telemetry.left_fin_deg:.1f}",
            f"{telemetry.bottom_fin_deg:.1f}",
        ]
    else:
        values = ["UNKNOWN", str(len(packet))]

    line = ",".join(values)
    if include_hex:
        line = f"{line} hex={hex_preview(packet, max_bytes=max_hex_bytes)}"
    return line


def format_protocol_packet_ascii(
    packet: bytes,
    *,
    label: str = "protocol",
    source: str | None = None,
    include_timestamp: bool = True,
    color: bool = True,
    main_motor_rpm_scale: float = DEFAULT_MAIN_MOTOR_RPM_SCALE,
) -> str:
    """Format packets as a detailed multi-line diagnostic block."""
    direction = detect_protocol_direction(packet)
    timestamp = _format_timestamp(include_timestamp)
    lines: list[str] = []

    if timestamp is not None:
        lines.append(f"Timestamp: {timestamp}")
    if label:
        lines.append(f"Label: {label}")
    if source:
        lines.append(f"Source: {source}")

    if direction == "downlink":
        state = parse_downlink_packet(packet, main_motor_rpm_scale=main_motor_rpm_scale)
        checksum_ok, checksum_expected, checksum_actual = _checksum_status(packet, PROTOCOL_DOWNLINK_CHECKSUM_INDEX)
        tail_ok, tail_expected, tail_actual = _tail_status(packet)

        lines.extend([
            "",
            "HEADER INFO:",
            f"  Frame Number: {state.frame_number}",
            f"  Object Address: {state.obj_address}",
            f"  Control Mode Byte: 0x{state.control_mode_byte:02X}",
            f"    -> {_control_mode_label(state.control_mode_byte)}",
            f"  Work Instruction: 0x{state.work_instruction:02X}",
            f"    -> {_work_instruction_label(state.work_instruction)}",
            "",
            "CONTROL SURFACES:",
            f"  Right Fin:   {state.right_fin_deg:+.1f} deg",
            f"  Top Fin:     {state.top_fin_deg:+.1f} deg",
            f"  Left Fin:    {state.left_fin_deg:+.1f} deg",
            f"  Bottom Fin:  {state.bottom_fin_deg:+.1f} deg",
            f"  Thrust:      {state.thrust_percent:+.1f} %",
            "",
            "MOTORS:",
            f"  Main Motor:  {state.main_motor_rpm:>5d} RPM",
            f"  Side Motor:  {state.side_motor_rpm:>5d} RPM",
            "",
            "NAVIGATION:",
            f"  Target Heading: {state.orientation_deg:+6.1f} deg",
            "",
            "FRAME INTEGRITY:",
            f"  Checksum: {'OK' if checksum_ok else 'BAD'}",
            f"    Expected: 0x{checksum_expected:02X}",
            f"    Actual:   0x{checksum_actual:02X}",
            f"  Frame Tail: {'OK' if tail_ok else 'BAD'}",
            f"    Expected: 0x{tail_expected.hex().upper()}",
            f"    Actual:   0x{tail_actual.hex().upper()}",
        ])
        title = "ASCII PROTOCOL PACKET - DOWNLINK ($CKTH)"

    elif direction == "uplink":
        telemetry = parse_uplink_packet(packet)
        checksum_ok, checksum_expected, checksum_actual = _checksum_status(packet, PROTOCOL_UPLINK_CHECKSUM_INDEX)
        tail_ok, tail_expected, tail_actual = _tail_status(packet)

        lines.extend([
            "",
            "HEADER INFO:",
            f"  Frame Number: {telemetry.frame_number}",
            f"  AUV Address: {telemetry.auv_address}",
            f"  Control Mode Byte: 0x{telemetry.control_mode_byte:02X}",
            f"    -> {_control_mode_label(telemetry.control_mode_byte)}",
            f"  Work Instruction: 0x{telemetry.work_instruction:02X}",
            f"    -> {_work_instruction_label(telemetry.work_instruction)}",
            "",
            "TELEMETRY:",
            f"  Depth:        {telemetry.depth_m:.2f} m",
            f"  Heading:      {telemetry.heading_deg:+6.1f} deg",
            f"  Pitch:        {telemetry.pitch_deg:+6.1f} deg",
            f"  Roll:         {telemetry.roll_deg:+6.1f} deg",
            f"  GPS Lon:      {telemetry.gps_lon_deg:.6f}",
            f"  GPS Lat:      {telemetry.gps_lat_deg:.6f}",
            f"  Voltage:      {telemetry.total_voltage_v:.1f} V",
            f"  Current:      {telemetry.total_current_a:.1f} A",
            f"  Main Motor:   {telemetry.main_motor_rpm:>5d} RPM",
            f"  Side Motor:   {telemetry.side_motor_rpm:>5d} RPM",
            "",
            "CONTROL REPLAY:",
            f"  Right Fin:    {telemetry.right_fin_deg:+.1f} deg",
            f"  Top Fin:      {telemetry.top_fin_deg:+.1f} deg",
            f"  Left Fin:     {telemetry.left_fin_deg:+.1f} deg",
            f"  Bottom Fin:   {telemetry.bottom_fin_deg:+.1f} deg",
            "",
            "FRAME INTEGRITY:",
            f"  Checksum: {'OK' if checksum_ok else 'BAD'}",
            f"    Expected: 0x{checksum_expected:02X}",
            f"    Actual:   0x{checksum_actual:02X}",
            f"  Frame Tail: {'OK' if tail_ok else 'BAD'}",
            f"    Expected: 0x{tail_expected.hex().upper()}",
            f"    Actual:   0x{tail_actual.hex().upper()}",
        ])
        title = "ASCII PROTOCOL PACKET - UPLINK ($AUV)"

    else:
        title = "ASCII PROTOCOL PACKET - UNKNOWN"
        lines.extend([
            "",
            f"Packet Length: {len(packet)} bytes",
            f"Header: {hex_preview(packet, max_bytes=min(len(packet), 16))}",
            "",
            "FRAME INTEGRITY:",
            f"  Bytes: {len(packet)}",
        ])

    if not color:
        return _format_block(title, lines)

    # ASCII logs are kept plain-text so they remain easy to diff and grep.
    return _format_block(title, lines)


def summarize_downlink_packet(packet: bytes, *, main_motor_rpm_scale: float = DEFAULT_MAIN_MOTOR_RPM_SCALE) -> str:
    """Return a compact one-line summary for a decoded $CKTH packet."""
    state = parse_downlink_packet(packet, main_motor_rpm_scale=main_motor_rpm_scale)
    payload = downlink_state_to_payload(state)
    return (
        f"frame={payload['frame_number']} obj={payload['obj_address']} "
        f"mode=0x{payload['control_mode_byte']:02X} instr=0x{payload['work_instruction']:02X} "
        f"cmd=({payload['right']:.1f},{payload['top']:.1f},{payload['left']:.1f},"
        f"{payload['bottom']:.1f},{payload['thrust']:.1f}) "
        f"main_rpm={payload['main_motor_rpm']} side_rpm={payload['side_motor_rpm']} "
        f"heading={payload['orientation_deg']:.1f}deg"
    )


def summarize_uplink_packet(packet: bytes) -> str:
    """Return a compact one-line summary for a decoded $AUV packet."""
    telemetry = parse_uplink_packet(packet)
    return (
        f"frame={telemetry.frame_number} auv={telemetry.auv_address} "
        f"mode=0x{telemetry.control_mode_byte:02X} instr=0x{telemetry.work_instruction:02X} "
        f"depth={telemetry.depth_m:.2f}m heading={telemetry.heading_deg:.1f}deg "
        f"gps=({telemetry.gps_lon_deg:.6f},{telemetry.gps_lat_deg:.6f}) "
        f"voltage={telemetry.total_voltage_v:.1f}V "
        f"cmd=({telemetry.right_fin_deg:.1f},{telemetry.top_fin_deg:.1f},"
        f"{telemetry.left_fin_deg:.1f},{telemetry.bottom_fin_deg:.1f},"
        f"{telemetry.main_motor_rpm})"
    )


def format_protocol_packet(
    packet: bytes,
    *,
    label: str = "protocol",
    source: str | None = None,
    color: bool = True,
    include_hex: bool = False,
    max_hex_bytes: int = 48,
    main_motor_rpm_scale: float = DEFAULT_MAIN_MOTOR_RPM_SCALE,
) -> str:
    """Format protocol packets into a consistent single-line log view."""
    direction = detect_protocol_direction(packet)
    tag_parts = [label]

    if direction == "downlink":
        tag_parts.append("CKTH")
        summary_color = "cyan"
        try:
            summary = summarize_downlink_packet(packet, main_motor_rpm_scale=main_motor_rpm_scale)
        except Exception as exc:
            summary = f"decode_failed={exc}"
            summary_color = "red"
    elif direction == "uplink":
        tag_parts.append("AUV")
        summary_color = "green"
        try:
            summary = summarize_uplink_packet(packet)
        except Exception as exc:
            summary = f"decode_failed={exc}"
            summary_color = "red"
    else:
        tag_parts.append("UNKNOWN")
        summary = f"len={len(packet)} unsupported header"
        summary_color = "yellow"

    if source:
        tag_parts.append(source)

    tag_text = "[" + "][".join(tag_parts) + "]"
    parts = [colorize(tag_text, summary_color, enabled=color and supports_color())]
    parts.append(summary)

    if include_hex:
        parts.append(f"hex={hex_preview(packet, max_bytes=max_hex_bytes)}")

    return " ".join(parts)


__all__ = [
    "colorize",
    "detect_protocol_direction",
    "format_protocol_packet",
    "format_protocol_packet_ascii",
    "format_protocol_packet_raw",
    "hex_preview",
    "supports_color",
    "summarize_downlink_packet",
    "summarize_uplink_packet",
]
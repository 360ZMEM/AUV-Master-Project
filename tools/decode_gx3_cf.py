"""Offline 3DM-GX3-25 0xCF response parser for firmware review and fixtures.

The byte layout and checksum are from the local Single Byte Data Communications
Protocol, pp. 23 and 38. This does not change the active VxWorks UART path.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import struct


FRAME_SIZE = 31
TIMER_TICKS_PER_SECOND = 62500
TIMER_MODULUS = 1 << 32


@dataclass(frozen=True)
class Gx3CfSample:
    roll_rad: float
    pitch_rad: float
    yaw_rad: float
    angular_rate_x_rps: float
    angular_rate_y_rps: float
    angular_rate_z_rps: float
    sensor_timer_ticks: int


def decode_gx3_cf(frame: bytes) -> Gx3CfSample:
    """Require the complete fixed-length reply and its 16-bit sum checksum."""
    if len(frame) != FRAME_SIZE:
        raise ValueError(f'0xCF response must be {FRAME_SIZE} bytes')
    if frame[0] != 0xCF:
        raise ValueError('0xCF response header missing')
    expected = sum(frame[:-2]) & 0xFFFF
    received = int.from_bytes(frame[-2:], 'big')
    if expected != received:
        raise ValueError('0xCF response checksum mismatch')
    values = struct.unpack('>6fI', frame[1:-2])
    if not all(math.isfinite(value) for value in values[:6]):
        raise ValueError('0xCF response contains nonfinite attitude or rate')
    return Gx3CfSample(*values)


def unwrap_gx3_timer(previous_unwrapped: int | None, raw_ticks: int,
                     *, max_gap_s: float = 5.) -> int:
    """Accept a new sensor timer, including one bounded 32-bit rollover.

    A reset or a long gap needs explicit re-synchronization and must not
    silently re-label an old attitude as fresh.
    """
    if not 0 <= raw_ticks < TIMER_MODULUS:
        raise ValueError('sensor timer outside uint32 range')
    if not math.isfinite(max_gap_s) or max_gap_s <= 0:
        raise ValueError('max_gap_s must be finite and positive')
    if previous_unwrapped is None:
        return raw_ticks
    if previous_unwrapped < 0:
        raise ValueError('previous timer invalid')
    epoch = previous_unwrapped // TIMER_MODULUS
    candidate = epoch * TIMER_MODULUS + raw_ticks
    if candidate <= previous_unwrapped:
        candidate += TIMER_MODULUS
    gap = candidate - previous_unwrapped
    if gap <= 0 or gap / TIMER_TICKS_PER_SECOND > max_gap_s:
        raise ValueError('sensor timer repeated, reset or gap too large')
    return candidate

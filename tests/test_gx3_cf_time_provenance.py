"""Synthetic 0xCF frames test parser semantics; they are not sensor evidence."""

import struct

import pytest

from tools.decode_gx3_cf import (
    TIMER_MODULUS, TIMER_TICKS_PER_SECOND,
    decode_gx3_cf, unwrap_gx3_timer,
)


def frame(timer: int) -> bytes:
    payload = b'\xcf' + struct.pack('>6fI', .1, -.2, .3, 1., 2., 3., timer)
    return payload + (sum(payload) & 0xffff).to_bytes(2, 'big')


def test_valid_frame_preserves_native_timer_and_orientation():
    result = decode_gx3_cf(frame(125000))
    assert result.sensor_timer_ticks == 125000
    assert abs(result.yaw_rad - .3) < 1e-6
    assert abs(result.angular_rate_z_rps - 3.) < 1e-6


def test_short_corrupt_and_nonfinite_frames_fail():
    good = frame(200000)
    with pytest.raises(ValueError, match='31 bytes'):
        decode_gx3_cf(good[:25])
    corrupt = bytearray(good)
    corrupt[10] ^= 1
    with pytest.raises(ValueError, match='checksum'):
        decode_gx3_cf(bytes(corrupt))
    nan_payload = b'\xcf' + struct.pack('>6fI', float('nan'), 0., 0., 0., 0., 0., 1)
    nan_frame = nan_payload + (sum(nan_payload) & 0xffff).to_bytes(2, 'big')
    with pytest.raises(ValueError, match='nonfinite'):
        decode_gx3_cf(nan_frame)


def test_timer_replay_reset_and_bounded_rollover():
    previous = TIMER_MODULUS - TIMER_TICKS_PER_SECOND // 2
    after_rollover = unwrap_gx3_timer(previous, TIMER_TICKS_PER_SECOND // 2)
    assert after_rollover - previous == TIMER_TICKS_PER_SECOND
    with pytest.raises(ValueError, match='timer repeated'):
        unwrap_gx3_timer(1000, 1000)
    with pytest.raises(ValueError, match='timer repeated'):
        unwrap_gx3_timer(1000, 900)
    with pytest.raises(ValueError, match='timer repeated'):
        unwrap_gx3_timer(1000, 1000 + 10 * TIMER_TICKS_PER_SECOND)

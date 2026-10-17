"""Versioned, opt-in IMU provenance sidecar wire format.

This independent 48-byte record carries one validated 3DM-GX3-25 0xCF sample.
It does not replace or change the existing $AUV uplink packet.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import struct
import zlib


MAGIC = b'IMV1'
VERSION = 1
FLAG_SOURCE_FRAME_VALIDATED = 1
_BODY = struct.Struct('>4sBBHIII6f')
_CRC = struct.Struct('>I')
WIRE_SIZE = _BODY.size + _CRC.size


@dataclass(frozen=True)
class ImuProvenanceV1:
    frame_checksum_u16: int
    sample_sequence: int
    sensor_timer_ticks: int
    pc104_receive_uptime_ms: int
    roll_rad: float
    pitch_rad: float
    yaw_rad: float
    angular_rate_x_rps: float
    angular_rate_y_rps: float
    angular_rate_z_rps: float


def _check_record(record: ImuProvenanceV1) -> None:
    for label, value, maximum in (
        ('frame_checksum_u16', record.frame_checksum_u16, 0xffff),
        ('sample_sequence', record.sample_sequence, 0xffffffff),
        ('sensor_timer_ticks', record.sensor_timer_ticks, 0xffffffff),
        ('pc104_receive_uptime_ms', record.pc104_receive_uptime_ms, 0xffffffff),
    ):
        if not isinstance(value, int) or not 0 <= value <= maximum:
            raise ValueError(f'{label} outside wire range')
    floats = (record.roll_rad, record.pitch_rad, record.yaw_rad,
              record.angular_rate_x_rps, record.angular_rate_y_rps,
              record.angular_rate_z_rps)
    if not all(math.isfinite(value) for value in floats):
        raise ValueError('IMU sidecar contains nonfinite attitude or rate')


def encode_imu_provenance(record: ImuProvenanceV1) -> bytes:
    _check_record(record)
    body = _BODY.pack(
        MAGIC, VERSION, FLAG_SOURCE_FRAME_VALIDATED,
        record.frame_checksum_u16, record.sample_sequence,
        record.sensor_timer_ticks, record.pc104_receive_uptime_ms,
        record.roll_rad, record.pitch_rad, record.yaw_rad,
        record.angular_rate_x_rps, record.angular_rate_y_rps,
        record.angular_rate_z_rps,
    )
    return body + _CRC.pack(zlib.crc32(body) & 0xffffffff)


def decode_imu_provenance(packet: bytes) -> ImuProvenanceV1:
    if len(packet) != WIRE_SIZE:
        raise ValueError(f'IMU sidecar must be {WIRE_SIZE} bytes')
    body = packet[:-_CRC.size]
    reported = _CRC.unpack(packet[-_CRC.size:])[0]
    if zlib.crc32(body) & 0xffffffff != reported:
        raise ValueError('IMU sidecar CRC32 mismatch')
    magic, version, flags, *values = _BODY.unpack(body)
    if magic != MAGIC or version != VERSION or flags != FLAG_SOURCE_FRAME_VALIDATED:
        raise ValueError('IMU sidecar magic/version/flags mismatch')
    result = ImuProvenanceV1(*values)
    _check_record(result)
    return result

"""Wire compatibility checks for the isolated IMU sidecar candidate."""

import struct
import zlib
from pathlib import Path
import shutil
import subprocess

import pytest

from common.imu_provenance_sidecar import (
    WIRE_SIZE, ImuProvenanceV1, decode_imu_provenance,
    encode_imu_provenance,
)


def sample() -> ImuProvenanceV1:
    return ImuProvenanceV1(0x127f, 23, 125000, 4390,
                           .1, -.2, .3, 1., 2., 3.)


def test_roundtrip_and_fixed_wire_size():
    packet = encode_imu_provenance(sample())
    decoded = decode_imu_provenance(packet)
    assert WIRE_SIZE == 48
    assert decoded.sample_sequence == 23
    assert decoded.sensor_timer_ticks == 125000
    assert abs(decoded.yaw_rad - .3) < 1e-6


def test_truncation_crc_and_version_tamper_rejected():
    packet = encode_imu_provenance(sample())
    with pytest.raises(ValueError, match='48 bytes'):
        decode_imu_provenance(packet[:-1])
    bad = bytearray(packet)
    bad[20] ^= 1
    with pytest.raises(ValueError, match='CRC32'):
        decode_imu_provenance(bytes(bad))
    body = bytearray(packet[:-4])
    body[4] = 2
    versioned = bytes(body) + struct.pack('>I', zlib.crc32(body) & 0xffffffff)
    with pytest.raises(ValueError, match='version'):
        decode_imu_provenance(versioned)


def test_declared_validity_and_finite_sample_required():
    packet = encode_imu_provenance(sample())
    body = bytearray(packet[:-4])
    body[5] = 0
    invalid = bytes(body) + struct.pack('>I', zlib.crc32(body) & 0xffffffff)
    with pytest.raises(ValueError, match='flags'):
        decode_imu_provenance(invalid)
    bad = ImuProvenanceV1(0x127f, 23, 125000, 4390,
                          float('nan'), -.2, .3, 1., 2., 3.)
    with pytest.raises(ValueError, match='nonfinite'):
        encode_imu_provenance(bad)


def test_portable_c_encoder_matches_python_wire_bytes(tmp_path):
    compiler = shutil.which('cc')
    if compiler is None:
        pytest.skip('host C compiler unavailable')
    root = Path(__file__).resolve().parents[1]
    candidate = root / 'csd_vx6.8_lastest/inspection_v2_candidate'
    binary = tmp_path / 'imu_sidecar_host'
    subprocess.run([
        compiler, '-std=c99', '-O2', '-Wall', '-Wextra', '-Werror', '-pedantic',
        '-I', str(candidate), str(candidate / 'imu_provenance_sidecar_v1.c'),
        str(candidate / 'test_imu_provenance_sidecar_host.c'), '-lm', '-o', str(binary),
    ], check=True, capture_output=True, text=True)
    output = subprocess.run([str(binary)], check=True, capture_output=True, text=True)
    assert bytes.fromhex(output.stdout.strip()) == encode_imu_provenance(sample())

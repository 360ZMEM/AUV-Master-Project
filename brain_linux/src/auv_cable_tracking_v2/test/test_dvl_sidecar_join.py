"""Body DVL is usable only with a fresh, time-matched sidecar orientation."""

import json
import math

import pytest

from common.imu_provenance_sidecar import ImuProvenanceV1
from auv_cable_tracking_v2.dvl_sidecar_join import (
    BodyDvlSample, join_body_dvl_to_sidecar, parse_body_dvl_json)


def _imu(gyro_z=0.):
    return ImuProvenanceV1(0x1234, 11, 106250, 1150,
                           0., 0., math.pi / 2., 0., 0., gyro_z)


def test_body_velocity_rotates_using_matched_sidecar_yaw_and_dvl_time():
    dvl = BodyDvlSample(1120, 1100, (1., 0., 0.))
    q = (0., 0., math.sqrt(.5), math.sqrt(.5))
    result = join_body_dvl_to_sidecar(dvl, _imu(), q, 100.15, 100.16)
    assert result.accepted
    assert result.stamp_s == pytest.approx(100.10)
    assert result.world_xyz_mps == pytest.approx((0., 1., 0.), abs=1e-12)


def test_stale_uplink_unmatched_time_fast_rotation_and_speed_fail_closed():
    q = (0., 0., 0., 1.)
    check = lambda dvl, imu=_imu(): join_body_dvl_to_sidecar(dvl, imu, q, 100.15, 100.16)
    assert check(BodyDvlSample(1700, 1100, (1., 0., 0.))).reason == 'dvl_sample_stale_in_uplink'
    assert check(BodyDvlSample(1000, 900, (1., 0., 0.))).reason == 'dvl_imu_time_mismatch'
    assert check(BodyDvlSample(1120, 1100, (1., 0., 0.)), _imu(gyro_z=2.)).reason == \
        'rotation_between_samples_too_large'
    assert check(BodyDvlSample(1120, 1100, (3., 0., 0.))).reason == \
        'dvl_speed_out_of_envelope'
    assert join_body_dvl_to_sidecar(BodyDvlSample(1120, 1100, (1., 0., 0.)),
                                    _imu(), q, 99., 100.16).reason == \
        'dvl_ros_time_stale_or_future'


def test_body_record_parser_rejects_implicit_or_nonfinite_fields():
    valid = {'pc104_packet_uptime_ms': 1120, 'pc104_dvl_uptime_ms': 1100,
             'velocity_xyz_mps': [1., 0., 0.]}
    assert parse_body_dvl_json(json.dumps(valid)).velocity_xyz_mps == (1., 0., 0.)
    for invalid in ({**valid, 'velocity_xyz_mps': [float('nan'), 0, 0]},
                    {**valid, 'pc104_dvl_uptime_ms': True},
                    {**valid, 'extra': 1}):
        with pytest.raises(ValueError):
            parse_body_dvl_json(json.dumps(invalid))

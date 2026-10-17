"""Source identity must advance before a candidate IMU can reach ROS."""

from dataclasses import replace

from common.imu_provenance_sidecar import ImuProvenanceV1
from auv_cable_tracking_v2.imu_sidecar_gate import ImuSidecarGate


def sample(sequence=10, timer=100000, uptime=1000):
    return ImuProvenanceV1(
        frame_checksum_u16=1, sample_sequence=sequence,
        sensor_timer_ticks=timer, pc104_receive_uptime_ms=uptime,
        roll_rad=0., pitch_rad=0., yaw_rad=0.,
        angular_rate_x_rps=0., angular_rate_y_rps=0., angular_rate_z_rps=0.)


def test_second_consistent_source_sample_admitted_with_board_time():
    gate = ImuSidecarGate()
    assert gate.admit(sample(), receive_ros_s=100.).reason == 'warming_up'
    result = gate.admit(sample(11, 106250, 1100), receive_ros_s=100.1)
    assert result.accepted and abs(result.stamp_s - 100.1) < 1e-9
    assert gate.admit(sample(11, 106250, 1100), receive_ros_s=100.2).reason == 'sample_sequence_replay_or_reset'


def test_frozen_timer_and_reset_sequence_are_rejected():
    gate = ImuSidecarGate()
    gate.admit(sample(), receive_ros_s=100.)
    assert gate.admit(sample(11, 100000, 1100), receive_ros_s=100.1).reason == 'sensor_timer_inconsistent'
    assert gate.admit(sample(1, 106250, 1100), receive_ros_s=100.1).reason == 'sample_sequence_replay_or_reset'


def test_timer_wrap_needs_sequence_and_board_clock_agreement():
    gate = ImuSidecarGate()
    previous = sample(0xffffffff, 0xfffff000, 0xffffff00)
    gate.admit(previous, receive_ros_s=100.)
    next_sample = replace(previous, sample_sequence=0,
                          sensor_timer_ticks=(previous.sensor_timer_ticks + 6250) & 0xffffffff,
                          pc104_receive_uptime_ms=(previous.pc104_receive_uptime_ms + 100) & 0xffffffff)
    assert gate.admit(next_sample, receive_ros_s=100.1).accepted


def test_gap_requires_two_new_samples_before_readmission():
    gate = ImuSidecarGate()
    gate.admit(sample(), receive_ros_s=100.)
    assert gate.admit(sample(11, 162500, 2000), receive_ros_s=101.).reason == 'pc104_time_gap_requires_readmission'
    assert gate.admit(sample(12, 168750, 2100), receive_ros_s=101.1).reason == 'warming_up'
    assert gate.admit(sample(13, 175000, 2200), receive_ros_s=101.2).accepted

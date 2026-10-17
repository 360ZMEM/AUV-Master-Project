"""Keep filtered navigation tied to a live IMU acquisition time anchor."""

from auv_localization.auv_localization_node import imu_anchor_fresh


def test_recent_receipt_and_stamp_are_required():
    common = dict(now_wall_s=10., now_ros_s=20., maximum_age_s=.75)
    assert imu_anchor_fresh(last_rx_wall_s=9.5, last_stamp_s=19.5, **common)
    assert not imu_anchor_fresh(last_rx_wall_s=None, last_stamp_s=19.5, **common)
    assert not imu_anchor_fresh(last_rx_wall_s=9., last_stamp_s=19.5, **common)
    assert not imu_anchor_fresh(last_rx_wall_s=9.5, last_stamp_s=19., **common)


def test_replayed_and_future_stamps_do_not_refresh_navigation():
    common = dict(now_wall_s=10., last_rx_wall_s=10., now_ros_s=20.,
                  maximum_age_s=.75)
    assert not imu_anchor_fresh(last_stamp_s=18., **common)
    assert not imu_anchor_fresh(last_stamp_s=20.3, **common)


def test_legacy_launch_can_leave_gate_disabled():
    assert imu_anchor_fresh(now_wall_s=10., last_rx_wall_s=None,
                            now_ros_s=20., last_stamp_s=0., maximum_age_s=0.)

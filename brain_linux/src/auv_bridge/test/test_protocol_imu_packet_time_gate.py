"""A PC104 receive timestamp must not masquerade as advancing packet time."""

from types import SimpleNamespace

from builtin_interfaces.msg import Time
from auv_bridge.bridge_node import (AUVBridgeNode, protocol_imu_packet_time_check,
                                    protocol_imu_stamp_fresh)


def test_packet_time_gate_rejects_fallback_replay_and_reset():
    check = protocol_imu_packet_time_check
    assert check(pc104_time_valid=True, pc104_uptime_ms=1000,
                 last_accepted_uptime_ms=None) == (True, 'pc104_packet_time_advanced')
    assert check(pc104_time_valid=False, pc104_uptime_ms=1100,
                 last_accepted_uptime_ms=1000) == (False, 'pc104_packet_time_unavailable')
    assert check(pc104_time_valid=True, pc104_uptime_ms=1000,
                 last_accepted_uptime_ms=1000) == (False, 'pc104_packet_time_repeated')
    assert check(pc104_time_valid=True, pc104_uptime_ms=900,
                 last_accepted_uptime_ms=1000) == (False, 'pc104_packet_time_regressed')
    assert check(pc104_time_valid=True, pc104_uptime_ms=1010,
                 last_accepted_uptime_ms=1000) == (True, 'pc104_packet_time_advanced')


class _Logger:
    def warning(self, _message):
        pass

    def info(self, _message):
        pass


def test_opt_in_bridge_only_advances_accepted_packet_time():
    node = AUVBridgeNode.__new__(AUVBridgeNode)
    node.require_packet_time_for_imu = True
    node._last_protocol_imu_packet_uptime_ms = None
    node._protocol_imu_time_rejection_reason = ''
    node.get_logger = lambda: _Logger()
    sample = lambda valid, uptime: SimpleNamespace(
        pc104_time_valid=valid, pc104_uptime_ms=uptime)
    assert node._protocol_imu_packet_time_ok(sample(True, 1000))
    assert node._last_protocol_imu_packet_uptime_ms == 1000
    assert not node._protocol_imu_packet_time_ok(sample(False, 1200))
    assert not node._protocol_imu_packet_time_ok(sample(True, 1000))
    assert not node._protocol_imu_packet_time_ok(sample(True, 900))
    assert node._last_protocol_imu_packet_uptime_ms == 1000
    assert node._protocol_imu_packet_time_ok(sample(True, 1010))
    assert node._last_protocol_imu_packet_uptime_ms == 1010


def test_protocol_imu_publisher_does_not_refresh_on_replayed_packet_time():
    node = AUVBridgeNode.__new__(AUVBridgeNode)
    node.require_packet_time_for_imu = True
    node._last_protocol_imu_packet_uptime_ms = None
    node._protocol_imu_time_rejection_reason = ''
    node._protocol_imu_stamp_was_fresh = None
    node.max_packet_time_age_s = .75
    node.get_logger = lambda: _Logger()
    now_sec = [100]
    node.get_clock = lambda: SimpleNamespace(
        now=lambda: SimpleNamespace(to_msg=lambda: Time(sec=now_sec[0])))
    node.imu_pub = object()
    messages = []
    node._safe_publish_ros = lambda _publisher, message: messages.append(message)
    sample = lambda valid, uptime: SimpleNamespace(
        pc104_time_valid=valid, pc104_uptime_ms=uptime,
        gyro_x_rps=0., gyro_y_rps=0., gyro_z_rps=0.)
    stamp = Time(sec=100, nanosec=0)
    quaternion = (0., 0., 0., 1.)
    assert node._publish_protocol_imu(sample(True, 1000), stamp, quaternion)
    assert not node._publish_protocol_imu(sample(True, 1000), stamp, quaternion)
    assert not node._publish_protocol_imu(sample(False, 1010), stamp, quaternion)
    assert not node._publish_protocol_imu(sample(True, 900), stamp, quaternion)
    now_sec[0] = 101
    assert node._publish_protocol_imu(sample(True, 1010), Time(sec=101), quaternion)
    assert len(messages) == 2
    assert [msg.header.stamp.sec for msg in messages] == [100, 101]


def test_packet_timestamp_age_rejects_slowly_advancing_old_imu():
    assert protocol_imu_stamp_fresh(now_ros_s=10., stamp_s=9.5, maximum_age_s=.75)
    assert not protocol_imu_stamp_fresh(now_ros_s=10., stamp_s=9., maximum_age_s=.75)
    assert not protocol_imu_stamp_fresh(now_ros_s=10., stamp_s=10.3, maximum_age_s=.75)
    node = AUVBridgeNode.__new__(AUVBridgeNode)
    node.require_packet_time_for_imu = True
    node.max_packet_time_age_s = .75
    node._last_protocol_imu_packet_uptime_ms = 1000
    node._protocol_imu_time_rejection_reason = ''
    node._protocol_imu_stamp_was_fresh = None
    node.get_logger = lambda: _Logger()
    node.get_clock = lambda: SimpleNamespace(
        now=lambda: SimpleNamespace(to_msg=lambda: Time(sec=102)))
    messages = []
    node.imu_pub = object()
    node._safe_publish_ros = lambda _publisher, message: messages.append(message)
    telemetry = SimpleNamespace(
        pc104_time_valid=True, pc104_uptime_ms=1010,
        gyro_x_rps=0., gyro_y_rps=0., gyro_z_rps=0.)
    assert not node._publish_protocol_imu(
        telemetry, Time(sec=100, nanosec=10000000), (0., 0., 0., 1.))
    assert not messages


def test_legacy_bridge_does_not_enable_packet_time_gate_implicitly():
    node = AUVBridgeNode.__new__(AUVBridgeNode)
    node.require_packet_time_for_imu = False
    assert node._protocol_imu_packet_time_ok(SimpleNamespace(
        pc104_time_valid=False, pc104_uptime_ms=0))


def test_rejected_regression_does_not_rebase_pc104_ros_clock():
    node = AUVBridgeNode.__new__(AUVBridgeNode)
    node.require_packet_time_for_imu = True
    node._last_protocol_imu_packet_uptime_ms = 1000
    node._protocol_pc104_time_base_ms = 1000
    node._protocol_ros_time_base_s = 50.
    node.get_clock = lambda: SimpleNamespace(
        now=lambda: SimpleNamespace(to_msg=lambda: Time(sec=51)))
    stamp = node._make_protocol_header_stamp(SimpleNamespace(
        pc104_time_valid=True, pc104_uptime_ms=900))
    assert stamp.sec == 51
    assert node._protocol_pc104_time_base_ms == 1000
    assert node._protocol_ros_time_base_s == 50.
    resumed = node._make_protocol_header_stamp(SimpleNamespace(
        pc104_time_valid=True, pc104_uptime_ms=1010))
    assert resumed.sec == 50
    assert resumed.nanosec == 10000000

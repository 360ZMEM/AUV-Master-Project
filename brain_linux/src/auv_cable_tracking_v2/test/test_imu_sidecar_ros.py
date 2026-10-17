"""Synthetic loopback packet-to-ROS admission; no physical source claim."""

import socket
import time
import math
from pathlib import Path

import rclpy
from rclpy.parameter import Parameter
from geometry_msgs.msg import TwistStamped
from nav_msgs.msg import Odometry
from sensor_msgs.msg import Imu
from rosgraph_msgs.msg import Clock
from std_msgs.msg import Float32
import yaml

from common.imu_provenance_sidecar import ImuProvenanceV1, encode_imu_provenance
from common.protocol import build_uplink_packet
from auv_cable_tracking_v2.inspection_bridge_node import InspectionBridgeNode
from auv_cable_tracking_v2.imu_sidecar_node import ImuSidecarNode
from auv_localization.auv_localization_node import AUVLocalizationNode


def _frame(sequence, timer, uptime):
    return encode_imu_provenance(ImuProvenanceV1(
        frame_checksum_u16=0x1234, sample_sequence=sequence,
        sensor_timer_ticks=timer, pc104_receive_uptime_ms=uptime,
        roll_rad=0., pitch_rad=0., yaw_rad=0.,
        angular_rate_x_rps=0., angular_rate_y_rps=0., angular_rate_z_rps=0.))


def _spin_pair(receiver, observer, duration_s):
    deadline = time.monotonic() + duration_s
    while time.monotonic() < deadline:
        rclpy.spin_once(receiver, timeout_sec=0.005)
        rclpy.spin_once(observer, timeout_sec=0.005)


def _free_udp_port():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as reserve:
        reserve.bind(('127.0.0.1', 0))
        return reserve.getsockname()[1]


def _spin_many(nodes, duration_s):
    deadline = time.monotonic() + duration_s
    while time.monotonic() < deadline:
        for node in nodes:
            rclpy.spin_once(node, timeout_sec=0.002)


def _wait_many(nodes, predicate, *, timeout_s=3.0):
    """Wait for DDS discovery or a positive message with a bounded deadline."""
    deadline = time.monotonic() + timeout_s
    while not predicate():
        if time.monotonic() >= deadline:
            raise AssertionError('timed out waiting for DDS discovery or message')
        for node in nodes:
            rclpy.spin_once(node, timeout_sec=0.005)


def test_loopback_sidecar_candidate_rejects_damage_replay_and_frozen_timer():
    port = _free_udp_port()
    rclpy.init()
    receiver = observer = None
    try:
        receiver = ImuSidecarNode(parameter_overrides=[Parameter('local_port', value=port)])
        observer = rclpy.create_node('sidecar_loopback_test_observer')
        candidate = []
        navigation = []
        observer.create_subscription(Imu, '/auv/sensors/imu_provenance_candidate',
                                     candidate.append, 10)
        observer.create_subscription(Imu, '/auv/sensors/imu', navigation.append, 10)
        _wait_many((receiver, observer),
                   lambda: receiver.candidate_pub.get_subscription_count() == 1)
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sender:
            sender.sendto(_frame(10, 100000, 1000), ('127.0.0.1', port))
            _wait_many((receiver, observer), lambda: receiver.gate._last is not None)
            assert not candidate
            sender.sendto(_frame(11, 106250, 1100), ('127.0.0.1', port))
            _wait_many((receiver, observer), lambda: len(candidate) >= 1)
            assert len(candidate) == 1
            assert candidate[0].header.frame_id == 'imu/gx3_unaligned'
            bad = bytearray(_frame(12, 112500, 1200))
            bad[20] ^= 1
            sender.sendto(bytes(bad), ('127.0.0.1', port))
            sender.sendto(_frame(11, 106250, 1100), ('127.0.0.1', port))
            sender.sendto(_frame(12, 106250, 1200), ('127.0.0.1', port))
            _spin_pair(receiver, observer, .1)
            assert len(candidate) == 1
            assert not navigation
    finally:
        if observer is not None:
            observer.destroy_node()
        if receiver is not None:
            receiver.destroy_node()
        rclpy.shutdown()


def test_old_uplink_cannot_refresh_imu_or_rotated_dvl_in_sidecar_profile(tmp_path):
    bridge_port = _free_udp_port()
    sidecar_port = _free_udp_port()
    profile = yaml.safe_load((Path(__file__).parents[1] / 'config'
                              / 'inspection_bridge_sidecar_candidate.yaml').read_text())
    profile['bridge']['protocol_udp']['local_port'] = bridge_port
    profile_path = tmp_path / 'bridge.yaml'
    profile_path.write_text(yaml.safe_dump(profile))
    rclpy.init(args=['--ros-args', '-p', f'params_file:={profile_path}',
                     '-p', 'passive_mode:=true'])
    bridge = sidecar = observer = None
    try:
        bridge = InspectionBridgeNode()
        sidecar = ImuSidecarNode(parameter_overrides=[Parameter('local_port', value=sidecar_port)])
        observer = rclpy.create_node('sidecar_mutual_exclusion_observer')
        received = {key: [] for key in ('imu', 'dvl', 'depth', 'candidate')}
        observer.create_subscription(Imu, '/auv/sensors/imu', received['imu'].append, 10)
        observer.create_subscription(TwistStamped, '/auv/sensors/dvl', received['dvl'].append, 10)
        observer.create_subscription(Float32, '/auv/sensors/depth', received['depth'].append, 10)
        observer.create_subscription(Imu, '/auv/sensors/imu_provenance_candidate',
                                     received['candidate'].append, 10)
        nodes = (bridge, sidecar, observer)
        _wait_many(nodes, lambda: bridge.depth_pub.get_subscription_count() == 1
                   and bridge.body_dvl_candidate_pub.get_subscription_count() == 1
                   and sidecar.candidate_pub.get_subscription_count() == 1)
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sender:
            sender.sendto(build_uplink_packet(
                frame_counter=1, heading_deg=40., depth_m=3.,
                pc104_uptime_ms=1000, dvl_bi_uptime_ms=1000),
                ('127.0.0.1', bridge_port))
            _wait_many(nodes, lambda: len(received['depth']) >= 1)
            assert len(received['depth']) == 1
            assert not received['imu'] and not received['dvl']
            sender.sendto(_frame(10, 100000, 1000), ('127.0.0.1', sidecar_port))
            _wait_many(nodes, lambda: sidecar.gate._last is not None)
            sender.sendto(_frame(11, 106250, 1100), ('127.0.0.1', sidecar_port))
            _wait_many(nodes, lambda: len(received['candidate']) >= 1)
        assert len(received['candidate']) == 1
        assert not received['imu'] and not received['dvl']
    finally:
        if observer is not None:
            observer.destroy_node()
        if sidecar is not None:
            sidecar.destroy_node()
        if bridge is not None:
            bridge.destroy_node()
        rclpy.shutdown()


def test_synthetic_fixture_rotates_body_dvl_with_sidecar_yaw_only(tmp_path):
    bridge_port = _free_udp_port()
    sidecar_port = _free_udp_port()
    profile = yaml.safe_load((Path(__file__).parents[1] / 'config'
                              / 'inspection_bridge_sidecar_candidate.yaml').read_text())
    profile['bridge']['protocol_udp']['local_port'] = bridge_port
    profile_path = tmp_path / 'bridge.yaml'
    profile_path.write_text(yaml.safe_dump(profile))
    rclpy.init(args=['--ros-args', '-p', f'params_file:={profile_path}',
                     '-p', 'passive_mode:=true'])
    bridge = sidecar = observer = None
    try:
        bridge = InspectionBridgeNode()
        sidecar = ImuSidecarNode(parameter_overrides=[
            Parameter('local_port', value=sidecar_port),
            Parameter('publish_navigation_imu', value=True),
            Parameter('synthetic_fixture_only', value=True),
            Parameter('yaw_alignment_deg', value=90.0),
            Parameter('synthetic_orientation_variance_rad2', value=0.01),
            Parameter('use_sim_time', value=True),
        ])
        observer = rclpy.create_node('sidecar_dvl_join_observer')
        clock_pub = observer.create_publisher(Clock, '/clock', 10)
        imu = []
        dvl = []
        candidate_dvl = []
        observer.create_subscription(Imu, '/auv/sensors/imu', imu.append, 10)
        observer.create_subscription(TwistStamped, '/auv/sensors/dvl', dvl.append, 10)
        observer.create_subscription(TwistStamped, '/auv/sensors/dvl_provenance_candidate',
                                     candidate_dvl.append, 10)
        nodes = (bridge, sidecar, observer)
        _wait_many(nodes, lambda: sidecar.navigation_pub.get_subscription_count() == 1
                   and sidecar.dvl_navigation_pub.get_subscription_count() == 1
                   and sidecar.dvl_candidate_pub.get_subscription_count() == 1
                   and bridge.body_dvl_candidate_pub.get_subscription_count() == 1
                   and clock_pub.get_subscription_count() == 1)

        def set_time(nanoseconds):
            tick = Clock()
            tick.clock.sec, tick.clock.nanosec = divmod(nanoseconds, 1_000_000_000)
            clock_pub.publish(tick)
            _wait_many(nodes, lambda: sidecar.get_clock().now().nanoseconds == nanoseconds)

        # Preserve the IMV1 board-time deltas independently of host scheduling.
        set_time(100_000_000_000)
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sender:
            sender.sendto(_frame(10, 100000, 1000), ('127.0.0.1', sidecar_port))
            _wait_many(nodes, lambda: sidecar.gate._last is not None)
            body_parameters = [0, 0, 0, 0, 1000, 0, 0, 0, 0, 0, 0, 0]
            sender.sendto(build_uplink_packet(
                frame_counter=1, heading_deg=0., depth_m=3.,
                parameter_values=body_parameters,
                pc104_uptime_ms=1100, dvl_bi_uptime_ms=1100),
                ('127.0.0.1', bridge_port))
            _wait_many(nodes, lambda: sidecar._latest_dvl is not None)
            assert not dvl and not imu
            set_time(100_150_000_000)
            sender.sendto(_frame(11, 109375, 1150), ('127.0.0.1', sidecar_port))
            _wait_many(nodes, lambda: len(imu) >= 1 and len(dvl) >= 1
                       and len(candidate_dvl) >= 1)
            assert len(imu) == 1 and len(dvl) == 1 and len(candidate_dvl) == 1
            # Old $AUV heading is zero and would yield (1, 0, 0). The admitted
            # IMV1 fixture alignment is 90 deg, yielding (0, 1, 0).
            assert abs(dvl[0].twist.linear.x) < 1e-6
            assert abs(dvl[0].twist.linear.y - 1.) < 1e-6
            assert dvl[0].header.frame_id == 'auv/world'
            sender.sendto(build_uplink_packet(
                frame_counter=2, heading_deg=0., depth_m=3.,
                parameter_values=body_parameters,
                pc104_uptime_ms=1200, dvl_bi_uptime_ms=1100),
                ('127.0.0.1', bridge_port))
            _spin_pair(sidecar, observer, .10)
            assert len(dvl) == 1  # repeated DVL sample cannot refresh velocity
            set_time(100_250_000_000)
            sender.sendto(_frame(12, 109375, 1250), ('127.0.0.1', sidecar_port))
            _spin_pair(sidecar, observer, .05)
            sender.sendto(build_uplink_packet(
                frame_counter=3, heading_deg=0., depth_m=3.,
                parameter_values=body_parameters,
                pc104_uptime_ms=1250, dvl_bi_uptime_ms=1150),
                ('127.0.0.1', bridge_port))
            _spin_pair(sidecar, observer, .08)
            assert len(dvl) == 1  # rejected frozen IMU cannot authorize new DVL
    finally:
        if observer is not None:
            observer.destroy_node()
        if sidecar is not None:
            sidecar.destroy_node()
        if bridge is not None:
            bridge.destroy_node()
        rclpy.shutdown()


def test_synthetic_sidecar_dvl_reaches_localization_then_stale_imu_stops_it(tmp_path):
    bridge_port = _free_udp_port()
    sidecar_port = _free_udp_port()
    profile = yaml.safe_load((Path(__file__).parents[1] / 'config'
                              / 'inspection_bridge_sidecar_candidate.yaml').read_text())
    profile['bridge']['protocol_udp']['local_port'] = bridge_port
    profile['ekf'] = {'imu_acc_is_linear': True}
    profile['localization'] = {'use_imu_orientation_measurement': True}
    profile_path = tmp_path / 'combined.yaml'
    profile_path.write_text(yaml.safe_dump(profile))
    rclpy.init(args=['--ros-args', '-p', f'params_file:={profile_path}',
                     '-p', 'passive_mode:=true', '-p', 'navigation_imu_max_age_s:=0.75'])
    bridge = sidecar = localization = observer = None
    try:
        bridge = InspectionBridgeNode()
        sidecar = ImuSidecarNode(parameter_overrides=[
            Parameter('local_port', value=sidecar_port),
            Parameter('publish_navigation_imu', value=True),
            Parameter('synthetic_fixture_only', value=True),
            Parameter('yaw_alignment_deg', value=90.0),
            Parameter('synthetic_orientation_variance_rad2', value=0.01),
        ])
        localization = AUVLocalizationNode()
        observer = rclpy.create_node('sidecar_localization_observer')
        odom = []
        observer.create_subscription(Odometry, '/auv/state/filtered', odom.append, 10)
        nodes = (sidecar, localization, observer)
        _spin_many(nodes, .3)
        body_parameters = [0, 0, 0, 0, 300, 0, 0, 0, 0, 0, 0, 0]
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sender:
            sender.sendto(_frame(10, 100000, 1000), ('127.0.0.1', sidecar_port))
            _spin_many(nodes, .1)
            for step in range(1, 8):
                uptime = 1000 + step * 100
                sender.sendto(build_uplink_packet(
                    frame_counter=step, heading_deg=0., depth_m=3.,
                    parameter_values=body_parameters,
                    pc104_uptime_ms=uptime, dvl_bi_uptime_ms=uptime),
                    ('127.0.0.1', bridge_port))
                _spin_many(nodes, .02)
                sender.sendto(_frame(10 + step, 100000 + step * 6250, uptime),
                              ('127.0.0.1', sidecar_port))
                _spin_many(nodes, .08)
        assert odom, 'matched IMU/DVL/depth should initialize the existing localization node'
        assert all(math.isfinite(msg.pose.pose.position.y) for msg in odom)
        assert abs(odom[-1].twist.twist.linear.x) < .1
        assert abs(odom[-1].twist.twist.linear.y - .3) < .1
        before_stale = len(odom)
        _spin_many(nodes, 1.0)
        after_grace = len(odom)
        _spin_many(nodes, .3)
        assert len(odom) == after_grace  # no timer-driven stale odometry replay
        assert after_grace >= before_stale
    finally:
        if observer is not None:
            observer.destroy_node()
        if localization is not None:
            localization.destroy_node()
        if sidecar is not None:
            sidecar.destroy_node()
        if bridge is not None:
            bridge.destroy_node()
        rclpy.shutdown()

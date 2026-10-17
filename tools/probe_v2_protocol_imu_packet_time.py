#!/usr/bin/env python3
"""Send synthetic $AUV UDP frames to the passive bridge and audit ROS IMU output."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import socket
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from common.protocol import build_uplink_packet
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Imu
from geometry_msgs.msg import TwistStamped


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-json', type=Path, required=True)
    parser.add_argument('--port', type=int, default=53665)
    parser.add_argument('--expect-control', action='store_true')
    args = parser.parse_args()
    if os.getenv('ROS_LOCALHOST_ONLY') != '1' or not os.getenv('ROS_DOMAIN_ID'):
        raise RuntimeError('use ROS_LOCALHOST_ONLY=1 and an isolated ROS_DOMAIN_ID')
    rclpy.init()
    node = Node('inspection_protocol_imu_packet_time_probe')
    received: dict[str, list] = {'imu': [], 'dvl': []}
    node.create_subscription(Imu, '/auv/sensors/imu',
                             lambda msg: received['imu'].append({
                                 'stamp_s': msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9,
                                 'receive_wall_s': time.time(),
                             }), 20)
    node.create_subscription(TwistStamped, '/auv/sensors/dvl',
                             lambda msg: received['dvl'].append(
                                 msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9), 20)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    cases = [('valid_initial', 1000, 1),
             ('valid_advanced_fresh', 1700, 1),
             ('repeated', 1700, 0),
             ('missing_marker', None, 0),
             ('regressed', 900, 0),
             ('advanced_but_stale', 1710, 0)]
    if args.expect_control:
        cases = [(name, uptime, 1) for name, uptime, _ in cases]
    observations = []
    try:
        deadline = time.monotonic() + 10.
        while not node.get_publishers_info_by_topic('/auv/sensors/imu'):
            if time.monotonic() >= deadline:
                raise RuntimeError('no bridge IMU publisher in ROS graph')
            rclpy.spin_once(node, timeout_sec=.1)
        for index, (label, uptime, expected_imu) in enumerate(cases):
            before_imu, before_dvl = len(received['imu']), len(received['dvl'])
            packet = build_uplink_packet(
                frame_counter=index + 1, pc104_uptime_ms=uptime,
                heading_deg=10., depth_m=10., dvl_speed_mps=0.,
            )
            sock.sendto(packet, ('127.0.0.1', args.port))
            until = time.monotonic() + .65
            while time.monotonic() < until:
                rclpy.spin_once(node, timeout_sec=.03)
            observations.append({
                'case': label,
                'pc104_uptime_ms': uptime,
                'expected_imu_increment': expected_imu,
                'imu_increment': len(received['imu']) - before_imu,
                'dvl_increment': len(received['dvl']) - before_dvl,
            })
    finally:
        sock.close()
        node.destroy_node()
        rclpy.shutdown()
    checks = {
        'every_packet_reached_bridge': all(row['dvl_increment'] == 1 for row in observations),
        'imu_publication_matches_expected': all(
            row['imu_increment'] == row['expected_imu_increment'] for row in observations),
        'timebase_behavior_matches_mode': (
            len(received['imu']) == 6
            and received['dvl'][-1] - received['imu'][0]['stamp_s'] > 2.
            if args.expect_control else
            len(received['imu']) == 2
            and len(received['dvl']) == len(cases)
            and abs((received['dvl'][-1] - received['imu'][0]['stamp_s']) - .71) < .005
        ),
    }
    result = {
        'role': ('single_run_local_udp_protocol_to_ros_imu_packet_time_control'
                 if args.expect_control else
                 'single_run_local_udp_protocol_to_ros_imu_packet_time_gate'),
        'cases': observations,
        'counts': {key: len(value) for key, value in received.items()},
        'imu_received_stamps': received['imu'],
        'checks': checks,
        'checks_passed': all(checks.values()),
        'ros_domain_id': os.environ['ROS_DOMAIN_ID'],
        'bridge_passive_mode': True,
        'packet_time_gate_enabled': not args.expect_control,
        'physical_pc104_tested': False,
        'imu_sensor_acquisition_time_tested': False,
        'field_release_authorized': False,
        'source_sha256': {
            'probe': sha(Path(__file__)),
            'bridge': sha(ROOT / 'brain_linux/src/auv_bridge/auv_bridge/bridge_node.py'),
            'fixture': sha(ROOT / 'brain_linux/src/auv_cable_tracking_v2/config' /
                           ('inspection_bridge_packet_time_legacy_sim.yaml'
                            if args.expect_control else 'inspection_bridge_packet_time_sim.yaml')),
        },
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'checks_passed': result['checks_passed'], 'cases': observations},
                     ensure_ascii=False))
    if not result['checks_passed']:
        raise SystemExit(2)


if __name__ == '__main__':
    main()

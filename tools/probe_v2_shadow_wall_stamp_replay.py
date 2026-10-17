#!/usr/bin/env python3
"""Exercise a live-receipt, frozen-stamp IMU fault on the passive ROS stack."""

from __future__ import annotations

import argparse
from collections import Counter
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import time

import numpy as np

from geometry_msgs.msg import TwistStamped
from nav_msgs.msg import Odometry
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Imu, MagneticField
from std_msgs.msg import Bool, Float32, Float32MultiArray, String
from auv_interfaces.msg import Setpoint


ROOT = Path(__file__).resolve().parents[1]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', required=True, type=Path)
    parser.add_argument('--expect-safe', action='store_true')
    parser.add_argument('--healthy-s', default=10., type=float)
    parser.add_argument('--replay-s', default=4., type=float)
    args = parser.parse_args()
    if os.getenv('ROS_LOCALHOST_ONLY') != '1' or not os.getenv('ROS_DOMAIN_ID'):
        raise RuntimeError('use ROS_LOCALHOST_ONLY=1 and an isolated ROS_DOMAIN_ID')
    if not 8. <= args.healthy_s <= 30. or not 3. <= args.replay_s <= 10.:
        raise ValueError('invalid phase durations')
    args.output_dir.mkdir(parents=True, exist_ok=True)
    rclpy.init()
    node = Node('inspection_shadow_wall_stamp_replay_probe')
    counts: Counter[str] = Counter()
    modes: Counter[str] = Counter()
    data: dict = {'capability': None, 'mode': None, 'setpoint_speed': None,
                  'bridge_authorized': None, 'nav_stamp': None}
    trace: list[dict] = []
    sent_mission = False
    capability_healthy_seen = False
    capability_revoked = False
    degraded_seen = False
    zero_speed_seen = False
    bridge_authorized_seen = False
    depth_published_true = False
    nav_at_fault = None
    nav_after_grace = None
    replay_stamp = None

    def nav_cb(msg: Odometry) -> None:
        counts['nav'] += 1
        data['nav_stamp'] = msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9
    def capability_cb(msg: String) -> None:
        counts['capability'] += 1
        try:
            payload = json.loads(msg.data)
            data['capability'] = bool(payload['capabilities']['cable_inspection']['available'])
        except (ValueError, KeyError, TypeError):
            data['capability'] = None
    def track_cb(msg: String) -> None:
        counts['tracking'] += 1
        try:
            payload = json.loads(msg.data)
            mode = str(payload.get('mode', '')).lower()
            data['mode'] = mode
            diagnostics = payload.get('diagnostics') or {}
            data['tracking_reason'] = (
                diagnostics.get('continuity_reason') or diagnostics.get('reason')
                or payload.get('acceptance_flags'))
            data['tracking_payload'] = payload
            modes[mode] += 1
        except (ValueError, TypeError):
            pass
    def speed_cb(msg: Setpoint) -> None:
        counts['setpoint'] += 1
        data['setpoint_speed'] = float(msg.target_speed_mps)
    def bridge_cb(msg: String) -> None:
        counts['bridge'] += 1
        try:
            data['bridge_authorized'] = bool(json.loads(msg.data)['autonomous_execution_authorized'])
        except (ValueError, KeyError, TypeError):
            pass
    def depth_cb(msg: Bool) -> None:
        nonlocal depth_published_true
        counts['depth_valid'] += 1
        depth_published_true |= bool(msg.data)
    def covariance_cb(msg: Float32MultiArray) -> None:
        counts['covariance'] += 1
        try:
            matrix = np.asarray(msg.data, dtype=float).reshape(15, 15)
            data['covariance_diag'] = [float(matrix[i, i]) for i in (0, 1, 3, 4, 8)]
            data['position_min_eigenvalue'] = float(np.linalg.eigvalsh(
                .5 * (matrix[:2, :2] + matrix[:2, :2].T))[0])
        except (ValueError, TypeError):
            data['covariance_diag'] = None

    node.create_subscription(Odometry, '/auv/state/filtered', nav_cb, 20)
    node.create_subscription(Float32MultiArray, '/auv/state/covariance', covariance_cb, 20)
    node.create_subscription(String, '/auv/sensors/runtime_status', capability_cb, 20)
    node.create_subscription(String, '/auv/cable/tracking', track_cb, 20)
    node.create_subscription(Setpoint, '/auv/control/setpoint', speed_cb, 20)
    node.create_subscription(String, '/auv/cable/operational_status', bridge_cb, 20)
    node.create_subscription(Bool, '/auv/cable/depth_valid', depth_cb, 20)
    imu_pub = node.create_publisher(Imu, '/auv/sensors/imu', 10)
    dvl_pub = node.create_publisher(TwistStamped, '/auv/sensors/dvl', 10)
    depth_pub = node.create_publisher(Float32, '/auv/sensors/depth', 10)
    mag_pub = node.create_publisher(MagneticField, '/auv/sensors/magnetic', 10)
    mission_pub = node.create_publisher(String, '/auv/cable/mission_command', 10)

    started = time.monotonic()
    last_sample = -1.
    try:
        while time.monotonic() - started < args.healthy_s + args.replay_s:
            elapsed = time.monotonic() - started
            stamp = node.get_clock().now().to_msg()
            if elapsed >= args.healthy_s:
                if replay_stamp is None:
                    replay_stamp = stamp
                    nav_at_fault = counts['nav']
                if nav_after_grace is None and elapsed >= args.healthy_s + 1.:
                    nav_after_grace = counts['nav']
                imu_stamp = replay_stamp
            else:
                imu_stamp = stamp
            imu = Imu()
            imu.header.stamp = imu_stamp
            imu.header.frame_id = 'auv/imu_link'
            imu.orientation.w = math.cos(math.radians(5.))
            imu.orientation.z = math.sin(math.radians(5.))
            imu.orientation_covariance = [.0001, 0., 0.,
                                          0., .0001, 0.,
                                          0., 0., .0001]
            imu_pub.publish(imu)
            dvl = TwistStamped()
            dvl.header.stamp = stamp
            dvl.header.frame_id = 'world'
            dvl_pub.publish(dvl)
            depth_pub.publish(Float32(data=10.))
            mag = MagneticField()
            mag.header.stamp = stamp
            mag.header.frame_id = 'mag_link'
            mag.magnetic_field.x = 1.e-9
            mag_pub.publish(mag)

            rclpy.spin_once(node, timeout_sec=.02)
            for _ in range(25):
                rclpy.spin_once(node, timeout_sec=0.)
            capability_healthy_seen |= elapsed < args.healthy_s and data['capability'] is True
            if elapsed > args.healthy_s + 1.:
                capability_revoked |= data['capability'] is False
                degraded_seen |= data['mode'] == 'sensor_degraded'
                zero_speed_seen |= data['setpoint_speed'] == 0.
            bridge_authorized_seen |= data['bridge_authorized'] is True
            if (not sent_mission and elapsed > 5. and counts['nav'] >= 5
                    and data['capability'] is True
                    and mission_pub.get_subscription_count() > 0):
                mission_pub.publish(String(data=json.dumps({
                    'mission_type': 'CABLE_INSPECTION', 'target_depth': 10.,
                    'target_speed_mps': .3,
                })))
                sent_mission = True
            if elapsed - last_sample >= .25:
                trace.append({'elapsed_s': round(elapsed, 3),
                              'phase': 'healthy' if elapsed < args.healthy_s else 'stamp_replay',
                              'nav_count': counts['nav'],
                              'nav_stamp_s': data['nav_stamp'],
                              'covariance_diag': data.get('covariance_diag'),
                              'position_min_eigenvalue': data.get('position_min_eigenvalue'),
                              'cable_capability': data['capability'],
                              'tracking_mode': data['mode'],
                              'tracking_reason': data.get('tracking_reason'),
                              'setpoint_speed_mps': data['setpoint_speed'],
                              'bridge_authorized': data['bridge_authorized']})
                last_sample = elapsed
            time.sleep(.025)
    finally:
        node.destroy_node()
        rclpy.shutdown()

    after_grace = counts['nav'] - (nav_after_grace if nav_after_grace is not None else counts['nav'])
    checks = {
        'raw_sensor_to_filtered_nav': counts['nav'] > 5,
        'healthy_inspection_capability': capability_healthy_seen,
        'mission_command_sent': sent_mission,
        'tracking_and_setpoint_output': counts['tracking'] > 0 and counts['setpoint'] > 0,
        'unapproved_synthetic_side_hint_does_not_search': modes['hold'] > 0 and modes['search'] == 0,
        'passive_bridge_never_authorized': not bridge_authorized_seen,
        'no_uncalibrated_depth': not depth_published_true,
        'replay_stops_filtered_navigation': after_grace <= 2,
        'replay_revokes_capability': capability_revoked,
        'replay_degrades_tracking': degraded_seen,
        'replay_sets_zero_speed': zero_speed_seen,
    }
    summary = {
        'role': 'single_run_synthetic_wall_clock_imu_stamp_replay_on_passive_inspection_shadow',
        'ros_domain_id': os.environ['ROS_DOMAIN_ID'],
        'healthy_s': args.healthy_s, 'replay_s': args.replay_s,
        'counts': dict(counts), 'tracking_modes': dict(modes),
        'last_tracking_payload': data.get('tracking_payload'),
        'last_covariance_diag': data.get('covariance_diag'),
        'last_position_min_eigenvalue': data.get('position_min_eigenvalue'),
        'nav_count_after_fault': counts['nav'] - (nav_at_fault or counts['nav']),
        'nav_count_after_one_second_grace': after_grace,
        'checks': checks, 'checks_passed': all(checks.values()),
        'source_sha256': {
            'probe': sha(Path(__file__)),
            'localization': sha(ROOT / 'brain_linux/src/auv_localization/auv_localization/auv_localization_node.py'),
            'shadow_launch': sha(ROOT / 'brain_linux/src/auv_cable_tracking_v2/launch/inspection_shadow_stack.launch.py'),
            'v2_config': sha(ROOT / 'brain_linux/src/auv_cable_tracking_v2/config/cable_tracking_v2_flythrough.yaml'),
            'base_params': sha(ROOT / 'brain_linux/src/auv_cable_tracking_v2/config/inspection_shadow_raw_sensor_sim_params.yaml'),
        },
        'physical_sensors_tested': False, 'field_release_authorized': False,
    }
    (args.output_dir / 'summary.json').write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    with (args.output_dir / 'trace.csv').open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(trace[0]))
        writer.writeheader()
        writer.writerows(trace)
    print(json.dumps({'checks_passed': summary['checks_passed'], 'checks': checks,
                      'nav_count_after_one_second_grace': after_grace,
                      'tracking_modes': dict(modes)}, ensure_ascii=False))
    if args.expect_safe and not summary['checks_passed']:
        raise SystemExit(2)


if __name__ == '__main__':
    main()

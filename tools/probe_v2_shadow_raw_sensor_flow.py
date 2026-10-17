#!/usr/bin/env python3
"""Exercise raw sensors -> localization -> supervisor -> passive v2 stack.

Run beside inspection_shadow_stack.launch.py in an isolated ROS domain. The
input trajectory and magnetic signal are synthetic and remain stationary.
The IMU alone stops in the second phase so a republished old navigation stamp
cannot be mistaken for a fresh observation.
"""

from __future__ import annotations

import argparse
import collections
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import time

from geometry_msgs.msg import TwistStamped
from nav_msgs.msg import Odometry
import rclpy
from rclpy.node import Node
from rosgraph_msgs.msg import Clock
from sensor_msgs.msg import Imu, MagneticField
from std_msgs.msg import Bool, Float32, Float32MultiArray, String
from auv_interfaces.msg import MpcCmd, Setpoint


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / 'AUV-Master-Mag/results/v2/inspection_shadow_sensor_flow_20260927'


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--healthy-s', type=float, default=12.)
    parser.add_argument('--imu-dropout-s', type=float, default=4.)
    parser.add_argument('--output-dir', type=Path, default=DEFAULT_OUT)
    parser.add_argument('--require-safe-dropout', action='store_true')
    args = parser.parse_args()
    if os.environ.get('ROS_LOCALHOST_ONLY') != '1' or not os.environ.get('ROS_DOMAIN_ID'):
        raise RuntimeError('use ROS_LOCALHOST_ONLY=1 and an isolated ROS_DOMAIN_ID')
    if not 8. <= args.healthy_s <= 60. or not 2. <= args.imu_dropout_s <= 20.:
        raise ValueError('healthy-s must be [8,60], imu-dropout-s must be [2,20]')
    args.output_dir.mkdir(parents=True, exist_ok=True)

    rclpy.init()
    node = Node('inspection_shadow_raw_sensor_probe')
    counts = collections.Counter()
    modes = collections.Counter()
    data = {'nav_stamp': None, 'capability': None, 'mode': None,
            'setpoint_speed': None, 'mpc_thrust': None,
            'bridge_authorized': None, 'visual_state': None,
            'inspection_status': None}
    trace: list[dict] = []
    mission_published = False
    nav_after_dropout = 0
    healthy_capability_seen = False
    dropout_capability_false_seen = False
    dropout_tracking_degraded_seen = False
    dropout_zero_setpoint_seen = False
    bridge_authority_true_seen = False
    depth_true_seen = False

    def nav_cb(msg: Odometry) -> None:
        counts['nav'] += 1
        data['nav_stamp'] = msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9
        data['nav_xy'] = [msg.pose.pose.position.x, msg.pose.pose.position.y]
    def capability_cb(msg: String) -> None:
        counts['runtime_status'] += 1
        try:
            payload = json.loads(msg.data)
            data['capability'] = bool(payload['capabilities']['cable_inspection']['available'])
        except (ValueError, KeyError, TypeError):
            data['capability'] = None
    def tracking_cb(msg: String) -> None:
        counts['tracking'] += 1
        try:
            payload = json.loads(msg.data)
            mode = str(payload.get('mode', '')).lower()
            modes[mode] += 1
            data['mode'] = mode
        except (ValueError, TypeError):
            pass
    def setpoint_cb(msg: Setpoint) -> None:
        counts['setpoint'] += 1
        data['setpoint_speed'] = float(msg.target_speed_mps)
    def mpc_cb(msg: MpcCmd) -> None:
        counts['mpc'] += 1
        data['mpc_thrust'] = float(msg.thrust_percent)
    def bridge_cb(msg: String) -> None:
        counts['operational_status'] += 1
        try:
            payload = json.loads(msg.data)
            data['bridge_authorized'] = bool(payload['autonomous_execution_authorized'])
            data['bridge_reason'] = payload.get('authority_reason')
        except (ValueError, KeyError, TypeError):
            pass
    def inspection_cb(msg: String) -> None:
        counts['inspection_status'] += 1
        data['inspection_status'] = msg.data
    def visual_cb(msg: String) -> None:
        counts['visual_state'] += 1
        data['visual_state'] = msg.data
    def depth_cb(msg: Bool) -> None:
        nonlocal depth_true_seen
        counts['depth_valid'] += 1
        depth_true_seen |= bool(msg.data)

    node.create_subscription(Odometry, '/auv/state/filtered', nav_cb, 20)
    node.create_subscription(Float32MultiArray, '/auv/state/covariance',
                             lambda _msg: counts.update(['covariance']), 20)
    node.create_subscription(String, '/auv/sensors/runtime_status', capability_cb, 20)
    node.create_subscription(String, '/auv/cable/tracking', tracking_cb, 20)
    node.create_subscription(Setpoint, '/auv/control/setpoint', setpoint_cb, 20)
    node.create_subscription(MpcCmd, '/auv/control/mpc_cmd', mpc_cb, 20)
    node.create_subscription(String, '/auv/cable/operational_status', bridge_cb, 20)
    node.create_subscription(String, '/auv/cable/inspection_status', inspection_cb, 20)
    node.create_subscription(String, '/auv/visual/mission_state', visual_cb, 20)
    node.create_subscription(Bool, '/auv/cable/depth_valid', depth_cb, 20)

    clock_pub = node.create_publisher(Clock, '/clock', 10)
    imu_pub = node.create_publisher(Imu, '/auv/sensors/imu', 10)
    dvl_pub = node.create_publisher(TwistStamped, '/auv/sensors/dvl', 10)
    depth_pub = node.create_publisher(Float32, '/auv/sensors/depth', 10)
    mag_pub = node.create_publisher(MagneticField, '/auv/sensors/magnetic', 10)
    mission_pub = node.create_publisher(String, '/auv/cable/mission_command', 10)

    started = time.monotonic()
    last_sample = float('-inf')
    nav_count_at_drop = None
    nav_count_after_grace = None
    clock_seconds_at_drop = None
    nav_sources: list[str] = []
    try:
        while time.monotonic() - started < args.healthy_s + args.imu_dropout_s:
            elapsed = time.monotonic() - started
            sensor_stamp = 1. + elapsed
            clock = Clock()
            clock.clock.sec = int(sensor_stamp)
            clock.clock.nanosec = int((sensor_stamp - int(sensor_stamp)) * 1e9)
            clock_pub.publish(clock)
            if elapsed < args.healthy_s:
                imu = Imu()
                imu.header.stamp = clock.clock
                imu.header.frame_id = 'auv/imu_link'
                yaw = math.radians(10.)
                imu.orientation.z = math.sin(yaw / 2.)
                imu.orientation.w = math.cos(yaw / 2.)
                imu_pub.publish(imu)
            else:
                if nav_count_at_drop is None:
                    nav_count_at_drop = counts['nav']
                    clock_seconds_at_drop = sensor_stamp
                if nav_count_after_grace is None and elapsed >= args.healthy_s + 1.:
                    nav_count_after_grace = counts['nav']
                # Keep DVL, depth and magnetometer alive. Only the IMU time
                # anchor disappears, so the navigation gate must catch it.
            dvl = TwistStamped()
            dvl.header.stamp = clock.clock
            dvl.header.frame_id = 'world'
            dvl_pub.publish(dvl)
            depth_pub.publish(Float32(data=10.))
            mag = MagneticField()
            mag.header.stamp = clock.clock
            mag.header.frame_id = 'mag_link'
            mag.magnetic_field.x = 1.e-9
            mag_pub.publish(mag)

            # The probe subscribes to ten output topics. Drain their ready
            # callbacks each cycle; one spin_once would make the observer
            # fall minutes behind a 20 Hz stack and misdate the dropout.
            rclpy.spin_once(node, timeout_sec=.025)
            for _ in range(30):
                rclpy.spin_once(node, timeout_sec=0.)
            healthy_capability_seen |= elapsed < args.healthy_s and data['capability'] is True
            if elapsed > args.healthy_s + 1.:
                dropout_capability_false_seen |= data['capability'] is False
                dropout_tracking_degraded_seen |= data['mode'] == 'sensor_degraded'
                dropout_zero_setpoint_seen |= data['setpoint_speed'] == 0.
            bridge_authority_true_seen |= data['bridge_authorized'] is True

            if (not mission_published and elapsed > 6. and counts['nav'] >= 5
                    and data['capability'] is True
                    and mission_pub.get_subscription_count() > 0):
                mission_pub.publish(String(data=json.dumps({
                    'mission_type': 'CABLE_INSPECTION', 'target_depth': 10.,
                    'target_speed_mps': .3,
                })))
                mission_published = True

            if elapsed - last_sample >= .5:
                nav_sources = sorted({info.node_name for info in
                                      node.get_publishers_info_by_topic('/auv/state/filtered')})
                trace.append({'elapsed_s': round(elapsed, 3),
                              'phase': 'healthy' if elapsed < args.healthy_s else 'imu_dropout',
                              'nav_count': counts['nav'], 'nav_stamp_s': data['nav_stamp'],
                              'nav_x_m': (data.get('nav_xy') or [None, None])[0],
                              'nav_y_m': (data.get('nav_xy') or [None, None])[1],
                              'cable_capability': data['capability'],
                              'tracking_mode': data['mode'],
                              'inspection_status': data['inspection_status'],
                              'setpoint_speed_mps': data['setpoint_speed'],
                              'mpc_thrust_percent': data['mpc_thrust'],
                              'bridge_authorized': data['bridge_authorized'],
                              'visual_state': data['visual_state']})
                last_sample = elapsed
            time.sleep(.035)
    finally:
        node.destroy_node()
        rclpy.shutdown()

    nav_after_dropout = counts['nav'] - (nav_count_at_drop or counts['nav'])
    nav_after_grace = counts['nav'] - (nav_count_after_grace
                                      if nav_count_after_grace is not None else counts['nav'])
    final_stamp_age = (None if data['nav_stamp'] is None else
                       round(1. + args.healthy_s + args.imu_dropout_s - data['nav_stamp'], 3))
    checks = {
        'single_localization_publisher': nav_sources == ['auv_localization_node'],
        'raw_sensor_to_filtered_nav': counts['nav'] > 5 and counts['covariance'] > 5,
        'healthy_inspection_capability': healthy_capability_seen,
        'mission_command_sent': mission_published,
        'tracking_output': counts['tracking'] > 0,
        'setpoint_output': counts['setpoint'] > 0,
        'inspection_status_output': counts['inspection_status'] > 0,
        'visual_state_output': counts['visual_state'] > 0,
        'bridge_status_output': counts['operational_status'] > 0,
        'passive_bridge_never_authorized': not bridge_authority_true_seen,
        'no_uncalibrated_depth': not depth_true_seen,
        'dropout_stops_filtered_navigation': nav_after_grace <= 2,
        'dropout_revokes_capability': dropout_capability_false_seen,
        'dropout_degrades_tracking': dropout_tracking_degraded_seen,
        'dropout_sets_zero_speed': dropout_zero_setpoint_seen,
    }
    result = {
        'role': 'single_run_synthetic_raw_sensor_to_passive_inspection_shadow',
        'ros_domain_id': os.environ['ROS_DOMAIN_ID'],
        'healthy_s': args.healthy_s,
        'imu_dropout_s': args.imu_dropout_s,
        'mission_published': mission_published,
        'counts': dict(counts),
        'tracking_modes': dict(modes),
        'nav_publishers': nav_sources,
        'nav_count_after_imu_dropout': nav_after_dropout,
        'nav_count_after_one_second_grace': nav_after_grace,
        'clock_seconds_at_dropout': clock_seconds_at_drop,
        'final_nav_stamp_age_s': final_stamp_age,
        'checks': checks,
        'checks_passed': all(checks.values()),
        'source_sha256': {
            'probe': sha(Path(__file__)),
            'base_params': sha(ROOT / 'brain_linux/src/auv_cable_tracking_v2/config/'
                               'inspection_shadow_raw_sensor_sim_params.yaml'),
            'v2_config': sha(ROOT / 'brain_linux/src/auv_cable_tracking_v2/config/'
                             'cable_tracking_v2_flythrough.yaml'),
            'localization': sha(ROOT / 'brain_linux/src/auv_localization/auv_localization/'
                                'auv_localization_node.py'),
            'v2_node': sha(ROOT / 'brain_linux/src/auv_cable_tracking_v2/auv_cable_tracking_v2/'
                           'cable_tracking_v2_node.py'),
        },
        'physical_sensors_tested': False,
        'field_release_authorized': False,
    }
    output = args.output_dir / 'summary.json'
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    trace_path = args.output_dir / 'trace.csv'
    with trace_path.open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(trace[0]) if trace else ['elapsed_s'])
        writer.writeheader()
        writer.writerows(trace)
    print(json.dumps({'checks_passed': result['checks_passed'], 'checks': checks,
                      'nav_count_after_imu_dropout': nav_after_dropout,
                      'nav_count_after_one_second_grace': nav_after_grace,
                      'tracking_modes': result['tracking_modes']}, ensure_ascii=False))
    if args.require_safe_dropout and not result['checks_passed']:
        raise SystemExit(2)


if __name__ == '__main__':
    main()

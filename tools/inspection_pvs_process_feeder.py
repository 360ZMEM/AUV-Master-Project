#!/usr/bin/env python3
"""Paced native-PVS or open-loop route-replay fixture for inspection ROS nodes.

This program is a local software fixture. It does not emulate a physical sonar,
PC104 receiver, or a safety bridge, and it must never grant field authority.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
from pathlib import Path
import sys
from threading import Lock, Thread
import time

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import rclpy
from rclpy.executors import SingleThreadedExecutor
from rclpy.node import Node
from auv_interfaces.msg import (ArbiterStatus, MpcCmd, PerceptionQuality,
                                Setpoint, SonarCableObservation)
from nav_msgs.msg import Odometry
from rosgraph_msgs.msg import Clock
from sensor_msgs.msg import MagneticField
from std_msgs.msg import Float32MultiArray, String
from common.protocol import (KEY_BOTTOM, KEY_CONTROL_MODE_BYTE, KEY_LEFT,
                             KEY_ORIENTATION_DEG, KEY_RIGHT, KEY_TARGET_DEPTH_M,
                             KEY_THRUST, KEY_TOP, build_downlink_packet_from_payload,
                             parse_downlink_packet)


MAP_COLUMNS = ('source_stamp_s', 'tick_start_monotonic_s',
               'navigation_publish_before_monotonic_s',
               'navigation_publish_after_monotonic_s',
               'magnetic_publish_before_monotonic_s',
               'magnetic_publish_after_monotonic_s')
TRACE_COLUMNS = ('source_stamp_s', 'monotonic_s', 'x_m', 'y_m', 'heading_deg',
                 'ground_speed_mps', 'setpoint_speed_mps', 'pid_thrust_percent',
                 'codec_rpm', 'applied_rpm', 'setpoint_receipt_age_s', 'pid_receipt_age_s',
                 'mode', 'endpoint_complete', 'depth_published',
                 'sensor_publish_duration_s', 'pvs_step_duration_s',
                 'pvs_step_cpu_duration_s', 'tick_work_duration_s',
                 'sensor_publish_cpu_duration_s', 'sonar_work_duration_s',
                 'sonar_published')


def seconds(stamp) -> float:
    return stamp.sec + stamp.nanosec * 1e-9


def stamp_from_seconds(stamp, value: float) -> None:
    stamp.sec = int(value)
    stamp.nanosec = int(round((value - stamp.sec) * 1e9))


def finite_positive(value: float) -> bool:
    return math.isfinite(value) and value > 0.


def load_replay(path: Path, end_time_s: float) -> dict[str, np.ndarray]:
    with path.open(newline='', encoding='utf-8') as stream:
        rows = list(csv.DictReader(stream))
    names = ('time_s', 'x_m', 'y_m', 'heading_deg',
             'nav_ground_velocity_x_mps', 'nav_ground_velocity_y_mps')
    if len(rows) < 2 or any(name not in rows[0] for name in names):
        raise ValueError('route replay needs two rows and timed pose/ground-velocity columns')
    values = {name: np.asarray([float(row[name]) for row in rows]) for name in names}
    if (not all(np.isfinite(series).all() for series in values.values())
            or not np.all(np.diff(values['time_s']) > 0)
            or values['time_s'][0] > 1.
            or values['time_s'][-1] < end_time_s):
        raise ValueError('route replay times must be finite, increasing and cover requested window')
    values['heading_rad_unwrapped'] = np.unwrap(np.radians(values['heading_deg']))
    return values


def run(args: argparse.Namespace) -> dict:
    if os.environ.get('ROS_LOCALHOST_ONLY') != '1' or not os.environ.get('ROS_DOMAIN_ID'):
        raise RuntimeError('set ROS_LOCALHOST_ONLY=1 and an isolated ROS_DOMAIN_ID')
    if not all(map(finite_positive, (args.max_time_s, args.period_s,
                                     args.startup_timeout_s, args.output_timeout_s))):
        raise ValueError('time limits must be finite and positive')
    if args.period_s < .05 or args.period_s / .05 != round(args.period_s / .05):
        raise ValueError('period-s must be an integer multiple of the native 0.05 s PVS step')
    if args.sonar_every_n < 1:
        raise ValueError('sonar-every-n must be at least 1')
    if not args.config_file.is_file():
        raise FileNotFoundError(args.config_file)
    replay = (load_replay(args.replay_route_csv, 1. + args.max_time_s - args.period_s)
              if args.replay_route_csv is not None else None)
    cfg = yaml.safe_load(args.config_file.read_text(encoding='utf-8'))['cable_tracking']['v2']
    fly = cfg['flythrough']
    prior = yaml.safe_load(args.config_file.read_text(encoding='utf-8'))['cable_tracking']['prior']['yaml_points_ned']
    a, b = np.asarray(prior[0][:2], dtype=float), np.asarray(prior[-1][:2], dtype=float)
    direction = (b - a) / np.linalg.norm(b - a)
    normal = np.array([-direction[1], direction[0]])
    start = a + float(fly['start_along_m']) * direction + float(fly['start_lateral_m']) * normal
    end = a + float(fly['end_along_m']) * direction + float(fly['end_lateral_m']) * normal
    initial_heading = math.degrees(math.atan2(end[1] - start[1], end[0] - start[0]))
    pvs_cfg = {'simulation': {'dt': .05}, 'pvs': {
        'control_mode': 'depthHeadingAutopilot', 'autonomy_motion_model': 'native',
        'initial_depth_m': 10., 'initial_heading_deg': initial_heading,
        'initial_speed_mps': .3, 'initial_rpm': 0., 'reference_rpm': 0.,
        'current_speed_mps': args.current_speed_mps,
        'current_direction_deg': args.current_direction_deg,
    }}
    args.output_dir.mkdir(parents=True, exist_ok=False)
    rclpy.init()
    node = Node('inspection_pvs_process_feeder')
    executor = SingleThreadedExecutor()
    executor.add_node(node)
    receipt_lock = Lock()
    clock_pub = node.create_publisher(Clock, '/clock', 10)
    odom_pub = node.create_publisher(Odometry, '/auv/state/filtered', 10)
    mag_pub = node.create_publisher(MagneticField, '/auv/sensors/magnetic', 10)
    mission_pub = node.create_publisher(String, '/auv/cable/mission_command', 10)
    arbiter_pub = node.create_publisher(ArbiterStatus, '/auv/arbiter/status', 10)
    covariance_pub = node.create_publisher(Float32MultiArray, '/auv/state/covariance', 10)
    sonar_pub = node.create_publisher(SonarCableObservation,
                                      '/auv/sensors/cable_sonar_observation', 10)
    quality_pub = node.create_publisher(PerceptionQuality,
                                        '/auv/perception/quality/sonar', 10)
    latest: dict = {'setpoint': None, 'pid': None, 'tracking': {}, 'depth_valid': False,
                    'setpoint_at': None, 'pid_at': None}

    def on_setpoint(msg: Setpoint) -> None:
        with receipt_lock:
            latest['setpoint'], latest['setpoint_at'] = msg, time.monotonic()

    def on_pid(msg: MpcCmd) -> None:
        with receipt_lock:
            latest['pid'], latest['pid_at'] = msg, time.monotonic()

    def on_tracking(msg: String) -> None:
        try:
            decoded = json.loads(msg.data)
        except json.JSONDecodeError:
            decoded = {}
        with receipt_lock:
            latest['tracking'] = decoded

    node.create_subscription(Setpoint, '/auv/control/setpoint', on_setpoint, 100)
    node.create_subscription(MpcCmd, '/auv/control/mpc_cmd', on_pid, 100)
    node.create_subscription(String, '/auv/cable/tracking', on_tracking, 100)
    require_sonar = bool(fly.get('require_runtime_identity_cue', False))
    if require_sonar:
        calibration = cfg['runtime_identity']['calibration_id']
    covariance = np.eye(15) * .0004
    covariance[0, 0] = covariance[1, 1] = .01
    covariance[8, 8] = math.radians(1.) ** 2
    rng = np.random.default_rng(args.seed)
    plant = None
    if replay is None:
        from sim_holoocean.interfaces.pvs_sim_wrapper import PVSSimWrapper
        plant = PVSSimWrapper(config=pvs_cfg, scenario_cfg={}, agent_name='auv').open()
        plant.eta[:2] = start
    spin_thread = Thread(target=executor.spin, name='pvs_fixture_ros_receipts', daemon=True)
    spin_thread.start()
    rows = []
    published = 0
    mission_sent = False
    startup_started = time.monotonic()
    try:
        with (args.output_dir / 'fixture_source_wall_map.csv').open('w', newline='', encoding='utf-8') as map_file, \
             (args.output_dir / 'pvs_trace.csv').open('w', newline='', encoding='utf-8') as trace_file:
            map_writer = csv.DictWriter(map_file, fieldnames=MAP_COLUMNS)
            trace_writer = csv.DictWriter(trace_file, fieldnames=TRACE_COLUMNS)
            map_writer.writeheader()
            trace_writer.writeheader()
            while time.monotonic() - startup_started < args.startup_timeout_s:
                ready = (mission_pub.get_subscription_count() >= 1
                         and odom_pub.get_subscription_count() >= 2
                         and mag_pub.get_subscription_count() >= 2
                         and node.count_publishers('/auv/control/setpoint') >= 1
                         and node.count_publishers('/auv/control/mpc_cmd') >= 1)
                if ready:
                    break
                time.sleep(.02)
            else:
                raise TimeoutError('product nodes or recorder did not discover feeder topics')
            schedule = time.monotonic()
            for index in range(round(args.max_time_s / args.period_s)):
                next_tick = schedule + index * args.period_s
                while time.monotonic() < next_tick:
                    time.sleep(min(.01, next_tick - time.monotonic()))
                tick_start = time.monotonic()
                tick_cpu_start = time.thread_time()
                t = 1. + index * args.period_s
                clock = Clock()
                stamp_from_seconds(clock.clock, t)
                clock_pub.publish(clock)
                if replay is None:
                    x, y = map(float, plant.eta[:2])
                    heading_rad = float(plant.eta[5])
                    ground_vx = (float(plant.nu[0]) * math.cos(heading_rad)
                                 - float(plant.nu[1]) * math.sin(heading_rad))
                    ground_vy = (float(plant.nu[0]) * math.sin(heading_rad)
                                 + float(plant.nu[1]) * math.cos(heading_rad))
                    depth_m = float(plant.eta[2])
                    vertical_speed = float(plant.nu[2])
                    yaw_rate = float(plant.nu[5])
                else:
                    samples = replay['time_s']
                    x = float(np.interp(t, samples, replay['x_m']))
                    y = float(np.interp(t, samples, replay['y_m']))
                    heading_rad = float(np.interp(t, samples, replay['heading_rad_unwrapped']))
                    ground_vx = float(np.interp(t, samples, replay['nav_ground_velocity_x_mps']))
                    ground_vy = float(np.interp(t, samples, replay['nav_ground_velocity_y_mps']))
                    depth_m, vertical_speed, yaw_rate = 10., 0., 0.
                odom = Odometry()
                odom.header.stamp = clock.clock
                odom.header.frame_id = 'world'
                odom.pose.pose.position.x, odom.pose.pose.position.y = x, y
                odom.pose.pose.position.z = -depth_m
                odom.pose.pose.orientation.z = math.sin(heading_rad / 2.)
                odom.pose.pose.orientation.w = math.cos(heading_rad / 2.)
                odom.twist.twist.linear.x = ground_vx
                odom.twist.twist.linear.y = ground_vy
                odom.twist.twist.linear.z = vertical_speed
                odom.twist.twist.angular.z = yaw_rate
                lateral = float(np.dot(np.asarray([x, y]) - a, normal))
                value_nt = (1. + 20. / math.sqrt(1. + ((lateral - args.cable_lateral_m) / 3.) ** 2)
                            + rng.normal(0., .03))
                magnetic = MagneticField()
                magnetic.header.stamp = clock.clock
                magnetic.magnetic_field.x = value_nt * 1e-9
                nav_before = time.monotonic()
                odom_pub.publish(odom)
                nav_after = time.monotonic()
                mag_before = time.monotonic()
                mag_pub.publish(magnetic)
                mag_after = time.monotonic()
                map_writer.writerow(dict(zip(MAP_COLUMNS, (t, tick_start, nav_before,
                                                          nav_after, mag_before, mag_after))))
                map_file.flush()
                arbiter_pub.publish(ArbiterStatus(active_arbiter='AUTONOMOUS', autonomy_allowed=True))
                sonar_work_duration_s = 0.
                sonar_due = require_sonar and index % args.sonar_every_n == 0
                if sonar_due:
                    sonar_started = time.monotonic()
                    covariance_pub.publish(Float32MultiArray(data=covariance.reshape(-1).tolist()))
                    # Identity is a deliberately idealized fixture tied to true PVS pose.
                    cross_track = args.cable_lateral_m - lateral
                    line_heading = -heading_rad
                    tangent = np.array([math.cos(line_heading), math.sin(line_heading)])
                    normal_body = np.array([-tangent[1], tangent[0]])
                    points = cross_track * normal_body + np.linspace(-5., 5., 20)[:, None] * tangent
                    sonar = SonarCableObservation()
                    sonar.header.stamp = clock.clock
                    sonar.header.frame_id = 'sonar_link'
                    sonar.valid = True
                    sonar.detector_score = 12.
                    sonar.point_x_m, sonar.point_y_m = points[:, 0].tolist(), points[:, 1].tolist()
                    sonar.point_weight = [1.] * 20
                    sonar.contrast_to_noise_ratio, sonar.visible_length_m = 10., 10.
                    sonar.ambiguity_margin = 5.
                    sonar.detector_id = 'synthetic_identity_fixture'
                    quality = PerceptionQuality()
                    quality.header = sonar.header
                    quality.source = 'sonar_cable'
                    quality.validity = PerceptionQuality.VALIDITY_VALID
                    quality.p_track = .99
                    quality.track_probability_calibrated = True
                    quality.estimate = [cross_track, line_heading, float('nan')]
                    quality.covariance = [.0025, 0., 0., 0., .0001, 0., 0., 0., float('nan')]
                    quality.sample_count, quality.data_completeness = 20, 1.
                    quality.calibration_id = calibration
                    sonar_pub.publish(sonar)
                    quality_pub.publish(quality)
                    sonar_work_duration_s = time.monotonic() - sonar_started
                if index >= round(args.prewarm_s / args.period_s) and not mission_sent:
                    mission_pub.publish(String(data=json.dumps({
                        'mission_type': 'CABLE_INSPECTION', 'target_depth': 10.,
                        'target_speed_mps': .3})))
                    mission_sent = True
                sensor_publish_duration_s = time.monotonic() - tick_start
                sensor_publish_cpu_duration_s = time.thread_time() - tick_cpu_start
                # The fixture actuates the latest independently received PID,
                # but refuses a stale or missing output. This is not a bridge.
                with receipt_lock:
                    setpoint = latest['setpoint']
                    pid = latest['pid']
                    setpoint_at = latest['setpoint_at']
                    pid_at = latest['pid_at']
                    tracking = latest['tracking']
                receipt_snapshot_at = time.monotonic()
                sp_age = (receipt_snapshot_at - setpoint_at
                          if setpoint_at is not None else float('inf'))
                pid_age = (receipt_snapshot_at - pid_at
                           if pid_at is not None else float('inf'))
                thrust = (float(pid.thrust_percent)
                          if pid is not None and pid_age <= args.output_timeout_s
                          and setpoint is not None and sp_age <= args.output_timeout_s
                          and setpoint.target_speed_mps > 0 else 0.)
                heading_deg = (math.degrees(float(setpoint.target_heading_rad)) % 360.
                               if setpoint is not None else math.degrees(heading_rad) % 360.)
                target_depth = (float(setpoint.target_depth_m)
                                if setpoint is not None else 10.)
                payload = {KEY_CONTROL_MODE_BYTE: 238,
                           KEY_ORIENTATION_DEG: heading_deg,
                           KEY_TARGET_DEPTH_M: target_depth,
                           KEY_THRUST: thrust, KEY_RIGHT: 0., KEY_LEFT: 0.,
                           KEY_TOP: 0., KEY_BOTTOM: 0.}
                decoded = parse_downlink_packet(build_downlink_packet_from_payload(
                    payload, main_motor_rpm_scale=15.), main_motor_rpm_scale=15.)
                heading_ref = math.degrees(heading_rad) + (
                    decoded.orientation_deg - math.degrees(heading_rad) + 180.) % 360. - 180.
                pvs_step_started = time.monotonic()
                pvs_step_cpu_started = time.thread_time()
                if plant is not None:
                    plant.set_reference(depth_m=decoded.target_depth_m,
                                        heading_rad=math.radians(heading_ref),
                                        propeller_rpm=max(0., decoded.main_motor_rpm))
                    for _ in range(round(args.period_s / .05)):
                        plant.step([0, 0, 0, 0, 0])
                pvs_step_duration_s = time.monotonic() - pvs_step_started
                pvs_step_cpu_duration_s = time.thread_time() - pvs_step_cpu_started
                if plant is not None and not np.isfinite([*plant.eta, *plant.nu, *plant.u_actual]).all():
                    raise AssertionError('PVS state became nonfinite')
                row = {'source_stamp_s': t, 'monotonic_s': tick_start,
                       'x_m': x, 'y_m': y, 'heading_deg': math.degrees(heading_rad),
                       'ground_speed_mps': math.hypot(odom.twist.twist.linear.x,
                                                    odom.twist.twist.linear.y),
                       'setpoint_speed_mps': (float(setpoint.target_speed_mps)
                                              if setpoint is not None else 0.),
                       'pid_thrust_percent': (float(pid.thrust_percent)
                                              if pid is not None else 0.),
                       'codec_rpm': decoded.main_motor_rpm,
                       'applied_rpm': decoded.main_motor_rpm if plant is not None else 0,
                       'setpoint_receipt_age_s': sp_age,
                       'pid_receipt_age_s': pid_age,
                       'mode': tracking.get('mode', ''),
                       'endpoint_complete': bool(tracking.get('endpoint_complete')),
                       'depth_published': tracking.get('burial_depth_m') is not None,
                       'sensor_publish_duration_s': sensor_publish_duration_s,
                       'pvs_step_duration_s': pvs_step_duration_s,
                       'pvs_step_cpu_duration_s': pvs_step_cpu_duration_s,
                       'tick_work_duration_s': time.monotonic() - tick_start,
                       'sensor_publish_cpu_duration_s': sensor_publish_cpu_duration_s,
                       'sonar_work_duration_s': sonar_work_duration_s,
                       'sonar_published': sonar_due}
                trace_writer.writerow(row)
                trace_file.flush()
                rows.append(row)
                published += 1
                if row['endpoint_complete']:
                    break
        result = {'completed': bool(rows and rows[-1]['endpoint_complete']),
                  'ticks': published, 'sim_duration_s': rows[-1]['source_stamp_s'] if rows else None,
                  'max_tick_start_delay_s': max((row['monotonic_s'] - schedule
                                                  - i * args.period_s
                                                  for i, row in enumerate(rows)), default=None),
                  'ever_confirm': any(r['mode'] == 'confirm' for r in rows),
                  'ever_track': any(r['mode'] == 'track' for r in rows),
                  'positive_encoded_rpm_ticks': sum(r['codec_rpm'] > 0 for r in rows),
                  'positive_applied_rpm_ticks': sum(r['applied_rpm'] > 0 for r in rows),
                  'depth_published': any(r['depth_published'] for r in rows),
                  'field_release_authorized': False,
                  'synthetic_target_identity': require_sonar,
                  'sonar_every_n': args.sonar_every_n,
                  'motion_replay_source': str(args.replay_route_csv) if replay is not None else None,
                  'plant_actuation_applied': replay is None,
                  'bridge_connected': False, 'pc104_connected': False,
                  'source_map_file': 'fixture_source_wall_map.csv',
                  'trace_file': 'pvs_trace.csv'}
        (args.output_dir / 'feeder_summary.json').write_text(
            json.dumps(result, indent=2) + '\n', encoding='utf-8')
        return result
    finally:
        if plant is not None:
            plant.close()
        executor.shutdown(timeout_sec=5.)
        spin_thread.join(timeout=5.)
        executor.remove_node(node)
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--config-file', type=Path, required=True)
    parser.add_argument('--max-time-s', type=float, default=1600.)
    parser.add_argument('--period-s', type=float, default=.1)
    parser.add_argument('--prewarm-s', type=float, default=2.)
    parser.add_argument('--startup-timeout-s', type=float, default=60.)
    parser.add_argument('--output-timeout-s', type=float, default=.5)
    parser.add_argument('--current-speed-mps', type=float, default=.05)
    parser.add_argument('--current-direction-deg', type=float, default=90.)
    parser.add_argument('--cable-lateral-m', type=float, default=6.)
    parser.add_argument('--seed', type=int, default=101)
    parser.add_argument('--replay-route-csv', type=Path,
                        help='open-loop dynamic navigation replay; no PVS actuation is applied')
    parser.add_argument('--sonar-every-n', type=int, default=1,
                        help='publish synthetic sonar/covariance every N navigation samples')
    args = parser.parse_args()
    print(json.dumps(run(args), ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()

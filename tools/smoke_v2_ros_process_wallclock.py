#!/usr/bin/env python3
"""Isolated wall-clock ROS liveness probe for the installed v2 node and PID.

Two installed executables run as separate processes. This synthetic fixture
publishes stationary navigation, magnetic data, covariance, clock and arbiter
status at 10 Hz, then interrupts navigation/magnetic inputs. It has no plant,
bridge, UDP downlink, PC104 or vehicle and cannot certify route completion.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import time

import numpy as np
import rclpy
from rclpy.executors import SingleThreadedExecutor
from rclpy.node import Node
from auv_interfaces.msg import ArbiterStatus, MpcCmd, Setpoint
from nav_msgs.msg import Odometry
from rosgraph_msgs.msg import Clock
from sensor_msgs.msg import MagneticField
from std_msgs.msg import Bool, Float32MultiArray, String


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / 'brain_linux/install/auv_cable_tracking_v2/lib/auv_cable_tracking_v2'
CONFIG = ROOT / 'brain_linux/src/auv_cable_tracking_v2/config/cable_tracking_v2_flythrough_transient_gate_sim.yaml'
FIELDS = ('elapsed_s', 'sim_time_s', 'phase', 'topic', 'mode', 'speed_mps',
          'thrust_percent', 'note', 'status', 'depth_valid', 'recovery_required')


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def stop_process(process: subprocess.Popen) -> int:
    if process.poll() is None:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            process.wait(timeout=5.)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=5.)
    return int(process.returncode)


def run(output_dir: Path, healthy_s: float, dropout_s: float,
        recovery_s: float, startup_timeout_s: float, prewarm_s: float,
        trace_algorithm: bool = False, diagnostics_every_n: int = 1,
        multithread_algorithm: bool = False,
        controller_timeout_s: float = 1.5,
        two_rate_supervisor: bool = False,
        algorithm_period_s: float = .1,
        candidate_timeout_s: float = .35,
        maximum_candidate_displacement_m: float = .35) -> dict:
    if os.environ.get('ROS_LOCALHOST_ONLY') != '1' or not os.environ.get('ROS_DOMAIN_ID'):
        raise RuntimeError('set ROS_LOCALHOST_ONLY=1 and an isolated ROS_DOMAIN_ID')
    if not all(math.isfinite(value) and value > 0 for value in
               (healthy_s, dropout_s, recovery_s, startup_timeout_s,
                prewarm_s, controller_timeout_s, algorithm_period_s,
                candidate_timeout_s, maximum_candidate_displacement_m)):
        raise ValueError('durations must be finite and positive')
    if algorithm_period_s != .1 and not two_rate_supervisor:
        raise ValueError('slower inspection decision period requires two-rate supervisor')
    if diagnostics_every_n < 1 or (diagnostics_every_n != 1 and not trace_algorithm):
        raise ValueError('diagnostics cadence override requires --trace-algorithm and n >= 1')
    if multithread_algorithm and not trace_algorithm:
        raise ValueError('multithread algorithm counterfactual requires --trace-algorithm')
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f'output directory must be new or empty: {output_dir}')
    output_dir.mkdir(parents=True, exist_ok=True)
    rclpy.init()
    peer = Node('v2_process_wallclock_fixture')
    executor = SingleThreadedExecutor()
    executor.add_node(peer)
    mission_pub = peer.create_publisher(String, '/auv/cable/mission_command', 10)
    clock_pub = peer.create_publisher(Clock, '/clock', 10)
    odom_pub = peer.create_publisher(Odometry, '/auv/state/filtered', 10)
    mag_pub = peer.create_publisher(MagneticField, '/auv/sensors/magnetic', 10)
    covariance_pub = peer.create_publisher(Float32MultiArray, '/auv/state/covariance', 10)
    arbiter_pub = peer.create_publisher(ArbiterStatus, '/auv/arbiter/status', 10)
    events: list[dict] = []
    start_s = time.monotonic()
    load_at_start = os.getloadavg()
    phase = 'startup'

    def add_event(topic: str, **values) -> None:
        event = {field: '' for field in FIELDS}
        event.update(elapsed_s=time.monotonic() - start_s,
                     sim_time_s=1. + time.monotonic() - start_s,
                     phase=phase, topic=topic, **values)
        events.append(event)

    def on_setpoint(msg: Setpoint) -> None:
        add_event('setpoint', mode=msg.mode, speed_mps=float(msg.target_speed_mps),
                  note=msg.note)

    def on_effort(msg: MpcCmd) -> None:
        add_event('effort', thrust_percent=float(msg.thrust_percent), note=msg.note)

    peer.create_subscription(Setpoint, '/auv/control/setpoint', on_setpoint, 10)
    if two_rate_supervisor:
        peer.create_subscription(Setpoint, '/auv/control/setpoint_candidate',
                                 lambda msg: add_event('candidate', mode=msg.mode,
                                                       speed_mps=float(msg.target_speed_mps),
                                                       note=msg.note), 10)
        peer.create_subscription(String, '/auv/cable/setpoint_supervisor_reason',
                                 lambda msg: add_event('supervisor_reason', status=msg.data), 10)
    peer.create_subscription(MpcCmd, '/auv/control/mpc_cmd', on_effort, 10)
    peer.create_subscription(String, '/auv/cable/inspection_status',
                             lambda msg: add_event('inspection_status', status=msg.data), 10)
    peer.create_subscription(Bool, '/auv/cable/depth_valid',
                             lambda msg: add_event('depth_valid', depth_valid=bool(msg.data)), 10)
    peer.create_subscription(Bool, '/auv/cable/recovery_required',
                             lambda msg: add_event('recovery_required', recovery_required=bool(msg.data)), 10)
    children: list[tuple[str, subprocess.Popen, object]] = []
    child_exit_before_cleanup: dict[str, int | None] = {}
    error = None
    started = False
    fixture_ready_s = None
    mission_start_s = None
    schedule_start_s = None
    sensor_publish_count = 0
    try:
        processes = [
            ('algorithm', PACKAGE / 'cable_tracking_v2_node',
             [f'config_file:={CONFIG}', 'use_sim_time:=true',
              f'inspection_decision_period_s:={algorithm_period_s}']),
            ('controller', PACKAGE / 'inspection_controller_node',
             ['use_sim_time:=true', 'publish_arbiter_command:=true',
              f'inspection_input_timeout_s:={controller_timeout_s}',
              'inspection_speed_feedforward_b:=40.0']),
        ]
        if two_rate_supervisor:
            processes.insert(1, ('supervisor', PACKAGE / 'inspection_setpoint_supervisor_node',
                                 ['use_sim_time:=true',
                                  f'candidate_timeout_s:={candidate_timeout_s}',
                                  f'maximum_candidate_displacement_m:={maximum_candidate_displacement_m}']))
        for name, executable, parameters in processes:
            logfile = (output_dir / f'{name}.log').open('w', encoding='utf-8')
            command = [str(executable), '--ros-args']
            for item in parameters:
                command += ['-p', item]
            if name == 'algorithm' and two_rate_supervisor:
                command += ['-r', '/auv/control/setpoint:=/auv/control/setpoint_candidate']
            if name == 'algorithm' and trace_algorithm:
                command = ['python3', str(ROOT / 'tools/trace_v2_ros_algorithm_callback.py'),
                           '--output-jsonl', str(output_dir / 'algorithm_callback_timing.jsonl'),
                           '--diagnostics-every-n', str(diagnostics_every_n),
                           *(['--separate-timer-group'] if multithread_algorithm else []),
                           '--ros-args']
                for item in parameters:
                    command += ['-p', item]
                if two_rate_supervisor:
                    command += ['-r', '/auv/control/setpoint:=/auv/control/setpoint_candidate']
            process = subprocess.Popen(command, cwd=ROOT, env=os.environ.copy(),
                                       stdout=logfile, stderr=subprocess.STDOUT,
                                       start_new_session=True)
            children.append((name, process, logfile))

        next_publish_s = time.monotonic()
        ready_deadline_s = start_s + startup_timeout_s
        total_s = healthy_s + dropout_s + recovery_s
        while True:
            now_s = time.monotonic()
            for name, process, _ in children:
                if process.poll() is not None:
                    raise RuntimeError(f'{name} exited before cleanup: {process.returncode}')
            if now_s >= next_publish_s:
                clock = Clock()
                stamp_s = 1. + now_s - start_s
                clock.clock.sec = int(stamp_s)
                clock.clock.nanosec = int((stamp_s - int(stamp_s)) * 1e9)
                clock_pub.publish(clock)
                arbiter = ArbiterStatus()
                arbiter.active_arbiter, arbiter.autonomy_allowed = 'AUTONOMOUS', True
                arbiter_pub.publish(arbiter)
                if fixture_ready_s is not None:
                    if mission_start_s is None:
                        phase = 'startup'
                    elif schedule_start_s is None:
                        phase = 'warmup'
                    else:
                        elapsed = now_s - schedule_start_s
                        phase = ('healthy' if elapsed < healthy_s else
                                 'dropout' if elapsed < healthy_s + dropout_s else 'restored')
                    if phase != 'dropout':
                        odom = Odometry()
                        odom.header.stamp = clock.clock
                        odom.header.frame_id = 'world'
                        odom.pose.pose.position.x = -250.
                        odom.pose.pose.position.y = -15.
                        odom.pose.pose.position.z = -10.
                        yaw = math.radians(10.)
                        odom.pose.pose.orientation.z = math.sin(yaw / 2.)
                        odom.pose.pose.orientation.w = math.cos(yaw / 2.)
                        mag = MagneticField()
                        mag.header.stamp = clock.clock
                        mag.magnetic_field.x = (1. + 20. / math.sqrt(1. + ((-15. - 6.) / 3.) ** 2)) * 1e-9
                        covariance = np.eye(15) * .0004
                        covariance[0, 0] = covariance[1, 1] = .01
                        covariance[8, 8] = math.radians(1.) ** 2
                        odom_pub.publish(odom)
                        mag_pub.publish(mag)
                        covariance_pub.publish(Float32MultiArray(data=covariance.reshape(-1).tolist()))
                        sensor_publish_count += 1
                        add_event('fixture_sensor_publish')
                next_publish_s = max(next_publish_s + .1, now_s + .02)
            executor.spin_once(timeout_sec=min(.02, max(0., next_publish_s - time.monotonic())))
            if mission_start_s is None:
                ready = (mission_pub.get_subscription_count() >= 1
                         and clock_pub.get_subscription_count() >= 2
                         and odom_pub.get_subscription_count() >= 2
                         and mag_pub.get_subscription_count() >= 1
                         and covariance_pub.get_subscription_count() >= 1
                         and arbiter_pub.get_subscription_count() >= 1)
                if ready:
                    if fixture_ready_s is None:
                        fixture_ready_s = time.monotonic()
                    if time.monotonic() - fixture_ready_s < prewarm_s or sensor_publish_count < 5:
                        continue
                    mission_pub.publish(String(data=json.dumps({
                        'mission_type': 'CABLE_INSPECTION', 'target_depth': 10.,
                        'target_speed_mps': .3,
                    })))
                    mission_start_s = time.monotonic()
                elif time.monotonic() >= ready_deadline_s:
                    raise TimeoutError('installed ROS nodes did not discover required fixture topics')
            elif schedule_start_s is None:
                warmup_setpoint = any(row['topic'] == 'setpoint' and row['speed_mps'] != ''
                                      and float(row['speed_mps']) > 0 for row in events)
                warmup_effort = any(row['topic'] == 'effort' and row['thrust_percent'] != ''
                                    and float(row['thrust_percent']) > 0 for row in events)
                if warmup_setpoint and warmup_effort:
                    schedule_start_s = time.monotonic()
                    phase = 'healthy'
                    started = True
                elif time.monotonic() >= ready_deadline_s:
                    raise TimeoutError('installed ROS nodes did not produce initial positive setpoint and PID effort')
            elif time.monotonic() >= schedule_start_s + total_s:
                break
    except Exception as exc:
        error = f'{type(exc).__name__}: {exc}'
    finally:
        for name, process, _ in children:
            child_exit_before_cleanup[name] = process.poll()
        child_cleanup_exit = {name: stop_process(process) for name, process, _ in children}
        for _, _, logfile in children:
            logfile.close()
        executor.remove_node(peer)
        peer.destroy_node()
        executor.shutdown()
        if rclpy.ok():
            rclpy.shutdown()

    with (output_dir / 'events.csv').open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(events)

    def count(topic: str, selected_phase: str, positive: bool | None = None) -> int:
        selected = [row for row in events if row['topic'] == topic and row['phase'] == selected_phase]
        if positive is None:
            return len(selected)
        value_key = 'speed_mps' if topic == 'setpoint' else 'thrust_percent'
        return sum((float(row[value_key]) > 0) == positive for row in selected)

    healthy_setpoints = count('setpoint', 'healthy')
    healthy_efforts = count('effort', 'healthy')
    healthy_setpoint_rows = [row for row in events if row['topic'] == 'setpoint' and row['phase'] == 'healthy']
    healthy_setpoint_times = ([schedule_start_s - start_s]
                              + [row['elapsed_s'] for row in healthy_setpoint_rows]
                              + [schedule_start_s - start_s + healthy_s]
                              if schedule_start_s is not None else [])
    healthy_setpoint_max_gap_s = (max(right - left for left, right in
                                      zip(healthy_setpoint_times, healthy_setpoint_times[1:]))
                                  if len(healthy_setpoint_times) >= 2 else None)
    healthy_sensor_times = ([schedule_start_s - start_s]
                            + [row['elapsed_s'] for row in events
                               if row['topic'] == 'fixture_sensor_publish' and row['phase'] == 'healthy']
                            + [schedule_start_s - start_s + healthy_s]
                            if schedule_start_s is not None else [])
    healthy_sensor_max_gap_s = (max(right - left for left, right in
                                    zip(healthy_sensor_times, healthy_sensor_times[1:]))
                                if len(healthy_sensor_times) >= 2 else None)
    healthy_recovery_alarms = sum(row['recovery_required'] is True for row in events
                                  if row['phase'] == 'healthy' and row['topic'] == 'recovery_required')
    dropout_setpoints = [row for row in events if row['topic'] == 'setpoint' and row['phase'] == 'dropout']
    dropout_efforts = [row for row in events if row['topic'] == 'effort' and row['phase'] == 'dropout']
    dropout_start_elapsed_s = (schedule_start_s - start_s + healthy_s
                               if schedule_start_s is not None else None)
    guarded_setpoints = [row for row in dropout_setpoints
                         if dropout_start_elapsed_s is not None
                         and row['elapsed_s'] >= dropout_start_elapsed_s + .7]
    guarded_efforts = [row for row in dropout_efforts
                       if dropout_start_elapsed_s is not None
                       and row['elapsed_s'] >= dropout_start_elapsed_s + 1.7]
    depth_valid_count = sum(row['depth_valid'] is True for row in events if row['topic'] == 'depth_valid')
    all_finite = all(math.isfinite(float(row[key])) for row in events
                     for key in ('speed_mps', 'thrust_percent') if row[key] != '')
    summary = {
        'role': 'isolated_installed_ros_algorithm_controller_wallclock_liveness_probe',
        'start_monotonic_s': start_s,
        'trace_algorithm': trace_algorithm,
        'diagnostics_every_n': diagnostics_every_n,
        'multithread_algorithm': multithread_algorithm,
        'controller_input_timeout_s': controller_timeout_s,
        'two_rate_supervisor': two_rate_supervisor,
        'algorithm_period_s': algorithm_period_s,
        'candidate_timeout_s': candidate_timeout_s,
        'maximum_candidate_displacement_m': maximum_candidate_displacement_m,
        'process_affinity_cpus': sorted(os.sched_getaffinity(0)),
        'host_load_average_at_start': load_at_start,
        'host_load_average_at_end': os.getloadavg(),
        'ros_domain_id': os.environ['ROS_DOMAIN_ID'],
        'healthy_s': healthy_s, 'dropout_s': dropout_s, 'restored_s': recovery_s,
        'startup_completed': started, 'error': error,
        'required_prewarm_s': prewarm_s,
        'fixture_prewarm_s': (None if fixture_ready_s is None or mission_start_s is None
                              else mission_start_s - fixture_ready_s),
        'child_exit_before_cleanup': child_exit_before_cleanup,
        'child_cleanup_exit': child_cleanup_exit,
        'sensor_publish_count': sensor_publish_count,
        'healthy_setpoints': healthy_setpoints,
        'healthy_positive_setpoints': count('setpoint', 'healthy', True),
        'healthy_setpoint_max_gap_s': healthy_setpoint_max_gap_s,
        'healthy_fixture_sensor_max_gap_s': healthy_sensor_max_gap_s,
        'healthy_recovery_alarms': healthy_recovery_alarms,
        'healthy_efforts': healthy_efforts,
        'healthy_positive_efforts': count('effort', 'healthy', True),
        'dropout_setpoints': len(dropout_setpoints),
        'dropout_zero_setpoints': sum(float(row['speed_mps']) == 0 for row in dropout_setpoints),
        'dropout_efforts': len(dropout_efforts),
        'dropout_zero_efforts': sum(float(row['thrust_percent']) == 0 for row in dropout_efforts),
        'guarded_dropout_setpoints': len(guarded_setpoints),
        'guarded_dropout_zero_setpoints': sum(float(row['speed_mps']) == 0 for row in guarded_setpoints),
        'guarded_dropout_efforts': len(guarded_efforts),
        'guarded_dropout_zero_efforts': sum(float(row['thrust_percent']) == 0 for row in guarded_efforts),
        'restored_setpoints': count('setpoint', 'restored'),
        'restored_efforts': count('effort', 'restored'),
        'depth_valid_count': depth_valid_count, 'all_finite': all_finite,
        'simulated_stationary_fixture': True, 'pvs_connected': False,
        'bridge_connected': False, 'hardware_connected': False,
        'source_sha256': sha(Path(__file__)), 'config_sha256': sha(CONFIG),
        'callback_trace_wrapper_sha256': (sha(ROOT / 'tools/trace_v2_ros_algorithm_callback.py')
                                           if trace_algorithm else None),
        'installed_node_sha256': {name: sha(PACKAGE / executable) for name, executable in
                                  ([('algorithm', 'cable_tracking_v2_node'),
                                    ('controller', 'inspection_controller_node')]
                                   + ([('supervisor', 'inspection_setpoint_supervisor_node')]
                                      if two_rate_supervisor else []))},
    }
    summary['liveness_passed'] = bool(
        error is None and started and all(value is None for value in child_exit_before_cleanup.values())
        and healthy_setpoints >= 3 and healthy_efforts >= 3
        and summary['healthy_positive_setpoints'] == healthy_setpoints
        and summary['healthy_positive_efforts'] >= 1
        and healthy_setpoint_max_gap_s is not None and healthy_setpoint_max_gap_s <= .5
        and healthy_sensor_max_gap_s is not None and healthy_sensor_max_gap_s <= .5
        and healthy_recovery_alarms == 0
        and len(guarded_setpoints) > 0 and len(guarded_efforts) > 0
        and summary['guarded_dropout_zero_setpoints'] == len(guarded_setpoints)
        and summary['guarded_dropout_zero_efforts'] == len(guarded_efforts)
        and summary['restored_setpoints'] > 0 and summary['restored_efforts'] > 0
        and depth_valid_count == 0 and all_finite
    )
    (output_dir / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--healthy-s', type=float, default=8.)
    parser.add_argument('--dropout-s', type=float, default=3.)
    parser.add_argument('--recovery-s', type=float, default=5.)
    parser.add_argument('--startup-timeout-s', type=float, default=60.)
    parser.add_argument('--prewarm-s', type=float, default=1.)
    parser.add_argument('--trace-algorithm', action='store_true')
    parser.add_argument('--diagnostics-every-n', type=int, default=1)
    parser.add_argument('--multithread-algorithm', action='store_true')
    parser.add_argument('--controller-timeout-s', type=float, default=1.5)
    parser.add_argument('--two-rate-supervisor', action='store_true')
    parser.add_argument('--algorithm-period-s', type=float, default=.1)
    parser.add_argument('--candidate-timeout-s', type=float, default=.35)
    parser.add_argument('--maximum-candidate-displacement-m', type=float, default=.35)
    args = parser.parse_args()
    result = run(args.output_dir, args.healthy_s, args.dropout_s,
                 args.recovery_s, args.startup_timeout_s, args.prewarm_s,
                 args.trace_algorithm, args.diagnostics_every_n,
                 args.multithread_algorithm, args.controller_timeout_s,
                 args.two_rate_supervisor, args.algorithm_period_s,
                 args.candidate_timeout_s, args.maximum_candidate_displacement_m)
    print(json.dumps(result))
    raise SystemExit(0 if result['liveness_passed'] else 2)


if __name__ == '__main__':
    main()

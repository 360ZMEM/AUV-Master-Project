#!/usr/bin/env python3
"""Fixed-timeline ROS liveness probe with a separate measured 10 Hz feeder."""
import argparse
from collections import Counter
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import time

import rclpy
from rclpy.executors import SingleThreadedExecutor
from rclpy.node import Node
from auv_interfaces.msg import MpcCmd, Setpoint
from std_msgs.msg import Bool, String


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / 'brain_linux/install/auv_cable_tracking_v2/lib/auv_cable_tracking_v2'
CONFIG = ROOT / 'brain_linux/src/auv_cable_tracking_v2/config/cable_tracking_v2_flythrough_transient_gate_sim.yaml'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def stop(proc):
    if proc.poll() is None:
        os.killpg(proc.pid, signal.SIGTERM)
        try:
            proc.wait(timeout=5.)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait(timeout=5.)
    return proc.returncode


def maximum_gap(times, left, right):
    ordered = [left, *sorted(t for t in times if left <= t <= right), right]
    return max((b-a for a,b in zip(ordered, ordered[1:])), default=float('inf'))


def run(args):
    if os.environ.get('ROS_LOCALHOST_ONLY') != '1' or not os.environ.get('ROS_DOMAIN_ID'):
        raise RuntimeError('isolated localhost ROS domain required')
    if not all(math.isfinite(x) and x > 0 for x in
               (args.algorithm_period_s, args.candidate_timeout_s,
                args.displacement_bound_m, args.sensor_timeout_s, args.mission_speed_mps)):
        raise ValueError('positive finite timing and displacement parameters required')
    if not math.isfinite(args.controller_source_timeout_s) or args.controller_source_timeout_s < 0:
        raise ValueError('controller source timeout must be finite and nonnegative')
    config_file = args.config_file.resolve() if args.config_file else CONFIG
    if not config_file.is_file():
        raise FileNotFoundError(config_file)
    topology = {'algorithm': '0-3', 'supervisor': '4', 'controller': '5',
                'feeder': '6', 'observer': 7, 'receipt_recorder': '7'}
    if args.pin_processes and not set(range(8)).issubset(os.sched_getaffinity(0)):
        raise RuntimeError('pin-processes requires available CPUs 0-7')
    args.output_dir.mkdir(parents=True, exist_ok=False)
    rclpy.init()
    peer = Node('inspection_fixed_feeder_observer')
    executor = SingleThreadedExecutor()
    executor.add_node(peer)
    events = []

    def record(topic, *, speed='', mode='', value='', source_stamp_s=''):
        events.append({'monotonic_s': time.monotonic(), 'wall_received_s': time.time(),
                       'topic': topic,
                       'speed_or_thrust': speed, 'mode': mode, 'value': value,
                       'source_stamp_s': source_stamp_s})

    peer.create_subscription(Setpoint, '/auv/control/setpoint',
                             lambda msg: record('setpoint', speed=float(msg.target_speed_mps),
                                                mode=msg.mode, value=msg.note,
                                                source_stamp_s=msg.header.stamp.sec
                                                + msg.header.stamp.nanosec * 1e-9), 10)
    peer.create_subscription(Setpoint, '/auv/control/setpoint_candidate',
                             lambda msg: record('candidate', speed=float(msg.target_speed_mps),
                                                mode=msg.mode, value=msg.note,
                                                source_stamp_s=msg.header.stamp.sec
                                                + msg.header.stamp.nanosec * 1e-9), 10)
    peer.create_subscription(MpcCmd, '/auv/control/mpc_cmd',
                             lambda msg: record('effort', speed=float(msg.thrust_percent),
                                                value=msg.note), 10)
    peer.create_subscription(Bool, '/auv/cable/recovery_required',
                             lambda msg: record('recovery_required', value=str(bool(msg.data))), 10)
    peer.create_subscription(String, '/auv/cable/setpoint_supervisor_reason',
                             lambda msg: record('supervisor_reason', value=msg.data), 10)
    children = []
    early_exit = {}
    cleanup_exit = {}
    error = None
    try:
        use_sim_time = 'false' if args.wall_time else 'true'
        commands = [
            ('algorithm', [str(PACKAGE / 'cable_tracking_v2_node'), '--ros-args',
                           '-p', f'config_file:={config_file}', '-p', f'use_sim_time:={use_sim_time}',
                           '-p', f'inspection_decision_period_s:={args.algorithm_period_s}',
                           '-p', f'inspection_latest_navigation_qos:={str(args.latest_navigation_qos).lower()}',
                           '-p', f'inspection_snapshot_freshness:={str(args.snapshot_freshness).lower()}',
                           '-p', f'inspection_recoverable_input_stale:={str(args.recoverable_input_stale).lower()}',
                           '-r', '/auv/control/setpoint:=/auv/control/setpoint_candidate']),
            ('supervisor', [str(PACKAGE / 'inspection_setpoint_supervisor_node'), '--ros-args',
                            '-p', f'use_sim_time:={use_sim_time}',
                            '-p', f'output_thread_enabled:={str(args.output_thread).lower()}',
                            '-p', f'candidate_timeout_s:={args.candidate_timeout_s}',
                            '-p', f'sensor_timeout_s:={args.sensor_timeout_s}',
                            '-p', f'maximum_candidate_displacement_m:={args.displacement_bound_m}']),
            ('controller', [str(PACKAGE / 'inspection_controller_node'), '--ros-args',
                            '-p', f'use_sim_time:={use_sim_time}', '-p', 'publish_arbiter_command:=true',
                            '-p', 'inspection_input_timeout_s:=1.5',
                            '-p', f'inspection_setpoint_source_timeout_s:={args.controller_source_timeout_s}',
                            '-p', 'inspection_speed_feedforward_b:=40.0']),
            ('feeder', ['python3', str(ROOT / 'tools/inspection_fixed_sensor_feeder.py'),
                        '--events', str(args.output_dir / 'feeder_events.json'),
                        '--startup-timeout-s', str(args.startup_timeout_s),
                        '--mission-speed-mps', str(args.mission_speed_mps),
                        *(['--wall-time-stamps'] if args.wall_time or args.wall_clock_fixture else [])]),
        ]
        if args.trace_algorithm:
            commands[0] = ('algorithm', [
                'python3', str(ROOT / 'tools/trace_v2_ros_algorithm_callback.py'),
                '--output-jsonl', str(args.output_dir / 'algorithm_callback_timing.jsonl'),
                *(['--separate-timer-group'] if args.separate_timer_group else []),
                '--ros-args', '-p', f'config_file:={config_file}', '-p', f'use_sim_time:={use_sim_time}',
                '-p', f'inspection_decision_period_s:={args.algorithm_period_s}',
                '-p', f'inspection_latest_navigation_qos:={str(args.latest_navigation_qos).lower()}',
                '-p', f'inspection_snapshot_freshness:={str(args.snapshot_freshness).lower()}',
                '-p', f'inspection_recoverable_input_stale:={str(args.recoverable_input_stale).lower()}',
                '-r', '/auv/control/setpoint:=/auv/control/setpoint_candidate',
            ])
        if args.telemetry_partition_every_n:
            commands[0] = ('algorithm', [
                'python3', str(ROOT / 'tools/run_v2_diagnostic_telemetry_partition.py'),
                '--every-n', str(args.telemetry_partition_every_n),
                *(['--suppress-full-monitor'] if args.telemetry_partition_suppress_full else []),
                '--stats-path', str(args.output_dir / 'telemetry_partition_counts.json'),
                *commands[0][1][1:],
            ])
        if args.trace_supervisor:
            commands[1] = ('supervisor', [
                'python3', str(ROOT / 'tools/trace_v2_setpoint_supervisor_callback.py'),
                '--output-jsonl', str(args.output_dir / 'supervisor_callback_timing.jsonl'),
                *(['--gate-csv', str(args.output_dir / 'gate_ticks.csv')]
                  if args.record_ros_receipts else []),
                '--ros-args', '-p', f'use_sim_time:={use_sim_time}',
                '-p', f'output_thread_enabled:={str(args.output_thread).lower()}',
                '-p', f'candidate_timeout_s:={args.candidate_timeout_s}',
                '-p', f'sensor_timeout_s:={args.sensor_timeout_s}',
                '-p', f'maximum_candidate_displacement_m:={args.displacement_bound_m}',
            ])
        if args.record_ros_receipts:
            commands.insert(-1, ('receipt_recorder', [
                'python3', str(ROOT / 'tools/record_v2_inspection_ros_timing.py'),
                '--output-dir', str(args.output_dir / 'ros_receipt'),
                '--session-id', args.output_dir.name,
            ]))
        for name, command in commands:
            if args.pin_processes:
                command = ['taskset', '-c', topology[name], *command]
            stream = (args.output_dir / f'{name}.log').open('w', encoding='utf-8')
            proc = subprocess.Popen(command, cwd=ROOT, env=os.environ.copy(),
                                    stdout=stream, stderr=subprocess.STDOUT,
                                    start_new_session=True)
            children.append((name, proc, stream))
        if args.pin_processes:
            os.sched_setaffinity(0, {topology['observer']})
        deadline = time.monotonic() + args.startup_timeout_s + 35.
        while children[-1][1].poll() is None:
            if time.monotonic() > deadline:
                raise TimeoutError('fixed feeder or ROS processes exceeded wallclock deadline')
            for name, proc, _ in children[:-1]:
                if proc.poll() is not None:
                    raise RuntimeError(f'{name} exited early: {proc.returncode}')
            executor.spin_once(timeout_sec=.02)
        for _ in range(20):
            executor.spin_once(timeout_sec=.02)
        if children[-1][1].returncode != 0:
            raise RuntimeError(f'feeder exited: {children[-1][1].returncode}')
    except Exception as exc:
        error = f'{type(exc).__name__}: {exc}'
    finally:
        early_exit = {name: proc.poll() for name, proc, _ in children}
        cleanup_exit = {name: stop(proc) for name, proc, _ in children}
        for _, _, stream in children:
            stream.close()
        executor.remove_node(peer)
        peer.destroy_node()
        executor.shutdown()
        rclpy.shutdown()
    with (args.output_dir / 'observer_events.csv').open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=('monotonic_s','wall_received_s','topic','speed_or_thrust',
                                                    'mode','value','source_stamp_s'))
        writer.writeheader()
        writer.writerows(events)
    feeder_path = args.output_dir / 'feeder_events.json'
    feeder = json.loads(feeder_path.read_text(encoding='utf-8')) if feeder_path.exists() else None
    receipt_path = args.output_dir / 'ros_receipt/capture_summary.json'
    receipt_summary = (json.loads(receipt_path.read_text(encoding='utf-8'))
                       if receipt_path.exists() else None)
    phases = {}
    passed = False
    if feeder is not None:
        start = feeder['start_monotonic_s']
        healthy_start = start + feeder['prewarm_s']
        dropout_start = healthy_start + feeder['healthy_s']
        restored_start = dropout_start + feeder['dropout_s']
        end = restored_start + feeder['recovery_s']
        bounds = {'healthy': (healthy_start, dropout_start),
                  'dropout': (dropout_start, restored_start),
                  'restored': (restored_start, end)}
        for phase, (left, right) in bounds.items():
            selected = [row for row in events if left <= row['monotonic_s'] < right]
            phase_feed = [row for row in feeder['events'] if row['phase'] == phase
                          and row['event'] == 'sensor_tick']
            by_topic = Counter(row['topic'] for row in selected)
            setpoints = [row for row in selected if row['topic'] == 'setpoint']
            efforts = [row for row in selected if row['topic'] == 'effort']
            phases[phase] = {
                'feeder_count': len(phase_feed),
                'feeder_max_gap_s': maximum_gap([row['monotonic_s'] for row in phase_feed], left, right)
                    if phase != 'dropout' else None,
                'setpoint_count': len(setpoints),
                'setpoint_positive': sum(row['speed_or_thrust'] > 0 for row in setpoints),
                'setpoint_max_gap_s': maximum_gap([row['monotonic_s'] for row in setpoints], left, right),
                'effort_count': len(efforts),
                'effort_positive': sum(row['speed_or_thrust'] > 0 for row in efforts),
                'topics': dict(by_topic),
                'reasons': dict(Counter(row['value'] for row in selected
                                        if row['topic'] == 'supervisor_reason')),
            }
            if receipt_summary is not None:
                with (args.output_dir / 'ros_receipt/ros_setpoint.csv').open(
                        newline='', encoding='utf-8') as stream:
                    received = [row for row in csv.DictReader(stream)
                                if left <= float(row['time_s']) < right]
                positive_ages = [float(row['time_s']) - float(row['candidate_source_time_s'])
                                 for row in received if float(row['target_speed_mps']) > 0]
                phases[phase]['receipt_setpoint_count'] = len(received)
                phases[phase]['receipt_positive_setpoint_count'] = len(positive_ages)
                phases[phase]['receipt_max_positive_source_age_s'] = max(positive_ages, default=None)
                phases[phase]['receipt_stale_positive_count'] = sum(
                    age > args.candidate_timeout_s for age in positive_ages)
        guarded_sp = [row for row in events if row['topic'] == 'setpoint'
                      and dropout_start + .75 <= row['monotonic_s'] < restored_start]
        guarded_effort = [row for row in events if row['topic'] == 'effort'
                          and dropout_start + 1.75 <= row['monotonic_s'] < restored_start]
        phases['dropout']['guarded_setpoint_count'] = len(guarded_sp)
        phases['dropout']['guarded_setpoint_zero'] = sum(row['speed_or_thrust'] == 0 for row in guarded_sp)
        phases['dropout']['guarded_effort_count'] = len(guarded_effort)
        phases['dropout']['guarded_effort_zero'] = sum(row['speed_or_thrust'] == 0 for row in guarded_effort)
        healthy = phases['healthy']
        passed = bool(error is None and all(early_exit.get(x) is None for x in ('algorithm','supervisor','controller'))
                      and healthy['feeder_count'] >= 40 and healthy['feeder_max_gap_s'] <= .25
                      and healthy['setpoint_count'] >= 40
                      and healthy['setpoint_positive'] == healthy['setpoint_count']
                      and healthy['setpoint_max_gap_s'] <= .3
                      and phases['dropout']['guarded_setpoint_count'] > 0
                      and phases['dropout']['guarded_setpoint_zero'] == phases['dropout']['guarded_setpoint_count']
                      and phases['dropout']['guarded_effort_count'] > 0
                      and phases['dropout']['guarded_effort_zero'] == phases['dropout']['guarded_effort_count'])
    summary = {'role': 'fixed_feeder_separate_process_algorithm_supervisor_pid_probe',
               'passed': passed, 'error': error, 'ros_domain_id': os.environ['ROS_DOMAIN_ID'],
               'algorithm_period_s': args.algorithm_period_s,
               'latest_navigation_qos': args.latest_navigation_qos,
               'snapshot_freshness': args.snapshot_freshness,
               'recoverable_input_stale': args.recoverable_input_stale,
               'candidate_timeout_s': args.candidate_timeout_s,
               'sensor_timeout_s': args.sensor_timeout_s,
               'wall_time': args.wall_time,
               'wall_clock_fixture': args.wall_clock_fixture,
               'mission_speed_mps': args.mission_speed_mps,
               'controller_source_timeout_s': args.controller_source_timeout_s,
               'maximum_candidate_displacement_m': args.displacement_bound_m,
               'pin_processes': args.pin_processes,
               'trace_algorithm': args.trace_algorithm,
               'telemetry_partition_every_n': args.telemetry_partition_every_n,
               'telemetry_partition_suppress_full': args.telemetry_partition_suppress_full,
               'trace_supervisor': args.trace_supervisor,
               'record_ros_receipts': args.record_ros_receipts,
               'receipt_capture_complete': (receipt_summary.get('capture_complete')
                                            if receipt_summary is not None else None),
               'receipt_data_reviewable': (receipt_summary.get('data_reviewable')
                                           if receipt_summary is not None else None),
               'receipt_positive_source_reviewable': (
                   receipt_summary.get('positive_setpoint_source_reviewable')
                   if receipt_summary is not None else None),
               'output_thread': args.output_thread,
               'separate_timer_group': args.separate_timer_group,
               'process_topology': topology if args.pin_processes else None,
               'child_exit_before_cleanup': early_exit, 'child_cleanup_exit': cleanup_exit,
               'phases': phases, 'source_sha256': sha(Path(__file__)),
               'telemetry_partition_sha256': (
                   sha(ROOT / 'tools/run_v2_diagnostic_telemetry_partition.py')
                   if args.telemetry_partition_every_n else None),
               'feeder_sha256': sha(ROOT / 'tools/inspection_fixed_sensor_feeder.py'),
               'receipt_recorder_sha256': (sha(ROOT / 'tools/record_v2_inspection_ros_timing.py')
                                           if args.record_ros_receipts else None),
               'config_sha256': sha(config_file),
               'algorithm_module_sha256': sha(ROOT / 'brain_linux/install/auv_cable_tracking_v2/lib/python3.10/site-packages/auv_cable_tracking_v2/cable_tracking_v2_node.py'),
               'supervisor_module_sha256': sha(ROOT / 'brain_linux/install/auv_cable_tracking_v2/lib/python3.10/site-packages/auv_cable_tracking_v2/inspection_setpoint_supervisor_node.py'),
               'plant_connected': False, 'bridge_connected': False, 'hardware_connected': False}
    (args.output_dir / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', required=True, type=Path)
    parser.add_argument('--algorithm-period-s', type=float, default=.1)
    parser.add_argument('--latest-navigation-qos', action='store_true')
    parser.add_argument('--snapshot-freshness', action='store_true')
    parser.add_argument('--recoverable-input-stale', action='store_true')
    parser.add_argument('--candidate-timeout-s', type=float, default=.35)
    parser.add_argument('--sensor-timeout-s', type=float, default=.5)
    parser.add_argument('--mission-speed-mps', type=float, default=.3)
    parser.add_argument('--controller-source-timeout-s', type=float, default=0.,
                        help='enable opt-in PID check of final Setpoint source age')
    parser.add_argument('--wall-time', action='store_true',
                        help='use system-clock sensor stamps with use_sim_time=false')
    parser.add_argument('--wall-clock-fixture', action='store_true',
                        help='use system-clock /clock and sensor stamps while retaining simulated-gate status')
    parser.add_argument('--config-file', type=Path)
    parser.add_argument('--displacement-bound-m', type=float, default=.35)
    parser.add_argument('--startup-timeout-s', type=float, default=60.)
    parser.add_argument('--pin-processes', action='store_true')
    parser.add_argument('--trace-algorithm', action='store_true')
    parser.add_argument('--telemetry-partition-every-n', type=int, default=0)
    parser.add_argument('--telemetry-partition-suppress-full', action='store_true')
    parser.add_argument('--trace-supervisor', action='store_true')
    parser.add_argument('--record-ros-receipts', action='store_true',
                        help='independent DDS receipt CSV; requires system-epoch stamps and supervisor trace')
    parser.add_argument('--output-thread', action='store_true')
    parser.add_argument('--separate-timer-group', action='store_true')
    args = parser.parse_args()
    if args.wall_time and args.wall_clock_fixture:
        parser.error('--wall-time and --wall-clock-fixture are mutually exclusive')
    if args.separate_timer_group and not args.trace_algorithm:
        parser.error('--separate-timer-group requires --trace-algorithm')
    if args.recoverable_input_stale and not args.snapshot_freshness:
        parser.error('--recoverable-input-stale requires --snapshot-freshness')
    if args.telemetry_partition_every_n and args.trace_algorithm:
        parser.error('--telemetry-partition-every-n cannot be used with --trace-algorithm')
    if args.telemetry_partition_suppress_full and not args.telemetry_partition_every_n:
        parser.error('--telemetry-partition-suppress-full requires --telemetry-partition-every-n')
    if args.telemetry_partition_every_n and args.telemetry_partition_every_n < 2:
        parser.error('--telemetry-partition-every-n must be at least 2')
    if args.record_ros_receipts and not (args.wall_clock_fixture or args.wall_time):
        parser.error('--record-ros-receipts requires --wall-clock-fixture or --wall-time')
    if args.record_ros_receipts and not args.trace_supervisor:
        parser.error('--record-ros-receipts requires --trace-supervisor')
    result = run(args)
    print(json.dumps(result))
    raise SystemExit(0 if result['passed'] else 2)

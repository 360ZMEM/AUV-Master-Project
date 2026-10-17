#!/usr/bin/env python3
"""Run installed inspection and PID nodes against paced PVS or route replay.

Algorithm, PID, feeder and ROS receipt recorder are four separate processes.
Open-loop route replay removes PVS compute but does not test closed-loop motion.
Both are local diagnostic topologies without the physical bridge or PC104.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / 'brain_linux/install/auv_cable_tracking_v2/lib/auv_cable_tracking_v2'
INSTALLED_MODULES = ROOT / 'brain_linux/install/auv_cable_tracking_v2/lib/python3.10/site-packages/auv_cable_tracking_v2'
CONFIG = (ROOT / 'AUV-Master-Mag/results/v2/'
          'inspection_route_budget_clockfix_20260927/sonar_route_budget_sim.yaml')


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stop(proc: subprocess.Popen) -> int:
    if proc.poll() is None:
        os.killpg(proc.pid, signal.SIGTERM)
        try:
            return proc.wait(timeout=20.)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
    return proc.wait()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--config-file', type=Path, default=CONFIG)
    parser.add_argument('--max-time-s', type=float, default=1600.)
    parser.add_argument('--wall-timeout-s', type=float, default=1800.)
    parser.add_argument('--period-s', type=float, default=.1)
    parser.add_argument('--current-speed-mps', type=float, default=.05)
    parser.add_argument('--current-direction-deg', type=float, default=90.)
    parser.add_argument('--seed', type=int, default=101)
    parser.add_argument('--trace-algorithm', action='store_true',
                        help='replace the installed algorithm entry point with timing-only wrapper')
    parser.add_argument('--replay-route-csv', type=Path,
                        help='historical dynamic pose to replay in real time without online PVS')
    parser.add_argument('--sonar-every-n', type=int, default=1,
                        help='synthetic sonar/covariance cadence relative to nav/mag feeder')
    args = parser.parse_args()
    if os.environ.get('ROS_LOCALHOST_ONLY') != '1' or not os.environ.get('ROS_DOMAIN_ID'):
        parser.error('set ROS_LOCALHOST_ONLY=1 and an isolated ROS_DOMAIN_ID')
    try:
        import auv_interfaces  # noqa: F401
    except ImportError as exc:
        parser.error(f'source brain_linux/install/setup.bash first: {exc}')
    if not all(math.isfinite(x) and x > 0 for x in
               (args.max_time_s, args.wall_timeout_s, args.period_s)):
        parser.error('time limits and period must be finite and positive')
    if args.sonar_every_n < 1:
        parser.error('sonar-every-n must be at least 1')
    for path in (args.config_file, PACKAGE / 'cable_tracking_v2_node',
                 PACKAGE / 'inspection_controller_node',
                 INSTALLED_MODULES / 'cable_tracking_v2_node.py',
                 INSTALLED_MODULES / 'inspection_controller_node.py'):
        if not path.is_file():
            parser.error(f'missing installed input: {path}')
    if args.replay_route_csv is not None and not args.replay_route_csv.is_file():
        parser.error(f'missing route replay: {args.replay_route_csv}')
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=False)
    input_paths = (Path(__file__), ROOT / 'tools/inspection_pvs_process_feeder.py',
                   ROOT / 'tools/record_v2_inspection_ros_timing.py',
                   args.config_file.resolve(), PACKAGE / 'cable_tracking_v2_node',
                   PACKAGE / 'inspection_controller_node',
                   INSTALLED_MODULES / 'cable_tracking_v2_node.py',
                   INSTALLED_MODULES / 'inspection_controller_node.py')
    if args.trace_algorithm:
        input_paths += (ROOT / 'tools/trace_v2_ros_algorithm_callback.py',)
    if args.replay_route_csv is not None:
        input_paths += (args.replay_route_csv.resolve(),)
    prelaunch_input_sha256 = {
        str(path.relative_to(ROOT) if path.is_relative_to(ROOT) else path): digest(path)
        for path in input_paths}
    data_root = output / 'data_root'
    data_root.mkdir()
    env = dict(os.environ, AUV_DATA_ROOT=str(data_root))
    commands = {
        'algorithm': [str(PACKAGE / 'cable_tracking_v2_node'), '--ros-args',
                      '-p', f'config_file:={args.config_file.resolve()}',
                      '-p', 'use_sim_time:=true',
                      '-p', 'publish_arbiter_command:=true'],
        'controller': [str(PACKAGE / 'inspection_controller_node'), '--ros-args',
                       '-p', 'use_sim_time:=true',
                       '-p', 'publish_arbiter_command:=true',
                       '-p', 'inspection_speed_feedforward_b:=40.0'],
        'recorder': [sys.executable, str(ROOT / 'tools/record_v2_inspection_ros_timing.py'),
                     '--output-dir', str(output / 'ros_receipt'),
                     '--session-id', output.name, '--queue-size', '50000'],
        'feeder': [sys.executable, str(ROOT / 'tools/inspection_pvs_process_feeder.py'),
                   '--output-dir', str(output / 'pvs_fixture'),
                   '--config-file', str(args.config_file.resolve()),
                   '--max-time-s', str(args.max_time_s),
                   '--period-s', str(args.period_s),
                   '--current-speed-mps', str(args.current_speed_mps),
                   '--current-direction-deg', str(args.current_direction_deg),
                   '--seed', str(args.seed),
                   '--sonar-every-n', str(args.sonar_every_n)],
    }
    if args.trace_algorithm:
        commands['algorithm'] = [
            sys.executable, str(ROOT / 'tools/trace_v2_ros_algorithm_callback.py'),
            '--output-jsonl', str(output / 'algorithm_callback_timing.jsonl'),
            *commands['algorithm'][1:]]
    if args.replay_route_csv is not None:
        commands['feeder'] += ['--replay-route-csv', str(args.replay_route_csv.resolve())]
    processes = {}
    streams = {}
    early_exit = {}
    cleanup_exit = {}
    error = None
    timed_out = False
    started = time.time()
    try:
        for name in ('recorder', 'algorithm', 'controller', 'feeder'):
            stream = (output / f'{name}.log').open('w', encoding='utf-8')
            streams[name] = stream
            processes[name] = subprocess.Popen(
                commands[name], cwd=ROOT, env=env, stdout=stream,
                stderr=subprocess.STDOUT, start_new_session=True)
        deadline = time.monotonic() + args.wall_timeout_s
        while processes['feeder'].poll() is None:
            if time.monotonic() >= deadline:
                timed_out = True
                break
            for name in ('recorder', 'algorithm', 'controller'):
                if processes[name].poll() is not None:
                    raise RuntimeError(f'{name} exited early: {processes[name].returncode}')
            time.sleep(.1)
        if not timed_out and processes['feeder'].returncode != 0:
            raise RuntimeError(f'feeder exited: {processes["feeder"].returncode}')
    except Exception as exc:
        error = f'{type(exc).__name__}: {exc}'
    finally:
        early_exit = {name: proc.poll() for name, proc in processes.items()}
        cleanup_exit = {name: stop(proc) for name, proc in reversed(list(processes.items()))}
        for stream in streams.values():
            stream.close()
    feeder_summary_path = output / 'pvs_fixture/feeder_summary.json'
    recorder_summary_path = output / 'ros_receipt/capture_summary.json'
    feeder = (json.loads(feeder_summary_path.read_text(encoding='utf-8'))
              if feeder_summary_path.is_file() else None)
    recorder = (json.loads(recorder_summary_path.read_text(encoding='utf-8'))
                if recorder_summary_path.is_file() else None)
    files = sorted(path for path in output.rglob('*') if path.is_file()
                   and path.name != 'same_session_capture.json')
    result = {
        'schema_version': 1,
        'session_id': output.name,
        'started_wall_s': started,
        'elapsed_wall_s': time.time() - started,
        'ros_domain_id': os.environ['ROS_DOMAIN_ID'],
        'commands': commands,
        'early_exit': early_exit,
        'cleanup_exit': cleanup_exit,
        'error': error,
        'timed_out': timed_out,
        'feeder_completed': feeder is not None,
        'software_route_complete': feeder.get('completed') if feeder else None,
        'recorder_capture_complete': recorder.get('capture_complete') if recorder else None,
        'independent_ros_receipt_process_used': 'recorder' in processes,
        'algorithm_and_controller_separate_processes': True,
        'algorithm_timing_wrapper_used': args.trace_algorithm,
        'fixture_clock_is_paced_sim_time': True,
        'motion_replay_source': (str(args.replay_route_csv.resolve())
                                 if args.replay_route_csv is not None else None),
        'sonar_every_n': args.sonar_every_n,
        'plant_actuation_applied': args.replay_route_csv is None,
        'synthetic_sonar_and_magnetic': True,
        'physical_pc104_connected': False,
        'physical_target_evidence': False,
        'strict_continuity_assessed': False,
        'field_release_authorized': False,
        'prelaunch_input_sha256': prelaunch_input_sha256,
        'inputs_unchanged_during_run': all(
            digest(path) == prelaunch_input_sha256[
                str(path.relative_to(ROOT) if path.is_relative_to(ROOT) else path)]
            for path in input_paths),
        'file_sha256': {str(path.relative_to(output)): digest(path) for path in files},
    }
    (output / 'same_session_capture.json').write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(json.dumps({key: result[key] for key in
                      ('session_id', 'error', 'timed_out', 'software_route_complete',
                       'recorder_capture_complete', 'field_release_authorized')},
                     ensure_ascii=False), flush=True)
    return 0 if error is None and not timed_out and feeder is not None \
        and recorder is not None and recorder.get('capture_complete') else 1


if __name__ == '__main__':
    raise SystemExit(main())

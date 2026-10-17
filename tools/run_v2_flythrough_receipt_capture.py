#!/usr/bin/env python3
"""Run one synthetic full ROS/PVS inspection with an independent DDS recorder.

Source the installed ROS workspace before invoking this program. The run is a
local software experiment; no PC104 or physical sensor is connected.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = (ROOT / 'AUV-Master-Mag/results/v2/'
                  'inspection_route_budget_clockfix_20260927/sonar_route_budget_sim.yaml')


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--config-file', type=Path, default=DEFAULT_CONFIG)
    parser.add_argument('--max-time-s', type=float, default=1600.)
    parser.add_argument('--wall-timeout-s', type=float, default=1800.)
    parser.add_argument('--current-speed-mps', type=float, default=.05)
    parser.add_argument('--current-direction-deg', type=float, default=90.)
    parser.add_argument('--inspection-current-step-mps', type=float)
    parser.add_argument('--inspection-current-step-direction-deg', type=float, default=270.)
    parser.add_argument('--post-hold-coast-s', type=float, default=60.)
    parser.add_argument('--seed', type=int, default=101)
    args = parser.parse_args()
    if os.environ.get('ROS_LOCALHOST_ONLY') != '1' or not os.environ.get('ROS_DOMAIN_ID'):
        parser.error('set ROS_LOCALHOST_ONLY=1 and an isolated ROS_DOMAIN_ID')
    try:
        import auv_interfaces  # noqa: F401  installed workspace check
    except ImportError as exc:
        parser.error(f'source brain_linux/install/setup.bash first: {exc}')
    if args.max_time_s <= 0 or args.wall_timeout_s <= 0:
        parser.error('time limits must be positive')
    if not args.config_file.is_file():
        parser.error(f'missing config: {args.config_file}')
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=False)
    recorder_dir = output_dir / 'ros_receipt'
    recorder_cmd = [sys.executable, str(ROOT / 'tools/record_v2_inspection_ros_timing.py'),
                    '--output-dir', str(recorder_dir), '--session-id', output_dir.name,
                    '--queue-size', '50000']
    runner_cmd = [sys.executable, str(ROOT / 'tools/smoke_v2_flythrough_ros_pvs.py'),
                  '--case', 'wire', '--seed', str(args.seed),
                  '--max-time-s', str(args.max_time_s),
                  '--config-file', str(args.config_file.resolve()),
                  '--current-speed-mps', str(args.current_speed_mps),
                  '--current-direction-deg', str(args.current_direction_deg),
                  '--post-hold-coast-s', str(args.post_hold_coast_s),
                  '--ground-velocity-from-position', '--sonar-identity-mode', 'target',
                  '--with-bridge', '--record-source-wall-map',
                  '--output-dir', str(output_dir)]
    if args.inspection_current_step_mps is not None:
        runner_cmd += ['--inspection-current-step-mps',
                       str(args.inspection_current_step_mps),
                       '--inspection-current-step-direction-deg',
                       str(args.inspection_current_step_direction_deg)]
    env = dict(os.environ)
    env['AUV_V2_HARNESS_INSTALLED_NODE'] = '1'
    started_wall = time.time()
    runner_returncode = None
    runner_timed_out = False
    recorder_returncode = None
    recorder = None
    runner = None
    startup_error = None
    with (output_dir / 'recorder.log').open('w', encoding='utf-8') as recorder_log, \
         (output_dir / 'runner.log').open('w', encoding='utf-8') as runner_log:
        try:
            recorder = subprocess.Popen(recorder_cmd, cwd=ROOT, env=env,
                                        stdout=recorder_log, stderr=subprocess.STDOUT)
            # Allow the independent subscriber to discover the ROS graph.
            time.sleep(1.5)
            if recorder.poll() is not None:
                startup_error = 'recorder exited before runner startup'
            else:
                runner = subprocess.Popen(runner_cmd, cwd=ROOT, env=env,
                                          stdout=runner_log, stderr=subprocess.STDOUT)
                try:
                    runner_returncode = runner.wait(timeout=args.wall_timeout_s)
                except subprocess.TimeoutExpired:
                    runner_timed_out = True
                    runner.terminate()
                    try:
                        runner_returncode = runner.wait(timeout=10.)
                    except subprocess.TimeoutExpired:
                        runner.kill()
                        runner_returncode = runner.wait()
        finally:
            if runner is not None and runner.poll() is None:
                runner.terminate()
                try:
                    runner_returncode = runner.wait(timeout=10.)
                except subprocess.TimeoutExpired:
                    runner.kill()
                    runner_returncode = runner.wait()
            if recorder is not None:
                if recorder.poll() is None:
                    recorder.send_signal(signal.SIGTERM)
                try:
                    recorder_returncode = recorder.wait(timeout=20.)
                except subprocess.TimeoutExpired:
                    recorder.kill()
                    recorder_returncode = recorder.wait()
    capture_summary_path = recorder_dir / 'capture_summary.json'
    runner_summary_path = output_dir / f'wire_seed_{args.seed}_summary.json'
    recorder_summary = (json.loads(capture_summary_path.read_text(encoding='utf-8'))
                        if capture_summary_path.is_file() else None)
    runner_summary = (json.loads(runner_summary_path.read_text(encoding='utf-8'))
                      if runner_summary_path.is_file() else None)
    paths = [path for path in output_dir.rglob('*') if path.is_file()
             and path.name != 'same_session_capture.json']
    result = {
        'schema_version': 1,
        'session_id': output_dir.name,
        'started_wall_s': started_wall,
        'elapsed_wall_s': time.time() - started_wall,
        'ros_domain_id': env['ROS_DOMAIN_ID'],
        'runner_command': runner_cmd,
        'recorder_command': recorder_cmd,
        'runner_returncode': runner_returncode,
        'startup_error': startup_error,
        'runner_timed_out': runner_timed_out,
        'recorder_returncode': recorder_returncode,
        'runner_summary_present': runner_summary is not None,
        'runner_software_route_complete': (runner_summary.get('completed')
                                           if runner_summary else None),
        'recorder_capture_complete': (recorder_summary.get('capture_complete')
                                      if recorder_summary else None),
        'recorder_data_reviewable_by_epoch_rules': (recorder_summary.get('data_reviewable')
                                                    if recorder_summary else None),
        'fixture_clock_is_accelerated_sim_time': True,
        'independent_ros_receipt_process_used': recorder is not None,
        'physical_pc104_connected': False,
        'physical_source_authenticated': False,
        'field_release_authorized': False,
        'files_sha256': {str(path.relative_to(output_dir)): digest(path)
                         for path in sorted(paths)},
        'wrapper_sha256': digest(Path(__file__)),
        'runner_source_sha256': digest(ROOT / 'tools/smoke_v2_flythrough_ros_pvs.py'),
        'recorder_source_sha256': digest(ROOT / 'tools/record_v2_inspection_ros_timing.py'),
        'config_sha256': digest(args.config_file),
    }
    (output_dir / 'same_session_capture.json').write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({key: result[key] for key in (
        'runner_returncode', 'runner_timed_out', 'runner_software_route_complete',
        'recorder_capture_complete', 'recorder_data_reviewable_by_epoch_rules',
        'field_release_authorized')}, ensure_ascii=False))
    return 0 if runner_returncode == 0 and recorder_returncode == 0 else 2


if __name__ == '__main__':
    raise SystemExit(main())

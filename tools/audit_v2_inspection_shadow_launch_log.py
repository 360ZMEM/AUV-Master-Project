#!/usr/bin/env python3
"""Summarize the bounded passive inspection launch without hiding shutdown traces."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / 'AUV-Master-Mag/results/v2/inspection_shadow_stack_20260927'
PUBLICATION = (ROOT / 'AUV-Master-Mag/docs/v2/publication/'
               'fwhm_v2_experiment_results/data')


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--launch-log', type=Path, default=RESULTS / 'launch.log')
    parser.add_argument('--graph-audit', type=Path, default=RESULTS / 'graph_audit.json')
    parser.add_argument('--scene-audit', type=Path, default=RESULTS / 'scene_fallback_audit.json')
    parser.add_argument('--observed-timeout-exit-code', type=int, required=True,
                        help='Exit code observed by the caller of timeout -s INT 90')
    parser.add_argument('--output-json', type=Path, default=(
        PUBLICATION / 'inspection_v2_shadow_stack_manifest_20260927.json'))
    args = parser.parse_args()

    log = args.launch_log.read_text(encoding='utf-8', errors='replace')
    graph = json.loads(args.graph_audit.read_text(encoding='utf-8'))
    scene = json.loads(args.scene_audit.read_text(encoding='utf-8'))
    # ROS launch does not always print a Ctrl-C marker. The first traceback
    # starts the shutdown region here, provided every traceback terminates in
    # KeyboardInterrupt and the external timeout exit code was 124.
    boundary = log.find('Traceback (most recent call last):')
    pre_shutdown = log[:boundary] if boundary >= 0 else log
    started = re.findall(r'^\[INFO\] \[([^]]+)\]: process started with pid',
                         pre_shutdown, flags=re.MULTILINE)
    runtime_errors = [line for line in pre_shutdown.splitlines()
                      if '[ERROR]' in line or 'Traceback' in line]
    shutdown_traces = len(re.findall(r'Traceback \(most recent call last\):',
                                     log[boundary:] if boundary >= 0 else ''))
    interrupted = len(re.findall(r'\bKeyboardInterrupt\b',
                                 log[boundary:] if boundary >= 0 else ''))
    shutdown_classified = (args.observed_timeout_exit_code == 124
                           and shutdown_traces > 0
                           and shutdown_traces == interrupted)
    result = {
        'role': 'passive_inspection_shadow_stack_launch_snapshot',
        'graph_checks_passed': bool(graph.get('checks_passed')),
        'source_launch_sha256': graph.get('source_sha256'),
        'graph_audit_sha256': digest(args.graph_audit),
        'scene_audit_sha256': digest(args.scene_audit),
        'scene_fallback_checks_passed': bool(scene.get('checks_passed')),
        'launch_log_sha256': digest(args.launch_log),
        'observed_timeout_exit_code': args.observed_timeout_exit_code,
        'started_processes_before_test_shutdown': started,
        'runtime_errors_before_first_shutdown_traceback': runtime_errors,
        'shutdown_traceback_count': shutdown_traces,
        'shutdown_keyboard_interrupt_count': interrupted,
        'shutdown_classified_from_external_exit_and_log': shutdown_classified,
        'physical_actuation_tested': False,
        'field_release_authorized': False,
        'interpretation': ('One live ROS graph snapshot, a bounded no-scene topic audit, '
                           'and a bounded idle launch. '
                           'The 124 exit code was observed by the external timeout caller; '
                           'the log alone cannot prove its cause or sustained stability.'),
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n',
                                encoding='utf-8')
    print(json.dumps({'graph_checks_passed': result['graph_checks_passed'],
                      'started_count': len(started),
                      'runtime_error_count': len(runtime_errors),
                      'shutdown_classified': shutdown_classified}))
    if not (result['graph_checks_passed'] and result['scene_fallback_checks_passed']
            and len(started) == 6
            and not runtime_errors and shutdown_classified):
        raise SystemExit(2)


if __name__ == '__main__':
    main()

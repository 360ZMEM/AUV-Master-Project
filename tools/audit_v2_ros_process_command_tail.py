#!/usr/bin/env python3
"""Audit observable Setpoint-to-PID command tail in isolated ROS probes."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def audit(run: Path) -> dict:
    summary_path = run / 'summary.json'
    events_path = run / 'events.csv'
    summary = json.loads(summary_path.read_text(encoding='utf-8'))
    with events_path.open(newline='', encoding='utf-8') as stream:
        rows = list(csv.DictReader(stream))
    setpoints = [row for row in rows if row['topic'] == 'setpoint' and row['speed_mps'] != '']
    efforts = [row for row in rows if row['topic'] == 'effort' and row['thrust_percent'] != '']
    positive_setpoints = [row for row in setpoints if float(row['speed_mps']) > 0.]
    if not positive_setpoints:
        raise ValueError(f'no positive Setpoint in {run}')
    last_positive_sp = max(positive_setpoints, key=lambda row: float(row['elapsed_s']))
    last_positive_sp_t = float(last_positive_sp['elapsed_s'])
    zero_sp = [row for row in setpoints if float(row['elapsed_s']) > last_positive_sp_t
               and float(row['speed_mps']) == 0.]
    if not zero_sp:
        raise ValueError(f'no subsequent zero Setpoint in {run}')
    first_zero_sp = min(zero_sp, key=lambda row: float(row['elapsed_s']))
    first_zero_sp_t = float(first_zero_sp['elapsed_s'])
    tail_efforts = [row for row in efforts if float(row['elapsed_s']) > last_positive_sp_t]
    positive_tail = [row for row in tail_efforts if float(row['thrust_percent']) > 0.]
    first_zero_effort = next((row for row in tail_efforts if float(row['thrust_percent']) == 0.), None)
    positive_before_zero_sp = [row for row in positive_tail
                               if float(row['elapsed_s']) < first_zero_sp_t]
    positive_after_zero_sp = [row for row in positive_tail
                              if float(row['elapsed_s']) >= first_zero_sp_t]
    return {
        'run': run.name,
        'source_events_sha256': sha(events_path),
        'source_summary_sha256': sha(summary_path),
        'controller_input_timeout_s': summary.get('controller_input_timeout_s', 1.5),
        'controller_input_timeout_provenance': ('summary' if 'controller_input_timeout_s' in summary
                                                else 'original_probe_hardcoded_1.5_s'),
        'last_positive_setpoint_elapsed_s': last_positive_sp_t,
        'first_zero_setpoint_elapsed_s': first_zero_sp_t,
        'positive_setpoint_to_zero_setpoint_s': first_zero_sp_t - last_positive_sp_t,
        'positive_efforts_after_last_positive_setpoint': [
            {'elapsed_s': float(row['elapsed_s']),
             'delay_from_last_positive_setpoint_s': float(row['elapsed_s']) - last_positive_sp_t,
             'thrust_percent': float(row['thrust_percent'])}
            for row in positive_tail
        ],
        'positive_effort_count_before_first_zero_setpoint': len(positive_before_zero_sp),
        'positive_effort_count_after_first_zero_setpoint': len(positive_after_zero_sp),
        'first_zero_effort_elapsed_s': (None if first_zero_effort is None else
                                        float(first_zero_effort['elapsed_s'])),
        'positive_setpoint_to_first_zero_effort_s': (None if first_zero_effort is None else
                                                     float(first_zero_effort['elapsed_s']) - last_positive_sp_t),
        'first_zero_effort_note': None if first_zero_effort is None else first_zero_effort['note'],
        'scope': 'fixture receipt timestamps; no bridge, UDP, PC104 or physical thrust',
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, action='append', required=True)
    parser.add_argument('--output-json', type=Path, required=True)
    args = parser.parse_args()
    result = {'role': 'isolated_ros_process_observable_command_tail_audit',
              'audit_script_sha256': sha(Path(__file__)),
              'cases': [audit(path) for path in args.run]}
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n',
                                encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()

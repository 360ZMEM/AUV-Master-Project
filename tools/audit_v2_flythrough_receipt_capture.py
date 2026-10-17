#!/usr/bin/env python3
"""Join accelerated-PVS fixture publication times with independent DDS receipts.

The joined latency is synthetic fixture publication to receipt on one host's
monotonic clock. It is not a physical sensor acquisition age or field timing
certificate. The recorder's epoch-based age columns are deliberately ignored.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path


def rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline='', encoding='utf-8') as stream:
        return list(csv.DictReader(stream))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stamp_key(value: str) -> int:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f'nonfinite source stamp: {value}')
    return round(number * 1e9)


def audit(directory: Path) -> dict:
    directory = directory.resolve()
    capture = json.loads((directory / 'same_session_capture.json').read_text())
    hash_mismatches = [name for name, expected in capture['files_sha256'].items()
                       if not (directory / name).is_file()
                       or sha256(directory / name) != expected]
    source = rows(directory / 'fixture_source_wall_map.csv')
    stage = rows(directory / 'fixture_stage_wall_timing.csv')
    source_map = {stamp_key(row['source_stamp_s']): row for row in source}
    if len(source_map) != len(source):
        raise ValueError('duplicate source stamp in publication map')
    receipt_dir = directory / 'ros_receipt'
    recorder = json.loads((receipt_dir / 'capture_summary.json').read_text())
    joined = {}
    independent_receipt_by_stamp = {}
    for role, positive_key in [('navigation', None), ('magnetic', None),
                               ('ros_setpoint', 'target_speed_mps'),
                               ('pid', 'thrust_percent')]:
        data = rows(receipt_dir / f'{role}.csv')
        selected = ([row for row in data if float(row[positive_key]) > 0]
                    if positive_key else data)
        matched = []
        unmatched = []
        negative_age = []
        for row in selected:
            key = stamp_key(row['header_stamp_s'])
            publication = source_map.get(key)
            if publication is None:
                unmatched.append(float(row['header_stamp_s']))
                continue
            field = ('navigation_publish_after_monotonic_s'
                     if role == 'navigation' else 'magnetic_publish_after_monotonic_s')
            age = float(row['time_s']) - float(publication[field])
            if age < -1e-3:
                negative_age.append(age)
            if role in ('ros_setpoint', 'pid'):
                independent_receipt_by_stamp.setdefault(role, {})[key] = float(row['time_s'])
            matched.append({'source_stamp_s': float(row['header_stamp_s']),
                            'receipt_monotonic_s': float(row['time_s']),
                            'fixture_publication_to_receipt_s': age})
        ages = [item['fixture_publication_to_receipt_s'] for item in matched]
        gaps = [float(b['time_s']) - float(a['time_s']) for a, b in zip(data, data[1:])]
        joined[role] = {
            'received_count': len(data), 'selected_count': len(selected),
            'mapped_count': len(matched), 'unmapped_stamps_first': unmatched[:5],
            'negative_age_first': negative_age[:5],
            'max_fixture_publication_to_receipt_s': max(ages, default=None),
            'max_receipt_gap_s': max(gaps, default=None),
            'first_joined': matched[:3],
        }
    events_by_stamp: dict[int, list[dict[str, str]]] = {}
    for event in stage:
        events_by_stamp.setdefault(stamp_key(event['source_stamp_s']), []).append(event)
    stage_durations = {}
    for events in events_by_stamp.values():
        for first, second in zip(events, events[1:]):
            name = f"{first['stage']}__to__{second['stage']}"
            duration = float(second['monotonic_s']) - float(first['monotonic_s'])
            stage_durations.setdefault(name, []).append(duration)
    stage_max = {key: max(values) for key, values in stage_durations.items()}
    peer_lag = {}
    for role, stage_name in [('ros_setpoint', 'peer_received_algorithm_outputs'),
                             ('pid', 'peer_received_pid_output')]:
        values = []
        for key, events in events_by_stamp.items():
            independent_time = independent_receipt_by_stamp.get(role, {}).get(key)
            peer_time = next((float(event['monotonic_s']) for event in events
                              if event['stage'] == stage_name), None)
            if independent_time is not None and peer_time is not None:
                values.append({'source_stamp_s': key * 1e-9,
                               'peer_minus_independent_receipt_s': peer_time - independent_time})
        peer_lag[role] = {'matched_count': len(values),
                          'max_peer_minus_independent_receipt_s': max(
                              (row['peer_minus_independent_receipt_s'] for row in values),
                              default=None),
                          'first': values[:3]}
    recording_reviewable = (
        not hash_mismatches and bool(source_map)
        and bool(recorder.get('capture_complete'))
        and not recorder.get('dropped')
        and recorder.get('max_setpoint_publishers_seen') == 1
        and all(joined[role]['selected_count'] > 0
                for role in ('navigation', 'magnetic', 'ros_setpoint', 'pid'))
        and all(not joined[role]['unmapped_stamps_first']
                and not joined[role]['negative_age_first']
                for role in ('navigation', 'magnetic', 'ros_setpoint', 'pid'))
    )
    return {
        'schema_version': 1,
        'session_id': capture['session_id'],
        'evidence_level': 'same_host_accelerated_PVS_fixture_and_independent_DDS_receipts',
        'recording_reviewable': recording_reviewable,
        'hash_mismatches': hash_mismatches,
        'source_map_tick_count': len(source),
        'runner_returncode': capture['runner_returncode'],
        'runner_software_route_complete': capture['runner_software_route_complete'],
        'recorder_capture_complete': recorder.get('capture_complete'),
        'recorder_epoch_source_age_reviewable': recorder.get('positive_setpoint_source_reviewable'),
        'joined': joined,
        'stage_max_interval_s': stage_max,
        'same_host_peer_delivery_lag': peer_lag,
        'strict_continuity_assessed': False,
        'strict_continuity_passed': None,
        'physical_pc104_verified': False,
        'field_release_authorized': False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', type=Path, required=True)
    parser.add_argument('--output-json', type=Path)
    args = parser.parse_args()
    result = audit(args.run_dir)
    output = args.output_json or args.run_dir / 'receipt_join_audit.json'
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({key: result[key] for key in (
        'recording_reviewable', 'source_map_tick_count', 'runner_returncode',
        'runner_software_route_complete', 'strict_continuity_passed',
        'field_release_authorized')}, ensure_ascii=False))
    return 0 if result['recording_reviewable'] else 2


if __name__ == '__main__':
    raise SystemExit(main())

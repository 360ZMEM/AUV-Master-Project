#!/usr/bin/env python3
"""Audit paced, separate-process PVS fixture publications and DDS receipts.

All timestamps used here are same-host monotonic values. The synthetic /clock
stamps cannot be interpreted as Unix-epoch sensor acquisition times.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path


def table(path: Path) -> list[dict[str, str]]:
    with path.open(newline='', encoding='utf-8') as stream:
        return list(csv.DictReader(stream))


def stamp_key(value: str) -> int:
    stamp = float(value)
    if not math.isfinite(stamp):
        raise ValueError('nonfinite source stamp')
    return round(stamp * 1e9)


def maximum_gap(values: list[float]) -> float | None:
    return max((b - a for a, b in zip(values, values[1:])), default=None)


def audit(directory: Path) -> dict:
    directory = directory.resolve()
    manifest = json.loads((directory / 'same_session_capture.json').read_text(encoding='utf-8'))
    mismatches = []
    for name, expected in manifest['file_sha256'].items():
        path = directory / name
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            mismatches.append(name)
    feeder = json.loads((directory / 'pvs_fixture/feeder_summary.json').read_text())
    recorder = json.loads((directory / 'ros_receipt/capture_summary.json').read_text())
    publication = table(directory / 'pvs_fixture/fixture_source_wall_map.csv')
    source = {stamp_key(row['source_stamp_s']): row for row in publication}
    if len(source) != len(publication):
        raise ValueError('duplicate source stamp in PVS fixture map')
    if len(publication) != feeder['ticks']:
        raise ValueError('PVS fixture map length differs from feeder tick count')
    joined = {}
    for role in ('navigation', 'magnetic', 'ros_setpoint', 'pid'):
        data = table(directory / 'ros_receipt' / f'{role}.csv')
        field = ('navigation_publish_before_monotonic_s' if role == 'navigation'
                 else 'magnetic_publish_before_monotonic_s' if role == 'magnetic'
                 else None)
        latencies = []
        unmapped = []
        for row in data:
            published = source.get(stamp_key(row['header_stamp_s']))
            if published is None:
                unmapped.append(row['header_stamp_s'])
            elif field is not None:
                latencies.append(float(row['time_s']) - float(published[field]))
        received = [float(row['time_s']) for row in data]
        positive_column = ('target_speed_mps' if role == 'ros_setpoint'
                           else 'thrust_percent' if role == 'pid' else None)
        joined[role] = {
            'received_count': len(data), 'mapped_count': len(data) - len(unmapped),
            'source_complete': (len(data) == len(source)
                                and {stamp_key(row['header_stamp_s']) for row in data}
                                == set(source)) if role in ('navigation', 'magnetic') else None,
            'unmapped_stamps_first': unmapped[:5],
            'receipt_before_publish_call_first': [x for x in latencies if x < -1e-3][:5],
            'max_sensor_publish_start_to_receipt_s': max(latencies, default=None),
            'max_receipt_gap_s': maximum_gap(received),
            'positive_count': (sum(float(row[positive_column]) > 0 for row in data)
                               if positive_column else None),
        }
    publication_times = [float(row['magnetic_publish_after_monotonic_s'])
                         for row in publication]
    reviewable = (not mismatches and bool(publication)
                  and bool(manifest.get('recorder_capture_complete'))
                  and bool(recorder.get('capture_complete'))
                  and not recorder.get('dropped')
                  and recorder.get('max_setpoint_publishers_seen') == 1
                  and joined['navigation']['source_complete']
                  and joined['magnetic']['source_complete']
                  and all(joined[role]['received_count'] > 0
                          and not joined[role]['unmapped_stamps_first']
                          and not joined[role]['receipt_before_publish_call_first']
                          for role in joined))
    return {
        'schema_version': 1,
        'session_id': manifest['session_id'],
        'evidence_level': 'same_host_paced_PVS_fixture_separate_product_processes_independent_DDS',
        'recording_reviewable': reviewable,
        'hash_mismatches': mismatches,
        'source_map_tick_count': len(publication),
        'max_fixture_publication_gap_s': maximum_gap(publication_times),
        'max_tick_start_delay_s': feeder['max_tick_start_delay_s'],
        'software_route_complete': feeder['completed'],
        'ever_confirm': feeder['ever_confirm'],
        'ever_track': feeder['ever_track'],
        'positive_applied_rpm_ticks': feeder['positive_applied_rpm_ticks'],
        'joined': joined,
        'strict_continuity_assessed': False,
        'physical_pc104_verified': False,
        'field_release_authorized': False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', type=Path, required=True)
    parser.add_argument('--output-json', type=Path)
    args = parser.parse_args()
    result = audit(args.run_dir)
    target = args.output_json or args.run_dir / 'receipt_join_audit.json'
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({key: result[key] for key in (
        'recording_reviewable', 'source_map_tick_count',
        'max_fixture_publication_gap_s', 'software_route_complete',
        'positive_applied_rpm_ticks', 'field_release_authorized')}))
    return 0 if result['recording_reviewable'] else 2


if __name__ == '__main__':
    raise SystemExit(main())

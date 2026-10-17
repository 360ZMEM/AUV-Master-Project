#!/usr/bin/env python3
"""Audit one synchronized inspection timing run; never authorize field use.

The gate CSV is exported from the actual supervisor tick instrumentation, and
the remaining CSVs are independently observed streams from the same session.
This checks an engineering acceptance *candidate*, not physical provenance.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path

try:
    from .analyze_v2_inspection_field_packages import correlate_pc104_receipts
except ImportError:
    from analyze_v2_inspection_field_packages import correlate_pc104_receipts


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / 'AUV-Master-Mag/docs/v2/inspection_timing_envelope_template.json'
ROLES = {
    'gate_ticks': {'time_s', 'end_s', 'decision_speed_mps', 'navigation_receipt_age_s',
                   'navigation_source_age_s', 'magnetic_receipt_age_s',
                   'magnetic_source_age_s', 'covariance_receipt_age_s',
                   'candidate_receipt_age_s', 'candidate_source_age_s',
                   'budget_receipt_age_s', 'budget_latched'},
    'ros_setpoint': {'time_s', 'target_speed_mps', 'candidate_source_time_s'},
    'pid': {'time_s', 'thrust_percent'},
    'udp_downlink': {'time_s', 'frame_number', 'main_motor_rpm'},
    'pc104_receipt': {'time_s', 'frame_number', 'main_motor_rpm'},
    'mission_events': {'time_s', 'event'},
}
ECHO_COLUMNS = {'time_s', 'frame_number', 'pc104_recv_uptime_ms'}
LIMITS = ('max_gate_gap_s', 'max_gate_duration_s', 'max_ros_gap_s',
          'max_pid_gap_s', 'max_udp_gap_s', 'max_pc104_gap_s',
          'max_ros_delivery_s', 'max_sensor_age_s', 'max_candidate_age_s',
          'max_budget_age_s', 'max_pc104_lag_s', 'min_pc104_receipt_fraction',
          'max_local_zero_delay_s', 'max_fault_zero_delay_s')
AGE_COLUMNS = ('navigation_receipt_age_s', 'navigation_source_age_s',
               'magnetic_receipt_age_s', 'magnetic_source_age_s',
               'covariance_receipt_age_s', 'candidate_receipt_age_s',
               'candidate_source_age_s', 'budget_receipt_age_s')


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def number(value, label: str, *, positive: bool = False) -> float:
    x = float(value)
    if not math.isfinite(x) or (positive and x <= 0):
        raise ValueError(f'{label}: finite {"positive " if positive else ""}number required')
    return x


def read_artifact(base: Path, record: dict, label: str) -> Path:
    if not isinstance(record, dict) or not record.get('path') or not record.get('sha256'):
        raise ValueError(f'{label}: path and SHA-256 required')
    path = Path(record['path']).expanduser()
    if not path.is_absolute():
        path = base / path
    path = path.resolve()
    if not path.is_file() or not path.stat().st_size:
        raise ValueError(f'{label}: missing or empty file')
    if digest(path) != record['sha256'].lower():
        raise ValueError(f'{label}: SHA-256 mismatch')
    return path


def read_csv(path: Path, role: str, columns: set[str] | None = None) -> list[dict]:
    required = columns if columns is not None else ROLES[role]
    with path.open(newline='', encoding='utf-8') as stream:
        reader = csv.DictReader(stream)
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f'{role}: missing columns {sorted(missing)}')
        rows = list(reader)
    if len(rows) < 2:
        raise ValueError(f'{role}: at least two rows required')
    times = [number(row['time_s'], f'{role}.time_s') for row in rows]
    if any(b <= a for a, b in zip(times, times[1:])):
        raise ValueError(f'{role}: time_s must increase strictly')
    for row in rows:
        for name in required - {'time_s'}:
            value = str(row[name]).strip()
            if name == 'event':
                if not value:
                    raise ValueError(f'{role}.event: nonempty event required')
                continue
            if not value and role == 'gate_ticks' and name in AGE_COLUMNS:
                continue
            v = number(value, f'{role}.{name}')
            if name in ('frame_number', 'budget_latched', 'pc104_recv_uptime_ms') and (
                    not v.is_integer() or not 0 <= v <=
                    (255 if name == 'frame_number' else 1 if name == 'budget_latched' else math.inf)):
                raise ValueError(f'{role}.{name}: invalid integer')
    if 'pc104_recv_uptime_ms' in required:
        uptimes = [int(r['pc104_recv_uptime_ms']) for r in rows]
        if any(b <= a for a, b in zip(uptimes, uptimes[1:])):
            raise ValueError('pc104 receipt uptime must increase after echo deduplication')
    return rows


def gaps(times: list[float], left: float, right: float) -> float | None:
    inside = [t for t in times if left <= t <= right]
    if not inside:
        return None
    return max(b - a for a, b in zip([left] + inside, inside + [right]))


def zero_tail(rows: list[dict], column: str, fault_s: float, end_s: float,
              max_gap_s: float, max_delay_s: float) -> dict:
    post = [r for r in rows if fault_s <= float(r['time_s']) <= end_s]
    first_zero = next((i for i, r in enumerate(post) if float(r[column]) == 0), None)
    tail = post[first_zero:] if first_zero is not None else []
    first_time = float(tail[0]['time_s']) if tail else None
    max_gap = gaps([float(r['time_s']) for r in tail], first_time, end_s) if tail else None
    passed = bool(len(tail) >= 2 and all(float(r[column]) == 0 for r in tail)
                  and first_time - fault_s <= max_delay_s
                  and max_gap is not None and max_gap <= max_gap_s)
    return {'post_fault_rows': len(post), 'first_zero_delay_s':
            first_time - fault_s if first_time is not None else None,
            'zero_tail_rows': len(tail), 'zero_tail_max_gap_s': max_gap,
            'zero_tail_passed': passed}


def analyze(manifest_path: Path) -> dict:
    blockers: list[str] = []
    flags: list[str] = []
    report = {'role': 'inspection_same_session_timing_envelope',
              'data_reviewable': False, 'timing_bounds_passed': False,
              'field_release_authorized': False, 'blockers': blockers,
              'red_flags': flags, 'audit_script_sha256': digest(Path(__file__))}
    try:
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        if manifest.get('schema_version') != 2:
            raise ValueError('schema_version must be 2 for received-source-age audit')
        for key in ('session_id', 'mission_id', 'target_id', 'platform_id'):
            if not str(manifest.get(key, '')).strip():
                raise ValueError(f'{key} required')
        if manifest.get('data_domain') != 'physical':
            raise ValueError('data_domain must be physical')
        if manifest.get('case_kind') not in ('nominal', 'input_loss'):
            raise ValueError('case_kind must be nominal or input_loss')
        receipt_mode = manifest.get('receipt_mode')
        if receipt_mode not in ('board_command_log', 'checksum_valid_echo'):
            raise ValueError('receipt_mode must be board_command_log or checksum_valid_echo')
        base = manifest_path.resolve().parent
        read_artifact(base, manifest['raw_archive'], 'raw_archive')
        read_artifact(base, manifest['software_snapshot'], 'software_snapshot')
        clock = manifest['clock_alignment']
        if not str(clock.get('method', '')).strip():
            raise ValueError('clock_alignment.method required')
        clock_error = number(clock['measured_max_error_ms'], 'clock error') / 1000
        if clock_error < 0:
            raise ValueError('clock error must be nonnegative')
        read_artifact(base, clock['raw_alignment_trace'], 'clock_alignment.raw_alignment_trace')
        bounds = {key: number(manifest['limits'][key], key, positive=True) for key in LIMITS}
        if bounds['min_pc104_receipt_fraction'] > 1:
            raise ValueError('min_pc104_receipt_fraction must be at most 1')
        if clock_error >= min(bounds[key] for key in (
                'max_ros_delivery_s', 'max_gate_gap_s', 'max_sensor_age_s',
                'max_candidate_age_s')):
            raise ValueError('clock alignment uncertainty cannot resolve declared timing limits')
        window = manifest['windows']
        start = number(window['healthy_start_s'], 'healthy_start_s')
        end = number(window['healthy_end_s'], 'healthy_end_s')
        record_end = number(window['record_end_s'], 'record_end_s')
        if not start < end <= record_end:
            raise ValueError('healthy window must fit inside recording')
        fault = None
        if manifest['case_kind'] == 'input_loss':
            fault = number(window['fault_start_s'], 'fault_start_s')
            if not end <= fault < record_end:
                raise ValueError('fault window must follow healthy window')
        streams = {role: read_csv(
            read_artifact(base, manifest['exports'][role], role), role,
            ECHO_COLUMNS if role == 'pc104_receipt' and receipt_mode == 'checksum_valid_echo'
            else None)
                   for role in ROLES}
        events = streams['mission_events']
        expected_end = 'ROUTE_COMPLETE' if manifest['case_kind'] == 'nominal' else 'SUSPENDED'
        if events[0]['event'] != 'MISSION_START' or events[-1]['event'] != expected_end:
            raise ValueError(f'mission_events must span MISSION_START to {expected_end}')
        mission_start = float(events[0]['time_s'])
        mission_end = float(events[-1]['time_s'])
        if not mission_start <= start < end <= mission_end <= record_end:
            raise ValueError('healthy window and recording must cover mission events')
        if fault is not None and not end <= fault <= mission_end:
            raise ValueError('input loss must occur before mission suspension')
        if not all(float(rows[0]['time_s']) <= start + clock_error
                   and float(rows[-1]['time_s']) >= record_end - clock_error
                   for role, rows in streams.items() if role != 'mission_events'):
            raise ValueError('every stream must cover the declared recording window')
        if not all(float(rows[0]['time_s']) <= mission_start + clock_error
                   for role, rows in streams.items() if role != 'mission_events'):
            raise ValueError('streams must begin by mission start')
    except (OSError, UnicodeError, KeyError, TypeError, ValueError, csv.Error,
            json.JSONDecodeError) as exc:
        blockers.append(str(exc))
        return report
    report['data_reviewable'] = True
    report['mission'] = {'start_s': mission_start, 'terminal_s': mission_end,
                         'terminal_event': expected_end, 'events': len(events)}
    gate, ros = streams['gate_ticks'], streams['ros_setpoint']
    if any(float(r['end_s']) < float(r['time_s']) for r in gate):
        flags.append('gate callback ends before it starts')
    healthy_gate = [r for r in gate if start <= float(r['time_s']) < end]
    healthy_ros = [r for r in ros if start <= float(r['time_s']) < end]
    duration = max((float(r['end_s']) - float(r['time_s']) for r in healthy_gate), default=None)
    gate_gap = gaps([float(r['time_s']) for r in healthy_gate], start, end)
    ros_gap = gaps([float(r['time_s']) for r in healthy_ros], start, end)
    positive_gate = [r for r in healthy_gate if float(r['decision_speed_mps']) > 0]
    positive_ros = [r for r in healthy_ros if float(r['target_speed_mps']) > 0]
    report['healthy'] = {'gate_ticks': len(healthy_gate), 'ros_setpoints': len(healthy_ros),
                         'positive_gate_ticks': len(positive_gate),
                         'positive_ros_setpoints': len(positive_ros),
                         'max_gate_duration_s': duration, 'max_gate_gap_s': gate_gap,
                         'max_ros_gap_s': ros_gap}
    for label, value, limit in (('gate_duration', duration, bounds['max_gate_duration_s']),
                                ('gate_gap', gate_gap, bounds['max_gate_gap_s']),
                                ('ros_gap', ros_gap, bounds['max_ros_gap_s'])):
        if value is None or value > limit + clock_error:
            flags.append(f'{label}: {value} exceeds {limit} s')
    if not healthy_gate or len(positive_gate) != len(healthy_gate):
        flags.append('healthy gate ticks include zero or no output')
    if not healthy_ros or len(positive_ros) != len(healthy_ros):
        flags.append('healthy ROS setpoints include zero or no output')
    positive_ros_all = [r for r in ros if start <= float(r['time_s']) <= record_end
                        and float(r['target_speed_mps']) > 0]
    observed_source_ages = [float(r['time_s']) - float(r['candidate_source_time_s'])
                            for r in positive_ros_all]
    report['maximum_observed_positive_candidate_source_age_s'] = (
        max(observed_source_ages) if observed_source_ages else None)
    for age in observed_source_ages:
        if not -2 * clock_error <= age <= bounds['max_candidate_age_s'] + 2 * clock_error:
            flags.append('positive ROS setpoint source stale at independent receipt')
            break
    for row in positive_gate:
        if float(row['budget_latched']) != 0:
            flags.append('positive gate decision while budget latched')
        for column in AGE_COLUMNS:
            raw = str(row[column]).strip()
            limit = (bounds['max_budget_age_s'] if column == 'budget_receipt_age_s'
                     else bounds['max_candidate_age_s'] if column.startswith('candidate_')
                     else bounds['max_sensor_age_s'])
            if not raw or not -clock_error <= float(raw) <= limit + clock_error:
                flags.append(f'positive gate decision with invalid {column}')
    # The gate is the sole declared publisher. Preserve order and demand one
    # independently observed ROS output per tick; no nearest-neighbour remap.
    gate_all = [r for r in gate if start <= float(r['time_s']) <= record_end]
    ros_all = [r for r in ros if start <= float(r['time_s']) <=
               record_end + bounds['max_ros_delivery_s'] + clock_error]
    if len(gate_all) != len(ros_all):
        flags.append('gate/ROS output count differs; exact causal pairing unavailable')
    else:
        delays = []
        for tick, output in zip(gate_all, ros_all):
            lag = float(output['time_s']) - float(tick['end_s'])
            delays.append(lag)
            if not -clock_error <= lag <= bounds['max_ros_delivery_s'] + clock_error:
                flags.append('gate to ROS observation exceeds delivery bound')
            if abs(float(tick['decision_speed_mps']) - float(output['target_speed_mps'])) > 1e-6:
                flags.append('gate/ROS ordered output value mismatch')
        report['maximum_observed_gate_to_ros_delay_s'] = max(delays) if delays else None
    pc104, paired = correlate_pc104_receipts(
        streams['udp_downlink'], streams['pc104_receipt'],
        receipt_mode=receipt_mode, max_lag_s=bounds['max_pc104_lag_s'],
        clock_error_s=clock_error, fault_time_s=fault)
    report['pc104'] = pc104
    receipt_fraction = pc104['matched_pc104_receipts'] / len(streams['udp_downlink'])
    report['pc104']['observed_receipt_fraction'] = receipt_fraction
    if (pc104['unmatched_pc104_receipts'] or pc104['ambiguous_pc104_receipts']
            or pc104['matched_command_rpm_mismatches']
            or receipt_fraction < bounds['min_pc104_receipt_fraction']):
        flags.append('UDP/PC104 observed receipts lack unique pairing or coverage')
    for name, rows, column, max_gap in (
            ('pid', streams['pid'], 'thrust_percent', bounds['max_pid_gap_s']),
            ('udp', streams['udp_downlink'], 'main_motor_rpm', bounds['max_udp_gap_s']),
            ('pc104', paired, 'main_motor_rpm', bounds['max_pc104_gap_s'])):
        selected = [r for r in rows if start <= float(r['time_s']) < end]
        gap = gaps([float(r['time_s']) for r in selected], start, end)
        report['healthy'][f'{name}_count'] = len(selected)
        report['healthy'][f'{name}_max_gap_s'] = gap
        report['healthy'][f'{name}_positive_count'] = sum(float(r[column]) > 0 for r in selected)
        if (not selected or gap is None or gap > max_gap + clock_error
                or any(float(r[column]) <= 0 for r in selected)):
            flags.append(f'healthy {name} output has zero/negative or excessive gap')
    if fault is not None:
        for name, rows, column, gap_limit in (
                ('gate', gate, 'decision_speed_mps', bounds['max_gate_gap_s']),
                ('ros', ros, 'target_speed_mps', bounds['max_ros_gap_s']),
                ('pid', streams['pid'], 'thrust_percent', bounds['max_pid_gap_s']),
                ('udp', streams['udp_downlink'], 'main_motor_rpm', bounds['max_udp_gap_s']),
                ('pc104', paired, 'main_motor_rpm', bounds['max_pc104_gap_s'])):
            delay_limit = (bounds['max_fault_zero_delay_s'] if name == 'pc104'
                           else bounds['max_local_zero_delay_s'])
            tail = zero_tail(rows, column, fault, record_end, gap_limit, delay_limit)
            report.setdefault('fault_zero_tails', {})[name] = tail
            if not tail['zero_tail_passed']:
                flags.append(f'{name}: no bounded continuous zero-command tail')
    report['timing_bounds_passed'] = not flags
    report['manifest_sha256'] = digest(manifest_path)
    report['interpretation'] = ('Bounds are checked on synchronized exports from one session. '
        'This cannot authenticate physical sources, infer actual thrust or issue field approval.')
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, default=TEMPLATE)
    parser.add_argument('--output-json', type=Path)
    args = parser.parse_args()
    result = analyze(args.manifest)
    if args.output_json:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n',
                                    encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result['timing_bounds_passed'] else 2)


if __name__ == '__main__':
    main()

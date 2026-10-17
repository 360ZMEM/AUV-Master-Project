#!/usr/bin/env python3
"""Audit four isolated synthetic ROS/PID/bridge/PVS process invocations.

This checks recorded outputs and source/install consistency. The invocations
are not a physical PC104 test, a statistical reliability estimate, or proof
that a bounded Hold can continue forever.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUNS = ROOT / 'AUV-Master-Mag/results/v2/inspection_repeatability_20260927'
DEFAULT_REPORT = (ROOT / 'AUV-Master-Mag/docs/v2/publication/fwhm_v2_experiment_results/data/'
                  'inspection_v2_process_restart_audit_20260927.json')
PLAN = (
    ('pilot_normal', 'wire', 104, 'normal'),
    ('normal_repeat', 'wire', 107, 'normal'),
    ('guard_loss', 'wire_guard_telemetry_loss', 105, 'guard_loss'),
    ('identity_switch', 'wire', 106, 'identity_switch'),
)
SOURCES = (
    'brain_linux/src/auv_cable_tracking_v2/auv_cable_tracking_v2/cable_tracking_v2_node.py',
    'brain_linux/src/auv_cable_tracking_v2/auv_cable_tracking_v2/inspection_controller_node.py',
    'brain_linux/src/auv_cable_tracking_v2/auv_cable_tracking_v2/inspection_bridge_node.py',
    'brain_linux/src/auv_cable_tracking_v2/config/cable_tracking_v2_flythrough_sonar_identity_corridor_budget_sim.yaml',
    'tools/smoke_v2_flythrough_ros_pvs.py',
)


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def flag(value: str) -> bool:
    normalized = str(value).strip().lower()
    if normalized not in ('true', 'false', '1', '0'):
        raise ValueError(f'invalid boolean {value!r}')
    return normalized in ('true', '1')


def audit_case(base: Path, directory: str, case: str, seed: int, expectation: str) -> dict:
    prefix = base / directory / f'{case}_seed_{seed}'
    summary_path = prefix.with_name(prefix.name + '_summary.json')
    csv_path = prefix.with_suffix('.csv')
    problems = []
    if not summary_path.is_file() or not csv_path.is_file():
        return {'case': case, 'seed': seed, 'expectation': expectation,
                'checks_passed': False, 'problems': ['summary or CSV missing']}
    try:
        summary = json.loads(summary_path.read_text(encoding='utf-8'))
        with csv_path.open(newline='', encoding='utf-8') as stream:
            rows = list(csv.DictReader(stream))
        if not rows:
            raise ValueError('empty CSV')
        times = [float(row['time_s']) for row in rows]
        rpm = [float(row['rpm']) for row in rows]
        if (not all(math.isfinite(item) for item in times + rpm)
                or any(right <= left for left, right in zip(times, times[1:]))):
            problems.append('nonfinite value or nonincreasing time')
        if len(rows) != summary['ticks'] or not math.isclose(times[-1], summary['duration_s'], abs_tol=1e-9):
            problems.append('CSV length or duration differs from summary')
        if summary['case'] != case or summary['seed'] != seed:
            problems.append('case or seed differs from plan')
        if not all(summary.get(name) is True for name in
                   ('native_pvs', 'ros_dds', 'protocol_encoded', 'bridge_and_guard_connected')):
            problems.append('required synthetic chain stage missing')
        if summary.get('hardware_connected') is not False:
            problems.append('physical provenance is not this synthetic harness')
        depth_rows = sum(flag(row['depth_valid']) for row in rows)
        if depth_rows or summary['depth_published']:
            problems.append('depth published without physical calibration')
        if expectation == 'normal':
            if not (summary['completed'] and summary['ever_track'] and summary['route_quality_valid']):
                problems.append('normal mission did not finish with route quality')
            if (summary['route_observed_lateral_mae_m'] is None
                    or summary['route_observed_lateral_mae_m'] > 1.0
                    or summary['route_observed_lateral_max_m'] > 2.0):
                problems.append('normal route exceeds frozen synthetic 1 m / 2 m example gates')
        elif expectation == 'guard_loss':
            ticks = summary['guard_telemetry_loss_ticks']
            if (summary['completed'] or ticks <= 0 or
                    summary['guard_telemetry_loss_zero_pid_ticks'] != ticks or
                    summary['guard_telemetry_loss_zero_udp_ticks'] != ticks or
                    summary['final_operational_status']['authority_reason'] != 'AMD_UPLINK_STALE'):
                problems.append('guard-loss revocation invariant failed')
            if any(value != 0 for value in rpm[-ticks:]):
                problems.append('nonzero UDP RPM in recorded guard-loss tail')
            if any(flag(row['autonomous_execution_authorized']) or
                   row['authority_reason'] != 'AMD_UPLINK_STALE'
                   for row in rows[-ticks:]):
                problems.append('bridge authority or reason inconsistent in guard-loss tail')
        elif expectation == 'identity_switch':
            hold = summary['first_hold_s']
            if (summary['completed'] or hold is None or
                    summary['first_hold_reason'] != 'flythrough_runtime_identity_diverged' or
                    summary['post_hold_coast_s'] < 60 or times[-1] - hold < 60):
                problems.append('identity-switch Hold or observation horizon missing')
            if hold is not None and any(
                    float(row['rpm']) != 0 or row['mode'] != 'hold' or
                    flag(row['autonomous_execution_authorized'])
                    for row in rows if float(row['time_s']) >= hold):
                problems.append('nonzero UDP RPM or autonomous authority after identity Hold')
        return {
            'case': case, 'seed': seed, 'expectation': expectation,
            'checks_passed': not problems, 'problems': problems,
            'ticks': len(rows), 'simulated_duration_s': times[-1],
            'depth_publication_rows': depth_rows,
            'completed': summary['completed'],
            'first_hold_reason': summary['first_hold_reason'],
            'first_hold_s': summary['first_hold_s'],
            'route_observed_lateral_mae_m': summary['route_observed_lateral_mae_m'],
            'route_observed_lateral_max_m': summary['route_observed_lateral_max_m'],
            'guard_loss_ticks': summary['guard_telemetry_loss_ticks'],
            'identity_hold_displacement_m': summary['hold_to_final_displacement_m'],
            'summary_sha256': sha(summary_path), 'csv_sha256': sha(csv_path),
        }
    except (OSError, UnicodeError, json.JSONDecodeError, csv.Error, KeyError,
            TypeError, ValueError, OverflowError) as exc:
        return {'case': case, 'seed': seed, 'expectation': expectation,
                'checks_passed': False, 'problems': [f'unreadable or invalid trace: {exc}']}


def audit(base: Path) -> dict:
    cases = [audit_case(base, *entry) for entry in PLAN]
    sources = {}
    installed_equal = {}
    for relative in SOURCES:
        path = ROOT / relative
        sources[relative] = sha(path) if path.is_file() else None
        if 'auv_cable_tracking_v2/auv_cable_tracking_v2/' in relative:
            installed = (ROOT / 'brain_linux/install/auv_cable_tracking_v2/'
                         'lib/python3.10/site-packages/auv_cable_tracking_v2' / path.name)
            installed_equal[path.name] = installed.is_file() and sha(installed) == sources[relative]
    all_passed = (all(item['checks_passed'] for item in cases)
                  and all(value is not None for value in sources.values())
                  and all(installed_equal.values()))
    return {
        'role': 'synthetic_saved_trace_contract_audit',
        'checks_passed': all_passed,
        'field_release_authorized': False,
        'cases': cases,
        'source_sha256': sources,
        'installed_source_equal': installed_equal,
        'audit_script_sha256': sha(Path(__file__)),
        'interpretation': ('Four saved synthetic traces from separate invocations; '
                           'this file audit does not independently authenticate process or ROS-domain isolation. '
                           'Not one uninterrupted service soak. Native PVS, scripted sonar '
                           'and AMD uplink, local UDP; no physical PC104 or real vehicle. '
                           'The 1 m / 2 m route gates are frozen synthetic example gates.'),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runs-dir', type=Path, default=DEFAULT_RUNS)
    parser.add_argument('--output-json', type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()
    result = audit(args.runs_dir)
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n',
                                encoding='utf-8')
    print(json.dumps({'checks_passed': result['checks_passed'],
                      'field_release_authorized': False}, ensure_ascii=False))
    raise SystemExit(0 if result['checks_passed'] else 2)


if __name__ == '__main__':
    main()

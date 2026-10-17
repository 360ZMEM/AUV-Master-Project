#!/usr/bin/env python3
"""Audit the disposition after transient navigation loss in synthetic v2.

This audits saved ROS/PID/guard/local-UDP/native-PVS outputs. It does not
measure physical stopping, hardware availability, or continuous endurance.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUN = (ROOT / 'AUV-Master-Mag/results/v2/inspection_recovery_20260927/'
               'navigation_dropout')
DEFAULT_OUTPUT = (ROOT / 'AUV-Master-Mag/docs/v2/publication/'
                  'fwhm_v2_experiment_results/data/'
                  'inspection_v2_transient_nav_recovery_audit_20260927.json')
PREFIX = 'wire_navigation_dropout_seed_108'
SOURCES = (
    'tools/smoke_v2_flythrough_ros_pvs.py',
    'brain_linux/src/auv_cable_tracking_v2/auv_cable_tracking_v2/cable_tracking_v2_node.py',
    'brain_linux/src/auv_cable_tracking_v2/auv_cable_tracking_v2/inspection_controller_node.py',
    'brain_linux/src/auv_cable_tracking_v2/auv_cable_tracking_v2/inspection_bridge_node.py',
    'brain_linux/src/auv_cable_tracking_v2/config/cable_tracking_v2_flythrough_sonar_identity_corridor_budget_sim.yaml',
)


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def flag(value: str) -> bool:
    value = str(value).strip().lower()
    if value not in {'true', 'false', '1', '0'}:
        raise ValueError(f'invalid boolean {value!r}')
    return value in {'true', '1'}


def audit(run_dir: Path) -> dict:
    summary_path = run_dir / f'{PREFIX}_summary.json'
    csv_path = run_dir / f'{PREFIX}.csv'
    summary = json.loads(summary_path.read_text(encoding='utf-8'))
    with csv_path.open(newline='', encoding='utf-8') as stream:
        rows = list(csv.DictReader(stream))
    problems = []
    if not rows:
        raise ValueError('empty CSV')
    times = [float(row['time_s']) for row in rows]
    if (not all(math.isfinite(t) for t in times)
            or any(not math.isclose(b - a, .25, abs_tol=1e-7)
                   for a, b in zip(times, times[1:]))):
        problems.append('time grid is nonfinite or not 0.25 s')
    if (summary.get('case') != 'wire_navigation_dropout' or summary.get('seed') != 108
            or len(rows) != summary.get('ticks')
            or not math.isclose(times[-1], summary.get('duration_s', math.nan), abs_tol=1e-7)):
        problems.append('case, seed, row count or duration mismatch')
    if not all(summary.get(key) is True for key in
               ('native_pvs', 'ros_dds', 'protocol_encoded', 'bridge_and_guard_connected')):
        problems.append('synthetic chain flag missing')
    if summary.get('hardware_connected') is not False or summary.get('sonar_identity_mode') != 'target':
        problems.append('unexpected hardware or identity fixture provenance')
    first_track = summary.get('first_track_s')
    if first_track is None:
        problems.append('no first Track time')
        fault_rows = []
        after_rows = []
        fault_start = fault_end = None
    else:
        fault_start = float(first_track) + 8.
        fault_end = float(first_track) + 23.
        fault_rows = [row for row in rows if fault_start <= float(row['time_s']) < fault_end]
        after_rows = [row for row in rows if float(row['time_s']) >= fault_end]
    if len(fault_rows) != 60 or summary.get('navigation_fault_ticks') != 60:
        problems.append('15 s navigation fault coverage missing')
    if any(any(abs(float(row[key])) > 1e-9 for key in
               ('target_speed_mps', 'thrust_percent', 'rpm')) for row in fault_rows):
        problems.append('nonzero guidance, PID or UDP during navigation fault')
    if any(flag(row['autonomous_execution_authorized']) for row in fault_rows):
        problems.append('bridge authority remained enabled during navigation fault')
    if not after_rows or any(any(abs(float(row[key])) > 1e-9 for key in
                                 ('target_speed_mps', 'thrust_percent', 'rpm'))
                             for row in after_rows):
        problems.append('guidance, PID or UDP propulsion resumed despite latched recovery requirement')
    if not after_rows or not any(row['mode'] == 'track' for row in after_rows):
        problems.append('perception did not resume Track after navigation recovered')
    if any(flag(row['autonomous_execution_authorized']) or
           row['authority_reason'] != 'inspection_recovery_required' or
           row['hold_budget_state'] != 'RECOVERY_REQUIRED'
           for row in after_rows):
        problems.append('autonomy was reauthorized without external recovery review')
    if (summary.get('completed') or any(flag(row['endpoint_complete']) for row in after_rows)
            or summary.get('route_quality_valid') is not None):
        problems.append('terminal task or route quality reported despite stopped execution')
    if (summary.get('first_hold_reason') != 'navigation_invalid'
            or summary.get('first_recovery_reason') != 'hold_geometry_invalid'
            or summary.get('bridge_budget_latched') is not True
            or summary.get('bridge_recovery_stop_observed') is not True
            or summary.get('final_inspection_status') != 'RECOVERY_REQUIRED'
            or summary.get('final_operational_status', {}).get('authority_reason')
            != 'inspection_recovery_required'):
        problems.append('expected latched Hold disposition is absent')
    if summary.get('depth_published') or any(flag(row['depth_valid']) for row in rows):
        problems.append('uncalibrated depth was published')
    sources = {path: sha(ROOT / path) for path in SOURCES}
    installed_equal = {}
    for relative in SOURCES:
        if '/auv_cable_tracking_v2/auv_cable_tracking_v2/' in relative:
            target = (ROOT / 'brain_linux/install/auv_cable_tracking_v2/'
                      'lib/python3.10/site-packages/auv_cable_tracking_v2/'
                      / Path(relative).name)
            installed_equal[Path(relative).name] = target.is_file() and sha(target) == sources[relative]
    if not all(installed_equal.values()):
        problems.append('ROS installed code differs from source')
    first_resume = next((float(row['time_s']) for row in after_rows
                         if float(row['rpm']) > 0), None)
    return {
        'role': 'synthetic_saved_trace_transient_recovery_audit',
        'checks_passed': not problems,
        'field_release_authorized': False,
        'problems': problems,
        'case': summary.get('case'), 'seed': summary.get('seed'),
        'ticks': len(rows), 'simulated_duration_s': times[-1],
        'fault_window_s': [fault_start, fault_end],
        'fault_rows': len(fault_rows),
        'fault_zero_guidance_pid_udp_rows': sum(
            all(abs(float(row[key])) <= 1e-9 for key in
                ('target_speed_mps', 'thrust_percent', 'rpm')) for row in fault_rows),
        'autonomous_resume_observed': first_resume is not None,
        'first_positive_udp_after_fault_s': first_resume,
        'after_fault_track_rows': sum(row['mode'] == 'track' for row in after_rows),
        'after_fault_authorized_rows': sum(flag(row['autonomous_execution_authorized']) for row in after_rows),
        'after_fault_zero_udp_rows': sum(float(row['rpm']) == 0 for row in after_rows),
        'after_fault_zero_guidance_pid_udp_rows': sum(
            all(abs(float(row[key])) <= 1e-9 for key in
                ('target_speed_mps', 'thrust_percent', 'rpm')) for row in after_rows),
        'first_hold_reason': summary.get('first_hold_reason'),
        'first_recovery_reason': summary.get('first_recovery_reason'),
        'completed': summary.get('completed'),
        'route_observed_lateral_mae_m': summary.get('route_observed_lateral_mae_m'),
        'route_observed_lateral_max_m': summary.get('route_observed_lateral_max_m'),
        'summary_sha256': sha(summary_path), 'csv_sha256': sha(csv_path),
        'source_sha256': sources, 'installed_source_equal': installed_equal,
        'audit_script_sha256': sha(Path(__file__)),
        'interpretation': ('One independent, scripted 15 s NaN navigation dropout in native PVS '
                           'with ROS/PID/guard/local UDP and synthetic target-sonar cue. '
                           'Perception returns to Track, but invalid Hold geometry latches '
                           'RECOVERY_REQUIRED and execution remains denied. This is a safe '
                           'disposition, not autonomous task recovery, physical vessel stopping, '
                           'statistical reliability, or uninterrupted endurance.'),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', type=Path, default=DEFAULT_RUN)
    parser.add_argument('--output-json', type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    result = audit(args.run_dir)
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'checks_passed': result['checks_passed'],
                      'field_release_authorized': False, 'problems': result['problems']}))
    raise SystemExit(0 if result['checks_passed'] else 2)


if __name__ == '__main__':
    main()

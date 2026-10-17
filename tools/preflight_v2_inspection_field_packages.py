#!/usr/bin/env python3
"""Check traceability of physical target and execution acceptance bundles.

Passing this preflight means that named records can be opened and reviewed. It
does not establish physical provenance, trial independence, algorithm accuracy,
safe stopping distance, or authorization for an AUV mission.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / 'AUV-Master-Mag/docs/v2/inspection_field_packages_template.json'
DEFAULT_REPORT = (ROOT / 'AUV-Master-Mag/docs/v2/publication/fwhm_v2_experiment_results/data/'
                  'inspection_v2_field_package_preflight_20260927.json')
TARGET_ROLES = {
    'magnetic': ({'time_s', 'x_m', 'y_m', 'envelope_nt'}, 20),
    'navigation': ({'time_s', 'x_m', 'y_m', 'position_sigma_m'}, 20),
    'identity': ({'time_s', 'center_y_m', 'valid'}, 1),
    'independent_truth': ({'time_s', 'true_target_y_m', 'truth_method'}, 1),
    'target_decision': ({'time_s', 'lateral_y_m', 'lateral_valid',
                         'target_confirmed', 'task_complete', 'autonomous_allowed',
                         'depth_published'}, 2),
}
EXECUTION_ROLES = {
    'ros_setpoint': ({'time_s', 'target_speed_mps'}, 2),
    'udp_downlink': ({'time_s', 'frame_number', 'main_motor_rpm'}, 2),
    'pc104_receipt': ({'time_s', 'frame_number', 'main_motor_rpm'}, 2),
    'vehicle_motion': ({'time_s', 'x_m', 'y_m', 'ground_speed_mps'}, 2),
    'boundary': ({'time_s', 'clearance_m'}, 2),
    'fault_events': ({'time_s', 'event'}, 1),
}
ECHO_RECEIPT_COLUMNS = {'time_s', 'frame_number', 'pc104_recv_uptime_ms'}
BOOLEAN_COLUMNS = {'valid', 'lateral_valid', 'target_confirmed', 'task_complete',
                   'autonomous_allowed', 'depth_published'}


def boolean(value: str) -> bool:
    normalized = str(value).strip().lower()
    if normalized not in ('0', '1', 'false', 'true'):
        raise ValueError(f'invalid boolean {value!r}')
    return normalized in ('1', 'true')


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def artifact(base: Path, value: Any, label: str, blockers: list[str]) -> Path | None:
    if not isinstance(value, dict):
        blockers.append(f'{label}: path and sha256 record required')
        return None
    name, digest = value.get('path'), value.get('sha256')
    if not isinstance(name, str) or not name.strip():
        blockers.append(f'{label}: path missing')
        return None
    if (not isinstance(digest, str) or len(digest) != 64
            or any(char not in '0123456789abcdef' for char in digest.lower())):
        blockers.append(f'{label}: SHA-256 missing or invalid')
        return None
    path = Path(name).expanduser()
    if not path.is_absolute():
        path = base / path
    path = path.resolve()
    if not path.is_file() or path.stat().st_size == 0:
        blockers.append(f'{label}: file missing or empty')
        return None
    if sha(path) != digest.lower():
        blockers.append(f'{label}: SHA-256 mismatch')
        return None
    return path


def exported_csv(path: Path | None, label: str, columns: set[str], minimum: int,
                 blockers: list[str]) -> tuple[int, float | None, float | None]:
    if path is None:
        return 0, None, None
    try:
        with path.open(newline='', encoding='utf-8') as stream:
            reader = csv.DictReader(stream)
            missing = columns - set(reader.fieldnames or [])
            if missing:
                raise ValueError('missing columns ' + ', '.join(sorted(missing)))
            times = []
            uptimes = []
            for row in reader:
                t = float(row['time_s'])
                if not math.isfinite(t):
                    raise ValueError('nonfinite time_s')
                times.append(t)
                for name in columns & BOOLEAN_COLUMNS:
                    boolean(row[name])
                for name in columns - {'time_s', 'truth_method', 'event',
                                       'lateral_y_m'} - BOOLEAN_COLUMNS:
                    value = float(row[name])
                    if not math.isfinite(value):
                        raise ValueError(f'nonfinite {name}')
                    if name == 'frame_number' and (not value.is_integer() or not 0 <= value <= 255):
                        raise ValueError('frame_number must be an integer from 0 to 255')
                    if name == 'pc104_recv_uptime_ms':
                        if value < 0 or not value.is_integer():
                            raise ValueError('pc104_recv_uptime_ms must be a nonnegative integer')
                        uptimes.append(int(value))
                if 'lateral_y_m' in columns:
                    lateral = str(row['lateral_y_m']).strip()
                    if boolean(row['lateral_valid']) and not lateral:
                        raise ValueError('valid lateral decision needs lateral_y_m')
                    if lateral and not math.isfinite(float(lateral)):
                        raise ValueError('nonfinite lateral_y_m')
                for name in columns & {'event', 'truth_method'}:
                    if not str(row[name]).strip():
                        raise ValueError(f'empty {name}')
            if len(times) < minimum:
                raise ValueError(f'needs at least {minimum} rows')
            if any(right < left for left, right in zip(times, times[1:])):
                raise ValueError('time_s goes backward')
            if any(right <= left for left, right in zip(uptimes, uptimes[1:])):
                raise ValueError('echo receive uptime must increase; deduplicate repeated uplink echoes')
            return len(times), times[0], times[-1]
    except (OSError, UnicodeError, csv.Error, TypeError, ValueError, OverflowError) as exc:
        blockers.append(f'{label}: invalid CSV: {exc}')
        return 0, None, None


def package(base: Path, value: Any, label: str, roles: dict, required_kinds: set[str],
            clock_error_s: float | None, blockers: list[str]) -> dict:
    if not isinstance(value, dict):
        blockers.append(f'{label}: package object missing')
        return {'cases': 0, 'kinds': [], 'csv_rows': {}}
    cases = value.get('cases')
    if not isinstance(cases, list):
        blockers.append(f'{label}: cases must be a list')
        cases = []
    seen_ids, kinds, seen_raw = set(), set(), set()
    row_counts = {}
    for index, case in enumerate(cases):
        prefix = f'{label}.cases[{index}]'
        if not isinstance(case, dict):
            blockers.append(f'{prefix}: case object required')
            continue
        case_id, kind = str(case.get('case_id', '')).strip(), str(case.get('kind', '')).strip()
        if not case_id or case_id in seen_ids:
            blockers.append(f'{prefix}: nonempty unique case_id required')
        seen_ids.add(case_id)
        if kind not in required_kinds:
            blockers.append(f'{prefix}: kind must be one of {sorted(required_kinds)}')
        kinds.add(kind)
        if not str(case.get('session_id', '')).strip():
            blockers.append(f'{prefix}: physical session_id required')
        raw = artifact(base, case.get('raw_archive'), f'{prefix}.raw_archive', blockers)
        if raw is not None:
            if raw in seen_raw:
                blockers.append(f'{prefix}: raw archive reused by another case')
            seen_raw.add(raw)
        exports = case.get('exports')
        if not isinstance(exports, dict):
            blockers.append(f'{prefix}: exports object required')
            exports = {}
        paths, bounds = {}, {}
        for role, (columns, minimum) in roles.items():
            path = artifact(base, exports.get(role), f'{prefix}.{role}', blockers)
            paths[role] = path
            count, first, last = exported_csv(
                path, f'{prefix}.{role}', columns, minimum, blockers)
            row_counts[f'{case_id}.{role}'] = count
            if first is not None:
                bounds[role] = (first, last)
        if len(bounds) == len(roles) and clock_error_s is not None:
            latest_start = max(first for first, _ in bounds.values())
            earliest_end = min(last for _, last in bounds.values())
            if latest_start > earliest_end + 2 * clock_error_s:
                blockers.append(f'{prefix}: required streams have no shared time interval')
        if len({path for path in paths.values() if path is not None}) != len(
                [path for path in paths.values() if path is not None]):
            blockers.append(f'{prefix}: one export file reused for multiple roles')
        if label == 'target_package':
            truth_method = str(case.get('truth_method', '')).strip().lower()
            if (not truth_method or any(token in truth_method for token in
                    ('magnetic', 'fwhm', 'simulation', 'pvs'))):
                blockers.append(f'{prefix}: independent physical truth_method required')
    for missing in sorted(required_kinds - kinds):
        blockers.append(f'{label}: missing {missing} case')
    return {'cases': len(cases), 'kinds': sorted(kinds), 'csv_rows': row_counts}


def audit(manifest_path: Path) -> dict:
    blockers: list[str] = []
    try:
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return {'preflight_passed': False, 'field_release_authorized': False,
                'blockers': [f'manifest unreadable: {exc}']}
    if not isinstance(manifest, dict) or manifest.get('schema_version') != 1:
        return {'preflight_passed': False, 'field_release_authorized': False,
                'blockers': ['schema_version must be 1']}
    base = manifest_path.resolve().parent
    if manifest.get('data_domain') != 'physical':
        blockers.append('data_domain must be physical')
    mission_id, target_id = (str(manifest.get(key, '')).strip() for key in ('mission_id', 'target_id'))
    if not mission_id or not target_id:
        blockers.append('mission_id and target_id required')
    if not str(manifest.get('site_id', '')).strip():
        blockers.append('site_id required')
    if not str(manifest.get('coordinate_frame', '')).strip():
        blockers.append('coordinate_frame required for all x/y and lateral truth')
    artifact(base, manifest.get('software_snapshot'), 'software_snapshot', blockers)
    identity_basis = manifest.get('identity_basis')
    if identity_basis not in ('reviewed_static_prior', 'physical_sonar'):
        blockers.append('identity_basis must be reviewed_static_prior or physical_sonar')
    identity = artifact(base, manifest.get('identity_source'), 'identity_source', blockers)
    if identity is not None and identity_basis == 'reviewed_static_prior':
        try:
            reviewed = json.loads(identity.read_text(encoding='utf-8'))
            if (reviewed.get('mission_id') != mission_id or reviewed.get('target_id') != target_id
                    or reviewed.get('reviewed_for_mission') is not True):
                blockers.append('reviewed static prior does not match mission and target')
        except (OSError, UnicodeError, json.JSONDecodeError, AttributeError) as exc:
            blockers.append(f'identity_source static prior invalid: {exc}')
    sync = manifest.get('clock_alignment')
    clock_error_s = None
    if not isinstance(sync, dict) or not str(sync.get('method', '')).strip():
        blockers.append('clock_alignment.method required')
    else:
        try:
            error_ms = float(sync.get('measured_max_error_ms'))
            if not math.isfinite(error_ms) or error_ms < 0:
                raise ValueError
            clock_error_s = error_ms / 1000
        except (TypeError, ValueError, OverflowError):
            blockers.append('clock_alignment.measured_max_error_ms must be finite and nonnegative')
    artifact(base, (sync or {}).get('raw_alignment_trace') if isinstance(sync, dict) else None,
             'clock_alignment.raw_alignment_trace', blockers)
    receipt_mode = manifest.get('receipt_mode')
    if receipt_mode not in ('board_command_log', 'checksum_valid_echo'):
        blockers.append('receipt_mode must be board_command_log or checksum_valid_echo')
    try:
        max_receipt_lag_s = float(manifest.get('max_receipt_lag_s'))
        if not math.isfinite(max_receipt_lag_s) or max_receipt_lag_s <= 0:
            raise ValueError
    except (TypeError, ValueError, OverflowError):
        blockers.append('max_receipt_lag_s must be finite and positive')
    target_blockers, execution_blockers = [], []
    target = package(base, manifest.get('target_package'), 'target_package', TARGET_ROLES,
                     {'target', 'neighbor', 'cue_loss'}, clock_error_s, target_blockers)
    execution_roles = dict(EXECUTION_ROLES)
    if receipt_mode == 'checksum_valid_echo':
        execution_roles['pc104_receipt'] = (ECHO_RECEIPT_COLUMNS, 2)
    execution = package(base, manifest.get('execution_package'), 'execution_package',
                        execution_roles, {'nominal', 'uplink_loss'}, clock_error_s,
                        execution_blockers)
    global_blockers = list(blockers)
    blockers.extend(target_blockers + execution_blockers)
    return {
        'role': 'physical_inspection_bundle_traceability_preflight',
        'preflight_passed': not blockers,
        'target_package_reviewable': not global_blockers and not target_blockers and target['cases'] >= 3,
        'execution_package_reviewable': not global_blockers and not execution_blockers and execution['cases'] >= 2,
        'field_release_authorized': False,
        'manifest_sha256': sha(manifest_path),
        'audit_script_sha256': sha(Path(__file__)),
        'identity_basis': identity_basis,
        'receipt_mode': receipt_mode,
        'target_package': target,
        'execution_package': execution,
        'blockers': blockers,
        'interpretation': 'Preflight checks file hashes, named streams and minimum case coverage only; human review and measured performance gates remain mandatory.',
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, default=TEMPLATE)
    parser.add_argument('--output-json', type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()
    report = audit(args.manifest)
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({name: report[name] for name in (
        'preflight_passed', 'target_package_reviewable',
        'execution_package_reviewable', 'field_release_authorized')}, ensure_ascii=False))
    raise SystemExit(0 if report['preflight_passed'] else 2)


if __name__ == '__main__':
    main()

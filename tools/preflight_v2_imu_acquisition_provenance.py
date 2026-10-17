#!/usr/bin/env python3
"""Structural preflight for physical IMU sample-time evidence; never grants field use."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / 'AUV-Master-Mag/docs/v2/inspection_imu_acquisition_template.json'
COVARIANCE_COLUMNS = tuple(f'cov_{row}{col}' for row in range(3) for col in range(3))
REQUIRED_COLUMNS = frozenset({
    'imu_sample_id', 'imu_acquisition_time_s', 'pc104_packet_time_s',
    'ros_receive_time_s', 'orientation_x', 'orientation_y',
    'orientation_z', 'orientation_w', *COVARIANCE_COLUMNS,
})
ARTIFACTS = (
    'sensor_driver_source', 'raw_imu_log', 'raw_pc104_uplink',
    'raw_ros_imu_bag', 'raw_clock_alignment_trace',
    'orientation_calibration_report', 'sample_trace',
)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def artifact(base: Path, entry: object, name: str, blockers: list[str]) -> Path | None:
    if not isinstance(entry, dict) or not str(entry.get('path', '')).strip():
        blockers.append(f'{name}: path and sha256 required')
        return None
    value = Path(str(entry['path']))
    path = value if value.is_absolute() else base / value
    if not path.is_file() or path.stat().st_size == 0:
        blockers.append(f'{name}: nonempty file missing')
        return None
    expected = entry.get('sha256')
    if not isinstance(expected, str) or len(expected) != 64 or sha(path) != expected.lower():
        blockers.append(f'{name}: sha256 mismatch')
        return None
    return path


def positive_number(value: object, name: str, blockers: list[str]) -> float | None:
    try:
        result = float(value)
        if not math.isfinite(result) or result <= 0:
            raise ValueError
    except (TypeError, ValueError, OverflowError):
        blockers.append(f'{name}: finite positive value required')
        return None
    return result


def audit(manifest_path: Path) -> dict:
    manifest_path = Path(manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    blockers: list[str] = []
    if manifest.get('schema_version') != 1:
        blockers.append('schema_version must be 1')
    for key in ('mission_id', 'target_id', 'sensor_model', 'firmware_version',
                'acquisition_clock_method', 'orientation_calibration_method'):
        if not isinstance(manifest.get(key), str) or not manifest[key].strip():
            blockers.append(f'{key}: nonempty value required')
    if manifest.get('acquisition_time_basis') != 'sensor_native_timestamp':
        blockers.append('acquisition_time_basis must be sensor_native_timestamp; PC104 packet or ROS receipt time is insufficient')
    clock_error = positive_number(manifest.get('measured_max_clock_error_s'),
                                  'measured_max_clock_error_s', blockers)
    candidate_age = positive_number(manifest.get('candidate_max_sample_age_s'),
                                    'candidate_max_sample_age_s', blockers)
    base = manifest_path.parent
    paths = {name: artifact(base, manifest.get(name), name, blockers) for name in ARTIFACTS}
    resolved = [path.resolve() for path in paths.values() if path is not None]
    if len(resolved) != len(set(resolved)):
        blockers.append('artifacts: distinct evidence roles must use distinct files')
    summary = {
        'sample_count': 0,
        'maximum_acquisition_to_packet_s': None,
        'maximum_acquisition_to_ros_s': None,
        'maximum_heading_std_deg': None,
    }
    trace = paths['sample_trace']
    if trace is not None:
        try:
            with trace.open(newline='', encoding='utf-8') as stream:
                reader = csv.DictReader(stream)
                if reader.fieldnames is None or not REQUIRED_COLUMNS.issubset(reader.fieldnames):
                    missing = sorted(REQUIRED_COLUMNS - set(reader.fieldnames or []))
                    blockers.append('sample_trace: missing columns ' + ','.join(missing))
                    rows = []
                else:
                    rows = list(reader)
        except (OSError, UnicodeError, csv.Error) as exc:
            blockers.append(f'sample_trace: unreadable CSV: {exc}')
            rows = []
        summary['sample_count'] = len(rows)
        if len(rows) < 5:
            blockers.append('sample_trace: at least five samples required')
        previous = None
        ids: set[str] = set()
        acquisition_to_packet: list[float] = []
        acquisition_to_ros: list[float] = []
        heading_std_deg: list[float] = []
        for index, row in enumerate(rows, 1):
            try:
                sample_id = row['imu_sample_id'].strip()
                if not sample_id or sample_id in ids:
                    raise ValueError('missing/repeated sensor-native sample ID')
                ids.add(sample_id)
                times = tuple(float(row[key]) for key in (
                    'imu_acquisition_time_s', 'pc104_packet_time_s', 'ros_receive_time_s'))
                if not all(math.isfinite(value) for value in times):
                    raise ValueError('nonfinite time')
                if previous is not None and any(new <= old for new, old in zip(times, previous)):
                    raise ValueError('sample, packet and ROS times must each advance')
                previous = times
                tolerance = clock_error or 0.
                if times[0] > times[1] + tolerance or times[1] > times[2] + tolerance:
                    raise ValueError('acquisition/packet/receive order invalid')
                age = times[2] - times[0]
                if candidate_age is not None and age - tolerance > candidate_age:
                    raise ValueError('sensor-native sample age exceeds candidate bound')
                quaternion = np.array([float(row[f'orientation_{axis}'])
                                       for axis in 'xyzw'], dtype=float)
                if not np.all(np.isfinite(quaternion)) or abs(np.linalg.norm(quaternion) - 1.) > .02:
                    raise ValueError('orientation quaternion invalid')
                covariance = np.array([float(row[key]) for key in COVARIANCE_COLUMNS],
                                      dtype=float).reshape(3, 3)
                if not np.all(np.isfinite(covariance)):
                    raise ValueError('nonfinite orientation covariance')
                if not np.allclose(covariance, covariance.T, rtol=0., atol=1e-8):
                    raise ValueError('orientation covariance not symmetric')
                eigenvalues = np.linalg.eigvalsh(covariance)
                if eigenvalues[0] < -1e-10 or eigenvalues[-1] <= 0:
                    raise ValueError('orientation covariance not positive semidefinite and nonzero')
                acquisition_to_packet.append(times[1] - times[0])
                acquisition_to_ros.append(age)
                heading_std_deg.append(math.degrees(math.sqrt(max(0., eigenvalues[-1]))))
            except (TypeError, ValueError, KeyError, OverflowError) as exc:
                blockers.append(f'sample_trace row {index}: {exc}')
        if acquisition_to_ros:
            summary.update(
                maximum_acquisition_to_packet_s=max(acquisition_to_packet),
                maximum_acquisition_to_ros_s=max(acquisition_to_ros),
                maximum_heading_std_deg=max(heading_std_deg),
            )
    return {
        'role': 'physical_imu_acquisition_provenance_structural_preflight',
        'navigation_evidence_reviewable': not blockers,
        'field_release_authorized': False,
        'manifest_sha256': sha(manifest_path),
        'audit_script_sha256': sha(Path(__file__)),
        'summary': summary,
        'blockers': blockers,
        'interpretation': 'Hashes, declared native provenance, monotonic samples, mapped time, and covariance structure only; physical source and calibration still need independent review.',
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, default=TEMPLATE)
    parser.add_argument('--output-json', type=Path)
    args = parser.parse_args()
    report = audit(args.manifest)
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + '\n'
    if args.output_json:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(rendered, encoding='utf-8')
    print(rendered, end='')
    if not report['navigation_evidence_reviewable']:
        raise SystemExit(2)


if __name__ == '__main__':
    main()

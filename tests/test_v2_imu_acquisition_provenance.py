"""Generated records validate the preflight contract, not physical readiness."""

import csv
import hashlib
import json
from pathlib import Path

from tools import preflight_v2_imu_acquisition_provenance as preflight


def _record(path: Path, content: bytes) -> dict:
    path.write_bytes(content)
    return {'path': str(path), 'sha256': hashlib.sha256(content).hexdigest()}


def _fixture(tmp_path: Path) -> tuple[Path, dict, Path]:
    manifest = json.loads(preflight.TEMPLATE.read_text(encoding='utf-8'))
    manifest.update(mission_id='fixture_mission', target_id='fixture_target',
                    sensor_model='fixture_imu', firmware_version='fixture_1',
                    acquisition_time_basis='sensor_native_timestamp',
                    acquisition_clock_method='fixture_clock_mapping',
                    orientation_calibration_method='fixture_external_reference',
                    measured_max_clock_error_s=.001,
                    candidate_max_sample_age_s=.75)
    for name in preflight.ARTIFACTS:
        if name != 'sample_trace':
            manifest[name] = _record(tmp_path / (name + '.txt'), b'synthetic fixture')
    trace = tmp_path / 'trace.csv'
    with trace.open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=sorted(preflight.REQUIRED_COLUMNS))
        writer.writeheader()
        for index in range(5):
            row = {name: '0' for name in preflight.REQUIRED_COLUMNS}
            row.update(imu_sample_id=str(index + 1),
                       imu_acquisition_time_s=str(index),
                       pc104_packet_time_s=str(index + .05),
                       ros_receive_time_s=str(index + .10),
                       orientation_w='1', cov_00='.0001', cov_11='.0001', cov_22='.0001')
            writer.writerow(row)
    manifest['sample_trace'] = {'path': str(trace), 'sha256': preflight.sha(trace)}
    path = tmp_path / 'manifest.json'
    path.write_text(json.dumps(manifest), encoding='utf-8')
    return path, manifest, trace


def _mutate_trace(trace: Path, manifest: dict, path: Path, mutate) -> dict:
    with trace.open(newline='', encoding='utf-8') as stream:
        reader = csv.DictReader(stream)
        fields, rows = reader.fieldnames, list(reader)
    mutate(rows)
    with trace.open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    manifest['sample_trace']['sha256'] = preflight.sha(trace)
    path.write_text(json.dumps(manifest), encoding='utf-8')
    return preflight.audit(path)


def test_blank_template_fails_closed():
    report = preflight.audit(preflight.TEMPLATE)
    assert not report['navigation_evidence_reviewable']
    assert not report['field_release_authorized']


def test_native_sample_trace_is_reviewable_but_never_field_release(tmp_path):
    path, _, _ = _fixture(tmp_path)
    report = preflight.audit(path)
    assert report['navigation_evidence_reviewable'], report['blockers']
    assert not report['field_release_authorized']
    assert report['summary']['sample_count'] == 5
    assert abs(report['summary']['maximum_acquisition_to_ros_s'] - .1) < 1e-9


def test_packet_time_cannot_replace_native_sample_and_frozen_sample_rejected(tmp_path):
    path, manifest, trace = _fixture(tmp_path)
    manifest['acquisition_time_basis'] = 'pc104_packet_time'
    path.write_text(json.dumps(manifest), encoding='utf-8')
    assert any('sensor_native_timestamp' in item for item in preflight.audit(path)['blockers'])
    manifest['acquisition_time_basis'] = 'sensor_native_timestamp'
    frozen = _mutate_trace(trace, manifest, path,
                           lambda rows: rows[3].update(imu_acquisition_time_s=rows[2]['imu_acquisition_time_s']))
    assert not frozen['navigation_evidence_reviewable']
    assert any('row 4' in item and 'advance' in item for item in frozen['blockers'])


def test_stale_or_uncalibrated_covariance_rejected(tmp_path):
    path, manifest, trace = _fixture(tmp_path)
    stale = _mutate_trace(trace, manifest, path,
                          lambda rows: rows[4].update(ros_receive_time_s='5.5'))
    assert any('sample age exceeds' in item for item in stale['blockers'])
    path, manifest, trace = _fixture(tmp_path)
    zero_cov = _mutate_trace(trace, manifest, path,
                             lambda rows: rows[4].update(cov_00='0', cov_11='0', cov_22='0'))
    assert any('covariance' in item for item in zero_cov['blockers'])


def test_one_file_cannot_masquerade_as_multiple_raw_sources(tmp_path):
    path, manifest, _ = _fixture(tmp_path)
    manifest['raw_pc104_uplink'] = manifest['raw_imu_log']
    path.write_text(json.dumps(manifest), encoding='utf-8')
    report = preflight.audit(path)
    assert not report['navigation_evidence_reviewable']
    assert any('distinct evidence roles' in item for item in report['blockers'])

"""Check independent DDS/fixture time joining and source-file integrity."""

import csv
import hashlib
import importlib.util
import json
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / 'tools/audit_v2_flythrough_receipt_capture.py'
SPEC = importlib.util.spec_from_file_location('flythrough_receipt_audit', SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _csv(path, columns, values):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(values)


def _fixture(root):
    _csv(root / 'fixture_source_wall_map.csv',
         ['source_stamp_s', 'navigation_publish_after_monotonic_s',
          'magnetic_publish_after_monotonic_s'],
         [{'source_stamp_s': 1., 'navigation_publish_after_monotonic_s': 10.,
           'magnetic_publish_after_monotonic_s': 10.01}])
    _csv(root / 'fixture_stage_wall_timing.csv',
         ['source_stamp_s', 'stage', 'monotonic_s'],
         [{'source_stamp_s': 1., 'stage': 'sensors_published', 'monotonic_s': 10.01},
          {'source_stamp_s': 1., 'stage': 'peer_received_algorithm_outputs',
           'monotonic_s': 10.16},
          {'source_stamp_s': 1., 'stage': 'peer_received_pid_output',
           'monotonic_s': 10.30}])
    for role, time_s, extra in [
        ('navigation', 10.02, {}), ('magnetic', 10.03, {}),
        ('ros_setpoint', 10.15, {'target_speed_mps': .3}),
        ('pid', 10.20, {'thrust_percent': 10.}),
    ]:
        row = {'time_s': time_s, 'header_stamp_s': 1., **extra}
        _csv(root / 'ros_receipt' / f'{role}.csv', list(row), [row])
    (root / 'ros_receipt' / 'capture_summary.json').write_text(json.dumps({
        'capture_complete': True, 'dropped': {},
        'max_setpoint_publishers_seen': 1,
        'positive_setpoint_source_reviewable': False,
    }))
    paths = [p for p in root.rglob('*') if p.is_file()]
    (root / 'same_session_capture.json').write_text(json.dumps({
        'session_id': 'test', 'runner_returncode': 0,
        'runner_software_route_complete': False,
        'files_sha256': {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
                         for p in paths},
    }))


def test_accelerated_sim_stamp_maps_without_epoch_assumption(tmp_path):
    _fixture(tmp_path)
    result = MODULE.audit(tmp_path)
    assert result['recording_reviewable'] is True
    assert result['recorder_epoch_source_age_reviewable'] is False
    assert abs(result['joined']['pid']['max_fixture_publication_to_receipt_s'] - .19) < 1e-9
    assert result['same_host_peer_delivery_lag']['pid']['matched_count'] == 1
    assert result['field_release_authorized'] is False


def test_modified_receipt_rejected(tmp_path):
    _fixture(tmp_path)
    pid = tmp_path / 'ros_receipt' / 'pid.csv'
    pid.write_text(pid.read_text().replace('1.0', '2.0'))
    result = MODULE.audit(tmp_path)
    assert 'ros_receipt/pid.csv' in result['hash_mismatches']
    assert result['joined']['pid']['mapped_count'] == 0
    assert result['recording_reviewable'] is False

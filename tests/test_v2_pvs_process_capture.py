"""Review paced PVS receipt joins without inventing output causality."""

import csv
import hashlib
import importlib.util
import json
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / 'tools/audit_v2_pvs_process_capture.py'
SPEC = importlib.util.spec_from_file_location('pvs_process_capture_audit', SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _csv(path, row):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(row))
        writer.writeheader()
        writer.writerow(row)


def _fixture(root):
    _csv(root / 'pvs_fixture/fixture_source_wall_map.csv', {
        'source_stamp_s': 1.,
        'magnetic_publish_before_monotonic_s': 10.005,
        'magnetic_publish_after_monotonic_s': 10.01,
        'navigation_publish_before_monotonic_s': 9.99,
        'navigation_publish_after_monotonic_s': 10.00})
    (root / 'pvs_fixture/feeder_summary.json').write_text(json.dumps({
        'ticks': 1, 'completed': False, 'ever_confirm': False,
        'ever_track': False, 'positive_applied_rpm_ticks': 0,
        'max_tick_start_delay_s': .01}))
    _csv(root / 'ros_receipt/navigation.csv',
         {'header_stamp_s': 1., 'time_s': 10.02})
    _csv(root / 'ros_receipt/magnetic.csv',
         {'header_stamp_s': 1., 'time_s': 10.03})
    _csv(root / 'ros_receipt/ros_setpoint.csv',
         {'header_stamp_s': 1., 'time_s': 10.15, 'target_speed_mps': .3})
    # Sharing a source stamp does not imply this PID came from the magnetic
    # publication at 10.01; it may be based on an earlier navigation input.
    _csv(root / 'ros_receipt/pid.csv',
         {'header_stamp_s': 1., 'time_s': 10.005, 'thrust_percent': 10.})
    (root / 'ros_receipt/capture_summary.json').write_text(json.dumps({
        'capture_complete': True, 'dropped': {},
        'max_setpoint_publishers_seen': 1}))
    files = [p for p in root.rglob('*') if p.is_file()]
    (root / 'same_session_capture.json').write_text(json.dumps({
        'session_id': 'test', 'recorder_capture_complete': True,
        'file_sha256': {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
                        for p in files}}))


def test_outputs_are_mapped_without_false_causal_latency(tmp_path):
    _fixture(tmp_path)
    result = MODULE.audit(tmp_path)
    assert result['recording_reviewable'] is True
    assert result['joined']['pid']['mapped_count'] == 1
    assert result['joined']['pid']['max_sensor_publish_start_to_receipt_s'] is None
    assert abs(result['joined']['navigation']['max_sensor_publish_start_to_receipt_s'] - .03) < 1e-9
    assert result['field_release_authorized'] is False


def test_modified_sensor_receipt_rejected(tmp_path):
    _fixture(tmp_path)
    magnetic = tmp_path / 'ros_receipt/magnetic.csv'
    magnetic.write_text(magnetic.read_text().replace('10.03', '10.04'))
    result = MODULE.audit(tmp_path)
    assert 'ros_receipt/magnetic.csv' in result['hash_mismatches']
    assert result['recording_reviewable'] is False

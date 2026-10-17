"""Structural tests with generated files, never physical acceptance evidence."""

import csv
import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from tools import preflight_v2_inspection_field_packages as preflight
from tools import analyze_v2_inspection_field_packages as analysis


def record(path: Path, content: bytes) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return {'path': str(path), 'sha256': hashlib.sha256(content).hexdigest()}


class InspectionFieldPackagePreflightTest(unittest.TestCase):
    def test_single_trailing_zero_does_not_count_as_observed_zero_run(self):
        samples = [{'time_s': '0', 'main_motor_rpm': '100'},
                   {'time_s': '1', 'main_motor_rpm': '0'}]
        result = analysis.observed_zero_suffix(samples, 'main_motor_rpm', 0)
        self.assertEqual(result['zero_suffix_rows'], 1)
        self.assertIsNone(result['first_observed_zero_suffix_delay_s'])

    def test_board_frame_wrap_must_have_unique_time_window_match(self):
        udp = [{'time_s': '0', 'frame_number': '7', 'main_motor_rpm': '100'},
               {'time_s': '1', 'frame_number': '7', 'main_motor_rpm': '0'}]
        board = [{'time_s': '1', 'frame_number': '7', 'main_motor_rpm': '0'}]
        ambiguous, _ = analysis.correlate_pc104_receipts(
            udp, board, receipt_mode='board_command_log',
            max_lag_s=2, clock_error_s=0.001, fault_time_s=0)
        self.assertEqual(ambiguous['ambiguous_pc104_receipts'], 1)
        matched, _ = analysis.correlate_pc104_receipts(
            udp, board, receipt_mode='board_command_log',
            max_lag_s=0.2, clock_error_s=0.001, fault_time_s=0)
        self.assertEqual(matched['matched_pc104_receipts'], 1)
        self.assertEqual(matched['matched_command_rpm_mismatches'], 0)
        board[0]['main_motor_rpm'] = '100'
        mismatched, _ = analysis.correlate_pc104_receipts(
            udp, board, receipt_mode='board_command_log',
            max_lag_s=0.2, clock_error_s=0.001, fault_time_s=0)
        self.assertEqual(mismatched['matched_command_rpm_mismatches'], 1)
        echo = [{'time_s': '1', 'frame_number': '7', 'pc104_recv_uptime_ms': '1000'}]
        echo_report, echoed_commands = analysis.correlate_pc104_receipts(
            udp, echo, receipt_mode='checksum_valid_echo',
            max_lag_s=0.2, clock_error_s=0.001, fault_time_s=0)
        self.assertEqual(echo_report['matched_pc104_receipts'], 1)
        self.assertEqual(echoed_commands[0]['main_motor_rpm'], '0.0')

    def test_empty_template_does_not_authorize_field_use(self):
        report = preflight.audit(preflight.TEMPLATE)
        self.assertFalse(report['preflight_passed'])
        self.assertFalse(report['field_release_authorized'])
        self.assertGreater(len(report['blockers']), 0)

    def test_complete_structure_and_pc104_tamper(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest = json.loads(preflight.TEMPLATE.read_text(encoding='utf-8'))
            manifest.update(mission_id='m1', target_id='c1', site_id='s1',
                            coordinate_frame='fixture_ned', max_receipt_lag_s=0.2,
                            receipt_mode='board_command_log')
            manifest['software_snapshot'] = record(root / 'snapshot.json', b'{"revision":"test"}')
            manifest['identity_source'] = record(
                root / 'identity.json',
                json.dumps({'mission_id': 'm1', 'target_id': 'c1',
                            'reviewed_for_mission': True}).encode())
            manifest['clock_alignment'] = {
                'method': 'generated_fixture', 'measured_max_error_ms': 1.0,
                'raw_alignment_trace': record(root / 'clock.txt', b'fixture clock trace')}
            for package_name, roles in (
                    ('target_package', preflight.TARGET_ROLES),
                    ('execution_package', preflight.EXECUTION_ROLES)):
                for case in manifest[package_name]['cases']:
                    case_id = case['case_id']
                    case['session_id'] = 'fixture_' + case_id
                    case['raw_archive'] = record(root / f'{case_id}.raw', b'fixture raw ' + case_id.encode())
                    if package_name == 'target_package':
                        case['truth_method'] = 'independent surveyed marker fixture'
                    for role, (required, minimum) in roles.items():
                        path = root / f'{case_id}_{role}.csv'
                        columns = sorted(required)
                        with path.open('w', newline='', encoding='utf-8') as stream:
                            writer = csv.DictWriter(stream, fieldnames=columns)
                            writer.writeheader()
                            count = max(minimum, 3) if (case['kind'] == 'cue_loss'
                                                          and role in ('identity', 'target_decision')) else minimum
                            for index in range(count):
                                writer.writerow({name: (float(index) if name == 'time_s'
                                                       else 'uplink_loss' if (case['kind'] == 'uplink_loss'
                                                                              and role == 'fault_events'
                                                                              and name == 'event')
                                                       else 'fixture' if name in ('truth_method', 'event')
                                                       else '1.0' if name == 'lateral_y_m'
                                                       else '0' if (case['kind'] == 'cue_loss'
                                                                    and role == 'identity'
                                                                    and name == 'valid' and index >= 1)
                                                       else '1') for name in columns})
                        case['exports'][role] = {
                            'path': str(path), 'sha256': preflight.sha(path)}
            manifest_path = root / 'manifest.json'
            manifest_path.write_text(json.dumps(manifest), encoding='utf-8')
            report = preflight.audit(manifest_path)
            self.assertTrue(report['preflight_passed'], report['blockers'])
            self.assertTrue(report['target_package_reviewable'])
            self.assertTrue(report['execution_package_reviewable'])
            self.assertFalse(report['field_release_authorized'])

            manifest['coordinate_frame'] = ''
            manifest_path.write_text(json.dumps(manifest), encoding='utf-8')
            missing_frame = preflight.audit(manifest_path)
            self.assertFalse(missing_frame['target_package_reviewable'])
            self.assertFalse(missing_frame['execution_package_reviewable'])
            manifest['coordinate_frame'] = 'fixture_ned'
            manifest_path.write_text(json.dumps(manifest), encoding='utf-8')

            metrics = analysis.analyze(manifest_path)
            self.assertTrue(metrics['analysis_ready'], metrics.get('analysis_blockers'))
            self.assertFalse(metrics['field_release_authorized'])
            self.assertFalse(metrics['observed_protocol_red_flags_clear'])
            neighbor = next(case for case in metrics['target_cases'] if case['kind'] == 'neighbor')
            self.assertTrue(neighbor['task_complete_ever'])  # Deliberate bad fixture outcome.
            loss = next(case for case in metrics['execution_cases'] if case['kind'] == 'uplink_loss')
            self.assertEqual(loss['pc104_receipt_post_fault_nonzero_rows'], 2)
            self.assertIsNone(loss['pc104_receipt_first_observed_zero_suffix_delay_s'])
            self.assertEqual(loss['matched_post_fault_pc104_receipts'], 2)
            self.assertEqual(loss['unmatched_pc104_receipts'], 0)

            # The checksum-valid uplink echo mode derives RPM only from a
            # uniquely matched original downlink, never from motor feedback.
            direct_manifest = copy.deepcopy(manifest)
            manifest['receipt_mode'] = 'checksum_valid_echo'
            for case in manifest['execution_package']['cases']:
                path = root / f"{case['case_id']}_echo.csv"
                with path.open('w', newline='', encoding='utf-8') as stream:
                    writer = csv.DictWriter(stream, fieldnames=sorted(preflight.ECHO_RECEIPT_COLUMNS))
                    writer.writeheader()
                    for index in range(2):
                        writer.writerow({'time_s': index, 'frame_number': 1,
                                         'pc104_recv_uptime_ms': 1000 + 1000 * index})
                case['exports']['pc104_receipt'] = {'path': str(path), 'sha256': preflight.sha(path)}
            manifest_path.write_text(json.dumps(manifest), encoding='utf-8')
            self.assertTrue(preflight.audit(manifest_path)['preflight_passed'])
            echo_metrics = analysis.analyze(manifest_path)
            self.assertTrue(echo_metrics['analysis_ready'], echo_metrics.get('analysis_blockers'))
            echo_loss = next(case for case in echo_metrics['execution_cases']
                             if case['kind'] == 'uplink_loss')
            self.assertEqual(echo_loss['pc104_command_rpm_source'], 'matched_original_udp_frame')
            self.assertEqual(echo_loss['matched_post_fault_pc104_receipts'], 2)
            self.assertFalse(echo_metrics['field_release_authorized'])
            manifest = direct_manifest
            manifest_path.write_text(json.dumps(manifest), encoding='utf-8')

            # A structurally complete, internally consistent fixture can
            # clear *observed protocol* flags without granting field release.
            bad_manifest = copy.deepcopy(manifest)
            originals = {}

            def edit_export(case, role, change):
                record_info = case['exports'][role]
                path = Path(record_info['path'])
                originals[path] = path.read_bytes()
                with path.open(newline='', encoding='utf-8') as stream:
                    reader = csv.DictReader(stream)
                    names, data = reader.fieldnames, list(reader)
                change(data)
                with path.open('w', newline='', encoding='utf-8') as stream:
                    writer = csv.DictWriter(stream, fieldnames=names)
                    writer.writeheader()
                    writer.writerows(data)
                record_info['sha256'] = preflight.sha(path)

            for case in manifest['target_package']['cases']:
                def clean_decision(data, kind=case['kind']):
                    for row in data:
                        row['depth_published'] = '0'
                        if kind == 'neighbor':
                            row['target_confirmed'] = row['task_complete'] = '0'
                        if kind == 'cue_loss' and float(row['time_s']) >= 1:
                            for name in ('target_confirmed', 'task_complete', 'autonomous_allowed'):
                                row[name] = '0'
                edit_export(case, 'target_decision', clean_decision)

            loss_case = next(case for case in manifest['execution_package']['cases']
                             if case['kind'] == 'uplink_loss')
            for role, column in (('ros_setpoint', 'target_speed_mps'),
                                 ('udp_downlink', 'main_motor_rpm'),
                                 ('pc104_receipt', 'main_motor_rpm')):
                def zero_tail(data, value_column=column):
                    data[1][value_column] = '0'
                    extra = dict(data[1])
                    extra['time_s'] = '2'
                    data.append(extra)
                edit_export(loss_case, role, zero_tail)
            manifest_path.write_text(json.dumps(manifest), encoding='utf-8')
            self.assertTrue(preflight.audit(manifest_path)['preflight_passed'])
            clean_metrics = analysis.analyze(manifest_path)
            self.assertTrue(clean_metrics['analysis_ready'], clean_metrics.get('analysis_blockers'))
            self.assertTrue(clean_metrics['observed_protocol_red_flags_clear'],
                            clean_metrics['observed_protocol_red_flags'])
            self.assertFalse(clean_metrics['field_release_authorized'])
            clean_loss = next(case for case in clean_metrics['execution_cases']
                              if case['kind'] == 'uplink_loss')
            self.assertEqual(clean_loss['pc104_receipt_zero_suffix_rows'], 2)
            self.assertEqual(clean_loss['pc104_receipt_zero_suffix_duration_s'], 1)
            for path, original_content in originals.items():
                path.write_bytes(original_content)
            manifest = bad_manifest
            manifest_path.write_text(json.dumps(manifest), encoding='utf-8')

            # A mutated hardware receipt must invalidate the execution package.
            receipt = Path(manifest['execution_package']['cases'][0]['exports']['pc104_receipt']['path'])
            original = receipt.read_bytes()
            receipt.write_text('tampered', encoding='utf-8')
            report = preflight.audit(manifest_path)
            self.assertFalse(report['preflight_passed'])
            self.assertFalse(report['execution_package_reviewable'])
            self.assertTrue(report['target_package_reviewable'])
            self.assertFalse(report['field_release_authorized'])
            self.assertTrue(any('pc104_receipt' in item for item in report['blockers']))

            # A valid archive with no motion after the fault is analyzable only as a gap.
            receipt.write_bytes(original)
            motion_record = manifest['execution_package']['cases'][1]['exports']['vehicle_motion']
            motion_path = Path(motion_record['path'])
            motion_original = motion_path.read_bytes()
            with motion_path.open(newline='', encoding='utf-8') as stream:
                reader = csv.DictReader(stream)
                motion_columns, motion_rows = reader.fieldnames, list(reader)
            motion_rows[0]['time_s'] = '-1'
            motion_rows[1]['time_s'] = '0'
            with motion_path.open('w', newline='', encoding='utf-8') as stream:
                writer = csv.DictWriter(stream, fieldnames=motion_columns)
                writer.writeheader()
                writer.writerows(motion_rows)
            motion_record['sha256'] = preflight.sha(motion_path)
            manifest_path.write_text(json.dumps(manifest), encoding='utf-8')
            self.assertTrue(preflight.audit(manifest_path)['preflight_passed'])
            metrics = analysis.analyze(manifest_path)
            self.assertFalse(metrics['analysis_ready'])
            self.assertTrue(any('vehicle motion' in item for item in metrics['analysis_blockers']))
            self.assertFalse(metrics['field_release_authorized'])
            motion_path.write_bytes(motion_original)
            motion_record['sha256'] = preflight.sha(motion_path)

            # Correct hashes do not rescue streams from unrelated time intervals.
            shifted = manifest['target_package']['cases'][0]['exports']['target_decision']
            path = Path(shifted['path'])
            with path.open(newline='', encoding='utf-8') as stream:
                reader = csv.DictReader(stream)
                columns, decisions = reader.fieldnames, list(reader)
            for index, row in enumerate(decisions):
                row['time_s'] = str(100 + index)
            with path.open('w', newline='', encoding='utf-8') as stream:
                writer = csv.DictWriter(stream, fieldnames=columns)
                writer.writeheader()
                writer.writerows(decisions)
            shifted['sha256'] = preflight.sha(path)
            manifest_path.write_text(json.dumps(manifest), encoding='utf-8')
            report = preflight.audit(manifest_path)
            self.assertFalse(report['preflight_passed'])
            self.assertTrue(any('shared time interval' in item for item in report['blockers']))


if __name__ == '__main__':
    unittest.main()

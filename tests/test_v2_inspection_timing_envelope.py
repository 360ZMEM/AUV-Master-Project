"""Generated timing fixtures exercise audit semantics, not physical acceptance."""

import csv
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from tools import audit_v2_inspection_timing_envelope as audit


def artifact(path: Path) -> dict:
    return {'path': path.name, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


class TimingEnvelopeTest(unittest.TestCase):
    def fixture(self, root: Path, kind: str = 'input_loss') -> tuple[Path, dict]:
        manifest = json.loads(audit.TEMPLATE.read_text(encoding='utf-8'))
        manifest.update(session_id='synthetic_session', mission_id='m1', target_id='c1',
                        platform_id='generated_fixture', case_kind=kind,
                        receipt_mode='board_command_log')
        for key, content in [('raw_archive', b'fixture only'),
                             ('software_snapshot', b'fixture software')]:
            path = root / f'{key}.bin'
            path.write_bytes(content)
            manifest[key] = artifact(path)
        alignment = root / 'clock.txt'
        alignment.write_text('generated clock, 1 ms bound', encoding='utf-8')
        manifest['clock_alignment'] = {'method': 'generated_fixture',
                                       'measured_max_error_ms': 1,
                                       'raw_alignment_trace': artifact(alignment)}
        manifest['limits'] = {
            'max_gate_gap_s': .15, 'max_gate_duration_s': .05,
            'max_ros_gap_s': .15, 'max_pid_gap_s': .15,
            'max_udp_gap_s': .15, 'max_pc104_gap_s': .15,
            'max_ros_delivery_s': .05,
            'max_sensor_age_s': .5, 'max_candidate_age_s': .35,
            'max_budget_age_s': 1.5, 'max_pc104_lag_s': .1,
            'min_pc104_receipt_fraction': .3,
            'max_local_zero_delay_s': .15,
            'max_fault_zero_delay_s': .15,
        }
        manifest['windows'] = {'healthy_start_s': .5, 'healthy_end_s': 1.5,
                               'fault_start_s': 1.6, 'record_end_s': 3.0}
        if kind == 'nominal':
            manifest['windows'].pop('fault_start_s')
        for role, columns in audit.ROLES.items():
            path = root / f'{role}.csv'
            with path.open('w', newline='', encoding='utf-8') as stream:
                writer = csv.DictWriter(stream, fieldnames=sorted(columns))
                writer.writeheader()
                if role == 'mission_events':
                    writer.writerow({'time_s': .05, 'event': 'MISSION_START'})
                    writer.writerow({'time_s': 2.95,
                                     'event': 'ROUTE_COMPLETE' if kind == 'nominal' else 'SUSPENDED'})
                else:
                    for i in range(31):
                        t = round(i * .1, 6)
                        positive = kind == 'nominal' or i < 16
                        row = {'time_s': t, 'end_s': t + .005,
                               'decision_speed_mps': .3 if positive else 0,
                               'target_speed_mps': .3 if positive else 0,
                               'candidate_source_time_s': t - .05,
                               'thrust_percent': 25 if positive else 0,
                               'main_motor_rpm': 100 if positive else 0,
                               'frame_number': i, 'budget_latched': 0}
                        for name in audit.AGE_COLUMNS:
                            row[name] = .05
                        if role == 'ros_setpoint':
                            row['time_s'] = t + .015
                        elif role == 'pid':
                            row['time_s'] = t + .02
                        elif role == 'udp_downlink':
                            row['time_s'] = t + .03
                        elif role == 'pc104_receipt':
                            row['time_s'] = t + .04
                        writer.writerow({key: row[key] for key in columns})
            manifest['exports'][role] = artifact(path)
        path = root / 'manifest.json'
        path.write_text(json.dumps(manifest), encoding='utf-8')
        return path, manifest

    def edit(self, root: Path, manifest: dict, role: str, func) -> Path:
        path = root / manifest['exports'][role]['path']
        with path.open(newline='', encoding='utf-8') as stream:
            reader = csv.DictReader(stream)
            columns, rows = reader.fieldnames, list(reader)
        func(rows)
        with path.open('w', newline='', encoding='utf-8') as stream:
            writer = csv.DictWriter(stream, fieldnames=columns)
            writer.writeheader()
            writer.writerows(rows)
        manifest['exports'][role] = artifact(path)
        (root / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
        return root / 'manifest.json'

    def test_empty_template_rejects(self):
        result = audit.analyze(audit.TEMPLATE)
        self.assertFalse(result['data_reviewable'])
        self.assertFalse(result['field_release_authorized'])

    def test_generated_complete_run_and_adversarial_faults(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path, manifest = self.fixture(root)
            good = audit.analyze(path)
            self.assertTrue(good['data_reviewable'], good['blockers'])
            self.assertTrue(good['timing_bounds_passed'], good['red_flags'])
            self.assertFalse(good['field_release_authorized'])
            self.assertEqual(good['pc104']['matched_pc104_receipts'], 31)
            self.assertTrue(good['fault_zero_tails']['pc104']['zero_tail_passed'])
            self.assertAlmostEqual(good['maximum_observed_positive_candidate_source_age_s'],
                                   .065)

            self.edit(root, manifest, 'ros_setpoint',
                      lambda rows: rows[9].update(candidate_source_time_s='0.35'))
            stale_at_receipt = audit.analyze(path)
            self.assertFalse(stale_at_receipt['timing_bounds_passed'])
            self.assertTrue(any('source stale at independent receipt' in x
                                for x in stale_at_receipt['red_flags']))

            path, manifest = self.fixture(root)
            manifest['schema_version'] = 1
            path.write_text(json.dumps(manifest), encoding='utf-8')
            legacy = audit.analyze(path)
            self.assertFalse(legacy['data_reviewable'])
            self.assertTrue(any('schema_version must be 2' in x
                                for x in legacy['blockers']))

            path, manifest = self.fixture(root)
            self.edit(root, manifest, 'gate_ticks',
                      lambda rows: rows[8].update(navigation_source_age_s='1.2'))
            old = audit.analyze(path)
            self.assertFalse(old['timing_bounds_passed'])
            self.assertTrue(any('navigation_source_age_s' in x for x in old['red_flags']))

            path, manifest = self.fixture(root)
            self.edit(root, manifest, 'ros_setpoint',
                      lambda rows: rows[9].update(target_speed_mps='0'))
            missing = audit.analyze(path)
            self.assertFalse(missing['timing_bounds_passed'])
            self.assertTrue(any('healthy ROS' in x or 'value mismatch' in x
                                for x in missing['red_flags']))

            path, manifest = self.fixture(root)
            self.edit(root, manifest, 'pc104_receipt',
                      lambda rows: rows[18].update(main_motor_rpm='100'))
            board = audit.analyze(path)
            self.assertFalse(board['timing_bounds_passed'])
            self.assertEqual(board['pc104']['matched_command_rpm_mismatches'], 1)

            path, manifest = self.fixture(root)
            receipt = root / manifest['exports']['pc104_receipt']['path']
            receipt.write_text('tampered', encoding='utf-8')
            tampered = audit.analyze(path)
            self.assertFalse(tampered['data_reviewable'])
            self.assertTrue(any('SHA-256 mismatch' in x for x in tampered['blockers']))

            path, manifest = self.fixture(root)
            self.edit(root, manifest, 'mission_events',
                      lambda rows: rows[1].update(event='ROUTE_COMPLETE'))
            wrong_terminal = audit.analyze(path)
            self.assertFalse(wrong_terminal['data_reviewable'])
            self.assertTrue(any('MISSION_START to SUSPENDED' in x
                                for x in wrong_terminal['blockers']))

    def test_nominal_run(self):
        with tempfile.TemporaryDirectory() as directory:
            path, _ = self.fixture(Path(directory), kind='nominal')
            result = audit.analyze(path)
            self.assertTrue(result['timing_bounds_passed'], result['red_flags'])
            self.assertNotIn('fault_zero_tails', result)

    def test_board_receives_one_of_three_udp_frames(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path, manifest = self.fixture(root)
            manifest['limits']['max_pc104_gap_s'] = .35
            manifest['limits']['max_fault_zero_delay_s'] = .4
            self.edit(root, manifest, 'pc104_receipt',
                      lambda rows: rows.__setitem__(slice(None), rows[::3]))
            path.write_text(json.dumps(manifest), encoding='utf-8')
            result = audit.analyze(path)
            self.assertTrue(result['timing_bounds_passed'], result['red_flags'])
            self.assertEqual(result['pc104']['matched_pc104_receipts'], 11)
            self.assertLess(result['pc104']['observed_receipt_fraction'], .36)

    def test_clock_error_must_resolve_limits(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path, manifest = self.fixture(root)
            manifest['clock_alignment']['measured_max_error_ms'] = 100
            path.write_text(json.dumps(manifest), encoding='utf-8')
            result = audit.analyze(path)
            self.assertFalse(result['data_reviewable'])
            self.assertTrue(any('clock alignment' in x for x in result['blockers']))

    def test_checksum_valid_echo_mode(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path, manifest = self.fixture(root)
            board_path = root / manifest['exports']['pc104_receipt']['path']
            with board_path.open(newline='', encoding='utf-8') as stream:
                rows = list(csv.DictReader(stream))
            with board_path.open('w', newline='', encoding='utf-8') as stream:
                writer = csv.DictWriter(stream, fieldnames=sorted(audit.ECHO_COLUMNS))
                writer.writeheader()
                for i, row in enumerate(rows):
                    writer.writerow({'time_s': row['time_s'],
                                     'frame_number': row['frame_number'],
                                     'pc104_recv_uptime_ms': 1000 + 100 * i})
            manifest['receipt_mode'] = 'checksum_valid_echo'
            manifest['exports']['pc104_receipt'] = artifact(board_path)
            path.write_text(json.dumps(manifest), encoding='utf-8')
            result = audit.analyze(path)
            self.assertTrue(result['timing_bounds_passed'], result['red_flags'])
            self.assertEqual(result['pc104']['pc104_command_rpm_source'],
                             'matched_original_udp_frame')


if __name__ == '__main__':
    unittest.main()

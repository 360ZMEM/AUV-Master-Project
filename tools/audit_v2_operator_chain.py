#!/usr/bin/env python3
"""Audit the current bridge-to-console candidate and its separate synthetic runs."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / 'AUV-Master-Mag/results/v2/operator_chain'
OUT = ROOT / 'AUV-Master-Mag/docs/v2/publication/fwhm_v2_experiment_results/data'
FILES = (
    'brain_linux/src/auv_cable_tracking_v2/auv_cable_tracking_v2/inspection_bridge_node.py',
    'brain_linux/src/auv_cable_tracking_v2/auv_cable_tracking_v2/operational_status.py',
    'brain_linux/src/auv_cable_tracking_v2/config/cable_tracking_v2_flythrough_sonar_identity_corridor_budget_sim.yaml',
    'console_soft/auv_console_pyside6/src/ui/inspection_operational_view.py',
    'console_soft/auv_console_pyside6/src/ui/main_window.py',
    'console_soft/auv_console_pyside6/console_config.defense.yaml',
    'console_soft/auv_console_pyside6/tests/test_inspection_operational_view.py',
    'tools/smoke_v2_flythrough_ros_pvs.py',
    'tools/smoke_v2_operator_side_channel.py',
    'AUV-Master-Mag/docs/v2/publication/fwhm_v2_experiment_results/figures/operator_console_status_loopback.png',
)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_case(folder: str, case: str):
    base = RUN / folder / f'{case}_seed_101'
    csv_path = base.with_suffix('.csv')
    summary_path = base.with_name(base.name + '_summary.json')
    with csv_path.open(newline='', encoding='utf-8') as stream:
        rows = list(csv.DictReader(stream))
    summary = json.loads(summary_path.read_text(encoding='utf-8'))
    assert len(rows) == summary['ticks']
    return rows, summary, {str(csv_path.relative_to(ROOT)): sha(csv_path),
                           str(summary_path.relative_to(ROOT)): sha(summary_path)}


def main() -> None:
    guard_rows, guard, guard_hashes = read_case('guard_loss', 'wire_guard_telemetry_loss')
    hold_rows, hold, hold_hashes = read_case('identity_hold', 'wire')
    active = [row for row in guard_rows if row['autonomous_execution_authorized'] == 'True']
    denied = [row for row in guard_rows if row['authority_reason'] == 'AMD_UPLINK_STALE']
    held = [row for row in hold_rows if row['mode'] == 'hold']
    assert len(active) == 2336 and len(denied) == 241
    assert all(row['autonomous_execution_authorized'] == 'False' and
               row['operational_localization_status'] == 'LOCALIZED_DEPTH_PENDING' and
               float(row['rpm']) == 0. for row in denied)
    assert guard['guard_telemetry_loss_zero_udp_ticks'] == len(denied)
    assert len(held) == 41 and hold['post_hold_nonzero_rpm_ticks'] == 0
    assert all(row['autonomous_execution_authorized'] == 'False' and
               row['arbiter_source'] == 'SAFETY_FALLBACK' and
               float(row['rpm']) == 0. for row in held)

    ui_summary_path = RUN / 'zenoh_ui/summary.json'
    ui = json.loads(ui_summary_path.read_text(encoding='utf-8'))
    assert ui['bridge_to_console_received'] and not ui['hardware_connected']
    assert '自治许可: 禁止（上行失鲜）' in ui['denied_label']
    assert '状态失鲜' in ui['duplicate_stale_label']
    screenshot = RUN / 'zenoh_ui/console_inspection_authority.png'
    assert screenshot.is_file() and screenshot.stat().st_size > 10000
    payload = {
        'role': 'inspection_v2_bridge_zenoh_console_candidate',
        'field_release_authorized': False,
        'guard_loss': {'authorized_before_cycles': len(active),
                       'revoked_after_cycles': len(denied),
                       'localized_after_cycles': len(denied),
                       'zero_udp_rpm_after_cycles': len(denied)},
        'identity_hold': {'hold_cycles': len(held), 'revoked_cycles': len(held),
                          'zero_udp_rpm_cycles': len(held)},
        'ui_loopback': {'bridge_to_console_received': True,
                        'duplicate_sample_does_not_refresh_status': True,
                        'hardware_connected': False},
        'source_sha256': {name: sha(ROOT / name) for name in FILES},
        'evidence_sha256': {**guard_hashes, **hold_hashes,
                            str(ui_summary_path.relative_to(ROOT)): sha(ui_summary_path),
                            str(screenshot.relative_to(ROOT)): sha(screenshot)},
        'audit_script_sha256': sha(Path(__file__)),
        'remaining_field_gates': [
            'physical target-sonar evidence and independent identity calibration',
            'measured AUV zero-thrust drift/current and actual corridor bounds',
            'cross-device Zenoh continuity, physical PC104 receipt and upper-level disposition timing',
            'magnetic width-to-distance and synchronized altitude calibration before depth release',
        ],
    }
    target = OUT / 'inspection_v2_candidate_snapshot_20260927_operator_chain.json'
    if target.exists() and json.loads(target.read_text(encoding='utf-8')) != payload:
        raise SystemExit('pinned operator-chain snapshot changed; create a new version')
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'guard_loss': payload['guard_loss'], 'identity_hold': payload['identity_hold'],
                      'ui_loopback': payload['ui_loopback'], 'field_release_authorized': False},
                     ensure_ascii=False))


if __name__ == '__main__':
    main()

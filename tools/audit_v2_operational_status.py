#!/usr/bin/env python3
"""Freeze the v2 bridge authority/status evidence without field-release claims."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'AUV-Master-Mag/docs/v2/publication/fwhm_v2_experiment_results/data'
RUNS = ROOT / 'AUV-Master-Mag/results/v2/operational_status'
FILES = (
    'brain_linux/src/auv_cable_tracking_v2/auv_cable_tracking_v2/cable_tracking_v2_node.py',
    'brain_linux/src/auv_cable_tracking_v2/auv_cable_tracking_v2/hold_budget.py',
    'brain_linux/src/auv_cable_tracking_v2/auv_cable_tracking_v2/inspection_bridge_node.py',
    'brain_linux/src/auv_cable_tracking_v2/auv_cable_tracking_v2/operational_status.py',
    'brain_linux/src/auv_cable_tracking_v2/config/cable_tracking_v2_flythrough_sonar_identity_corridor_budget_sim.yaml',
    'brain_linux/src/auv_cable_tracking_v2/test/test_inspection_bridge_gate.py',
    'brain_linux/src/auv_cable_tracking_v2/test/test_operational_status.py',
    'tools/smoke_v2_flythrough_ros_pvs.py',
    'tools/plot_v2_operational_status.py',
    'AUV-Master-Mag/docs/v2/publication/fwhm_v2_experiment_results/data/36_localization_vs_autonomy_authority_summary.json',
    'AUV-Master-Mag/docs/v2/publication/fwhm_v2_experiment_results/figures/36_localization_vs_autonomy_authority.pdf',
)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(folder: str, case: str):
    base = RUNS / folder / f'{case}_seed_101'
    csv_path, summary_path = base.with_suffix('.csv'), base.with_name(base.name + '_summary.json')
    with csv_path.open(newline='', encoding='utf-8') as stream:
        rows = list(csv.DictReader(stream))
    summary = json.loads(summary_path.read_text(encoding='utf-8'))
    assert len(rows) == summary['ticks']
    return rows, summary, {
        str(csv_path.relative_to(ROOT)): sha(csv_path),
        str(summary_path.relative_to(ROOT)): sha(summary_path),
    }


def main() -> None:
    guard_rows, guard, guard_hashes = load('guard_loss_verified', 'wire_guard_telemetry_loss')
    hold_rows, hold, hold_hashes = load('identity_hold', 'wire')
    active = [row for row in guard_rows if row['autonomous_execution_authorized'] == 'True']
    denied = [row for row in guard_rows if row['authority_reason'] == 'AMD_UPLINK_STALE']
    held = [row for row in hold_rows if row['mode'] == 'hold']
    assert len(active) == 2336 and len(denied) == 241
    assert all(row['autonomous_execution_authorized'] == 'False' for row in denied)
    assert all(row['operational_localization_status'] == 'LOCALIZED_DEPTH_PENDING' for row in denied)
    assert all(float(row['rpm']) == 0. for row in denied)
    assert guard['guard_telemetry_loss_zero_udp_ticks'] == len(denied)
    assert len(held) == 41 and hold['first_hold_s'] == 585.
    assert all(row['autonomous_execution_authorized'] == 'False' and
               row['arbiter_source'] == 'SAFETY_FALLBACK' and
               float(row['rpm']) == 0. for row in held)
    assert hold['post_hold_nonzero_rpm_ticks'] == 0
    payload = {
        'role': 'inspection_v2_operational_status_software_candidate',
        'field_release_authorized': False,
        'guard_loss': {'authorized_before_cycles': len(active),
                       'revoked_after_cycles': len(denied),
                       'localization_still_valid_cycles': len(denied),
                       'zero_udp_rpm_cycles': len(denied)},
        'identity_hold': {'hold_cycles': len(held), 'authority_revoked_cycles': len(held),
                          'zero_udp_rpm_cycles': len(held)},
        'source_sha256': {name: sha(ROOT / name) for name in FILES},
        'run_sha256': {**guard_hashes, **hold_hashes},
        'audit_script_sha256': sha(Path(__file__)),
        'remaining_field_gates': [
            'physical target-sonar evidence and independent identity calibration',
            'measured zero-thrust drift, current and stop envelope within a real corridor',
            'physical PC104 command receipt and upper-level disposition timing',
            'controlled magnetic width-to-distance and synchronized altitude calibration before depth release',
        ],
    }
    out = DATA / 'inspection_v2_candidate_snapshot_20260927_operational_status.json'
    if out.exists() and json.loads(out.read_text(encoding='utf-8')) != payload:
        raise SystemExit('existing operational-status snapshot changed; create a new version')
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'guard_loss': payload['guard_loss'], 'identity_hold': payload['identity_hold'],
                      'field_release_authorized': False}, ensure_ascii=False))


if __name__ == '__main__':
    main()

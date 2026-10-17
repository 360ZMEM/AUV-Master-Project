#!/usr/bin/env python3
"""Independently audit the single-run synthetic PVS-to-console guard loss."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / 'AUV-Master-Mag/results/v2/operator_chain/same_run_guard_loss_verified'
OUT = ROOT / 'AUV-Master-Mag/docs/v2/publication/fwhm_v2_experiment_results'
IMAGE = OUT / 'figures/operator_console_same_run_guard_loss.png'
SOURCES = {
    'bridge': ROOT / 'brain_linux/src/auv_cable_tracking_v2/auv_cable_tracking_v2/inspection_bridge_node.py',
    'console': ROOT / 'console_soft/auv_console_pyside6/src/ui/main_window.py',
    'pvs_harness': ROOT / 'tools/smoke_v2_flythrough_ros_pvs.py',
    'same_run_harness': ROOT / 'tools/smoke_v2_operator_chain_same_run.py',
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    csv_path = RUN / 'wire_guard_telemetry_loss_seed_101.csv'
    trace_path = RUN / 'console_operational_status.json'
    screenshot = RUN / 'console_same_run_guard_loss.png'
    summary_path = RUN / 'same_run_summary.json'
    summary = json.loads(summary_path.read_text(encoding='utf-8'))
    trace = json.loads(trace_path.read_text(encoding='utf-8'))
    with csv_path.open(newline='', encoding='utf-8') as stream:
        rows = list(csv.DictReader(stream))
    assert summary['same_run'] and not summary['hardware_connected']
    assert summary['physical_amd_uplink'] is False
    assert len(trace) == summary['console_status_count'] == summary['bridge_status_count']
    assert all(sha(SOURCES[key]) == value for key, value in summary['source_sha256'].items())
    for name, digest in summary['evidence_sha256'].items():
        assert sha(RUN / name) == digest
    assert sha(IMAGE) == sha(screenshot)

    active = [row for row in rows if row['autonomous_execution_authorized'] == 'True']
    denied = [row for row in rows if row['authority_reason'] == 'AMD_UPLINK_STALE']
    assert len(rows) == 2577 and len(active) == 2336 and len(denied) == 241
    assert all(row['autonomous_execution_authorized'] == 'False' and
               row['operational_localization_status'] == 'LOCALIZED_DEPTH_PENDING' and
               float(row['rpm']) == 0. for row in denied)
    assert all(row['depth_valid'] == 'False' for row in rows)
    assert summary['guard_loss_zero_udp_ticks'] == len(denied)

    seen_keys = set()
    for item in trace:
        key = (item['command_sequence'], item['timestamp_s'])
        assert key not in seen_keys
        seen_keys.add(key)
    assert all(a['timestamp_s'] <= b['timestamp_s'] for a, b in zip(trace, trace[1:]))
    ui_active = [item for item in trace if item['autonomous_execution_authorized'] is True]
    ui_denied = [item for item in trace if item['authority_reason'] == 'AMD_UPLINK_STALE']
    assert ui_active and len(ui_denied) == 723
    assert all(item['autonomous_execution_authorized'] is False and
               item['localization_status'] == 'LOCALIZED_DEPTH_PENDING' and
               item['console_label'] == '定位: 已定位（埋深未许可） | 自治许可: 禁止（上行失鲜）'
               for item in ui_denied)
    first_denied = trace.index(ui_denied[0])
    assert all(item['authority_reason'] == 'AMD_UPLINK_STALE' for item in trace[first_denied:])
    assert summary['final_console_label'] == ui_denied[-1]['console_label']

    report = {
        'role': 'single_synthetic_ros_pid_guard_udp_pvs_zenoh_pyside6_audit',
        'field_release_authorized': False,
        'pvs_cycles': len(rows), 'pvs_authorized_cycles': len(active),
        'pvs_guard_revoked_zero_udp_cycles': len(denied),
        'bridge_and_console_matched_statuses': len(trace),
        'console_guard_revoked_statuses': len(ui_denied),
        'final_console_label': summary['final_console_label'],
        'scope': 'one isolated host, synthetic magnetic/sonar/AMD fixtures and native PVS; no PC104 or physical AUV',
        'source_sha256': summary['source_sha256'],
        'evidence_sha256': {
            **summary['evidence_sha256'],
            str(summary_path.relative_to(ROOT)): sha(summary_path),
            str(IMAGE.relative_to(ROOT)): sha(IMAGE),
        },
        'audit_script_sha256': sha(Path(__file__)),
    }
    target = OUT / 'data/inspection_v2_same_run_operator_chain_20260927.json'
    if target.exists() and json.loads(target.read_text(encoding='utf-8')) != report:
        raise SystemExit('pinned same-run audit changed; create a new version')
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({key: report[key] for key in (
        'pvs_cycles', 'pvs_guard_revoked_zero_udp_cycles',
        'bridge_and_console_matched_statuses', 'console_guard_revoked_statuses',
        'field_release_authorized')}, ensure_ascii=False))


if __name__ == '__main__':
    main()

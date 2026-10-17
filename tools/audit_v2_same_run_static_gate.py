#!/usr/bin/env python3
"""Audit the current synthetic ROS-to-console run after static-prior gating."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / 'AUV-Master-Mag/results/v2/operator_chain/same_run_guard_loss_static_gate_pinned_v2_20260927'
DATA = ROOT / 'AUV-Master-Mag/docs/v2/publication/fwhm_v2_experiment_results/data'
SNAPSHOT = DATA / 'inspection_v2_static_target_prior_gate_20260927.json'
OUT = DATA / 'inspection_v2_same_run_static_gate_pinned_v2_20260927.json'
SOURCES = {
    'decision_node': 'brain_linux/src/auv_cable_tracking_v2/auv_cable_tracking_v2/cable_tracking_v2_node.py',
    'static_prior': 'brain_linux/src/auv_cable_tracking_v2/auv_cable_tracking_v2/static_target_prior.py',
    'bridge': 'brain_linux/src/auv_cable_tracking_v2/auv_cable_tracking_v2/inspection_bridge_node.py',
    'console': 'console_soft/auv_console_pyside6/src/ui/main_window.py',
    'pvs_harness': 'tools/smoke_v2_flythrough_ros_pvs.py',
    'same_run_harness': 'tools/smoke_v2_operator_chain_same_run.py',
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def audit() -> dict:
    csv_path = RUN / 'wire_guard_telemetry_loss_seed_101.csv'
    trace_path = RUN / 'console_operational_status.json'
    bridge_trace_path = RUN / 'bridge_operational_status.json'
    summary_path = RUN / 'same_run_summary.json'
    screenshot = RUN / 'console_same_run_guard_loss.png'
    summary = json.loads(summary_path.read_text(encoding='utf-8'))
    trace = json.loads(trace_path.read_text(encoding='utf-8'))
    bridge_trace = json.loads(bridge_trace_path.read_text(encoding='utf-8'))
    snapshot = json.loads(SNAPSHOT.read_text(encoding='utf-8'))
    with csv_path.open(newline='', encoding='utf-8') as stream:
        rows = list(csv.DictReader(stream))
    assert summary['same_run'] is True
    assert summary['hardware_connected'] is False
    assert summary['physical_amd_uplink'] is False
    assert summary['console_authorized_seen'] is True
    assert summary['console_guard_revocation_seen'] is True
    for role, digest in summary['source_sha256'].items():
        assert sha(ROOT / SOURCES[role]) == digest, role
    for name, digest in snapshot['source_sha256'].items():
        assert sha(ROOT / name) == digest, name
    for name, digest in summary['evidence_sha256'].items():
        assert sha(RUN / name) == digest, name
    assert len(rows) == 2577
    active = [row for row in rows if row['autonomous_execution_authorized'] == 'True']
    denied = [row for row in rows if row['authority_reason'] == 'AMD_UPLINK_STALE']
    assert len(active) == 2336 and len(denied) == 241
    assert summary['guard_loss_zero_udp_ticks'] == len(denied)
    assert all(row['autonomous_execution_authorized'] == 'False'
               and row['operational_localization_status'] == 'LOCALIZED_DEPTH_PENDING'
               and float(row['rpm']) == 0.
               and float(row['thrust_percent']) == 0.
               for row in denied)
    assert all(row['depth_valid'] == 'False' for row in rows)
    assert len(trace) == len(bridge_trace) == summary['bridge_status_count'] == summary['console_status_count']
    keys = [(item['command_sequence'], item['timestamp_s']) for item in trace]
    assert len(keys) == len(set(keys))
    bridge_by_key = {(item['command_sequence'], item['timestamp_s']): item for item in bridge_trace}
    assert len(bridge_by_key) == len(bridge_trace)
    assert set(keys) == set(bridge_by_key)
    assert all(item['autonomous_execution_authorized'] == bridge_by_key[key]['autonomous_execution_authorized']
               and item['authority_reason'] == bridge_by_key[key]['authority_reason']
               and item['localization_status'] == bridge_by_key[key]['localization_status']
               for key, item in zip(keys, trace))
    assert all(a['timestamp_s'] <= b['timestamp_s'] for a, b in zip(trace, trace[1:]))
    ui_denied = [item for item in trace if item['authority_reason'] == 'AMD_UPLINK_STALE']
    assert ui_denied and all(item['autonomous_execution_authorized'] is False
                             and item['localization_status'] == 'LOCALIZED_DEPTH_PENDING'
                             and '禁止（上行失鲜）' in item['console_label'] for item in ui_denied)
    assert summary['final_console_label'] == ui_denied[-1]['console_label']
    return {
        'role': 'current_source_single_synthetic_ros_pid_guard_udp_pvs_zenoh_pyside6_audit',
        'field_release_authorized': False,
        'pvs_cycles': len(rows),
        'pvs_authorized_cycles': len(active),
        'pvs_guard_revoked_zero_pid_udp_cycles': len(denied),
        'bridge_and_console_matched_statuses': len(trace),
        'console_guard_revoked_statuses': len(ui_denied),
        'scope': 'one host, synthetic magnetic/sonar/AMD inputs, native PVS; no PC104, physical survey or AUV',
        'source_sha256': {
            **{SOURCES[key]: digest for key, digest in summary['source_sha256'].items()},
            **snapshot['source_sha256'],
        },
        'evidence_sha256': {
            str(path.relative_to(ROOT)): sha(path)
            for path in (csv_path, trace_path, bridge_trace_path, summary_path, screenshot, SNAPSHOT)
        },
        'audit_script_sha256': sha(Path(__file__)),
    }


def main() -> None:
    report = audit()
    if OUT.exists() and json.loads(OUT.read_text(encoding='utf-8')) != report:
        raise SystemExit('pinned current-source audit changed; create a new version')
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({name: report[name] for name in (
        'pvs_cycles', 'pvs_guard_revoked_zero_pid_udp_cycles',
        'bridge_and_console_matched_statuses', 'console_guard_revoked_statuses',
        'field_release_authorized')}, ensure_ascii=False))


if __name__ == '__main__':
    main()

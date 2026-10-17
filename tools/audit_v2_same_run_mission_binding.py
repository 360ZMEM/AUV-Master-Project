#!/usr/bin/env python3
"""Pin a new same-run audit after static prior mission/target ID binding."""

from __future__ import annotations

import json
from pathlib import Path

import audit_v2_same_run_static_gate as base


base.RUN = base.ROOT / 'AUV-Master-Mag/results/v2/operator_chain/same_run_static_mission_binding_20260927'
base.SNAPSHOT = base.DATA / 'inspection_v2_static_target_mission_binding_20260927.json'
OUT = base.DATA / 'inspection_v2_same_run_mission_binding_20260927.json'


def main() -> None:
    report = base.audit()
    report['role'] = 'mission_bound_current_source_single_synthetic_operator_chain_audit'
    report['parent_audit_script_sha256'] = base.sha(Path(base.__file__))
    report['audit_script_sha256'] = base.sha(Path(__file__))
    if OUT.exists() and json.loads(OUT.read_text(encoding='utf-8')) != report:
        raise SystemExit('pinned mission-binding audit changed; create a new version')
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({name: report[name] for name in (
        'pvs_cycles', 'pvs_guard_revoked_zero_pid_udp_cycles',
        'bridge_and_console_matched_statuses', 'console_guard_revoked_statuses',
        'field_release_authorized')}, ensure_ascii=False))


if __name__ == '__main__':
    main()

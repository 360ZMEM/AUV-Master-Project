#!/usr/bin/env python3
"""Inventory local raw-vs-derived physical evidence for v2 field release.

This is a scoped filesystem audit, not proof that a reported physical test
occurred or that the current v2 stack is certified for an AUV deployment.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'AUV-Master-Mag/docs/v2/publication/fwhm_v2_experiment_results/data'
RAW_GROUPS = {
    'tmr_aruco_joint_freehand_record': (
        'hardware_wrappers/fangkong_adc/raw_data/1783235358_205719.npz',
        'hardware_wrappers/fangkong_adc/raw_data/relative_pose_log.txt',
    ),
    'measured_magnetic_background_noise': (
        'hardware_wrappers/fangkong_adc/raw_data/1780675809_291477.npz',
        'hardware_wrappers/fangkong_adc/raw_data/1780676130_241387.npz',
    ),
    'pc104_watchdog_fault_trial': (
        'results/control/pc104_fault_injection_formal_v2_20260822/fault_timeline.csv',
        'results/control/pc104_fault_injection_formal_v2_20260822/status.json',
    ),
    'pc104_firmware_echo_timing': (
        'results/control/pc104_udp_timing_echo_300s_20260822/udp_timing_samples.csv',
        'results/control/pc104_udp_timing_echo_300s_20260822/status.json',
    ),
    'pc104_ros_cross_layer_fault_trial': (
        'results/control/pc104_cross_layer_fault_sync_20260822_225436/status.json',
        'results/control/pc104_cross_layer_fault_sync_20260822_225436/summary.json',
    ),
}
DERIVED = {
    'tmr_replay_report': 'AUV-Master-Mag/docs/v2/TMR_JOINT_REPLAY.md',
    'pc104_fault_report': 'docs/real_deployment/15_pc104_fault_injection_and_layered_safety.md',
    'pc104_fault_derived_summary': 'docs/thesis/figures/hardware/pc104_fault_injection/fault_derived_summary.json',
    'pc104_fault_derived_trials': 'docs/thesis/figures/hardware/pc104_fault_injection/fault_trial_metrics.csv',
    'pc104_timing_report': 'docs/thesis/figures/hardware/pc104_timing/report.md',
    'pc104_timing_derived_summary': 'docs/thesis/figures/hardware/pc104_timing/firmware_echo_summary.json',
    'sonar_bag_inventory': 'AUV-Master-Mag/docs/v2/publication/fwhm_v2_experiment_results/data/field_sonar_evidence_inventory.json',
    'v2_same_run_synthetic_audit': 'AUV-Master-Mag/docs/v2/publication/fwhm_v2_experiment_results/data/inspection_v2_same_run_operator_chain_20260927.json',
}


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def inspect(path: Path) -> dict:
    if not path.is_file():
        return {'present': False, 'sha256': None, 'bytes': None}
    return {'present': True, 'sha256': sha(path), 'bytes': path.stat().st_size}


def audit(raw_root: Path) -> dict:
    raw = {
        name: {relative: inspect(raw_root / relative) for relative in paths}
        for name, paths in RAW_GROUPS.items()
    }
    derived = {name: {'path': relative, **inspect(ROOT / relative)}
               for name, relative in DERIVED.items()}
    group_complete = {name: all(item['present'] for item in files.values())
                      for name, files in raw.items()}
    sonar_messages = None
    sonar_quality_messages = None
    approved_sonar_calibrations = None
    sonar_path = ROOT / DERIVED['sonar_bag_inventory']
    if sonar_path.is_file():
        sonar = json.loads(sonar_path.read_text(encoding='utf-8'))
        sonar_messages = sonar.get('cable_sonar_observation_messages')
        sonar_quality_messages = sonar.get('sonar_quality_messages')
        approved_sonar_calibrations = sonar.get('physically_approved_sonar_calibrations')
    report = {
        'role': 'scoped_v2_field_evidence_source_inventory',
        'raw_root': str(raw_root.resolve()),
        'field_release_authorized': False,
        'raw_groups': raw,
        'raw_group_complete': group_complete,
        'derived_local': derived,
        'local_sonar_target_message_count': sonar_messages,
        'local_sonar_quality_message_count': sonar_quality_messages,
        'local_physically_approved_sonar_calibration_count': approved_sonar_calibrations,
        'interpretation': {
            'pc104_history': 'Derived reports describe earlier physical zero-actuator and timing tests; missing source bundles cannot be replayed here and did not run the current v2 inspection stack.',
            'magnetic_history': 'The TMR-ArUco report audits incomplete freehand sweeps; it is neither a controlled full-width calibration nor a target-cable identity test.',
            'field_gate': 'A physical target cue, synchronized magnetic scans, vehicle coast/corridor measurements and current-v2-to-PC104 same-run receipt still require separate evidence.',
        },
        'audit_script_sha256': sha(Path(__file__)),
    }
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raw-root', type=Path, default=ROOT,
                        help='root under which historical raw bundle relative paths can be mounted')
    parser.add_argument('--output-json', type=Path, default=OUT / 'inspection_v2_field_source_readiness_20260927.json')
    args = parser.parse_args()
    report = audit(args.raw_root)
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'raw_group_complete': report['raw_group_complete'],
                      'derived_present': sum(v['present'] for v in report['derived_local'].values()),
                      'field_release_authorized': False}, ensure_ascii=False))


if __name__ == '__main__':
    main()

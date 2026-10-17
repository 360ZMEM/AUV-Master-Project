#!/usr/bin/env python3
"""Compute descriptive field-bundle metrics; never grant deployment approval.

Requires the structural preflight to pass. Metrics are observations for a
reviewer, not statistical confidence bounds, source authentication or a safety
decision. Use independent full-mission hold-outs for acceptance.
"""

from __future__ import annotations

import argparse
from bisect import bisect_left, bisect_right
from collections import defaultdict
import csv
import json
import math
from pathlib import Path

try:
    from . import preflight_v2_inspection_field_packages as preflight
except ImportError:  # Running this file directly from tools/.
    import preflight_v2_inspection_field_packages as preflight


def rows(manifest_dir: Path, case: dict, role: str) -> list[dict]:
    path = Path(case['exports'][role]['path']).expanduser()
    if not path.is_absolute():
        path = manifest_dir / path
    with path.open(newline='', encoding='utf-8') as stream:
        return list(csv.DictReader(stream))


def true(value: str) -> bool:
    return preflight.boolean(value)


def interpolate_truth(samples: list[dict], t: float) -> float | None:
    if len(samples) == 1:
        return float(samples[0]['true_target_y_m'])
    if t < float(samples[0]['time_s']) or t > float(samples[-1]['time_s']):
        return None
    for left, right in zip(samples, samples[1:]):
        t0, t1 = float(left['time_s']), float(right['time_s'])
        if t0 <= t <= t1:
            y0, y1 = float(left['true_target_y_m']), float(right['true_target_y_m'])
            return y1 if t1 == t0 else y0 + (y1 - y0) * (t - t0) / (t1 - t0)
    return None


def observed_zero_suffix(samples: list[dict], value_column: str, after_s: float) -> dict:
    """Describe the final recorded zero run; one last zero is not a run."""
    tail = [row for row in samples if float(row['time_s']) >= after_s]
    start = len(tail)
    while start > 0 and float(tail[start - 1][value_column]) == 0:
        start -= 1
    suffix = tail[start:]
    times = [float(row['time_s']) for row in suffix]
    duration = times[-1] - times[0] if times else 0.0
    return {
        'post_fault_rows': len(tail),
        'zero_suffix_rows': len(suffix),
        'zero_suffix_duration_s': duration,
        'zero_suffix_max_gap_s': max((right - left for left, right in zip(times, times[1:])),
                                 default=None),
        'first_observed_zero_suffix_delay_s':
            times[0] - after_s if len(suffix) >= 2 and duration > 0 else None,
    }


def correlate_pc104_receipts(udp: list[dict], receipts: list[dict], *,
                             receipt_mode: str, max_lag_s: float, clock_error_s: float,
                             fault_time_s: float | None) -> tuple[dict, list[dict]]:
    """Pair checksum-valid receipts or board logs with sent $CKTH frames.

    A unique frame number within the declared time window is required. This
    verifies consistency of exports; raw packet and board-log provenance is
    still a separate physical review.
    """
    indexed = defaultdict(list)
    for index, row in enumerate(udp):
        indexed[int(row['frame_number'])].append((float(row['time_s']), index, float(row['main_motor_rpm'])))
    times = {frame: [entry[0] for entry in entries] for frame, entries in indexed.items()}
    used, unmatched, ambiguous, value_mismatch, matched_after_fault = set(), 0, 0, 0, 0
    delays, paired_commands = [], []
    for row in receipts:
        frame, received = int(row['frame_number']), float(row['time_s'])
        entries = indexed.get(frame, [])
        frame_times = times.get(frame, [])
        start = bisect_left(frame_times, received - max_lag_s - clock_error_s)
        stop = bisect_right(frame_times, received + clock_error_s)
        candidates = [entry for entry in entries[start:stop] if entry[1] not in used]
        if not candidates:
            unmatched += 1
            continue
        if len(candidates) != 1:
            ambiguous += 1
            continue
        sent, index, commanded = candidates[0]
        used.add(index)
        delays.append(received - sent)
        if (receipt_mode == 'board_command_log'
                and float(row['main_motor_rpm']) != commanded):
            value_mismatch += 1
        paired_commands.append({
            'time_s': row['time_s'],
            'main_motor_rpm': (row['main_motor_rpm'] if receipt_mode == 'board_command_log'
                               else str(commanded)),
        })
        if fault_time_s is not None and received >= fault_time_s:
            matched_after_fault += 1
    return {
        'pc104_receipts': len(receipts),
        'matched_pc104_receipts': len(delays),
        'unmatched_pc104_receipts': unmatched,
        'ambiguous_pc104_receipts': ambiguous,
        'matched_command_rpm_mismatches': value_mismatch,
        'matched_post_fault_pc104_receipts': matched_after_fault,
        'pc104_command_rpm_source': ('board_receive_log' if receipt_mode == 'board_command_log'
                                     else 'matched_original_udp_frame'),
        'maximum_observed_tx_to_receipt_record_delay_s': max(delays) if delays else None,
    }, paired_commands


def target_metrics(base: Path, case: dict) -> dict:
    decision = rows(base, case, 'target_decision')
    truth = rows(base, case, 'independent_truth')
    identity = rows(base, case, 'identity')
    errors = []
    missing_truth = 0
    for row in decision:
        if not (true(row['lateral_valid']) and true(row['target_confirmed'])):
            continue
        reference = interpolate_truth(truth, float(row['time_s']))
        if reference is None:
            missing_truth += 1
        else:
            errors.append(abs(float(row['lateral_y_m']) - reference))
    seen_valid = False
    cue_loss = None
    for row in identity:
        if true(row['valid']):
            seen_valid = True
        elif seen_valid:
            cue_loss = float(row['time_s'])
            break
    after_loss = ([row for row in decision if float(row['time_s']) >= cue_loss]
                  if cue_loss is not None else [])
    revoke = (next((float(row['time_s']) for row in after_loss
                    if not true(row['autonomous_allowed'])), None)
              if cue_loss is not None else None)
    return {
        'case_id': case['case_id'], 'kind': case['kind'],
        'decision_rows': len(decision),
        'target_confirmed_rows': sum(true(row['target_confirmed']) for row in decision),
        'task_complete_ever': any(true(row['task_complete']) for row in decision),
        'depth_published_rows': sum(true(row['depth_published']) for row in decision),
        'lateral_error_samples_with_truth': len(errors),
        'lateral_error_samples_without_truth': missing_truth,
        'lateral_mae_m': sum(errors) / len(errors) if errors else None,
        'lateral_max_error_m': max(errors) if errors else None,
        'cue_loss_time_s': cue_loss,
        'identity_last_time_s': float(identity[-1]['time_s']),
        'identity_last_valid': true(identity[-1]['valid']),
        'decision_last_time_s': float(decision[-1]['time_s']),
        'post_cue_loss_decision_rows': len(after_loss),
        'first_observed_autonomy_revoke_delay_s':
            revoke - cue_loss if revoke is not None else None,
        'post_cue_loss_autonomous_rows':
            sum(true(row['autonomous_allowed']) for row in after_loss),
        'post_cue_loss_last_autonomous_allowed':
            true(after_loss[-1]['autonomous_allowed']) if after_loss else None,
        'post_cue_loss_autonomy_reenabled': any(
            true(right['autonomous_allowed']) and not true(left['autonomous_allowed'])
            for left, right in zip(after_loss, after_loss[1:])),
        'post_cue_loss_completion_rows':
            sum(true(row['task_complete']) for row in after_loss),
        'post_cue_loss_target_confirmed_rows':
            sum(true(row['target_confirmed']) for row in after_loss),
    }


def execution_metrics(base: Path, case: dict, *, receipt_mode: str,
                      max_receipt_lag_s: float, clock_error_s: float) -> dict:
    streams = {role: rows(base, case, role) for role in preflight.EXECUTION_ROLES}
    faults = streams['fault_events']
    loss = next((float(row['time_s']) for row in faults
                 if row['event'].strip().lower() == 'uplink_loss'), None)
    result = {'case_id': case['case_id'], 'kind': case['kind'],
              'uplink_loss_time_s': loss,
              'uplink_recovery_observed': any(
                  row['event'].strip().lower() in ('uplink_restored', 'uplink_recovered')
                  for row in faults),
              'minimum_observed_clearance_m':
                  min(float(row['clearance_m']) for row in streams['boundary'])}
    correlation, paired_commands = correlate_pc104_receipts(
        streams['udp_downlink'], streams['pc104_receipt'],
        receipt_mode=receipt_mode, max_lag_s=max_receipt_lag_s,
        clock_error_s=clock_error_s, fault_time_s=loss)
    result.update(correlation)
    if loss is None:
        return result
    for role, column in (('ros_setpoint', 'target_speed_mps'),
                         ('udp_downlink', 'main_motor_rpm'),
                         ('pc104_receipt', 'main_motor_rpm')):
        series = paired_commands if role == 'pc104_receipt' else streams[role]
        for name, value in observed_zero_suffix(series, column, loss).items():
            result[f'{role}_{name}'] = value
        result[f'{role}_post_fault_nonzero_rows'] = sum(
            float(row[column]) != 0 for row in series if float(row['time_s']) >= loss)
        result[f'{role}_last_sample_time_s'] = float(series[-1]['time_s']) if series else None
        result[f'{role}_last_value'] = float(series[-1][column]) if series else None
    motion = [row for row in streams['vehicle_motion']
              if loss <= float(row['time_s']) <= loss + 60.0]
    result['motion_60s_observed_rows'] = len(motion)
    if motion:
        x0, y0 = float(motion[0]['x_m']), float(motion[0]['y_m'])
        result['motion_60s_observed_duration_s'] = (
            float(motion[-1]['time_s']) - float(motion[0]['time_s']))
        result['motion_60s_displacement_m'] = math.hypot(
            float(motion[-1]['x_m']) - x0, float(motion[-1]['y_m']) - y0)
        result['motion_60s_path_length_m'] = sum(math.hypot(
            float(right['x_m']) - float(left['x_m']),
            float(right['y_m']) - float(left['y_m']))
            for left, right in zip(motion, motion[1:]))
        result['motion_60s_last_ground_speed_mps'] = float(motion[-1]['ground_speed_mps'])
    return result


def analyze(manifest_path: Path) -> dict:
    gate = preflight.audit(manifest_path)
    if not gate['preflight_passed']:
        return {'analysis_ready': False, 'field_release_authorized': False,
                'preflight_blockers': gate['blockers']}
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    base = manifest_path.resolve().parent
    target = [target_metrics(base, case) for case in manifest['target_package']['cases']]
    execution = [execution_metrics(
        base, case, receipt_mode=manifest['receipt_mode'],
        max_receipt_lag_s=float(manifest['max_receipt_lag_s']),
        clock_error_s=float(manifest['clock_alignment']['measured_max_error_ms']) / 1000)
        for case in manifest['execution_package']['cases']]
    blockers, observed_red_flags = [], []
    for case in target:
        if case['kind'] == 'cue_loss' and case['cue_loss_time_s'] is None:
            blockers.append(f"{case['case_id']}: no observed cue-loss transition")
        if case['kind'] == 'cue_loss' and case['post_cue_loss_decision_rows'] < 2:
            blockers.append(f"{case['case_id']}: fewer than two decisions after cue loss")
        if case['kind'] == 'cue_loss' and (case['identity_last_valid'] or
                case['identity_last_time_s'] < case['decision_last_time_s']):
            blockers.append(f"{case['case_id']}: cue loss not observed through decision end")
        if case['lateral_error_samples_without_truth']:
            blockers.append(f"{case['case_id']}: confirmed lateral output lacks overlapping truth")
        if case['kind'] == 'neighbor' and case['task_complete_ever']:
            observed_red_flags.append(f"{case['case_id']}: neighbor case reported task complete")
        if case['kind'] == 'neighbor' and case['target_confirmed_rows']:
            observed_red_flags.append(f"{case['case_id']}: neighbor case confirmed the target")
        if case['depth_published_rows']:
            observed_red_flags.append(f"{case['case_id']}: depth published in lateral-only acceptance package")
        if case['kind'] == 'cue_loss' and case['post_cue_loss_completion_rows']:
            observed_red_flags.append(f"{case['case_id']}: completion reported after sustained cue loss")
        if case['kind'] == 'cue_loss' and case['post_cue_loss_target_confirmed_rows']:
            observed_red_flags.append(f"{case['case_id']}: target remained confirmed after sustained cue loss")
        if case['kind'] == 'cue_loss' and case['post_cue_loss_last_autonomous_allowed'] is True:
            observed_red_flags.append(f"{case['case_id']}: autonomous authority still allowed at record end")
        if case['kind'] == 'cue_loss' and case['post_cue_loss_autonomy_reenabled']:
            observed_red_flags.append(f"{case['case_id']}: autonomous authority reenabled during sustained cue loss")
    for case in execution:
        if case['unmatched_pc104_receipts'] or case['ambiguous_pc104_receipts']:
            blockers.append(f"{case['case_id']}: PC104 receipts cannot be uniquely linked to UDP frames")
        if case['matched_command_rpm_mismatches']:
            observed_red_flags.append(
                f"{case['case_id']}: board-side command RPM differs from matched UDP command")
        if case['kind'] == 'uplink_loss' and case['uplink_loss_time_s'] is None:
            blockers.append(f"{case['case_id']}: no uplink_loss event")
        if case['kind'] == 'uplink_loss' and case['uplink_recovery_observed']:
            blockers.append(f"{case['case_id']}: sustained uplink-loss case includes recovery")
        if case['kind'] == 'uplink_loss' and case['uplink_loss_time_s'] is not None:
            if any(case[f'{role}_post_fault_rows'] < 2
                   for role in ('ros_setpoint', 'udp_downlink', 'pc104_receipt')):
                blockers.append(f"{case['case_id']}: fewer than two post-fault output samples")
            if case['matched_post_fault_pc104_receipts'] < 2:
                blockers.append(f"{case['case_id']}: fewer than two matched post-fault PC104 receipts")
            for role in ('ros_setpoint', 'udp_downlink', 'pc104_receipt'):
                if case[f'{role}_last_value'] is None:
                    continue
                if case[f'{role}_last_value'] != 0:
                    observed_red_flags.append(
                        f"{case['case_id']}: {role} still nonzero at record end")
                elif case[f'{role}_first_observed_zero_suffix_delay_s'] is None:
                    observed_red_flags.append(
                        f"{case['case_id']}: {role} has no multi-sample zero suffix")
            if (case.get('motion_60s_observed_rows', 0) < 2
                    or case.get('motion_60s_observed_duration_s', 0) <= 0):
                blockers.append(f"{case['case_id']}: insufficient post-fault vehicle motion")
            boundary = rows(base, next(entry for entry in manifest['execution_package']['cases']
                                   if entry['case_id'] == case['case_id']), 'boundary')
            if not any(float(row['time_s']) > case['uplink_loss_time_s'] for row in boundary):
                blockers.append(f"{case['case_id']}: missing post-fault boundary clearance")
    return {
        'analysis_ready': not blockers,
        'observed_protocol_red_flags_clear': not observed_red_flags and not blockers,
        'field_release_authorized': False,
        'manifest_sha256': gate['manifest_sha256'],
        'preflight_script_sha256': gate['audit_script_sha256'],
        'analysis_script_sha256': preflight.sha(Path(__file__)),
        'clock_alignment_max_error_ms': manifest['clock_alignment']['measured_max_error_ms'],
        'receipt_mode': manifest['receipt_mode'],
        'target_cases': target,
        'execution_cases': execution,
        'analysis_blockers': blockers,
        'observed_protocol_red_flags': observed_red_flags,
        'interpretation': ('Descriptive observed metrics only. A zero suffix requires at least two '
                           'recorded samples for a delay; neither this nor clear protocol flags '
                           'proves vehicle stop. Sample gaps, clock error, independent truth, source provenance, '
                           'held-out mission split and site-approved limits require human review.'),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, default=preflight.TEMPLATE)
    parser.add_argument('--output-json', type=Path, required=True)
    args = parser.parse_args()
    report = analyze(args.manifest)
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n',
                                encoding='utf-8')
    print(json.dumps({'analysis_ready': report['analysis_ready'],
                      'field_release_authorized': False}, ensure_ascii=False))
    raise SystemExit(0 if report['analysis_ready'] else 2)


if __name__ == '__main__':
    main()

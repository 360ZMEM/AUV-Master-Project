#!/usr/bin/env python3
"""Recompute robustness results from complete, frozen CSV evidence.

This checks evidence integrity, not universal inspection safety. Rejections
and failed missions remain explicit outcomes and are not converted to passes.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import itertools
import json
import math
from pathlib import Path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def yes(value):
    return value is True or value == 'True'


def close(a, b):
    return a is b if a is None or b is None else math.isclose(a, b, rel_tol=1e-8, abs_tol=1e-8)


def audit(directory):
    plan = json.loads((directory / 'plan.json').read_text())
    manifest = json.loads((directory / 'manifest.json').read_text())
    summary = json.loads((directory / 'summary.json').read_text())
    errors = []
    def check(condition, message):
        if not condition:
            errors.append(message)
    check(manifest.get('sources_unchanged') is True, 'runtime source freeze not confirmed')
    check(sha(directory / 'plan.json') == manifest['plan_sha256'], 'plan hash mismatch')
    for name, expected in manifest['artifacts'].items():
        check((directory / name).is_file() and sha(directory / name) == expected, f'artifact mismatch: {name}')
    index_path = directory / 'source_snapshot_index.json'
    if index_path.exists():
        index = json.loads(index_path.read_text())
        check(set(index) == set(plan['sources']), 'source snapshot graph mismatch')
        for source, item in index.items():
            snapshot = directory / item['snapshot']
            check(snapshot.is_file() and sha(snapshot) == item['sha256'] == plan['sources'][source], f'source snapshot mismatch: {source}')
    expected_grid = set(itertools.product([c['name'] for c in plan['cases']], plan['methods'], plan['seeds']))
    observed_grid = [(s['case'], s['method'], s['seed']) for s in summary]
    check(len(observed_grid) == len(set(observed_grid)), 'duplicate runs')
    check(set(observed_grid) == expected_grid, 'incomplete or unexpected experiment grid')
    lo, hi = plan['core_interval_m']
    audited = []
    for s in summary:
        name = s['trace']
        path = directory / name
        check(sha(path) == s['trace_sha256'], f'{name}: summary trace hash mismatch')
        with path.open(newline='') as stream:
            rows = list(csv.DictReader(stream))
        check(bool(rows), f'{name}: empty trace')
        if not rows:
            continue
        numeric = ['time_s', 'x_m', 'y_m', 'nav_x_m', 'nav_y_m', 'true_target_y_m',
                   'true_offset_m', 'encoded_rpm', 'speed_command_mps', 'actual_navigation_error_m']
        check(all(math.isfinite(float(r[k])) for r in rows for k in numeric), f'{name}: nonfinite required observation')
        check(all(close(float(r['true_offset_m']), abs(float(r['y_m'])-float(r['true_target_y_m']))) for r in rows), f'{name}: incorrect truth offset')
        dt = plan['mission_dt_s']
        check(all(close(float(b['time_s'])-float(a['time_s']), dt) for a,b in zip(rows, rows[1:])), f'{name}: timestamp gap')
        core = [r for r in rows if r['mode'] == 'track' and lo <= float(r['x_m']) <= hi]
        track = [r for r in rows if r['mode'] == 'track']
        mean = sum(float(r['true_offset_m']) for r in core)/len(core) if core else None
        maximum = max((float(r['true_offset_m']) for r in core), default=None)
        coverage = bool(track and min(float(r['x_m']) for r in track) <= lo and max(float(r['x_m']) for r in track) >= hi)
        completed = yes(rows[-1]['endpoint_complete'])
        quality = bool(completed and coverage and mean is not None and mean <= plan['true_mean_limit_m'] and maximum <= plan['true_max_limit_m'])
        center_error = max((abs(float(r['estimated_cable_y_m'])-float(r['true_target_y_m'])) for r in rows if yes(r['lateral_valid'])), default=None)
        # Old development traces predate the explicit named-target flag.
        named = lambda r: yes(r.get('named_target_authorized', r['mode'] == 'track'))
        false_geometry = any(named(r) and yes(r['lateral_valid']) and abs(float(r['estimated_cable_y_m'])-float(r['true_target_y_m'])) > .5 for r in rows)
        tail = [r for r in rows if r['mode'] == 'hold']
        zero_tail = bool(tail and all(float(r['encoded_rpm']) == 0 and float(r['speed_command_mps']) == 0 for r in tail))
        if tail:
            check(close(float(tail[-1]['time_s'])-float(tail[0]['time_s']), 60.), f'{name}: missing full 60s withdrawal tail')
            check(zero_tail, f'{name}: nonzero withdrawal command')
            check(len(tail) == round(60. / dt) + 1, f'{name}: incorrect withdrawal sample count')
            check(rows[-len(tail):] == tail, f'{name}: withdrawal did not remain latched')
        nav_bound = all(float(r['actual_navigation_error_m']) <= plan['supervisor_contract']['navigation_position_bound_m'] + 1e-9 for r in rows)
        if s['method'] == 'supervised':
            for r in rows:
                b = r.get('robustness_true_offset_upper_bound_m')
                # The bound has meaning only when the assumed navigation
                # and external anchor bounds hold. Never certify a hidden bias.
                if b and float(r['actual_navigation_error_m']) <= plan['supervisor_contract']['navigation_position_bound_m']:
                    check(float(r['true_offset_m']) <= float(b)+1e-8, f'{name}: conditional triangle bound violated')
        check(not any(yes(r['depth_valid']) for r in rows), f'{name}: unauthorized depth publication')
        for key, value in dict(core_samples=len(core), core_true_mae_m=mean, core_true_max_m=maximum,
                core_coverage=coverage, completed=completed, true_quality_passed=quality,
                false_completion=completed and not quality, released_center_max_error_m=center_error,
                false_geometry_publication=false_geometry, zero_withdrawal_tail=zero_tail,
                navigation_bound_actually_satisfied=nav_bound).items():
            check(close(s.get(key), value), f'{name}: summary mismatch {key}')
        first_track = next((float(r['time_s']) for r in rows if r['mode']=='track'), None)
        withdrawal = float(tail[0]['time_s']) if tail else None
        event = next((float(r['time_s']) for r in rows if yes(r['fault_active'])), None)
        for key,value in dict(ticks=len(rows), duration_s=float(rows[-1]['time_s']),
                first_track_s=first_track, withdrawal_time_s=withdrawal, fault_start_s=event,
                withdrawal_delay_s=None if withdrawal is None or event is None else withdrawal-event).items():
            check(close(s.get(key),value),f'{name}: summary mismatch {key}')
        if tail:
            displacement=math.hypot(float(tail[-1]['x_m'])-float(tail[0]['x_m']),float(tail[-1]['y_m'])-float(tail[0]['y_m']))
            check(close(s['post_withdrawal_motion_m'],displacement),f'{name}: incorrect withdrawal displacement')
        if 'geometric_route_completed' in s:
            geometry=yes(rows[-1]['geometric_route_complete'])
            geometry_quality=bool(geometry and coverage and mean is not None and mean <= plan['true_mean_limit_m'] and maximum <= plan['true_max_limit_m'])
            check(s['geometric_route_completed']==geometry and s['geometric_true_quality_passed']==geometry_quality,f'{name}: geometric-only completion mismatch')
            if tail and s['method'] in ['supervised','diagnostic_only']:
                check(yes(rows[-1].get('robustness_higher_level_recovery_requested')),f'{name}: missing finite Hold recovery request')
        if s['method'] == 'diagnostic_only':
            check(not any(yes(r.get('named_target_authorized')) or yes(r.get('named_target_completed')) for r in rows), f'{name}: anonymous anomaly received named authority')
            check(not completed, f'{name}: anonymous route set generic endpoint_complete')
        audited.append(dict(case=s['case'], method=s['method'], seed=s['seed'],
            completed=completed, true_quality_passed=quality, false_geometry_publication=false_geometry,
            false_completion=completed and not quality, withdrawal=bool(tail), zero_tail=zero_tail,
            core_samples=len(core), core_true_mae_m=mean, core_true_max_m=maximum, core_coverage=coverage,
            navigation_bound_actually_satisfied=nav_bound))
    counts = {}
    for method in plan['methods']:
        subset = [r for r in audited if r['method'] == method]
        counts[method] = dict(runs=len(subset), **{k:sum(bool(r[k]) for r in subset) for k in
            ['completed', 'true_quality_passed', 'false_geometry_publication', 'false_completion', 'withdrawal', 'zero_tail']})
    return dict(schema_version=1, split=plan['split'], evidence_integrity_passed=not errors,
        errors=errors, counts=counts, runs=audited, plan_sha256=sha(directory / 'plan.json'),
        manifest_sha256=sha(directory / 'manifest.json'),
        scope='finite native-PVS toy conditions; integrity is not field or universal performance acceptance')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run-dir', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    result = audit(args.run_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ['evidence_integrity_passed', 'errors', 'counts']}))
    if not result['evidence_integrity_passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()

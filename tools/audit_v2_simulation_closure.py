#!/usr/bin/env python3
"""Freeze and audit the bounded magnetic/PID/native-PVS simulation result."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
CORE_START_M, CORE_END_M = 5., 75.
MEAN_ERROR_LIMIT_M, MAX_ERROR_LIMIT_M = 1., 2.


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def audit(summary: dict, directory: Path) -> dict:
    path = directory / summary['source']
    with path.open(newline='') as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == summary['ticks'] and rows
    for row in rows:
        assert all(math.isfinite(float(row[k])) for k in (
            'time_s', 'x_m', 'y_m', 'heading_deg', 'speed_mps',
            'magnetic_nt', 'estimated_cable_y_m', 'encoded_rpm'))
        assert -260. <= float(row['x_m']) <= 110. and -20. <= float(row['y_m']) <= 20.
        assert row['depth_valid'] == 'False'
    times = [float(r['time_s']) for r in rows]
    assert all(abs(b-a-.25) < 1e-8 for a, b in zip(times, times[1:]))
    endpoints = [i for i, r in enumerate(rows) if r['endpoint_complete'] == 'True']
    modes = {r['mode'] for r in rows}
    result = {'case': summary['case'], 'seed': summary['seed'], 'sample_count': len(rows),
              'duration_s': times[-1], 'trace': str(path.relative_to(directory.parent)),
              'trace_sha256': sha(path), 'all_samples_finite': True,
              'simulated_sample_gap_s': .25, 'depth_published': False}
    if summary['case'] == 'no_source':
        assert not summary['completed'] and not endpoints
        assert modes == {'search', 'hold'}
        assert not any(r['lateral_valid'] == 'True' for r in rows)
        assert rows[-1]['reason'] == 'flythrough_no_detection'
        assert float(rows[-1]['encoded_rpm']) == 0.
        result.update(no_source_rejected=True, completed=False,
                      terminal_reason=rows[-1]['reason'])
        return result
    assert summary['completed'] and endpoints == [len(rows)-1]
    assert {'search', 'confirm', 'track'} <= modes and 'hold' not in modes
    assert float(rows[-1]['encoded_rpm']) == 0.
    inspect = [r for r in rows if r['mode'] == 'track' and float(r['x_m']) >= 0.]
    assert inspect and float(inspect[0]['x_m']) <= CORE_START_M and float(inspect[-1]['x_m']) >= CORE_END_M
    assert all(float(b['x_m']) > float(a['x_m']) for a, b in zip(inspect, inspect[1:]))
    # Include every Track sample in the spatial interval, including lateral
    # rejoin corrections. Stage-label selection would undercount large errors.
    core = [r for r in rows if r['mode'] == 'track'
            and CORE_START_M <= float(r['x_m']) <= CORE_END_M]
    assert core and all(float(r['encoded_rpm']) > 0. for r in core)
    assert all(abs(float(b['time_s'])-float(a['time_s'])-.25) < 1e-8
               for a,b in zip(core,core[1:]))
    errors = [abs(float(r['y_m'])-6.) for r in core]
    mean_error, max_error = sum(errors)/len(errors), max(errors)
    assert mean_error <= MEAN_ERROR_LIMIT_M and max_error <= MAX_ERROR_LIMIT_M
    confirmed = next(r for r in rows if r['lateral_valid'] == 'True')
    center_error = abs(float(confirmed['estimated_cable_y_m'])-6.)
    assert center_error <= .5
    assert math.hypot(float(rows[-1]['x_m'])-80.,
                      float(rows[-1]['y_m'])-float(rows[-1]['estimated_cable_y_m'])) <= 1.5
    result.update(completed=True, core_coverage_verified=True,
                  core_interval_m=[CORE_START_M, CORE_END_M], core_sample_count=len(core),
                  core_mean_true_offset_m=mean_error, core_max_true_offset_m=max_error,
                  estimated_center_error_m=center_error, endpoint_command_zero=True,
                  first_inspection_x_m=float(inspect[0]['x_m']),
                  last_inspection_x_m=float(inspect[-1]['x_m']))
    return result


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--raw-dir', type=Path, required=True)
    p.add_argument('--output-dir', type=Path, required=True)
    args = p.parse_args()
    raw = args.raw_dir.resolve()
    runs, versions = [], []
    for name in ('native_pvs', 'native_seed102_103'):
        directory = raw / name
        manifest = json.loads((directory/'manifest.json').read_text())
        assert manifest['config']['flythrough_policy']['rejoin_runin_m'] == 20.
        versions.append(manifest['config']['source_sha256'])
        for relative, expected in versions[-1].items():
            assert sha(ROOT/relative) == expected, relative
        runs.extend(audit(s, directory) for s in json.loads((directory/'summary.json').read_text()))
    assert versions[0] == versions[1]
    assert {(r['case'], r['seed']) for r in runs} == {
        (case, seed) for case in ('wire', 'dipole', 'no_source') for seed in (101, 102, 103)}
    history = json.loads((raw/'historical_route_recheck.json').read_text())
    assert history['normal_steady_completion_count'] == history['normal_steady_run_count'] == 6
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=False)
    for name in ('native_pvs', 'native_seed102_103'):
        shutil.copytree(raw/name, output/name)
        shutil.copyfile(raw/f'{name}.log', output/f'{name}.log')
    shutil.copyfile(raw/'historical_route_recheck.json', output/'historical_route_recheck.json')
    sources = dict(versions[0])
    for directory in ('AUV-Master-Mag/src', 'brain_linux/src/auv_controller/auv_controller', 'common'):
        paths = (ROOT/directory).glob('*.py') if directory == 'common' else (ROOT/directory).rglob('*.py')
        for file in paths:
            sources[str(file.relative_to(ROOT))] = sha(file)
    for relative in ('tools/audit_v2_simulation_closure.py',
                     'tests/test_v2_simulation_closure.py',
                     'AUV-Master-Mag/tools/run_v2_inspection_closed_loop.py',
                     'sim_holoocean/interfaces/ocean_current_model.py',
                     'brain_linux/config/params.yaml'):
        sources[relative] = sha(ROOT/relative)
    for relative, expected in sources.items():
        target = output/'source_snapshot'/relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT/relative, target)
        assert sha(target) == expected
    external_root = ROOT.parent/'PythonVehicleSimulator-master'
    external_hashes = {}
    for file in sorted((external_root/'src/python_vehicle_simulator').rglob('*.py')):
        relative = file.relative_to(external_root)
        target = output/'external_pvs_snapshot'/relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(file, target)
        external_hashes[str(relative)] = sha(target)
    for file in sorted(external_root.glob('*LICENSE*')):
        if file.is_file():
            shutil.copyfile(file, output/'external_pvs_snapshot'/file.name)
    payload = {
        'schema_version': 1,
        'scope': 'bounded offline magnetic/PID/72-byte-codec/native-PVS simulation; not ROS timing or field release',
        'user_completion_criterion': 'reliable constrained simulation plus visualization and defense assets',
        'simulation_checks_passed': True,
        'positive_completion_count': sum(r['completed'] for r in runs),
        'no_source_rejection_count': sum(r.get('no_source_rejected', False) for r in runs),
        'seeds': [101, 102, 103], 'seed_101_role': 'initial verification',
        'seeds_102_103_role': 'repeatability checks after core interval was declared',
        'envelope': {'known_isolated_straight_source': True, 'current_speed_mps': 0.,
                     'nominal_route_m': [0., 80.], 'verified_core_m': [5., 75.],
                     'edge_buffers_m': 5., 'nominal_speed_mps': .3,
                     'noise_sigma_nt': .03, 'field_models': ['wire_p_half', 'dipole_p_one'],
                     'magnetic_vertical_scale_m': 3., 'scalar_envelope_only': True,
                     'rejoin_runin_m': 20., 'side_hint_interval_m': [2.,8.],
                     'ideal_navigation': True, 'prior_lateral_bias_m': 6.,
                     'scan_start_m': [-250., -15.], 'scan_end_m': [-80., 15.],
                     'boundary_xy_m': [[-270.,-30.],[120.,-30.],[120.,30.],[-270.,30.]],
                     'boundary_margin_m': 10., 'endpoint_tolerance_m': 1.5,
                     'core_mean_error_limit_m': MEAN_ERROR_LIMIT_M,
                     'core_max_error_limit_m': MAX_ERROR_LIMIT_M,
                     'depth_release_enabled': False},
        'runs': runs, 'source_sha256': sources,
        'external_pvs_source_root': str(external_root),
        'external_pvs_source_sha256': external_hashes,
        'historical_ros_chain_role': 'separate fixed-version evidence; six steady-current normal tasks complete',
        'real_time_scheduling_verified': False, 'field_release_authorized': False,
        'artifact_sha256': {str(f.relative_to(output)): sha(f)
                            for f in sorted(output.rglob('*')) if f.is_file()},
    }
    (output/'audit.json').write_text(json.dumps(payload, indent=2, ensure_ascii=False)+'\n')
    print(json.dumps({k: payload[k] for k in ('simulation_checks_passed',
          'positive_completion_count','no_source_rejection_count','field_release_authorized')}))


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Native-PVS, packet-encoded diagnostic of opt-in oblique cable inspection.

This does not exercise ROS scheduling, watchdog, or hardware. It isolates
mission geometry, magnetic gating, protocol quantization and PVS dynamics.
"""
from __future__ import annotations

import argparse
import csv
from dataclasses import replace
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'AUV-Master-Mag/src'),
                str(ROOT / 'AUV-Master-Mag/tools'), str(ROOT / 'brain_linux/src/auv_controller')]
from auv_mag_tracking.api import CableMap, MagneticInput, NavigationInput
from auv_mag_tracking.v2 import FlythroughInspectionPipelineV2, write_experiment_manifest
from auv_controller.pid_controller import PIDController
from common.protocol import (KEY_BOTTOM, KEY_CONTROL_MODE_BYTE, KEY_LEFT,
                             KEY_ORIENTATION_DEG, KEY_RIGHT, KEY_TARGET_DEPTH_M,
                             KEY_THRUST, KEY_TOP,
                             build_downlink_packet_from_payload, parse_downlink_packet)
from sim_holoocean.interfaces.pvs_sim_wrapper import PVSSimWrapper
from run_v2_inspection_closed_loop import config as load_inspection_config


SOURCE_FILES = (
    'tools/probe_v2_flythrough_pvs.py',
    'AUV-Master-Mag/src/auv_mag_tracking/v2/flythrough.py',
    'AUV-Master-Mag/src/auv_mag_tracking/v2/pipeline.py',
    'AUV-Master-Mag/src/auv_mag_tracking/v2/fwhm.py',
    'AUV-Master-Mag/src/auv_mag_tracking/v2/config.py',
    'AUV-Master-Mag/src/auv_mag_tracking/v2/types.py',
    'brain_linux/src/auv_controller/auv_controller/pid_controller.py',
    'sim_holoocean/interfaces/pvs_sim_wrapper.py',
)


def manifest_config(cases: list[str], seed_start: int, seeds: int, max_time_s: float) -> dict:
    try:
        commit = subprocess.check_output(
            ['git', '-c', f'safe.directory={ROOT}', 'rev-parse', 'HEAD'],
            cwd=ROOT, text=True, stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        commit = None
    return {
        'cases': cases, 'seed_start': seed_start, 'seeds': seeds,
        'max_time_s': max_time_s, 'pvs_dt_s': .05, 'mission_dt_s': .25,
        'speed_feedforward_b': 40., 'simulator_heading_unwrap': True,
        'not_ros_or_hardware_acceptance': True, 'repository_commit': commit,
        'source_sha256': {
            name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
            for name in SOURCE_FILES
        },
    }


def run(case: str, seed: int, out: Path, max_time_s: float = 1600.) -> dict:
    if case not in {'wire', 'no_source', 'dipole'}:
        raise ValueError(case)
    base = load_inspection_config()
    setting = replace(base,
        search=replace(base.search, velocity_mps=.3),
        cross_scan=replace(base.cross_scan, velocity_mps=.3, alignment_speed_mps=.3),
        tracking=replace(base.tracking, nominal_speed_mps=.3, minimum_speed_mps=.3),
        inspection=replace(base.inspection,
                           maximum_scan_duration_s=450., maximum_observation_age_s=1000.,
                           maximum_observation_distance_m=250., boundary_stop_margin_m=10.),
    )
    boundary = np.array([[-270., -30.], [120., -30.], [120., 30.], [-270., 30.]])
    pipeline = FlythroughInspectionPipelineV2(
        object(), CableMap(np.array([[0., 0.], [80., 0.]])),
        v2_config=setting, search_boundary_xy_m=boundary,
    )
    params = yaml.safe_load((ROOT / 'brain_linux/config/params.yaml').read_text())
    controller = PIDController(params['control'], params['limits'], params['mappers'])
    controller._pid.speed_ff_b = 40.
    start = pipeline._fly_start
    direction = pipeline._fly_end - start
    initial_heading = math.degrees(math.atan2(direction[1], direction[0]))
    plant_cfg = {'simulation': {'dt': .05}, 'pvs': {
        'control_mode': 'depthHeadingAutopilot', 'autonomy_motion_model': 'native',
        'initial_depth_m': 10., 'initial_heading_deg': initial_heading,
        'initial_speed_mps': .3, 'initial_rpm': 0., 'reference_rpm': 0.,
        'current_speed_mps': 0.,
    }}
    plant = PVSSimWrapper(config=plant_cfg, scenario_cfg={}, agent_name='auv').open()
    plant.eta[:2] = start
    rng = np.random.default_rng(seed)
    rows = []
    try:
        for index in range(round(max_time_s / .25)):
            t = index * .25
            x, y = map(float, plant.eta[:2])
            heading = math.degrees(float(plant.eta[5]))
            speed = float(plant.nu[0])
            q = ((y - 6.) / 3.) ** 2
            exponent = .5 if case == 'wire' else 1.
            value = 1. + (0. if case == 'no_source' else 20. / (1. + q) ** exponent) + rng.normal(0., .03)
            nav = NavigationInput(t, np.array([x, y, -10.]), heading, speed_mps=speed, position_std_m=.1)
            mag = MagneticInput(t, np.tile([value, 0., 0.], (4, 1)), 50.)
            tracking, guidance = pipeline.step_with_guidance(nav, mag, target_depth_m=10.)
            state = {'x': x, 'y': y, 'z': -float(plant.eta[2]), 'u': speed,
                     'v': float(plant.nu[1]), 'w': float(plant.nu[2]),
                     'roll': float(plant.eta[3]), 'pitch': float(plant.eta[4]),
                     'yaw': float(plant.eta[5]), 'p': float(plant.nu[3]),
                     'q': float(plant.nu[4]), 'r': float(plant.nu[5]),
                     'depth': float(plant.eta[2])}
            thrust = (controller.compute(state, {
                'target_speed_mps': guidance.speed_mps,
                'target_heading_rad': math.radians(guidance.desired_heading_deg),
                'target_depth_m': guidance.target_depth_m, 'dt': .25,
            }).thrust_percent if guidance.speed_mps > 0 and tracking.mode in
                ('search', 'confirm', 'track', 'reacquire') else 0.)
            payload = {KEY_CONTROL_MODE_BYTE: 238,
                       KEY_ORIENTATION_DEG: guidance.desired_heading_deg % 360.,
                       KEY_TARGET_DEPTH_M: guidance.target_depth_m, KEY_THRUST: thrust,
                       KEY_RIGHT: 0., KEY_LEFT: 0., KEY_TOP: 0., KEY_BOTTOM: 0.}
            packet = build_downlink_packet_from_payload(payload, main_motor_rpm_scale=15.)
            decoded = parse_downlink_packet(packet, main_motor_rpm_scale=15.)
            # Convert only the simulator target to the nearest equivalent yaw.
            # The physical packet remains the deployed 0..360-degree format.
            heading_ref = heading + (decoded.orientation_deg - heading + 180.) % 360. - 180.
            plant.set_reference(depth_m=decoded.target_depth_m,
                                heading_rad=math.radians(heading_ref),
                                propeller_rpm=max(0., decoded.main_motor_rpm))
            for _ in range(5):
                plant.step([0, 0, 0, 0, 0])
            assert np.isfinite([*plant.eta, *plant.nu, *plant.u_actual]).all()
            assert tracking.burial_depth_m is None
            rows.append({
                'time_s': t, 'x_m': x, 'y_m': y, 'heading_deg': heading,
                'speed_mps': speed, 'magnetic_nt': value, 'mode': tracking.mode,
                'stage': tracking.diagnostics.get('tracking_stage', ''),
                'reason': tracking.diagnostics.get('continuity_reason', ''),
                'lateral_valid': bool(tracking.diagnostics.get('lateral_valid')),
                'depth_valid': bool(tracking.diagnostics.get('depth_valid')),
                'fwhm_width_m': tracking.diagnostics.get('fwhm_width_m'),
                'fwhm_left_x_m': tracking.diagnostics.get('fwhm_left_x_m'),
                'fwhm_right_x_m': tracking.diagnostics.get('fwhm_right_x_m'),
                'fwhm_half_level_nt': tracking.diagnostics.get('fwhm_half_level_nt'),
                'fwhm_peak_x_m': tracking.diagnostics.get('fwhm_peak_x_m'),
                'fwhm_reasons': '|'.join(tracking.diagnostics.get('fwhm_reason_codes', [])),
                'fwhm_model_residual': tracking.diagnostics.get('fwhm_model_residual'),
                'fwhm_competing_residual': tracking.diagnostics.get('fwhm_competing_model_residual'),
                'inspection_declared_residual': tracking.diagnostics.get('fwhm_inspection_declared_shape_residual'),
                'inspection_competing_residual': tracking.diagnostics.get('fwhm_inspection_competing_shape_residual'),
                'fwhm_shape_support_widths': tracking.diagnostics.get('fwhm_shape_support_widths'),
                'estimated_cable_y_m': float(tracking.estimated_cable_xy_m[1]),
                'endpoint_complete': bool(tracking.diagnostics.get('endpoint_complete')),
                'encoded_rpm': decoded.main_motor_rpm,
            })
            if tracking.diagnostics.get('endpoint_complete') or tracking.mode == 'hold':
                break
    finally:
        plant.close()
    out.mkdir(parents=True, exist_ok=True)
    name = f'{case}_seed_{seed}'
    with (out / f'{name}.csv').open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0].keys())
        writer.writeheader(); writer.writerows(rows)
    track_rows = [row for row in rows if row['mode'] == 'track' and row['stage'] == 'inspect_along_cable']
    confirmed = next((row for row in rows if row['lateral_valid']), None)
    return {
        'case': case, 'seed': seed, 'ticks': len(rows), 'duration_s': rows[-1]['time_s'],
        'completed': rows[-1]['endpoint_complete'],
        'ever_confirm': any(row['mode'] == 'confirm' for row in rows),
        'ever_track': any(row['mode'] == 'track' for row in rows),
        'lateral_valid': any(row['lateral_valid'] for row in rows),
        'depth_published': any(row['depth_valid'] for row in rows),
        'first_hold_reason': next((row['reason'] for row in rows if row['mode'] == 'hold'), None),
        'final_xy_m': [rows[-1]['x_m'], rows[-1]['y_m']],
        'max_abs_y_m': max(abs(row['y_m']) for row in rows),
        'tracking_mae_m': float(np.mean([abs(row['y_m'] - 6.) for row in track_rows])) if track_rows else None,
        'confirmed_lateral_error_m': None if confirmed is None else abs(confirmed['estimated_cable_y_m'] - 6.),
        'declared_shape_residual': None if confirmed is None else confirmed['fwhm_model_residual'],
        'competing_shape_residual': None if confirmed is None else confirmed['fwhm_competing_residual'],
        'equal_dof_declared_residual': None if confirmed is None else confirmed['inspection_declared_residual'],
        'equal_dof_competing_residual': None if confirmed is None else confirmed['inspection_competing_residual'],
        'shape_support_widths': None if confirmed is None else confirmed['fwhm_shape_support_widths'],
        'final_fwhm_reasons': next((row['fwhm_reasons'] for row in reversed(rows) if row['fwhm_reasons']), ''),
        'source': f'{name}.csv', 'native_pvs': True, 'protocol_encoded': True,
        'not_system_acceptance': True,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cases', nargs='+', default=['wire', 'dipole', 'no_source'])
    parser.add_argument('--seed-start', type=int, default=101)
    parser.add_argument('--seeds', type=int, default=1)
    parser.add_argument('--max-time-s', type=float, default=1600.)
    parser.add_argument('--output-dir', type=Path,
                        default=ROOT / 'AUV-Master-Mag/results/v2/inspection_flythrough_pvs_20260926')
    args = parser.parse_args()
    results = []
    for case in args.cases:
        for seed in range(args.seed_start, args.seed_start + args.seeds):
            result = run(case, seed, args.output_dir, args.max_time_s)
            results.append(result)
            print(json.dumps(result), flush=True)
    summary_path = args.output_dir / 'summary.json'
    summary_path.write_text(json.dumps(results, indent=2) + '\n')
    write_experiment_manifest(
        args.output_dir, experiment='inspection_flythrough_native_pvs_diagnostic',
        config=manifest_config(args.cases, args.seed_start, args.seeds, args.max_time_s),
        artifact_paths=[summary_path, *args.output_dir.glob('*.csv'),
                        *args.output_dir.glob('pvs_flythrough_profile_and_track.*')],
        repository_root=ROOT,
    )


if __name__ == '__main__':
    main()

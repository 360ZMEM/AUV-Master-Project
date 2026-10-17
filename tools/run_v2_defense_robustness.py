#!/usr/bin/env python3
"""Paired native-PVS robustness evidence for a straight toy target.

No ROS timing or hardware claim. Truth generates sensors and is used only by
the independent evaluator; the optional supervisor sees public inputs/outputs
and a separately declared surveyed target interval.
"""
from __future__ import annotations

import argparse
import csv
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict, dataclass, replace
import hashlib
import inspect
import json
import math
import platform
import shutil
from pathlib import Path
import sys
import time

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import probe_v2_flythrough_pvs as base
from auv_mag_tracking.v2 import FlythroughConfig, FlythroughInspectionPipelineV2
from auv_mag_tracking.v2.robustness_supervisor import RobustnessContract, RobustnessSupervisor
from auv_mag_tracking.v2.robustness_pipeline import DirectionalRejoinContract, DirectionalRejoinPipelineV2
from python_vehicle_simulator.lib.gnc import Rzyx


@dataclass(frozen=True)
class Case:
    name: str
    family: str = 'wire'
    current_mps: float = 0.0
    current_amplitude_mps: float = 0.0
    current_period_s: float = 60.0
    current_step_mps: float = 0.0
    position_noise_std_m: float = 0.0
    heading_bias_deg: float = 0.0
    velocity_bias_mps: float = 0.0
    position_bias_m: float = 0.0
    position_jump_m: float = 0.0
    position_drift_mps: float = 0.0
    neighbor_distance_m: float = 3.0
    neighbor_amplitude_ratio: float = 0.0
    neighbor_phase_deg: float = 0.0
    field_exponent: float | None = None
    primary_scale: float = 1.0
    magnetic_step_gain: float = 1.0


CASES = {c.name: c for c in [
    Case('clean_wire'), Case('clean_dipole', family='dipole'),
    Case('steady_plus', current_mps=0.03), Case('steady_minus', current_mps=-0.03),
    Case('periodic_current', current_amplitude_mps=0.02),
    Case('step_current', current_step_mps=-0.05),
    Case('strong_current', current_mps=0.12),
    Case('navigation_noise', position_noise_std_m=0.03, heading_bias_deg=0.5, velocity_bias_mps=0.005),
    Case('navigation_hidden_bias', position_bias_m=0.7),
    Case('navigation_jump', position_jump_m=0.8),
    Case('navigation_drift', position_drift_mps=0.03),
    Case('weak_neighbor', neighbor_amplitude_ratio=0.05),
    Case('fused_neighbor', neighbor_amplitude_ratio=0.45),
    Case('equal_close_neighbor', neighbor_distance_m=1.5, neighbor_amplitude_ratio=1.0),
    Case('opposed_neighbor', neighbor_amplitude_ratio=0.45, neighbor_phase_deg=180.0),
    Case('quadrature_neighbor', neighbor_amplitude_ratio=0.45, neighbor_phase_deg=90.0),
    Case('combined_bounded', current_mps=0.03, position_noise_std_m=0.03,
         heading_bias_deg=0.5, velocity_bias_mps=0.005, neighbor_amplitude_ratio=0.05),
    Case('unknown_shape', field_exponent=0.7),
    Case('no_source', primary_scale=0.0),
    Case('magnetic_gain_step', magnetic_step_gain=0.5),
]}

POLICY = FlythroughConfig(
    side_hint_required=True, side_hint_min_m=2.0, side_hint_max_m=8.0,
    side_hint_source='synthetic_test_fixture', minimum_halfmax_tail_m=7.0,
    rejoin_runin_m=20.0, route_quality_mean_limit_m=1.0,
    route_quality_max_limit_m=2.0, route_quality_min_samples=200,
)
CONTRACT = RobustnessContract()
REJOIN = DirectionalRejoinContract()


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def source_manifest():
    paths = [ROOT / p for p in base.SOURCE_FILES]
    paths += [Path(__file__), ROOT / 'AUV-Master-Mag/src/auv_mag_tracking/v2/robustness_supervisor.py',
              ROOT / 'common/protocol.py', ROOT / 'brain_linux/config/params.yaml']
    pvs_root = Path(inspect.getfile(base.PVSSimWrapper.step.__globals__['remus100'])).parents[1]
    paths += list(pvs_root.rglob('*.py'))
    for directory in ['AUV-Master-Mag/src/auv_mag_tracking', 'common', 'sim_holoocean/interfaces',
                      'brain_linux/src/auv_controller/auv_controller']:
        paths += list((ROOT / directory).rglob('*.py'))
    paths += [ROOT / 'algorithm/auv_pid_controller.py',
              ROOT / 'AUV-Master-Mag/tools/run_v2_inspection_closed_loop.py']
    return {str(p.resolve()): digest(p) for p in sorted(set(paths))}


def run_case(case: Case, seed: int, method: str, directory: Path, max_time_s: float):
    started = time.perf_counter()
    cfg = base.load_inspection_config()
    cfg = replace(cfg,
        search=replace(cfg.search, velocity_mps=0.3),
        cross_scan=replace(cfg.cross_scan, velocity_mps=0.3, alignment_speed_mps=0.3),
        tracking=replace(cfg.tracking, nominal_speed_mps=0.3, minimum_speed_mps=0.3),
        inspection=replace(cfg.inspection, maximum_scan_duration_s=450.0,
                           maximum_observation_age_s=1000.0, maximum_observation_distance_m=250.0,
                           boundary_stop_margin_m=10.0))
    boundary = np.array([[-270., -30.], [120., -30.], [120., 30.], [-270., 30.]])
    pipeline_class = FlythroughInspectionPipelineV2 if method == 'legacy' else DirectionalRejoinPipelineV2
    pipeline = pipeline_class(object(), base.CableMap(np.array([[0., 0.], [80., 0.]])),
        v2_config=cfg, search_boundary_xy_m=boundary, flythrough_config=POLICY)
    supervisor = RobustnessSupervisor(CONTRACT if method == 'supervised' else
        replace(CONTRACT, enforce_target_anchor=False, target_anchor_center_m=0.0)) if method in ('supervised', 'diagnostic_only') else None
    params = yaml.safe_load((ROOT / 'brain_linux/config/params.yaml').read_text())
    controller = base.PIDController(params['control'], params['limits'], params['mappers'])
    controller._pid.speed_ff_b = 40.0
    direction = pipeline._fly_end - pipeline._fly_start
    yaw0 = math.degrees(math.atan2(direction[1], direction[0]))
    plant = base.PVSSimWrapper(config={'simulation': {'dt': 0.05}, 'pvs': {
        'control_mode': 'depthHeadingAutopilot', 'autonomy_motion_model': 'native',
        'initial_depth_m': 10., 'initial_heading_deg': yaw0, 'initial_speed_mps': 0.3,
        'initial_rpm': 0., 'reference_rpm': 0., 'current_speed_mps': 0.,
    }}, scenario_cfg={}, agent_name='auv').open()
    plant.eta[:2] = pipeline._fly_start
    # Apply the same measured yaw bias at the local PVS heading feedback,
    # preserving physical eta for the dynamics integrator. The legacy fixture
    # had ideal local feedback even when guidance navigation was perturbed.
    original_autopilot = plant._depth_heading_autopilot_control
    def observed_autopilot():
        physical_eta = plant.eta
        observed_eta = physical_eta.copy()
        observed_eta[5] += math.radians(case.heading_bias_deg)
        plant.eta = observed_eta
        try:
            return original_autopilot()
        finally:
            plant.eta = physical_eta
    plant._depth_heading_autopilot_control = observed_autopilot
    # Independent streams keep the magnetic draw index identical between
    # methods even when navigation disturbances are absent or rejected early.
    mag_rng = np.random.default_rng(seed)
    nav_rng = np.random.default_rng(seed + 100000)
    rows = []
    first_track = fault_start = withdrawn = None
    last_xy = None
    distance = 0.0
    try:
        for index in range(round(max_time_s / 0.25)):
            t = index * 0.25
            x, y = map(float, plant.eta[:2])
            heading = math.degrees(float(plant.eta[5]))
            speed = float(plant.nu[0])
            if first_track is not None and fault_start is None and x >= 10.0:
                fault_start = t
            active_fault = fault_start is not None
            elapsed_fault = 0.0 if fault_start is None else t - fault_start
            flow = case.current_mps
            if active_fault:
                flow += case.current_step_mps + case.current_amplitude_mps * math.sin(2.0 * math.pi * elapsed_fault / case.current_period_s)
            plant.vehicle.V_c = abs(flow)
            plant.vehicle.beta_c = math.copysign(math.pi / 2.0, flow) if flow else 0.0
            ground_velocity = Rzyx(*plant.eta[3:6]) @ plant.nu[:3]
            exponent = case.field_exponent or (0.5 if case.family == 'wire' else 1.0)
            primary = case.primary_scale * 20.0 / (1.0 + ((y - 6.0) / 3.0) ** 2) ** exponent
            neighbor = 20.0 * case.neighbor_amplitude_ratio / (1.0 + ((y - 6.0 - case.neighbor_distance_m) / 3.0) ** 2) ** exponent
            # Synthetic coherent envelopes, including opposing/quadrature
            # phases. This is not a full three-dimensional armored-cable model.
            phasor = primary + neighbor * complex(math.cos(math.radians(case.neighbor_phase_deg)), math.sin(math.radians(case.neighbor_phase_deg)))
            gain = case.magnetic_step_gain if active_fault else 1.0
            value = 1.0 + gain * abs(phasor) + mag_rng.normal(0.0, 0.03)
            noise = np.clip(nav_rng.normal(0.0, case.position_noise_std_m, 2),
                            -2.0 * case.position_noise_std_m, 2.0 * case.position_noise_std_m)
            bias_y = case.position_bias_m
            if active_fault:
                bias_y += case.position_jump_m + elapsed_fault * case.position_drift_mps
            reported = np.array([x + noise[0], y + noise[1] + bias_y, -10.0])
            nav = base.NavigationInput(t, reported, heading + case.heading_bias_deg,
                speed_mps=speed, position_std_m=0.03, heading_std_deg=0.25)
            nav.ground_velocity_ned_mps = ground_velocity + np.array([0., case.velocity_bias_mps, 0.])
            nav.ground_velocity_std_mps = 0.005
            nav.ground_velocity_frame_valid = True
            mag = base.MagneticInput(t, np.tile([value, 0., 0.], (4, 1)), 50.)
            tracking, guidance = pipeline.step_with_guidance(nav, mag, target_depth_m=10.0)
            raw_mode = tracking.mode
            if supervisor is not None:
                measured_profile = np.column_stack([pipeline._scan_x_m, pipeline._scan_envelope_nt])
                tracking, guidance = supervisor.apply(nav, mag, tracking, guidance, profile=measured_profile)
            if tracking.mode == 'track' and first_track is None:
                first_track = t
            if tracking.mode == 'hold' and withdrawn is None:
                withdrawn = t
            state = dict(x=float(reported[0]), y=float(reported[1]), z=-float(plant.eta[2]), u=speed,
                         v=float(plant.nu[1]), w=float(plant.nu[2]), roll=float(plant.eta[3]),
                         pitch=float(plant.eta[4]), yaw=math.radians(nav.heading_deg),
                         p=float(plant.nu[3]), q=float(plant.nu[4]), r=float(plant.nu[5]), depth=float(plant.eta[2]))
            thrust = controller.compute(state, dict(target_speed_mps=guidance.speed_mps,
                target_heading_rad=math.radians(guidance.desired_heading_deg),
                target_depth_m=guidance.target_depth_m, dt=0.25)).thrust_percent if guidance.speed_mps > 0 and tracking.mode in ('search', 'confirm', 'track') else 0.0
            payload = {base.KEY_CONTROL_MODE_BYTE: 238, base.KEY_ORIENTATION_DEG: guidance.desired_heading_deg % 360.,
                       base.KEY_TARGET_DEPTH_M: guidance.target_depth_m, base.KEY_THRUST: thrust,
                       base.KEY_RIGHT: 0., base.KEY_LEFT: 0., base.KEY_TOP: 0., base.KEY_BOTTOM: 0.}
            packet = base.build_downlink_packet_from_payload(payload, main_motor_rpm_scale=15.)
            decoded = base.parse_downlink_packet(packet, main_motor_rpm_scale=15.)
            heading_ref = heading + (decoded.orientation_deg - heading + 180.) % 360. - 180.
            if last_xy is not None:
                distance += float(np.linalg.norm(np.array([x, y]) - last_xy))
            last_xy = np.array([x, y])
            d = tracking.diagnostics
            row = dict(time_s=t, x_m=x, y_m=y, nav_x_m=float(reported[0]), nav_y_m=float(reported[1]),
                       true_target_y_m=6.0, true_offset_m=abs(y - 6.0),
                       actual_navigation_error_m=float(np.linalg.norm(reported[:2] - [x, y])),
                       true_current_mps=flow, magnetic_nt=value, heading_deg=heading, actual_speed_mps=speed,
                       mode=tracking.mode, raw_mode=raw_mode, stage=d.get('tracking_stage', ''),
                       reason=d.get('continuity_reason', ''), estimated_cable_y_m=float(tracking.estimated_cable_xy_m[1]),
                       lateral_valid=bool(d.get('lateral_valid')), depth_valid=bool(d.get('depth_valid')),
                       endpoint_complete=bool(d.get('endpoint_complete')), encoded_rpm=decoded.main_motor_rpm,
                       geometric_route_complete=bool(d.get('geometric_route_complete', d.get('endpoint_complete'))),
                       speed_command_mps=guidance.speed_mps, fault_active=active_fault,
                       named_target_authorized=bool(d.get('named_target_authorized', method in ('legacy', 'directional_only') and tracking.mode == 'track')),
                       named_target_completed=bool(d.get('endpoint_complete') and d.get('named_target_authorized', method in ('legacy', 'directional_only'))),
                       proxy_y_mps=float(pipeline._fly_current_xy[1]))
            for key in ('robustness_position_increment_residual_m', 'robustness_navigation_window_residual_m',
                        'robustness_navigation_window_limit_m', 'robustness_target_anchor_residual_m',
                        'robustness_target_anchor_limit_m', 'robustness_profile_window_residual',
                        'robustness_profile_residual', 'robustness_expected_magnetic_nt',
                        'robustness_profile_supported', 'robustness_profile_monitor_status',
                        'robustness_true_offset_upper_bound_m', 'robustness_mean_offset_upper_bound_m',
                        'robustness_max_offset_upper_bound_m', 'robustness_conditional_quality_valid'):
                row[key] = d.get(key)
            row['robustness_disturbance_change_mps'] = d.get('robustness_disturbance_change_mps')
            row['robustness_disturbance_change_limit_mps'] = d.get('robustness_disturbance_change_limit_mps')
            for key in ('robustness_hold_elapsed_s', 'robustness_hold_budget_s',
                        'robustness_higher_level_recovery_requested'):
                row[key] = d.get(key)
            row['selected_rejoin_runin_m'] = pipeline._fly_active_runin_m
            rows.append(row)
            assert np.isfinite([*plant.eta, *plant.nu, *plant.u_actual, guidance.speed_mps]).all()
            assert tracking.burial_depth_m is None and not d.get('depth_valid')
            plant.set_reference(depth_m=decoded.target_depth_m, heading_rad=math.radians(heading_ref),
                                propeller_rpm=max(0., decoded.main_motor_rpm))
            for _ in range(5):
                plant.step([0, 0, 0, 0, 0])
            if row['geometric_route_complete'] or (withdrawn is not None and t - withdrawn >= 60.0):
                break
    finally:
        plant.close()
    directory.mkdir(parents=True, exist_ok=True)
    name = f'{case.name}_{method}_seed{seed}.csv'
    path = directory / name
    with path.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0].keys()); writer.writeheader(); writer.writerows(rows)
    core = [r for r in rows if r['mode'] == 'track' and 5.0 <= r['x_m'] <= 75.0]
    mean = float(np.mean([r['true_offset_m'] for r in core])) if core else None
    maximum = max((r['true_offset_m'] for r in core), default=None)
    track = [r for r in rows if r['mode'] == 'track']
    coverage = bool(track and min(r['x_m'] for r in track) <= 5.0 and max(r['x_m'] for r in track) >= 75.0)
    completed = bool(rows[-1]['endpoint_complete'])
    geometric_completed = bool(rows[-1]['geometric_route_complete'])
    quality = bool(completed and coverage and mean is not None and mean <= 1.0 and maximum <= 2.0)
    released = [r for r in rows if r['lateral_valid']]
    center_max = max((abs(r['estimated_cable_y_m'] - 6.0) for r in released), default=None)
    false_geometry = bool(any(r['named_target_authorized'] and r['lateral_valid']
                              and abs(r['estimated_cable_y_m'] - 6.0) > 0.5 for r in rows))
    tail = [r for r in rows if withdrawn is not None and r['time_s'] >= withdrawn]
    zero_tail = bool(tail and all(r['encoded_rpm'] == 0.0 and r['speed_command_mps'] == 0.0 for r in tail))
    tail_motion = float(np.linalg.norm(np.array([tail[-1]['x_m'], tail[-1]['y_m']]) - [tail[0]['x_m'], tail[0]['y_m']])) if tail else None
    return dict(case=case.name, method=method, seed=seed, completed=completed,
        geometric_route_completed=geometric_completed,
        geometric_true_quality_passed=bool(geometric_completed and coverage and mean is not None and mean <= 1.0 and maximum <= 2.0),
        named_target_completed=bool(rows[-1]['named_target_completed']),
        true_quality_passed=quality, false_completion=bool(completed and not quality),
        false_geometry_publication=false_geometry, released_center_max_error_m=center_max,
        core_true_mae_m=mean, core_true_max_m=maximum, core_samples=len(core), core_coverage=coverage,
        first_track_s=first_track, fault_start_s=fault_start, withdrawal_time_s=withdrawn,
        withdrawal_delay_s=None if withdrawn is None or fault_start is None else withdrawn - fault_start,
        withdrawal_reason=next((r['reason'] for r in rows if r['mode'] == 'hold'), None),
        zero_withdrawal_tail=zero_tail, post_withdrawal_motion_m=tail_motion,
        upstream_recovery_requested=bool(rows[-1].get('robustness_higher_level_recovery_requested')),
        selected_rejoin_runin_m=pipeline._fly_active_runin_m,
        post_withdrawal_max_true_offset_m=max((r['true_offset_m'] for r in tail), default=None),
        navigation_bound_actually_satisfied=all(r['actual_navigation_error_m'] <= CONTRACT.navigation_position_bound_m + 1e-9 for r in rows),
        travelled_distance_m=distance, duration_s=rows[-1]['time_s'], ticks=len(rows),
        depth_publications=0, trace=name, trace_sha256=digest(path), wall_time_s=time.perf_counter() - started)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--cases', nargs='+', choices=CASES, default=list(CASES))
    p.add_argument('--methods', nargs='+', choices=['legacy', 'supervised', 'diagnostic_only', 'directional_only'], default=['legacy', 'supervised'])
    p.add_argument('--seeds', nargs='+', type=int, default=[401])
    p.add_argument('--split', choices=['development', 'held_out'], default='development')
    p.add_argument('--max-time-s', type=float, default=1600.)
    p.add_argument('--output-dir', type=Path, required=True)
    p.add_argument('--workers', type=int, default=1, help='independent OS processes; no realtime performance claim')
    args = p.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=False)
    sources = source_manifest()
    if args.workers < 1:
        p.error('--workers must be positive')
    import scipy
    plan = dict(schema_version=1, purpose='graduation defense robustness; not field deployment',
        split=args.split, cases=[asdict(CASES[n]) for n in args.cases], seeds=args.seeds, methods=args.methods,
        frozen_before_execution=True, flight_policy=asdict(POLICY), supervisor_contract=asdict(CONTRACT),
        directional_rejoin_contract=asdict(REJOIN),
        methods_contract={'legacy':'fixed 20m rejoin, legacy authorization',
            'supervised':'directional 20/5m rejoin plus external-anchor supervisor',
            'diagnostic_only':'directional rejoin and observable checks; no named-target authority',
            'directional_only':'directional rejoin without supervisor; geometric ablation'},
        max_time_s=args.max_time_s, mission_dt_s=0.25, plant_dt_s=0.05,
        core_interval_m=[5., 75.], true_mean_limit_m=1., true_max_limit_m=2.,
        navigation_noise='independent Gaussian clipped at +/-2 sigma per XY coordinate',
        multisource_model='coherent scalar-envelope phasor sum; not full 3-D armored-cable fields',
        heading_error_scope='same bias in guidance navigation and local PVS autopilot feedback; physical state unchanged',
        control_structure='legacy hybrid PID speed loop, encoded heading/depth references, PVS local depth/heading loop',
        pairing='same initial conditions, disturbance rule and random streams; sensor values diverge after different control actions',
        external_anchor='separate synthetic surveyed straight-target interval, constant 6+/-0.05m; no runtime truth input',
        workers=args.workers, environment={'python':sys.version,'platform':platform.platform(),
            'numpy':np.__version__,'scipy':scipy.__version__,'PyYAML':yaml.__version__},
        sources=sources)
    (args.output_dir / 'plan.json').write_text(json.dumps(plan, indent=2) + '\n')
    snapshot_index = {}
    for name,h in sources.items():
        path=Path(name)
        rel=Path('repo') / path.relative_to(ROOT) if path.is_relative_to(ROOT) else Path('external') / path.relative_to('/')
        dest=args.output_dir/'source_snapshot'/rel
        dest.parent.mkdir(parents=True,exist_ok=True); shutil.copyfile(path,dest)
        assert digest(dest)==h
        snapshot_index[name]={'snapshot':str(dest.relative_to(args.output_dir)),'sha256':h}
    (args.output_dir/'source_snapshot_index.json').write_text(json.dumps(snapshot_index,indent=2)+'\n')
    runs = []
    jobs=[(CASES[case],seed,method,args.output_dir,args.max_time_s) for case in args.cases for seed in args.seeds for method in args.methods]
    def record(result):
        runs.append(result)
        (args.output_dir / 'summary.json').write_text(json.dumps(runs, indent=2) + '\n')
        print(json.dumps(result), flush=True)
    if args.workers==1:
        for job in jobs:
            record(run_case(*job))
    else:
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            futures=[pool.submit(run_case,*job) for job in jobs]
            for future in as_completed(futures):
                record(future.result())
    assert source_manifest() == sources, 'sources changed while the experiment ran'
    manifest = dict(plan_sha256=digest(args.output_dir / 'plan.json'), sources_unchanged=True,
                    artifacts={f.name:digest(f) for f in args.output_dir.iterdir() if f.is_file()})
    (args.output_dir / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Diagnostic cable-inspection loop with protocol-encoded PID and native PVS.

This bypasses ROS scheduling/guard and is therefore not a system acceptance
test. It isolates propulsion calibration and mission geometry from DDS timing.
"""
from __future__ import annotations

import csv
from dataclasses import replace
import json
import math
from pathlib import Path
import sys

import numpy as np
import yaml
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'AUV-Master-Mag/src'),
                str(ROOT / 'AUV-Master-Mag/tools'), str(ROOT / 'brain_linux/src/auv_controller')]
from auv_mag_tracking.api import CableMap, MagneticInput, NavigationInput
from auv_mag_tracking.v2 import AuvMagTrackingPipelineV2
from auv_controller.pid_controller import PIDController
from common.protocol import (KEY_BOTTOM, KEY_CONTROL_MODE_BYTE, KEY_LEFT,
                             KEY_ORIENTATION_DEG, KEY_RIGHT, KEY_TARGET_DEPTH_M,
                             KEY_THRUST, KEY_TOP,
                             build_downlink_packet_from_payload, parse_downlink_packet)
from sim_holoocean.interfaces.pvs_sim_wrapper import PVSSimWrapper
from run_v2_inspection_closed_loop import config as load_inspection_config
from tools import thesis_plot_style as style


def run(feedforward_b: float, max_time_s: float = 900., *, stop_margin_m: float = 0.,
        unwrap_pvs_heading: bool = False, output_dir: Path | None = None) -> dict:
    config = load_inspection_config()
    config = replace(config, inspection=replace(config.inspection, boundary_stop_margin_m=stop_margin_m))
    boundary = np.array([[-30., -30.], [100., -30.], [100., 36.], [-30., 36.]])
    pipeline = AuvMagTrackingPipelineV2(
        object(), CableMap(np.array([[0., 0.], [60., 0.]])),
        v2_config=config, search_boundary_xy_m=boundary,
    )
    params = yaml.safe_load((ROOT / 'brain_linux/config/params.yaml').read_text())
    controller = PIDController(params['control'], params['limits'], params['mappers'])
    controller._pid.speed_ff_b = feedforward_b
    pvs_cfg = {'simulation': {'dt': .05}, 'pvs': {
        'control_mode': 'depthHeadingAutopilot', 'autonomy_motion_model': 'native',
        'initial_depth_m': 10., 'initial_heading_deg': 0., 'initial_speed_mps': .3,
        'initial_rpm': 0., 'reference_rpm': 0., 'current_speed_mps': 0.,
    }}
    plant = PVSSimWrapper(config=pvs_cfg, scenario_cfg={}, agent_name='auv').open()
    plant.eta[1] = -10.
    rng = np.random.default_rng(101)
    rows = []
    try:
        for index in range(round(max_time_s / .25)):
            t = index * .25
            x, y = map(float, plant.eta[:2]); heading = math.degrees(float(plant.eta[5]))
            u = float(plant.nu[0])
            value = 1. + 20. / math.sqrt(1. + ((y - 6.) / 3.) ** 2) + rng.normal(0., .03)
            nav = NavigationInput(t, np.array([x, y, -10.]), heading, speed_mps=u, position_std_m=.1)
            magnetic = MagneticInput(t, np.tile([value, 0., 0.], (4, 1)), 50.)
            tracking, guidance = pipeline.step_with_guidance(nav, magnetic, target_depth_m=10.)
            state = {'x': x, 'y': y, 'z': -float(plant.eta[2]), 'u': u,
                     'v': float(plant.nu[1]), 'w': float(plant.nu[2]),
                     'roll': float(plant.eta[3]), 'pitch': float(plant.eta[4]),
                     'yaw': float(plant.eta[5]), 'p': float(plant.nu[3]),
                     'q': float(plant.nu[4]), 'r': float(plant.nu[5]),
                     'depth': float(plant.eta[2])}
            if guidance.speed_mps <= 0 or not tracking.mode in ('search', 'confirm', 'track', 'reacquire'):
                thrust = 0.
            else:
                thrust = controller.compute(state, {
                    'target_speed_mps': guidance.speed_mps,
                    'target_heading_rad': math.radians(guidance.desired_heading_deg),
                    'target_depth_m': guidance.target_depth_m, 'dt': .25,
                }).thrust_percent
            payload = {KEY_CONTROL_MODE_BYTE: 238, KEY_ORIENTATION_DEG: guidance.desired_heading_deg % 360,
                       KEY_TARGET_DEPTH_M: guidance.target_depth_m, KEY_THRUST: thrust,
                       KEY_RIGHT: 0., KEY_LEFT: 0., KEY_TOP: 0., KEY_BOTTOM: 0.}
            packet = build_downlink_packet_from_payload(payload, main_motor_rpm_scale=15.)
            decoded = parse_downlink_packet(packet, main_motor_rpm_scale=15.)
            # The wire packet carries [0, 360) degrees. Native PVS expects a
            # continuous reference: 356 degrees otherwise commands a long
            # positive turn when the vehicle is near zero degrees.
            pvs_heading_deg = decoded.orientation_deg
            if unwrap_pvs_heading:
                pvs_heading_deg = heading + (pvs_heading_deg - heading + 180.) % 360. - 180.
            plant.set_reference(depth_m=decoded.target_depth_m,
                                heading_rad=math.radians(pvs_heading_deg),
                                propeller_rpm=max(0., decoded.main_motor_rpm))
            for _ in range(5): plant.step([0, 0, 0, 0, 0])
            assert np.isfinite([*plant.eta, *plant.nu, *plant.u_actual]).all()
            assert tracking.burial_depth_m is None
            rows.append({'time_s': t, 'x_m': x, 'y_m': y, 'heading_deg': heading,
                         'speed_mps': u, 'target_speed_mps': guidance.speed_mps,
                         'thrust_percent': thrust, 'encoded_rpm': decoded.main_motor_rpm,
                         'mode': tracking.mode,
                         'stage': tracking.diagnostics.get('tracking_stage', ''),
                         'reason': tracking.diagnostics.get('continuity_reason', ''),
                         'lateral_valid': bool(tracking.diagnostics.get('lateral_valid')),
                         'depth_valid': bool(tracking.diagnostics.get('depth_valid')),
                         'endpoint_complete': bool(tracking.diagnostics.get('endpoint_complete'))})
            if tracking.diagnostics.get('endpoint_complete'):
                break
    finally:
        plant.close()
    OUT = output_dir or ROOT / 'AUV-Master-Mag/results/v2/inspection_pvs_closed_loop_probe_20260926'
    OUT.mkdir(parents=True, exist_ok=True)
    name = 'baseline' if feedforward_b == 0 else ('buffered_feedforward' if stop_margin_m else 'feedforward')
    with (OUT / f'{name}.csv').open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0].keys())
        writer.writeheader(); writer.writerows(rows)
    hold_reasons = [r['reason'] for r in rows if r['mode'] == 'hold']
    return {'variant': name, 'feedforward_b': feedforward_b, 'stop_margin_m': stop_margin_m,
            'unwrap_pvs_heading': unwrap_pvs_heading,
            'ticks': len(rows),
            'duration_s': rows[-1]['time_s'], 'completed': rows[-1]['endpoint_complete'],
            'ever_confirm': any(r['mode'] == 'confirm' for r in rows),
            'ever_track': any(r['mode'] == 'track' for r in rows),
            'max_rpm': max(r['encoded_rpm'] for r in rows),
            'final_xy_m': [rows[-1]['x_m'], rows[-1]['y_m']],
            'max_abs_y_m': max(abs(r['y_m']) for r in rows),
            'first_hold_reason': hold_reasons[0] if hold_reasons else None,
            'final_inside_boundary': -30 <= float(rows[-1]['y_m']) <= 36,
            'source': f'{name}.csv', 'not_system_acceptance': True}


def main() -> None:
    results = [run(0.), run(40.), run(40., stop_margin_m=10.)]
    out = ROOT / 'AUV-Master-Mag/results/v2/inspection_pvs_closed_loop_probe_20260926'
    (out / 'summary.json').write_text(json.dumps(results, indent=2) + '\n')
    style.apply_thesis_style()
    fig, axes = plt.subplots(1, 2, figsize=style.figure_size(height=4.7), constrained_layout=True)
    colors = {'baseline': style.BASELINE_1, 'feedforward': style.PROPOSED,
              'buffered_feedforward': style.BASELINE_3}
    names = {'baseline': '原 PID 配置', 'feedforward': '独立航速前馈',
             'buffered_feedforward': '前馈＋10 m 停止缓冲'}
    for result in results:
        with (out / result['source']).open() as stream:
            rows = list(csv.DictReader(stream))
        x = np.array([float(row['x_m']) for row in rows])
        y = np.array([float(row['y_m']) for row in rows])
        t = np.array([float(row['time_s']) for row in rows])
        speed = np.array([float(row['speed_mps']) for row in rows])
        axes[0].plot(x, y, color=colors[result['variant']], lw=1.4, label=names[result['variant']])
        axes[0].scatter(x[0], y[0], color=colors[result['variant']], marker='o', s=25)
        axes[0].scatter(x[-1], y[-1], color=colors[result['variant']], marker='x', s=35)
        axes[1].plot(t, speed, color=colors[result['variant']], lw=1.4, label=names[result['variant']])
    axes[0].plot([0, 60], [0, 0], '--', color=style.NEUTRAL, lw=1, label='先验中心')
    axes[0].plot([0, 60], [6, 6], '-', color=style.REFERENCE, lw=1, label='电缆真值')
    axes[0].plot([-30,100,100,-30,-30],[-30,-30,36,36,-30],':',color=style.WARNING,lw=1,label='搜索边界')
    axes[0].set(xlabel='沿先验方向 / m', ylabel='横向位置 / m', title='(a) 原生 PVS 下的实际航迹')
    axes[0].set_xlim(-10, 75); axes[0].set_ylim(-42, 48)
    axes[0].legend(fontsize=7, ncol=3, loc='upper center', bbox_to_anchor=(.5, -.19))
    axes[0].grid(alpha=.25)
    axes[1].axhline(.3,ls='--',color=style.REFERENCE,lw=1,label='确认段目标速度')
    axes[1].set(xlabel='任务时间 / s', ylabel='实际前进速度 / (m/s)',
                title='(b) 前馈改善速度，仍未完成巡检', xlim=(0, 350))
    axes[1].legend(fontsize=7, ncol=2, loc='upper center', bbox_to_anchor=(.5, -.19))
    axes[1].grid(alpha=.25)
    style.save_figure(fig, out / 'pvs_closed_loop_counterexample')
    plt.close(fig)
    for result in results: print(json.dumps(result))


if __name__ == '__main__': main()

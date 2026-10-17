#!/usr/bin/env python3
"""Reproducible native-PVS envelope check for the installed inspection PID trace.

This is a diagnostic, not a closed-loop mission success test. It uses the same
15 RPM per thrust-percent protocol mapping and PVS autopilot that Mock AMD uses
for autonomous protocol packets. No network or hardware endpoint is opened.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
import sys

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sim_holoocean.interfaces.pvs_sim_wrapper import PVSSimWrapper
from tools import thesis_plot_style as style
TRACE = ROOT / 'AUV-Master-Mag/results/v2/inspection_ros_controller_installed_20260926/trajectory.json'
OUT = ROOT / 'AUV-Master-Mag/results/v2/inspection_pvs_propulsion_probe_20260926'
DT = 0.05
RPM_PER_PERCENT = 15.0


def simulate(rpm: int) -> dict:
    cfg = {
        'simulation': {'dt': DT},
        'pvs': {
            'control_mode': 'depthHeadingAutopilot',
            'autonomy_motion_model': 'native',
            'initial_depth_m': 10.0,
            'initial_heading_deg': 0.0,
            'initial_speed_mps': 0.3,
            'initial_rpm': rpm,
            'reference_rpm': rpm,
            'current_speed_mps': 0.0,
        },
    }
    wrapper = PVSSimWrapper(config=cfg, scenario_cfg={}, agent_name='auv').open()
    try:
        wrapper.set_reference(depth_m=10.0, heading_rad=0.0, propeller_rpm=rpm)
        for _ in range(round(60 / DT)):
            wrapper.step([0, 0, 0, 0, 0])
        speed = float(wrapper.nu[0])
        initial_heading = float(wrapper.eta[5])
        wrapper.set_reference(depth_m=10.0, heading_rad=math.radians(30), propeller_rpm=rpm)
        heading_series = []
        for _ in range(round(60 / DT)):
            wrapper.step([0, 0, 0, 0, 0])
            heading_series.append(math.degrees(float(wrapper.eta[5]) - initial_heading))
        return {
            'rpm': rpm,
            'steady_speed_mps': speed,
            'heading_30deg_step_after_20s_deg': heading_series[399],
            'heading_30deg_step_after_60s_deg': heading_series[-1],
            'heading_series_deg': heading_series,
            'final_depth_m': float(wrapper.eta[2]),
        }
    finally:
        wrapper.close()


def main() -> None:
    style.apply_thesis_style()
    trace = json.loads(TRACE.read_text())
    values = np.array([float(row['thrust_percent']) for row in trace if 'thrust_percent' in row])
    positive = values[values > 0]
    encoded_rpm = np.rint(np.maximum(0, values) * RPM_PER_PERCENT).astype(int)
    rpms = [0, 1, 10, 43, 75, 120, 180, 240, 300, 450, 600, 900]
    runs = [simulate(rpm) for rpm in rpms]
    assert max(encoded_rpm) <= 43
    assert runs[3]['steady_speed_mps'] < .15
    assert runs[6]['steady_speed_mps'] > .25
    OUT.mkdir(parents=True, exist_ok=True)
    summary = {
        'experiment': 'native PVS REMUS 100, protocol-autonomy inner autopilot, zero current',
        'not_a_closed_loop_mission': True,
        'trace_source': str(TRACE.relative_to(ROOT)),
        'trace_count': len(values),
        'positive_thrust_count': len(positive),
        'thrust_percentiles_positive': {str(p): float(np.percentile(positive, p)) for p in (50, 90, 95, 99, 100)},
        'encoded_rpm_max': int(max(encoded_rpm)),
        'encoded_rpm_p99': float(np.percentile(encoded_rpm, 99)),
        'rpm_per_percent': RPM_PER_PERCENT,
        'native_pvs_probe': [{k: v for k, v in run.items() if k != 'heading_series_deg'} for run in runs],
    }
    (OUT / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')

    fig, axes = plt.subplots(1, 2, figsize=style.figure_size(height=4.25), constrained_layout=True)
    ax = axes[0]
    ax.plot(rpms, [run['steady_speed_mps'] for run in runs], 'o-', color=style.PROPOSED, lw=1.8)
    ax.axvspan(0, max(encoded_rpm), color=style.WARNING, alpha=.16, label='现有 PID 报文范围')
    ax.axhline(.3, color=style.REFERENCE, ls='--', lw=1.2, label='确认段 0.3 m/s 目标')
    ax.set(xlabel='主推转速指令 / RPM', ylabel='稳态前进速度 / (m/s)', title='(a) 控制输出与推进尺度错配')
    ax.grid(alpha=.25); ax.legend(fontsize=8, loc='upper left')
    ax = axes[1]
    t = np.arange(1, round(60 / DT) + 1) * DT
    for run in runs:
        if run['rpm'] in (43, 180, 450, 900):
            ax.plot(t, run['heading_series_deg'], lw=1.5, label=f"{run['rpm']} RPM")
    ax.axhline(30, color=style.REFERENCE, ls='--', lw=1.2, label='30° 航向目标')
    ax.set(xlabel='航向阶跃后时间 / s', ylabel='航向变化 / (°)', title='(b) 原生自动驾驶仪转向响应')
    ax.grid(alpha=.25); ax.legend(fontsize=8)
    style.save_figure(fig, OUT / 'pvs_propulsion_turning_envelope')
    plt.close(fig)
    print(json.dumps({k: v for k, v in summary.items() if k != 'native_pvs_probe'}, ensure_ascii=False))


if __name__ == '__main__':
    main()

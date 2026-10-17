#!/usr/bin/env python3
"""Thesis-style evidence for redundant manual-cancel and persistent-fault holds."""
from __future__ import annotations

import csv
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

from thesis_plot_style import (BASELINE_1, BASELINE_3, PROPOSED, WARNING,
                               apply_thesis_style, figure_size, save_figure)

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / 'AUV-Master-Mag/results/v2'
OUT = RESULTS / 'inspection_flythrough_ros_pvs_bridge_cancel_controller_gate_20260926'


def read(directory: str, case: str):
    with (RESULTS / directory / f'{case}_seed_101.csv').open() as stream:
        return list(csv.DictReader(stream))


def column(rows, name: str):
    return np.array([float(row[name]) for row in rows])


def main() -> None:
    apply_thesis_style()
    before = read('inspection_flythrough_ros_pvs_bridge_cancel_20260926', 'wire_manual_cancel')
    after = read('inspection_flythrough_ros_pvs_bridge_cancel_controller_gate_20260926', 'wire_manual_cancel')
    persistent = read('inspection_flythrough_ros_pvs_bridge_persistent_20260926', 'wire_magnetic_persistent')
    navigation = read('inspection_flythrough_ros_pvs_bridge_navigation_20260926', 'wire_navigation_dropout')
    telemetry = read('inspection_flythrough_ros_pvs_bridge_telemetry_loss_20260926', 'wire_guard_telemetry_loss')
    cancel_at = next(float(row['time_s']) for row in after if row['arbiter_mode'] == 'REMOTE')
    fault_at = next(float(row['time_s']) for row in persistent
                    if row['mode'] == 'hold' and row['reason'] == 'magnetic_invalid')

    fig, axes = plt.subplots(2, 1, figsize=figure_size(height=4.7), constrained_layout=True)
    ax = axes[0]
    for rows, key, color, style, label in [
        (before, 'thrust_percent', BASELINE_3, '--', '修复前：PID 推力'),
        (after, 'thrust_percent', PROPOSED, '-', '修复后：PID 推力'),
        (after, 'rpm', BASELINE_1, ':', '桥输出：主电机转速 / 15'),
    ]:
        time_s = column(rows, 'time_s')
        mask = (time_s >= cancel_at - 12) & (time_s <= cancel_at + 35)
        y = column(rows, key)[mask]
        if key == 'rpm':
            y = y / 15.
        ax.plot(time_s[mask], y, style, color=color, lw=1.45, label=label)
    ax.axvspan(cancel_at, cancel_at + 35, color=WARNING, alpha=.10, label='手动取消后')
    ax.set(xlabel='任务时间 / s', ylabel='等效推力 / %',
           title='(a) 手动取消：控制器与桥均停止旧推力',
           xlim=(cancel_at - 12, cancel_at + 35), ylim=(-.8, 20))
    ax.legend(fontsize=7, ncol=2, loc='upper right')

    ax = axes[1]
    time_s = column(persistent, 'time_s')
    mask = (time_s >= fault_at - 12) & (time_s <= fault_at + 60)
    ax.plot(time_s[mask], column(persistent, 'rpm')[mask], color=PROPOSED,
            lw=1.35, label='桥输出主电机 RPM')
    ax.axvspan(fault_at, fault_at + 60, color=WARNING, alpha=.10, label='持续磁测故障')
    ax.set(xlabel='任务时间 / s', ylabel='主电机转速 / RPM',
           title='(b) 持续坏磁输入：241 个周期零推进、不误报完成',
           xlim=(fault_at - 12, fault_at + 60), ylim=(-10, 225))
    secondary = ax.twinx()
    secondary.plot(time_s[mask], column(persistent, 'speed_mps')[mask],
                   color=BASELINE_1, ls='--', lw=1.1, label='载体实际前进速度')
    secondary.set(ylabel='实际前进速度 / (m/s)', ylim=(-.02, .36))
    handles, labels = ax.get_legend_handles_labels()
    handles2, labels2 = secondary.get_legend_handles_labels()
    ax.legend(handles + handles2, labels + labels2, fontsize=7, ncol=3, loc='upper right')

    OUT.mkdir(parents=True, exist_ok=True)
    save_figure(fig, OUT / 'flythrough_safety_chain')
    plt.close(fig)

    old_cancel = [row for row in before if float(row['time_s']) >= cancel_at]
    new_cancel = [row for row in after if row['arbiter_mode'] == 'REMOTE']
    magnetic_hold = [row for row in persistent if row['mode'] == 'hold' and row['reason'] == 'magnetic_invalid']
    nav_hold = [row for row in navigation if row['mode'] == 'hold' and row['reason'] == 'navigation_invalid']
    telemetry_hold = [row for row in telemetry if row['arbiter_mode'] == 'REMOTE']

    def counts(rows):
        return {
            'ticks': len(rows),
            'positive_pid_ticks': sum(float(row['thrust_percent']) > 0 for row in rows),
            'positive_udp_rpm_ticks': sum(float(row['rpm']) > 0 for row in rows),
            'max_pid_thrust_percent': max(float(row['thrust_percent']) for row in rows),
        }

    summary = {
        'scope': 'isolated ROS2 + inspection PID + real guard/arbiter + localhost UDP + native PVS; synthetic magnetic source and scripted guard inputs; no PC104',
        'seed': 101,
        'manual_cancel_trigger_s': cancel_at,
        'manual_before_controller_gate': counts(old_cancel),
        'manual_after_controller_gate': counts(new_cancel),
        'persistent_magnetic_invalid': {**counts(magnetic_hold), 'completed': False,
                                        'final_speed_mps': float(persistent[-1]['speed_mps'])},
        'navigation_invalid_15_s': {**counts(nav_hold), 'completed_after_recovery': navigation[-1]['endpoint_complete'] == 'True',
                                    'duration_s': float(navigation[-1]['time_s'])},
        'stale_guard_telemetry': {**counts(telemetry_hold), 'completed': False,
                                  'final_speed_mps': float(telemetry[-1]['speed_mps'])},
    }
    assert len(new_cancel) == len(old_cancel) == len(magnetic_hold) == len(telemetry_hold) == 241
    assert len(nav_hold) == 60
    assert counts(old_cancel)['positive_pid_ticks'] == 241
    for item in (new_cancel, magnetic_hold, nav_hold, telemetry_hold):
        assert counts(item)['positive_pid_ticks'] == counts(item)['positive_udp_rpm_ticks'] == 0
    assert summary['navigation_invalid_15_s']['completed_after_recovery']
    (OUT / 'flythrough_safety_chain_summary.json').write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + '\n'
    )


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Compare sign-directed single-pass scans with a wrong-side staging counterexample."""
from __future__ import annotations

import csv
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

from thesis_plot_style import (BASELINE_3, PROPOSED, REFERENCE, WARNING,
                               apply_thesis_style, figure_size, save_figure)

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / 'AUV-Master-Mag/results/v2'
OUT = RESULTS / 'inspection_flythrough_side_hint_20260926'


def read(directory: str):
    with (RESULTS / directory / 'wire_seed_101.csv').open() as stream:
        return list(csv.DictReader(stream))


def values(rows, key: str):
    return np.array([float(row[key]) for row in rows])


def main() -> None:
    apply_thesis_style()
    south_start = read('inspection_flythrough_ros_pvs_bridge_side_final_plus6_20260926')
    north_start = read('inspection_flythrough_ros_pvs_bridge_side_final_minus6_20260926')
    wrong_side = read('inspection_flythrough_ros_pvs_bridge_offset_minus6_20260926')
    fig, axes = plt.subplots(1, 2, figsize=figure_size(height=3.15), constrained_layout=True)

    ax = axes[0]
    ax.plot(values(south_start, 'x_m'), values(south_start, 'y_m'),
            color=PROPOSED, lw=1.45, label='南侧起步：电缆 +6 m')
    ax.plot(values(north_start, 'x_m'), values(north_start, 'y_m'),
            color='#009E73', lw=1.45, label='北侧起步：电缆 −6 m')
    ax.plot([0, 80], [6, 6], color=PROPOSED, lw=.9, ls='--')
    ax.plot([0, 80], [-6, -6], color='#009E73', lw=.9, ls='--')
    ax.axhline(0, color=REFERENCE, lw=.7, ls=':', label='先验中心线')
    ax.set(xlim=(-255, 88), ylim=(-22, 22), xlabel='沿先验位置 / m', ylabel='横向位置 / m',
           title='(a) 两侧均有正确接近方向时完成巡检')
    ax.legend(fontsize=6.4, loc='lower left')

    ax = axes[1]
    ax.plot(values(wrong_side, 'x_m'), values(wrong_side, 'y_m'),
            color=BASELINE_3, lw=1.4, ls='--', label='方向相反：扫描超时')
    ax.plot(values(north_start, 'x_m'), values(north_start, 'y_m'),
            color='#009E73', lw=1.45, label='方向匹配：任务完成')
    ax.plot([0, 80], [-6, -6], color=REFERENCE, lw=1., label='电缆真值 −6 m')
    ax.axhline(0, color=REFERENCE, lw=.7, ls=':')
    ax.scatter([float(wrong_side[-1]['x_m'])], [float(wrong_side[-1]['y_m'])],
               color=WARNING, marker='x', s=35, zorder=5)
    ax.annotate('450 s 扫描时限', xy=(float(wrong_side[-1]['x_m']), float(wrong_side[-1]['y_m'])),
                xytext=(-235, 16), fontsize=6.8, color=WARNING,
                arrowprops={'arrowstyle': '->', 'lw': .8, 'color': WARNING})
    ax.set(xlim=(-255, 88), ylim=(-22, 22), xlabel='沿先验位置 / m', ylabel='横向位置 / m',
           title='(b) 侧向提示错误时拒绝完成')
    ax.legend(fontsize=6.4, loc='lower left')

    OUT.mkdir(parents=True, exist_ok=True)
    save_figure(fig, OUT / 'side_hint_flythrough_paths')
    plt.close(fig)

    def metrics(rows, truth):
        errors = [abs(float(row['y_m']) - truth) for row in rows
                  if row['mode'] == 'track' and float(row['x_m']) >= 0]
        return {
            'ticks': len(rows), 'duration_s': float(rows[-1]['time_s']),
            'completed': rows[-1]['endpoint_complete'] == 'True',
            'first_hold_reason': next((row['reason'] for row in rows if row['mode'] == 'hold'), None),
            'track_x_ge_0_samples': len(errors),
            'track_x_ge_0_true_lateral_mae_m': float(np.mean(errors)) if errors else None,
            'track_x_ge_0_true_lateral_p95_m': float(np.percentile(errors, 95)) if errors else None,
            'track_x_ge_0_true_lateral_max_m': max(errors) if errors else None,
            'depth_published': any(row['depth_valid'] == 'True' for row in rows),
            'maximum_abs_lateral_m': max(abs(float(row['y_m'])) for row in rows),
        }

    summary = {
        'scope': 'seed 101 synthetic single straight wire; actual ROS2/PID/guard/localhost UDP/native PVS; no physical PC104',
        'precondition': 'side hint selects the opposite starting side; prealigned vehicle, 390 x 60 m corridor, target speed 0.3 m/s, zero current',
        'south_start_cable_plus6': metrics(south_start, 6.),
        'north_start_cable_minus6': metrics(north_start, -6.),
        'wrong_south_start_cable_minus6': metrics(wrong_side, -6.),
    }
    assert summary['south_start_cable_plus6']['completed']
    assert summary['north_start_cable_minus6']['completed']
    assert not summary['wrong_south_start_cable_minus6']['completed']
    assert all(not value['depth_published'] for key, value in summary.items() if isinstance(value, dict))
    (OUT / 'side_hint_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')


if __name__ == '__main__':
    main()

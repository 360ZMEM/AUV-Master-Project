#!/usr/bin/env python3
"""Thesis-style process and insight plots for the ROS/PID/native-PVS audit."""
from __future__ import annotations

import csv
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

from thesis_plot_style import (PROPOSED, BASELINE_1, BASELINE_3, REFERENCE,
                               WARNING, apply_thesis_style, figure_size, save_figure)

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / 'AUV-Master-Mag/results/v2'
OUT = RESULTS / 'inspection_flythrough_ros_pvs_adaptive_final_20260926'


def read(directory: str, case: str = 'wire'):
    with (RESULTS / directory / f'{case}_seed_101.csv').open() as stream:
        return list(csv.DictReader(stream))


def values(rows, key):
    return np.array([float(row[key]) for row in rows])


def main():
    apply_thesis_style()
    old_n = read('inspection_flythrough_ros_pvs_current_north_20260926')
    old_s = read('inspection_flythrough_ros_pvs_current_south_20260926')
    zero = read('inspection_flythrough_ros_pvs_adaptive_final_20260926')
    north = read('inspection_flythrough_ros_pvs_rejoin_north_20260926')
    south = read('inspection_flythrough_ros_pvs_rejoin_south_20260926')
    dropout = read('inspection_flythrough_ros_pvs_adaptive_final_20260926', 'wire_magnetic_dropout')

    fig, axes = plt.subplots(2, 2, figsize=figure_size(height=4.8), constrained_layout=True)
    ax = axes[0, 0]
    for rows, color, label, style in [
        (old_n, BASELINE_1, '北向流：原引导', '--'),
        (old_s, BASELINE_3, '南向流：原引导', '--'),
        (north, PROPOSED, '北向流：改进后', '-'),
        (south, '#009E73', '南向流：改进后', '-'),
    ]:
        ax.plot(values(rows, 'x_m'), values(rows, 'y_m'), style,
                color=color, lw=1.15 if style == '--' else 1.5, label=label)
    ax.plot([0, 80], [6, 6], color=REFERENCE, lw=1.1, label='电缆真值')
    ax.axhline(20, color=WARNING, ls=':', lw=.8)
    ax.axhline(-20, color=WARNING, ls=':', lw=.8)
    ax.set(xlabel='沿缆方向位置 / m', ylabel='横向位置 / m',
           title='(a) 同一 0.05 m/s 横流：穿越与返回',
           xlim=(-255, 90), ylim=(-23, 23))
    ax.legend(fontsize=6.4, ncol=2, loc='lower right')

    ax = axes[0, 1]
    for rows, color, label in [
        (zero, REFERENCE, '零流'),
        (north, PROPOSED, '北向流'),
        (south, '#009E73', '南向流'),
    ]:
        # Include every TRACK sample past the route start, including periods
        # that the planner temporarily labels "rejoin" after an excursion.
        mask = np.array([row['mode'] == 'track' and float(row['x_m']) >= 0 for row in rows])
        xx = values(rows, 'x_m')[mask]
        yy = values(rows, 'y_m')[mask] - 6.
        ax.plot(xx, yy, color=color, lw=1.25, label=label)
    ax.axhline(0, color=BASELINE_1, ls='--', lw=.8)
    ax.set(xlabel='沿缆段位置 / m', ylabel='真实横向误差 / m',
           title='(b) 全部沿缆 TRACK 样本的真值误差', xlim=(0, 82), ylim=(-2.2, 2.2))
    ax.legend(fontsize=7, ncol=3, loc='lower center')

    ax = axes[1, 0]
    for rows, color, label in [
        (old_n, BASELINE_1, '原引导：北向流'),
        (north, PROPOSED, '改进后：北向流'),
        (old_s, BASELINE_3, '原引导：南向流'),
        (south, '#009E73', '改进后：南向流'),
    ]:
        ax.plot(values(rows, 'time_s'), values(rows, 'y_m'),
                '--' if '原引导' in label else '-', color=color,
                lw=1.2, label=label)
    ax.axhline(20, color=WARNING, ls=':', lw=.9, label='北侧停止缓冲')
    ax.set(xlabel='任务时间 / s', ylabel='横向位置 / m',
           title='(c) 固定终点指向的晚修正风险', xlim=(0, 1250), ylim=(-22, 22))
    ax.legend(fontsize=6.5, ncol=2, loc='lower right')

    ax = axes[1, 1]
    fault = np.array([row['mode'] == 'hold' and row['reason'] == 'magnetic_invalid' for row in dropout])
    fault_indices = np.flatnonzero(fault)
    start = values(dropout, 'time_s')[fault_indices[0]]
    end = values(dropout, 'time_s')[fault_indices[-1]] + .25
    window = (values(dropout, 'time_s') >= start - 20) & (values(dropout, 'time_s') <= end + 25)
    t = values(dropout, 'time_s')[window]
    rpm = values(dropout, 'rpm')[window]
    ax.plot(t, rpm, color=PROPOSED, lw=1.2, label='协议解码主电机 RPM')
    ax.axvspan(start, end, color=WARNING, alpha=.12, label='磁测量故障 15 s')
    ax.set(xlabel='任务时间 / s', ylabel='主电机转速 / RPM',
           title='(d) 故障期间零推力，恢复后继续', ylim=(-10, 230))
    ax.legend(fontsize=7, loc='upper right')

    save_figure(fig, OUT / 'ros_pvs_flythrough_current_and_fault')
    plt.close(fig)


if __name__ == '__main__':
    main()

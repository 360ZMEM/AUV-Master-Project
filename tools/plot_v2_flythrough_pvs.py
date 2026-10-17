#!/usr/bin/env python3
"""Render the PVS flythrough diagnostic with the thesis figure style."""
from __future__ import annotations

import csv
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

from thesis_plot_style import (PROPOSED, BASELINE_1, REFERENCE, WARNING,
                               apply_thesis_style, figure_size, save_figure)

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'AUV-Master-Mag/results/v2/inspection_flythrough_pvs_final_20260926'


def read(case: str):
    with (OUT / f'{case}_seed_101.csv').open() as stream:
        return list(csv.DictReader(stream))


def values(rows, key):
    return np.array([float(row[key]) for row in rows], dtype=float)


def main():
    wire = read('wire')
    no_source = read('no_source')
    apply_thesis_style()
    fig, axes = plt.subplots(1, 2, figsize=figure_size(height=3.55), constrained_layout=True)
    ax = axes[0]
    x, y = values(wire, 'x_m'), values(wire, 'y_m')
    modes = np.array([row['mode'] for row in wire])
    for mode, color, label in [('search', BASELINE_1, '先验搜索'),
                               ('confirm', PROPOSED, '穿越确认'),
                               ('track', '#009E73', '沿缆跟踪')]:
        selected = modes == mode
        ax.plot(np.where(selected, x, np.nan), np.where(selected, y, np.nan),
                color=color, lw=1.6, label=label)
    ax.plot(values(no_source, 'x_m'), values(no_source, 'y_m'), ':',
            color=WARNING, lw=1.1, label='无磁源：终点拒绝')
    ax.scatter([float(no_source[-1]['x_m'])], [float(no_source[-1]['y_m'])],
               marker='x', color=WARNING, s=35, zorder=5)
    ax.plot([0, 80], [0, 0], '--', color=REFERENCE, lw=1., label='先验电缆')
    ax.plot([0, 80], [6, 6], '-', color=REFERENCE, lw=1.2, label='真实电缆')
    ax.axhline(20, color=WARNING, ls=':', lw=.8)
    ax.axhline(-20, color=WARNING, ls=':', lw=.8)
    ax.scatter([x[0], x[-1]], [y[0], y[-1]], color=PROPOSED, s=16, zorder=4)
    ax.set(xlabel='沿缆方向位置 / m', ylabel='横向位置 / m',
           title='(a) 原生 PVS：一次浅角度穿越与跟踪',
           xlim=(-255, 90), ylim=(-23, 23))
    ax.legend(fontsize=7, ncol=2, loc='lower right')

    ax = axes[1]
    before_track = modes != 'track'
    yy = y[before_track]
    bb = values(wire, 'magnetic_nt')[before_track]
    ax.plot(yy, bb, color=PROPOSED, lw=1.2, label='沿航迹实测磁包络')
    confirmed = next(row for row in wire if row['lateral_valid'] == 'True')
    half = float(confirmed['fwhm_half_level_nt'])
    left = float(confirmed['fwhm_left_x_m'])
    right = float(confirmed['fwhm_right_x_m'])
    ax.axhline(half, color=WARNING, ls='--', lw=1., label='背景修正半峰')
    ax.axvline(left, color=WARNING, ls=':', lw=.8)
    ax.axvline(right, color=WARNING, ls=':', lw=.8)
    ax.axvline(6., color=REFERENCE, ls='--', lw=.9, label='真实横向中心')
    ax.set(xlabel='横向空间坐标 / m', ylabel='磁包络 / nT',
           title='(b) 双侧交点可见，场形深度仍拒绝', xlim=(-16, 16))
    ax.legend(fontsize=7, loc='upper left')
    save_figure(fig, OUT / 'pvs_flythrough_profile_and_track')
    plt.close(fig)


if __name__ == '__main__':
    main()

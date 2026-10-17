#!/usr/bin/env python3
"""Thesis-style diagnostic of paced PVS input gaps and applied fixture RPM."""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

import matplotlib.pyplot as plt

from thesis_plot_style import (NEUTRAL, PROPOSED, REFERENCE, WARNING,
                               add_panel_labels, apply_thesis_style,
                               figure_size, save_figure)


def rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline='', encoding='utf-8') as stream:
        return list(csv.DictReader(stream))


def plot(run_dir: Path, output_base: Path) -> list[Path]:
    fixture = rows(run_dir / 'pvs_fixture/pvs_trace.csv')
    if not fixture:
        raise ValueError('empty PVS fixture trace')
    apply_thesis_style(layout='full')
    fig, axes = plt.subplots(2, 1, figsize=figure_size('full', height=5.0))
    receipt_dir = run_dir / 'ros_receipt'
    origin = float(fixture[0]['monotonic_s'])
    for role, name, color, marker in (
            ('magnetic', '磁测独立接收', PROPOSED, 'o'),
            ('ros_setpoint', 'Setpoint 独立接收', WARNING, 's')):
        data = rows(receipt_dir / f'{role}.csv')
        times = [float(row['time_s']) for row in data]
        axes[0].plot([value - origin for value in times[1:]],
                     [b - a for a, b in zip(times, times[1:])],
                     color=color, marker=marker, ms=3.0, lw=.9, label=name)
    axes[0].axhline(.25, color=REFERENCE, ls='--', lw=.9,
                    label='输入短探针参考 0.25 s')
    axes[0].axhline(.30, color=NEUTRAL, ls=':', lw=.9,
                    label='输出短探针参考 0.30 s')
    axes[0].set(xlabel='本机运行时间 / s', ylabel='相邻独立接收间隔 / s',
                title='输入与输出均有超过参考门的长空档')
    axes[0].legend(ncol=2, loc='upper right', fontsize=7)
    axes[0].grid(alpha=.3)

    sim_time = [float(row['source_stamp_s']) for row in fixture]
    rpm = [float(row['applied_rpm']) for row in fixture]
    axes[1].step(sim_time, rpm, where='post', color=PROPOSED,
                 lw=1.5, label='PVS 夹具采用的本地协议转速')
    holds = [i for i, row in enumerate(fixture) if row['mode'] == 'hold']
    if holds:
        axes[1].scatter([sim_time[i] for i in holds], [rpm[i] for i in holds],
                        color=WARNING, marker='x', s=20, label='算法 Hold 观测', zorder=3)
    axes[1].set(xlabel='模拟任务时间 / s', ylabel='PVS 夹具采用的转速 / rpm',
                title=f'短试仅 {sum(value > 0 for value in rpm)}/{len(rpm)} 周期正向；未完成任务')
    axes[1].set_ylim(-12, max(210., max(rpm) + 20.))
    axes[1].legend(loc='upper right', fontsize=7)
    axes[1].grid(alpha=.3)
    add_panel_labels(axes)
    fig.suptitle('分进程产品节点＋实时 PVS 供数的短时活性诊断', y=.99, fontsize=11)
    fig.text(.5, .014,
             '本机合成声磁输入；转速仅用于 PVS 数字孪生，未经过实体桥或 PC104。',
             ha='center', va='bottom', fontsize=8, color=NEUTRAL)
    fig.subplots_adjust(left=.14, right=.98, bottom=.17, top=.87, hspace=.57)
    paths = save_figure(fig, output_base)
    plt.close(fig)
    return paths


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', type=Path, required=True)
    parser.add_argument('--output-base', type=Path, required=True)
    args = parser.parse_args()
    print('\n'.join(str(path) for path in plot(args.run_dir, args.output_base)))


if __name__ == '__main__':
    main()

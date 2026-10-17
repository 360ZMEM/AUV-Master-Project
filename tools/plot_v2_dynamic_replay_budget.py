#!/usr/bin/env python3
"""Plot independent DDS gaps and feeder publish cost for open-loop route replay."""
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


def plot(run: Path, output_base: Path) -> list[Path]:
    trace = rows(run / 'pvs_fixture/pvs_trace.csv')
    if not trace or not all('sensor_publish_cpu_duration_s' in row for row in trace):
        raise ValueError('route-replay publication CPU trace is missing')
    apply_thesis_style(layout='full')
    fig, axes = plt.subplots(2, 1, figsize=figure_size('full', height=5.1))
    origin = float(trace[0]['monotonic_s'])
    for role, label, color, marker in (
            ('magnetic', '磁测独立接收', PROPOSED, 'o'),
            ('ros_setpoint', 'Setpoint 独立接收', WARNING, 's')):
        receipt = rows(run / 'ros_receipt' / f'{role}.csv')
        times = [float(row['time_s']) for row in receipt]
        axes[0].plot([t - origin for t in times[1:]],
                     [b - a for a, b in zip(times, times[1:])],
                     color=color, marker=marker, ms=2.8, lw=.8, label=label)
    axes[0].axhline(.25, color=REFERENCE, ls='--', lw=.9,
                    label='输入短探针参考 0.25 s')
    axes[0].axhline(.30, color=NEUTRAL, ls=':', lw=.9,
                    label='输出短探针参考 0.30 s')
    axes[0].set(xlabel='本机运行时间 / s', ylabel='相邻独立接收间隔 / s',
                title='无在线 PVS 时，动态重放的输入输出仍有长空档')
    axes[0].legend(loc='upper center', fontsize=7, ncol=2)
    axes[0].grid(alpha=.3)

    wall = [float(row['sensor_publish_duration_s']) for row in trace]
    cpu = [float(row['sensor_publish_cpu_duration_s']) for row in trace]
    sonar = [row['sonar_published'] == 'True' for row in trace]
    for due, label, color, marker in (
            (False, '仅导航／磁测周期', PROPOSED, 'o'),
            (True, '含合成声呐周期', WARNING, 's')):
        chosen = [i for i, value in enumerate(sonar) if value == due]
        axes[1].scatter([wall[i] for i in chosen], [cpu[i] for i in chosen],
                        color=color, marker=marker, s=26, alpha=.78, label=label)
    axes[1].plot([0., .8], [0., .8], ls=':', color=REFERENCE, lw=.8,
                 label='墙钟与线程 CPU 相等')
    axes[1].axvline(.1, color=NEUTRAL, ls='--', lw=.9,
                    label='名义发布周期 0.10 s')
    axes[1].set(xlabel='传感器发布阶段墙钟耗时 / s',
                ylabel='该阶段线程 CPU 耗时 / s',
                title='发布阶段自身可超周期；墙钟长尾不能全算为 CPU 计算')
    axes[1].set_xlim(0., .8)
    axes[1].set_ylim(0., .36)
    axes[1].legend(loc='upper right', fontsize=7, ncol=2)
    axes[1].grid(alpha=.3)
    add_panel_labels(axes)
    fig.suptitle('动态航迹实时重放：移除在线 PVS 后的时序边界', y=.99, fontsize=11)
    fig.text(.5, .012,
             '历史位姿开环重放＋重新合成磁测／声呐；无控制反馈、无实物桥或 PC104。',
             ha='center', va='bottom', fontsize=8, color=NEUTRAL)
    fig.subplots_adjust(left=.15, right=.98, bottom=.17, top=.88, hspace=.57)
    paths = save_figure(fig, output_base)
    plt.close(fig)
    return paths


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', required=True, type=Path)
    parser.add_argument('--output-base', required=True, type=Path)
    args = parser.parse_args()
    print('\n'.join(str(path) for path in plot(args.run_dir, args.output_base)))


if __name__ == '__main__':
    main()

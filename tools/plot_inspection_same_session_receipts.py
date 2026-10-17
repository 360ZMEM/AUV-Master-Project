#!/usr/bin/env python3
"""Thesis-style insight figure for one fixed-feeder, same-session ROS receipt probe."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from thesis_plot_style import (NEUTRAL, PROPOSED, REFERENCE, WARNING,
                               add_panel_labels, apply_thesis_style,
                               figure_size, save_figure)

import matplotlib.pyplot as plt


def rows(path: Path) -> list[dict]:
    with path.open(newline='', encoding='utf-8') as stream:
        return list(csv.DictReader(stream))


def plot(run_dir: Path, out_base: Path) -> list[Path]:
    feeder = json.loads((run_dir / 'feeder_events.json').read_text(encoding='utf-8'))
    summary = json.loads((run_dir / 'summary.json').read_text(encoding='utf-8'))
    if not summary.get('record_ros_receipts'):
        raise ValueError('run has no independent ROS receipt capture')
    origin = feeder['start_monotonic_s'] + feeder['prewarm_s']
    healthy_end = feeder['healthy_s']
    dropout_end = healthy_end + feeder['dropout_s']
    finish = dropout_end + feeder['recovery_s']
    gate = rows(run_dir / 'gate_ticks.csv')
    candidate = rows(run_dir / 'ros_receipt/candidate.csv')
    final = rows(run_dir / 'ros_receipt/ros_setpoint.csv')
    pid = rows(run_dir / 'ros_receipt/pid.csv')
    lanes = [
        ('供数', 5, [{'time_s': r['monotonic_s'], 'value': 1.}
                    for r in feeder['events'] if r['event'] == 'sensor_tick']),
        ('候选', 4, [{'time_s': r['time_s'], 'value': r['target_speed_mps']} for r in candidate]),
        ('门决定', 3, [{'time_s': r['time_s'], 'value': r['decision_speed_mps']} for r in gate]),
        ('DDS 接收', 2, [{'time_s': r['time_s'], 'value': r['target_speed_mps']} for r in final]),
        ('PID 输出', 1, [{'time_s': r['time_s'], 'value': r['thrust_percent']} for r in pid]),
    ]
    apply_thesis_style(layout='full')
    fig, axes = plt.subplots(2, 1, figsize=figure_size('full', height=4.9),
                             sharex=True, gridspec_kw={'height_ratios': [1.6, 1.]})
    for ax in axes:
        ax.axvspan(healthy_end, dropout_end, color='#F4E6DF', zorder=-2)
        ax.axvline(healthy_end, color=WARNING, ls=':', lw=.9)
        ax.axvline(dropout_end, color=WARNING, ls=':', lw=.9)
        ax.set_xlim(0., finish)
        ax.grid(axis='x', alpha=.4)
    for label, lane, entries in lanes:
        positive = [float(r['time_s']) - origin for r in entries
                    if 0 <= float(r['time_s']) - origin < finish and float(r['value']) > 0]
        zero = [float(r['time_s']) - origin for r in entries
                if 0 <= float(r['time_s']) - origin < finish and float(r['value']) <= 0]
        axes[0].scatter(positive, [lane] * len(positive), marker='|', s=78,
                        linewidth=1.1, color=REFERENCE if lane == 5 else PROPOSED, zorder=3)
        axes[0].scatter(zero, [lane] * len(zero), marker='|', s=78,
                        linewidth=1.1, color=WARNING, zorder=3)
    axes[0].set_yticks([1, 2, 3, 4, 5], ['PID 输出', 'DDS 接收', '门决定', '候选', '供数'])
    axes[0].set_ylim(.5, 5.5)
    axes[0].text(.99, 1.02, '蓝：正向  橙：零输出  灰：供数', transform=axes[0].transAxes,
                 ha='right', va='bottom', fontsize=8, color=NEUTRAL, clip_on=False)

    ages = [(float(r['time_s']) - origin,
             float(r['time_s']) - float(r['candidate_source_time_s']))
            for r in final if float(r['target_speed_mps']) > 0
            and 0 <= float(r['time_s']) - origin < finish]
    threshold = float(summary['candidate_timeout_s'])
    fresh = [(t, age) for t, age in ages if age <= threshold]
    stale = [(t, age) for t, age in ages if age > threshold]
    axes[1].scatter([x for x, _ in fresh], [y for _, y in fresh], color=PROPOSED,
                    s=18, label='限值内', zorder=3)
    axes[1].scatter([x for x, _ in stale], [y for _, y in stale], color=WARNING,
                    s=27, marker='D', label='接收时已旧', zorder=4)
    axes[1].axhline(threshold, color=WARNING, ls='--', lw=1.,
                    label=f'候选来源年龄限值 {threshold:g} s')
    axes[1].set_ylabel('正向 Setpoint 来源年龄 / s')
    axes[1].set_xlabel('健康窗开始后的墙钟时间 / s')
    axes[1].set_ylim(bottom=0.)
    axes[1].legend(loc='upper right', fontsize=7, ncol=2)
    add_panel_labels(axes)
    fig.suptitle('同次监督门与 DDS 接收：失鲜来源的可观测性', y=.995, fontsize=11)
    healthy = summary['phases']['healthy']
    foot = (f"合成健康窗：{healthy['setpoint_positive']}/{healthy['setpoint_count']} 正向；"
            f"接收时已旧 {healthy['receipt_stale_positive_count']} 条；"
            f"输入最大缺口 {healthy['feeder_max_gap_s']:.3f} s。非现场验收。")
    fig.text(.5, .012, foot, ha='center', va='bottom', fontsize=8, color=REFERENCE)
    fig.subplots_adjust(left=.16, right=.98, bottom=.18, top=.87, hspace=.28)
    paths = save_figure(fig, out_base)
    plt.close(fig)
    return paths


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', required=True, type=Path)
    parser.add_argument('--out-base', required=True, type=Path)
    args = parser.parse_args()
    for path in plot(args.run_dir, args.out_base):
        print(path)

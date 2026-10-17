#!/usr/bin/env python3
"""Thesis-style, raw-message timeline for the recoverable inspection probe."""
import argparse
import csv
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from thesis_plot_style import (PROPOSED, REFERENCE, WARNING, NEUTRAL,
                               add_panel_labels, apply_thesis_style,
                               figure_size, save_figure)

import matplotlib.pyplot as plt


def plot(run_dir: Path, out_base: Path):
    feeder = json.loads((run_dir / 'feeder_events.json').read_text(encoding='utf-8'))
    summary = json.loads((run_dir / 'summary.json').read_text(encoding='utf-8'))
    with (run_dir / 'observer_events.csv').open(encoding='utf-8', newline='') as stream:
        rows = list(csv.DictReader(stream))
    origin = feeder['start_monotonic_s'] + feeder['prewarm_s']
    dropout = feeder['healthy_s']
    restore = dropout + feeder['dropout_s']
    finish = restore + feeder['recovery_s']
    apply_thesis_style(layout='full')
    fig, axes = plt.subplots(3, 1, figsize=figure_size('full', height=5.5),
                             sharex=True, gridspec_kw={'height_ratios': [1., 1.15, 1.15]})
    for ax in axes:
        ax.axvspan(dropout, restore, color='#F4E6DF', zorder=-2)
        ax.axvline(dropout, color=WARNING, ls=':', lw=1.)
        ax.axvline(restore, color=WARNING, ls=':', lw=1.)
        ax.set_xlim(0., finish)
        ax.grid(axis='x', alpha=.35)
    sensor = [row['monotonic_s']-origin for row in feeder['events']
              if row['event']=='sensor_tick' and origin<=row['monotonic_s']<origin+finish]
    candidate = [row for row in rows if row['topic']=='candidate'
                 and 0.<=float(row['monotonic_s'])-origin<finish]
    axes[0].scatter(sensor, [1.]*len(sensor), marker='|', s=45, color=REFERENCE,
                    linewidth=.8, label='输入样本', zorder=3)
    for positive, y, color, label in ((True, .58, PROPOSED, '算法正候选'),
                                      (False, .22, WARNING, '算法 Hold')):
        selected = [row for row in candidate if (float(row['speed_or_thrust'])>0.)==positive]
        axes[0].scatter([float(row['monotonic_s'])-origin for row in selected],
                        [y]*len(selected), s=18, color=color, label=label, zorder=4)
    axes[0].set_yticks([.22,.58,1.], ['Hold','候选','输入'])
    axes[0].set_ylim(.02,1.15)
    axes[0].legend(loc='center right', bbox_to_anchor=(1., .78), ncol=3, fontsize=7)

    for topic, ax, ylabel in (('setpoint',axes[1],'目标速度 / m·s$^{-1}$'),
                              ('effort',axes[2],'PID 主推 / %')):
        selected = [row for row in rows if row['topic']==topic
                    and 0.<=float(row['monotonic_s'])-origin<finish]
        for positive, color, label in ((True,PROPOSED,'正向'),(False,WARNING,'零输出')):
            part = [row for row in selected if (float(row['speed_or_thrust'])>0.)==positive]
            ax.scatter([float(row['monotonic_s'])-origin for row in part],
                       [float(row['speed_or_thrust']) for row in part],
                       s=20 if positive else 15, color=color, label=label, zorder=4)
        ax.set_ylabel(ylabel)
        ax.legend(loc='center right', ncol=2, fontsize=7)
    axes[1].set_ylim(-.03,.38)
    axes[2].set_ylim(bottom=-4.)
    axes[2].set_xlabel('任务开始后的墙钟时间 / s')
    axes[0].text(dropout+.15, 1.11, '输入断流', color=WARNING, va='top', fontsize=8)
    axes[1].axvline(dropout+.75, color=NEUTRAL, ls='--', lw=.8)
    axes[1].text(dropout+.83, .35, '故障守卫窗', color=NEUTRAL, va='top', fontsize=8)
    add_panel_labels(axes)
    fig.suptitle('来源校验与可恢复 Hold：合成任务消息时序', y=.995, fontsize=11)
    healthy = summary['phases']['healthy']
    fault = summary['phases']['dropout']
    recovered = summary['phases']['restored']
    fig.text(.5, .012,
             f"健康 {healthy['setpoint_positive']}/{healthy['setpoint_count']} 正向；"
             f"故障守卫窗 {fault['guarded_setpoint_zero']}/{fault['guarded_setpoint_count']} 零速；"
             f"恢复 {recovered['setpoint_positive']}/{recovered['setpoint_count']} 正向。"
             '独立 ROS 合成探针，非持续运行验收。',
             ha='center', va='bottom', fontsize=7.5, color=REFERENCE)
    fig.subplots_adjust(left=.12,right=.98,bottom=.17,top=.91,hspace=.33)
    paths = save_figure(fig,out_base)
    plt.close(fig)
    return paths


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir',required=True,type=Path)
    parser.add_argument('--out-base',required=True,type=Path)
    args=parser.parse_args()
    for path in plot(args.run_dir,args.out_base):
        print(path)

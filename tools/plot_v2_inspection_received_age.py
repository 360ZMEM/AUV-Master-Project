#!/usr/bin/env python3
"""Plot independently received Setpoint timing for a wall-clock synthetic probe."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import matplotlib.pyplot as plt

from thesis_plot_style import (BASELINE_1, PROPOSED, REFERENCE, WARNING,
                               apply_thesis_style, figure_size)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    summary = json.loads((args.run_dir / 'summary.json').read_text(encoding='utf-8'))
    feeder = json.loads((args.run_dir / 'feeder_events.json').read_text(encoding='utf-8'))
    if not summary.get('wall_clock_fixture') or not feeder.get('wall_time_stamps'):
        raise ValueError('plot requires the wall-clock synthetic fixture')
    with (args.run_dir / 'observer_events.csv').open(newline='', encoding='utf-8') as stream:
        rows = [row for row in csv.DictReader(stream) if row['topic'] == 'setpoint']
    if not rows:
        raise ValueError('no independently observed Setpoints')
    start = feeder['start_monotonic_s'] + feeder['prewarm_s']
    healthy_end = feeder['healthy_s']
    dropout_end = healthy_end + feeder['dropout_s']
    record_end = dropout_end + feeder['recovery_s']
    points = [(float(row['monotonic_s']) - start, float(row['speed_or_thrust']),
               float(row['wall_received_s']) - float(row['source_stamp_s']))
              for row in rows if 0 <= float(row['monotonic_s']) - start <= record_end]
    positive = [(t, age) for t, speed, age in points if speed > 0]
    apply_thesis_style(layout='full')
    fig, axes = plt.subplots(2, 1, figsize=figure_size('full', height=4.5),
                             sharex=True, gridspec_kw={'height_ratios': [1, 1.2]})
    for ax in axes:
        ax.axvspan(healthy_end, dropout_end, color=REFERENCE, alpha=.09, zorder=0)
        ax.axvline(healthy_end, color=REFERENCE, lw=.8, ls=':')
        ax.axvline(dropout_end, color=REFERENCE, lw=.8, ls=':')
        ax.set_xlim(0, record_end)
        ax.grid(axis='y', alpha=.25)
    axes[0].plot([x[0] for x in points], [x[1] for x in points],
                 color=PROPOSED, lw=.9, marker='.', ms=3)
    axes[0].set_ylabel('到达的 Setpoint 速度 (m/s)')
    axes[0].set_ylim(-.025, max(.25, summary['mission_speed_mps'] * 1.3))
    axes[1].scatter([x[0] for x in positive], [x[1] for x in positive],
                    color=WARNING, s=11, label='正向消息到达时来源年龄', zorder=3)
    axes[1].axhline(summary['candidate_timeout_s'], color=BASELINE_1,
                    lw=1, ls='--', label='候选年龄上限')
    axes[1].set_ylabel('接收时来源年龄 (s)')
    axes[1].set_xlabel('健康段起点后的墙钟时间 (s)')
    axes[1].set_ylim(0, max(1.9, max((x[1] for x in positive), default=0) * 1.12))
    axes[1].legend(loc='upper right', frameon=False, fontsize=8)
    axes[0].text(healthy_end / 2, axes[0].get_ylim()[1] * .96, '健康供数',
                 ha='center', va='top', fontsize=8)
    axes[0].text((healthy_end + dropout_end) / 2, axes[0].get_ylim()[1] * .96,
                 '输入断流', ha='center', va='top', fontsize=8)
    axes[0].text((dropout_end + record_end) / 2, axes[0].get_ylim()[1] * .96,
                 '恢复供数', ha='center', va='top', fontsize=8)
    fig.tight_layout(h_pad=.6)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.output, dpi=600)
    plt.close(fig)


if __name__ == '__main__':
    main()

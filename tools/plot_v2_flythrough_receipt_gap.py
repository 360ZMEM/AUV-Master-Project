#!/usr/bin/env python3
"""Thesis-style diagnostic of independent receipt and fixture callback delay."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import matplotlib.pyplot as plt

from thesis_plot_style import (NEUTRAL, PROPOSED, REFERENCE, WARNING,
                               add_panel_labels, apply_thesis_style,
                               figure_size, save_figure)


def rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline='', encoding='utf-8') as stream:
        return list(csv.DictReader(stream))


def first_stamp_events(run: Path) -> dict[str, float]:
    stage = rows(run / 'fixture_stage_wall_timing.csv')
    first_stamp = stage[0]['source_stamp_s']
    events = {row['stage']: float(row['monotonic_s']) for row in stage
              if row['source_stamp_s'] == first_stamp}
    origin = events['sensors_published']
    for role, label in [('ros_setpoint', 'dds_setpoint'), ('pid', 'dds_pid')]:
        matching = [row for row in rows(run / 'ros_receipt' / f'{role}.csv')
                    if abs(float(row['header_stamp_s']) - float(first_stamp)) < 1e-6]
        if not matching:
            raise ValueError(f'{run}: missing {role} for first source stamp')
        events[label] = float(matching[0]['time_s'])
    return {key: value - origin for key, value in events.items()}


def plot(run_dirs: list[Path], out_base: Path) -> list[Path]:
    if len(run_dirs) != 3:
        raise ValueError('expected three diagnostic runs: four ticks, first-tick failure, four ticks')
    audits = [json.loads((run / 'receipt_join_audit.json').read_text()) for run in run_dirs]
    events = [first_stamp_events(run) for run in run_dirs]
    apply_thesis_style(layout='full')
    fig, axes = plt.subplots(2, 1, figsize=figure_size('full', height=5.5),
                             gridspec_kw={'height_ratios': [1.25, 1.]})
    labels = ['四周期短试 A', '首周期拒止', '四周期短试 B']
    markers = [
        ('dds_setpoint', '独立接收 Setpoint', 'o', PROPOSED, .12),
        ('dds_pid', '独立接收 PID', 's', REFERENCE, .04),
        ('peer_received_pid_output', '夹具观察 PID', '^', WARNING, -.04),
        ('bridge_udp_received', '本地 UDP', 'D', NEUTRAL, -.12),
    ]
    for lane, (label, values) in enumerate(zip(labels, events), start=1):
        axes[0].hlines(lane, 0., max(values.values()) + .05,
                       color='#D9D9D9', lw=.8)
        for key, legend, marker, color, y_offset in markers:
            if key in values:
                axes[0].scatter(values[key], lane + y_offset, marker=marker, s=42,
                                color=color, label=legend if lane == 1 else None,
                                zorder=3)
    axes[0].set_yticks([1, 2, 3], labels)
    axes[0].set_xlim(0., 1.6)
    axes[0].set_xlabel('本周期磁测发布后墙钟时间 / s')
    axes[0].grid(axis='x', alpha=.35)
    axes[0].legend(loc='upper right', ncol=2, fontsize=7)

    categories = ['四周期短试 A', '四周期短试 B']
    chosen = [audits[0], audits[2]]
    xx = [0., 1.]
    width = .32
    for offset, role, label, color in [(-width / 2, 'ros_setpoint', 'Setpoint', PROPOSED),
                                       (width / 2, 'pid', 'PID', REFERENCE)]:
        heights = [audit['joined'][role]['max_receipt_gap_s'] for audit in chosen]
        axes[1].bar([x + offset for x in xx], heights, width=width,
                    color=color, label=label)
        for x, height in zip(xx, heights):
            axes[1].text(x + offset, height + .035, f'{height:.2f}',
                         ha='center', va='bottom', fontsize=8)
    axes[1].axhline(.30, color=WARNING, ls='--', lw=1., label='短探针参考门 0.30 s')
    axes[1].set_xticks(xx, categories)
    axes[1].set_ylabel('独立接收最大间隔 / s')
    axes[1].set_ylim(0., 2.05)
    axes[1].grid(axis='y', alpha=.35)
    axes[1].legend(loc='upper right', fontsize=7, ncol=3)
    add_panel_labels(axes)
    fig.suptitle('同次 DDS 接收与飞越夹具回调等待的分离', y=.985, fontsize=11)
    fig.text(.5, .015,
             '合成短探针：独立接收≠共享执行器观察；四周期试验不是完整巡检或现场时序验收。',
             ha='center', va='bottom', fontsize=8, color=NEUTRAL)
    fig.subplots_adjust(left=.17, right=.98, bottom=.19, top=.87, hspace=.48)
    paths = save_figure(fig, out_base)
    plt.close(fig)
    return paths


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', action='append', required=True, type=Path)
    parser.add_argument('--output-base', required=True, type=Path)
    args = parser.parse_args()
    print('\n'.join(str(path) for path in plot(args.run, args.output_base)))


if __name__ == '__main__':
    main()

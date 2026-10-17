#!/usr/bin/env python3
"""Plot same-run PVS feeder work and algorithm callback budget diagnostics."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import matplotlib.pyplot as plt

from thesis_plot_style import (BASELINE_1, NEUTRAL, PROPOSED, REFERENCE,
                               WARNING, add_panel_labels, apply_thesis_style,
                               figure_size, save_figure)


def rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline='', encoding='utf-8') as stream:
        return list(csv.DictReader(stream))


def plot(run: Path, output_base: Path) -> list[Path]:
    feeder = rows(run / 'pvs_fixture/pvs_trace.csv')
    mapped = rows(run / 'pvs_fixture/fixture_source_wall_map.csv')
    algorithm = [json.loads(line) for line in
                 (run / 'algorithm_callback_timing.jsonl').read_text(encoding='utf-8').splitlines()]
    if len(feeder) != len(mapped) or len(feeder) < 2 or not algorithm:
        raise ValueError('incomplete same-run timing input')
    work = [float(row['tick_work_duration_s']) for row in feeder[:-1]]
    next_gap = [float(b['magnetic_publish_after_monotonic_s'])
                - float(a['magnetic_publish_after_monotonic_s'])
                for a, b in zip(mapped, mapped[1:])]
    apply_thesis_style(layout='full')
    fig, axes = plt.subplots(2, 1, figsize=figure_size('full', height=5.3))
    axes[0].scatter(work, next_gap, color=PROPOSED, s=23, alpha=.82,
                    edgecolors='white', linewidths=.3)
    axes[0].axvline(.1, color=REFERENCE, ls='--', lw=.9, label='名义供数周期 0.1 s')
    axes[0].axhline(.25, color=WARNING, ls=':', lw=.9, label='输入短探针参考 0.25 s')
    axes[0].set(xlabel='本周期供数器工作耗时 / s',
                ylabel='下次磁测发布间隔 / s',
                title='供数器自身长周期与后续发布空档同次出现')
    axes[0].set_xlim(-.015, max(1.12, max(work) + .06))
    axes[0].set_ylim(0., max(1.0, max(next_gap) + .08))
    axes[0].legend(loc='lower right', fontsize=7)
    axes[0].grid(alpha=.3)

    xx = list(range(1, len(algorithm) + 1))
    step = [float(row['step_duration_s'] or 0.) for row in algorithm]
    monitor = [float(row['base_publish_duration_s'] or 0.) for row in algorithm]
    other = [max(0., float(row['tick_duration_s']) - s - m)
             for row, s, m in zip(algorithm, step, monitor)]
    axes[1].bar(xx, step, color=PROPOSED, label='算法步进')
    axes[1].bar(xx, monitor, bottom=step, color=BASELINE_1, label='完整状态发布')
    axes[1].bar(xx, other, bottom=[s + m for s, m in zip(step, monitor)],
                color=NEUTRAL, label='其他回调开销')
    axes[1].axhline(.1, color=WARNING, ls='--', lw=.9, label='名义算法周期 0.1 s')
    axes[1].set(xlabel='算法回调序号', ylabel='单次回调墙钟耗时 / s',
                title='长尾不仅来自算法步进，状态发布亦占显著时长')
    axes[1].set_xticks(xx[::2] if len(xx) > 12 else xx)
    axes[1].legend(loc='upper left', fontsize=7, ncol=2)
    axes[1].grid(axis='y', alpha=.3)
    add_panel_labels(axes)
    fig.suptitle('分进程实时 PVS 短试的双端节拍预算', y=.99, fontsize=11)
    fig.text(.5, .011,
             '同次合成短试；算法状态发布启用 cProfile，耗时含诊断开销；非目标平台 WCET。',
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

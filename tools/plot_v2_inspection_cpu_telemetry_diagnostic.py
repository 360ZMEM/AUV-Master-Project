#!/usr/bin/env python3
"""Plot isolated ROS callback CPU cost and the still-failing output interval."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from thesis_plot_style import PROPOSED, REFERENCE, WARNING, apply_thesis_style, figure_size, save_figure


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'AUV-Master-Mag/results/v2/inspection_process_cpu_wall_20260927'
STEM = 'inspection_callback_cpu_and_output_gap'


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]


def main() -> None:
    source_paths = []
    trials = (
        ('prewarm5_affinity_5_3_4', '原发布频率', REFERENCE),
        ('telemetry05_5_3_4', '监控最短间隔 0.5 s', PROPOSED),
    )
    apply_thesis_style(base_font_size=8.4)
    fig, (ax, bx) = plt.subplots(2, 1, figsize=figure_size(height=4.2),
                                 constrained_layout=True,
                                 gridspec_kw={'height_ratios': [1.05, 1.]})
    for dirname, label, color in trials:
        path = BASE / dirname / 'algorithm_callback_timing.jsonl'
        source_paths.append(path)
        data = rows(path)
        ax.scatter([r['tick_duration_s'] for r in data],
                   [r['tick_cpu_duration_s'] for r in data], s=16,
                   alpha=.65, color=color, label=f'{label}（独立运行）')
    ax.plot([0, .85], [0, .85], color='0.35', lw=.8, ls='--', label='CPU 时间＝墙钟时间')
    ax.axvline(.5, color=WARNING, ls=':', lw=1.)
    ax.set(xlim=(0, .84), ylim=(0, .84), xlabel='单次决策回调墙钟耗时 / s',
           ylabel='同线程 CPU 耗时 / s',
           title='(a) 回调长尾主要占用 CPU；降低监控频率仍有长尾')
    ax.legend(loc='upper left', fontsize=6.8)
    ax.grid(alpha=.22)

    run = BASE / 'telemetry05_budget_each_tick_8cpu_5_3_4'
    source_paths.extend((run / 'events.csv', run / 'summary.json'))
    summary = json.loads((run / 'summary.json').read_text(encoding='utf-8'))
    assert summary['liveness_passed'] is False
    with (run / 'events.csv').open(newline='', encoding='utf-8') as stream:
        setpoints = [r for r in csv.DictReader(stream)
                     if r['phase'] == 'healthy' and r['topic'] == 'setpoint']
    times = [float(r['elapsed_s']) - float(setpoints[0]['elapsed_s']) for r in setpoints]
    speeds = [float(r['speed_mps']) for r in setpoints]
    gaps = [(times[i + 1] - times[i], i) for i in range(len(times) - 1)]
    largest_gap, gap_index = max(gaps)
    bx.axvspan(times[gap_index], times[gap_index + 1], color=WARNING, alpha=.13)
    bx.scatter(times, speeds, color=PROPOSED, marker='o', s=15,
               label='收到的算法 Setpoint')
    bx.scatter([times[i] for i, speed in enumerate(speeds) if speed == 0.],
               [0.] * sum(speed == 0. for speed in speeds),
               color=WARNING, marker='x', s=25, label='健康时窗内零速／撤权')
    bx.annotate(f'最长输出缺口 {largest_gap:.3f} s',
                xy=((times[gap_index] + times[gap_index + 1]) / 2., .18),
                xytext=(.48, .65), textcoords='axes fraction',
                arrowprops={'arrowstyle': '->', 'lw': .7}, ha='center', fontsize=7.1)
    bx.set(xlim=(-.12, max(times) + .12), ylim=(-.035, .39),
           xlabel='另一趟八核允许短探针的健康时窗 / s',
           ylabel='目标速度 / (m/s)',
           title=f'(b) 输入最大发送缺口 {summary["healthy_fixture_sensor_max_gap_s"]:.3f} s，严格健康输出门仍失败')
    bx.legend(loc='lower left', fontsize=6.8)
    bx.grid(alpha=.22)
    figures = BASE / 'figures'
    figures.mkdir(parents=True, exist_ok=True)
    save_figure(fig, figures / STEM, dpi=500)
    plt.close(fig)
    result = {
        'role': 'three_independent_isolated_host_trials_not_target_jetson_or_full_mission',
        'eight_cpu_output_gap_s': largest_gap,
        'eight_cpu_fixture_max_gap_s': summary['healthy_fixture_sensor_max_gap_s'],
        'eight_cpu_healthy_positive_setpoints': summary['healthy_positive_setpoints'],
        'eight_cpu_healthy_setpoints': summary['healthy_setpoints'],
        'inputs_sha256': {str(p.relative_to(ROOT)): sha(p) for p in source_paths},
        'figure_png_sha256': sha(figures / f'{STEM}.png'),
        'figure_pdf_sha256': sha(figures / f'{STEM}.pdf'),
        'plot_script_sha256': sha(Path(__file__)),
    }
    (BASE / f'{STEM}.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n',
                                       encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()

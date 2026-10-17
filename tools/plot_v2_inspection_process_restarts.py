#!/usr/bin/env python3
"""Defense-readable view of independent synthetic mission invocations."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

from thesis_plot_style import (BASELINE_2, PROPOSED, REFERENCE, WARNING,
                               apply_thesis_style, figure_size, save_figure)


ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / 'AUV-Master-Mag/results/v2/inspection_repeatability_20260927'
PUBLICATION = ROOT / 'AUV-Master-Mag/docs/v2/publication/fwhm_v2_experiment_results'
STEM = '37_inspection_process_restart_diagnostics'


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(directory: str, case: str, seed: int) -> tuple[dict, dict[str, np.ndarray], Path]:
    prefix = RUNS / directory / f'{case}_seed_{seed}'
    summary = json.loads(prefix.with_name(prefix.name + '_summary.json').read_text(encoding='utf-8'))
    path = prefix.with_suffix('.csv')
    with path.open(newline='', encoding='utf-8') as stream:
        rows = list(csv.DictReader(stream))
    columns = {name: np.asarray([float(row[name]) for row in rows])
               for name in ('time_s', 'x_m', 'y_m', 'rpm', 'speed_mps')}
    columns['route_observed_lateral_samples'] = np.asarray([
        float(row['route_observed_lateral_samples'] or 0) for row in rows])
    columns['mode'] = np.asarray([row['mode'] for row in rows])
    columns['stage'] = np.asarray([row['stage'] for row in rows])
    return summary, columns, path


def main() -> None:
    first, a, first_path = load('pilot_normal', 'wire', 104)
    repeat, b, repeat_path = load('normal_repeat', 'wire', 107)
    guard, c, guard_path = load('guard_loss', 'wire_guard_telemetry_loss', 105)
    switched, d, switch_path = load('identity_switch', 'wire', 106)
    if not (first['completed'] and repeat['completed'] and
            not guard['completed'] and not switched['completed']):
        raise RuntimeError('case outcomes do not match the frozen diagnostic panel')
    if guard['guard_telemetry_loss_ticks'] <= 0 or switched['first_hold_s'] is None:
        raise RuntimeError('fault evidence missing')
    guard_start = float(c['time_s'][-guard['guard_telemetry_loss_ticks']])
    hold = float(switched['first_hold_s'])
    mask_guard = (c['time_s'] >= guard_start - 20) & (c['time_s'] <= guard_start + 60)
    mask_switch = (d['time_s'] >= hold - 20) & (d['time_s'] <= hold + 60)
    hold_xy = np.array([np.interp(hold, d['time_s'], d['x_m']),
                        np.interp(hold, d['time_s'], d['y_m'])])
    displacement = np.hypot(d['x_m'] - hold_xy[0], d['y_m'] - hold_xy[1])

    apply_thesis_style(base_font_size=8.0)
    fig, axes = plt.subplots(2, 2, figsize=figure_size(height=5.8),
                             constrained_layout=True)
    ax = axes[0, 0]
    ax.axhline(6., color=REFERENCE, ls=':', lw=1.0, label='合成目标线 $y=6$ m')
    for run, label, color, linestyle, width in (
            (a, '种子 104', PROPOSED, '-', 2.1),
            (b, '种子 107', BASELINE_2, '--', 1.3)):
        ax.plot(run['x_m'], run['y_m'], color=color, ls=linestyle,
                lw=width, label=label)
    ax.set(xlim=(-255, 5), ylim=(-20, 23), xlabel='沿缆 $x$ / m', ylabel='横向 $y$ / m',
           title='(a) 独立进程的两次正常巡检')
    ax.legend(loc='upper left', fontsize=6.5, ncol=1)

    ax = axes[0, 1]
    for run, label, color, linestyle in (
            (a, '种子 104', PROPOSED, '-'),
            (b, '种子 107', BASELINE_2, '--')):
        track = ((run['stage'] == 'inspect_along_cable') &
                 (run['route_observed_lateral_samples'] > 0))
        ax.plot(run['x_m'][track], np.abs(run['y_m'][track] - 6.),
                color=color, ls=linestyle, lw=1.15, label=label)
    ax.axhline(2., color=WARNING, ls=':', lw=1.0, label='合成最大横偏示例门 2 m')
    ax.set(xlim=(0, 82), ylim=(0, 2.25), xlabel='沿缆 $x$ / m', ylabel='真实横偏 / m',
           title='(b) 正向沿缆段真值横偏')
    ax.legend(loc='upper right', fontsize=6.5)

    ax = axes[1, 0]
    ax.axvspan(0, 60, color=WARNING, alpha=.08)
    ax.axvline(0, color=WARNING, ls=':', lw=1.0)
    ax.step(c['time_s'][mask_guard] - guard_start, c['rpm'][mask_guard],
            where='post', color=PROPOSED, lw=1.4)
    ax.set(xlim=(-20, 60), xlabel='上行失鲜后仿真时间 / s', ylabel='本地 UDP 主推 / rpm',
           title=f"(c) 上行失鲜后 {guard['guard_telemetry_loss_ticks']} 周期撤权")
    ax.annotate('桥撤权，零命令', xy=(0, 0), xytext=(4, 110),
                textcoords='offset points', color=WARNING, fontsize=7)

    ax = axes[1, 1]
    ax.axvspan(0, 60, color=WARNING, alpha=.08)
    ax.axvline(0, color=WARNING, ls=':', lw=1.0)
    command_line = ax.step(d['time_s'][mask_switch] - hold, d['rpm'][mask_switch],
                           where='post', color=PROPOSED, lw=1.4, label='协议主推命令')[0]
    ax.set(xlim=(-20, 60), xlabel='目标线索改指后仿真时间 / s',
           ylabel='本地 UDP 主推 / rpm', title='(d) 零命令后仍有惯性滑行')
    drift = ax.twinx()
    after_hold = (d['time_s'] >= hold) & (d['time_s'] <= hold + 60)
    displacement_line = drift.plot(d['time_s'][after_hold] - hold, displacement[after_hold],
                                   color=WARNING, lw=1.35, label='相对 Hold 位置位移')[0]
    drift.set(ylabel='相对 Hold 位置位移 / m')
    ax.legend(handles=[command_line, displacement_line],
              loc='upper left', fontsize=6.5)

    figures = PUBLICATION / 'figures'
    save_figure(fig, figures / STEM, dpi=600)
    plt.close(fig)
    summary = {
        'role': 'synthetic_independent_process_diagnostic_figure',
        'normal_completed': [first['completed'], repeat['completed']],
        'normal_route_mae_m': [first['route_observed_lateral_mae_m'],
                               repeat['route_observed_lateral_mae_m']],
        'guard_loss_zero_udp_ticks': guard['guard_telemetry_loss_zero_udp_ticks'],
        'identity_hold_displacement_m': switched['hold_to_final_displacement_m'],
        'source_csv_sha256': {path.name: sha(path) for path in
                              (first_path, repeat_path, guard_path, switch_path)},
        'caveat': ('Four separate synthetic harness invocations, not one uninterrupted '
                   'soak or physical PC104/vehicle evidence.'),
    }
    data = PUBLICATION / 'data'
    summary_path = data / f'{STEM}_summary.json'
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n',
                            encoding='utf-8')
    (data / f'{STEM}_manifest.json').write_text(json.dumps({
        'plot_script_sha256': sha(Path(__file__)),
        'summary_sha256': sha(summary_path),
        'png_sha256': sha(figures / f'{STEM}.png'),
        'pdf_sha256': sha(figures / f'{STEM}.pdf'),
    }, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == '__main__':
    main()

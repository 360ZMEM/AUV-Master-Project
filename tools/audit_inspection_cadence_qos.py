#!/usr/bin/env python3
"""Audit five independent cadence/QoS probes without rewriting their verdicts."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

from thesis_plot_style import (PROPOSED, BASELINE_1, WARNING, REFERENCE,
                               apply_thesis_style, figure_size, save_figure)

import matplotlib.pyplot as plt


CASES = (
    ("period02_snapshot_recoverable_thread", "0.2 s 决策"),
    ("period04_snapshot_recoverable_thread", "0.4 s 决策"),
    ("period01_latest_supervisor_input", "0.1 s 最新输入"),
    ("period02_latest_supervisor_input", "0.2 s 最新输入"),
    ("period01_latest_both", "双侧最新输入"),
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def maximum_gap(times: list[float], left: float, right: float) -> float:
    points = [left, *sorted(t for t in times if left <= t < right), right]
    return max(b - a for a, b in zip(points, points[1:]))


def audit(root: Path) -> dict:
    cases = []
    for dirname, label in CASES:
        run = root / dirname
        summary_path, feeder_path, observer_path = (run / 'summary.json',
                                                     run / 'feeder_events.json',
                                                     run / 'observer_events.csv')
        summary = json.loads(summary_path.read_text(encoding='utf-8'))
        feeder = json.loads(feeder_path.read_text(encoding='utf-8'))
        with observer_path.open(encoding='utf-8', newline='') as stream:
            rows = list(csv.DictReader(stream))
        mission = [float(event['monotonic_s']) for event in feeder['events']
                   if event['event'] == 'mission']
        if len(mission) != 1:
            raise ValueError(f'{dirname}: expected exactly one mission publication')
        mission_at = mission[0]
        healthy_end = (feeder['start_monotonic_s'] + feeder['prewarm_s']
                       + feeder['healthy_s'])
        steady_start = mission_at + 1.
        if steady_start >= healthy_end:
            raise ValueError(f'{dirname}: no steady diagnostic window')
        sensor_ticks = [float(event['monotonic_s']) for event in feeder['events']
                        if event['event'] == 'sensor_tick'
                        and steady_start <= event['monotonic_s'] < healthy_end]
        setpoints = [row for row in rows if row['topic'] == 'setpoint'
                     and steady_start <= float(row['monotonic_s']) < healthy_end]
        positives = [row for row in rows if row['topic'] == 'setpoint'
                     and mission_at <= float(row['monotonic_s']) < healthy_end
                     and float(row['speed_or_thrust']) > 0.]
        first_positive_latency = (None if not positives else
                                  min(float(row['monotonic_s']) for row in positives) - mission_at)
        steady_positive = sum(float(row['speed_or_thrust']) > 0. for row in setpoints)
        cases.append({
            'run': dirname,
            'label': label,
            'strict_passed_original': summary['passed'],
            'decision_period_s': summary['algorithm_period_s'],
            'supervisor_latest_input_qos': bool(summary.get('latest_supervisor_input_qos', False)),
            'algorithm_latest_navigation_qos': summary['latest_navigation_qos'],
            'healthy_input_max_gap_s': summary['phases']['healthy']['feeder_max_gap_s'],
            'healthy_final_output_max_gap_s': summary['phases']['healthy']['setpoint_max_gap_s'],
            'healthy_positive': summary['phases']['healthy']['setpoint_positive'],
            'healthy_final_count': summary['phases']['healthy']['setpoint_count'],
            'first_positive_after_mission_s': first_positive_latency,
            'steady_window_start_after_mission_s': 1.,
            'steady_window_duration_s': healthy_end - steady_start,
            'steady_input_count': len(sensor_ticks),
            'steady_input_max_gap_s': maximum_gap(sensor_ticks, steady_start, healthy_end),
            'steady_final_count': len(setpoints),
            'steady_final_positive': steady_positive,
            'steady_final_max_gap_s': maximum_gap(
                [float(row['monotonic_s']) for row in setpoints], steady_start, healthy_end),
            'dropout_guard_setpoint_zero': summary['phases']['dropout']['guarded_setpoint_zero'],
            'dropout_guard_setpoint_count': summary['phases']['dropout']['guarded_setpoint_count'],
            'dropout_guard_effort_zero': summary['phases']['dropout']['guarded_effort_zero'],
            'dropout_guard_effort_count': summary['phases']['dropout']['guarded_effort_count'],
            'summary_sha256': sha256(summary_path),
            'feeder_sha256': sha256(feeder_path),
            'observer_sha256': sha256(observer_path),
        })
    return {
        'role': 'retrospective_diagnostic_only_original_verdicts_unchanged',
        'steady_window_definition': 'from 1.0 s after actual mission publication to end of fixed healthy phase',
        'strict_gate': {'healthy_input_max_gap_s': .25,
                        'healthy_final_output_max_gap_s': .3,
                        'healthy_final_positive_fraction': 1.},
        'independent_runs_not_paired': True,
        'all_original_strict_passed': all(case['strict_passed_original'] for case in cases),
        'all_steady_positive': all(case['steady_final_positive'] == case['steady_final_count']
                                   and case['steady_final_count'] > 0 for case in cases),
        'cases': cases,
    }


def plot(audit_data: dict, out_base: Path) -> None:
    cases = audit_data['cases']
    apply_thesis_style(layout='full')
    fig, axes = plt.subplots(1, 3, figsize=figure_size('full', height=4.15),
                             sharey=True, gridspec_kw={'width_ratios': [1., 1., 1.22]})
    y = list(range(len(cases)))
    colors = [BASELINE_1, BASELINE_1, PROPOSED, PROPOSED, PROPOSED]
    metrics = (
        ('healthy_input_max_gap_s', '供数最大空档 / s', .25, .4),
        ('healthy_positive', '正向输出比例', 1., 1.08),
        ('healthy_final_output_max_gap_s', '最终输出最大空档 / s', .3, 1.27),
    )
    for ax, (key, title, threshold, xmax) in zip(axes, metrics):
        values = ([case[key] / case['healthy_final_count'] for case in cases]
                  if key == 'healthy_positive' else [case[key] for case in cases])
        ax.barh(y, values, color=colors, edgecolor=REFERENCE, linewidth=.6, height=.62)
        ax.axvline(threshold, color=WARNING, linestyle='--', linewidth=1.1)
        for yi, value in zip(y, values):
            inside = value > xmax * .74
            ax.text(value - xmax * .015 if inside else value + xmax * .015, yi,
                    f'{value:.3f}' if key != 'healthy_positive' else f'{value:.0%}',
                    va='center', ha='right' if inside else 'left',
                    color='white' if inside else REFERENCE, fontsize=7)
        ax.set_xlim(0., xmax)
        ax.set_title(title, fontsize=9)
        ax.grid(axis='x')
        ax.invert_yaxis()
    axes[0].set_yticks(y, [case['label'] for case in cases])
    axes[1].set_xlabel('虚线：全部正向')
    axes[0].set_xlabel('虚线：≤ 0.25 s')
    axes[2].set_xlabel('虚线：≤ 0.30 s')
    fig.suptitle('决策节拍与最新值队列：独立进程连续性诊断', fontsize=10.5, y=.98)
    fig.text(.5, .025, '五次独立合成运行；原严格门全部失败。首指令建链另列诊断，不据此改写原判定。',
             ha='center', fontsize=7.5, color=REFERENCE)
    fig.subplots_adjust(left=.24, right=.98, top=.86, bottom=.19, wspace=.15)
    save_figure(fig, out_base)
    plt.close(fig)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--results-dir', required=True, type=Path)
    args = parser.parse_args()
    results = audit(args.results_dir)
    (args.results_dir / 'cadence_qos_audit.json').write_text(
        json.dumps(results, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    figure_base = args.results_dir / 'figures' / 'inspection_cadence_qos_diagnostic'
    figure_base.parent.mkdir(parents=True, exist_ok=True)
    plot(results, figure_base)
    print(json.dumps({'cases': len(results['cases']),
                      'all_original_strict_passed': results['all_original_strict_passed'],
                      'all_steady_positive': results['all_steady_positive'],
                      'figure': str(figure_base) + '.png'}))

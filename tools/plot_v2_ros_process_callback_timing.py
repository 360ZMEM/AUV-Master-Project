#!/usr/bin/env python3
"""Plot the isolated installed ROS process timing failure for defense diagnosis."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

from thesis_plot_style import PROPOSED, REFERENCE, WARNING, apply_thesis_style, figure_size, save_figure


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'AUV-Master-Mag/results/v2/inspection_process_wallclock_20260927'
RUN = BASE / 'prewarm5_affinity_5_3_4'
STEM = 'ros_process_callback_freshness_diagnostic'


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    summary_path = RUN / 'summary.json'
    events_path = RUN / 'events.csv'
    trace_path = RUN / 'algorithm_callback_timing.jsonl'
    summary = json.loads(summary_path.read_text(encoding='utf-8'))
    with events_path.open(newline='', encoding='utf-8') as stream:
        events = list(csv.DictReader(stream))
    ticks = [json.loads(line) for line in trace_path.read_text(encoding='utf-8').splitlines()]
    assert summary['trace_algorithm'] and summary['required_prewarm_s'] == 5.
    assert not summary['liveness_passed'] and summary['healthy_fixture_sensor_max_gap_s'] < .5
    assert summary['healthy_setpoint_max_gap_s'] > .5
    first_healthy = min(float(row['elapsed_s']) for row in events if row['phase'] == 'healthy')
    first_hold = min(float(row['elapsed_s']) for row in events
                     if row['phase'] == 'healthy' and row['topic'] == 'setpoint'
                     and row['speed_mps'] != '' and float(row['speed_mps']) == 0.)
    end = first_healthy + float(summary['healthy_s'])
    selected = [row for row in ticks if first_healthy - .1 <=
                row['tick_start_monotonic_s'] - summary['start_monotonic_s'] <= end + .1]
    t = np.array([row['tick_start_monotonic_s'] - summary['start_monotonic_s'] - first_healthy
                  for row in selected])
    before = np.array([row['navigation_age_before_s'] for row in selected], dtype=float)
    after = np.array([row['navigation_age_after_s'] for row in selected], dtype=float)
    total = np.array([row['tick_duration_s'] for row in selected])
    step = np.array([row['step_duration_s'] or 0. for row in selected])
    publish = np.array([row['publish_tracking_duration_s'] or 0. for row in selected])
    other = np.maximum(total - step - publish, 0.)
    sensor_t = np.array([float(row['elapsed_s']) - first_healthy for row in events
                         if row['phase'] == 'healthy' and row['topic'] == 'fixture_sensor_publish'])
    setpoint = [(float(row['elapsed_s']) - first_healthy, float(row['speed_mps']))
                for row in events if row['phase'] == 'healthy' and row['topic'] == 'setpoint']
    setpoint_t, speeds = map(np.array, zip(*setpoint))
    efforts = [(float(row['elapsed_s']) - first_healthy, float(row['thrust_percent']))
               for row in events if row['phase'] == 'healthy' and row['topic'] == 'effort']
    effort_t, effort_pct = map(np.array, zip(*efforts))
    assert len(selected) > 10 and len(sensor_t) > 10 and len(setpoint_t) > 10
    assert np.any((before < .5) & (after > .5))

    apply_thesis_style(base_font_size=8.2)
    fig, axes = plt.subplots(3, 1, figsize=figure_size(height=4.75), sharex=True,
                             constrained_layout=True,
                             gridspec_kw={'height_ratios': [1.3, 1.3, .8]})
    a, b, c = axes
    hold_t = first_hold - first_healthy
    for ax in axes:
        ax.axvspan(hold_t, 5., color=WARNING, alpha=.09, lw=0)
        ax.axvline(hold_t, color=WARNING, lw=.85, ls=':')

    a.plot(t, before, color=REFERENCE, lw=1., marker='o', ms=2., label='进入回调前')
    a.plot(t, after, color=PROPOSED, lw=1.15, marker='o', ms=2., label='退出回调后')
    a.axhline(.5, color=WARNING, lw=.9, ls='--', label='0.5 s 新鲜度门')
    a.set(ylabel='导航年龄 / s', ylim=(0, 1.4), title='(a) 输入已发布，回调尾延迟跨过新鲜度门')
    a.legend(loc='upper left', ncol=3, fontsize=6.6)

    width = .055
    b.bar(t, step, width=width, color=PROPOSED, label='算法步进')
    b.bar(t, publish, bottom=step, width=width, color=REFERENCE, label='跟踪／诊断发布')
    b.bar(t, other, bottom=step + publish, width=width, color='#a5a5a5', label='其余／调度')
    b.axhline(.1, color=WARNING, ls='--', lw=.9, label='10 Hz 周期')
    b.set(ylabel='单次回调 / s', ylim=(0, .86), title='(b) 最慢一次约 0.790 s，包含算法与发布')
    b.legend(loc='upper left', ncol=2, fontsize=6.6)

    c.vlines(sensor_t, 0., .17, color=REFERENCE, lw=.85, label='夹具导航／磁测发布')
    c.step(setpoint_t, speeds, where='post', color=PROPOSED, lw=1.25,
           label='算法目标速度')
    c.scatter(setpoint_t, speeds, color=PROPOSED, s=7, zorder=3)
    c_effort = c.twinx()
    c_effort.plot(effort_t, effort_pct, color=WARNING, lw=.9, marker='s', ms=2.,
                  alpha=.85, label='PID 推力计算')
    c_effort.set(ylabel='PID 推力 / %', ylim=(-1., max(17., float(np.max(effort_pct)) * 1.13)))
    c.set(xlabel='首个健康事件后的墙钟时间 / s', ylabel='目标速度 / (m/s)',
          xlim=(0, 5.), ylim=(-.04, .37),
          title='(c) 目标速度与 PID 计算存在传播时差')
    handles, labels = c.get_legend_handles_labels()
    effort_handles, effort_labels = c_effort.get_legend_handles_labels()
    c.legend(handles + effort_handles, labels + effort_labels,
             loc='upper right', ncol=2, fontsize=6.3)
    figures = BASE / 'figures'
    figures.mkdir(parents=True, exist_ok=True)
    save_figure(fig, figures / STEM, dpi=500)
    plt.close(fig)

    payload = {
        'role': 'isolated_ros_process_short_wallclock_failure_diagnostic',
        'run': RUN.name,
        'healthy_fixture_sensor_max_gap_s': summary['healthy_fixture_sensor_max_gap_s'],
        'healthy_setpoint_max_gap_s': summary['healthy_setpoint_max_gap_s'],
        'maximum_tick_duration_s': max(row['tick_duration_s'] for row in selected),
        'first_zero_setpoint_relative_s': hold_t,
        'source_summary_sha256': sha(summary_path),
        'source_events_sha256': sha(events_path),
        'source_callback_trace_sha256': sha(trace_path),
        'figure_png_sha256': sha(figures / f'{STEM}.png'),
        'figure_pdf_sha256': sha(figures / f'{STEM}.pdf'),
        'plot_script_sha256': sha(Path(__file__)),
        'scope': 'synthetic stationary fixture, not a full-route or physical acceptance',
    }
    (BASE / f'{STEM}.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n',
                                       encoding='utf-8')
    print(json.dumps(payload, ensure_ascii=False))


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Plot a short synthetic ROS/PVS navigation-freshness timing diagnostic."""

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
BASE = ROOT / 'AUV-Master-Mag/results/v2/inspection_wait_bound_20260927'
RUN = BASE / 'measured_5s'
STEM = 'host_navigation_freshness_diagnostic'


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    csv_path = RUN / 'wire_seed_101.csv'
    summary_path = RUN / 'wire_seed_101_summary.json'
    with csv_path.open(newline='', encoding='utf-8') as stream:
        rows = list(csv.DictReader(stream))
    summary = json.loads(summary_path.read_text(encoding='utf-8'))
    t = np.array([float(row['time_s']) for row in rows])
    before = np.array([float(row['nav_age_before_tick_s']) for row in rows])
    after = np.array([float(row['nav_age_after_tick_s']) for row in rows])
    rpm = np.array([int(row['rpm']) for row in rows])
    recovery_t = float(summary['first_recovery_required_s'])
    assert (len(rows) == summary['ticks'] and np.max(before) < .5
            and np.max(after) > .5
            and summary['first_recovery_reason'] == 'hold_navigation_unavailable')
    assert np.all(rpm[t >= recovery_t] == 0)

    apply_thesis_style(base_font_size=8.4)
    fig, axes = plt.subplots(2, 1, sharex=True, figsize=figure_size(height=3.45),
                             constrained_layout=True)
    axes[0].plot(t, before, color=REFERENCE, lw=1.25, marker='o', ms=2.3,
                 label='决策前导航年龄')
    axes[0].plot(t, after, color=PROPOSED, lw=1.35, marker='o', ms=2.3,
                 label='决策后导航年龄')
    axes[0].axhline(.5, color=WARNING, lw=1., ls='--', label='候选新鲜度门 0.5 s')
    axes[0].fill_between(t, .5, after, where=after > .5, color=WARNING, alpha=.18)
    axes[0].set(ylabel='墙钟导航年龄 / s', ylim=(0, 1.28),
                title='(a) 一次决策跨过导航新鲜度门')
    axes[0].legend(loc='upper left', fontsize=6.7, ncol=2)
    axes[1].step(t, rpm, where='post', color=PROPOSED, lw=1.3, label='本地 UDP 主推转速')
    axes[1].axvspan(recovery_t, t[-1] + .125, color=WARNING, alpha=.12,
                    label='恢复处置锁存')
    axes[1].set(xlabel='短探针仿真时间 / s', ylabel='协议主推 / RPM',
                xlim=(t[0] - .125, t[-1] + .125), ylim=(-7, max(rpm) * 1.12),
                title='(b) 锁存后持续零主推；短探针不评价到端')
    axes[1].legend(loc='upper right', fontsize=6.7)
    figures = BASE / 'figures'
    figures.mkdir(parents=True, exist_ok=True)
    save_figure(fig, figures / STEM, dpi=500)
    plt.close(fig)

    payload = {
        'role': 'one_short_synthetic_host_timing_failure_diagnostic',
        'ticks': len(rows),
        'first_recovery_required_s': recovery_t,
        'first_recovery_reason': summary['first_recovery_reason'],
        'maximum_navigation_age_before_tick_s': float(np.max(before)),
        'maximum_navigation_age_after_tick_s': float(np.max(after)),
        'maximum_tick_wall_elapsed_s': float(summary['wall_tick_max_s']),
        'post_recovery_zero_udp_ticks': int(np.sum(t >= recovery_t)),
        'source_csv_sha256': sha(csv_path),
        'source_summary_sha256': sha(summary_path),
        'figure_png_sha256': sha(figures / f'{STEM}.png'),
        'figure_pdf_sha256': sha(figures / f'{STEM}.pdf'),
        'plot_script_sha256': sha(Path(__file__)),
        'interpretation': ('This is a 5 s simulated-time probe on a variable-load VM, '
                           'not a full inspection or vehicle timing qualification.'),
    }
    (BASE / f'{STEM}.json').write_text(json.dumps(payload, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(payload, ensure_ascii=False))


if __name__ == '__main__':
    main()

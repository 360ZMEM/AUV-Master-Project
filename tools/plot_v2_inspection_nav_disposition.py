#!/usr/bin/env python3
"""Plot perception versus execution after a transient navigation dropout."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

from thesis_plot_style import (BASELINE_2, PROPOSED, WARNING,
                               apply_thesis_style, figure_size, save_figure)


ROOT = Path(__file__).resolve().parents[1]
RUN = (ROOT / 'AUV-Master-Mag/results/v2/inspection_recovery_20260927/'
       'navigation_dropout')
PUBLICATION = ROOT / 'AUV-Master-Mag/docs/v2/publication/fwhm_v2_experiment_results'
STEM = '38_inspection_nav_dropout_disposition'
PREFIX = 'wire_navigation_dropout_seed_108'


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    audit_path = PUBLICATION / 'data/inspection_v2_transient_nav_recovery_audit_20260927.json'
    audit = json.loads(audit_path.read_text(encoding='utf-8'))
    if not audit['checks_passed'] or audit['autonomous_resume_observed']:
        raise RuntimeError('saved trace does not satisfy the conservative recovery disposition')
    csv_path = RUN / f'{PREFIX}.csv'
    with csv_path.open(newline='', encoding='utf-8') as stream:
        rows = list(csv.DictReader(stream))
    t = np.asarray([float(row['time_s']) for row in rows])
    x = np.asarray([float(row['x_m']) for row in rows])
    y = np.asarray([float(row['y_m']) for row in rows])
    rpm = np.asarray([float(row['rpm']) for row in rows])
    tracking = np.asarray([row['mode'] == 'track' for row in rows], dtype=float)
    authorized = np.asarray([row['autonomous_execution_authorized'] == 'True'
                             for row in rows], dtype=float)
    start, end = audit['fault_window_s']
    near = (t >= start - 15.) & (t <= end + 20.)
    after = t >= start
    hold_x = np.interp(start, t, x)
    hold_y = np.interp(start, t, y)
    drift = np.hypot(x[after] - hold_x, y[after] - hold_y)

    apply_thesis_style(base_font_size=8.0)
    fig, axes = plt.subplots(3, 1, figsize=figure_size(height=6.1),
                             constrained_layout=True)
    for ax in axes[:2]:
        ax.axvspan(start, end, color=WARNING, alpha=.12)
        ax.axvline(start, color=WARNING, lw=.9, ls=':')
        ax.axvline(end, color=WARNING, lw=.9, ls=':')
        ax.set_xlim(start - 15., end + 20.)

    axes[0].step(t[near], tracking[near], where='post', color=PROPOSED, lw=1.8,
                 label='感知状态为 Track')
    axes[0].step(t[near], authorized[near], where='post', color=BASELINE_2,
                 lw=1.2, ls='--', label='桥允许自治执行')
    axes[0].set(ylim=(-.08, 1.2), yticks=[0, 1], ylabel='状态 / 0, 1',
                title='(a) 导航恢复后感知继续跟踪，执行许可仍被锁存拒绝')
    axes[0].legend(loc='upper right', fontsize=7, ncol=2)

    axes[1].step(t[near], rpm[near], where='post', color=PROPOSED, lw=1.35)
    axes[1].set(xlabel='仿真时间 / s', ylabel='本地 UDP 主推 / rpm',
                title='(b) 无效导航及后续恢复阶段都维持零命令')
    axes[1].annotate('15 s 无效导航', xy=((start + end) / 2., 0),
                     xytext=(0, 18), textcoords='offset points', ha='center',
                     fontsize=7, color=WARNING)

    axes[2].plot(t[after] - start, drift, color=WARNING, lw=1.4)
    axes[2].set(xlim=(0., t[-1] - start), ylim=(0., max(5.3, drift.max() * 1.1)),
                xlabel='首次 Hold 后仿真时间 / s',
                ylabel='相对首次 Hold 位置位移 / m',
                title='(c) 零推进仍有滑行；进程持续报告 RECOVERY_REQUIRED')
    axes[2].annotate(f'{drift[-1]:.2f} m', xy=(t[-1] - start, drift[-1]),
                     xytext=(-48, -17), textcoords='offset points',
                     fontsize=7, color=WARNING)

    figures = PUBLICATION / 'figures'
    save_figure(fig, figures / STEM, dpi=600)
    plt.close(fig)
    summary = {
        'role': 'synthetic_navigation_dropout_safe_disposition_figure',
        'fault_window_s': [start, end],
        'after_fault_track_rows': audit['after_fault_track_rows'],
        'after_fault_authorized_rows': audit['after_fault_authorized_rows'],
        'after_fault_zero_udp_rows': audit['after_fault_zero_udp_rows'],
        'post_hold_displacement_m': float(drift[-1]),
        'csv_sha256': sha(csv_path),
        'audit_sha256': sha(audit_path),
        'caveat': 'One synthetic NaN navigation fault; no physical vehicle or PC104.',
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

#!/usr/bin/env python3
"""Show why localization evidence is not autonomous command authority."""

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
SOURCE = ROOT / 'AUV-Master-Mag/results/v2/operational_status/guard_loss_verified/wire_guard_telemetry_loss_seed_101.csv'
PUBLICATION = ROOT / 'AUV-Master-Mag/docs/v2/publication/fwhm_v2_experiment_results'
STEM = '36_localization_vs_autonomy_authority'


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    with SOURCE.open(newline='', encoding='utf-8') as stream:
        rows = list(csv.DictReader(stream))
    times = np.array([float(row['time_s']) for row in rows])
    authorized = np.array([row['autonomous_execution_authorized'] == 'True' for row in rows], dtype=int)
    localized = np.array([row['operational_localization_status'] == 'LOCALIZED_DEPTH_PENDING' for row in rows], dtype=int)
    rpm = np.array([float(row['rpm']) for row in rows])
    revoked = np.flatnonzero(np.diff(authorized) == -1)
    assert len(revoked) == 1
    transition = float(times[revoked[0] + 1])
    assert all(row['authority_reason'] == 'AMD_UPLINK_STALE' for row in rows[revoked[0] + 1:])
    assert np.all(rpm[revoked[0] + 1:] == 0.)
    assert np.all(localized[revoked[0] + 1:] == 1)
    view = (times >= transition - 12.) & (times <= transition + 24.)

    apply_thesis_style(base_font_size=8.5)
    fig, axes = plt.subplots(2, 1, sharex=True, figsize=figure_size(height=4.1),
                             gridspec_kw={'height_ratios': [1.2, 1]}, constrained_layout=True)
    for ax in axes:
        ax.axvspan(transition, transition + 24., color=WARNING, alpha=.09)
        ax.axvline(transition, color=WARNING, ls=':', lw=1.2)
        ax.grid(axis='y', alpha=.2)
    axes[0].step(times[view], localized[view] + .08, where='post', color=REFERENCE,
                 lw=1.6, label='横向定位状态有效')
    axes[0].step(times[view], authorized[view] - .08, where='post', color=PROPOSED,
                 lw=1.8, label='桥允许自治指令')
    axes[0].set(ylim=(-.2, 1.3), yticks=[0, 1], yticklabels=['否', '是'],
                ylabel='状态', title='(a) 定位证据与自治执行许可分离')
    axes[0].legend(loc='center right', ncol=1, fontsize=7.4)
    axes[0].annotate('上行失鲜，桥撤权', (transition, .48), xytext=(7, 0),
                     textcoords='offset points', color=WARNING, fontsize=7.5)
    axes[1].step(times[view], rpm[view], where='post', color=PROPOSED, lw=1.7)
    axes[1].set(xlim=(transition-12., transition+24.), ylim=(-10, max(220., rpm[view].max()*1.1)),
                xlabel='仿真时间 / s', ylabel='本地 UDP 主推 / rpm',
                title='(b) 撤权后的协议命令主推为零')
    figures = PUBLICATION / 'figures'
    save_figure(fig, figures / STEM, dpi=600)
    plt.close(fig)
    summary = {
        'role': 'synthetic_ros_pid_guard_local_udp_pvs_status_boundary',
        'transition_time_s': transition,
        'authorized_before_cycles': int(authorized[:revoked[0]+1].sum()),
        'revoked_after_cycles': int(len(rows)-revoked[0]-1),
        'localization_still_valid_after_cycles': int(localized[revoked[0]+1:].sum()),
        'zero_udp_rpm_after_cycles': int(np.count_nonzero(rpm[revoked[0]+1:] == 0.)),
        'source_csv_sha256': sha(SOURCE),
        'caveat': 'Synthetic sonar and telemetry; zero command is not stationary vehicle or physical PC104 verification.',
    }
    data = PUBLICATION / 'data'
    summary_path = data / f'{STEM}_summary.json'
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (data / f'{STEM}_manifest.json').write_text(json.dumps({
        'plot_script_sha256': sha(Path(__file__)),
        'summary_sha256': sha(summary_path),
        'png_sha256': sha(figures / f'{STEM}.png'),
        'pdf_sha256': sha(figures / f'{STEM}.pdf'),
    }, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Defense plot: observed old PID tail and independent new bridge gate proof."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

from thesis_plot_style import PROPOSED, REFERENCE, WARNING, apply_thesis_style, figure_size, save_figure


ROOT = Path(__file__).resolve().parents[1]
WALLCLOCK = ROOT / 'AUV-Master-Mag/results/v2/inspection_process_wallclock_20260927'
BASE = ROOT / 'AUV-Master-Mag/results/v2/inspection_bridge_setpoint_gate_20260927'
RUN = BASE / 'loopback_b'
STEM = 'bridge_setpoint_provenance_gate'


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    audit_path = WALLCLOCK / 'observable_command_tail_audit.json'
    summary_path = RUN / 'summary.json'
    packets_path = RUN / 'packets.json'
    audit = json.loads(audit_path.read_text(encoding='utf-8'))['cases'][0]
    summary = json.loads(summary_path.read_text(encoding='utf-8'))
    packets = {row['stage']: row for row in json.loads(packets_path.read_text(encoding='utf-8'))}
    assert audit['run'] == 'prewarm5_affinity_5_3_4'
    assert summary['stale_setpoint_fresh_pid_zero'] and summary['stale_setpoint_keepalive_zero']
    assert summary['explicit_hold_fresh_pid_zero']
    assert audit['positive_effort_count_after_first_zero_setpoint'] == 2

    first_sp = audit['last_positive_setpoint_elapsed_s']
    zero_sp_t = audit['positive_setpoint_to_zero_setpoint_s']
    zero_effort_t = audit['positive_setpoint_to_first_zero_effort_s']
    effort_t = [row['delay_from_last_positive_setpoint_s']
                for row in audit['positive_efforts_after_last_positive_setpoint']]
    stages = ('fresh_setpoint_fresh_pid', 'stale_setpoint_fresh_pid',
              'stale_setpoint_keepalive', 'explicit_hold_fresh_pid')
    values = [float(packets[stage]['payload']['thrust']) for stage in stages]
    assert values[0] > 0 and values[1:] == [0., 0., 0.]

    apply_thesis_style(base_font_size=8.5)
    fig, (ax, bx) = plt.subplots(2, 1, figsize=figure_size(height=4.05),
                                 constrained_layout=True,
                                 gridspec_kw={'height_ratios': [1.15, 1.]})
    ax.axvspan(zero_sp_t, zero_effort_t, color=WARNING, alpha=.13)
    ax.axvline(zero_sp_t, color=WARNING, lw=.9, ls='--',
               label=f'零 Setpoint 到达夹具：{zero_sp_t:.3f} s')
    ax.scatter([0., zero_sp_t], [2., 2.], c=[PROPOSED, WARNING],
               marker='o', s=35, zorder=3)
    ax.scatter(effort_t, [1.] * len(effort_t), color=PROPOSED,
               marker='s', s=33, zorder=3, label='正 PID 消息')
    ax.scatter([zero_effort_t], [1.], color=WARNING, marker='s', s=36,
               zorder=3, label=f'零 PID 到达夹具：{zero_effort_t:.3f} s')
    ax.set(xlim=(-.08, 1.32), ylim=(.55, 2.45),
           yticks=[1., 2.], yticklabels=['PID 输出', '算法 Setpoint'],
           xlabel='最后正向 Setpoint 之后的墙钟时间 / s',
           title='(a) 原独立进程短探针：未连接桥，存在输出传播尾时差')
    ax.legend(loc='upper left', fontsize=6.3, ncol=2)
    ax.grid(axis='x', alpha=.25)

    labels = ['新鲜 Setpoint\n＋正 PID', 'Setpoint 失鲜\n＋正 PID',
              '失鲜时\n命令保活', '显式 Hold\n＋正 PID']
    bars = bx.bar(np.arange(4), values, color=[PROPOSED, WARNING, WARNING, WARNING],
                  width=.57)
    for bar, value in zip(bars, values):
        bx.text(bar.get_x() + bar.get_width() / 2., value + .7,
                f'{value:.0f}%', ha='center', va='bottom', fontsize=7.6)
    bx.set(xticks=np.arange(4), xticklabels=labels, ylim=(0., 31.),
           ylabel='本地 UDP 下行主推 / %',
           title='(b) 新安装版桥独立回环：上游决策失鲜时拒绝正 PID')
    bx.grid(axis='y', alpha=.25)
    figures = BASE / 'figures'
    figures.mkdir(parents=True, exist_ok=True)
    save_figure(fig, figures / STEM, dpi=500)
    plt.close(fig)

    result = {
        'role': 'two_separate_isolated_software_trials_not_one_end_to_end_run',
        'original_process_probe_last_positive_setpoint_elapsed_s': first_sp,
        'original_process_probe_zero_setpoint_delay_s': zero_sp_t,
        'original_process_probe_zero_pid_delay_s': zero_effort_t,
        'bridge_loopback_udp_thrust_percent': dict(zip(stages, values)),
        'source_tail_audit_sha256': sha(audit_path),
        'source_bridge_summary_sha256': sha(summary_path),
        'source_bridge_packets_sha256': sha(packets_path),
        'figure_png_sha256': sha(figures / f'{STEM}.png'),
        'figure_pdf_sha256': sha(figures / f'{STEM}.pdf'),
        'plot_script_sha256': sha(Path(__file__)),
    }
    (BASE / f'{STEM}.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n',
                                       encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Visualize wall-clock IMU stamp replay versus the inspection freshness gate."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
import shutil

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from thesis_plot_style import (BASELINE_1, GRID_COLOR, PROPOSED, REFERENCE,
                               apply_thesis_style, figure_size, save_figure)


ROOT = Path(__file__).resolve().parents[1]
RESULT = ROOT / 'AUV-Master-Mag/results/v2/inspection_shadow_wall_stamp_replay_20260927'
OUT = ROOT / 'AUV-Master-Mag/docs/v2/publication/fwhm_v2_experiment_results'


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(name: str) -> tuple[dict, list[dict]]:
    folder = RESULT / name
    summary = json.loads((folder / 'summary.json').read_text(encoding='utf-8'))
    with (folder / 'trace.csv').open(newline='', encoding='utf-8') as stream:
        rows = list(csv.DictReader(stream))
    assert summary['source_sha256']['probe'] == sha(ROOT / 'tools/probe_v2_shadow_wall_stamp_replay.py')
    assert summary['source_sha256']['localization'] == sha(
        ROOT / 'brain_linux/src/auv_localization/auv_localization/auv_localization_node.py')
    assert summary['source_sha256']['shadow_launch'] == sha(
        ROOT / 'brain_linux/src/auv_cable_tracking_v2/launch/inspection_shadow_stack.launch.py')
    assert summary['checks']['unapproved_synthetic_side_hint_does_not_search']
    assert summary['checks']['passive_bridge_never_authorized']
    assert summary['checks']['no_uncalibrated_depth']
    return summary, rows


def main() -> None:
    control, control_rows = load('control_229')
    gated, gated_rows = load('gated_228')
    assert control['source_sha256'] == gated['source_sha256']
    assert gated['checks_passed']
    assert not control['checks']['replay_stops_filtered_navigation']
    assert not control['checks']['replay_revokes_capability']

    apply_thesis_style(base_font_size=9)
    fig, axes = plt.subplots(2, 1, figsize=figure_size(height=4.0),
                             sharex=True, constrained_layout=True)
    for rows, color, label in ((control_rows, BASELINE_1, '关闭时间门'),
                               (gated_rows, PROPOSED, '启用时间门')):
        after = [row for row in rows if float(row['elapsed_s']) >= 10.]
        first = int(after[0]['nav_count'])
        axes[0].plot([10.] + [float(row['elapsed_s']) for row in after],
                     [0] + [int(row['nav_count']) - first for row in after],
                     color=color, linewidth=1.7, marker='o', markersize=2.4,
                     label=label)
        axes[1].step([float(row['elapsed_s']) for row in rows],
                     [1 if row['cable_capability'] == 'True' else 0 for row in rows],
                     where='post', color=color, linewidth=1.8, label=label)
    for ax in axes:
        ax.axvline(10., color=REFERENCE, linestyle='--', linewidth=.9)
        ax.axvspan(10., 14., color='#F4F4F4', zorder=-2)
        ax.grid(axis='y', color=GRID_COLOR, linewidth=.5, alpha=.65)
        ax.spines[['top', 'right']].set_visible(False)
        ax.set_xlim(9.5, 14.)
    axes[0].set_ylabel('累计导航消息增量 / 条')
    axes[0].legend(loc='upper left', ncol=2, frameon=False)
    axes[1].set_ylabel('巡检能力可用')
    axes[1].set_yticks([0, 1], ['否', '是'])
    axes[1].set_xlabel('输入开始后的墙钟时间 / s')
    axes[1].text(10.06, .08, 'IMU 持续到达，但采集时间戳冻结',
                 fontsize=8, color=REFERENCE)
    paths = save_figure(fig, OUT / 'figures/41_wall_clock_imu_stamp_replay')
    plt.close(fig)

    copied = []
    for name in ('control_229', 'gated_228'):
        for leaf in ('summary.json', 'trace.csv'):
            target = OUT / 'data' / f'41_{name}_{leaf}'
            shutil.copyfile(RESULT / name / leaf, target)
            copied.append(target)
    manifest = {
        'role': 'matched_wall_clock_synthetic_imu_stamp_replay_shadow_comparison',
        'control_launch_override': 'inspection_navigation_imu_max_age_s:=0.0',
        'matched_heading_source': 'imu_orientation_covariance',
        'heading_covariance_in_probe_rad2': .0001,
        'gated_imu_max_age_s': .75,
        'untrusted_target_side_hint': 'synthetic_test_fixture rejected under non-sim clock',
        'physical_sensor_calibration': False,
        'field_release_authorized': False,
        'source_sha256': {
            'plot': sha(Path(__file__)),
            'probe': sha(ROOT / 'tools/probe_v2_shadow_wall_stamp_replay.py'),
            'v2_node': sha(ROOT / 'brain_linux/src/auv_cable_tracking_v2/auv_cable_tracking_v2/cable_tracking_v2_node.py'),
            'localization': sha(ROOT / 'brain_linux/src/auv_localization/auv_localization/auv_localization_node.py'),
        },
        'data_sha256': {path.name: sha(path) for path in copied},
        'figure_sha256': {path.name: sha(path) for path in paths},
    }
    target = OUT / 'data/41_wall_clock_imu_stamp_replay_manifest.json'
    target.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'figures': [str(path.relative_to(ROOT)) for path in paths],
                      'manifest': str(target.relative_to(ROOT))}, ensure_ascii=False))


if __name__ == '__main__':
    main()

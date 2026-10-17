#!/usr/bin/env python3
"""Plot matched raw-sensor dropout observations of the passive inspection stack."""

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
RESULT = ROOT / 'AUV-Master-Mag/results/v2/inspection_shadow_sensor_flow_20260927'
OUT = ROOT / 'AUV-Master-Mag/docs/v2/publication/fwhm_v2_experiment_results'


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_run(name: str) -> tuple[dict, list[dict]]:
    source = RESULT / name
    summary = json.loads((source / 'summary.json').read_text(encoding='utf-8'))
    with (source / 'trace.csv').open(newline='', encoding='utf-8') as stream:
        trace = list(csv.DictReader(stream))
    assert summary['source_sha256']['probe'] == sha(ROOT / 'tools/probe_v2_shadow_raw_sensor_flow.py')
    assert summary['source_sha256']['localization'] == sha(
        ROOT / 'brain_linux/src/auv_localization/auv_localization/auv_localization_node.py')
    assert summary['nav_publishers'] == ['auv_localization_node']
    assert summary['checks']['raw_sensor_to_filtered_nav']
    assert summary['checks']['mission_command_sent']
    assert summary['checks']['passive_bridge_never_authorized']
    assert summary['healthy_s'] == 12. and summary['imu_dropout_s'] == 4.
    return summary, trace


def numeric(rows: list[dict], field: str) -> list[float]:
    return [float(row[field]) if row[field] not in ('', None) else float('nan')
            for row in rows]


def main() -> None:
    control, control_rows = load_run('control_222')
    gated, gated_rows = load_run('fixed_221')
    assert control['source_sha256']['probe'] == gated['source_sha256']['probe']
    assert control['source_sha256']['v2_config'] == gated['source_sha256']['v2_config']
    assert not control['checks']['dropout_stops_filtered_navigation']
    assert all(gated['checks'].values())

    apply_thesis_style(base_font_size=9)
    fig, axes = plt.subplots(2, 1, figsize=figure_size(height=4.35),
                             sharex=True, constrained_layout=True)
    for summary, rows, color, label in (
        (control, control_rows, BASELINE_1, '关闭时效门'),
        (gated, gated_rows, PROPOSED, '启用时效门'),
    ):
        x = numeric(rows, 'elapsed_s')
        count = numeric(rows, 'nav_count')
        post = [(elapsed, value) for elapsed, value in zip(x, count)
                if elapsed >= 12.]
        first_count = post[0][1]
        axes[0].plot([12.] + [elapsed for elapsed, _ in post],
                     [0.] + [value - first_count for _, value in post],
                     color=color, linewidth=1.8, marker='o', markersize=2.5,
                     label=label)
        axes[1].step(x, numeric(rows, 'setpoint_speed_mps'), where='post',
                     color=color, linewidth=1.8, label=label)
    for ax in axes:
        ax.axvspan(12., 16., facecolor='#F4F4F4', zorder=-2)
        ax.axvline(12., color=REFERENCE, linewidth=.9, linestyle='--')
        ax.grid(axis='y', color=GRID_COLOR, linewidth=.5, alpha=.65)
        ax.set_xlim(11.5, 16.)
        ax.spines[['top', 'right']].set_visible(False)
    axes[0].set_ylabel('累计定位消息增量 / 条')
    axes[0].legend(loc='upper left', frameon=False, ncol=2)
    axes[1].set_ylabel('巡检目标速度 / (m/s)')
    axes[1].set_xlabel('注入开始后的墙钟时间 / s')
    axes[1].set_ylim(-.035, .37)
    axes[1].text(12.05, .34, 'IMU 停止；DVL、深度和磁输入保持',
                 fontsize=8, color=REFERENCE, va='top')

    out_base = OUT / 'figures/40_shadow_raw_sensor_imu_gate'
    paths = save_figure(fig, out_base)
    plt.close(fig)
    copied = []
    for name in ('control_222', 'fixed_221'):
        for leaf in ('summary.json', 'trace.csv'):
            target = OUT / 'data' / f'40_{name}_{leaf}'
            shutil.copyfile(RESULT / name / leaf, target)
            copied.append(target)
    manifest = {
        'role': 'matched_synthetic_raw_sensor_imu_dropout_shadow_comparison',
        'control_launch_override': 'inspection_navigation_imu_max_age_s:=0.0',
        'gated_launch_default_s': .75,
        'sensor_input': 'synthetic stationary IMU/DVL/depth/magnetic; IMU only stops at 12 s',
        'passive_bridge': True,
        'published_field_depth': False,
        'field_release_authorized': False,
        'source_sha256': {'plot_script': sha(Path(__file__)),
                          'localization': sha(ROOT / 'brain_linux/src/auv_localization/auv_localization/auv_localization_node.py'),
                          'shadow_launch': sha(ROOT / 'brain_linux/src/auv_cable_tracking_v2/launch/inspection_shadow_stack.launch.py'),
                          'probe': sha(ROOT / 'tools/probe_v2_shadow_raw_sensor_flow.py')},
        'data_sha256': {path.name: sha(path) for path in copied},
        'figure_sha256': {path.name: sha(path) for path in paths},
    }
    target = OUT / 'data/40_shadow_raw_sensor_imu_gate_manifest.json'
    target.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n',
                      encoding='utf-8')
    print(json.dumps({'figures': [str(path.relative_to(ROOT)) for path in paths],
                      'manifest': str(target.relative_to(ROOT))}, ensure_ascii=False))


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Figure 44: synthetic, source-matched DVL/IMU interface contract."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import sys

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

from thesis_plot_style import (BASELINE_1, GRID_COLOR, PROPOSED, REFERENCE,
                               WARNING, apply_thesis_style, figure_size,
                               save_figure)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'brain_linux/src/auv_cable_tracking_v2'))
from common.imu_provenance_sidecar import ImuProvenanceV1  # noqa: E402
from auv_cable_tracking_v2.dvl_sidecar_join import (  # noqa: E402
    BodyDvlSample, join_body_dvl_to_sidecar)

OUT = ROOT / 'AUV-Master-Mag/docs/v2/publication/fwhm_v2_experiment_results'
THESIS = ROOT / 'docs/thesis/figures/experiments/fwhm_v2'
STEM = '44_sidecar_dvl_source_match'
PROBE_RESULT = ROOT / 'AUV-Master-Mag/results/v2/inspection_imu_sidecar_dvl_join_20260927/fixture.json'


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    probe = json.loads(PROBE_RESULT.read_text(encoding='utf-8'))
    assert probe['checks_passed']
    assert probe['old_uplink_only_counts'] == {'imu': 0, 'dvl': 0, 'depth': 1}
    assert probe['matched_sample_counts']['imu'] == 7
    assert probe['matched_sample_counts']['dvl'] == 7
    assert probe['stale_window_new_odom_count'] == 0
    observed = probe['last_filtered_velocity_xyz_mps']
    assert abs(observed[0]) < .1 and abs(observed[1] - .3) < .1
    imu = ImuProvenanceV1(0x1234, 11, 109375, 1150,
                          0., 0., math.pi / 2., 0., 0., 0.)
    q = (0., 0., math.sqrt(.5), math.sqrt(.5))
    cases = [
        ('新鲜且对时', '间隔 50 ms，限 150 ms', BodyDvlSample(1120, 1100, (.3, 0., 0.)), imu),
        ('包内 DVL 旧', '样本龄 600 ms，限 500 ms', BodyDvlSample(1700, 1100, (.3, 0., 0.)), imu),
        ('跨源时间不符', '间隔 250 ms，限 150 ms', BodyDvlSample(1000, 900, (.3, 0., 0.)), imu),
        ('横切转动过快', '转角 5.7°，限 2°', BodyDvlSample(1120, 1100, (.3, 0., 0.)),
         ImuProvenanceV1(0x1234, 11, 109375, 1150, 0., 0., math.pi/2., 0., 0., 2.)),
        ('越出速度包络', '速度 3 m/s，限 2 m/s', BodyDvlSample(1120, 1100, (3., 0., 0.)), imu),
    ]
    records = []
    for label, diagnostic, dvl, source_imu in cases:
        outcome = join_body_dvl_to_sidecar(dvl, source_imu, q, 100.15, 100.16)
        records.append({'case': label, 'diagnostic': diagnostic,
                        'accepted': outcome.accepted, 'reason': outcome.reason,
                        'world_velocity_xyz_mps': outcome.world_xyz_mps})
    assert [x['accepted'] for x in records] == [True, False, False, False, False]
    assert abs(records[0]['world_velocity_xyz_mps'][1] - .3) < 1e-12

    apply_thesis_style(base_font_size=9)
    fig, (ax_xy, ax_gate) = plt.subplots(
        1, 2, figsize=figure_size(height=3.0),
        gridspec_kw={'width_ratios': [1, 1.45]}, constrained_layout=True)
    ax_xy.set_title('(a) 同一机体前向速度的世界系投影', loc='left', pad=7)
    ax_xy.set_xlim(-.055, .42)
    ax_xy.set_ylim(-.055, .42)
    ax_xy.set_aspect('equal')
    ax_xy.set_xticks([0, .1, .2, .3, .4])
    ax_xy.set_yticks([0, .1, .2, .3, .4])
    ax_xy.set_xlabel('世界系 X 速度 (m/s)')
    ax_xy.set_ylabel('世界系 Y 速度 (m/s)')
    ax_xy.annotate('', xy=(.3, 0), xytext=(0, 0),
                   arrowprops={'arrowstyle': '-|>', 'color': BASELINE_1, 'lw': 2.2})
    ax_xy.annotate('', xy=(0, .3), xytext=(0, 0),
                   arrowprops={'arrowstyle': '-|>', 'color': PROPOSED, 'lw': 2.2})
    ax_xy.text(.13, -.04, '旧包航向 0°', color=BASELINE_1, ha='center', fontsize=8)
    ax_xy.text(.035, .34, '侧帧航向 90°', color=PROPOSED, ha='left', fontsize=8)
    ax_xy.text(.02, .14, '机体系前向\n0.3 m/s', color=REFERENCE, ha='left', fontsize=8)

    ax_gate.set_title('(b) 板端同基准的受界配对', loc='left', pad=7)
    ax_gate.set_xlim(0, 1)
    ax_gate.set_ylim(0, 1)
    ax_gate.axis('off')
    ax_gate.text(.02, .93, '输入情形', va='center', fontweight='bold')
    ax_gate.text(.42, .93, '发布', va='center', fontweight='bold')
    ax_gate.text(.63, .93, '诊断量', va='center', fontweight='bold')
    for index, record in enumerate(records):
        y = .78 - index * .155
        ax_gate.axhline(y + .075, xmin=.02, xmax=.98, color=GRID_COLOR, lw=.5)
        ax_gate.text(.02, y, record['case'], va='center', fontsize=8)
        color = PROPOSED if record['accepted'] else WARNING
        ax_gate.add_patch(Rectangle((.42, y-.047), .15, .094,
                                    facecolor=color, edgecolor='none'))
        ax_gate.text(.495, y, '通过' if record['accepted'] else '拒绝',
                     ha='center', va='center', color='white', fontsize=8)
        ax_gate.text(.63, y, record['diagnostic'], va='center', fontsize=7.5,
                     color=REFERENCE)
    ax_gate.axhline(.08, xmin=.02, xmax=.98, color=GRID_COLOR, lw=.5)
    paths = save_figure(fig, OUT / 'figures' / STEM)
    thesis_paths = save_figure(fig, THESIS / STEM)
    plt.close(fig)

    manifest = {
        'role': 'synthetic_source_matched_body_dvl_contract_diagnostic',
        'case_data': records,
        'same_version_ros_probe_counts': probe['matched_sample_counts'],
        'same_version_ros_probe_last_filtered_velocity_xyz_mps': observed,
        'source_sha256': {
            'plot': sha(Path(__file__)),
            'join': sha(ROOT / 'brain_linux/src/auv_cable_tracking_v2/auv_cable_tracking_v2/dvl_sidecar_join.py'),
            'ros_test': sha(ROOT / 'brain_linux/src/auv_cable_tracking_v2/test/test_imu_sidecar_ros.py'),
            'probe': sha(ROOT / 'tools/probe_v2_sidecar_dvl_join.py'),
        },
        'ros_probe_result_sha256': sha(PROBE_RESULT),
        'figure_sha256': {path.name: sha(path) for path in paths},
        'thesis_figure_sha256': {path.name: sha(path) for path in thesis_paths},
        'physical_imu_or_dvl_tested': False,
        'field_release_authorized': False,
    }
    target = OUT / 'data' / f'{STEM}_manifest.json'
    target.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'figure': [str(x.relative_to(ROOT)) for x in paths],
                      'manifest': str(target.relative_to(ROOT))}, ensure_ascii=False))


if __name__ == '__main__':
    main()

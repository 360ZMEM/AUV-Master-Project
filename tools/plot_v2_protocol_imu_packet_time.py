#!/usr/bin/env python3
"""Plot matched local UDP-to-ROS IMU packet-time gate observations."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

from thesis_plot_style import (BASELINE_1, PROPOSED, REFERENCE,
                               apply_thesis_style, figure_size, save_figure)


ROOT = Path(__file__).resolve().parents[1]
RESULT = ROOT / 'AUV-Master-Mag/results/v2/inspection_protocol_packet_time_20260927'
OUT = ROOT / 'AUV-Master-Mag/docs/v2/publication/fwhm_v2_experiment_results'
NAMES = ('control_201.json', 'gated_202.json')
CASE_LABELS = ('初始有效\n1000 ms', '递增且新鲜\n1700 ms', '时间重复\n1700 ms',
               '无时间标记', '时间倒退\n900 ms', '递增但过期\n1710 ms')


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    control, gated = [json.loads((RESULT / name).read_text(encoding='utf-8'))
                      for name in NAMES]
    assert control['checks_passed'] and gated['checks_passed']
    assert control['source_sha256']['probe'] == gated['source_sha256']['probe']
    assert control['source_sha256']['bridge'] == gated['source_sha256']['bridge']
    assert [case['case'] for case in control['cases']] == [case['case'] for case in gated['cases']]
    assert control['counts'] == {'imu': 6, 'dvl': 6}
    assert gated['counts'] == {'imu': 2, 'dvl': 6}
    for record in (control, gated):
        assert record['source_sha256']['probe'] == sha(ROOT / 'tools/probe_v2_protocol_imu_packet_time.py')
        assert record['source_sha256']['bridge'] == sha(ROOT / 'brain_linux/src/auv_bridge/auv_bridge/bridge_node.py')
    for record, fixture in ((control, 'inspection_bridge_packet_time_legacy_sim.yaml'),
                            (gated, 'inspection_bridge_packet_time_sim.yaml')):
        assert record['source_sha256']['fixture'] == sha(
            ROOT / 'brain_linux/src/auv_cable_tracking_v2/config' / fixture)

    apply_thesis_style(base_font_size=9)
    fig, ax = plt.subplots(figsize=figure_size(height=2.55), constrained_layout=True)
    fig.patch.set_facecolor('white')
    ax.set_xlim(0, 6)
    ax.set_ylim(-0.07, 2.02)
    ax.invert_yaxis()
    ax.set_xticks([i + .5 for i in range(6)], CASE_LABELS)
    ax.tick_params(axis='x', length=0, pad=5, labelsize=8)
    ax.set_yticks([.5, 1.5], ['对照：关闭门控', '候选：启用门控'])
    ax.tick_params(axis='y', length=0, pad=7, labelsize=9)
    ax.grid(False)
    for row, result in enumerate((control, gated)):
        for col, case in enumerate(result['cases']):
            published = case['imu_increment'] == 1
            color = (BASELINE_1 if row == 0 else PROPOSED) if published else '#E7E7E7'
            ax.add_patch(Rectangle((col + .035, row + .08), .93, .84,
                                   facecolor=color, edgecolor='white', linewidth=1.1))
            ax.text(col + .5, row + .5, '转发' if published else '拒绝',
                    ha='center', va='center', color='white' if published else REFERENCE,
                    fontsize=9, fontweight='bold')
    for spine in ax.spines.values():
        spine.set_visible(False)
    paths = save_figure(fig, OUT / 'figures/42_protocol_imu_packet_time_gate')
    plt.close(fig)

    copied = []
    for name in NAMES:
        target = OUT / 'data' / f'42_{name}'
        shutil.copyfile(RESULT / name, target)
        copied.append(target)
    manifest = {
        'role': 'matched_synthetic_udp_to_ros_packet_formation_time_gate',
        'control_ros_domain_id': control['ros_domain_id'],
        'gated_ros_domain_id': gated['ros_domain_id'],
        'source_sha256': {'plot': sha(Path(__file__)),
                          'probe': control['source_sha256']['probe'],
                          'bridge': control['source_sha256']['bridge'],
                          'control_fixture': control['source_sha256']['fixture'],
                          'gated_fixture': gated['source_sha256']['fixture']},
        'data_sha256': {path.name: sha(path) for path in copied},
        'figure_sha256': {path.name: sha(path) for path in paths},
        'imu_sensor_acquisition_time_tested': False,
        'physical_pc104_tested': False,
        'field_release_authorized': False,
    }
    target = OUT / 'data/42_protocol_imu_packet_time_gate_manifest.json'
    target.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'figures': [str(path.relative_to(ROOT)) for path in paths],
                      'manifest': str(target.relative_to(ROOT))}, ensure_ascii=False))


if __name__ == '__main__':
    main()

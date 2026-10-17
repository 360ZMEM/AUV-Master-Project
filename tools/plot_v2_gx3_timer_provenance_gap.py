#!/usr/bin/env python3
"""Show where the existing PC104 parser loses the GX3 sensor timer."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, Rectangle

from thesis_plot_style import (BASELINE_1, GRID_COLOR, NEUTRAL, PROPOSED,
                               REFERENCE, WARNING, apply_thesis_style,
                               figure_size, save_figure)


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'AUV-Master-Mag/docs/v2/publication/fwhm_v2_experiment_results'
PROTOCOL = ROOT / ('相关附件和参照/原始AUV部分潜在技术细节/'
                   '3DM-GX3-25 Single Byte Data Communications Protocol.pdf')
FIRMWARE = ROOT / 'csd_vx6.8_lastest'


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    apply_thesis_style(base_font_size=11)
    fig, ax = plt.subplots(figsize=figure_size(height=2.65), constrained_layout=True)
    ax.set_xlim(-.15, 8.15)
    ax.set_ylim(0, 3.25)
    ax.axis('off')
    widths = (1.2, 3.4, 2.1, 1.3)
    x = 0.
    blocks = (
        ('帧头 0xCF\n1 字节', '只验首字节', NEUTRAL),
        ('姿态 + 角速度\n24 字节', '取数值', BASELINE_1),
        ('传感器 Timer\n4 字节', '丢弃', PROPOSED),
        ('校验和\n2 字节', '未核对', WARNING),
    )
    for width, (source, old, color) in zip(widths, blocks):
        ax.add_patch(Rectangle((x+.025, 2.05), width-.05, .78,
                               facecolor=color, edgecolor=REFERENCE, linewidth=.7))
        ax.text(x+width/2, 2.44, source, ha='center', va='center',
                color='white', fontsize=11, fontweight='bold')
        ax.add_patch(FancyArrowPatch((x+width/2, 1.99), (x+width/2, 1.72),
                                     arrowstyle='-|>', mutation_scale=10,
                                     color=REFERENCE, linewidth=.8))
        old_color = '#E7E7E7' if old in ('只验首字节', '取数值') else '#F6E3DC'
        ax.add_patch(Rectangle((x+.025, 1.14), width-.05, .52,
                               facecolor=old_color, edgecolor=GRID_COLOR, linewidth=.7))
        ax.text(x+width/2, 1.4, old, ha='center', va='center',
                fontsize=11, color=REFERENCE if old_color == '#E7E7E7' else WARNING)
        x += width
    ax.text(0, 3.05, '3DM-GX3-25 原始 0xCF 应答（固定 31 字节）',
            ha='left', va='center', color=REFERENCE, fontsize=11)
    ax.text(0, .91, '现行 PC104 解析', ha='left', va='center', color=REFERENCE, fontsize=11)
    ax.add_patch(Rectangle((.55, .1), 6.9, .48, facecolor='#F2F2F2',
                           edgecolor=GRID_COLOR, linewidth=.7))
    ax.text(4, .34, '$AUV$ 上行仅有 PC104 组包时间：无法证明姿态来自新 IMU 样本',
            ha='center', va='center', color=REFERENCE, fontsize=9.5)
    paths = save_figure(fig, OUT / 'figures/43_gx3_timer_provenance_gap')
    plt.close(fig)
    manifest = {
        'role': 'source_audit_gx3_cf_timer_lost_before_pc104_uplink',
        'source_sha256': {
            'plot': sha(Path(__file__)),
            'protocol_pdf': sha(PROTOCOL),
            'firmware_com': sha(FIRMWARE / 'com.c'),
            'firmware_data_process': sha(FIRMWARE / 'DataProcess.c'),
            'offline_decoder': sha(ROOT / 'tools/decode_gx3_cf.py'),
        },
        'figure_sha256': {path.name: sha(path) for path in paths},
        'physical_imu_replay_tested': False,
        'firmware_modified': False,
        'field_release_authorized': False,
    }
    target = OUT / 'data/43_gx3_timer_provenance_gap_manifest.json'
    target.write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'figures': [str(path.relative_to(ROOT)) for path in paths],
                      'manifest': str(target.relative_to(ROOT))}, ensure_ascii=False))


if __name__ == '__main__':
    main()

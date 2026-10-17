#!/usr/bin/env python3
"""Plot the observed digital-twin scene fallback versus inspection display gate."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

from thesis_plot_style import (BASELINE_1, GRID_COLOR, NEUTRAL, PROPOSED,
                               REFERENCE, apply_thesis_style, figure_size,
                               save_figure)


ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / 'AUV-Master-Mag/results/v2/inspection_shadow_stack_20260927'
OUT = (ROOT / 'AUV-Master-Mag/docs/v2/publication/'
       'fwhm_v2_experiment_results')


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    legacy_path = RESULTS / 'legacy_scene_counterexample_audit.json'
    safe_path = RESULTS / 'scene_fallback_audit.json'
    legacy = json.loads(legacy_path.read_text(encoding='utf-8'))
    safe = json.loads(safe_path.read_text(encoding='utf-8'))
    assert legacy['checks_passed'] and legacy['expect_synthetic_fallback']
    assert safe['checks_passed'] and not safe['expect_synthetic_fallback']
    categories = [
        ('mock_scene', '模拟场景'),
        ('cable_add', '电缆标记 ADD'),
        ('truth_add', '真值艇位 ADD'),
        ('mission_state', '任务状态'),
    ]

    apply_thesis_style(base_font_size=9)
    fig, ax = plt.subplots(figsize=figure_size(height=2.9), constrained_layout=True)
    rows = [(legacy, '原显示回退', BASELINE_1),
            (safe, '巡检影子入口', PROPOSED)]
    for row_index, (audit, _, active_color) in enumerate(rows):
        for col_index, (field, _) in enumerate(categories):
            count = int(audit['observed'][field])
            synthetic = col_index < 3
            face = (active_color if count and synthetic else
                    PROPOSED if count else '#F2F2F2')
            ax.add_patch(Rectangle((col_index - .46, row_index - .39), .92, .78,
                                   facecolor=face, edgecolor=GRID_COLOR, linewidth=.7))
            ax.text(col_index, row_index, f'{count} 条',
                    ha='center', va='center', fontsize=10,
                    color='white' if count else REFERENCE, weight='bold')
    ax.set(xlim=(-.5, 3.5), ylim=(1.5, -.5),
           xticks=range(4), yticks=range(2),
           title='Zenoh 场景缺失时的显示输出（各自限时观察）')
    ax.set_xticklabels([name for _, name in categories])
    ax.set_yticklabels([f'{label}\n{audit["observe_s"]:g} s' for audit, label, _ in rows])
    ax.tick_params(axis='both', length=0)
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.text(.5, -.18, '色块表示消息出现；计数为实际 DDS 接收条数，不比较吞吐率',
            transform=ax.transAxes, ha='center', color=NEUTRAL, fontsize=7.5)
    out_base = OUT / 'figures/39_shadow_scene_truth_gate'
    paths = save_figure(fig, out_base)
    plt.close(fig)
    manifest = {
        'role': 'inspection_shadow_scene_truth_gate_figure',
        'legacy_audit_sha256': sha(legacy_path),
        'safe_audit_sha256': sha(safe_path),
        'plot_script_sha256': sha(Path(__file__)),
        'viz_bridge_source_sha256': sha(ROOT / 'brain_linux/src/auv_viz_bridge/auv_viz_bridge/zenoh_viz_bridge_node.py'),
        'shadow_launch_source_sha256': sha(ROOT / 'brain_linux/src/auv_cable_tracking_v2/launch/inspection_shadow_stack.launch.py'),
        'figure_sha256': {path.name: sha(path) for path in paths},
        'scene_provenance': 'legacy standalone viz and safe six-node passive shadow launch',
        'field_release_authorized': False,
    }
    target = OUT / 'data/39_shadow_scene_truth_gate_manifest.json'
    target.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n',
                      encoding='utf-8')
    print(json.dumps({'figures': [str(path.relative_to(ROOT)) for path in paths],
                      'manifest': str(target.relative_to(ROOT))}, ensure_ascii=False))


if __name__ == '__main__':
    main()

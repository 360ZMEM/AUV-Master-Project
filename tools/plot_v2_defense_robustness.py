#!/usr/bin/env python3
"""Thesis-style process and diagnostic plots from frozen robustness CSVs."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from thesis_plot_style import (apply_thesis_style, FULL_WIDTH, PROPOSED,
                              BASELINE_1, WARNING, REFERENCE, NEUTRAL)

apply_thesis_style()


def read(path):
    with path.open(newline='') as f:
        rows = list(csv.DictReader(f))
    return rows


def values(rows, key):
    return np.array([float(r[key]) if r.get(key) not in (None, '') else np.nan for r in rows])


def save(fig, directory, name):
    fig.savefig(directory / (name + '.png'), dpi=600, bbox_inches='tight')
    fig.savefig(directory / (name + '.pdf'), bbox_inches='tight')
    plt.close(fig)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run-dir', type=Path, required=True)
    p.add_argument('--output-dir', type=Path, required=True)
    p.add_argument('--seed', type=int, default=401)
    args = p.parse_args()
    run = args.run_dir
    out = args.output_dir
    out.mkdir(parents=True, exist_ok=True)
    plan = json.loads((run / 'plan.json').read_text())
    manifest = json.loads((run / 'manifest.json').read_text())
    assert manifest['plan_sha256'] == hashlib.sha256((run / 'plan.json').read_bytes()).hexdigest()
    summary = json.loads((run / 'summary.json').read_text())
    selected = {(r['case'], r['method']): r for r in summary if r['seed'] == args.seed}
    def trace(case, method):
        s = selected[(case, method)]
        path = run / s['trace']
        assert hashlib.sha256(path.read_bytes()).hexdigest() == s['trace_sha256']
        return read(path)
    colors = {'legacy': BASELINE_1, 'supervised': PROPOSED}
    names = {'legacy': '旧链', 'supervised': '监督候选（含参考）'}
    split_label = '开发同版对照（非留出）' if plan['split'] == 'development' else '独立留出对照'
    stamp = f'{split_label}，种子 {args.seed}；外部参考只用于监督'
    # The full mission and two targeted spatial views use actual recorded
    # paths; a rejected run is never rendered as a zero-error completed path.
    fig, axes = plt.subplots(3, 1, figsize=(FULL_WIDTH, 7.6), layout='constrained')
    fig.suptitle(stamp, fontsize=9)
    for ax, case, title in zip(axes,
            ['clean_wire', 'navigation_jump', 'fused_neighbor'],
            ['(a) 单源完整任务：搜索、横切、接入与有限巡检',
             '(b) 导航跳变：核心路段与撤权后的实际运动',
             '(c) 融合邻源：接入与有限段局部视图']):
        if case == 'clean_wire':
            ax.axhline(0., color=NEUTRAL, lw=.8, ls=':', label='原先验')
        ax.axhline(6., color=REFERENCE, lw=1., ls='--', label='真实目标（仅评价）')
        ax.axvspan(5., 75., color=PROPOSED, alpha=.06)
        if case == 'fused_neighbor':
            ax.axhline(9., color=WARNING, lw=.8, ls=':', label='邻源')
        for method in ('legacy', 'supervised'):
            rows = trace(case, method)
            active = [r for r in rows if r['mode'] != 'hold']
            tail = [r for r in rows if r['mode'] == 'hold']
            ax.plot(values(active, 'x_m'), values(active, 'y_m'), color=colors[method],
                    lw=1.1, ls='--' if method == 'legacy' else '-', label=names[method])
            if tail:
                ax.plot(values(tail, 'x_m'), values(tail, 'y_m'), color=colors[method], lw=1., ls=':', label=f'{names[method]}：零推进后')
                ax.scatter(float(tail[0]['x_m']), float(tail[0]['y_m']), marker='x', color=colors[method], s=28, zorder=5)
        ax.set_title(title, loc='left', fontsize=10)
        ax.set_xlabel('沿缆位置 / m'); ax.set_ylabel('横向位置 / m')
        ax.grid(alpha=.18)
        if case == 'clean_wire':
            ax.set_xlim(-260., 90.); ax.set_ylim(-20., 23.)
            ax.legend(loc='upper left', fontsize=8, ncol=2)
            measured = trace(case, 'supervised')
            confirmed = next(r for r in measured if r['mode'] == 'confirm')
            tracked = next(r for r in measured if r['mode'] == 'track')
            core = [r for r in measured if r['mode'] == 'track' and 5 <= float(r['x_m']) <= 75]
            annotations = [('搜索起点', measured[0], (-225.,-17.)),
                           ('检测／横切', confirmed, (-170.,-8.)),
                           ('横切确认／接入', tracked, (-50.,21.)),
                           ('核心巡检', core[len(core)//2], (40.,-9.))]
            for label, row, label_position in annotations:
                ax.annotate(label, xy=(float(row['x_m']),float(row['y_m'])), xytext=label_position,
                            fontsize=8, ha='center', color=REFERENCE,
                            arrowprops=dict(arrowstyle='->',color=REFERENCE,lw=.7))
        elif case == 'navigation_jump':
            ax.set_xlim(-5., 115.); ax.set_ylim(3., 9.)
            ax.legend(loc='upper right', fontsize=7.5, ncol=2)
        else:
            ax.set_xlim(-90., 90.); ax.set_ylim(3., 17.)
            ax.legend(loc='upper right', fontsize=7.5, ncol=2)
    save(fig, out, '72_defense_robustness_process_maps')

    fig, axes = plt.subplots(2, 2, figsize=(FULL_WIDTH, 5.6), layout='constrained')
    fig.suptitle(stamp, fontsize=9)
    visible_max = 2.0
    for method in ('legacy', 'supervised'):
        rows = trace('navigation_jump', method)
        s = selected[('navigation_jump', method)]
        t0 = s['fault_start_s']
        assert t0 is not None
        t = values(rows, 'time_s') - t0
        visible = (t >= -10.) & (t <= 400.)
        visible_max = max(visible_max, float(np.max(values(rows, 'true_offset_m')[visible])))
        axes[0,0].plot(t, values(rows, 'true_offset_m'), color=colors[method], lw=1.1,
                       ls='--' if method == 'legacy' else '-', label=names[method])
        axes[1,0].plot(t, values(rows, 'encoded_rpm'), color=colors[method], lw=1.1,
                       ls='--' if method == 'legacy' else '-')
        if method == 'supervised':
            residual = values(rows, 'robustness_position_increment_residual_m')
            valid = np.isfinite(residual)
            axes[0,1].plot(t[valid], residual[valid], color=PROPOSED, lw=1.)
            axes[0,1].scatter(t[valid][-1], residual[valid][-1], color=WARNING, s=20, zorder=5)
        tail = [r for r in rows if r['mode'] == 'hold']
        assert tail
        xy = np.column_stack([values(tail, 'x_m'), values(tail, 'y_m')])
        axes[1,1].plot(values(tail, 'time_s') - float(tail[0]['time_s']),
                       np.linalg.norm(xy - xy[0], axis=1), color=colors[method], lw=1.1,
                       ls='--' if method == 'legacy' else '-')
    axes[0,0].axhline(2., color=WARNING, ls=':', lw=.9, label='真实横偏评价门')
    axes[0,0].set_title('(a) 真实横偏；保持期间继续记录', loc='left', fontsize=9)
    axes[0,0].set_ylabel('真实横偏 / m')
    handles, labels = axes[0,0].get_legend_handles_labels()
    fig.legend(handles, labels, loc='upper center', bbox_to_anchor=(.5,-.01),
               ncol=3, fontsize=7, frameon=False)
    axes[0,0].set_ylim(0., visible_max * 1.18)
    axes[0,1].axhline(plan['supervisor_contract']['position_increment_margin_m'], color=WARNING, ls=':', lw=.9)
    axes[0,1].set_title('(b) 导航位移与地速积分不一致', loc='left', fontsize=9)
    axes[0,1].set_ylabel('单周期创新 / m')
    axes[1,0].set_title('(c) 编码主推：撤权不是轨迹结束', loc='left', fontsize=9)
    axes[1,0].set_ylabel('主推编码 / RPM')
    axes[1,1].set_title('(d) 零推进后的惯性位移', loc='left', fontsize=9)
    axes[1,1].set_ylabel('相对撤权点位移 / m'); axes[1,1].set_xlabel('撤权后仿真时间 / s')
    for ax in (axes[0,0], axes[1,0]):
        ax.set_xlim(-10., 400.); ax.set_xlabel('相对导航跳变的仿真时间 / s'); ax.axvline(0., color=NEUTRAL, lw=.7)
    axes[0,1].set_xlim(-5., 5.); axes[0,1].set_xlabel('相对导航跳变的仿真时间 / s')
    for ax in axes.flat:
        ax.grid(alpha=.18)
    save(fig, out, '73_defense_navigation_withdrawal_diagnostics')

    # Geometry and vehicle following are separate quantities. Withheld
    # geometry has no numerical zero; use an explicit unavailable annotation.
    fig, axes = plt.subplots(1, 2, figsize=(FULL_WIDTH, 3.0), layout='constrained')
    fig.suptitle(stamp, fontsize=8)
    for method in ('legacy', 'supervised'):
        rows = trace('fused_neighbor', method)
        scan = [r for r in rows if r['mode'] in ('search', 'confirm')]
        x = values(scan, 'nav_y_m'); b = values(scan, 'magnetic_nt')
        order = np.argsort(x)
        axes[0].plot(x[order], b[order], color=colors[method], ls='--' if method=='legacy' else '-', lw=.9, label=names[method])
    axes[0].axvline(6., color=REFERENCE, ls='--', lw=.9, label='指定目标')
    axes[0].axvline(9., color=WARNING, ls=':', lw=.9, label='邻源')
    center = float(next(r['estimated_cable_y_m'] for r in trace('fused_neighbor','legacy') if r['lateral_valid']=='True'))
    axes[0].axvline(center, color=BASELINE_1, ls='-.', lw=.9, label='旧链发布中心')
    axes[0].set_title('(a) 单个可见峰仍可能偏向邻源', loc='left', fontsize=9)
    axes[0].set_xlabel('观测法向位置 / m'); axes[0].set_ylabel('磁包络 / nT')
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc='upper center', bbox_to_anchor=(.5,-.01), ncol=3,
               fontsize=7, frameon=False)
    legacy = selected[('fused_neighbor','legacy')]
    values_plot = [legacy['released_center_max_error_m'], legacy['core_true_mae_m'], legacy['core_true_max_m']]
    axes[1].bar(range(3), values_plot, color=[BASELINE_1, PROPOSED, NEUTRAL], width=.6)
    for i, v in enumerate(values_plot):
        axes[1].text(i, v+.04, f'{v:.3f}', ha='center', va='bottom', fontsize=8)
    axes[1].set_xticks(range(3), ['发布中心\n偏差', '载体核心\nMAE', '载体核心\n最大偏差'])
    axes[1].set_ylim(0., max(values_plot)*1.28)
    axes[1].set_title('(b) 路线通过不能证明定位准确', loc='left', fontsize=9)
    axes[1].set_ylabel('相对指定目标的误差 / m')
    axes[1].text(.02,.98,'监督组：中心未授权，不能记作零误差',transform=axes[1].transAxes,fontsize=7,va='top')
    for ax in axes:
        ax.grid(axis='y', alpha=.18)
    save(fig, out, '74_defense_geometry_vs_tracking_insight')
    payload = dict(source_run=str(run.resolve()), source_split=plan['split'], seed=args.seed,
                   not_independent_held_out_claim=plan['split']!='held_out',
                   source_plan_sha256=manifest['plan_sha256'],
                   plot_script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                   assets={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in out.glob('*') if f.suffix in ('.png','.pdf') and f.name.startswith(('72_','73_','74_'))})
    (out/'figure_manifest.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(dict(figures=3, output=str(out), source_split=plan['split'])))


if __name__ == '__main__':
    main()

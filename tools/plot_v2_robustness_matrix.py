#!/usr/bin/env python3
"""Finite-case outcome map and current process figures, using frozen traces."""
import argparse
import csv
import hashlib
import json
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap
from matplotlib.patches import Patch
from matplotlib.lines import Line2D

from thesis_plot_style import apply_thesis_style, FULL_WIDTH, PROPOSED, BASELINE_1, WARNING, REFERENCE, NEUTRAL

apply_thesis_style()

LABELS = dict(clean_wire='孤立直导线', clean_dipole='孤立偶极', steady_plus='稳态横流 +0.03',
    steady_minus='稳态横流 −0.03', periodic_current='周期横流 ±0.02', step_current='反向阶跃 −0.05',
    strong_current='超界横流 +0.12', navigation_noise='小位置／航向扰动', navigation_hidden_bias='隐蔽偏差 +0.7 m',
    navigation_jump='位置跳变 +0.8 m', navigation_drift='位置漂移 +0.03 m/s', weak_neighbor='弱邻源 0.05',
    fused_neighbor='融合邻源 0.45', equal_close_neighbor='近距等强邻源', opposed_neighbor='反相邻源',
    quadrature_neighbor='正交相位邻源', combined_bounded='小流＋导航＋弱邻源', unknown_shape='未知包络指数',
    no_source='无磁源', magnetic_gain_step='扫描后磁幅减半')


def read(path):
    with path.open(newline='') as f:
        return list(csv.DictReader(f))


def values(rows, key):
    return np.array([float(r[key]) if r.get(key) not in (None, '') else np.nan for r in rows])


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run-dir', required=True, type=Path)
    p.add_argument('--output-dir', required=True, type=Path)
    p.add_argument('--seed', type=int, default=501)
    a = p.parse_args(); a.output_dir.mkdir(parents=True, exist_ok=True)
    plan = json.loads((a.run_dir/'plan.json').read_text())
    manifest = json.loads((a.run_dir/'manifest.json').read_text())
    summary = json.loads((a.run_dir/'summary.json').read_text())
    assert hashlib.sha256((a.run_dir/'plan.json').read_bytes()).hexdigest() == manifest['plan_sha256']
    for name, h in manifest['artifacts'].items():
        assert hashlib.sha256((a.run_dir/name).read_bytes()).hexdigest() == h
    selected = {(s['case'],s['method'],s['seed']):s for s in summary}
    def trace(case, method):
        return read(a.run_dir/selected[case,method,a.seed]['trace'])
    def save(fig, name):
        for ext in ['png','pdf']:
            fig.savefig(a.output_dir/(name+'.'+ext), dpi=600, bbox_inches='tight')
        plt.close(fig)
    split = '独立留出' if plan['split']=='held_out' else '开发对照（非留出）'
    stamp = f'{split}；监督候选另含外部参考'
    if 'directional_rejoin_contract' in plan:
        stamp += '与条件式接入'
    LABELS.update({k:v.replace('−','-') for k,v in LABELS.items()})
    cases=[c['name'] for c in plan['cases']]
    columns=[(m,s) for m in ['legacy','supervised'] for s in plan['seeds']]
    symbols=['C','R','G','F','T']
    descriptions=['合格完成', '撤权／未完成', '错误几何授权', '错误任务完成', '超时未完成']
    matrix=np.zeros((len(cases),len(columns)),dtype=int)
    for i,c in enumerate(cases):
        for j,(m,s) in enumerate(columns):
            r=selected[c,m,s]
            matrix[i,j]=3 if r['false_completion'] else 2 if r['false_geometry_publication'] else 0 if r['true_quality_passed'] else 1 if r['withdrawal_time_s'] is not None else 4
    colors=[PROPOSED,'#d5dce3',WARNING,'#ad2b32',NEUTRAL]
    fig,ax=plt.subplots(figsize=(FULL_WIDTH,6.8),layout='constrained')
    fig.suptitle(stamp,fontsize=9)
    ax.imshow(matrix,cmap=ListedColormap(colors),vmin=0,vmax=4,aspect='auto')
    for i in range(len(cases)):
        for j in range(len(columns)):
            ax.text(j,i,symbols[matrix[i,j]],ha='center',va='center',fontsize=8,
                    color='white' if matrix[i,j] in [0,3,4] else 'black')
    ax.set_yticks(range(len(cases)),[LABELS[c] for c in cases],fontsize=8)
    ax.set_xticks(range(len(columns)),[('旧链' if m=='legacy' else '监督')+'\n'+str(s) for m,s in columns],fontsize=8)
    ax.set_xlabel('同版有限条件与种子；撤权不计入任务完成',fontsize=9)
    ax.legend(handles=[Patch(facecolor=co,label=f'{sy}：{d}') for sy,d,co in zip(symbols,descriptions,colors)],
              bbox_to_anchor=(.5,-.105),loc='upper center',ncol=3,fontsize=7,frameon=False)
    save(fig,'75_defense_robustness_outcome_matrix')

    fig, axes=plt.subplots(3,2,figsize=(FULL_WIDTH,7.5),layout='constrained')
    fig.suptitle(f'{stamp}，种子 {a.seed}',fontsize=8)
    colors_method={'legacy':BASELINE_1,'supervised':PROPOSED}
    names={'legacy':'旧链','supervised':'监督候选'}
    for method in ['legacy','supervised']:
        col=colors_method[method]; ls='--' if method=='legacy' else '-'
        for case,ax in [('steady_minus',axes[0,0]),('periodic_current',axes[0,1])]:
            rows=[r for r in trace(case,method) if r['mode']=='track']
            ax.plot(values(rows,'x_m'),values(rows,'y_m'),color=col,ls=ls,lw=1.,label=names[method])
        for case,axflow,axerror in [('periodic_current',axes[1,0],axes[1,1]),('step_current',axes[2,0],axes[2,1])]:
            r=trace(case,method); t0=selected[case,method,a.seed]['fault_start_s']; t=values(r,'time_s')-t0
            mask=t>=-10.; rr=[v for v,ok in zip(r,mask) if ok]; tt=t[mask]
            axflow.plot(tt,values(rr,'proxy_y_mps'),color=col,ls=ls,lw=1.,label=names[method]+'代理')
            axerror.plot(tt,values(rr,'true_offset_m'),color=col,ls=ls,lw=1.,label=names[method]+'真实横偏')
            if method=='supervised':
                axflow.plot(tt,values(rr,'true_current_mps'),color=REFERENCE,ls=':',lw=1.,label='注入横流（仅评价）')
                bound=values(rr,'robustness_true_offset_upper_bound_m'); valid=np.isfinite(bound)
                axerror.plot(tt[valid],bound[valid],color=REFERENCE,ls=':',lw=.9,label='条件上界（撤权前）')
            wd=selected[case,method,a.seed]['withdrawal_time_s']
            if wd is not None:
                axerror.axvline(wd-t0,color=col,lw=.8,ls=':',label=names[method]+'撤权')
    for ax in axes[0]:
        ax.axhline(6.,color=REFERENCE,ls=':',lw=.9,label='目标（仅评价）'); ax.set_xlim(-80,80)
        ax.set_xlabel('沿先验位置 / m'); ax.set_ylabel('法向位置 / m')
    axes[0,0].set_title('(a) 反向小流：接入与有限段',loc='left',fontsize=9)
    axes[0,1].set_title('(b) 周期小流：完整核心段',loc='left',fontsize=9)
    axes[1,0].set_title('(c) 周期流与含侧滑诊断代理',loc='left',fontsize=9)
    axes[1,1].set_title('(d) 周期流真实横偏与条件上界',loc='left',fontsize=9)
    axes[2,0].set_title('(e) 反向阶跃：代理的渐进响应',loc='left',fontsize=9)
    axes[2,1].set_title('(f) 撤权之后仍有实际运动',loc='left',fontsize=9)
    for ax in axes[1:,0]:
        ax.set_ylabel('横向速度 / (m/s)')
    for ax in axes[1:,1]:
        ax.set_ylabel('相对目标的横偏 / m'); ax.axhline(2.,color=WARNING,ls=':',lw=.8)
    for ax in axes[1:].flat:
        ax.set_xlim(-10,250); ax.set_xlabel('相对干扰起点的仿真时间 / s')
    for ax in axes.flat:
        ax.grid(alpha=.16)
    axes[2,1].text(.98,.04,'竖线：对应方法撤权',transform=axes[2,1].transAxes,ha='right',fontsize=7)
    fig.legend(handles=[Line2D([],[],color=BASELINE_1,ls='--',label='旧链'),
        Line2D([],[],color=PROPOSED,label='监督候选（含参考）'),
        Line2D([],[],color=REFERENCE,ls=':',label='评价参考／条件上界'),
        Line2D([],[],color=WARNING,ls=':',label='真实横偏评价门')],
        loc='upper center',bbox_to_anchor=(.5,-.01),ncol=2,fontsize=8,frameon=False)
    save(fig,'76_defense_current_process_and_limits')
    payload=dict(source_plan_sha256=manifest['plan_sha256'],split=plan['split'],seed=a.seed,
        source_run=str(a.run_dir.resolve()),script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        assets={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in a.output_dir.glob('*') if p.name.startswith(('75_','76_'))})
    (a.output_dir/'matrix_figure_manifest.json').write_text(json.dumps(payload,indent=2)+'\n')
    print(json.dumps(dict(figures=2,split=plan['split'])))


if __name__=='__main__':
    main()

#!/usr/bin/env python3
"""Compact paper figure: directional rejoin and geometry/mission separation."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from plot_v2_robustness_matrix import read, values
from thesis_plot_style import FULL_WIDTH, PROPOSED, BASELINE_1, WARNING, REFERENCE, NEUTRAL


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run-dir',required=True,type=Path)
    p.add_argument('--output-dir',required=True,type=Path)
    p.add_argument('--seed',type=int,default=501)
    a=p.parse_args(); a.output_dir.mkdir(parents=True,exist_ok=True)
    plan=json.loads((a.run_dir/'plan.json').read_text())
    manifest=json.loads((a.run_dir/'manifest.json').read_text())
    assert plan['split']=='held_out'
    assert hashlib.sha256((a.run_dir/'plan.json').read_bytes()).hexdigest()==manifest['plan_sha256']
    runs=json.loads((a.run_dir/'summary.json').read_text())
    selected={(s['case'],s['method']):s for s in runs if s['seed']==a.seed}
    fig,axes=plt.subplots(1,2,figsize=(FULL_WIDTH,3.0),layout='constrained')
    fig.suptitle(f'独立留出，种子 {a.seed}；监督候选含外部参考，接入收益另有消融',fontsize=8)
    old_end=None
    for method,color,style in [('legacy',BASELINE_1,'--'),('supervised',PROPOSED,'-')]:
        s=selected['steady_minus',method]; path=a.run_dir/s['trace']
        assert hashlib.sha256(path.read_bytes()).hexdigest()==s['trace_sha256']
        rows=[r for r in read(path) if r['mode']=='track' and 5.<=float(r['x_m'])<=75.]
        axes[0].plot(values(rows,'x_m'),values(rows,'true_offset_m'),color=color,ls=style,lw=1.2,
            label='旧链：20 m 接入' if method=='legacy' else '候选：5 m 接入')
        if method=='legacy':
            old_end=max(values(rows,'x_m'))
    axes[0].axvspan(old_end,75.,color=NEUTRAL,alpha=.1)
    axes[0].text((old_end+75.)/2.,.1,'旧链未覆盖',fontsize=7,rotation=90,va='bottom')
    axes[0].axhline(2.,color=WARNING,lw=.8,ls=':',label='最大横偏门')
    axes[0].set_xlim(5.,75.); axes[0].set_ylim(0,2.2)
    axes[0].set_title('(a) 反向小流：真实核心横偏',loc='left',fontsize=9)
    axes[0].set_xlabel('真实沿缆位置 / m'); axes[0].set_ylabel('真实横偏 / m')
    handles, labels=axes[0].get_legend_handles_labels()
    fig.legend(handles,labels,loc='upper center',bbox_to_anchor=(.5,-.01),ncol=3,fontsize=7,frameon=False)
    s=selected['fused_neighbor','legacy']
    errors=np.array([s['released_center_max_error_m'],s['core_true_mae_m'],s['core_true_max_m']])
    limits=np.array([.5,1.,2.]); ratios=errors/limits
    axes[1].bar(range(3),ratios,color=[WARNING,BASELINE_1,NEUTRAL],width=.55)
    for i,v in enumerate(ratios):
        axes[1].text(i,v+.12,f'{errors[i]:.3f} m',ha='center',va='bottom',fontsize=8)
    axes[1].axhline(1.,color=REFERENCE,lw=.9,ls=':')
    axes[1].set_ylim(0.,max(ratios)*1.3)
    axes[1].set_xticks(range(3),['发布中心\n门 0.5 m','载体 MAE\n门 1 m','载体最大\n门 2 m'],fontsize=8)
    axes[1].set_ylabel('误差 / 对应阈值')
    axes[1].set_title('(b) 融合邻源：几何仍错误',loc='left',fontsize=9)
    axes[1].text(.02,.98,'监督：目标几何未授权',transform=axes[1].transAxes,va='top',fontsize=7)
    for ax in axes:
        ax.grid(axis='y',alpha=.16)
    name='77_defense_robustness_thesis_summary'
    for ext in ['png','pdf']:
        fig.savefig(a.output_dir/(name+'.'+ext),dpi=600,bbox_inches='tight')
    plt.close(fig)
    metadata=dict(plan_sha256=manifest['plan_sha256'],seed=a.seed,split='held_out',
        script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        assets={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in a.output_dir.glob(name+'.*')})
    (a.output_dir/'thesis_figure_manifest.json').write_text(json.dumps(metadata,indent=2)+'\n')
    print(json.dumps(dict(figures=1,split='held_out')))


if __name__=='__main__':
    main()

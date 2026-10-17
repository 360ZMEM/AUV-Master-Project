#!/usr/bin/env python3
"""Plot the newly audited, bounded native-PVS magnetic inspection cases."""
from __future__ import annotations
import argparse
import csv
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from thesis_plot_style import (PROPOSED, BASELINE_1, BASELINE_2, BASELINE_3,
                               REFERENCE, WARNING, apply_thesis_style,
                               figure_size, save_figure)

ROOT = Path(__file__).resolve().parents[1]
STEM = '71_current_magnetic_simulation_closure'


def read(directory, case, seed):
    folder = 'native_pvs' if seed == 101 else 'native_seed102_103'
    with (directory/folder/f'{case}_seed_{seed}.csv').open() as stream:
        return list(csv.DictReader(stream))


def values(rows, key):
    return np.array([float(r[key]) for r in rows])


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--results', type=Path, required=True)
    p.add_argument('--output-base', type=Path, required=True)
    args = p.parse_args()
    wire = read(args.results, 'wire', 101)
    none = read(args.results, 'no_source', 101)
    apply_thesis_style(base_font_size=9)
    fig, axes = plt.subplot_mosaic([['map','center'],['map','error']],
        figsize=figure_size(height=3.8), gridspec_kw={'width_ratios':[1.18,1.]})
    fig.subplots_adjust(left=.09,right=.98,bottom=.23,top=.90,wspace=.38,hspace=.62)
    ax = axes['map']
    x, y = values(wire,'x_m'), values(wire,'y_m')
    modes = np.array([r['mode'] for r in wire]); stages=np.array([r['stage'] for r in wire])
    styles = [((modes=='search'),BASELINE_1,'先验搜索'),
              ((modes=='confirm'),PROPOSED,'主动横切'),
              ((modes=='track')&(x<5.),BASELINE_3,'前向接入'),
              ((modes=='track')&(x>=5.),BASELINE_2,'沿缆巡检')]
    for selected,color,label in styles:
        ax.plot(np.where(selected,x,np.nan),np.where(selected,y,np.nan),color=color,lw=1.5,label=label)
    ax.plot([-260.,90.],[6.,6.],color=REFERENCE,lw=.9,label='真实电缆')
    ax.plot([0.,80.],[0.,0.],'--',color=REFERENCE,lw=.9,label='偏移先验')
    ax.axvspan(5.,75.,color=BASELINE_2,alpha=.08,label='70 m 核验段')
    ax.scatter([x[0]],[y[0]],color=BASELINE_1,s=16,zorder=5)
    ax.scatter([x[-1]],[y[-1]],color=BASELINE_2,marker='s',s=18,zorder=5)
    ax.scatter([float(none[-1]['x_m'])],[float(none[-1]['y_m'])],color=WARNING,marker='x',s=26,zorder=6)
    ax.annotate('无源：拒绝跟踪',xy=(float(none[-1]['x_m']),float(none[-1]['y_m'])),
                xytext=(-185.,21.),fontsize=7,color=WARNING,
                arrowprops={'arrowstyle':'-','color':WARNING,'lw':.7})
    ax.set(xlabel='沿缆方向位置 / m',ylabel='横向位置 / m',
           title='(a) 当前源码的完整巡检过程',xlim=(-265.,90.),ylim=(-22.,26.))
    handles,labels=ax.get_legend_handles_labels()
    fig.legend(handles,labels,loc='lower center',bbox_to_anchor=(.52,.005),ncol=4,
               fontsize=7,frameon=False,columnspacing=1.4)

    ax=axes['center']
    ax.axhline(6.,color=REFERENCE,lw=.9,label='真实中心')
    for case,color,label,style in [('wire',PROPOSED,'单直导线','-'),('dipole',BASELINE_1,'偶极包络','--')]:
        rows=read(args.results,case,101)
        selected=[r for r in rows if r['lateral_valid']=='True']
        ax.plot(values(selected,'time_s'),values(selected,'estimated_cable_y_m'),
                color=color,ls=style,lw=1.3,label=label)
    ax.set(xlabel='仿真时间 / s',ylabel='估计横向中心 / m',ylim=(5.96,6.04),
           title='(b) 发布横向中心，埋深保持空值')
    ax.legend(loc='upper right',fontsize=6.7,ncol=2)

    ax=axes['error']
    for case,color,label,style in [('wire',PROPOSED,'单直导线','-'),('dipole',BASELINE_1,'偶极包络','--')]:
        for seed in (101,102,103):
            rows=[r for r in read(args.results,case,seed) if r['mode']=='track' and float(r['x_m'])>=0.]
            xx=values(rows,'x_m'); err=np.abs(values(rows,'y_m')-6.)
            ax.plot(xx,err,color=color,ls=style,lw=1.2 if seed==101 else .65,
                    alpha=1. if seed==101 else .35,label=label if seed==101 else None)
    ax.axvspan(5.,75.,color=BASELINE_2,alpha=.08)
    ax.axhline(2.,color=WARNING,ls=':',lw=.9,label='2 m 上限')
    ax.set(xlabel='沿缆方向位置 / m',ylabel='真实横向误差 / m',
           title='(c) 两场形、三种子的沿程误差',xlim=(0.,80.),ylim=(0.,2.3))
    ax.legend(loc='upper right',fontsize=6.7,ncol=2)
    save_figure(fig,args.output_base)
    plt.close(fig)


if __name__ == '__main__':
    main()

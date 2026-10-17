#!/usr/bin/env python3
"""Re-export three middle-defense figures from frozen evidence; no experiments.

Run: python3 tools/plot_middle_systems.py
Needs numpy, matplotlib and PyMuPDF; Poppler renders the preview PNGs.  PyMuPDF
is used only for lossless vector composition, not rendering embedded CJK fonts.
"""
from __future__ import annotations
import csv
import hashlib
import io
import json
import re
from pathlib import Path
import subprocess
import sys

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from matplotlib.legend_handler import HandlerTuple
try:
    import pymupdf as fitz
except ImportError as exc:
    raise SystemExit('Install the plotting-only dependency: python3 -m pip install pymupdf') from exc

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import thesis_plot_style as tps
OUT = ROOT / 'thuthesis/middle/figures/systems'
WIDTH = 150 / 25.4
MIN_FONT = 9.5

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def rel(path):
    return str(path.relative_to(ROOT))

def style():
    tps.apply_thesis_style()
    plt.rcParams.update({'font.size':10, 'axes.labelsize':10, 'axes.titlesize':10,
                        'legend.fontsize':MIN_FONT, 'xtick.labelsize':MIN_FONT,
                        'ytick.labelsize':MIN_FONT, 'savefig.bbox':None,
                        'pdf.fonttype':42, 'lines.linewidth':1.15})

def pdf_bytes(fig):
    buffer = io.BytesIO()
    fig.savefig(buffer, format='pdf', bbox_inches=None,
                metadata={'CreationDate':None, 'ModDate':None})
    return buffer.getvalue()

def export(fig, stem):
    path = OUT / f'{stem}.pdf'
    path.write_bytes(pdf_bytes(fig))
    plt.close(fig)
    return path

def preview(path):
    # Poppler correctly renders the CFF Song font embedded by Matplotlib.
    subprocess.run(['pdftoppm','-singlefile','-png','-r','300',str(path),str(path.with_suffix(''))], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)

def font_measure(path):
    doc = fitz.open(path)
    spans = [s for b in doc[0].get_text('dict')['blocks'] if 'lines' in b
             for line in b['lines'] for s in line['spans'] if s['text'].strip()]
    scale = (150/25.4*72)/doc[0].rect.width
    return {'pdf_width_pt':doc[0].rect.width, 'pdf_height_pt':doc[0].rect.height,
            'font_sizes_pt':sorted(set(round(s['size'],4) for s in spans)),
            'min_final_font_pt_at_150mm':round(min(s['size'] for s in spans)*scale,4),
            'all_final_text_at_least_9pt':all(s['size']*scale >= 9 for s in spans)}

def plot_iq():
    source = ROOT / 'results/magnetic_analysis/20260809_r07_45hz_reanalysis/joint_geometry_rerun/1783235358_205719/aligned_timeseries.npz'
    a = np.load(source, allow_pickle=False)
    t = a['timestamp'] - a['timestamp'][0]
    fig, axes = plt.subplots(3,2,figsize=(WIDTH,5.7),sharex=True)
    fig.subplots_adjust(left=.125,right=.982,bottom=.12,top=.88,hspace=.20,wspace=.30)
    for row in range(3):
        for col,component in enumerate(['real','imag']):
            ax=axes[row,col]
            ax.plot(t,a[f'complex_phasor_{component}_ut'][:,row],color=tps.PROPOSED,label='实测')
            ax.plot(t,a[f'complex_model_{component}_ut'][:,row],color=tps.BASELINE_1,ls='--',label='模型')
            ax.set_ylabel(f'CH{row+1} (μT)' if col==0 else '')
            ax.tick_params(axis='both',pad=2)
            ax.set_xticks([0,10,20,30,40])
            ax.grid(alpha=.35)
        axes[-1,0].set_xlabel('时间 (s)')
        axes[-1,1].set_xlabel('时间 (s)')
    axes[0,0].set_title('(a) 同相分量',loc='left',pad=6)
    axes[0,1].set_title('(b) 正交分量',loc='left',pad=6)
    fig.legend(*axes[0,0].get_legend_handles_labels(),loc='upper center',ncol=2,
               bbox_to_anchor=(.55,.994),frameon=False)
    return export(fig,'complex_iq_fit_middle'),[source],{
        'method':'直接读取已存档777个实测/模型复数序列，仅重新排版；没有重跑锁相或拟合',
        'arrays':['timestamp','complex_phasor_real_ut','complex_phasor_imag_ut','complex_model_real_ut','complex_model_imag_ut'],
        'sample_count':len(t),'transforms':'时间减去首个时间戳；曲线值不变，单位μT'}

def plot_jetson():
    base=ROOT/'real_experiments/jetson_realtime/data/runs/20260822_165846'
    sources=[]; arrays=[]; success=[]
    for condition in ['steady','stress']:
        for mode in ['cold','warm']:
            p=base/condition/f'mpc_solve_microbench_{mode}_raw.csv';sources.append(p)
            with p.open(newline='') as f: rows=list(csv.DictReader(f))
            arrays.append(np.array([float(r['wall_ms']) for r in rows]))
            success.append(100*sum(r['solver_status']=='Solve_Succeeded' for r in rows)/len(rows))
    labels=['稳态\n冷启动','稳态\n热启动','约束压力\n冷启动','约束压力\n热启动']
    colors=[tps.BASELINE_1,tps.PROPOSED,tps.BASELINE_2,tps.BASELINE_3]
    fig,axes=plt.subplots(2,1,figsize=(WIDTH,5.55),gridspec_kw={'height_ratios':[1.3,1]})
    fig.subplots_adjust(left=.15,right=.97,bottom=.13,top=.95,hspace=.60)
    bp=axes[0].boxplot(arrays,labels=labels,showfliers=False,patch_artist=True)
    for patch,c in zip(bp['boxes'],colors):patch.set_facecolor(c);patch.set_alpha(.72)
    axes[0].axhline(50,color=tps.REFERENCE,ls='--',lw=1.2,label='20 Hz 周期：50 ms')
    axes[0].axhline(200,color=tps.NEUTRAL,ls=':',lw=1.2,label='MPC 离散周期：200 ms')
    axes[0].set_yscale('log');axes[0].set_ylim(25,320)
    axes[0].set_yticks([30,50,100,200]);axes[0].set_yticklabels(['30','50','100','200'])
    axes[0].yaxis.set_minor_locator(matplotlib.ticker.NullLocator())
    axes[0].set_ylabel('求解时延 (ms，对数轴)')
    axes[0].set_title('(a) 目标平台 MPC 求解时延',loc='left')
    axes[0].legend(loc='upper left',frameon=True)
    bars=axes[1].bar(range(1,5),success,color=colors,alpha=.8)
    for b,s in zip(bars,success):axes[1].text(b.get_x()+b.get_width()/2,s+2,f'{s:.0f}%',ha='center',fontsize=MIN_FONT)
    axes[1].set_xticks(range(1,5),labels);axes[1].set_ylim(0,118)
    axes[1].set_ylabel('求解成功率 (%)');axes[1].set_title('(b) 稳态与约束压力下的可行性',loc='left')
    return export(fig,'jetson_mpc_latency_and_success_middle'),sources,{
        'method':'既有4个CSV重新绘箱线与成功率，showfliers=False沿用旧图；无新求解或平台测试',
        'samples_per_group':[len(x)for x in arrays],'success_percent':success,
        'transform':'时延值不变；log轴改用普通数字刻度；标签换行；共500次既有样本'}

def plot_pc104():
    source=ROOT/'docs/thesis/figures/hardware/pc104_cross_layer/pc104_cross_layer_fault_timeline.pdf'
    original=fitz.open(source)
    # New in-memory copy; the source PDF and all archived paths stay untouched.
    vector=fitz.open(stream=original.tobytes(),filetype='pdf');page=vector[0]
    # The first three interiors contain no text.  The fourth original legend
    # is removed from the in-memory presentation copy above the y=0 samples.
    # graphics=1 removes only paths fully covered by this top legend band; no
    # command sample path intersects it (all command observations at y=0).
    page.add_redact_annot(fitz.Rect(130,254,420,282),fill=False)
    page.apply_redactions(images=0,graphics=1,text=0)
    for b in page.get_text('dict')['blocks']:
        for line in b.get('lines',[]):
            for s in line['spans']:
                page.add_redact_annot(s['bbox'],fill=False)
    page.apply_redactions(images=0,graphics=0,text=0)
    clips=[fitz.Rect(60.2456245,y0,486.4795227,y1) for y0,y1 in [
        (38.5301208,95.8031006),(119.9035797,177.1765747),
        (186.6770477,243.9500427),(253.4505310,310.7235107)]]
    # Recover the positions of the existing x tick/grid lines, not timestamps.
    grids=sorted(set(round(float(d['rect'].x0),5) for d in original[0].get_drawings()
        if d['type']=='s' and d['color'] and .7 < d['color'][0] < .75 and d['rect'].width<.001 and
        abs(d['rect'].y0-clips[0].y0)<.002 and abs(d['rect'].height-clips[0].height)<.002))
    # Recover only the six grey 0,2,...10s gridlines (not reauthorization lines).
    ticks=grids
    if len(ticks)!=6:raise RuntimeError(f'Unexpected archived tick geometry: {grids}')
    xs=[(v-clips[0].x0)/clips[0].width for v in ticks]
    fig,axes=plt.subplots(4,1,figsize=(WIDTH,6.7),sharex=True)
    fig.subplots_adjust(left=.19,right=.975,bottom=.11,top=.865,hspace=.46)
    specs=[((-0.12,1.2),[0,1],['0','1'],'故障位'),
           ((-.25,2.25),[0,1,2],['锁定','有效','拒绝'],'仲裁状态'),
           ((-.25,2.25),[0,1,2],['待机','平行跟踪','之字搜索'],'任务输出'),
           ((-.05,.15),[0,.1],['0.0','0.1'],'最大绝对命令')]
    for ax,(ylim,tick,label,ylabel) in zip(axes,specs):
        ax.set_xlim(0,1);ax.set_ylim(*ylim);ax.set_yticks(tick,label);ax.set_ylabel(ylabel)
        ax.grid(False);ax.tick_params(axis='both',pad=3)
    axes[-1].set_xticks(xs,[str(v)for v in range(0,12,2)])
    axes[-1].set_xlabel('相对健康自主基线的时间 (s)')
    fault_specs=[('#55a868',tps.BASELINE_2,'-.','Bit13 DVL 失锁'),
                 ('#dd8452',tps.BASELINE_1,'--','Bit5 系统通信'),
                 ('#c44e52',tps.BASELINE_3,':','Bit14 看门狗')]
    handles=[(Patch(facecolor=bg,alpha=.12),Line2D([0],[0],color=line,ls=ls))for bg,line,ls,_ in fault_specs]
    fig.legend(handles,[v[3] for v in fault_specs],handler_map={tuple:HandlerTuple(ndivide=None)},
               loc='upper center',bbox_to_anchor=(.565,.995),ncol=2,frameon=False)
    command_handles=[Line2D([0],[0],marker='o',ls='',color=c,markersize=3) for c in tps.ACCENT_COLORS[:3]]
    fig.legend(command_handles,['上行推进反馈','影子执行量','板端命令快照'],
               loc='lower center',bbox_to_anchor=(.575,axes[3].get_position().y1+.006),ncol=3,frameon=False)
    # Vector bodies are placed inside the new axes only.  This nonuniform
    # page-layout scaling is explicitly recorded; it does not infer new data.
    fig.canvas.draw(); new=fitz.open(stream=pdf_bytes(fig),filetype='pdf');height=new[0].rect.height
    destinations=[]
    for ax,clip in zip(axes,clips):
        box=ax.get_position();dest=fitz.Rect(box.x0*WIDTH*72,(1-box.y1)*height,
                                          box.x1*WIDTH*72,(1-box.y0)*height)
        new[0].show_pdf_page(dest,vector,0,clip=clip,keep_proportion=False,overlay=True)
        new[0].draw_rect(dest,color=(0,0,0),width=.9,overlay=True)
        destinations.append(list(dest))
    path=OUT/'pc104_cross_layer_fault_timeline_middle.pdf'
    new.set_metadata({'title':'PC104同步故障记录：中期报告矢量版式适配','creator':'plot_middle_systems.py'})
    new.save(path,garbage=4,deflate=True,no_new_id=True);plt.close(fig)
    return path,[source],{'method':'仅从旧PDF的四块绘图区保留矢量曲线/色带/零命令样本，坐标与图例重新排版；不重构raw事件',
        'evidence_level':'原始运行CSV在当前副本缺失；此图不构成新数据重算或新实验',
        'source_plot_clips_top_left_pdf_pt':[list(v)for v in clips],
        'destination_rects_top_left_pdf_pt':destinations,
        'x_tick_positions_source_pdf_pt':ticks,
        'retained_domain':'完整原图时间域、原故障/仲裁/任务状态与命令曲线；未裁除任何时间区间',
        'layout_only_changes':'移出原第四面板内图例，删去图内重复延时说明（图注保留）；绘图区非等比版式变换，各轴刻度映射保持',
        'command_evidence':'原图三类命令/反馈均为0；移除的图例上部区域不与y=0采样曲线相交'}

def main():
    OUT.mkdir(parents=True,exist_ok=True);style()
    record_path=ROOT/'docs/middle-defense/middle-systems-figures.json'
    previous=json.loads(record_path.read_text()) if record_path.exists() else {}
    source_graphics=[ROOT/p for p in [
       'docs/thesis/figures/experiments/magnetic_joint/complex_iq_fit.pdf',
       'real_experiments/jetson_realtime/figures/jetson_mpc_latency_and_success.pdf',
       'docs/thesis/figures/hardware/pc104_cross_layer/pc104_cross_layer_fault_timeline.pdf']]
    before={rel(p):sha(p)for p in source_graphics}
    records=[]
    for fn in [plot_iq,plot_jetson,plot_pc104]:
        path,sources,info=fn();preview(path);measurement=font_measure(path)
        if not measurement['all_final_text_at_least_9pt']:raise RuntimeError(f'Small figure text: {path} {measurement}')
        records.append({'output_pdf':rel(path),'output_png':rel(path.with_suffix('.png')),
                        'pdf_sha256':sha(path),'png_sha256':sha(path.with_suffix('.png')),
                        'sources':[{'path':rel(p),'sha256':sha(p)}for p in sources],
                        'derivation':info,'typography':measurement})
    after={rel(p):sha(p)for p in source_graphics}
    assert before==after,'Archived figure changed'
    record={'schema_version':1,'generated_by':'tools/plot_middle_systems.py','generated_by_sha256':sha(Path(__file__)),
            'python_executable':sys.executable,'new_experiments':False,
            'fonts':'FandolSong（沿用tools/thesis_plot_style.py），数学STIX；不声称STSong或Times New Roman',
            'width_mm':150,'minimum_font_pt':MIN_FONT,
            'reexport':f'{sys.executable} tools/plot_middle_systems.py；锁定依赖见tools/requirements-middle-figures.txt，另需poppler-utils',
            'old_figures_unchanged':before==after,'old_figure_sha256':after,'figures':records,
            'visual_review':'pending; exact final PDF placement must be checked after LaTeX rebuild'}
    previous_png={r['output_png']:r['png_sha256']for r in previous.get('figures',[])}
    if previous_png=={r['output_png']:r['png_sha256']for r in records} and previous.get('visual_review',{}).get('status')=='PASS':
        record['visual_review']=previous['visual_review']
        record['visual_review']['reexport_validation']='持久虚拟环境重新导出；3个PNG与实际查看版本逐字节SHA256一致，保留视觉验收'
    record_path.write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'outputs':[r['output_pdf']for r in records],'min_final_font_pt':[r['typography']['min_final_font_pt_at_150mm']for r in records]},ensure_ascii=False))

def audit_final():
    """Append actual final PDF measurements for all nine middle-report figures."""
    def spans(page):
        return [s for b in page.get_text('dict')['blocks'] if 'lines' in b
                for line in b['lines'] for s in line['spans'] if s['text'].strip()]
    source_paths=[]
    for name in ['chap03-magnetic.tex','chap04-systems.tex']:
        text=(ROOT/'thuthesis/middle'/name).read_text()
        for match in re.finditer(r'\\includegraphics\[[^]]*\]\{([^}]+)\}',text):
            path=(ROOT/'thuthesis'/match.group(1)).resolve()
            source_paths.append(path)
    if len(source_paths)!=8:
        raise RuntimeError(f'Expected eight external result figures, got {len(source_paths)}')
    result={'method':'最终PDF根Form XObject的实际缩放矩阵 × 源PDF字号，并核对最终文本匹配；1 PDF pt=1/72 inch',
            'minimum_critical_font_pt':8,'preferred_font_pt':9,'pdfs':{},'figures':[]}
    source_docs=[fitz.open(path) for path in source_paths]
    for variant in ['main','school']:
        path=ROOT/f'thuthesis/build/middle-{variant}/auv-middle-defense-{variant}.pdf'
        document=fitz.open(path)
        result['pdfs'][variant]={'path':rel(path),'sha256':sha(path),'pages':len(document)}
        forms=[]
        for pi,page in enumerate(document):
            for form in page.get_xobjects():
                if form[2]==0:forms.append((pi,page,form))
        if len(forms)!=8:raise RuntimeError(f'{variant}: expected eight root forms, got {len(forms)}')
        # TeX serializes external pictures as Fm0,Fm1,... in inclusion order.
        forms.sort(key=lambda item:int(item[2][1][2:]))
        for i,((pi,page,form),source) in enumerate(zip(forms,source_docs)):
            rect=fitz.Rect(form[3]); source_page=source[0]
            if abs(rect.width-source_page.rect.width)>.03 or abs(rect.height-source_page.rect.height)>.03:
                raise RuntimeError(f'{variant}: figure order/size mismatch at {i}')
            content=page.read_contents().decode('latin1')
            pattern=r'q\s+([.\d]+) 0 0 ([.\d]+) [-.\d]+ [-.\d]+ cm q 1 0 0 1 [-.\d]+ [-.\d]+ cm /'+re.escape(form[1])+r' Do'
            match=re.search(pattern,content)
            if match:
                scale=float(match.group(1))
            else:
                # At native 150mm width XeTeX can omit the identity scale.
                direct=r'q 1 0 0 1 [-.\d]+ [-.\d]+ cm /'+re.escape(form[1])+r' Do'
                if not re.search(direct,content):raise RuntimeError(f'Unknown placement transform: {variant} {form[1]}')
                scale=1.0
            ss=spans(source_page); fs=spans(page)
            sizes=sorted(set(round(s['size']*scale,4)for s in ss))
            direct_matches=sum(any(z['text']==s['text'] and abs(z['size']-s['size']*scale)<.02 for z in fs) for s in ss)
            actual_min=min(s['size']*scale for s in ss)
            item={'variant':variant,'index':i+1,'page':pi+1,'source':rel(source_paths[i]),
                  'source_sha256':sha(source_paths[i]),'scale':scale,
                  'placed_width_mm':round(rect.width*scale*25.4/72,3),
                  'placed_height_mm':round(rect.height*scale*25.4/72,3),
                  'font_sizes_final_pt':sizes,'min_final_font_pt':round(actual_min,4),
                  'final_text_spans_matched':direct_matches,'source_text_span_count':len(ss),
                  'pass_8pt':actual_min>=8,'pass_preferred_9pt':actual_min>=9}
            if direct_matches==0:raise RuntimeError(f'No direct final font match: {item}')
            result['figures'].append(item)
        tikz=[]
        for pi,page in enumerate(document):
            for s in spans(page):
                if s['text']=='磁采集、导航':tikz.append({'page':pi+1,'font_pt':s['size']})
        if len(tikz)!=1:raise RuntimeError(f'TikZ identification failed: {variant}')
        result['figures'].append({'variant':variant,'index':0,'source':'thuthesis/middle/chap02-design.tex',
                                 'page':tikz[0]['page'],'min_final_font_pt':tikz[0]['font_pt'],
                                 'pass_8pt':tikz[0]['font_pt']>=8,'pass_preferred_9pt':tikz[0]['font_pt']>=9})
    result['all_18_placements_pass_8pt']=all(r['pass_8pt'] for r in result['figures'])
    result['all_18_placements_pass_9pt']=all(r['pass_preferred_9pt'] for r in result['figures'])
    result['scope']='字高与缩放验收；重叠、越界及整页密度仍需Poppler最终页面视觉验收'
    output=ROOT/'docs/middle-defense/figure-size-check.json'
    old=json.loads(output.read_text());old['post_fix']=result
    old['recheck_command']=f'{sys.executable} tools/plot_middle_systems.py --audit-final'
    output.write_text(json.dumps(old,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'pass_8pt':result['all_18_placements_pass_8pt'],'pass_9pt':result['all_18_placements_pass_9pt'],
                      'figures':[{k:v for k,v in row.items()if k in ['variant','index','page','min_final_font_pt']}for row in result['figures']]},ensure_ascii=False))

if __name__=='__main__':
    if sys.argv[1:]==['--audit-final']:audit_final()
    elif not sys.argv[1:]:main()
    else:raise SystemExit('Usage: plot_middle_systems.py [--audit-final]')

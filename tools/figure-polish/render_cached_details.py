#!/usr/bin/env python3
"""Plot-only adapters for exact archived thesis inputs; no solvers/simulations."""
from __future__ import annotations
import argparse,csv,hashlib,json,re,sys,traceback
from pathlib import Path
from weakref import WeakSet
sys.path.insert(0,str(Path(__file__).resolve().parent))
import render_selected_plots as base
ROOT,RUN=base.ROOT,base.RUN
OUT=RUN/'plot-candidates/details'
import matplotlib.pyplot as plt
from matplotlib.figure import Figure
import thesis_plot_style as tps
from figure_polish_audit import inspect_figure
_original_save=Figure.savefig
_seen=WeakSet()
def measured_save(fig,filename,*args,**kwargs):
    if fig not in _seen and isinstance(filename,(str,Path)):
        inspect_figure(fig,RUN/'mpl'/(Path(filename).stem+'.json'))
        if fig.get_constrained_layout():fig.set_layout_engine(None)
        _seen.add(fig)
    return _original_save(fig,filename,*args,**kwargs)
Figure.savefig=measured_save

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def ensure(paths):
    missing=[str(p) for p in paths if not Path(p).is_file()]
    if missing:raise FileNotFoundError('\n'.join(missing))
    return {str(p):sha(p) for p in paths}
def cli(module,**args):
    saved=sys.argv
    sys.argv=[module.__file__]+[str(v) for k,val in args.items() for v in ('--'+k.replace('_','-'),val)]
    try:module.main()
    finally:sys.argv=saved

def noise():
    m=base.module('real_experiments/mag_chain_noise_ros/scripts/analyze_mag_noise_ros_run.py')
    source=ROOT/'real_experiments/mag_chain_noise_ros/data/summary.csv'
    inputs=ensure([source]);out=OUT/'noise';out.mkdir(parents=True,exist_ok=True)
    with source.open() as f:rows=list(csv.DictReader(f))
    m._plot_summary(rows,out);return inputs

def extrinsics():
    m=base.module('tools/plot_mag_extrinsics_validation.py')
    inputs=ensure([m.DEFAULT_INPUT/'validation_summary.json',m.DEFAULT_INPUT/'residuals.csv'])
    cli(m,input_dir=m.DEFAULT_INPUT,output_dir=OUT/'extrinsics');return inputs

def sensitivity():
    m=base.module('tools/plot_es_ekf_sensitivity.py');inputs=ensure([m.REPORT])
    cli(m,output_base=OUT/'sensitivity/eskf_param_sensitivity');return inputs

def iq():
    # Reuse the archived-array renderer; never call its PDF-composition routines.
    m=base.module('tools/plot_middle_systems.py')
    source=ROOT/'results/magnetic_analysis/20260809_r07_45hz_reanalysis/joint_geometry_rerun/1783235358_205719/aligned_timeseries.npz'
    inputs=ensure([source]);m.WIDTH=tps.FULL_WIDTH
    def export(fig,stem):
        p=OUT/'iq/complex_iq_fit'
        for ax in fig.axes[-2:]:ax.set_xlabel('相对对齐起点的时间 (s)')
        tps.save_figure(fig,p);plt.close(fig);return p.with_suffix('.pdf')
    m.export=export;m.plot_iq();return inputs

def pvs():
    m=base.module('tools/plot_pvs_closedloop_recovery.py')
    inputs=ensure([m.CLOSEDLOOP_ROOT/p/'tracking.jsonl' for p in ['cl_heavy_run1_recovery','cl_heavy_run1_prioroff']])
    m.plot_recovery(m.CLOSEDLOOP_ROOT,OUT/'pvs/pvs_closedloop_recovery_prior_alignment.pdf',3.4);return inputs

def scorecard():
    m=base.module('tools/plot_cable_dlt1278_scorecard.py')
    source=ROOT/'results/cable_ops_report/acceptance_fresh1_20260706_135331/inspection_summary.json'
    inputs=ensure([source]);cli(m,summary=source,output=OUT/'scorecard/cable_dlt1278_scorecard_fresh1.pdf');return inputs

def closure():
    m=base.module('tools/plot_v2_simulation_closure.py')
    source=ROOT/'AUV-Master-Mag/results/v2/inspection_simulation_closure_20260928'
    inputs=ensure(list((source/'native_pvs').glob('*.csv'))+list((source/'native_seed102_103').glob('*.csv')))
    cli(m,results=source,output_base=OUT/'closure'/m.STEM);return inputs

def robustness():
    m=base.module('tools/plot_v2_robustness_thesis_summary.py')
    source=ROOT/'AUV-Master-Mag/results/v2/defense_robustness_20260929/05_held_out'
    summary=json.loads((source/'summary.json').read_text())
    files=[source/'summary.json',source/'manifest.json',source/'plan.json']
    files += [source/s['trace'] for s in summary if s['seed']==501 and (s['case'],s['method']) in {('steady_minus','legacy'),('steady_minus','supervised')}]
    inputs=ensure(files);cli(m,run_dir=source,output_dir=OUT/'robustness');return inputs

def historical():
    m=base.module('tools/plot_v2_shallow_survey_ros_pvs.py')
    files=[p.with_suffix('.csv') for p in m.FILES.values()]+[p.with_name(p.name+'_summary.json') for p in m.FILES.values()]
    inputs=ensure(files);m.PUB=OUT/'historical/publication';m.THESIS=OUT/'historical/thesis'
    (m.PUB/'data').mkdir(parents=True,exist_ok=True)
    m.main(allow_historical_source=True);return inputs

def round2():
    m=base.module('patent/round2/20261020T015226Z/delivery/figures/experiments/plot_round2_evidence.py')
    original=json.loads((ROOT/'docs/thesis/figures/magnetics/round2_20261020/plot_manifest.json').read_text())
    sources=[Path(r['path']) for r in original['sources']];inputs=ensure(sources)
    assert all(sha(p)==r['sha256'] for p,r in zip(sources,original['sources']))
    rows,_=m.read_metrics(sources,'G3');example=original['figures']['reference']['example']
    out=OUT/'round2';out.mkdir(parents=True,exist_ok=True)
    original=m.save_figure
    def presentation_save(fig,output,name):
        if name=='r2_reference_lifecycle':
            for text in fig.texts:
                if text.get_text().startswith('H1与强基线输出一致'):
                    text.set_y(.012)
        return original(fig,output,name)
    m.save_figure=presentation_save
    m.lifecycle_figure(rows,out,'G3',example['group'],example['seed']);m.pressure_figure(rows,out,'G3');return inputs

def coverage():
    m=base.module('tools/normalized_coverage_sweep.py')
    source=ROOT/'results/coverage_normalized/20260809_r12/coverage_sweep.csv'
    inputs=ensure([source])
    with source.open() as f: rows=list(csv.DictReader(f))
    # CSV strings become the numbers expected by the original plot selector;
    # read only the cached sweep, never call generate_rows/evaluate_configuration.
    for row in rows:
        for key in ['beam_deg','magnetic_width_ratio','speed_ratio','lateral_error_ratio','spacing_ratio','mission_time_normalized','guaranteed_coverage_ratio']:
            row[key]=float(row[key])
    (OUT/'coverage/figures').mkdir(parents=True,exist_ok=True)
    m.write_plots(OUT/'coverage',rows);return inputs

def jetson():
    m=base.module('real_experiments/jetson_realtime/scripts/run_jetson_realtime.py')
    source=ROOT/'real_experiments/jetson_realtime/data/runs/20260822_165846'
    inputs=ensure([source/c/f'mpc_solve_microbench_{mode}_raw.csv' for c in ['steady','stress'] for mode in ['cold','warm']])
    out=OUT/'jetson';out.mkdir(parents=True,exist_ok=True)
    m.plot_solver_distributions(out,{c:source/c for c in ['steady','stress']},{'ros_controller_20hz':50,'mpc_discretization_dt':200})
    return inputs

def fwhm():
    m=base.module('tools/plot_fwhm_v2_publication.py')
    inputs=ensure([m.RESULTS/c/n for c in ['stability_comparison','shape_guard_validation'] for n in ['summary.json','per_run.csv']])
    m.FIG=OUT/'fwhm/publication';m.THESIS_FIG=OUT/'fwhm/thesis'
    m.plot_stability_comparison();m.plot_stability_sensitivity();m.plot_shape_guard_validation()
    return inputs

def decision():
    m=base.module('tests/benchmark_bt_vs_fsm.py')
    source=ROOT/'docs/thesis/figures/experiments/decision_bt_vs_fsm/_source_report.md'
    inputs=ensure([source])
    match=re.search(r'BT ~(\d+)行/状态 vs FSM ~(\d+)行/状态',source.read_text())
    if not match:raise ValueError('Archived expansion cost values unavailable')
    m.plot_expansion_cost({'bt_new_state_lines':int(match[1]),'fsm_new_state_lines':int(match[2])},OUT/'decision')
    return inputs

def trajectory():
    # This archived NPZ is also the original I/Q plot input. Reuse its stored
    # TMR positions and vector amplitudes; never refit the wire geometry.
    import numpy as np
    source=ROOT/'results/magnetic_analysis/20260809_r07_45hz_reanalysis/joint_geometry_rerun/1783235358_205719/aligned_timeseries.npz'
    inputs=ensure([source]);arrays=np.load(source,allow_pickle=False)
    fig,ax=plt.subplots(figsize=(3.3,3.0),constrained_layout=True)
    points=ax.scatter(arrays['tmr_position_m'][:,0],arrays['tmr_position_m'][:,1],
                      c=arrays['vector_amplitude_ut'],s=16,cmap='cividis')
    ax.set_xlabel('TMR 在 aruco1 坐标系的 X 位置 (m)')
    ax.set_ylabel('TMR 在 aruco1 坐标系的 Y 位置 (m)')
    # Retain the original published spatial domain; this is a font/layout
    # replay, not a zoomed view that could alter its visual interpretation.
    ax.set_xlim(-.55,.05);ax.set_xticks(np.arange(-.5,.01,.1));ax.set_ylim(-.18,.5)
    ax.grid(True,alpha=.3)
    fig.colorbar(points,ax=ax,label='45 Hz 磁场模量 (μT)')
    tps.save_figure(fig,OUT/'trajectory/trajectory_colored_by_b');plt.close(fig)
    return inputs

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--group',action='append',choices=['noise','extrinsics','sensitivity','iq','pvs','scorecard','closure','robustness','historical','round2','coverage','jetson','fwhm','decision','trajectory']);a=p.parse_args()
    records=[]
    for name in a.group or ['noise','extrinsics','sensitivity','iq','pvs','scorecard','closure','robustness','historical','round2','coverage','jetson','fwhm','decision','trajectory']:
        try:
            tps.apply_thesis_style();inputs=globals()[name]()
            assert inputs=={path:sha(path) for path in inputs},'input changed during render'
            records.append({'group':name,'status':'RENDERED_AWAITING_REVIEW','input_sha256':inputs})
        except (Exception,SystemExit):records.append({'group':name,'status':'BLOCKED','traceback':traceback.format_exc()})
        print(name,records[-1]['status'],flush=True)
    path=RUN/'cached_detail_runs.json';prior=json.loads(path.read_text()) if path.exists() else {}
    prior.update({r['group']:r for r in records});path.write_text(json.dumps(prior,ensure_ascii=False,indent=2)+'\n')
    sys.exit(1 if any(r['status']=='BLOCKED' for r in records) else 0)

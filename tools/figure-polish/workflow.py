#!/usr/bin/env python3
"""One-command cached-data figure replay or read-only fresh acceptance.

run: backup -> tests -> native regeneration/idempotence -> native export ->
cached plot rendering/review-pin gate -> thesis build -> fresh acceptance.
verify: tests -> independent fresh render -> PDF/paper audits -> report.
Neither mode runs an algorithm experiment. Verify protects source/publication
assets, raw inputs and the built thesis with before/after SHA-256 manifests.
Exit 2 means unresolved/review/deferred items, never full PASS.
"""
from __future__ import annotations
import argparse,hashlib,json,os,shutil,subprocess,sys
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
RUN=ROOT/'.diagram-governance/runs/20261021_presentation_polish'
os.chdir(ROOT)
os.environ['FONTCONFIG_FILE']=str(ROOT/'config/diagram-governance/fonts.conf')
os.environ['PLAYWRIGHT_BROWSERS_PATH']=str(ROOT/'.diagram-governance/browsers')
native=Path.home()/'.cache/auv-diagram-governance/browsers'
if (native/'chromium_headless_shell-1243/chrome-headless-shell-linux64/chrome-headless-shell').exists():
    os.environ['PLAYWRIGHT_BROWSERS_PATH']=str(native)
os.environ['PYTHONPATH']=':'.join(str(ROOT/p) for p in ['.diagram-governance/plotdeps','.diagram-governance/pdfdeps','.diagram-governance/pydeps','tools','.'])
os.environ['SOURCE_DATE_EPOCH']='1792540800'
P=sys.executable
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text())
def call(name,args,allowed=(0,)):
    print(name,flush=True)
    with (RUN/(name+'.log')).open('w') as log:
        result=subprocess.run(args,stdout=log,stderr=subprocess.STDOUT)
    if result.returncode not in allowed:raise RuntimeError(f'{name}: exit {result.returncode}; see {RUN/name}.log')
def protected():
    paths=set()
    baseline=read(RUN/'baseline_manifest.json')
    paths.update(ROOT/r['path'] for r in baseline)
    for group in read(ROOT/'docs/thesis/figure-polish/inventory.json'):
        for asset in group['assets']:
            p=ROOT/asset;paths.add(p)
            if p.suffix=='.pdf' and p.with_suffix('.png').exists():paths.add(p.with_suffix('.png'))
    for record in read(RUN/'cached_detail_runs.json').values():
        paths.update(Path(p) for p in record.get('input_sha256',{}))
    paths.add(ROOT/'thuthesis/build/auv-thesis/auv-thesis.pdf')
    paths.update((ROOT/'tools/figure-polish').glob('*.py'))
    paths.update(ROOT/'docs/thesis/figure-polish'/name for name in ['POLICY.md','inventory.json','presentation_edits.json','cached_promotions.json','native_visual_review.json','snapshot_visual_review.json','paper_visual_review.json','deferral_decisions.json'])
    paths.update(ROOT/name for name in ['config/diagram-governance/fonts.conf','config/diagram-governance/policy.json','相关附件和参照/DRAWIO_GOVERNANCE.md','tools/figure-polish/requirements.lock'])
    return {p.relative_to(ROOT).as_posix():sha(p) for p in sorted(paths) if p.is_file()}
def tests():
    call('environment',[P,'tools/figure-polish/check_environment.py'])
    call('inspector-tests',[P,'-c',"import mpl_toolkits; mpl_toolkits.__path__ = ['.diagram-governance/plotdeps/mpl_toolkits']+list(mpl_toolkits.__path__); import pytest; raise SystemExit(pytest.main(['-q','tests/test_figure_polish_audit.py']))"])
    code="""import pathlib,sys,fcntl
sys.path.insert(0,'tools/diagram-governance');import governance as g
g.RUN=pathlib.Path('.diagram-governance/runs/20261021_presentation_polish').resolve()
with pathlib.Path('.diagram-governance/render.lock').open('a') as lock:
 fcntl.flock(lock,fcntl.LOCK_EX);sys.exit(g.selftest())
"""
    call('native-selftest',[P,'-c',code])
def sources():
    sys.path.insert(0,str(ROOT/'tools/diagram-governance'))
    import governance as g
    return g.current_paths()+[ROOT/'AUV-Master-Mag/thesis/figures/architecture/_SOURCE.md']
def regenerate():
    files=sources();before={str(p.relative_to(ROOT)):sha(p) for p in files}
    for name,path in [('generate_architecture','docs/thesis/figures/architecture/generate_architecture_diagrams.py'),('generate_methods','AUV-Master-Mag/docs/figure/generate_drawio_method_figures.py'),('sync','docs/thesis/figures/architecture/sync_mag_architecture_copies.py')]:call(name,[P,path])
    after={str(p.relative_to(ROOT)):sha(p) for p in files}
    changed=[p for p in before if before[p]!=after[p]]
    (RUN/'source_idempotence.json').write_text(json.dumps({'before':before,'after':after,'changed':changed,'pass':not changed},ensure_ascii=False,indent=2)+'\n')
    if changed:raise RuntimeError('Native regeneration changed sources; backed up, but new images require inspection: '+str(changed))
def run():
    paths=list(protected())
    call('backup-current',[P,'tools/figure-polish/backup.py',*paths])
    tests();regenerate()
    stems=[str(p.with_suffix('').relative_to(ROOT)) for p in sources() if p.suffix=='.drawio' and 'AUV-Master-Mag/thesis/' not in str(p) and p.stem!='auv_v2_five_layer_functional_architecture']
    call('formal-export',[P,'tools/figure-polish/export_drawio.py',*stems])
    call('five-layer-export',[P,'-c',"import fcntl,pathlib,runpy; lock=pathlib.Path('.diagram-governance/render.lock').open('a'); fcntl.flock(lock,fcntl.LOCK_EX); runpy.run_path('docs/thesis/figures/architecture/export_five_layer_architecture.py',run_name='__main__')"])
    call('cached-detail',[P,'tools/figure-polish/render_cached_details.py'])
    call('promote-cached',[P,'tools/figure-polish/promote_cached.py'])
    call('plot-selected',[P,'tools/figure-polish/render_selected_plots.py','--group','principles','--group','pipelines','--group','r13'],allowed=(0,1))
    for item in read(RUN/'plot_runs.json'):
        assert item['status']!='BLOCKED', item
        assert all('r13_v2_authority_policy_summary_by_scenario_mode.csv' in x for x in item.get('missing_inputs',[])),item
    call('thesis-build',['make','auv-thesis'])
    return verify(already_tested=True)
def verify(already_tested=False):
    before=protected()
    if not already_tested:tests()
    call('check-all-final',['bash','tools/figure-polish/check.sh','--all'],allowed=(0,2))
    call('pdf-audit',[P,'tools/figure-polish/audit_pdf.py'])
    call('baseline-previews',[P,'tools/figure-polish/prepare_baseline.py'])
    call('prepare-review',[P,'tools/figure-polish/prepare_review.py'])
    call('native-crops',[P,'tools/figure-polish/prepare_native_crops.py'])
    call('snapshot-crops',[P,'tools/figure-polish/prepare_snapshot_crops.py'])
    call('paper-audit',[P,'tools/figure-polish/audit_paper.py','--render'])
    after=protected();changed=[p for p in before if after.get(p)!=before[p]]
    (RUN/'readonly_integrity.json').write_text(json.dumps({'protected_files':len(before),'before':before,'after':after,'changed':changed,'pass':not changed},ensure_ascii=False,indent=2)+'\n')
    if changed:raise RuntimeError('Read-only acceptance changed protected files: '+str(changed))
    call('report',[P,'tools/figure-polish/report.py'],allowed=(0,2))
    return 0 if read(RUN/'acceptance.json')['status']=='PASS' else 2
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('mode',choices=['run','verify']);args=parser.parse_args()
    RUN.mkdir(parents=True,exist_ok=True)
    try:
        result=run() if args.mode=='run' else verify()
    except Exception as exc:
        (RUN/'workflow_completion.json').write_text(json.dumps({'mode':args.mode,'completed':False,'error':repr(exc)},ensure_ascii=False,indent=2)+'\n')
        raise
    (RUN/'workflow_completion.json').write_text(json.dumps({'mode':args.mode,'completed':True,'exit_code':result,
        'finished_utc':datetime.now(timezone.utc).isoformat(),'acceptance_status':read(RUN/'acceptance.json')['status'],
        'note':'Exit 2 records deferred/review items; it is not full PASS'},ensure_ascii=False,indent=2)+'\n')
    sys.exit(result)

#!/usr/bin/env python3
"""Local, backed-up thesis presentation pass; no experiment is executed."""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
OLD = ROOT / '.diagram-governance/runs/20261021_presentation_polish'
RUN = ROOT / '.diagram-governance/runs/20261023_compact_thesis'
DOC = ROOT / 'docs/thesis/figure-polish/20261023'
os.chdir(ROOT)
os.environ['FONTCONFIG_FILE'] = str(ROOT/'config/diagram-governance/fonts.conf')
os.environ['PLAYWRIGHT_BROWSERS_PATH'] = str(Path.home()/'.cache/auv-diagram-governance/browsers')
sys.path[:0] = [str(ROOT/p) for p in ['.diagram-governance/plotdeps','.diagram-governance/pdfdeps','.diagram-governance/pydeps','tools','tools/diagram-governance','docs/thesis/figures/architecture']]
os.environ['THESIS_FIGURE_AUDIT_DIR'] = str(RUN/'mpl')
os.environ['PYTHONPATH']=':'.join(str(ROOT/p) for p in ['.diagram-governance/plotdeps','.diagram-governance/pdfdeps','.diagram-governance/pydeps','tools','.'])
os.environ['SOURCE_DATE_EPOCH']='1792684800'

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p): return json.loads(Path(p).read_text())
def write(p,value):
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
def module(path):
    spec=importlib.util.spec_from_file_location(Path(path).stem,ROOT/path)
    m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m)
    return m

def baseline():
    RUN.mkdir(parents=True,exist_ok=True);DOC.mkdir(parents=True,exist_ok=True)
    manifest=RUN/'baseline_manifest.json'
    if manifest.exists():
        print('Existing baseline preserved');return
    paths={x['path'] for x in read(OLD/'baseline_manifest.json')}
    paths.update(str(p.relative_to(ROOT)) for p in (ROOT/'thuthesis/data').glob('auv-*.tex'))
    paths.update(['thuthesis/build/auv-thesis/auv-thesis.pdf','tools/independent/plot_three_phase_helical_field.py','tools/plot_v2_shallow_survey_ros_pvs.py'])
    records=[]
    for rel in sorted(paths):
        p=ROOT/rel
        if not p.is_file():continue
        target=RUN/'backup'/rel;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,target)
        records.append({'path':rel,'sha256':sha(p),'bytes':p.stat().st_size})
    write(manifest,records)
    git={name:subprocess.run(args,capture_output=True,text=True,check=True).stdout for name,args in {
        'head':['git','rev-parse','HEAD'],'root':['git','rev-parse','--show-toplevel'],
        'working_tree':['git','status','--porcelain=v1','--untracked-files=no']}.items()}
    write(RUN/'git_baseline.json',git)
    for name in ['paper_audit.json','acceptance.json']:
        shutil.copy2(OLD/name,RUN/('baseline_'+name))
    (RUN/'mpl').mkdir(exist_ok=True)
    for p in (OLD/'mpl').glob('*.json'):shutil.copy2(p,RUN/'mpl'/p.name)
    print('Backed up',len(records),'current working-tree files')

def samples():
    records=[]
    for x in read(OLD/'acceptance.json')['remaining']:
        p=ROOT/x['asset'];target=DOC/'retained_samples'/p.stem;target.parent.mkdir(parents=True,exist_ok=True)
        subprocess.run(['pdftoppm','-singlefile','-f','1','-r','125','-png',str(p),str(target)],check=True,capture_output=True)
        records.append({'asset':x['asset'],'asset_sha256':sha(p),'preview':str(target.with_suffix('.png').relative_to(ROOT)),
            'preview_sha256':sha(target.with_suffix('.png')),'status':'RETAINED_USER_ACCEPTED',
            'decision':'用户确认原始输入丢失，接受旧图作为不可重绘的保留资产；不侵入修改图片，仅必要时调整论文引用尺寸。',
            'known_limit':x['reason'],'visual_review':'PENDING'})
    write(DOC/'retained_images.json',records)
    print('Sampled',len(records),'retained PDFs without editing them')

def native():
    m=module('tools/figure-polish/check_drawio.py');m.RUN=RUN;m.g.RUN=RUN
    m.EDITS=RUN/'no_semantic_edits.json'
    # Current pass only changes layout: comparison is with its own full backup.
    import fcntl
    with (ROOT/'.diagram-governance/render.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        records=[]
        for p in m.g.current_paths():
            try: records+=m.inspect(p)
            except Exception as e:records.append({'file':str(p.relative_to(ROOT)),'errors':[{'code':'BLOCKED','reason':repr(e)}]})
    write(RUN/'checks_all.json',records)
    assert len(records)==34 and not any(x['errors'] for x in records), 'See checks_all.json'

def candidates():
    m=module('docs/thesis/figures/architecture/generate_architecture_diagrams.py')
    original=m.write;m.THESIS_OUT=RUN/'candidates/docs/thesis/figures/architecture'
    m.write=lambda name,cells,**kw:original(name,cells,**{**kw,'out':m.THESIS_OUT})
    for function in [m.verification_to_deployment_ladder,m.uncertainty_highway,m.behavior_tree_illustration,m.five_layer_functional_architecture]:function()
    rels=['docs/thesis/figures/architecture/'+stem+'.drawio' for stem in [
        'auv_system_verification_deployment_ladder','auv_v2_uncertainty_highway','auv_v2_behavior_tree_illustration','auv_v2_five_layer_functional_architecture']]
    for rel in list(rels):
        if 'behavior_tree' in rel:continue
        other='AUV-Master-Mag/thesis/figures/architecture/'+Path(rel).name
        target=RUN/'candidates'/other;target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(RUN/'candidates'/rel,target);rels.append(other)
    records=[]
    for rel in rels:
        candidate=RUN/'candidates'/rel;backup=RUN/'backup'/candidate.relative_to(ROOT)
        backup.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(RUN/'backup'/rel,backup)
        records.append({'file':rel,'baseline_sha256':sha(RUN/'backup'/rel),'candidate':str(candidate.relative_to(ROOT)),'candidate_sha256':sha(candidate)})
    write(RUN/'native_candidates.json',records)
    m=module('tools/figure-polish/check_drawio.py');m.RUN=RUN;m.g.RUN=RUN;m.EDITS=RUN/'no_semantic_edits.json'
    import fcntl
    checks=[]
    with (ROOT/'.diagram-governance/render.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        for x in records:checks+=m.inspect(ROOT/x['candidate'])
    write(RUN/'checks_candidates.json',checks)
    assert not any(x['errors'] for x in checks),'Candidate geometry failed; formal sources preserved'

def paper():
    m=module('tools/figure-polish/audit_paper.py');m.RUN=RUN;m.main(render=True)

def float_sweep():
    import re
    from collections import Counter
    import pymupdf
    audit=read(RUN/'paper_audit.json');pdf=pymupdf.open(ROOT/audit['pdf'])
    han=lambda s:Counter(re.findall(r'[\u4e00-\u9fff]',s))
    rows=[]
    for pi in sorted({x['physical_page'] for x in audit['placements']}):
        blocks=pdf[pi-1].get_text('blocks')
        body=han(''.join(b[4] for b in blocks if b[1]>85 and b[3]<750 and not re.match(r'^图\s*\d+[.．]\d+',b[4])))
        placements=[x for x in audit['placements'] if x['physical_page']==pi]
        for x in placements:
            if x['asset'].endswith('.pdf'):
                source=pymupdf.open(ROOT/x['asset'])
                body-=han(source[x['source_page']-1].get_text())
        remaining=sum(body.values())
        row={'physical_page':pi,'figures':sorted({x['figure'] for x in placements}),
             'body_han_estimate':remaining,'classification':'FIGURE_ONLY_CANDIDATE' if remaining<30 else 'SPARSE_TEXT' if remaining<100 else 'WITH_BODY',
             'note':'只用于筛选；图形抽字不全、标题/公式分组会影响估计，最终由实际页面查看确认'}
        rows.append(row)
        if remaining<100:print(row)
    write(RUN/'float_sweep.json',rows)

def caption_footer_errors(path):
    """Actual PDF text geometry: captions must remain above the page footer."""
    import re,pymupdf
    errors=[]
    for pi,page in enumerate(pymupdf.open(path)):
        groups=[]
        for block in page.get_text('dict')['blocks']:
            lines=[(''.join(s['text'] for s in line['spans']).strip(),line['bbox']) for line in block.get('lines',[])]
            if lines:groups.append(lines)
        footers=[box for lines in groups for text,box in lines if box[1]>page.rect.height*.88 and re.fullmatch(r'[0-9IVXLCivxlc]+',text)]
        if not footers:continue
        top=min(b[1] for b in footers)
        for lines in groups:
            for i,(text,box) in enumerate(lines):
                if not re.match(r'^(?:图|Figure)\s*\d+[.．]\d+',text):continue
                bottom=max(b[3] for t,b in lines[i:] if not re.fullmatch(r'[0-9IVXLCivxlc]+',t))
                if bottom>top-5:errors.append({'page':pi+1,'code':'CAPTION_IN_FOOTER','caption':text,'caption_bottom_pt':bottom,'footer_top_pt':top})
    return errors

def plot_data(fig):
    import numpy as np
    result=[]
    for ai,ax in enumerate(fig.axes):
        for li,line in enumerate(ax.lines):
            values=line.get_data_3d() if hasattr(line,'get_data_3d') else line.get_data()
            result.append({'axis':ai,'line':li,'arrays':[
                {'shape':list(np.asarray(v).shape),'sha256':hashlib.sha256(np.asarray(v,dtype='float64').tobytes()).hexdigest()} for v in values]})
    return result

def plots():
    import mpl_toolkits
    mpl_toolkits.__path__=[str(ROOT/'.diagram-governance/plotdeps/mpl_toolkits')]+list(mpl_toolkits.__path__)
    import matplotlib.pyplot as plt
    import thesis_plot_style as tps
    candidate=RUN/'plots';candidate.mkdir(exist_ok=True)
    baseline_module=module(RUN/'backup/tools/independent/plot_three_phase_helical_field.py')
    before,old_deviation=baseline_module.make_figure();data_before=plot_data(before);plt.close(before)
    m=module('tools/independent/plot_three_phase_helical_field.py')
    fig,deviation=m.make_figure();data_after=plot_data(fig)
    assert data_before==data_after and old_deviation==deviation
    tps.save_figure(fig,candidate/'three_phase_helical_field');plt.close(fig)
    current=module('tools/plot_v2_shallow_survey_ros_pvs.py')
    old=module(RUN/'backup/tools/plot_v2_shallow_survey_ros_pvs.py')
    old.ROOT=ROOT;old.SOURCE=current.SOURCE;old.FILES=current.FILES.copy()
    inputs={str(p.relative_to(ROOT)):sha(p) for base in current.FILES.values() for p in [base.with_suffix('.csv'),base.with_name(base.name+'_summary.json')]}
    traces={}
    for name,m in [('before',old),('after',current)]:
        m.PUB=candidate/name/'publication';m.THESIS=candidate/name/'thesis'
        (m.PUB/'data').mkdir(parents=True,exist_ok=True)
        def save(fig,base,*,_name=name):
            traces[_name]=plot_data(fig)
            return tps.save_figure(fig,base) if _name=='after' else []
        m.save_figure=save;m.main(allow_historical_source=True)
    assert traces['before']==traces['after']
    assert inputs=={p:sha(ROOT/p) for p in inputs}
    write(RUN/'plot_data_invariance.json',{'pass':True,'helical':data_after,'shallow_survey':traces['after'],'raw_input_sha256':inputs})
    print('Both candidate figures retain every plotted line array and original input hash')

def promote():
    review=read(DOC/'candidate_visual_review.json')
    assert all(x['status']=='VIEWED' and sha(ROOT/x['png'])==x['png_sha256'] for x in review)
    checks=read(RUN/'checks_candidates.json')
    assert len(checks)==9 and not any(x['errors'] for x in checks)
    previous=read(RUN/'promotions.json') if (RUN/'promotions.json').exists() else []
    previous_hashes={x['path']:x['sha256'] for x in previous}
    initial={x['path']:x['sha256'] for x in read(RUN/'baseline_manifest.json')}
    outputs=[]
    def copy(source,target):
        rel=str(target.relative_to(ROOT))
        assert sha(target) in {initial.get(rel),previous_hashes.get(rel)}, 'Concurrent change: '+rel
        shutil.copy2(source,target);outputs.append({'path':rel,'sha256':sha(target),'candidate':str(source.relative_to(ROOT))})
    for x in read(RUN/'native_candidates.json'):
        assert sha(ROOT/x['candidate'])==x['candidate_sha256']
        copy(ROOT/x['candidate'],ROOT/x['file'])
    for stem,source,targets in [
        ('three_phase_helical_field',RUN/'plots/three_phase_helical_field',[ROOT/'docs/thesis/figures/magnetics']),
        ('51_shallow_survey_ros_pvs_chain',RUN/'plots/after/thesis/51_shallow_survey_ros_pvs_chain',
         [ROOT/'docs/thesis/figures/experiments/fwhm_v2',ROOT/'AUV-Master-Mag/docs/v2/publication/fwhm_v2_experiment_results/figures'])]:
        audit=read(RUN/'mpl'/f'{stem}.json')
        assert not any(audit[k] for k in ['collisions','clipped_text','missing_cjk_glyphs'])
        for directory in targets:
            for ext in ['.pdf','.png']:copy(source.with_suffix(ext),directory/(stem+ext))
    import fcntl
    exporter=module('tools/figure-polish/export_drawio.py');exports={}
    with (ROOT/'.diagram-governance/render.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        for stem in ['auv_system_verification_deployment_ladder','auv_v2_uncertainty_highway','auv_v2_behavior_tree_illustration']:
            p=ROOT/'docs/thesis/figures/architecture'/stem
            for ext in ['.pdf','.png','.svg','.drawio.png']:
                target=Path(str(p)+ext);rel=str(target.relative_to(ROOT))
                assert sha(target) in {initial.get(rel),previous_hashes.get(rel)}, 'Concurrent export change: '+rel
            exports[stem]=exporter.export(p)
            outputs.extend(exports[stem]['outputs'])
        five=module('docs/thesis/figures/architecture/export_five_layer_architecture.py')
        source=ROOT/'docs/thesis/figures/architecture'/five.STEM
        for ext in ['.pdf','.png','.svg','.drawio.png']:
            target=Path(str(source)+ext);rel=str(target.relative_to(ROOT))
            assert sha(target) in {initial.get(rel),previous_hashes.get(rel)}, 'Concurrent five-layer change: '+rel
        five.main()
        exports[five.STEM]={'source_sha256':sha(source.with_suffix('.drawio')),'outputs':[
            {'path':str(Path(str(source)+ext).relative_to(ROOT)),'sha256':sha(Path(str(source)+ext))} for ext in ['.pdf','.png','.svg','.drawio.png']]}
        outputs.extend(exports[five.STEM]['outputs'])
    write(RUN/'exports.json',exports);write(RUN/'promotions.json',outputs)
    print('Promoted 7 native sources, 4 formal native exports and 2 reviewed plots')

def prose_audit():
    import re
    allowed={r'\$CKTH',r'\$AUV','0x01','0x02','0x03','0x11','0xEE','192.9.0.X','.50','.100','.60','.101','.200',
             '+Vdc','0Vdc','Trig1','tickGet()','Para3','Para4','0x5453','21/udp'}
    kept=[];findings=[]
    for p in sorted((ROOT/'thuthesis/data').glob('auv-chap*.tex')):
        text=p.read_text()
        for match in re.finditer(r'\\texttt\{([^{}]*)\}',text):
            item={'file':str(p.relative_to(ROOT)),'line':text[:match.start()].count('\n')+1,'text':match[1]}
            (kept if match[1] in allowed else findings).append(item)
        # Only visible body text: source paths in includegraphics are required.
        visible=re.sub(r'\\includegraphics\[[\s\S]*?\]\{[^}]*\}','',text)
        for match in re.finditer(r'[\w./-]+\.(?:py|csv|json|yaml|npz|sh|cpp)\b',visible):
            findings.append({'file':str(p.relative_to(ROOT)),'text':match[0],'reason':'Visible implementation filename'})
    write(DOC/'prose_audit.json',{'status':'PASS' if not findings else 'NEEDS_REVIEW','findings':findings,
        'intentional_protocol_hardware_identifiers':kept,
        'limit':'检查可见文件名及等宽实现标识；数学变量、物理符号、协议帧及硬件字段保留，不自动改写研究内容。'})
    print('Prose audit:',len(findings),'unexplained identifiers;',len(kept),'intentional protocol/hardware identifiers')
    assert not findings

def idempotence():
    import governance as g
    paths=g.current_paths()+[ROOT/'AUV-Master-Mag/thesis/figures/architecture/_SOURCE.md']
    before={str(p.relative_to(ROOT)):sha(p) for p in paths}
    for name in ['generate_architecture_diagrams.py','sync_mag_architecture_copies.py']:
        subprocess.run([sys.executable,'docs/thesis/figures/architecture/'+name],check=True,capture_output=True)
    after={str(p.relative_to(ROOT)):sha(p) for p in paths};changed=[p for p in before if before[p]!=after[p]]
    write(RUN/'idempotence.json',{'files':len(paths),'before':before,'after':after,'changed':changed,'pass':not changed})
    assert not changed,changed
    print('33 native/sync files regenerate without changes')

def protected():
    paths={ROOT/x['path'] for x in read(RUN/'baseline_manifest.json')}
    paths.update((ROOT/'tools/figure-polish').glob('*.py'))
    paths.update(DOC/name for name in ['candidate_visual_review.json','retained_images.json','prose_edits.json','float_placement.json','final_visual_review.json'] if (DOC/name).exists())
    if (RUN/'plot_data_invariance.json').exists():paths.update(ROOT/p for p in read(RUN/'plot_data_invariance.json')['raw_input_sha256'])
    return {str(p.relative_to(ROOT)):sha(p) for p in sorted(paths) if p.is_file()}

def tests():
    import mpl_toolkits
    mpl_toolkits.__path__=[str(ROOT/'.diagram-governance/plotdeps/mpl_toolkits')]+list(mpl_toolkits.__path__)
    # This imports the version/font doctor without changing any package.
    module('tools/figure-polish/check_environment.py')
    with (RUN/'inspector-tests.log').open('w') as log:
        code="import mpl_toolkits; mpl_toolkits.__path__=['.diagram-governance/plotdeps/mpl_toolkits']+list(mpl_toolkits.__path__); import pytest; raise SystemExit(pytest.main(['-q','tests/test_figure_polish_audit.py']))"
        subprocess.run([sys.executable,'-c',code],check=True,stdout=log,stderr=subprocess.STDOUT)
    import governance as g,fcntl
    g.RUN=RUN
    with (ROOT/'.diagram-governance/render.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        assert g.selftest()==0
    import pymupdf
    fixtures=RUN/'paper-fixtures';fixtures.mkdir(exist_ok=True)
    for bad in [False,True]:
        pdf=pymupdf.open();p=pdf.new_page(width=595,height=842)
        p.insert_text((290,780),'1',fontsize=10)
        p.insert_text((85,790 if bad else 700),'Figure 2.1 Caption',fontsize=10)
        target=fixtures/('bad.pdf' if bad else 'legal.pdf');pdf.save(target)
        assert bool(caption_footer_errors(target))==bad
    real=RUN/'iterations/footer_overflow_before_fix.pdf'
    assert any(x['page']==65 for x in caption_footer_errors(real)), 'Must catch the actual failed thesis page'
    write(RUN/'paper-fixtures/result.json',{'status':'PASS','cases':3,'bad_case_errors':caption_footer_errors(fixtures/'bad.pdf'),
        'actual_regression':caption_footer_errors(real)})
    print('17 native, 10 Matplotlib and 3 actual-PDF boundary cases passed')

def verify():
    before=protected();tests();native();paper();float_sweep();prose_audit()
    errors=caption_footer_errors(ROOT/'thuthesis/build/auv-thesis/auv-thesis.pdf')
    write(RUN/'paper_boundary_audit.json',{'status':'FAIL' if errors else 'PASS','errors':errors})
    assert not errors,errors
    audit=module('tools/figure-polish/audit_pdf.py')
    paths={x['asset'] for x in read(RUN/'paper_audit.json')['placements'] if x['asset'].endswith('.pdf')}
    for folder in ['docs/thesis/figures/architecture','docs/internals/figures/architecture','AUV-Master-Mag/docs/figure']:
        paths.update(str(p.with_suffix('.pdf').relative_to(ROOT)) for p in (ROOT/folder).glob('*.drawio') if p.with_suffix('.pdf').exists())
    fonts=[audit.audit(ROOT/p) for p in sorted(paths)];write(RUN/'pdf_audit.json',fonts)
    retained={x['asset'] for x in read(DOC/'retained_images.json')}
    assert not any(x['embedding_warning'] or x['unexpected_sans_cjk'] for x in fonts if x['path'] not in retained)
    assert all(sha(ROOT/x['asset'])==x['asset_sha256'] for x in read(DOC/'retained_images.json'))
    idem=read(RUN/'idempotence.json');assert idem['pass'] and all(sha(ROOT/p)==v for p,v in idem['after'].items())
    after=protected();changed=[p for p in before if before[p]!=after.get(p)]
    write(RUN/'readonly_integrity.json',{'protected_files':len(before),'before':before,'after':after,'changed':changed,'pass':not changed})
    assert not changed,changed
    write(RUN/'verification_completion.json',{'completed':True,'measurements':'PASS','visual_review':'Requires current hash-bound final_visual_review.json',
        'native_pages':34,'pdf_audits':len(fonts),'protected_files':len(before),'retained_assets':11})
    print('Read-only verification measurements complete; actual views remain a separate gate')
    result=subprocess.run([sys.executable,'tools/figure-polish/report_20261023.py'])
    if result.returncode:raise SystemExit(result.returncode)

def run():
    baseline();candidates();plots();promote();idempotence()
    subprocess.run(['make','auv-thesis'],check=True)
    verify()

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('mode',choices=['baseline','samples','candidates','native','plots','promote','prose_audit','paper','float_sweep','idempotence','verify','run']);a=parser.parse_args()
    try:
        globals()[a.mode]()
    except SystemExit as e:
        if a.mode in ['run','verify']:
            write(RUN/'workflow_completion.json',{'mode':a.mode,'completed':e.code in [0,2],'exit_code':e.code,
                'status':'NEEDS_REVIEW' if e.code else 'COMPLETE_WITH_RETAINED_ASSETS'})
        raise
    except Exception as e:
        if a.mode in ['run','verify']:write(RUN/'workflow_completion.json',{'mode':a.mode,'completed':False,'error':repr(e)})
        raise
    else:
        if a.mode in ['run','verify']:write(RUN/'workflow_completion.json',{'mode':a.mode,'completed':True,'exit_code':0,'status':'COMPLETE_WITH_RETAINED_ASSETS'})

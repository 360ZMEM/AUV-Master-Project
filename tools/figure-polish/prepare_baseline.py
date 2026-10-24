#!/usr/bin/env python3
"""Render missing baseline previews from backed-up native sources.

Some original publication PNG/PDF files are Git LFS pointer text. Their original
pointer bytes stay backed up. These previews are explicitly baseline-source
re-renders in the locked font environment, not the missing historical bitmap.
"""
import fcntl,hashlib,json,os,subprocess
from pathlib import Path
from PIL import Image
ROOT=Path(__file__).resolve().parents[2]
RUN=ROOT/'.diagram-governance/runs/20261021_presentation_polish'
os.environ['FONTCONFIG_FILE']=str(ROOT/'config/diagram-governance/fonts.conf')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
records=[]
with (ROOT/'.diagram-governance/render.lock').open('a') as lock:
    fcntl.flock(lock,fcntl.LOCK_EX)
    for source in sorted((RUN/'backup').rglob('*.drawio')):
        rel=source.relative_to(RUN/'backup')
        if str(rel).startswith('AUV-Master-Mag/thesis/'):continue
        png=source.with_suffix('.png')
        try:
            with Image.open(png) as im:im.load()
            continue
        except (OSError,FileNotFoundError):pass
        out=RUN/'baseline-rerender'/rel.with_suffix('.png');out.parent.mkdir(parents=True,exist_ok=True)
        command=['drawio','--export','--page-index','0','--scale','2','--format','png','--output',str(out),str(source)]
        subprocess.run(command,check=True,capture_output=True,timeout=60)
        records.append({'native_source':str(rel),'baseline_native_sha256':sha(source),'preview':str(out.relative_to(ROOT)),
            'preview_sha256':sha(out),'command':command,'provenance':'BASELINE_NATIVE_RERENDER; original published PNG unavailable/LFS pointer; not claimed historical bitmap'})
(RUN/'baseline_rerender.json').write_text(json.dumps(records,ensure_ascii=False,indent=2)+'\n')
print('Baseline native re-renders',len(records))

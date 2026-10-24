#!/usr/bin/env python3
"""Append-only baseline backup; never replace a captured working-tree file."""
import hashlib,json,shutil,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
RUN=ROOT/'.diagram-governance/runs/20261021_presentation_polish'
manifest=RUN/'baseline_manifest.json'
data=json.loads(manifest.read_text());known={r['path'] for r in data}
for arg in sys.argv[1:]:
    p=(ROOT/arg).resolve();rel=p.relative_to(ROOT).as_posix()
    if rel in known:continue
    out=RUN/'backup'/rel
    if out.exists():raise RuntimeError('unlisted backup already exists: '+rel)
    out.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,out)
    data.append({'path':rel,'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()});known.add(rel)
manifest.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
print('baseline files',len(data))

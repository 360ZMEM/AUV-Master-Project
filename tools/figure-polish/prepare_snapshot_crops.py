#!/usr/bin/env python3
"""Prepare each snapshot's own high-risk crop, checking canonical identity."""
import hashlib,json
from pathlib import Path
from PIL import Image
ROOT=Path(__file__).resolve().parents[2]
RUN=ROOT/'.diagram-governance/runs/20261021_presentation_polish'
checks=json.loads((RUN/'checks_all.json').read_text())
canonical=json.loads((RUN/'native_crop_inventory.json').read_text())
records=[]
for r in checks:
    if not r['file'].startswith('AUV-Master-Mag/thesis/'):continue
    reference=next(c for c in canonical if Path(c['file']).name==Path(r['file']).name and c['page']==r['page_index'])
    cell=r['measured']['cells'][reference['cell_id']];rect=cell['shape'];view=r['measured']['svg']
    with Image.open(ROOT/r['png']) as im:
        sx,sy=im.width/view['w'],im.height/view['h'];pad=45
        box=(max(0,(rect['x']-pad)*sx),max(0,(rect['y']-pad)*sy),min(im.width,(rect['right']+pad)*sx),min(im.height,(rect['bottom']+pad)*sy))
        target=RUN/'snapshot-crops'/f"{Path(r['file']).stem}_p{r['page_index']}.png"
        target.parent.mkdir(exist_ok=True);im.crop(tuple(map(round,box))).save(target)
    digest=hashlib.sha256(target.read_bytes()).hexdigest()
    assert digest==reference['crop_sha256'],'Snapshot crop differs from reviewed canonical crop'
    records.append({'file':r['file'],'page':r['page_index'],'source_sha256':r['source_sha256'],'crop':str(target.relative_to(ROOT)),
                    'crop_sha256':digest,'canonical':reference['file'],'visual_review':'PENDING'})
(RUN/'snapshot_crop_inventory.json').write_text(json.dumps(records,ensure_ascii=False,indent=2)+'\n')
print('Prepared',len(records),'snapshot page crops; all byte-identical to canonical crops')

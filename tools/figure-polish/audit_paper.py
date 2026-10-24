#!/usr/bin/env python3
"""Read actual XeTeX Form/Image placements; prepare final-page review evidence.

The form sequence is checked against every source page's exact dimensions.
Raster ImN and vector FmN share XeTeX's graphic inclusion sequence. No printed
page offset or guessed includegraphics width is used.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'.diagram-governance/pdfdeps'))
import pymupdf
RUN=ROOT/'.diagram-governance/runs/20261021_presentation_polish'
PDF=ROOT/'thuthesis/build/auv-thesis/auv-thesis.pdf'
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()

def main(render=False, *, asset_root=None):
    inv=json.loads((ROOT/'docs/thesis/figure-polish/inventory.json').read_text())
    doc=pymupdf.open(PDF); forms={}; images={}
    for pi,page in enumerate(doc):
        for form in page.get_xobjects():
            if form[2]==0: forms[int(form[1][2:])]=(pi,form)
        for pic in page.get_images(full=True):
            if re.fullmatch(r'Im\d+',pic[7]): images[int(pic[7][2:])]=(pi,pic)
    placements=[];n=0;used=set();source_pages={}
    for group in inv:
        for asset in group['assets']:
            source=(asset_root or ROOT)/asset; record={'figure':group['number'],'asset':asset,'source_sha256':sha(source),'inclusion_index':n}
            if source.suffix=='.pdf':
                source_doc=pymupdf.open(source)
                si=source_pages.get(asset,0) if len(source_doc)>1 else 0
                source_pages[asset]=si+1
                sp=source_doc[si];pi,form=forms[n];p=doc[pi]
                rect=pymupdf.Rect(form[3])
                assert abs(rect.width-sp.rect.width)<.03 and abs(rect.height-sp.rect.height)<.03, f'Inclusion order mismatch: {asset}'
                content=p.read_contents().decode('latin1')
                pattern=r'q\s+([.\d]+) 0 0 ([.\d]+) [-.\d]+ [-.\d]+ cm q 1 0 0 1 [-.\d]+ [-.\d]+ cm /'+re.escape(form[1])+r' Do'
                match=re.search(pattern,content)
                if match:
                    scale=float(match[1]);assert abs(scale-float(match[2]))<.0001
                else:
                    assert re.search(r'q 1 0 0 1 [-.\d]+ [-.\d]+ cm /'+re.escape(form[1])+r' Do',content),f'Unrecognized transform: {form}'
                    scale=1.
                spans=[s for b in sp.get_text('dict')['blocks'] for line in b.get('lines',[]) for s in line['spans'] if s['text'].strip()]
                minimum=min((s['size'] for s in spans),default=None)
                record.update(source_page=si+1,form=form[1],actual_scale=scale,
                    width_mm=rect.width*scale*25.4/72,height_mm=rect.height*scale*25.4/72,
                    extracted_text_min_final_pt=None if minimum is None else minimum*scale,
                    extracted_text_note='Extracted glyph subset only; Type3 Chinese outlines and formulas are not a complete font measurement')
                audit=RUN/'mpl'/(source.stem+'.json')
                if audit.exists():
                    measured=json.loads(audit.read_text())
                    minimum=min((x['font_size_pt'] for x in measured['labels']),default=None)
                    record['renderer_label_base_min_final_pt']=minimum*scale if minimum is not None else None
                    record['renderer_font_note']='Actual Agg label base sizes × actual PDF insertion scale; formula subscripts can be smaller'
                    record['renderer_audit_sha256']=sha(audit)
            else:
                pi,pic=images[n];rects=doc[pi].get_image_rects(pic[0]);assert len(rects)==1
                rect=rects[0];record.update(width_mm=rect.width*25.4/72,height_mm=rect.height*25.4/72,
                    native_pixels=[pic[2],pic[3]],image=pic[7],text_measurement='Original photo/report/screenshot, no editable font model')
            record.update(physical_page=pi+1,printed_page=doc[pi].get_label(),visual_review='PENDING')
            placements.append(record);used.add(pi+1);n+=1
    assert len(forms)==sum(x['asset'].endswith('.pdf') for x in placements)
    out=RUN/'paper-images';out.mkdir(exist_ok=True)
    previews=[]
    for pi in sorted(used):
        png=out/f'page_{pi:03}.png'
        if render:
            subprocess.run(['pdftoppm','-f',str(pi),'-l',str(pi),'-singlefile','-r','110','-png',str(PDF),str(png.with_suffix(''))],check=True,capture_output=True)
        previews.append({'physical_page':pi,'preview':png.relative_to(ROOT).as_posix(),
                         'sha256':sha(png) if png.exists() else None,'review':'PENDING'})
    record={'pdf':PDF.relative_to(ROOT).as_posix(),'pdf_sha256':sha(PDF),'pages':len(doc),
        'method':'Actual XeTeX FmN/ImN inclusion, exact source page dimensions and uniform Form matrix; raster actual image rectangle',
        'font_policy':'9 pt advisory per user; glyph clipping/overlap remains mandatory',
        'placements':placements,'page_previews':previews}
    (RUN/'paper_audit.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n')
    print(f'{len(placements)} actual placements, {len(used)} physical pages, {len(doc)} PDF pages')
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--render',action='store_true');a=p.parse_args();main(a.render)

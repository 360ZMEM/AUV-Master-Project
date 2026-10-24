#!/usr/bin/env python3
"""Prepare raster previews; preparation is never recorded as a visual review."""
import hashlib
import json
import subprocess
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / '.diagram-governance/pdfdeps'))
import pymupdf
RUN = ROOT / '.diagram-governance/runs/20261021_presentation_polish'

def main():
    inv = json.loads((ROOT / 'docs/thesis/figure-polish/inventory.json').read_text())
    assets = sorted({a for group in inv for a in group['assets']})
    records = []
    for asset in assets:
        p = ROOT / asset
        digest = hashlib.sha256(p.read_bytes()).hexdigest()
        if p.suffix != '.pdf':
            records.append({'asset':asset, 'sha256':digest, 'preview':asset, 'review':'PENDING'})
            continue
        doc = pymupdf.open(p)
        for page in doc:
            out = RUN / 'pdf-images' / f'{p.stem}_p{page.number+1}.png'
            out.parent.mkdir(parents=True, exist_ok=True)
            # Poppler is the primary thesis preview renderer. A separate
            # MuPDF comparison catches CFF/TrueType embedding mismatches.
            subprocess.run(["pdftoppm", "-f", str(page.number+1), "-l", str(page.number+1),
                            "-singlefile", "-r", "144", "-png", str(p), str(out.with_suffix(""))],
                           check=True, capture_output=True, timeout=60)
            records.append({'asset':asset,'page':page.number+1,'sha256':digest,
                            'preview':out.relative_to(ROOT).as_posix(),'review':'PENDING'})
    (RUN/'review_inventory.json').write_text(json.dumps(records,ensure_ascii=False,indent=2)+'\n')
    print('prepared',len(records),'page/images; no automatic visual PASS')
if __name__ == '__main__': main()

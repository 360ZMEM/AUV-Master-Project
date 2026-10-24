#!/usr/bin/env python3
"""Audit all actual thesis figure PDFs without changing their sources."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / ".diagram-governance/pdfdeps"))
import pymupdf


def audit(path: Path) -> dict:
    font_process = subprocess.run(["pdffonts", str(path)], capture_output=True, text=True, check=True)
    fonts = font_process.stdout
    doc = pymupdf.open(path)
    pages = []
    visible_fonts = set()
    for page in doc:
        visible_fonts.update(s['font'] for s in page.get_texttrace() if s['opacity'] > 0 and s['type'] != 3)
        lines = []
        for block_index, block in enumerate(page.get_text("dict")["blocks"]):
            for line in block.get("lines", []):
                text = "".join(s["text"] for s in line["spans"]).strip()
                if text:
                    lines.append({"text": text, "bbox": line["bbox"], "block": block_index,
                                  "direction": line["dir"], "fonts": sorted({s['font'] for s in line['spans']})})
        collisions = []
        for i, left in enumerate(lines):
            for right in lines[i + 1:]:
                a, b = pymupdf.Rect(left["bbox"]), pymupdf.Rect(right["bbox"])
                inter = a & b
                if inter.width > .75 and inter.height > .75:
                    collisions.append({"left": left, "right": right, "intersection_pt": list(inter)})
        pages.append({"page": page.number + 1, "lines": lines, "text_text_candidates": collisions})
    return {"path": path.relative_to(ROOT).as_posix(), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "pdffonts": fonts, "font_warnings": font_process.stderr,
            "embedding_warning": "Mismatch between font type and embedded font file" in font_process.stderr,
            "visible_fonts": sorted(visible_fonts),
            "unexpected_sans_cjk": any(re.search(r"WenQuan|ZenHei|NotoSansCJK|SimHei", f, re.I) for f in visible_fonts),
            "pages": pages, "limitations": "PDF text boxes are candidates, not glyph ink. Formula overlaps require review; data/mesh occlusion needs source-renderer and actual image review."}


def main():
    inventory = json.loads((ROOT / "docs/thesis/figure-polish/inventory.json").read_text())
    outputs = {asset for group in inventory for asset in group["assets"] if asset.endswith(".pdf")}
    # Include native architecture/method exports that are maintained but not
    # directly inserted in the current auv-thesis. Snapshots have native only.
    for directory in ['docs/thesis/figures/architecture','docs/internals/figures/architecture','AUV-Master-Mag/docs/figure']:
        for native in (ROOT/directory).glob('*.drawio'):
            pdf=native.with_suffix('.pdf')
            if pdf.is_file():outputs.add(pdf.relative_to(ROOT).as_posix())
    outputs=sorted(outputs)
    records = [audit(ROOT / p) for p in outputs]
    out = ROOT / ".diagram-governance/runs/20261021_presentation_polish/pdf_audit.json"
    out.write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n")
    for rec in records:
        hits = sum(len(p["text_text_candidates"]) for p in rec["pages"])
        print(Path(rec["path"]).stem, "text-pairs", hits, "sans-CJK", rec["unexpected_sans_cjk"], "embedding-warning", rec["embedding_warning"])


if __name__ == "__main__":
    main()

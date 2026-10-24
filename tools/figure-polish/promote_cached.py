#!/usr/bin/env python3
"""Promote only pinned, actually reviewed cached-input plot candidates.

No raw result bundle is an output. Existing working-tree destinations and any
affected publication manifests enter the append-only baseline before writing.
"""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
RUN = ROOT / '.diagram-governance/runs/20261021_presentation_polish'
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p): return json.loads(p.read_text())

def main():
    rules = read(ROOT / 'docs/thesis/figure-polish/cached_promotions.json')
    inputs = read(RUN / 'cached_detail_runs.json')
    pairs = []
    for rule in rules:
        stem = ROOT / rule['candidate']
        assert sha(stem.with_suffix('.png')) == rule['reviewed_png_sha256'], f'New image requires review: {stem}'
        report = read(RUN / 'mpl' / (stem.name + '.json'))
        assert not any(report[k] for k in ['collisions', 'clipped_text', 'missing_cjk_glyphs']), stem
        for path, digest in inputs[rule['input_group']]['input_sha256'].items():
            assert sha(Path(path)) == digest, f'Archived input changed: {path}'
        for target in rule['targets']:
            assert not target.startswith(('results/', 'patent/', 'AUV-Master-Mag/results/')), 'Frozen result output prohibited'
            for ext in ['.pdf', '.png']:
                pairs.append((stem.with_suffix(ext), (ROOT / target).with_suffix(ext)))
    pub = ROOT / 'AUV-Master-Mag/docs/v2/publication/fwhm_v2_experiment_results'
    manifests = [pub / n for n in ['publication_manifest.json', 'inspection_publication_manifest.json']]
    # Backup is a prerequisite, not a best-effort action after overwriting.
    existing = [p for _, p in pairs if p.exists()] + manifests
    subprocess.run([sys.executable, str(ROOT / 'tools/figure-polish/backup.py'),
                    *[str(p.relative_to(ROOT)) for p in existing]], check=True)
    path = RUN / 'promotions.json'
    records = read(path) if path.exists() else []
    by_target = {r['target']: r for r in records}
    for source, target in pairs:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        rel = target.relative_to(ROOT).as_posix()
        by_target[rel] = {'source': source.relative_to(ROOT).as_posix(), 'target': rel,
                          'sha256': sha(target), 'visual_review': 'PINNED_PNG_ACTUALLY_OPENED',
                          'input_sha256': inputs[next(r['input_group'] for r in rules if str(source.with_suffix('')) == str(ROOT/r['candidate']))]['input_sha256']}
    changed = {p.resolve() for _, p in pairs}
    def refresh(value):
        if isinstance(value, dict):
            if isinstance(value.get('path'), str) and 'sha256' in value:
                for base in [ROOT, pub]:
                    p = (base / value['path']).resolve()
                    if p in changed: value['sha256'] = sha(p)
            for child in value.values(): refresh(child)
        elif isinstance(value, list):
            for child in value: refresh(child)
    for manifest in manifests:
        data = read(manifest); refresh(data)
        manifest.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
    publication_records=[r for r in rules if any(t.startswith(str(pub.relative_to(ROOT))) for t in r['targets'])]
    supplement={'scope':'2026-10-22 presentation-only replay of current thesis-linked publication figures; historical experiments unchanged',
                'style_sha256':sha(ROOT/'tools/thesis_plot_style.py'),
                'adapter_sha256':sha(ROOT/'tools/figure-polish/render_cached_details.py'),
                'font':'FandolSong; Type3 vector outlines, Chinese PDF text extraction incomplete',
                'figures':[]}
    for rule in publication_records:
        target=next(t for t in rule['targets'] if t.startswith(str(pub.relative_to(ROOT))))
        supplement['figures'].append({'stem':Path(target).name,'input_sha256':inputs[rule['input_group']]['input_sha256'],
            'outputs':{ext:sha((ROOT/target).with_suffix('.'+ext)) for ext in ['pdf','png']},
            'change':'Font embedding / legend placement / spacing only; numerical inputs and interpretation unchanged'})
    (pub/'presentation_polish_manifest.json').write_text(json.dumps(supplement,ensure_ascii=False,indent=2)+'\n')
    path.write_text(json.dumps(list(by_target.values()), ensure_ascii=False, indent=2) + '\n')
    print(f'Promoted {len(pairs)} reviewed assets; archived inputs unchanged')

if __name__ == '__main__': main()

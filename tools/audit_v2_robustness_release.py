#!/usr/bin/env python3
"""Audit the final defense release without changing frozen experiment evidence."""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
RESULT = ROOT / 'AUV-Master-Mag/results/v2/defense_robustness_20260929'
PPT = ROOT / 'PPT制作'


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def read(path: Path):
    return json.loads(path.read_text())


def main() -> None:
    errors = []
    checked = {}

    def verify(path, expected, category):
        p = Path(path)
        if not p.is_absolute():
            p = ROOT / p
        ok = p.is_file() and sha(p) == expected
        checked[category] = checked.get(category, 0) + 1
        if not ok:
            errors.append({'category': category, 'path': str(p), 'reason': 'missing or hash mismatch'})

    old = read(PPT / 'assets/thesis_diff_20260929/asset_manifest.json')
    verify('thuthesis/backups/20260929_before_robustness_169p/auv-thesis.pdf',
           old['current_pdf']['sha256'], 'frozen_169_pdf')
    for key in ['full_pdf', 'source_backup', 'pptx_reference']:
        verify(old[key]['path'], old[key]['sha256'], key)
    for item in old['publication_figures']:
        for ext in ['png', 'pdf']:
            if item.get(ext):
                verify(item[ext], item[f'{ext}_sha256'], 'old_publication_figures')
    for key in ['original_record_assets', 'chapter_5_complete_graphic_assets']:
        for item in old[key]:
            verify(item['path'], item['sha256'], key)
    for item in old['original_record_backups']:
        verify(item['file'], item['sha256'], 'old_record_snapshots')
    for item in old['pdf_previews']:
        for side in ['old', 'new']:
            verify(item[f'{side}_preview'], item[f'{side}_preview_sha256'], 'old_pdf_previews')
    for item in [*old['patches'].values(), old['record_update_patch']]:
        verify(item['path'], item['sha256'], 'old_patches')
    snapshots = PPT / 'assets/robustness_20260929/records_before_sync'
    for name, digest in read(snapshots / 'manifest.json').items():
        verify(snapshots / name, digest, 'pre_update_record_snapshots')
    verify(snapshots / Path(old['ledger']['path']).name,
           old['ledger']['sha256'], 'historical_ledger_snapshot')
    bdir = ROOT / 'thuthesis/backups/20260929_before_robustness_169p'
    for name, digest in read(bdir / 'manifest.json').items():
        verify(bdir / name, digest, 'pre_update_thesis_backup')
    verify('thuthesis/data/auv-appendix-a.tex',
           read(bdir / 'manifest.json')['data/auv-appendix-a.tex'], 'appendix_unchanged')
    full_backup = read(ROOT / 'thuthesis/backups/20260928_full_236p/manifest.json')
    for path, digest in full_backup['source_files'].items():
        if (re.search(r'thuthesis/data/auv-chap0[1-4]\.tex$', path)
                or path.startswith('thuthesis/ref/')
                or path in ('thuthesis/thuthesis.cls', 'thuthesis/thuthesis.cfg', 'thuthesis/auv-thesis.tex')):
            verify(path, digest, 'earlier_chapters_template_references_unchanged')

    plans = []
    raw_counts = {}
    for directory in ['05_held_out', '06_reference_free_ablation', '07_direction_only_ablation']:
        run = RESULT / directory
        plan, manifest = read(run / 'plan.json'), read(run / 'manifest.json')
        plans.append(plan)
        verify(run / 'plan.json', manifest['plan_sha256'], 'final_plans')
        if not manifest['sources_unchanged'] or not plan['frozen_before_execution']:
            errors.append({'path': directory, 'reason': 'plan/source freeze invalid'})
        for path, digest in manifest['artifacts'].items():
            verify(run / path, digest, 'final_raw_artifacts')
        for path, digest in plan['sources'].items():
            verify(path, digest, 'current_runtime_inputs')
        for item in read(run / 'source_snapshot_index.json').values():
            verify(run / item['snapshot'], item['sha256'], 'frozen_runtime_inputs')
        raw_counts[directory] = len(list(run.glob('*.csv')))
    if not (plans[0]['sources'] == plans[1]['sources'] == plans[2]['sources']):
        errors.append({'reason': 'final source versions differ'})
    audits = {}
    for name, run in [('audit_held_out_05.json', '05_held_out'),
                      ('audit_ablation_06.json', '06_reference_free_ablation'),
                      ('audit_ablation_07.json', '07_direction_only_ablation')]:
        audit = read(RESULT / name)
        if not audit['evidence_integrity_passed'] or audit['errors']:
            errors.append({'path': name, 'reason': 'independent CSV audit failed'})
        verify(RESULT / run / 'plan.json', audit['plan_sha256'], 'audit_plan_bindings')
        verify(RESULT / run / 'manifest.json', audit['manifest_sha256'], 'audit_manifest_bindings')
        audits[name] = audit['counts']
    completion = read(RESULT / 'finite_grid_completion.json')
    if not completion['finite_grid_expectations_passed']:
        errors.append({'reason': 'finite-grid expectations failed'})

    font_evidence = {}
    assets = {}
    for name in ['figure_manifest.json', 'matrix_figure_manifest.json', 'thesis_figure_manifest.json']:
        manifest = read(RESULT / 'figures' / name)
        for path, digest in manifest['assets'].items():
            verify(RESULT / 'figures' / path, digest, 'new_figures')
            assets[path] = digest
            if path.endswith('.pdf'):
                text = subprocess.check_output(['pdffonts', str(RESULT / 'figures' / path)], text=True)
                font_evidence[path] = text
                if not re.search(r'FandolSong.*yes\s+yes\s+yes', text):
                    errors.append({'path': path, 'reason': 'embedded Song font missing'})
    for item in read(PPT / 'assets/robustness_20260929/figure_assets.json').values():
        verify(item['source'], item['sha256'], 'ppt_figure_sources')
        verify(item['copy'], item['sha256'], 'ppt_figure_copies')
    verify('docs/thesis/figures/experiments/fwhm_v2/77_defense_robustness_thesis_summary.pdf',
           assets['77_defense_robustness_thesis_summary.pdf'], 'thesis_figure_copy')
    sync = read(RESULT / 'thesis_source_sync.json')
    verify(sync['current_pdf']['path'], sync['current_pdf']['sha256'], 'current_thesis_pdf')
    pages = int(re.search(r'^Pages:\s+(\d+)', subprocess.check_output(
        ['pdfinfo', str(ROOT / sync['current_pdf']['path'])], text=True), re.M)[1])
    if pages != 170:
        errors.append({'reason': 'thesis page budget failed', 'pages': pages})
    for path, change in sync['changes'].items():
        verify(path, change['after_sha256'], 'current_thesis_sources')
    verify(sync['patch_validation']['path'], sync['patch_validation']['sha256'], 'new_thesis_patch')
    log = (ROOT / 'thuthesis/auv-thesis.log').read_text(errors='replace')
    if re.search(r'Overfull|There were undefined|(?:Reference|Citation).*undefined', log):
        errors.append({'reason': 'LaTeX overflow or unresolved reference'})
    for item in sync['key_figures'].values():
        n = str(item['pdf_page'])
        text = subprocess.check_output(['pdftotext', '-f', n, '-l', n, '-layout',
                                        str(ROOT / sync['current_pdf']['path']), '-'], text=True)
        if not re.search(r'图\s*' + re.escape(item['figure']) + r'\s', text):
            errors.append({'reason': 'figure/PDF page mismatch', 'figure': item})
    test = read(RESULT / 'verification/tests.json')
    verify(RESULT / 'verification/v2_tests_105.log', test['log_sha256'], 'tests_log')
    if not test['result'].startswith('105 passed'):
        errors.append({'reason': 'test count/result mismatch'})

    docs = [RESULT / 'README.md', PPT / 'README.md',
            PPT / '03new_扰流导航多源稳健性与答辩资产同步_20260929.md',
            PPT / '谢冠文_硕士毕设临时中期汇报_V4.4新增内容同步建议_20260925.md',
            PPT / 'FWHM_v2_PPT同步与答辩建议_20260925.md',
            PPT / '02new_论文169与236页差分_答辩资产总账_20260929.md',
            PPT / '01new_系统变更与当前巡检答辩资产同步_20260929.md',
            PPT / 'V4.4逐页7分钟讲稿.md',
            ROOT / 'AUV-Master-Mag/docs/v2/DEFENSE_ROBUSTNESS_BOUNDARIES_20260929.md',
            ROOT / 'AUV-Master-Mag/docs/v2/README.md',
            ROOT / 'AUV-Master-Mag/docs/v2/publication/fwhm_v2_experiment_results/README.md',
            ROOT / '毕业设计写作文档/潜在待完成事项/33_扰流导航多源边界与答辩稳健性目标_20260929.md',
            ROOT / '毕业设计写作文档/核心中间进度同步/01new_扰流导航多源条件性稳健性收口_20260929.md']
    link_counts = {}
    for doc in docs:
        count = 0
        for match in re.finditer(r'!?\[[^\]\n]*\]\(([^)\n]+)\)', doc.read_text()):
            target = match[1].strip()
            if target.startswith('<'):
                target = target[1:target.index('>')]
            if urlsplit(target).scheme or target.startswith('#'):
                continue
            target = unquote(target.split('#')[0])
            count += 1
            if not (doc.parent / target).exists():
                errors.append({'path': str(doc.relative_to(ROOT)), 'reason': 'broken relative link', 'target': target})
        link_counts[str(doc.relative_to(ROOT))] = count

    payload = {'schema_version': 1, 'release_integrity_passed': not errors, 'errors': errors,
               'verified_hash_counts': checked, 'final_runs': raw_counts,
               'independent_csv_audits': audits, 'finite_grid_completion': completion,
               'fonts': font_evidence, 'thesis': sync['current_pdf'],
               'figure_pages': sync['key_figures'], 'markdown_relative_links': link_counts,
               'tests': test, 'visual_review': 'six final figures and PDF pages 138–140 inspected; legends clear of key curves',
               'scope': 'finite controlled toy, external reference and actual horizontal navigation bounds required; no field authorization'}
    (RESULT / 'release_audit.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'passed': not errors, 'hash_checks': sum(checked.values()),
                      'links': sum(link_counts.values()), 'errors': errors}, ensure_ascii=False))
    raise SystemExit(0 if not errors else 1)


if __name__ == '__main__':
    main()

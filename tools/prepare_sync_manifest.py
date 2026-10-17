"""Audit a bounded Git release selection without staging or deleting files.

The current selection is intentionally narrower than the full working tree:
it keeps source, canonical evidence, the latest presentation and final PDF
renders while leaving development captures and old PPT revisions local.
"""
from collections import Counter
from pathlib import Path
import json
import subprocess


ROOT = Path(__file__).resolve().parents[1]


def git(*args):
    return subprocess.check_output(
        ['git', '-c', f'safe.directory={ROOT}', '-c', 'core.filemode=false',
         '-c', 'core.quotePath=false',
         '-C', str(ROOT), *args], stderr=subprocess.DEVNULL)


def selected_paths():
    tracked = []
    for row in git('diff', '--numstat', '--ignore-space-at-eol', 'origin/main').decode().splitlines():
        added, deleted, path = row.split('\t', 2)
        if (added, deleted) != ('0', '0') and path != '.gitignore':
            tracked.append(path)
    untracked = [p.decode() for p in git('ls-files', '--others', '--exclude-standard', '-z').split(b'\0') if p]
    chosen = []
    for path in untracked:
        p = Path(path)
        if path.startswith(('brain_linux/', 'common/', 'csd_vx6.8_lastest/inspection_v2_candidate/',
                            'console_soft/', 'scripts/', 'tests/', 'docs/thesis/',
                            'docs/experiment/', 'PPT制作/assets/',
                            'PPT制作/V4.7实验叙事与资产冻结版/',
                            '毕业设计写作文档/')):
            chosen.append(path)
        elif path.startswith('tools/') and p.suffix in ('.py', '.sh', '.md', '.json'):
            chosen.append(path)
        elif path.startswith('PPT制作/') and len(p.parts) == 2 and p.suffix == '.md':
            chosen.append(path)
        elif path.startswith('docs/middle-defense/'):
            rel = p.relative_to('docs/middle-defense')
            if (len(rel.parts) == 1 and p.suffix in ('.md', '.json', '.tsv', '.log')
                    or rel.parts[0] in ('render-main-final2', 'render-school-final2')
                    or p.suffix in ('.md', '.json', '.tsv') and rel.parts[0] in
                       ('baseline', 'diagnostics', 'thesis-regression', 'word-audit')):
                chosen.append(path)
        elif path.startswith('thuthesis/'):
            if (path in ('thuthesis/auv-middle-defense.tex',
                         'thuthesis/auv-middle-defense-main.tex',
                         'thuthesis/auv-middle-defense-school.tex',
                         'thuthesis/upstream-lock.json')
                    or path.startswith('thuthesis/middle/')
                    or path.startswith('thuthesis/backups/20260928_full_236p/')
                       and p.name in ('README.md', 'manifest.json', 'auv-thesis_full_236p.pdf',
                                      'source_and_figures.complete.tar.gz')):
                chosen.append(path)
        elif path in ('Makefile', '中期报告codex指引.md'):
            chosen.append(path)
    return sorted(set(tracked + chosen))


def main():
    selected = selected_paths()
    families = Counter(p.split('/')[0] for p in selected)
    bytes_total = sum((ROOT / p).stat().st_size for p in selected if (ROOT / p).is_file())
    print(json.dumps({'files': len(selected), 'MiB': round(bytes_total / 1048576, 2),
                      'families': families}, ensure_ascii=False, indent=2))
    return selected


if __name__ == '__main__':
    main()

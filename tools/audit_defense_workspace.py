"""Read-only working-tree inventory against a fetched origin/main.

Does not fetch, normalize files, delete assets, or change Git configuration.
Includes untracked files and nested repositories; zero-line differences are
metadata/formatting candidates, not reviewed algorithm changes.
"""
import argparse
from collections import Counter
import csv
import json
from pathlib import Path
import subprocess


def git(root, *args):
    return subprocess.check_output(
        ['git', '-c', f'safe.directory={root}', '-c', 'core.quotePath=false',
         '-C', str(root), *args], stderr=subprocess.DEVNULL)


def inventory(root, base):
    records = []
    for item in git(root, 'diff', '--no-renames', '--numstat', '-z',
                    '--ignore-space-at-eol', base).split(b'\0'):
        if not item:
            continue
        added, removed, path = item.decode('utf-8', errors='replace').split('\t', 2)
        kind = 'metadata_or_eol' if (added, removed) == ('0', '0') else 'content'
        records.append(dict(kind=kind, path=path, added=added, removed=removed))
    for path in git(root, 'ls-files', '--others', '--exclude-standard', '-z').split(b'\0'):
        if path:
            records.append(dict(kind='untracked', path=path.decode('utf-8', errors='replace'),
                                added='', removed=''))
    return dict(base=base, head=git(root, 'rev-parse', 'HEAD').decode().strip(),
                counts=dict(Counter(r['kind'] for r in records)),
                families=dict(Counter(r['path'].split('/')[0] for r in records
                                      if r['kind'] != 'metadata_or_eol')),
                files=records)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    base = git(root, 'rev-parse', 'origin/main').decode().strip()
    report = {'comparison': 'working tree (including index) against origin/main',
              'normalization': 'Git filters plus ignore-space-at-eol; no file mutation',
              'repositories': {'main': inventory(root, base)}}
    for path in ('AUV-Master-Mag', 'hardware_wrappers/fangkong_adc'):
        link = git(root, 'ls-tree', base, path).decode().split()[2]
        report['repositories'][path] = inventory(root / path, link)
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / 'workspace_inventory.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    with (out / 'workspace_inventory.tsv').open('w') as stream:
        writer = csv.writer(stream, delimiter='\t')
        writer.writerow(['repository', 'kind', 'added', 'removed', 'path'])
        for name, repo in report['repositories'].items():
            for row in repo['files']:
                writer.writerow([name, row['kind'], row['added'], row['removed'], row['path']])
    print(json.dumps({name: {k: v for k, v in repo.items() if k != 'files'}
                      for name, repo in report['repositories'].items()}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()

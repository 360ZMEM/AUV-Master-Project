#!/usr/bin/env python3
"""Explicit, locked ThuThesis vendor updates; never called implicitly by make.

fetch saves the entire official tagged tree. activate changes only template
runtime files after a hash guard; rollback restores only that activation.
"""
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
THU = ROOT / 'thuthesis'
VENDOR = THU / 'vendor'
LOCK = THU / 'upstream-lock.json'
URL = 'https://github.com/tuna/thuthesis.git'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def run(args, **kwargs):
    return subprocess.check_output(args, text=True, **kwargs).strip()


def fetch(tag):
    if not re.fullmatch(r'v\d+\.\d+\.\d+', tag):
        raise SystemExit('Use an explicit release tag: vX.Y.Z')
    dest = VENDOR / tag
    if dest.exists():
        raise SystemExit(f'Already exists; verify/use existing tree: {dest}')
    VENDOR.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='auv-thuthesis-') as tmp:
        checkout = Path(tmp) / 'upstream'
        run(['git', 'clone', '--depth', '1', '--branch', tag, URL, str(checkout)])
        commit = run(['git', '-C', str(checkout), 'rev-parse', 'HEAD'])
        tag_object = run(['git', '-C', str(checkout), 'rev-parse', tag])
        tracked = run(['git', '-C', str(checkout), 'ls-files']).splitlines()
        dtx = (checkout / 'thuthesis.dtx').read_text()
        if tag[1:] not in dtx:
            raise SystemExit('Tag/version mismatch')
        hashes = {p: sha(checkout / p) for p in tracked}
        build_log = run(['xetex', '-interaction=nonstopmode', '-halt-on-error', 'thuthesis.ins'], cwd=checkout)
        dest.mkdir()
        for p in tracked + ['thuthesis.cls', 'dtx-style.sty']:
            target = dest / p
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(checkout / p, target)
        (dest / 'docstrip-build.log').write_text(build_log + '\n')
        manifest = {'url': URL, 'tag': tag, 'tag_object': tag_object, 'commit': commit,
                    'source_sha256': hashes,
                    'generated_sha256': {p: sha(dest / p) for p in ['thuthesis.cls', 'dtx-style.sty']}}
        write_json(dest / 'vendor-manifest.json', manifest)
    print(f'Fetched full {tag} ({commit}); not activated. {len(tracked)} source files.')


def verify_vendor(tag):
    dest = VENDOR / tag
    manifest = json.loads((dest / 'vendor-manifest.json').read_text())
    for p, expected in {**manifest['source_sha256'], **manifest['generated_sha256']}.items():
        if sha(dest / p) != expected:
            raise SystemExit(f'Vendor changed: {p}')
    return dest, manifest


def activate(tag):
    dest, manifest = verify_vendor(tag)
    old = json.loads(LOCK.read_text()) if LOCK.exists() else None
    if old:
        for p, expected in old['runtime_sha256'].items():
            if sha(THU / p) != expected:
                raise SystemExit(f'Local template edit: {p}; preserve and reconcile before switching')
        if old['tag'] == tag:
            print('Already active; runtime and vendor hashes verified.')
            return
    runtime = sorted(p.name for p in dest.iterdir() if p.is_file() and
                     (p.suffix in ('.cls', '.sty', '.bst', '.bbx', '.cbx') or
                      p.name in ('thuthesis.dtx', 'thuthesis.ins', 'thu-fig-logo.pdf', 'thu-text-logo.pdf', 'LICENSE')))
    paths = sorted(set(runtime) | set(old['runtime_sha256'] if old else []))
    stamp = dt.datetime.now().strftime('%Y%m%dT%H%M%S%f')
    backup = THU / 'backups' / 'template-switch' / stamp
    backup.mkdir(parents=True)
    before = {p: sha(THU / p) for p in paths}
    for p in paths:
        if (THU / p).exists():
            shutil.copy2(THU / p, backup / p)
    after = {p: sha(dest / p) if p in runtime else None for p in paths}
    write_json(backup / 'restore.json', {'before': before, 'after': after, 'old_lock': old})
    for p in paths:
        if p in runtime:
            shutil.copy2(dest / p, THU / p)
        elif (THU / p).exists():
            (THU / p).unlink()
    lock = {k: manifest[k] for k in ('url', 'tag', 'tag_object', 'commit')}
    lock.update(runtime_sha256={p: after[p] for p in runtime}, rollback_snapshot=str(backup.relative_to(ROOT)))
    write_json(LOCK, lock)
    print(f'Activated {tag}; rollback snapshot: {backup.relative_to(ROOT)}')


def rollback(snapshot):
    backup = Path(snapshot).resolve()
    allowed = (THU / 'backups' / 'template-switch').resolve()
    if backup.parent != allowed:
        raise SystemExit('Use a template-switch snapshot created by this script')
    data = json.loads((backup / 'restore.json').read_text())
    for p, expected in data['after'].items():
        if sha(THU / p) != expected:
            raise SystemExit(f'Refusing to overwrite intervening edit: {p}')
    for p, expected in data['before'].items():
        if expected is not None and sha(backup / p) != expected:
            raise SystemExit(f'Backup checksum mismatch: {p}')
    for p, expected in data['before'].items():
        if expected is None:
            (THU / p).unlink(missing_ok=True)
        else:
            shutil.copy2(backup / p, THU / p)
    if data['old_lock'] is None:
        LOCK.unlink(missing_ok=True)
    else:
        write_json(LOCK, data['old_lock'])
    print('Restored only managed template files; thesis and report content untouched.')


def verify():
    lock = json.loads(LOCK.read_text())
    verify_vendor(lock['tag'])
    for p, expected in lock['runtime_sha256'].items():
        if sha(THU / p) != expected:
            raise SystemExit(f'Runtime checksum mismatch: {p}')
    print(f"Verified {lock['tag']} {lock['commit']}: vendor + {len(lock['runtime_sha256'])} runtime files")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest='command', required=True)
    for command in ('fetch', 'activate'):
        subs.add_parser(command).add_argument('--tag', required=True)
    subs.add_parser('rollback').add_argument('--snapshot', required=True)
    subs.add_parser('verify')
    args = parser.parse_args()
    if args.command == 'fetch': fetch(args.tag)
    elif args.command == 'activate': activate(args.tag)
    elif args.command == 'rollback': rollback(args.snapshot)
    else: verify()

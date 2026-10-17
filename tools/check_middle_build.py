#!/usr/bin/env python3
"""Fail report builds on unresolved content or wrong template provenance."""
import hashlib
import json
from pathlib import Path
import re
import sys

stem = Path(sys.argv[1])
log = stem.with_suffix('.log').read_text(errors='replace')
patterns = [r'^!', r'Undefined control sequence', r'Citation .* undefined',
            r'Reference .* undefined', r'There were undefined references',
            r'Rerun to get cross-references right', r'Please \(re\)run Biber',
            r'Missing character:', r'multiply defined', r'Overfull \\[hv]box']
bad = [line for line in log.splitlines() if any(re.search(p, line) for p in patterns)]
root = Path(__file__).resolve().parents[1]
thu = root / 'thuthesis'
lock = json.loads((thu / 'upstream-lock.json').read_text())
cls = thu / 'thuthesis.cls'
fls = stem.with_suffix('.fls')
# Some distro XeTeX builds retain the recorder's temporary xelatex<PID>.fls.
# Bind any fallback to this exact job's OUTPUT log, not an unrelated recorder.
if not fls.is_file():
    expected_log = stem.with_suffix('.log').resolve()
    matches = []
    for candidate in stem.parent.glob('xelatex*.fls'):
        lines = candidate.read_text(errors='replace').splitlines()
        if any(line.startswith('OUTPUT ') and Path(line[7:]).resolve() == expected_log for line in lines):
            matches.append(candidate)
    if not matches:
        raise SystemExit(f'No recorder bound to {expected_log}')
    fls = max(matches, key=lambda p: p.stat().st_mtime_ns)
    if fls.stat().st_mtime < stem.with_suffix('.log').stat().st_mtime - 120:
        raise SystemExit(f'Stale recorder: {fls}')
inputs = {Path(line[6:]).resolve() for line in fls.read_text().splitlines()
          if line.startswith('INPUT ') and line.endswith('thuthesis.cls')}
if inputs != {cls.resolve()}:
    bad.append(f'Unexpected template path(s): {inputs}')
if hashlib.sha256(cls.read_bytes()).hexdigest() != lock['runtime_sha256']['thuthesis.cls']:
    bad.append('Template checksum differs from lock')
if not stem.with_suffix('.pdf').is_file():
    bad.append('Missing PDF')
result = {'status': 'FAIL' if bad else 'PASS', 'errors': bad, 'template': str(cls), 'recorder': str(fls),
          'version': lock['tag'], 'commit': lock['commit']}
stem.with_suffix('.check.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
print(json.dumps(result, ensure_ascii=False))
sys.exit(bool(bad))

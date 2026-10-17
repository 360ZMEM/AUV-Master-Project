"""Compile and exercise the isolated C parser without changing VxWorks tasks."""

from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
CANDIDATE = ROOT / 'csd_vx6.8_lastest/inspection_v2_candidate'


def test_gx3_cf_guard_compiles_and_rejects_faults(tmp_path):
    compiler = shutil.which('cc')
    if compiler is None:
        pytest.skip('host C compiler unavailable')
    binary = tmp_path / 'gx3_cf_guard_host'
    subprocess.run([
        compiler, '-std=c99', '-O2', '-Wall', '-Wextra', '-Werror', '-pedantic',
        '-I', str(CANDIDATE), str(CANDIDATE / 'gx3_cf_guard.c'),
        str(CANDIDATE / 'test_gx3_cf_guard_host.c'), '-lm', '-o', str(binary),
    ], check=True, capture_output=True, text=True)
    result = subprocess.run([str(binary)], check=True, capture_output=True, text=True)
    assert 'fault injection passed' in result.stdout

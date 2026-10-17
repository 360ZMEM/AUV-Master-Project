"""Host-compile the isolated bounded DVL BI serial parser candidate."""

from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
CANDIDATE = ROOT / 'csd_vx6.8_lastest/inspection_v2_candidate'


def test_dvl_bi_guard_compiles_and_rejects_malformed_stream(tmp_path):
    compiler = shutil.which('cc')
    if compiler is None:
        pytest.skip('host C compiler unavailable')
    binary = tmp_path / 'dvl_bi_guard_host'
    subprocess.run([
        compiler, '-std=c99', '-O2', '-Wall', '-Wextra', '-Werror', '-pedantic',
        '-I', str(CANDIDATE), str(CANDIDATE / 'dvl_bi_guard.c'),
        str(CANDIDATE / 'test_dvl_bi_guard_host.c'), '-o', str(binary),
    ], check=True, capture_output=True, text=True)
    result = subprocess.run([str(binary)], check=True, capture_output=True, text=True)
    assert 'accepted=2 rejected_bi=4' in result.stdout

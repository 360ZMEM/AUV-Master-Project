#!/usr/bin/env bash
# E5 — 磁畸变扰动 sweep（论文 §3.5.2）
# 3 场景 × 5 种子 × 2 mpc_mode = 30 runs（默认 120s/run）
# Smoke 跑：bash scripts/run_mag_sweep.sh --duration 30 --seeds 0
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_DIR"
exec python3 tools/run_thesis_sweep.py \
    --scenarios baseline,mag_distortion_light,mag_distortion_heavy \
    --seeds 0,1,2,3,4 \
    --mpc-modes baseline,ua \
    --duration 120 "$@"

#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPT="$ROOT_DIR/scripts/compare_sim_equivalence.py"

if [[ ! -f "$SCRIPT" ]]; then
  echo "[AUV][ERROR] compare script not found: $SCRIPT"
  exit 1
fi

if [[ -n "${AUV_CONDA_ENV:-}" ]] && command -v conda >/dev/null 2>&1; then
  eval "$(conda shell.bash hook)"
  conda activate "$AUV_CONDA_ENV"
fi

/usr/bin/python3 "$SCRIPT" "$@"

#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
python3 "${SCRIPT_DIR}/scripts/run_jetson_realtime.py" --config "${SCRIPT_DIR}/config.yaml" "$@"

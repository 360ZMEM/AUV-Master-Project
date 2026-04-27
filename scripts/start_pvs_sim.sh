#!/usr/bin/env bash
set -euo pipefail

# Start the PVS-backed simulation side.
#
# This is the PVS counterpart to start_holoocean_sim.sh. It keeps the existing
# start_lin_sim.sh entrypoint but forces the simulation backend to PVS.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SIM_ENTRY="$ROOT_DIR/scripts/start_lin_sim.sh"

if [[ ! -f "$SIM_ENTRY" ]]; then
  echo "[AUV][ERROR] start_lin_sim.sh not found: $SIM_ENTRY"
  exit 1
fi

MODE="${1:-both}"
shift || true

echo "[AUV] starting PVS side via start_lin_sim.sh (${MODE})..."
bash "$SIM_ENTRY" "$MODE" --sim-backend pvs "$@"

#!/usr/bin/env bash
set -euo pipefail

# Start the HoloOcean simulation side only.
#
# This script is a convenience wrapper around start_lin_sim.sh.
# It keeps the simulation/bridge entrypoint unchanged while giving a clearer
# semantic name for day-to-day use.
#
# Usage examples:
#   bash start_holoocean_sim.sh
#   bash start_holoocean_sim.sh bridge
#   bash start_holoocean_sim.sh sim
#   bash start_holoocean_sim.sh both

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SIM_ENTRY="$ROOT_DIR/scripts/start_lin_sim.sh"

if [[ ! -f "$SIM_ENTRY" ]]; then
  echo "[AUV][ERROR] start_lin_sim.sh not found: $SIM_ENTRY"
  exit 1
fi

MODE="${1:-both}"
shift || true

echo "[AUV] starting HoloOcean side via start_lin_sim.sh (${MODE})..."
bash "$SIM_ENTRY" "$MODE" "$@"

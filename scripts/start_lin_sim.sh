#!/usr/bin/env bash
set -euo pipefail

# Start simulation side on Linux.
# Usage:
#   ./start_lin_sim.sh sim
#   ./start_lin_sim.sh bridge
#   ./start_lin_sim.sh both

MODE="${1:-both}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SIM_APPS_DIR="$ROOT_DIR/sim_holoocean/apps"
SIM_CFG="$ROOT_DIR/config/sim_params.yaml"
BRIDGE_CFG="$ROOT_DIR/config/bridge_params.yaml"

make_uuid() {
  /usr/bin/python3 - <<'PY'
import uuid
print(uuid.uuid4())
PY
}

handle_sigint() {
  echo "[AUV] received SIGINT, treating as manual termination."
  exit 0
}

handle_sigterm() {
  echo "[AUV] received SIGTERM, treating as manual termination."
  exit 0
}

if [[ ! -d "$SIM_APPS_DIR" ]]; then
  echo "[AUV][ERROR] sim_holoocean/apps not found: $SIM_APPS_DIR"
  exit 1
fi

if [[ ! -f "$SIM_CFG" ]]; then
  echo "[AUV][ERROR] sim config not found: $SIM_CFG"
  exit 1
fi

if [[ ! -f "$BRIDGE_CFG" ]]; then
  echo "[AUV][ERROR] bridge config not found: $BRIDGE_CFG"
  exit 1
fi

# Optional conda activation for Linux migration workflow.
if [[ -n "${AUV_CONDA_ENV:-}" ]] && command -v conda >/dev/null 2>&1; then
  eval "$(conda shell.bash hook)"
  conda activate "$AUV_CONDA_ENV"
fi

cd "$SIM_APPS_DIR"
trap handle_sigint INT
trap handle_sigterm TERM

run_sim() {
  local runtime_uuid="${AUV_HOLOOCEAN_UUID:-$(make_uuid)}"
  echo "[AUV] Starting main simulation..."
  AUV_HOLOOCEAN_UUID="$runtime_uuid" /usr/bin/python3 main.py --config "$SIM_CFG"
}

run_bridge() {
  local runtime_uuid="${AUV_HOLOOCEAN_UUID:-$(make_uuid)}"
  echo "[AUV] Starting Zenoh bridge..."
  AUV_HOLOOCEAN_UUID="$runtime_uuid" /usr/bin/python3 run_zenoh_bridge.py --config "$BRIDGE_CFG"
}

case "$MODE" in
  sim)
    run_sim
    ;;
  bridge)
    run_bridge
    ;;
  both)
    # Keep bridge in background so simulation remains attached to current shell.
    AUV_HOLOOCEAN_UUID="$(make_uuid)" run_bridge &
    BRIDGE_PID=$!
    trap 'echo "[AUV] stopping bridge ($BRIDGE_PID)"; kill "$BRIDGE_PID" 2>/dev/null || true' EXIT
    trap 'echo "[AUV] received SIGINT, treating as manual termination."; kill "$BRIDGE_PID" 2>/dev/null || true; exit 0' INT
    trap 'echo "[AUV] received SIGTERM, treating as manual termination."; kill "$BRIDGE_PID" 2>/dev/null || true; exit 0' TERM
    AUV_HOLOOCEAN_UUID="$(make_uuid)" run_sim
    ;;
  *)
    echo "[AUV][ERROR] invalid mode: $MODE"
    echo "[AUV] valid modes: sim | bridge | both"
    exit 1
    ;;
esac

echo "[AUV] Completed mode=$MODE"

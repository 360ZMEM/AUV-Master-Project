#!/usr/bin/env bash
set -euo pipefail

# Start simulation side on Linux.
# Usage:
#   ./start_lin_sim.sh sim
#   ./start_lin_sim.sh bridge --backend protocol_udp
#   ./start_lin_sim.sh both --bridge-cfg /abs/path/to/bridge_params.protocol_udp.yaml

MODE="both"
if [[ $# -gt 0 && "$1" != -* ]]; then
  MODE="$1"
  shift
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SIM_APPS_DIR="$ROOT_DIR/sim_holoocean/apps"
SIM_CFG="${AUV_SIM_CFG:-$ROOT_DIR/config/sim_params.yaml}"
BRIDGE_CFG_OVERRIDE="${AUV_BRIDGE_CFG:-}"
BRIDGE_BACKEND="${AUV_BRIDGE_BACKEND:-}"

usage() {
  cat <<'EOF'
Usage:
  ./start_lin_sim.sh [sim|bridge|both] [options]

Options:
  --backend BACKEND     bridge backend: zenoh_json or protocol_udp
  --bridge-cfg PATH     explicit bridge config path
  --sim-cfg PATH        explicit sim config path
  -h, --help            show this help

Notes:
  - default backend remains zenoh_json
  - when --backend protocol_udp is used and --bridge-cfg is omitted,
    config/bridge_params.protocol_udp.yaml is preferred if present
EOF
}

resolve_default_bridge_cfg() {
  local backend="$1"
  case "$backend" in
    protocol_udp)
      if [[ -f "$ROOT_DIR/config/bridge_params.protocol_udp.yaml" ]]; then
        echo "$ROOT_DIR/config/bridge_params.protocol_udp.yaml"
      else
        echo "$ROOT_DIR/config/bridge_params.yaml"
      fi
      ;;
    *)
      echo "$ROOT_DIR/config/bridge_params.yaml"
      ;;
  esac
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --backend)
      BRIDGE_BACKEND="${2:?missing value for --backend}"
      shift 2
      ;;
    --bridge-cfg)
      BRIDGE_CFG_OVERRIDE="${2:?missing value for --bridge-cfg}"
      shift 2
      ;;
    --sim-cfg)
      SIM_CFG="${2:?missing value for --sim-cfg}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "[AUV][ERROR] unknown argument: $1"
      usage
      exit 1
      ;;
  esac
done

if [[ -n "$BRIDGE_CFG_OVERRIDE" ]]; then
  BRIDGE_CFG="$BRIDGE_CFG_OVERRIDE"
else
  BRIDGE_CFG="$(resolve_default_bridge_cfg "${BRIDGE_BACKEND:-zenoh_json}")"
fi

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

echo "[AUV] sim config: $SIM_CFG"
echo "[AUV] bridge config: $BRIDGE_CFG"
if [[ -n "$BRIDGE_BACKEND" ]]; then
  echo "[AUV] requested bridge backend: $BRIDGE_BACKEND"
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
  echo "[AUV] Starting simulation bridge..."
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

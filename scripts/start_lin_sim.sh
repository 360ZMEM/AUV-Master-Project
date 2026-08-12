#!/usr/bin/env bash
set -euo pipefail

# Start simulation side on Linux.
# Usage:
#   ./start_lin_sim.sh sim
#   ./start_lin_sim.sh bridge --backend protocol_udp
#   ./start_lin_sim.sh both --sim-backend pvs --backend protocol_udp
#   ./start_lin_sim.sh both --bridge-cfg /abs/path/to/bridge_params.protocol_udp.yaml

MODE="both"
if [[ $# -gt 0 && "$1" != -* ]]; then
  MODE="$1"
  shift
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SIM_APPS_DIR="$ROOT_DIR/sim_holoocean/apps"
SIM_BACKEND="${AUV_SIM_BACKEND:-holoocean}"
SIM_CFG_OVERRIDE="${AUV_SIM_CFG:-}"
CLI_SIM_CFG_OVERRIDE=""
BRIDGE_CFG_OVERRIDE="${AUV_BRIDGE_CFG:-}"
CLI_BRIDGE_CFG_OVERRIDE=""
BRIDGE_BACKEND="${AUV_BRIDGE_BACKEND:-}"

usage() {
  cat <<'EOF'
Usage:
  ./start_lin_sim.sh [sim|bridge|both] [options]

Options:
  --sim-backend BACKEND  simulation backend: holoocean or pvs
  --backend BACKEND     bridge backend: zenoh_json or protocol_udp
  --bridge-cfg PATH     explicit bridge config path
  --sim-cfg PATH        explicit sim config path
  -h, --help            show this help

Notes:
  - default simulation backend remains holoocean
  - when --sim-backend pvs is used, PVS-specific config defaults are preferred
  - when --backend protocol_udp is used and --bridge-cfg is omitted,
    config/bridge_params.protocol_udp.yaml or the PVS overlay is preferred if present
EOF
}

resolve_default_sim_cfg() {
  local backend="$1"
  case "$backend" in
    pvs)
      if [[ -f "$ROOT_DIR/config/sim_params.pvs.yaml" ]]; then
        echo "$ROOT_DIR/config/sim_params.pvs.yaml"
      else
        echo "$ROOT_DIR/config/sim_params.yaml"
      fi
      ;;
    *)
      echo "$ROOT_DIR/config/sim_params.yaml"
      ;;
  esac
}

resolve_default_bridge_cfg() {
  local sim_backend="$1"
  local bridge_backend="$2"

  if [[ "$sim_backend" == "pvs" && "$bridge_backend" == "protocol_udp" ]]; then
    if [[ -f "$ROOT_DIR/config/bridge_params.protocol_udp.pvs.yaml" ]]; then
      echo "$ROOT_DIR/config/bridge_params.protocol_udp.pvs.yaml"
      return
    fi
    if [[ -f "$ROOT_DIR/config/bridge_params.protocol_udp.yaml" ]]; then
      echo "$ROOT_DIR/config/bridge_params.protocol_udp.yaml"
      return
    fi
  fi

  if [[ "$sim_backend" == "pvs" ]]; then
    if [[ -f "$ROOT_DIR/config/bridge_params.pvs.yaml" ]]; then
      echo "$ROOT_DIR/config/bridge_params.pvs.yaml"
      return
    fi
  fi

  case "$bridge_backend" in
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
    --sim-backend)
      SIM_BACKEND="${2:?missing value for --sim-backend}"
      shift 2
      ;;
    --backend)
      BRIDGE_BACKEND="${2:?missing value for --backend}"
      shift 2
      ;;
    --bridge-cfg)
      CLI_BRIDGE_CFG_OVERRIDE="${2:?missing value for --bridge-cfg}"
      shift 2
      ;;
    --sim-cfg)
      CLI_SIM_CFG_OVERRIDE="${2:?missing value for --sim-cfg}"
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

if [[ -n "$CLI_SIM_CFG_OVERRIDE" ]]; then
  SIM_CFG="$CLI_SIM_CFG_OVERRIDE"
elif [[ -n "$SIM_CFG_OVERRIDE" ]]; then
  SIM_CFG="$SIM_CFG_OVERRIDE"
else
  SIM_CFG="$(resolve_default_sim_cfg "$SIM_BACKEND")"
fi

if [[ -n "$CLI_BRIDGE_CFG_OVERRIDE" ]]; then
  BRIDGE_CFG="$CLI_BRIDGE_CFG_OVERRIDE"
elif [[ -n "$BRIDGE_CFG_OVERRIDE" ]]; then
  BRIDGE_CFG="$BRIDGE_CFG_OVERRIDE"
else
  BRIDGE_CFG="$(resolve_default_bridge_cfg "$SIM_BACKEND" "${BRIDGE_BACKEND:-zenoh_json}")"
fi
if [[ "$SIM_CFG" != /* ]]; then
  SIM_CFG="$ROOT_DIR/$SIM_CFG"
fi

if [[ "$BRIDGE_CFG" != /* ]]; then
  BRIDGE_CFG="$ROOT_DIR/$BRIDGE_CFG"
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
echo "[AUV] requested simulation backend: $SIM_BACKEND"
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
    sim_cleanup() {
      if [[ -n "${BRIDGE_PID:-}" ]]; then
        echo "[AUV] stopping bridge ($BRIDGE_PID)"
        kill -INT -- -"$BRIDGE_PID" >/dev/null 2>&1 || kill -INT "$BRIDGE_PID" >/dev/null 2>&1 || true
        for _ in 1 2 3; do
          kill -0 "$BRIDGE_PID" 2>/dev/null || break
          sleep 1
        done
        if kill -0 "$BRIDGE_PID" 2>/dev/null; then
          kill -KILL -- -"$BRIDGE_PID" >/dev/null 2>&1 || kill -KILL "$BRIDGE_PID" >/dev/null 2>&1 || true
        fi
      fi
      pkill -KILL -f "run_zenoh_bridge.py" >/dev/null 2>&1 || true
      pkill -KILL -f "sim_holoocean/apps/main.py" >/dev/null 2>&1 || true
      pkill -KILL -f "python3 main.py --config" >/dev/null 2>&1 || true
    }
    trap sim_cleanup EXIT
    trap 'echo "[AUV] received SIGINT, treating as manual termination."; sim_cleanup; exit 0' INT
    trap 'echo "[AUV] received SIGTERM, treating as manual termination."; sim_cleanup; exit 0' TERM
    AUV_HOLOOCEAN_UUID="$(make_uuid)" run_sim
    ;;
  *)
    echo "[AUV][ERROR] invalid mode: $MODE"
    echo "[AUV] valid modes: sim | bridge | both"
    exit 1
    ;;
esac

echo "[AUV] Completed mode=$MODE"

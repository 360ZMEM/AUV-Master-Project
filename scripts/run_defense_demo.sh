#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

DURATION_S=120
START_GUI=false
RECORD_BAG=true

while [[ $# -gt 0 ]]; do
  case "$1" in
    --duration)
      DURATION_S="${2:?missing value for --duration}"
      shift 2
      ;;
    --gui)
      START_GUI=true
      shift
      ;;
    --no-record-bag)
      RECORD_BAG=false
      shift
      ;;
    -h|--help)
      cat <<'EOF'
Usage: scripts/run_defense_demo.sh [--duration SECONDS] [--gui] [--no-record-bag]

Starts the local PVS + protocol_udp + ROS2 cable-inspection demo, Foxglove
WebSocket bridge, and the defense-1080 layout. --gui also opens the dark PySide6
console when a desktop DISPLAY is available.
EOF
      exit 0
      ;;
    *)
      echo "[AUV][ERROR] unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

export AUV_PROJECT_ROOT="$ROOT_DIR"
export AUV_DATA_ROOT="${AUV_DATA_ROOT:-$ROOT_DIR/.auv_data}"
mkdir -p "$AUV_DATA_ROOT" "$ROOT_DIR/foxglove_layout_project/output"

"$ROOT_DIR/scripts/build_foxglove_layout.sh" \
  --profile defense-1080 \
  --output foxglove_layout_project/output/auv_defense_1080.json \
  --temp-output tmp/foxglove_layout/auv_defense_1080.json \
  --name "AUV 海底电缆自主巡检答辩" \
  --description "1920x1080 mission dashboard" \
  --with-mock-topics

GUI_PID=""
cleanup() {
  if [[ -n "$GUI_PID" ]] && kill -0 "$GUI_PID" 2>/dev/null; then
    kill -TERM "$GUI_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

if [[ "$START_GUI" == true ]]; then
  if [[ -z "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ]]; then
    echo "[AUV][WARN] --gui requested but no desktop display is available"
  else
    AUV_CONSOLE_THEME=dark python3 console_soft/auv_console_pyside6/main.py --theme dark &
    GUI_PID=$!
  fi
fi

record_args=(--record-bag --bag-storage mcap --bag-profile cable_acceptance)
if [[ "$RECORD_BAG" != true ]]; then
  record_args=(--no-record-bag)
fi

if [[ -f "$ROOT_DIR/brain_linux/install/setup.bash" ]]; then
  export AUV_SKIP_BRAIN_BUILD=1
fi

bash scripts/start_experiment.sh \
  --preflight-clean \
  --sim-backend pvs \
  --bridge-backend protocol_udp \
  --arbiter-profile \
  --duration "$DURATION_S" \
  "${record_args[@]}" \
  --wait-before-record 8 \
  --bag-finalize 15 \
  --auto-activate \
  --skip-layout \
  --brain-arg enable_cable_tracking:=true \
  --brain-arg enable_cable_mission_autostart:=true \
  --brain-arg "cable_tracking_config:=$ROOT_DIR/brain_linux/config/cable_tracking.yaml"

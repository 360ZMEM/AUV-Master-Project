#!/usr/bin/env bash
set -euo pipefail

# Foxglove + HoloOcean + ROS2 unified launcher.
#
# Launch order:
#   1. Generate the Foxglove layout JSON first.
#   2. Start HoloOcean / Zenoh simulation side via start_lin_sim.sh.
#   3. Start foxglove_bridge in the same ROS2 environment.
#   4. Wait 10 seconds so the sim can bring up topics and sensors.
#   5. Start ROS2 brain side via start_lin_brain.sh.
#
# This script keeps the current repository structure intact and only reuses the
# existing entrypoints. It is intended to be the high-level command for day-to-
# day integration work and future changes.
#
# Usage examples:
#   ./start_foxglove_holoocean_ros.sh
#   ./start_foxglove_holoocean_ros.sh --sim-mode both --brain-mode stack
#   ./start_foxglove_holoocean_ros.sh --skip-layout
#   ./start_foxglove_holoocean_ros.sh --topic-prefix /sim

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPTS_DIR="$ROOT_DIR/scripts"
BRAIN_DIR="$ROOT_DIR/brain_linux"
WORKSPACE_ROOT="$(cd "$ROOT_DIR/.." && pwd)"
FOXGLOVE_SDK_ROS_DIR="${FOXGLOVE_SDK_ROS_DIR:-$WORKSPACE_ROOT/foxglove-sdk/ros}"

SIM_MODE="both"
BRAIN_MODE="stack"
LAYOUT_ARGS=()
VIZ_ARGS=()
SKIP_LAYOUT=false
SIM_DELAY_S="${SIM_DELAY_S:-10}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --sim-mode)
      SIM_MODE="${2:?missing value for --sim-mode}"
      shift 2
      ;;
    --brain-mode)
      BRAIN_MODE="${2:?missing value for --brain-mode}"
      shift 2
      ;;
    --skip-layout)
      SKIP_LAYOUT=true
      shift
      ;;
    --topic-prefix)
      LAYOUT_ARGS+=("--topic-prefix" "${2:?missing value for --topic-prefix}")
      shift 2
      ;;
    --with-map)
      LAYOUT_ARGS+=("--with-map")
      shift
      ;;
    --layout-name)
      LAYOUT_ARGS+=("--name" "${2:?missing value for --layout-name}")
      shift 2
      ;;
    --layout-description)
      LAYOUT_ARGS+=("--description" "${2:?missing value for --layout-description}")
      shift 2
      ;;
    --layout-output)
      LAYOUT_ARGS+=("--output" "${2:?missing value for --layout-output}")
      shift 2
      ;;
    --layout-meta-output)
      LAYOUT_ARGS+=("--meta-output" "${2:?missing value for --layout-meta-output}")
      shift 2
      ;;
    --layout-pretty)
      LAYOUT_ARGS+=("--pretty")
      shift
      ;;
    --viz-mock-mode)
      VIZ_ARGS+=("viz_mock_mode:=true")
      shift
      ;;
    --viz-mock-fallback-timeout)
      VIZ_ARGS+=("viz_mock_fallback_timeout_s:=${2:?missing value for --viz-mock-fallback-timeout}")
      shift 2
      ;;
    -h|--help)
      cat <<'EOF'
Usage:
  ./start_foxglove_holoocean_ros.sh [options]

Options:
  --sim-mode MODE            start_lin_sim.sh mode (default: both)
  --brain-mode MODE          start_lin_brain.sh mode (default: stack)
  --skip-layout              skip Foxglove JSON generation
  --topic-prefix PREFIX      apply a namespace prefix to Foxglove topics
  --with-map                 include the Foxglove 3D map layer
  --layout-name NAME         layout name written into the meta file
  --layout-description TEXT  layout description written into the meta file
  --layout-output PATH       output path passed to the layout generator
  --layout-meta-output PATH  meta output path passed to the layout generator
  --layout-pretty            pretty-print the generated layout JSON
  --viz-mock-mode            force the Foxglove visualization bridge into mock mode
  --viz-mock-fallback-timeout SECONDS
                             fallback timeout before switching to mock mode
EOF
      exit 0
      ;;
    *)
      echo "[AUV][ERROR] unknown argument: $1"
      exit 1
      ;;
  esac
done

if [[ ! -d "$SCRIPTS_DIR" ]]; then
  echo "[AUV][ERROR] scripts directory not found: $SCRIPTS_DIR"
  exit 1
fi

cleanup() {
  if [[ -n "${SIM_PID:-}" ]]; then
    echo "[AUV] stopping simulation launcher ($SIM_PID)"
    kill "$SIM_PID" >/dev/null 2>&1 || true
  fi
  if [[ -n "${BRIDGE_PID:-}" ]]; then
    echo "[AUV] stopping foxglove bridge ($BRIDGE_PID)"
    kill "$BRIDGE_PID" >/dev/null 2>&1 || true
  fi
}

on_sigint() {
  echo "[AUV] received SIGINT, treating as manual termination."
  cleanup
  exit 0
}

on_sigterm() {
  echo "[AUV] received SIGTERM, treating as manual termination."
  cleanup
  exit 0
}

trap cleanup EXIT
trap on_sigint INT
trap on_sigterm TERM

if [[ "$SKIP_LAYOUT" != true ]]; then
  echo "[AUV] generating Foxglove layout JSON..."
  "${SCRIPTS_DIR}/build_foxglove_layout.sh" "${LAYOUT_ARGS[@]}"
else
  echo "[AUV] skipping Foxglove layout generation as requested"
fi

echo "[AUV] starting HoloOcean + Zenoh simulation via start_lin_sim.sh (${SIM_MODE})..."
bash "$SCRIPTS_DIR/start_lin_sim.sh" "$SIM_MODE" &
SIM_PID=$!

if [[ -f "$BRAIN_DIR/install/setup.bash" && -f "$FOXGLOVE_SDK_ROS_DIR/install/local_setup.bash" ]]; then
  echo "[AUV] starting foxglove_bridge on ws://0.0.0.0:8765..."
  (
    set +u
    source /opt/ros/humble/setup.bash
    source "$BRAIN_DIR/install/setup.bash"
    source "$FOXGLOVE_SDK_ROS_DIR/install/local_setup.bash"
    set -u
    ros2 launch foxglove_bridge foxglove_bridge_launch.xml
  ) &
  BRIDGE_PID=$!
else
  echo "[AUV][WARN] foxglove_bridge not started because install/local_setup.bash was not found"
fi

echo "[AUV] waiting ${SIM_DELAY_S}s before starting ROS2 brain..."
sleep "$SIM_DELAY_S"

echo "[AUV] starting ROS2 brain via start_lin_brain.sh (${BRAIN_MODE})..."
bash "$SCRIPTS_DIR/start_lin_brain.sh" "$BRAIN_MODE" "${VIZ_ARGS[@]}"

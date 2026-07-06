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
#   ./start_foxglove_holoocean_ros.sh --bridge-backend protocol_udp --protocol-control-mode-byte 238
#   ./start_foxglove_holoocean_ros.sh --skip-layout
#   ./start_foxglove_holoocean_ros.sh --topic-prefix /sim

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPTS_DIR="$ROOT_DIR/scripts"
BRAIN_DIR="$ROOT_DIR/brain_linux"
WORKSPACE_ROOT="$(cd "$ROOT_DIR/.." && pwd)"
FOXGLOVE_SDK_ROS_DIR="${FOXGLOVE_SDK_ROS_DIR:-$WORKSPACE_ROOT/foxglove-sdk/ros}"
RUN_DIR="${AUV_RUN_DIR:-}"
CHILD_LOG_DIR=""
if [[ -n "$RUN_DIR" ]]; then
  CHILD_LOG_DIR="$RUN_DIR/child_logs"
  mkdir -p "$CHILD_LOG_DIR"
fi

SIM_MODE="both"
BRAIN_MODE="stack"
LAYOUT_ARGS=()
VIZ_ARGS=()
SIM_ARGS=()
BRAIN_ARGS=()
SKIP_LAYOUT=false
SIM_DELAY_S="${SIM_DELAY_S:-10}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --sim-mode)
      SIM_MODE="${2:?missing value for --sim-mode}"
      shift 2
      ;;
    --sim-backend)
      SIM_ARGS+=("--sim-backend" "${2:?missing value for --sim-backend}")
      shift 2
      ;;
    --brain-mode)
      BRAIN_MODE="${2:?missing value for --brain-mode}"
      shift 2
      ;;
    --bridge-backend)
      SIM_ARGS+=("--backend" "${2:?missing value for --bridge-backend}")
      BRAIN_ARGS+=("--backend" "${2:?missing value for --bridge-backend}")
      shift 2
      ;;
    --bridge-cfg)
      SIM_ARGS+=("--bridge-cfg" "${2:?missing value for --bridge-cfg}")
      shift 2
      ;;
    --sim-cfg)
      SIM_ARGS+=("--sim-cfg" "${2:?missing value for --sim-cfg}")
      shift 2
      ;;
    --protocol-control-mode-byte)
      BRAIN_ARGS+=("--protocol-control-mode-byte" "${2:?missing value for --protocol-control-mode-byte}")
      shift 2
      ;;
    --brain-arg)
      BRAIN_ARGS+=("${2:?missing value for --brain-arg}")
      shift 2
      ;;
    --arbiter-profile)
      BRAIN_ARGS+=("--arbiter-profile")
      shift
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
  --sim-backend BACKEND      simulation backend: holoocean or pvs
  --brain-mode MODE          start_lin_brain.sh mode (default: stack)
  --bridge-backend BACKEND   switch both sim and brain to zenoh_json or protocol_udp
  --bridge-cfg PATH          explicit simulation bridge config path
  --sim-cfg PATH             explicit HoloOcean sim config path
  --protocol-control-mode-byte N
                             decision-side control mode byte for protocol_udp
  --brain-arg ARG            append an extra launch argument forwarded to brain
  --arbiter-profile          use protocol_udp arbiter params on the brain side
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
  local grace="${LAUNCHER_GRACE_S:-5}"
  local pids_to_kill=()
  if [[ -n "${SIM_PID:-}" ]]; then
    pids_to_kill+=("$SIM_PID")
  fi
  if [[ -n "${BRIDGE_PID:-}" ]]; then
    pids_to_kill+=("$BRIDGE_PID")
  fi
  if [[ -n "${BRAIN_PID:-}" ]]; then
    pids_to_kill+=("$BRAIN_PID")
  fi
  if [[ "${#pids_to_kill[@]}" -gt 0 ]]; then
    echo "[AUV] stopping child launchers (${pids_to_kill[*]}), grace ${grace}s"
    local pid
    for pid in "${pids_to_kill[@]}"; do
      kill -INT -- -"$pid" >/dev/null 2>&1 || kill -INT "$pid" >/dev/null 2>&1 || true
    done
    local i
    for i in $(seq 1 "$grace"); do
      local any_alive=0
      for pid in "${pids_to_kill[@]}"; do
        if kill -0 "$pid" 2>/dev/null; then
          any_alive=1
          break
        fi
      done
      if [[ "$any_alive" -eq 0 ]]; then
        break
      fi
      sleep 1
    done
    for pid in "${pids_to_kill[@]}"; do
      if kill -0 "$pid" 2>/dev/null; then
        echo "[AUV][WARN] $pid still alive, escalating to SIGTERM on group"
        kill -TERM -- -"$pid" >/dev/null 2>&1 || kill -TERM "$pid" >/dev/null 2>&1 || true
      fi
    done
    sleep 2
    for pid in "${pids_to_kill[@]}"; do
      if kill -0 "$pid" 2>/dev/null; then
        echo "[AUV][WARN] $pid still alive, escalating to SIGKILL on group"
        kill -KILL -- -"$pid" >/dev/null 2>&1 || kill -KILL "$pid" >/dev/null 2>&1 || true
      fi
    done
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

echo "[AUV] starting HoloOcean + bridge simulation via start_lin_sim.sh (${SIM_MODE})..."
# NOTE: do NOT use setsid here — keep children in this script's process group so the
# parent (start_experiment.sh) can kill -- -<pgid> and reach every descendant.
if [[ -n "$CHILD_LOG_DIR" ]]; then
  SIM_LOG="$CHILD_LOG_DIR/sim_launcher.log"
  echo "[AUV] simulation stdout/stderr -> $SIM_LOG"
  bash "$SCRIPTS_DIR/start_lin_sim.sh" "$SIM_MODE" "${SIM_ARGS[@]}" >"$SIM_LOG" 2>&1 &
else
  bash "$SCRIPTS_DIR/start_lin_sim.sh" "$SIM_MODE" "${SIM_ARGS[@]}" &
fi
SIM_PID=$!

if [[ -f "$BRAIN_DIR/install/setup.bash" && -f "$FOXGLOVE_SDK_ROS_DIR/install/local_setup.bash" ]]; then
  echo "[AUV] starting foxglove_bridge on ws://0.0.0.0:8765..."
  if [[ -n "$CHILD_LOG_DIR" ]]; then
    FOXGLOVE_LOG="$CHILD_LOG_DIR/foxglove_bridge.log"
    echo "[AUV] foxglove_bridge stdout/stderr -> $FOXGLOVE_LOG"
    (
      set +u
      source /opt/ros/humble/setup.bash
      source "$BRAIN_DIR/install/setup.bash"
      source "$FOXGLOVE_SDK_ROS_DIR/install/local_setup.bash"
      set -u
      exec ros2 launch foxglove_bridge foxglove_bridge_launch.xml
    ) >"$FOXGLOVE_LOG" 2>&1 &
  else
    (
      set +u
      source /opt/ros/humble/setup.bash
      source "$BRAIN_DIR/install/setup.bash"
      source "$FOXGLOVE_SDK_ROS_DIR/install/local_setup.bash"
      set -u
      exec ros2 launch foxglove_bridge foxglove_bridge_launch.xml
    ) &
  fi
  BRIDGE_PID=$!
else
  echo "[AUV][WARN] foxglove_bridge not started because install/local_setup.bash was not found"
fi

echo "[AUV] waiting ${SIM_DELAY_S}s before starting ROS2 brain..."
sleep "$SIM_DELAY_S"

echo "[AUV] starting ROS2 brain via start_lin_brain.sh (${BRAIN_MODE})..."
if [[ -n "$CHILD_LOG_DIR" ]]; then
  BRAIN_LOG="$CHILD_LOG_DIR/brain_launcher.log"
  echo "[AUV] brain stdout/stderr -> $BRAIN_LOG"
  bash "$SCRIPTS_DIR/start_lin_brain.sh" "$BRAIN_MODE" "${BRAIN_ARGS[@]}" "${VIZ_ARGS[@]}" >"$BRAIN_LOG" 2>&1 &
else
  bash "$SCRIPTS_DIR/start_lin_brain.sh" "$BRAIN_MODE" "${BRAIN_ARGS[@]}" "${VIZ_ARGS[@]}" &
fi
BRAIN_PID=$!

# The experiment wrapper owns the wall-clock duration.  PVS/mock simulation
# helpers may finish their finite scenario before the brain-side nodes have
# produced enough ROS evidence, so the unified launcher must not tear the stack
# down just because the sim helper returned.
WAIT_PIDS=("$BRAIN_PID")
# foxglove_bridge is a visualization sidecar. Port conflicts or browser-side
# bridge crashes must not tear down sim/brain long-running experiments.
# cleanup() still stops it when the launcher exits.
EXIT_PID=""
wait -n -p EXIT_PID "${WAIT_PIDS[@]}" 2>/dev/null
EXIT_CODE=$?
which_child="unknown"
case "$EXIT_PID" in
  "$SIM_PID")    which_child="sim (start_lin_sim.sh)" ;;
  "$BRIDGE_PID") which_child="bridge (foxglove_bridge)" ;;
  "$BRAIN_PID")  which_child="brain (start_lin_brain.sh)" ;;
esac
echo "[AUV] one of (sim/bridge/brain) exited: pid=${EXIT_PID:-?} code=${EXIT_CODE} child=${which_child}"
echo "[AUV] finalizing via cleanup trap"
exit 0

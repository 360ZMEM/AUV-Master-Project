#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPTS_DIR="$ROOT_DIR/scripts"
BRAIN_DIR="$ROOT_DIR/brain_linux"
LOG_ROOT="${AUV_EXPERIMENT_LOG_ROOT:-$ROOT_DIR/log/experiments}"
SIM_MODE="both"
BRAIN_MODE="stack"
LAUNCH_ARGS=()
BAG_EXTRA_ARGS=()
WAIT_BEFORE_RECORD_S="${WAIT_BEFORE_RECORD_S:-3}"

timestamp() {
  date +"%Y%m%d_%H%M%S"
}

usage() {
  cat <<'EOF'
Usage:
  ./start_experiment.sh [options]

Options:
  --sim-mode MODE              start_lin_sim.sh mode passed through to unified launcher
  --brain-mode MODE            start_lin_brain.sh mode passed through to unified launcher
  --skip-layout                skip Foxglove layout generation
  --topic-prefix PREFIX        apply a namespace prefix to generated Foxglove topics
  --with-map                   include the 3D map layer in generated layout
  --viz-mock-mode              force visualization bridge mock mode
  --viz-mock-fallback-timeout SECONDS
                               fallback timeout before switching to mock mode
  --bag-arg ARG                append a raw argument to ros2 bag record
  --wait-before-record SECONDS wait before starting ros2 bag record (default: 3)
  --help                       show this message
EOF
}

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
    --skip-layout|--with-map|--viz-mock-mode)
      LAUNCH_ARGS+=("$1")
      shift
      ;;
    --topic-prefix|--viz-mock-fallback-timeout)
      LAUNCH_ARGS+=("$1" "${2:?missing value for $1}")
      shift 2
      ;;
    --bag-arg)
      BAG_EXTRA_ARGS+=("${2:?missing value for --bag-arg}")
      shift 2
      ;;
    --wait-before-record)
      WAIT_BEFORE_RECORD_S="${2:?missing value for --wait-before-record}"
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

if [[ ! -x "$SCRIPTS_DIR/start_foxglove_holoocean_ros.sh" ]]; then
  echo "[AUV][ERROR] launcher not found or not executable: $SCRIPTS_DIR/start_foxglove_holoocean_ros.sh"
  exit 1
fi

mkdir -p "$LOG_ROOT"
RUN_ID="$(timestamp)"
RUN_DIR="$LOG_ROOT/$RUN_ID"
BAG_DIR="$RUN_DIR/rosbag"
LAUNCH_LOG="$RUN_DIR/launcher.log"
BAG_LOG="$RUN_DIR/rosbag.log"
META_FILE="$RUN_DIR/metadata.txt"
mkdir -p "$RUN_DIR"

cleanup() {
  if [[ -n "${BAG_PID:-}" ]]; then
    echo "[AUV] stopping rosbag recorder ($BAG_PID)"
    kill -- -"$BAG_PID" >/dev/null 2>&1 || true
  fi
  if [[ -n "${LAUNCH_PID:-}" ]]; then
    echo "[AUV] stopping launcher ($LAUNCH_PID)"
    kill -- -"$LAUNCH_PID" >/dev/null 2>&1 || true
  fi
}

trap cleanup EXIT INT TERM

{
  echo "run_id=$RUN_ID"
  echo "created_at=$(date --iso-8601=seconds)"
  echo "root_dir=$ROOT_DIR"
  echo "sim_mode=$SIM_MODE"
  echo "brain_mode=$BRAIN_MODE"
  echo "launch_args=${LAUNCH_ARGS[*]:-}"
  echo "bag_extra_args=${BAG_EXTRA_ARGS[*]:-}"
  echo "git_head=$(cd "$ROOT_DIR" && git rev-parse HEAD)"
} > "$META_FILE"

echo "[AUV] experiment directory: $RUN_DIR"
echo "[AUV] starting integrated launcher..."
setsid bash "$SCRIPTS_DIR/start_foxglove_holoocean_ros.sh" \
  --sim-mode "$SIM_MODE" \
  --brain-mode "$BRAIN_MODE" \
  "${LAUNCH_ARGS[@]}" > >(tee -a "$LAUNCH_LOG") 2>&1 &
LAUNCH_PID=$!

echo "[AUV] waiting ${WAIT_BEFORE_RECORD_S}s before rosbag record..."
sleep "$WAIT_BEFORE_RECORD_S"

set +u
source /opt/ros/humble/setup.bash
if [[ -f "$BRAIN_DIR/install/setup.bash" ]]; then
  source "$BRAIN_DIR/install/setup.bash"
fi
set -u

echo "[AUV] recording rosbag to $BAG_DIR"
setsid ros2 bag record -a -o "$BAG_DIR" "${BAG_EXTRA_ARGS[@]}" > >(tee -a "$BAG_LOG") 2>&1 &
BAG_PID=$!

echo "[AUV] experiment running. Press Ctrl+C to stop and finalize logs."
wait "$LAUNCH_PID"
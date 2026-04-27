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
RECORD_BAG=true
BAG_STORAGE_ID="mcap"
RUN_DURATION_S=""
PROGRESS_PID=""

storage_backend_supported() {
  local storage_id="$1"
  local help_text

  help_text="$(ros2 bag record -h 2>&1 || true)"
  grep -Eq -- "-s \{[^}]*\b${storage_id}\b" <<<"$help_text"
}

run_progress_bar() {
  local total_s="$1"
  local elapsed_s=0
  local width=24

  while [[ "$elapsed_s" -le "$total_s" ]]; do
    local filled=$((elapsed_s * width / total_s))
    local empty=$((width - filled))
    local bar
    bar="$(printf '%0.s#' $(seq 1 "$filled" 2>/dev/null || true))$(printf '%0.s-' $(seq 1 "$empty" 2>/dev/null || true))"
    if [[ -z "$bar" ]]; then
      bar="$(printf '%*s' "$width" '')"
      bar="${bar// /-}"
    fi
    printf '\r[AUV] experiment progress [%s] %d/%ss' "$bar" "$elapsed_s" "$total_s"
    sleep 1
    elapsed_s=$((elapsed_s + 1))
  done
  printf '\n'
}

timestamp() {
  date +"%Y%m%d_%H%M%S"
}

usage() {
  cat <<'EOF'
Usage:
  ./start_experiment.sh [options]

Options:
  --sim-mode MODE              start_lin_sim.sh mode passed through to unified launcher
  --sim-backend BACKEND        simulation backend passed through to unified launcher
  --brain-mode MODE            start_lin_brain.sh mode passed through to unified launcher
  --skip-layout                skip Foxglove layout generation
  --bridge-backend BACKEND     forward backend to unified launcher
  --bridge-cfg PATH            explicit simulation bridge config path
  --sim-cfg PATH               explicit HoloOcean sim config path
  --protocol-control-mode-byte N
                               explicit protocol control mode byte for brain side
  --arbiter-profile            force protocol_udp arbiter profile on the brain side
  --topic-prefix PREFIX        apply a namespace prefix to generated Foxglove topics
  --with-map                   include the 3D map layer in generated layout
  --viz-mock-mode              force visualization bridge mock mode
  --viz-mock-fallback-timeout SECONDS
                               fallback timeout before switching to mock mode
  --bag-arg ARG                append a raw argument to ros2 bag record
  --record-bag                 enable rosbag recording (default)
  --no-record-bag              disable rosbag recording
  --bag-storage STORAGE_ID     rosbag storage backend (default: mcap)
  --wait-before-record SECONDS wait before starting ros2 bag record (default: 3)
  --duration SECONDS           auto-stop experiment after a fixed duration (recommend 120 for benchmark runs)
  --help                       show this message
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --sim-mode)
      SIM_MODE="${2:?missing value for --sim-mode}"
      shift 2
      ;;
    --sim-backend)
      LAUNCH_ARGS+=("--sim-backend" "${2:?missing value for --sim-backend}")
      shift 2
      ;;
    --brain-mode)
      BRAIN_MODE="${2:?missing value for --brain-mode}"
      shift 2
      ;;
    --skip-layout|--with-map|--viz-mock-mode|--arbiter-profile)
      LAUNCH_ARGS+=("$1")
      shift
      ;;
    --record-bag)
      RECORD_BAG=true
      shift
      ;;
    --no-record-bag)
      RECORD_BAG=false
      shift
      ;;
    --topic-prefix|--viz-mock-fallback-timeout|--bridge-backend|--bridge-cfg|--sim-cfg|--protocol-control-mode-byte)
      LAUNCH_ARGS+=("$1" "${2:?missing value for $1}")
      shift 2
      ;;
    --bag-arg)
      BAG_EXTRA_ARGS+=("${2:?missing value for --bag-arg}")
      shift 2
      ;;
    --bag-storage)
      BAG_STORAGE_ID="${2:?missing value for --bag-storage}"
      shift 2
      ;;
    --wait-before-record)
      WAIT_BEFORE_RECORD_S="${2:?missing value for --wait-before-record}"
      shift 2
      ;;
    --duration)
      RUN_DURATION_S="${2:?missing value for --duration}"
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

if [[ "$RECORD_BAG" == true ]]; then
  set +u
  source /opt/ros/humble/setup.bash
  if [[ -f "$BRAIN_DIR/install/setup.bash" ]]; then
    source "$BRAIN_DIR/install/setup.bash"
  fi
  set -u

  if ! storage_backend_supported "$BAG_STORAGE_ID"; then
    echo "[AUV][ERROR] rosbag storage backend '$BAG_STORAGE_ID' is not available in the current ROS 2 environment"
    echo "[AUV][ERROR] install the matching plugin or rerun with --bag-storage sqlite3 / --no-record-bag"
    exit 1
  fi
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
  if [[ -n "${PROGRESS_PID:-}" ]]; then
    kill "$PROGRESS_PID" >/dev/null 2>&1 || true
  fi
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
  echo "record_bag=$RECORD_BAG"
  echo "bag_storage_id=$BAG_STORAGE_ID"
  echo "run_duration_s=$RUN_DURATION_S"
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

if [[ "$RECORD_BAG" == true ]]; then
  echo "[AUV] waiting ${WAIT_BEFORE_RECORD_S}s before rosbag record..."
  sleep "$WAIT_BEFORE_RECORD_S"

  echo "[AUV] recording rosbag to $BAG_DIR with storage=$BAG_STORAGE_ID"
  setsid ros2 bag record -a -s "$BAG_STORAGE_ID" -o "$BAG_DIR" "${BAG_EXTRA_ARGS[@]}" > >(tee -a "$BAG_LOG") 2>&1 &
  BAG_PID=$!
else
  echo "[AUV] rosbag recording disabled"
fi

if [[ -n "$RUN_DURATION_S" ]]; then
  echo "[AUV] experiment running for ${RUN_DURATION_S}s"
  run_progress_bar "$RUN_DURATION_S" &
  PROGRESS_PID=$!
  sleep "$RUN_DURATION_S"
  kill "$PROGRESS_PID" >/dev/null 2>&1 || true
  wait "$PROGRESS_PID" >/dev/null 2>&1 || true
  echo "[AUV] requested duration reached, stopping experiment"
  exit 0
fi

echo "[AUV] experiment running. Press Ctrl+C to stop and finalize logs."
wait "$LAUNCH_PID"
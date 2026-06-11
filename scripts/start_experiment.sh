#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPTS_DIR="$ROOT_DIR/scripts"
BRAIN_DIR="$ROOT_DIR/brain_linux"
DATA_ROOT=$(python3 -c "import sys; sys.path.append('$ROOT_DIR'); from common.env_utils import get_data_root; print(get_data_root())")
LOG_ROOT="${AUV_EXPERIMENT_LOG_ROOT:-$DATA_ROOT/bags}"
SIM_MODE="both"
BRAIN_MODE="stack"
LAUNCH_ARGS=()
BAG_EXTRA_ARGS=()
WAIT_BEFORE_RECORD_S="${WAIT_BEFORE_RECORD_S:-3}"
RECORD_BAG=true
BAG_STORAGE_ID="mcap"
RUN_DURATION_S=""
PROGRESS_PID=""
SCENARIO_FILE=""
SCENARIO_SEED=""
MPC_MODE=""
BAG_FINALIZE_S="${BAG_FINALIZE_S:-30}"
AUTO_ACTIVATE=false
AUTO_ACTIVATE_RATE_HZ="${AUTO_ACTIVATE_RATE_HZ:-10}"
LEAN_BAG=true
LEAN_BAG_VISUAL=false
LEAN_BAG_VISUAL_RATE_HZ="${LEAN_BAG_VISUAL_RATE_HZ:-1.0}"

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
  --record-format FORMAT       alias for --bag-storage; one of {mcap, sqlite3}
  --wait-before-record SECONDS wait before starting ros2 bag record (default: 3)
  --bag-finalize SECONDS       grace period after SIGINT for bag finalize (default: 5)
  --auto-activate              start headless console emulator that periodically
                               sends 0xEE (JETSON_PROTOCOL) to unlock AutonomyGuard.
                               Required for unattended benchmarks; otherwise the
                               behavior tree stays in StandbyCheck and the bag
                               will be 0 byte. See docs/experiment/terrain_benchmark_log.md §3.2
  --auto-activate-rate HZ      heartbeat rate for the emulator (default: 10)
  --duration SECONDS           auto-stop experiment after a fixed duration (recommend 120 for benchmark runs)
  --scenario PATH              thesis scenario yaml (forwarded as AUV_SCENARIO_FILE env)
  --seed N                     thesis scenario seed (forwarded as AUV_SCENARIO_SEED env)
  --mpc-mode MODE              MPC mode {baseline,ua}; forwarded as AUV_MPC_MODE env
  --lean-bag                   exclude /auv/visual/.* from rosbag (drops ~97% of bag size)
  --lean-bag-visual            keep /auv/visual/history_trail at full rate, downsample
                               /auv/visual/seabed_mesh and /auv/visual/seabed_cloud
                               via scripts/visual_throttle.py (default 1 Hz)
                               implies --lean-bag (originals excluded; throttled copies kept)
  --lean-bag-visual-rate HZ    throttle rate for --lean-bag-visual (default: 1.0)
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
    --record-format)
      BAG_STORAGE_ID="${2:?missing value for --record-format}"
      shift 2
      ;;
    --wait-before-record)
      WAIT_BEFORE_RECORD_S="${2:?missing value for --wait-before-record}"
      shift 2
      ;;
    --bag-finalize)
      BAG_FINALIZE_S="${2:?missing value for --bag-finalize}"
      shift 2
      ;;
    --auto-activate)
      AUTO_ACTIVATE=true
      shift
      ;;
    --auto-activate-rate)
      AUTO_ACTIVATE_RATE_HZ="${2:?missing value for --auto-activate-rate}"
      shift 2
      ;;
    --duration)
      RUN_DURATION_S="${2:?missing value for --duration}"
      shift 2
      ;;
    --scenario)
      SCENARIO_FILE="${2:?missing value for --scenario}"
      shift 2
      ;;
    --seed)
      SCENARIO_SEED="${2:?missing value for --seed}"
      shift 2
      ;;
    --mpc-mode)
      MPC_MODE="${2:?missing value for --mpc-mode}"
      shift 2
      ;;
    --lean-bag)
      LEAN_BAG=true
      shift
      ;;
    --lean-bag-visual)
      LEAN_BAG_VISUAL=true
      shift
      ;;
    --lean-bag-visual-rate)
      LEAN_BAG_VISUAL_RATE_HZ="${2:?missing value for --lean-bag-visual-rate}"
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

# ---------------------------------------------------------------------------
# Pre-flight (timing contract v2.1, 2026-06-09):
# Two-layer split — main script stays lightweight (probe + daemon warm-up),
# heavy cleanup is an explicit operator action (scripts/preflight_clean.sh).
#
# Why split: contract v2 inlined the full sweep here, which also killed
# `_ros2_daemon`. Each subsequent launcher then paid a ~26s daemon cold-start
# before brain controllers came up — for 60s sweep runs that meant ~26s of
# the bag was uncontrolled drift, making the data incomparable to the n=1
# manual baseline (run 113311). See terrain_benchmark_log.md §6.7.6.
#
# v2.1 fast path (this script):
#   1. Probe stale state (port 8765 busy or stale brain/zenoh procs alive).
#      If detected → fail-fast and tell the operator to run preflight_clean.sh.
#      No process is killed, no shm is touched, no _ros2_daemon disturbed.
#   2. Warm up `_ros2_daemon` proactively so the first `ros2 bag record -a`
#      observes an up-to-date graph instead of cold-starting it.
#
# v2.1 slow path (operator action):
#   bash scripts/preflight_clean.sh   # see that script's header for details.
preflight_probe() {
  local pat
  pat="ros2 launch foxglove_bridge|/foxglove_bridge/foxglove_bridge"
  pat="$pat|run_zenoh_bridge\.py|sim_holoocean/apps/main\.py|mock_amd_server"
  pat="$pat|ros2 launch.*auv_stack|ros2 bag record"
  pat="$pat|zenoh_viz_bridge_node|zenoh_json_bridge_node"
  local stale_pids
  stale_pids=$(pgrep -f "$pat" 2>/dev/null || true)
  local port_busy=0
  if ! python3 -c "import socket,sys
s=socket.socket(); s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
try:
  s.bind(('0.0.0.0',8765)); s.close(); sys.exit(0)
except OSError:
  sys.exit(1)" 2>/dev/null; then
    port_busy=1
  fi
  if [[ -n "$stale_pids" || "$port_busy" == "1" ]]; then
    echo "[AUV][ERROR] pre-flight: stale state detected" >&2
    if [[ -n "$stale_pids" ]]; then
      echo "[AUV][ERROR]   stale pids: $(echo $stale_pids | tr '\n' ' ')" >&2
    fi
    if [[ "$port_busy" == "1" ]]; then
      echo "[AUV][ERROR]   port 8765 busy (foxglove_bridge would hit Bind Error)" >&2
    fi
    echo "[AUV][ERROR] please run: bash scripts/preflight_clean.sh   then re-run this command." >&2
    exit 2
  fi
  # Warm up ros2 daemon so the first bag recorder sees a fresh graph
  # without paying the ~26s cold-start cost. Idempotent: a no-op if already
  # running. Errors are tolerated (degrades gracefully to lazy start).
  # ROS env is sourced in a subshell so we don't leak it to the parent
  # (the main RECORD_BAG block below sources it again under controlled set -u).
  (
    set +u
    if [[ -f /opt/ros/humble/setup.bash ]]; then
      source /opt/ros/humble/setup.bash
      ros2 daemon start >/dev/null 2>&1 || true
    fi
  )
}
preflight_probe

# --lean-bag-visual implies --lean-bag (originals are excluded; throttled copies are recorded).
if [[ "$LEAN_BAG_VISUAL" == true ]]; then
  LEAN_BAG=true
fi

# --lean-bag: drop heavy /auv/visual/* topics from the bag, but keep
# /auv/visual/truth_marker (offline_ekf_benchmark needs it as ground truth).
# When --lean-bag-visual is also set, the throttled copies live on
# /auv/visual/*_throttled and are NOT matched by the exclude regex, so they get recorded.
if [[ "$LEAN_BAG" == true ]]; then
  if [[ "$LEAN_BAG_VISUAL" == true ]]; then
    # Keep history_trail at full rate; drop only mesh/cloud originals.
    # Throttled copies are on /auv/visual/seabed_(mesh|cloud)_throttled (not excluded).
    BAG_EXTRA_ARGS+=("--exclude" "^/auv/visual/seabed_(mesh|cloud)$")
  else
    # Negative lookahead exempts /auv/visual/truth_marker (std::regex ECMAScript).
    BAG_EXTRA_ARGS+=("--exclude" '^/auv/visual/(?!truth_marker$).*')
  fi
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
    echo "[AUV] stopping rosbag recorder ($BAG_PID), grace ${BAG_FINALIZE_S}s"
    # SIGINT to process group; if setsid was unavailable BAG_PID may not be a session leader,
    # so fall back to direct PID kill.
    kill -INT -- -"$BAG_PID" >/dev/null 2>&1 || kill -INT "$BAG_PID" >/dev/null 2>&1 || true
    # Wait up to BAG_FINALIZE_S for finalize message; poll for exit instead of fixed sleep.
    for _ in $(seq 1 "$BAG_FINALIZE_S"); do
      if ! kill -0 "$BAG_PID" 2>/dev/null; then
        break
      fi
      sleep 1
    done
    if kill -0 "$BAG_PID" 2>/dev/null; then
      echo "[AUV][WARN] bag recorder still alive after ${BAG_FINALIZE_S}s, escalating to SIGTERM"
      kill -TERM "$BAG_PID" >/dev/null 2>&1 || true
      sleep 1
    fi
  fi
  if [[ -n "${THROTTLE_PID:-}" ]]; then
    echo "[AUV] stopping visual_throttle ($THROTTLE_PID)"
    kill -INT "$THROTTLE_PID" >/dev/null 2>&1 || true
    for _ in 1 2 3; do
      if ! kill -0 "$THROTTLE_PID" 2>/dev/null; then break; fi
      sleep 1
    done
    if kill -0 "$THROTTLE_PID" 2>/dev/null; then
      kill -KILL "$THROTTLE_PID" >/dev/null 2>&1 || true
    fi
  fi
  if [[ -n "${LAUNCH_PID:-}" ]]; then
    echo "[AUV] stopping launcher ($LAUNCH_PID), grace ${BAG_FINALIZE_S}s"
    # SIGINT first → let the launcher's own cleanup propagate to its children.
    kill -INT -- -"$LAUNCH_PID" >/dev/null 2>&1 || kill -INT "$LAUNCH_PID" >/dev/null 2>&1 || true
    for _ in $(seq 1 "$BAG_FINALIZE_S"); do
      if ! kill -0 "$LAUNCH_PID" 2>/dev/null; then
        break
      fi
      sleep 1
    done
    if kill -0 "$LAUNCH_PID" 2>/dev/null; then
      echo "[AUV][WARN] launcher still alive after ${BAG_FINALIZE_S}s, escalating to SIGTERM on group"
      kill -TERM -- -"$LAUNCH_PID" >/dev/null 2>&1 || kill -TERM "$LAUNCH_PID" >/dev/null 2>&1 || true
      sleep 2
    fi
    if kill -0 "$LAUNCH_PID" 2>/dev/null; then
      echo "[AUV][WARN] launcher still alive, escalating to SIGKILL on group"
      kill -KILL -- -"$LAUNCH_PID" >/dev/null 2>&1 || kill -KILL "$LAUNCH_PID" >/dev/null 2>&1 || true
    fi
  fi
  # Last-resort sweep: any orphaned simulation children that escaped the group kill.
  pkill -KILL -f "run_zenoh_bridge.py" >/dev/null 2>&1 || true
  pkill -KILL -f "sim_holoocean/apps/main.py" >/dev/null 2>&1 || true
  pkill -KILL -f "mock_amd_server" >/dev/null 2>&1 || true
  if [[ -n "${EMU_PID:-}" ]]; then
    echo "[AUV] stopping auto_activate_emu ($EMU_PID)"
    kill -INT "$EMU_PID" >/dev/null 2>&1 || true
    for _ in 1 2 3; do
      if ! kill -0 "$EMU_PID" 2>/dev/null; then break; fi
      sleep 1
    done
    if kill -0 "$EMU_PID" 2>/dev/null; then
      kill -KILL "$EMU_PID" >/dev/null 2>&1 || true
    fi
  fi
  pkill -KILL -f "scripts/auto_activate_emu.py" >/dev/null 2>&1 || true
  pkill -KILL -f "scripts/visual_throttle.py" >/dev/null 2>&1 || true
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
  echo "bag_finalize_s=$BAG_FINALIZE_S"
  echo "auto_activate=$AUTO_ACTIVATE"
  echo "auto_activate_rate_hz=$AUTO_ACTIVATE_RATE_HZ"
  echo "lean_bag=$LEAN_BAG"
  echo "lean_bag_visual=$LEAN_BAG_VISUAL"
  echo "lean_bag_visual_rate_hz=$LEAN_BAG_VISUAL_RATE_HZ"
  echo "scenario_file=$SCENARIO_FILE"
  echo "scenario_seed=$SCENARIO_SEED"
  echo "mpc_mode=$MPC_MODE"
  echo "launch_args=${LAUNCH_ARGS[*]:-}"
  echo "bag_extra_args=${BAG_EXTRA_ARGS[*]:-}"
  echo "git_head=$(cd "$ROOT_DIR" && git rev-parse HEAD)"
} > "$META_FILE"

# Forward thesis-pipeline knobs as env vars consumed by mock_amd / mpc / scenario loader
if [[ -n "$SCENARIO_FILE" ]]; then
  export AUV_SCENARIO_FILE="$SCENARIO_FILE"
fi
if [[ -n "$SCENARIO_SEED" ]]; then
  export AUV_SCENARIO_SEED="$SCENARIO_SEED"
fi
if [[ -n "$MPC_MODE" ]]; then
  export AUV_MPC_MODE="$MPC_MODE"
fi

echo "[AUV] experiment directory: $RUN_DIR"
echo "[AUV] starting integrated launcher..."
setsid bash "$SCRIPTS_DIR/start_foxglove_holoocean_ros.sh" \
  --sim-mode "$SIM_MODE" \
  --brain-mode "$BRAIN_MODE" \
  "${LAUNCH_ARGS[@]}" > >(tee -a "$LAUNCH_LOG") 2>&1 &
LAUNCH_PID=$!

if [[ "$AUTO_ACTIVATE" == true ]]; then
  EMU_LOG="$RUN_DIR/auto_activate.log"
  echo "[AUV] starting auto_activate_emu (rate=${AUTO_ACTIVATE_RATE_HZ}Hz, log=$EMU_LOG)"
  # The emu must wait for the bridge's Zenoh router to be up. Give it a long
  # connect timeout; it retries internally.
  python3 "$SCRIPTS_DIR/auto_activate_emu.py" \
    --rate-hz "$AUTO_ACTIVATE_RATE_HZ" \
    --connect-timeout 60 \
    > "$EMU_LOG" 2>&1 &
  EMU_PID=$!
fi

if [[ "$LEAN_BAG_VISUAL" == true ]]; then
  THROTTLE_LOG="$RUN_DIR/visual_throttle.log"
  echo "[AUV] starting visual_throttle (rate=${LEAN_BAG_VISUAL_RATE_HZ}Hz, log=$THROTTLE_LOG)"
  python3 "$SCRIPTS_DIR/visual_throttle.py" \
    --rate-hz "$LEAN_BAG_VISUAL_RATE_HZ" \
    </dev/null > "$THROTTLE_LOG" 2>&1 &
  THROTTLE_PID=$!
fi

if [[ "$RECORD_BAG" == true ]]; then
  # Wait for brain stack to be ready before starting the bag recorder.
  # Why: launcher fork → sim → SIM_DELAY (10s) → colcon build (~15s) → ros2 launch
  # means /auv/control/mpc_cmd / raw_dr publishers don't appear until ~T+25s after
  # this script starts. If we record from T+3s, the first 22-26s of the bag are
  # uncontrolled drift (no MPC, no DR/EKF output) — analysis comparing 60s windows
  # against the n=1 manual baseline (run 113311, where brain was already warm)
  # becomes incoherent.
  #
  # Fix: poll `ros2 topic info /auv/control/mpc_cmd` until at least one publisher
  # is up (= brain controller node has spun and registered). Then start the bag
  # so its T0 is aligned with brain ready.
  #
  # Side-effect: total wall time of this script grows by ~25s, but the recorded
  # 60s duration is now entirely useful data. Timeout 90s gives slack for cold
  # colcon builds; if it expires we fall through (record anyway) so we don't
  # block on misconfiguration.
  local_brain_ready_topic="${BRAIN_READY_TOPIC:-/auv/control/mpc_cmd}"
  local_brain_ready_timeout="${BRAIN_READY_TIMEOUT_S:-90}"
  echo "[AUV] waiting up to ${local_brain_ready_timeout}s for brain ready (publisher on ${local_brain_ready_topic})..."
  brain_ready=0
  for i in $(seq 1 "$local_brain_ready_timeout"); do
    if ros2 topic info "$local_brain_ready_topic" 2>/dev/null | grep -qE "Publisher count: [1-9]"; then
      echo "[AUV] brain ready after ${i}s (publisher detected on ${local_brain_ready_topic})"
      brain_ready=1
      break
    fi
    sleep 1
  done
  if [[ "$brain_ready" == "0" ]]; then
    echo "[AUV][WARN] brain ready timeout (${local_brain_ready_timeout}s) — recording bag anyway; data may include warm-up drift"
  fi

  echo "[AUV] waiting ${WAIT_BEFORE_RECORD_S}s before rosbag record..."
  sleep "$WAIT_BEFORE_RECORD_S"

  echo "[AUV] recording rosbag to $BAG_DIR with storage=$BAG_STORAGE_ID"
  # NOTE(metadata.yaml fix, 2026-06-09):
  # 不要再用 `setsid ros2 bag record ... &`：在 `bash & + setsid` 组合下 setsid 会 fork,
  # `$!` 抓到的是已经退出的 setsid wrapper PID, cleanup() 的 `kill -INT $BAG_PID` 因而
  # 永远送达不了真实 ros2 bag record 进程, metadata.yaml 从未被 finalize。
  # 直接以 `&` 启动, $! 即真实进程 PID; 同时 stdin 重定向到 /dev/null, 避免后台进程读
  # 控制终端时被 SIGTTIN 挂起 (这才是原作者用 setsid 的真实动机)。
  ros2 bag record -a -s "$BAG_STORAGE_ID" -o "$BAG_DIR" "${BAG_EXTRA_ARGS[@]}" \
    </dev/null >>"$BAG_LOG" 2>&1 &
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
  echo "[AUV] requested duration reached, finalizing via cleanup trap"
  # NOTE(thesis Step 0 / S1 fix): 不再 exit 0；改为 return 让 trap EXIT 触发 cleanup()，
  # 避免 bag recorder 未收到 SIGINT、MCAP 文件未 finalize 的问题。
  exit 0
fi

echo "[AUV] experiment running. Press Ctrl+C to stop and finalize logs."
wait "$LAUNCH_PID"

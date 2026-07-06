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
BAG_TOPICS=()
BAG_PROFILE=""
SIM_BACKEND_OVERRIDE="${AUV_SIM_BACKEND:-}"
BRIDGE_BACKEND_OVERRIDE="${AUV_BRIDGE_BACKEND:-}"
CLI_BRIDGE_CFG_OVERRIDE=""
SIM_TIME_SCALE=""
TEMP_BRIDGE_CFG=""
LAUNCH_OUTPUT_MODE="${AUV_LAUNCH_OUTPUT_MODE:-log}"
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
BRAIN_READY_TOPIC="${BRAIN_READY_TOPIC:-}"
BRAIN_READY_TIMEOUT_S="${BRAIN_READY_TIMEOUT_S:-0}"
PREFLIGHT_CLEAN=false

storage_backend_supported() {
  local storage_id="$1"
  local help_text

  help_text="$(ros2 bag record -h 2>&1 || true)"
  grep -Eq -- "-s \{[^}]*\b${storage_id}\b" <<<"$help_text"
}

resolve_default_bridge_cfg() {
  local sim_backend="${1:-holoocean}"
  local bridge_backend="${2:-zenoh_json}"

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
  --sim-time-scale N           override simulation.time_scale in a per-run
                               temporary bridge config; useful for PVS sweeps
  --launcher-output MODE       launcher stdout mode: log or stream (default: log)
  --sim-cfg PATH               explicit HoloOcean sim config path
  --protocol-control-mode-byte N
                               explicit protocol control mode byte for brain side
  --arbiter-profile            force protocol_udp arbiter profile on the brain side
  --brain-arg ARG              append one raw argument forwarded to start_lin_brain.sh
  --topic-prefix PREFIX        apply a namespace prefix to generated Foxglove topics
  --with-map                   include the 3D map layer in generated layout
  --viz-mock-mode              force visualization bridge mock mode
  --viz-mock-fallback-timeout SECONDS
                               fallback timeout before switching to mock mode
  --bag-arg ARG                append a raw argument to ros2 bag record
  --bag-topic TOPIC            record a specific topic instead of recording all topics;
                               may be repeated
  --bag-profile PROFILE        predefined topic profile; currently supports
                               cable_acceptance
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
  --brain-ready-topic TOPIC    wait for a publisher on TOPIC before starting
                               rosbag; empty disables this wait
  --brain-ready-timeout SECONDS
                               max wait for --brain-ready-topic or
                               BRAIN_READY_TOPIC (default: 0 = disabled)
  --preflight-clean            run scripts/preflight_clean.sh before launching
                               sim/brain; recommended for PVS acceptance runs
  --duration SECONDS           auto-stop experiment after a fixed duration (recommend 120 for benchmark runs)
  --scenario PATH              thesis scenario yaml (forwarded as AUV_SCENARIO_FILE env)
  --seed N                     thesis scenario seed (forwarded as AUV_SCENARIO_SEED env)
  --mpc-mode MODE              MPC mode {baseline,ua}; forwarded as AUV_MPC_MODE env
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
      SIM_BACKEND_OVERRIDE="${2:?missing value for --sim-backend}"
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
    --bridge-backend)
      BRIDGE_BACKEND_OVERRIDE="${2:?missing value for --bridge-backend}"
      LAUNCH_ARGS+=("--bridge-backend" "$BRIDGE_BACKEND_OVERRIDE")
      shift 2
      ;;
    --bridge-cfg)
      CLI_BRIDGE_CFG_OVERRIDE="${2:?missing value for --bridge-cfg}"
      shift 2
      ;;
    --sim-time-scale)
      SIM_TIME_SCALE="${2:?missing value for --sim-time-scale}"
      shift 2
      ;;
    --launcher-output)
      LAUNCH_OUTPUT_MODE="${2:?missing value for --launcher-output}"
      shift 2
      ;;
    --topic-prefix|--viz-mock-fallback-timeout|--sim-cfg|--protocol-control-mode-byte)
      LAUNCH_ARGS+=("$1" "${2:?missing value for $1}")
      shift 2
      ;;
    --brain-arg)
      LAUNCH_ARGS+=("--brain-arg" "${2:?missing value for --brain-arg}")
      shift 2
      ;;
    --bag-arg)
      BAG_EXTRA_ARGS+=("${2:?missing value for --bag-arg}")
      shift 2
      ;;
    --bag-topic)
      BAG_TOPICS+=("${2:?missing value for --bag-topic}")
      shift 2
      ;;
    --bag-profile)
      BAG_PROFILE="${2:?missing value for --bag-profile}"
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
    --preflight-clean)
      PREFLIGHT_CLEAN=true
      shift
      ;;
    --auto-activate-rate)
      AUTO_ACTIVATE_RATE_HZ="${2:?missing value for --auto-activate-rate}"
      shift 2
      ;;
    --brain-ready-topic)
      BRAIN_READY_TOPIC="${2:?missing value for --brain-ready-topic}"
      shift 2
      ;;
    --brain-ready-timeout)
      BRAIN_READY_TIMEOUT_S="${2:?missing value for --brain-ready-timeout}"
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

case "$LAUNCH_OUTPUT_MODE" in
  log|stream)
    ;;
  *)
    echo "[AUV][ERROR] unknown --launcher-output mode: $LAUNCH_OUTPUT_MODE"
    echo "[AUV][ERROR] supported modes: log, stream"
    exit 1
    ;;
esac

if [[ -n "$BAG_PROFILE" ]]; then
  case "$BAG_PROFILE" in
    cable_acceptance)
      BAG_TOPICS+=(
        "/rosout"
        "/auv/state/filtered"
        "/auv/state/raw_dr"
        "/auv/sensors/magnetic"
        "/auv/mission_command"
        "/auv/cable/mission_command"
        "/auv/cable/tracking"
        "/auv/cable/diagnostics"
        "/auv/cable/industrial_ready"
        "/auv/cable/industrial_acceptance_pass"
        "/auv/cable/mode"
        "/auv/cable/acceptance_flags"
        "/auv/cable/status_text"
        "/auv/cable/cross_track_m"
        "/auv/cable/route_progress_m"
        "/auv/cable/burial_depth_m"
        "/auv/cable/burial_sigma_m"
        "/auv/cable/confidence"
        "/auv/cable/magnetic_snr_db"
        "/auv/cable/magnetic_confidence"
        "/auv/cable/dlt1278_summary"
        "/auv/cable/dlt1278_state"
        "/auv/cable/dlt1278_total_score"
        "/auv/control/setpoint"
        "/auv/arbiter/status"
      )
      ;;
    *)
      echo "[AUV][ERROR] unknown bag profile: $BAG_PROFILE"
      exit 1
      ;;
  esac
fi

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

if [[ "$PREFLIGHT_CLEAN" == true ]]; then
  echo "[AUV] running preflight cleanup before experiment..."
  bash "$SCRIPTS_DIR/preflight_clean.sh"
fi

mkdir -p "$LOG_ROOT"
RUN_ID="$(timestamp)"
RUN_DIR="$LOG_ROOT/$RUN_ID"
BAG_DIR="$RUN_DIR/rosbag"
LAUNCH_LOG="$RUN_DIR/launcher.log"
BAG_LOG="$RUN_DIR/rosbag.log"
META_FILE="$RUN_DIR/metadata.txt"
mkdir -p "$RUN_DIR"

if [[ -n "$SIM_TIME_SCALE" ]]; then
  python3 - "$SIM_TIME_SCALE" <<'PY'
import math
import sys

try:
    value = float(sys.argv[1])
except ValueError:
    print(f"[AUV][ERROR] --sim-time-scale must be numeric, got: {sys.argv[1]}", file=sys.stderr)
    sys.exit(2)
if not math.isfinite(value) or value <= 0.0:
    print(f"[AUV][ERROR] --sim-time-scale must be a positive finite number, got: {sys.argv[1]}", file=sys.stderr)
    sys.exit(2)
PY

  BASE_BRIDGE_CFG="${CLI_BRIDGE_CFG_OVERRIDE:-${AUV_BRIDGE_CFG:-}}"
  if [[ -z "$BASE_BRIDGE_CFG" ]]; then
    BASE_BRIDGE_CFG="$(resolve_default_bridge_cfg "${SIM_BACKEND_OVERRIDE:-holoocean}" "${BRIDGE_BACKEND_OVERRIDE:-zenoh_json}")"
  fi
  if [[ "$BASE_BRIDGE_CFG" != /* ]]; then
    BASE_BRIDGE_CFG="$ROOT_DIR/$BASE_BRIDGE_CFG"
  fi
  if [[ ! -f "$BASE_BRIDGE_CFG" ]]; then
    echo "[AUV][ERROR] bridge config for --sim-time-scale not found: $BASE_BRIDGE_CFG"
    exit 1
  fi

  TEMP_BRIDGE_CFG="$RUN_DIR/bridge_params.time_scale_${SIM_TIME_SCALE}.yaml"
  python3 - "$BASE_BRIDGE_CFG" "$TEMP_BRIDGE_CFG" "$SIM_TIME_SCALE" <<'PY'
from pathlib import Path
import sys

import yaml

src = Path(sys.argv[1])
dst = Path(sys.argv[2])
time_scale = float(sys.argv[3])

with src.open("r", encoding="utf-8") as f:
    cfg = yaml.safe_load(f) or {}
if not isinstance(cfg, dict):
    raise SystemExit(f"[AUV][ERROR] bridge config root must be a mapping: {src}")
simulation = cfg.setdefault("simulation", {})
if not isinstance(simulation, dict):
    raise SystemExit(f"[AUV][ERROR] bridge config simulation section must be a mapping: {src}")
simulation["time_scale"] = time_scale
dst.parent.mkdir(parents=True, exist_ok=True)
with dst.open("w", encoding="utf-8") as f:
    yaml.safe_dump(cfg, f, sort_keys=False, allow_unicode=True)
PY
  LAUNCH_ARGS+=("--bridge-cfg" "$TEMP_BRIDGE_CFG")
  echo "[AUV] simulation time_scale override: $SIM_TIME_SCALE"
  echo "[AUV] generated per-run bridge config: $TEMP_BRIDGE_CFG"
elif [[ -n "$CLI_BRIDGE_CFG_OVERRIDE" ]]; then
  LAUNCH_ARGS+=("--bridge-cfg" "$CLI_BRIDGE_CFG_OVERRIDE")
fi

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
}

trap cleanup EXIT INT TERM

{
  echo "run_id=$RUN_ID"
  echo "created_at=$(date --iso-8601=seconds)"
  echo "root_dir=$ROOT_DIR"
  echo "sim_mode=$SIM_MODE"
  echo "sim_backend_override=$SIM_BACKEND_OVERRIDE"
  echo "brain_mode=$BRAIN_MODE"
  echo "bridge_backend_override=$BRIDGE_BACKEND_OVERRIDE"
  echo "cli_bridge_cfg_override=$CLI_BRIDGE_CFG_OVERRIDE"
  echo "sim_time_scale=$SIM_TIME_SCALE"
  echo "temp_bridge_cfg=$TEMP_BRIDGE_CFG"
  echo "launcher_output_mode=$LAUNCH_OUTPUT_MODE"
  echo "record_bag=$RECORD_BAG"
  echo "bag_storage_id=$BAG_STORAGE_ID"
  echo "run_duration_s=$RUN_DURATION_S"
  echo "bag_finalize_s=$BAG_FINALIZE_S"
  echo "auto_activate=$AUTO_ACTIVATE"
  echo "auto_activate_rate_hz=$AUTO_ACTIVATE_RATE_HZ"
  echo "brain_ready_topic=$BRAIN_READY_TOPIC"
  echo "brain_ready_timeout_s=$BRAIN_READY_TIMEOUT_S"
  echo "preflight_clean=$PREFLIGHT_CLEAN"
  echo "bag_profile=$BAG_PROFILE"
  echo "bag_topics=${BAG_TOPICS[*]:-}"
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
export AUV_RUN_DIR="$RUN_DIR"
if [[ "$LAUNCH_OUTPUT_MODE" == "stream" ]]; then
  setsid bash "$SCRIPTS_DIR/start_foxglove_holoocean_ros.sh" \
    --sim-mode "$SIM_MODE" \
    --brain-mode "$BRAIN_MODE" \
    "${LAUNCH_ARGS[@]}" > >(tee -a "$LAUNCH_LOG") 2>&1 &
else
  echo "[AUV] launcher stdout redirected to $LAUNCH_LOG"
  setsid bash "$SCRIPTS_DIR/start_foxglove_holoocean_ros.sh" \
    --sim-mode "$SIM_MODE" \
    --brain-mode "$BRAIN_MODE" \
    "${LAUNCH_ARGS[@]}" > "$LAUNCH_LOG" 2>&1 &
fi
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

if [[ "$RECORD_BAG" == true ]]; then
  if [[ -n "$BRAIN_READY_TOPIC" && "${BRAIN_READY_TIMEOUT_S:-0}" != "0" ]]; then
    echo "[AUV] waiting for publisher on $BRAIN_READY_TOPIC before rosbag record (timeout=${BRAIN_READY_TIMEOUT_S}s)"
    ready=false
    for _ in $(seq 1 "$BRAIN_READY_TIMEOUT_S"); do
      if ros2 topic info "$BRAIN_READY_TOPIC" 2>/dev/null | grep -qE "Publisher count: [1-9]"; then
        ready=true
        break
      fi
      sleep 1
    done
    if [[ "$ready" != true ]]; then
      echo "[AUV][WARN] timed out waiting for publisher on $BRAIN_READY_TOPIC; starting rosbag anyway"
    else
      echo "[AUV] detected publisher on $BRAIN_READY_TOPIC"
    fi
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
  if [[ "${#BAG_TOPICS[@]}" -gt 0 ]]; then
    ros2 bag record "${BAG_TOPICS[@]}" -s "$BAG_STORAGE_ID" -o "$BAG_DIR" "${BAG_EXTRA_ARGS[@]}" \
      </dev/null >>"$BAG_LOG" 2>&1 &
  else
    ros2 bag record -a -s "$BAG_STORAGE_ID" -o "$BAG_DIR" "${BAG_EXTRA_ARGS[@]}" \
      </dev/null >>"$BAG_LOG" 2>&1 &
  fi
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

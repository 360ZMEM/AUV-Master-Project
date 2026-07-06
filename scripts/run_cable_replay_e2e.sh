#!/usr/bin/env bash
# Replay-driven end-to-end cable tracking run.
#
# Runs the REAL brain_linux cable_tracking_node (same-origin AuvMagTrackingPipeline)
# against recorded sensor/nav inputs from a prior source bag, with a chosen
# prior.pose_error config. Records the fresh /auv/cable/tracking output to a new
# MCAP. This is an OPEN-LOOP replay: the vehicle trajectory is fixed by the source
# recording, so distorted-prior setpoints do not re-steer the vehicle. It exercises
# the perception + PriorAlignmentState + DL/T-scoring chain under a warped prior.
#
# No live simulator (HoloOcean/PVS) is required or used.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

SOURCE_BAG=""
CONFIG_FILE=""
OUT_DIR=""
LABEL="replay"
PLAY_RATE="1.0"
export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-77}"

INPUT_TOPICS=(
  /auv/state/filtered
  /auv/sensors/magnetic
  /auv/mission_command
  /auv/cable/mission_command
  /auv/arbiter/status
)

usage() {
  cat <<EOF
Usage: $0 --source-bag PATH --config PATH --out-dir PATH [--label NAME] [--rate R]
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --source-bag) SOURCE_BAG="$2"; shift 2;;
    --config) CONFIG_FILE="$2"; shift 2;;
    --out-dir) OUT_DIR="$2"; shift 2;;
    --label) LABEL="$2"; shift 2;;
    --rate) PLAY_RATE="$2"; shift 2;;
    -h|--help) usage; exit 0;;
    *) echo "unknown arg: $1" >&2; usage; exit 1;;
  esac
done

[[ -n "$SOURCE_BAG" && -n "$CONFIG_FILE" && -n "$OUT_DIR" ]] || { usage; exit 1; }
[[ -e "$SOURCE_BAG" ]] || { echo "source bag not found: $SOURCE_BAG" >&2; exit 1; }
[[ -f "$CONFIG_FILE" ]] || { echo "config not found: $CONFIG_FILE" >&2; exit 1; }

mkdir -p "$OUT_DIR"
BAG_DIR="$OUT_DIR/rosbag"
rm -rf "$BAG_DIR"

set +u
# shellcheck disable=SC1091
source /opt/ros/humble/setup.bash
# shellcheck disable=SC1091
source "$ROOT_DIR/brain_linux/install/setup.bash"
set -u
export AUV_PROJECT_ROOT="$ROOT_DIR"

NODE_LOG="$OUT_DIR/node.log"
REC_LOG="$OUT_DIR/record.log"
PLAY_LOG="$OUT_DIR/play.log"

NODE_PGID=""
REC_PGID=""
kill_group() { # pgid signal
  local pgid="$1" sig="$2"
  [[ -n "$pgid" ]] && kill "-$sig" "-$pgid" 2>/dev/null || true
}
cleanup() {
  kill_group "$REC_PGID" INT
  kill_group "$NODE_PGID" INT
  sleep 3
  kill_group "$REC_PGID" KILL
  kill_group "$NODE_PGID" KILL
}
trap cleanup EXIT

echo "[replay] label=$LABEL rate=$PLAY_RATE domain=$ROS_DOMAIN_ID"
echo "[replay] source_bag=$SOURCE_BAG"
echo "[replay] config=$CONFIG_FILE"

# 1) Launch the real cable tracking node with the chosen config (own process group).
setsid ros2 run auv_decision_ros cable_tracking_node \
  --ros-args -p config_file:="$CONFIG_FILE" -p enabled:=true \
  >"$NODE_LOG" 2>&1 &
NODE_PID=$!
NODE_PGID=$(ps -o pgid= -p "$NODE_PID" | tr -d ' ')
sleep 5
kill -0 "$NODE_PID" 2>/dev/null || { echo "[replay] node died at startup"; cat "$NODE_LOG"; exit 1; }

# 2) Start recorder on the fresh output topic (own process group).
setsid ros2 bag record -s mcap -o "$BAG_DIR" /auv/cable/tracking \
  >"$REC_LOG" 2>&1 &
REC_PID=$!
REC_PGID=$(ps -o pgid= -p "$REC_PID" | tr -d ' ')
sleep 3

# 3) Replay ONLY the recorded input topics at the given rate (real-time by default).
ros2 bag play "$SOURCE_BAG" --rate "$PLAY_RATE" --topics "${INPUT_TOPICS[@]}" \
  >"$PLAY_LOG" 2>&1 || true

# 4) Let trailing messages flush, then stop recorder + node via trap.
sleep 3
echo "[replay] playback complete; finalizing bag"

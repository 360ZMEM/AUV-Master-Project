#!/usr/bin/env bash
# Direction A decoupled closed-loop cable tracking run.
#
# This harness closes the loop without PVS/HoloOcean dynamics:
#   decoupled_cable_sim_node -> odom + magnetic + mission
#   cable_tracking_node      -> production /auv/control/setpoint + diagnostics
#
# The recorded MCAP contains the vehicle trail, true cable marker, distorted
# prior marker, magnetic field, odometry, setpoints, and cable-tracking JSON so
# it can be opened directly in Foxglove for video capture.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CFG="${AUV_DIRECTION_A_CONFIG:-$ROOT_DIR/brain_linux/config/cable_tracking_direction_a.yaml}"
DURATION="${AUV_DIRECTION_A_DURATION:-90}"
OUT_ROOT="${AUV_DIRECTION_A_OUT:-$ROOT_DIR/results/cable_ops_report/direction_a_decoupled}"
RUN_ID="$(date +%Y%m%d_%H%M%S)"
RUN_DIR="$OUT_ROOT/$RUN_ID"

mkdir -p "$RUN_DIR"

set +u
source /opt/ros/humble/setup.bash
source "$ROOT_DIR/brain_linux/install/setup.bash"
set -u
export AUV_PROJECT_ROOT="$ROOT_DIR"

pids=()
cleanup() {
  for pid in "${pids[@]:-}"; do
    if kill -0 "$pid" >/dev/null 2>&1; then
      kill "$pid" >/dev/null 2>&1 || true
    fi
  done
  wait >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

echo "[direction-a] run_dir=$RUN_DIR"
echo "[direction-a] config=$CFG"

ros2 run auv_decision_ros decoupled_cable_sim_node \
  --ros-args -p "tracking_config_file:=$CFG" \
  >"$RUN_DIR/decoupled_sim.log" 2>&1 &
pids+=("$!")

ros2 run auv_decision_ros cable_tracking_node \
  --ros-args -p "config_file:=$CFG" \
  >"$RUN_DIR/cable_tracking.log" 2>&1 &
pids+=("$!")

sleep 4

set +e
timeout "$DURATION" ros2 bag record -s mcap -o "$RUN_DIR/rosbag" \
  /auv/state/filtered \
  /auv/sensors/magnetic \
  /auv/mission_command \
  /auv/cable/mission_command \
  /auv/control/setpoint \
  /auv/cable/tracking \
  /auv/cable/diagnostics \
  /auv/cable/cross_track_m \
  /auv/cable/route_progress_m \
  /auv/cable/confidence \
  /auv/cable/status_text \
  /auv/cable/industrial_ready \
  /auv/cable/industrial_acceptance_pass \
  /auv/visual/decoupled_true_cable \
  /auv/visual/decoupled_prior_cable \
  /auv/visual/decoupled_vehicle_trail \
  /auv/visual/decoupled_vehicle \
  >"$RUN_DIR/rosbag_record.log" 2>&1
rc=$?
set -e

bag_mcap="$(find "$RUN_DIR/rosbag" -name '*.mcap' -type f | head -n1 || true)"
status="ok"
if [[ "$rc" -ne 0 && "$rc" -ne 124 ]]; then
  status="record_exit_$rc"
fi
if [[ -z "$bag_mcap" ]]; then
  status="${status}_nobag"
fi

printf 'run_dir\t%s\nconfig\t%s\nbag_mcap\t%s\nstatus\t%s\n' \
  "$RUN_DIR" "$CFG" "${bag_mcap:-NONE}" "$status" >"$RUN_DIR/summary.tsv"

echo "[direction-a] bag=${bag_mcap:-NONE}"
echo "[direction-a] status=$status"
echo "[direction-a] summary=$RUN_DIR/summary.tsv"

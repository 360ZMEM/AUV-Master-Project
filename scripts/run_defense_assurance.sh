#!/usr/bin/env bash
set -euo pipefail

# Deterministic, physically consistent defense path:
# decoupled dynamics + Biot-Savart cable -> v2 adaptive cross scan -> FWHM
# -> burial estimate -> Track.  This is a digital-twin acceptance run, not a
# replacement for PVS integration or sea-trial evidence.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

DURATION_S=260
RECORD_BAG=true
CAPTURE_FWHM=true
while [[ $# -gt 0 ]]; do
  case "$1" in
    --duration) DURATION_S="${2:?missing value for --duration}"; shift 2 ;;
    --no-record-bag) RECORD_BAG=false; shift ;;
    --no-fwhm-analysis) CAPTURE_FWHM=false; shift ;;
    -h|--help)
      echo "Usage: scripts/run_defense_assurance.sh [--duration SECONDS] [--no-record-bag] [--no-fwhm-analysis]"
      exit 0 ;;
    *) echo "[assurance][ERROR] unknown argument: $1" >&2; exit 2 ;;
  esac
done

export AUV_PROJECT_ROOT="$ROOT_DIR"
export AUV_DATA_ROOT="${AUV_DATA_ROOT:-$ROOT_DIR/.auv_data}"
RUN_ID="$(date +%Y%m%d_%H%M%S)"
RUN_DIR="$AUV_DATA_ROOT/defense_assurance/$RUN_ID"
CFG="$ROOT_DIR/brain_linux/src/auv_cable_tracking_v2/config/cable_tracking_v2_defense.yaml"
mkdir -p "$RUN_DIR"

bash scripts/preflight_clean.sh
scripts/build_foxglove_layout.sh \
  --profile defense-perception-1366 \
  --output foxglove_layout_project/output/auv_defense_perception_1366.json \
  --temp-output tmp/foxglove_layout/auv_defense_perception_1366.json \
  --name "AUV 海缆巡检答辩保障" \
  --description "物理一致 FWHM、埋深质量门控与闭环跟踪" \
  --with-mock-topics

set +u
source /opt/ros/humble/setup.bash
source "$ROOT_DIR/brain_linux/install/setup.bash"
set -u

pids=()
cleanup() {
  for pid in "${pids[@]:-}"; do
    kill -TERM -- "-$pid" >/dev/null 2>&1 || kill -TERM "$pid" >/dev/null 2>&1 || true
  done
  sleep 1
  for pid in "${pids[@]:-}"; do
    kill -KILL -- "-$pid" >/dev/null 2>&1 || kill -KILL "$pid" >/dev/null 2>&1 || true
  done
  wait >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

setsid ros2 run auv_decision_ros decoupled_cable_sim_node --ros-args \
  -p "tracking_config_file:=$CFG" \
  -p frame_id:=world \
  -p base_link_frame_id:=base_link \
  -p initial_x_m:=0.0 -p initial_y_m:=7.5 -p initial_depth_m:=12.0 \
  -p true_cable_y_m:=0.0 -p true_cable_start_x_m:=-1000.0 \
  -p true_cable_end_x_m:=1000.0 -p true_cable_segment_m:=10.0 \
  -p vertical_separation_m:=4.0 -p altitude_m:=3.0 \
  -p current_amp_a:=600.0 -p magnetic_model:=infinite_straight_wire \
  -p mag_noise_mode:=none \
  >"$RUN_DIR/decoupled_sim.log" 2>&1 &
pids+=("$!")

setsid ros2 run auv_cable_tracking_v2 cable_tracking_v2_node --ros-args \
  -p "config_file:=$CFG" >"$RUN_DIR/cable_tracking_v2.log" 2>&1 &
pids+=("$!")

setsid ros2 run auv_viz_bridge zenoh_viz_bridge_node --ros-args \
  -p mock_mode:=true -p mock_fallback_timeout_s:=0.0 \
  >"$RUN_DIR/viz_bridge.log" 2>&1 &
pids+=("$!")

setsid ros2 launch foxglove_bridge foxglove_bridge_launch.xml \
  >"$RUN_DIR/foxglove_bridge.log" 2>&1 &
pids+=("$!")

sleep 4
if [[ "$CAPTURE_FWHM" == true ]]; then
  setsid /usr/bin/python3 tools/capture_fwhm_live_evidence.py \
    --duration "$DURATION_S" --output-dir "$RUN_DIR/fwhm_analysis" \
    >"$RUN_DIR/fwhm_capture.log" 2>&1 &
  pids+=("$!")
fi
if [[ "$RECORD_BAG" == true ]]; then
  setsid ros2 bag record -s mcap -o "$RUN_DIR/rosbag" \
    /auv/state/filtered /auv/sensors/magnetic /auv/sensors/altitude \
    /auv/control/setpoint /auv/cable/tracking /auv/cable/diagnostics \
    /auv/cable/mode /auv/cable/cross_track_m /auv/cable/burial_depth_m \
    /auv/cable/burial_sigma_m /auv/cable/confidence \
    /auv/cable/magnetic_strength_nt /auv/cable/fwhm_width_m \
    /auv/cable/fwhm_confidence /auv/cable/fwhm_validity \
    /auv/visual/decoupled_true_cable /auv/visual/decoupled_vehicle_trail \
    /auv/visual/search_pattern /auv/visual/cable_estimate \
    /auv/visual/burial_estimate /auv/visual/fwhm_span \
    >"$RUN_DIR/rosbag.log" 2>&1 &
  pids+=("$!")
fi

set +e
/usr/bin/python3 tools/monitor_defense_assurance.py \
  --duration "$DURATION_S" \
  --output "$RUN_DIR/assurance_report.json" \
  --expected-burial-m 1.0 --burial-tolerance-m 0.5 \
  | tee "$RUN_DIR/monitor.log"
monitor_rc=${PIPESTATUS[0]}
set -e

status="PASS"
if [[ "$monitor_rc" -ne 0 ]]; then status="FAIL"; fi
printf 'status\t%s\nrun_dir\t%s\nconfig\t%s\nlayout\t%s\nreport\t%s\n' \
  "$status" "$RUN_DIR" "$CFG" \
  "$ROOT_DIR/foxglove_layout_project/output/auv_defense_perception_1366.json" \
  "$RUN_DIR/assurance_report.json" >"$RUN_DIR/summary.tsv"
cat "$RUN_DIR/summary.tsv"
exit "$monitor_rc"

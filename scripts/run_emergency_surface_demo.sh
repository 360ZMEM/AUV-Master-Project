#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
export AUV_PROJECT_ROOT="$ROOT_DIR"
export AUV_DATA_ROOT="${AUV_DATA_ROOT:-$ROOT_DIR/.auv_data}"
RUN_ID="$(date +%Y%m%d_%H%M%S)"
RUN_DIR="$AUV_DATA_ROOT/emergency_surface/$RUN_ID"
CFG="$ROOT_DIR/brain_linux/src/auv_cable_tracking_v2/config/cable_tracking_v2_defense.yaml"
mkdir -p "$RUN_DIR"

bash scripts/preflight_clean.sh
scripts/build_foxglove_layout.sh \
  --profile defense-perception-1366 \
  --output foxglove_layout_project/output/auv_defense_perception_1366.json \
  --temp-output tmp/foxglove_layout/auv_defense_perception_1366.json \
  --name "AUV 海缆巡检答辩保障" \
  --description "巡检反演、上位机急停与紧急上浮" --with-mock-topics

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
  -p "tracking_config_file:=$CFG" -p frame_id:=world \
  -p initial_depth_m:=12.0 -p target_depth_m:=12.0 \
  -p true_cable_y_m:=0.0 -p vertical_separation_m:=4.0 \
  -p altitude_m:=3.0 -p magnetic_model:=infinite_straight_wire \
  >"$RUN_DIR/decoupled_sim.log" 2>&1 & pids+=("$!")
setsid ros2 run auv_cable_tracking_v2 cable_tracking_v2_node --ros-args \
  -p "config_file:=$CFG" >"$RUN_DIR/cable_tracking_v2.log" 2>&1 & pids+=("$!")
setsid ros2 run auv_viz_bridge zenoh_viz_bridge_node --ros-args \
  -p mock_mode:=true -p mock_fallback_timeout_s:=0.0 \
  >"$RUN_DIR/viz_bridge.log" 2>&1 & pids+=("$!")
setsid ros2 launch foxglove_bridge foxglove_bridge_launch.xml \
  >"$RUN_DIR/foxglove_bridge.log" 2>&1 & pids+=("$!")

sleep 4
setsid /usr/bin/python3 tools/console_estop_click_demo.py \
  --delay 12 --hold 35 \
  --config "$ROOT_DIR/console_soft/auv_console_pyside6/console_config.defense.yaml" \
  --screenshot "$RUN_DIR/console_estop.png" \
  >"$RUN_DIR/console.log" 2>&1 & pids+=("$!")

set +e
/usr/bin/python3 tools/monitor_emergency_surface.py --duration 60 \
  --output "$RUN_DIR/emergency_surface_report.json" | tee "$RUN_DIR/monitor.log"
rc=${PIPESTATUS[0]}
set -e
status=PASS; [[ "$rc" -eq 0 ]] || status=FAIL
printf 'status\t%s\nrun_dir\t%s\nreport\t%s\nconsole_screenshot\t%s\n' \
  "$status" "$RUN_DIR" "$RUN_DIR/emergency_surface_report.json" "$RUN_DIR/console_estop.png" \
  >"$RUN_DIR/summary.tsv"
cat "$RUN_DIR/summary.tsv"
# Keep publishers alive briefly so Foxglove receives and renders the stable
# SURFACED state after the monitor's hard acceptance condition is satisfied.
sleep 3
exit "$rc"

#!/usr/bin/env bash
# Linux-side ROS2 handoff for ADC-TMR measured magnetic noise replay.
#
# The script reuses the Direction A decoupled cable loop and only changes the
# magnetic observation noise mode.  Truth geometry, current, vehicle state, and
# controller configuration stay fixed across arms.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
EXP_DIR="$ROOT_DIR/real_experiments/mag_chain_noise_ros"
DATA_DIR="$EXP_DIR/data"
FIGURE_DIR="$EXP_DIR/figures"
THESIS_FIGURE_DIR="$ROOT_DIR/docs/thesis/figures/experiments/mag_chain_noise_ros"

DURATION="${AUV_MAG_NOISE_ROS_DURATION:-30}"
MODES="${AUV_MAG_NOISE_ROS_MODES:-none covariance_gaussian measured_replay}"
RUN_ID="${AUV_MAG_NOISE_ROS_RUN_ID:-$(date +%Y%m%d_%H%M%S)}"
RAW_ROOT="${AUV_MAG_NOISE_ROS_OUT:-${AUV_DATA_ROOT:-$ROOT_DIR/results}/mag_chain_noise_ros/$RUN_ID}"
NOISE_PROFILE="${AUV_MAG_NOISE_PROFILE_PATH:-real_experiments/mag_chain_noise/data/noise_profile.json}"
NOISE_SEED="${AUV_MAG_NOISE_SEED:-20260821}"
NOISE_SCALE="${AUV_MAG_NOISE_SCALE:-1.0}"
TRACKING_CONFIG="${AUV_DIRECTION_A_CONFIG:-$ROOT_DIR/brain_linux/config/cable_tracking_direction_a.yaml}"
ROS_DOMAIN_BASE="${AUV_MAG_NOISE_ROS_DOMAIN_BASE:-80}"

mkdir -p "$DATA_DIR" "$FIGURE_DIR" "$THESIS_FIGURE_DIR" "$RAW_ROOT"

set +u
source /opt/ros/humble/setup.bash
set -u

if [[ "${AUV_MAG_NOISE_ROS_SKIP_BUILD:-false}" != "true" ]]; then
  echo "[mag-chain-noise-ros] building auv_decision_ros"
  (cd "$ROOT_DIR/brain_linux" && colcon build --packages-select auv_decision_ros)
fi

RUN_INDEX="$DATA_DIR/run_index.csv"
printf 'mode,run_dir,bag_mcap,tracking_jsonl,noise_metadata_jsonl,status,extract_status,duration_s,seed,noise_scale,ros_domain_id\n' >"$RUN_INDEX"

echo "[mag-chain-noise-ros] raw_root=$RAW_ROOT"
echo "[mag-chain-noise-ros] duration_s=$DURATION"
echo "[mag-chain-noise-ros] modes=$MODES"

mode_index=0
for mode in $MODES; do
  ros_domain_id=$((ROS_DOMAIN_BASE + mode_index))
  mode_index=$((mode_index + 1))
  mode_root="$RAW_ROOT/$mode"
  mkdir -p "$mode_root"
  echo "[mag-chain-noise-ros] running mode=$mode ros_domain_id=$ros_domain_id"
  AUV_DIRECTION_A_DURATION="$DURATION" \
    AUV_DIRECTION_A_OUT="$mode_root" \
    AUV_DIRECTION_A_CONFIG="$TRACKING_CONFIG" \
    AUV_MAG_NOISE_MODE="$mode" \
    AUV_MAG_NOISE_PROFILE_PATH="$NOISE_PROFILE" \
    AUV_MAG_NOISE_SEED="$NOISE_SEED" \
    AUV_MAG_NOISE_SCALE="$NOISE_SCALE" \
    ROS_DOMAIN_ID="$ros_domain_id" \
    bash "$ROOT_DIR/scripts/run_direction_a_decoupled_cable_sim.sh" | tee "$mode_root/run_stdout.log"

  summary_file="$(find "$mode_root" -mindepth 2 -maxdepth 2 -name summary.tsv -type f | sort | tail -n1 || true)"
  run_dir=""
  bag_mcap=""
  status="no_summary"
  extract_status="not_run"
  tracking_jsonl=""
  noise_metadata_jsonl=""
  if [[ -n "$summary_file" ]]; then
    run_dir="$(dirname "$summary_file")"
    bag_mcap="$(awk -F'\t' '$1=="bag_mcap"{print $2}' "$summary_file")"
    status="$(awk -F'\t' '$1=="status"{print $2}' "$summary_file")"
    tracking_jsonl="$run_dir/tracking.jsonl"
    noise_metadata_jsonl="$run_dir/noise_metadata.jsonl"
    extract_status="ok"
    set +e
    python3 "$ROOT_DIR/tools/extract_cable_tracking_jsonl.py" \
      --bag "$run_dir/rosbag" \
      --output-jsonl "$tracking_jsonl" \
      --topic /auv/cable/tracking
    rc_tracking=$?
    python3 "$ROOT_DIR/tools/extract_cable_tracking_jsonl.py" \
      --bag "$run_dir/rosbag" \
      --output-jsonl "$noise_metadata_jsonl" \
      --topic /auv/sensors/magnetic_noise_metadata
    rc_noise=$?
    set -e
    if [[ "$rc_tracking" -ne 0 || "$rc_noise" -ne 0 ]]; then
      extract_status="tracking_${rc_tracking}_noise_${rc_noise}"
    fi
  fi
  printf '%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s\n' \
    "$mode" "$run_dir" "$bag_mcap" "$tracking_jsonl" "$noise_metadata_jsonl" \
    "$status" "$extract_status" "$DURATION" "$NOISE_SEED" "$NOISE_SCALE" "$ros_domain_id" >>"$RUN_INDEX"
done

python3 "$EXP_DIR/scripts/analyze_mag_noise_ros_run.py" \
  --run-index "$RUN_INDEX" \
  --output-dir "$EXP_DIR" \
  --figure-dir "$THESIS_FIGURE_DIR"

echo "[mag-chain-noise-ros] report=$EXP_DIR/report.md"
echo "[mag-chain-noise-ros] metrics=$EXP_DIR/metrics.json"

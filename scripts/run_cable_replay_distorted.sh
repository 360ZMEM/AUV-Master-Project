#!/usr/bin/env bash
# Distorted-prior runs only: mid (3) + heavy (3), one per distinct source bag.
# Clean regression already completed separately. Sequential to avoid DDS cross-talk.
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BASE="$ROOT_DIR/results/cable_ops_report/replay_e2e"
CFG="$BASE/_configs"
RATE="1.0"

declare -A BAGS=(
  [1]=/auv_data/bags/20260706_135331/rosbag/rosbag_0.mcap
  [2]=/auv_data/bags/20260706_135757/rosbag/rosbag_0.mcap
  [3]=/auv_data/bags/20260706_140156/rosbag/rosbag_0.mcap
)

run() {
  local tier="$1" label="$2" idx="$3"
  echo "=============== $label (tier=$tier bag=$idx) ==============="
  "$ROOT_DIR/scripts/run_cable_replay_one.sh" \
    --source-bag "${BAGS[$idx]}" \
    --config "$CFG/$tier.yaml" \
    --out-dir "$BASE/$label" \
    --label "$label" --rate "$RATE"
}

run mid mid_run1_bag1 1
run mid mid_run2_bag2 2
run mid mid_run3_bag3 3
run heavy heavy_run1_bag1 1
run heavy heavy_run2_bag2 2
run heavy heavy_run3_bag3 3

echo "ALL_DISTORTED_RUNS_DONE"

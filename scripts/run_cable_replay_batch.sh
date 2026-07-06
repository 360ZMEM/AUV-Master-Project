#!/usr/bin/env bash
# Batch: clean-prior regression (1) + mid (3) + heavy (3) replay-driven runs,
# each mid/heavy tier spanning the three distinct source bags (fresh1/2/3) so
# n=3 covers distinct recorded realizations. Runs are strictly sequential to
# avoid DDS cross-talk on the shared domain.
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

run() { # tier out-label bag-index
  local tier="$1" label="$2" idx="$3"
  echo "=============== $label (tier=$tier bag=$idx) ==============="
  "$ROOT_DIR/scripts/run_cable_replay_one.sh" \
    --source-bag "${BAGS[$idx]}" \
    --config "$CFG/$tier.yaml" \
    --out-dir "$BASE/$label" \
    --label "$label" --rate "$RATE"
}

# Step 3: clean-prior regression (single run on bag 1)
run clean clean_regression_bag1 1

# Step 4: mid tier x3 (distinct bags)
run mid mid_run1_bag1 1
run mid mid_run2_bag2 2
run mid mid_run3_bag3 3

# Step 4: heavy tier x3 (distinct bags)
run heavy heavy_run1_bag1 1
run heavy heavy_run2_bag2 2
run heavy heavy_run3_bag3 3

echo "ALL_RUNS_DONE"

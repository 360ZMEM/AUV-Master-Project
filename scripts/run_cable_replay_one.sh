#!/usr/bin/env bash
# One replay-driven end-to-end run + extract + DL/T report, matching the
# inspection-window / start-health parameters used by the original fresh1/2/3 runs.
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

SOURCE_BAG=""; CONFIG_FILE=""; OUT_DIR=""; LABEL="run"; RATE="1.0"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --source-bag) SOURCE_BAG="$2"; shift 2;;
    --config) CONFIG_FILE="$2"; shift 2;;
    --out-dir) OUT_DIR="$2"; shift 2;;
    --label) LABEL="$2"; shift 2;;
    --rate) RATE="$2"; shift 2;;
    *) echo "unknown arg: $1" >&2; exit 1;;
  esac
done

"$ROOT_DIR/scripts/run_cable_replay_e2e.sh" \
  --source-bag "$SOURCE_BAG" --config "$CONFIG_FILE" \
  --out-dir "$OUT_DIR" --label "$LABEL" --rate "$RATE"

set +u
source /opt/ros/humble/setup.bash
set -u

python3 "$ROOT_DIR/tools/extract_cable_tracking_jsonl.py" \
  --bag "$OUT_DIR/rosbag" \
  --output-jsonl "$OUT_DIR/tracking.jsonl" \
  --summary-json "$OUT_DIR/extract_summary.json"

python3 "$ROOT_DIR/tools/dlt1278_cable_report.py" \
  --tracking-jsonl "$OUT_DIR/tracking.jsonl" \
  --output-dir "$OUT_DIR" \
  --inspection-max-route-progress-m 50.0 \
  --inspection-max-abs-cross-track-m 2.0 \
  --inspection-require-burial-ready \
  --start-health-sample-count 30 \
  --start-max-route-progress-m 20.0 \
  --start-max-abs-cross-track-m 5.0

echo "[run_one] done: $OUT_DIR"

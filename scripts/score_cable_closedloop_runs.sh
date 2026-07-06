#!/usr/bin/env bash
# Score the closed-loop distorted-prior batch produced by
# run_cable_closedloop_distorted.sh. For each run in the manifest, extract the
# /auv/cable/tracking JSONL from its bag, run the DL/T 1278 report with the same
# inspection-window / start-health params used by the fresh acceptance runs, then
# aggregate per tier. Output lands under closedloop_e2e/<label>/ and _agg_<tier>/.
#
# Scoring params mirror scripts/run_cable_replay_one.sh so the correction-on
# batch is directly comparable to the correction-off baseline (*_prioroff dirs).
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_ROOT="$ROOT_DIR/results/cable_ops_report/closedloop_e2e"
MANIFEST="$OUT_ROOT/run_manifest.tsv"

set +u
source /opt/ros/humble/setup.bash
set -u

score_one() {
  local label="$1" bag_mcap="$2"
  local out_dir="$OUT_ROOT/$label"
  mkdir -p "$out_dir"
  echo "=============== scoring $label ==============="
  echo "[score] bag=$bag_mcap out=$out_dir"

  python3 "$ROOT_DIR/tools/extract_cable_tracking_jsonl.py" \
    --bag "$(dirname "$bag_mcap")" \
    --output-jsonl "$out_dir/tracking.jsonl" \
    --summary-json "$out_dir/extract_summary.json"

  python3 "$ROOT_DIR/tools/dlt1278_cable_report.py" \
    --tracking-jsonl "$out_dir/tracking.jsonl" \
    --output-dir "$out_dir" \
    --inspection-max-route-progress-m 50.0 \
    --inspection-max-abs-cross-track-m 2.0 \
    --inspection-require-burial-ready \
    --start-health-sample-count 30 \
    --start-max-route-progress-m 20.0 \
    --start-max-abs-cross-track-m 5.0
}

declare -A TIER_RUNS
# Skip header; iterate manifest rows.
while IFS=$'\t' read -r label tier run_dir bag_mcap status; do
  [[ "$label" == "label" ]] && continue
  [[ -z "$label" ]] && continue
  if [[ "$bag_mcap" == "NONE" || -z "$bag_mcap" ]]; then
    echo "[score] SKIP $label (no bag, status=$status)"
    continue
  fi
  score_one "$label" "$bag_mcap"
  TIER_RUNS[$tier]="${TIER_RUNS[$tier]:-} $OUT_ROOT/$label/inspection_summary.json"
done < "$MANIFEST"

for tier in "${!TIER_RUNS[@]}"; do
  echo "=============== aggregating tier=$tier ==============="
  # shellcheck disable=SC2086
  python3 "$ROOT_DIR/tools/aggregate_cable_acceptance_runs.py" \
    ${TIER_RUNS[$tier]} \
    --output-dir "$OUT_ROOT/_agg_$tier" \
    --min-runs 3 --min-pass-ratio 0.67
done

echo "ALL_CLOSEDLOOP_SCORING_DONE"

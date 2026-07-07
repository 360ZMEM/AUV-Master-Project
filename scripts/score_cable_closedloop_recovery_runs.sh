#!/usr/bin/env bash
# Score closed-loop distorted-prior runs with a two-stage recovery gate.
#
# Stage 1 (recovery) is not counted as DL/T inspection evidence.  Stage 2 starts
# only after the configured recovery gate is reached, then applies the normal
# inspection corridor and burial-ready requirements.  Outputs are written next
# to the original reports as <label>_recovery and _agg_<tier>_recovery.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_ROOT="$ROOT_DIR/results/cable_ops_report/closedloop_e2e"
MANIFEST="$OUT_ROOT/run_manifest.tsv"

RECOVERY_CROSS_TRACK_M="${AUV_RECOVERY_CROSS_TRACK_M:-3.4}"
INSPECTION_CROSS_TRACK_M="${AUV_INSPECTION_CROSS_TRACK_M:-$RECOVERY_CROSS_TRACK_M}"
MAX_ROUTE_OFFSET_TARGET_M="${AUV_ACCEPTANCE_MAX_ROUTE_OFFSET_M:-$INSPECTION_CROSS_TRACK_M}"
MEAN_ROUTE_OFFSET_TARGET_M="${AUV_ACCEPTANCE_MEAN_ROUTE_OFFSET_M:-2.5}"
MAX_BURIAL_SIGMA_M="${AUV_ACCEPTANCE_MAX_BURIAL_SIGMA_M:-1.2}"
RECOVERY_CONSECUTIVE="${AUV_RECOVERY_CONSECUTIVE:-20}"
INSPECTION_LENGTH_M="${AUV_RECOVERY_INSPECTION_LENGTH_M:-50.0}"

set +u
source /opt/ros/humble/setup.bash
set -u

score_one() {
  local label="$1" bag_mcap="$2"
  local out_dir="$OUT_ROOT/${label}_recovery"
  mkdir -p "$out_dir"
  echo "=============== recovery scoring $label ==============="
  echo "[score] bag=$bag_mcap out=$out_dir"

  python3 "$ROOT_DIR/tools/extract_cable_tracking_jsonl.py" \
    --bag "$(dirname "$bag_mcap")" \
    --output-jsonl "$out_dir/tracking.jsonl" \
    --summary-json "$out_dir/extract_summary.json"

  python3 "$ROOT_DIR/tools/dlt1278_cable_report.py" \
    --tracking-jsonl "$out_dir/tracking.jsonl" \
    --output-dir "$out_dir" \
    --inspection-max-route-progress-m "$INSPECTION_LENGTH_M" \
    --inspection-route-progress-origin recovery \
    --inspection-max-abs-cross-track-m "$INSPECTION_CROSS_TRACK_M" \
    --inspection-require-burial-ready \
    --recovery-start-max-abs-cross-track-m "$RECOVERY_CROSS_TRACK_M" \
    --recovery-start-require-burial-ready \
    --recovery-start-consecutive-samples "$RECOVERY_CONSECUTIVE" \
    --max-route-offset-target-m "$MAX_ROUTE_OFFSET_TARGET_M" \
    --mean-route-offset-target-m "$MEAN_ROUTE_OFFSET_TARGET_M" \
    --max-burial-sigma-m "$MAX_BURIAL_SIGMA_M" \
    --start-health-sample-count 0
}

declare -A TIER_RUNS
while IFS=$'\t' read -r label tier run_dir bag_mcap status; do
  [[ "$label" == "label" ]] && continue
  [[ -z "$label" ]] && continue
  if [[ "$bag_mcap" == "NONE" || -z "$bag_mcap" ]]; then
    echo "[score] SKIP $label (no bag, status=$status)"
    continue
  fi
  score_one "$label" "$bag_mcap"
  TIER_RUNS[$tier]="${TIER_RUNS[$tier]:-} $OUT_ROOT/${label}_recovery/inspection_summary.json"
done < "$MANIFEST"

for tier in "${!TIER_RUNS[@]}"; do
  echo "=============== recovery aggregating tier=$tier ==============="
  # shellcheck disable=SC2086
  python3 "$ROOT_DIR/tools/aggregate_cable_acceptance_runs.py" \
    ${TIER_RUNS[$tier]} \
    --output-dir "$OUT_ROOT/_agg_${tier}_recovery" \
    --min-runs 3 --min-pass-ratio 0.67
done

echo "ALL_CLOSEDLOOP_RECOVERY_SCORING_DONE"

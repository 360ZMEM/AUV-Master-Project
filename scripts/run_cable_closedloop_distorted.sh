#!/usr/bin/env bash
# Closed-loop distorted-prior fresh runs (PVS backend): mid (3) + heavy (3).
#
# Unlike the open-loop replay harness (run_cable_replay_distorted.sh), this drives
# a full PVS closed-loop fresh run per tier: the distorted prior is injected via
# cable_tracking_config, the brain re-steers through /auv/control/setpoint, so the
# online PriorAlignmentState correction is actually exercised. This is the evidence
# needed to test whether closed-loop recovery absorbs the cross-track offset.
#
# Canonical on-disk config is untouched; only the throwaway _configs/{mid,heavy}.yaml
# variants (prior.pose_error enabled) are pointed at. Runs are sequential to avoid
# DDS/UDP cross-talk. AUV_SKIP_BRAIN_BUILD=1 reuses the already-built brain install.
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BASE="$ROOT_DIR/results/cable_ops_report/replay_e2e"
CFG="$BASE/_configs"
OUT_ROOT="$ROOT_DIR/results/cable_ops_report/closedloop_e2e"
MANIFEST="$OUT_ROOT/run_manifest.tsv"
DURATION="${AUV_CL_DURATION:-140}"
TIMEOUT_S="${AUV_CL_TIMEOUT:-240}"

mkdir -p "$OUT_ROOT"
: > "$MANIFEST"
printf 'label\ttier\trun_dir\tbag_mcap\tstatus\n' >> "$MANIFEST"

run() {
  local tier="$1" label="$2"
  local cfg="$CFG/$tier.yaml"
  local log="$OUT_ROOT/$label.launch.log"
  echo "=============== $label (tier=$tier duration=${DURATION}s) ==============="
  echo "[harness] cable_tracking_config=$cfg"

  set +e
  AUV_SKIP_BRAIN_BUILD=1 AUV_LAUNCH_OUTPUT_MODE=log timeout "$TIMEOUT_S" \
    bash "$ROOT_DIR/scripts/start_experiment.sh" \
      --sim-backend pvs --bridge-backend protocol_udp --arbiter-profile \
      --protocol-control-mode-byte 238 --skip-layout --preflight-clean \
      --bag-profile cable_acceptance --bag-storage mcap --bag-finalize 18 \
      --duration "$DURATION" \
      --brain-arg enable_cable_tracking:=true \
      --brain-arg enable_cable_mission_autostart:=true \
      --brain-arg "cable_tracking_config:=$cfg" \
      >"$log" 2>&1
  local rc=$?
  set -e

  local run_dir
  run_dir="$(grep -oE '/auv_data/bags/[0-9_]+' "$log" | head -n1 || true)"
  local bag_mcap=""
  if [[ -n "$run_dir" ]]; then
    bag_mcap="$(ls "$run_dir"/rosbag/*.mcap 2>/dev/null | head -n1 || true)"
  fi
  local status="ok"
  [[ "$rc" -ne 0 ]] && status="exit_$rc"
  [[ -z "$bag_mcap" ]] && status="${status}_nobag"

  printf '%s\t%s\t%s\t%s\t%s\n' "$label" "$tier" "${run_dir:-NONE}" "${bag_mcap:-NONE}" "$status" >> "$MANIFEST"
  echo "[harness] $label -> run_dir=${run_dir:-NONE} bag=${bag_mcap:-NONE} status=$status (rc=$rc)"
  # Settle time between runs so preflight cleanup finds a quiet system.
  sleep 8
}

run mid   cl_mid_run1
run mid   cl_mid_run2
run mid   cl_mid_run3
run heavy cl_heavy_run1
run heavy cl_heavy_run2
run heavy cl_heavy_run3

echo "ALL_CLOSEDLOOP_DISTORTED_RUNS_DONE"
cat "$MANIFEST"

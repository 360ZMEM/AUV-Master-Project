#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRAIN_DIR="$ROOT_DIR/brain_linux"

LOG_ROOT="${AUV_TRANSPARENCY_BENCHMARK_ROOT:-$ROOT_DIR/log/transparency_benchmarks}"
WARMUP_S="${WARMUP_S:-6}"
RUN_DURATION_S="${RUN_DURATION_S:-20}"
BARE_BAG_ARGS=()

usage() {
  cat <<'EOF'
Usage:
  ./scripts/run_transparency_level_benchmark.sh [options]

Options:
  --output-root PATH     Root directory for generated bags and reports
  --warmup SECONDS       Seconds to wait after launch before starting rosbag record
  --duration SECONDS     Recording duration per level
  --bag-arg ARG          Extra argument forwarded to ros2 bag record (repeatable)
  -h, --help             Show this help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --output-root)
      LOG_ROOT="${2:?missing value for --output-root}"
      shift 2
      ;;
    --warmup)
      WARMUP_S="${2:?missing value for --warmup}"
      shift 2
      ;;
    --duration)
      RUN_DURATION_S="${2:?missing value for --duration}"
      shift 2
      ;;
    --bag-arg)
      BARE_BAG_ARGS+=("${2:?missing value for --bag-arg}")
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "[AUV][ERROR] unknown argument: $1"
      usage
      exit 1
      ;;
  esac
done

if [[ ! -f "$BRAIN_DIR/install/setup.bash" ]]; then
  echo "[AUV][ERROR] brain workspace is not built: $BRAIN_DIR/install/setup.bash missing"
  exit 1
fi

set +u
source /opt/ros/humble/setup.bash
source "$BRAIN_DIR/install/setup.bash"
set -u

mkdir -p "$LOG_ROOT"
RUN_ID="$(date +%Y%m%d_%H%M%S)"
RUN_DIR="$LOG_ROOT/$RUN_ID"
mkdir -p "$RUN_DIR"

REPORT_FILE="$RUN_DIR/report.md"
SUMMARY_CSV="$RUN_DIR/summary.csv"
printf '# Transparency Benchmark Report\n\n' > "$REPORT_FILE"
printf 'debug_level,level_name,mcap_files,speed_target_mean_mps\n' > "$SUMMARY_CSV"
printf 'run_id: %s\n\n' "$RUN_ID" >> "$REPORT_FILE"

cleanup() {
  if [[ -n "${BAG_PID:-}" ]]; then
    kill -- -"$BAG_PID" >/dev/null 2>&1 || true
  fi
  if [[ -n "${LAUNCH_PID:-}" ]]; then
    kill -- -"$LAUNCH_PID" >/dev/null 2>&1 || true
  fi
}

trap cleanup EXIT INT TERM

level_names=("L1 Hold" "L2 AnalyticalPath" "L3 Full Mission")
debug_levels=(1 2 3)

for idx in "${!debug_levels[@]}"; do
  debug_level="${debug_levels[$idx]}"
  level_name="${level_names[$idx]}"
  level_dir="$RUN_DIR/level_${debug_level}"
  bag_dir="$level_dir/rosbag"
  analysis_dir="$level_dir/analysis"
  launch_log="$level_dir/launch.log"
  bag_log="$level_dir/rosbag.log"
  analyze_log="$level_dir/analyze.log"

  mkdir -p "$level_dir"

  echo "[AUV] starting integrated stack for $level_name (debug_level=$debug_level)"
  setsid bash "$ROOT_DIR/scripts/start_foxglove_holoocean_ros.sh" \
    --skip-layout \
    --sim-mode both \
    --brain-mode stack \
    --brain-arg "debug_level:=$debug_level" \
    --brain-arg "mock_amd_timeout_s:=5.0" \
    --brain-arg "transition_threshold_m:=2.0" \
    --brain-arg "transition_duration_s:=3.0" \
    > >(tee "$launch_log") 2>&1 &
  LAUNCH_PID=$!

  echo "[AUV] waiting for stack startup and /auv/state/filtered to become available..."
  sleep "$WARMUP_S"

  # Wait for /auv/state/filtered to be published with a timeout
  echo "[AUV] checking for /auv/state/filtered publisher..."
  wait_timeout=30
  wait_start=$(date +%s)
  while true; do
    current_time=$(date +%s)
    elapsed=$((current_time - wait_start))
    
    if [[ $elapsed -ge $wait_timeout ]]; then
      echo "[AUV][WARN] timeout waiting for /auv/state/filtered after ${wait_timeout}s"
      echo "[AUV][WARN] proceeding with recording anyway, but diagnostics may be incomplete"
      break
    fi

    # Check if topic is being published
    if timeout 2 ros2 topic list | grep -q "/auv/state/filtered"; then
      # Verify there's at least one publisher
      pub_count=$(timeout 2 ros2 topic info /auv/state/filtered 2>/dev/null | grep -c "Publisher count:" || echo "0")
      if [[ "$pub_count" -gt 0 ]]; then
        # Wait a bit longer to ensure first messages are published
        echo "[AUV] detected /auv/state/filtered publisher, waiting 2s for first messages..."
        sleep 2
        echo "[AUV] /auv/state/filtered is active, starting recording"
        break
      fi
    fi

    echo "[AUV] still waiting for /auv/state/filtered... (${elapsed}s/${wait_timeout}s)"
    sleep 1
  done

  echo "[AUV] recording rosbag for $level_name -> $bag_dir"
  setsid ros2 bag record -a -s mcap -o "$bag_dir" "${BARE_BAG_ARGS[@]}" \
    > >(tee "$bag_log") 2>&1 &
  BAG_PID=$!

  sleep "$RUN_DURATION_S"

  kill -- -"$BAG_PID" >/dev/null 2>&1 || true
  wait "$BAG_PID" >/dev/null 2>&1 || true
  BAG_PID=""

  kill -- -"$LAUNCH_PID" >/dev/null 2>&1 || true
  wait "$LAUNCH_PID" >/dev/null 2>&1 || true
  LAUNCH_PID=""

  if [[ -x /usr/bin/python3 ]]; then
    if /usr/bin/python3 "$ROOT_DIR/tools/analyze_bag.py" "$bag_dir" --stats-only --output-dir "$analysis_dir" > "$analyze_log" 2>&1; then
      echo "[AUV] analysis complete for $level_name"
    else
      echo "[AUV][WARN] analysis failed for $level_name, see $analyze_log"
    fi
  fi

  bag_count="$(find "$bag_dir" -maxdepth 1 -name '*.mcap' | wc -l | tr -d ' ')"
  summary_csv="$analysis_dir/summary_statistics.csv"
  if [[ -f "$summary_csv" ]]; then
    level_summary="$RUN_DIR/level_${debug_level}_summary.csv"
    cp "$summary_csv" "$level_summary"
    target_speed_mean="$(/usr/bin/python3 - "$summary_csv" <<'PY'
import csv, sys
path = sys.argv[1]
with open(path, newline='', encoding='utf-8') as handle:
    rows = dict(csv.reader(handle))
print(rows.get('speed_target_mean_mps', 'nan'))
PY
    )"
  else
    level_summary="$RUN_DIR/level_${debug_level}_summary.csv"
    printf 'metric,value\nlevel,%s\n' "$debug_level" > "$level_summary"
    target_speed_mean="nan"
  fi

  estimated_samples="nan"
  diagnostics_samples="nan"
  if [[ -f "$level_summary" ]]; then
    estimated_samples="$(/usr/bin/python3 - "$level_summary" <<'PY'
import csv, sys
path = sys.argv[1]
with open(path, newline='', encoding='utf-8') as handle:
    rows = dict(csv.reader(handle))
print(rows.get('estimated_sample_count', 'nan'))
PY
    )"
    diagnostics_samples="$(/usr/bin/python3 - "$level_summary" <<'PY'
import csv, sys
path = sys.argv[1]
with open(path, newline='', encoding='utf-8') as handle:
    rows = dict(csv.reader(handle))
print(rows.get('diagnostics_sample_count', 'nan'))
PY
    )"
  fi

  {
    echo "## $level_name"
    echo "- debug_level: $debug_level"
    echo "- bag_dir: $bag_dir"
    echo "- mcap_files: $bag_count"
    echo "- estimated_samples: $estimated_samples"
    echo "- diagnostics_samples: $diagnostics_samples"
    echo "- summary_csv: $level_summary"
    echo "- speed_target_mean_mps: ${target_speed_mean}"
    echo
  } >> "$REPORT_FILE"

  printf '%s,%s,%s,%s\n' "$debug_level" "$level_name" "$bag_count" "$target_speed_mean" >> "$SUMMARY_CSV"
done

echo "[AUV] benchmark complete"
echo "[AUV] report: $REPORT_FILE"
echo "[AUV] summary: $SUMMARY_CSV"

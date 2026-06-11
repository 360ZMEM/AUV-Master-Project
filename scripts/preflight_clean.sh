#!/usr/bin/env bash
# Preflight cleanup for AUV experiment harness (timing contract v2.1, 2026-06-09).
#
# Run this manually before a fresh batch of experiments when the previous run
# crashed / aborted, or when start_experiment.sh fails fast with a "stale
# state" error. On a clean machine it is a no-op.
#
# What it sweeps (in order):
#
#   1. Process leakage (12 patterns):
#      - foxglove_bridge holds port 8765 → next launcher trips Bind Error →
#        launcher's `wait -n` returns → whole sim/bridge/brain stack is torn
#        down before brain finishes colcon build, so /auv/sensors/{imu,dvl,
#        depth} are never published and the bag is unusable.
#      - zenoh_viz_bridge_node / zenoh_json_bridge_node persist their zenoh
#        peer sessions, so the new bridge gets duplicate publishers.
#      - _ros2_daemon (rclpy._daemon) caches the previous run's node graph;
#        a stale cache makes `ros2 bag record -a` inherit the old graph and
#        the recorder silently writes nothing.
#
#   2. DDS / zenoh shared memory:
#      - /dev/shm/fastrtps_* and /dev/shm/sem.fastrtps_* segments from killed
#        nodes block FastRTPS discovery on the new run.
#      - /dev/shm/*.zenoh segments do the same for zenoh.
#
#   3. Final port probe (8765) → confirm the next start_experiment.sh will
#      not hit a foxglove_bridge Bind Error.
#
# This script is idempotent: running it twice in a row is safe.
#
# Exit codes:
#   0  cleanup ok (or nothing to clean)
#   2  port 8765 still busy after sweep — manual intervention needed
#
# Why it is no longer inlined into start_experiment.sh (v2 → v2.1):
# The inlined v2 also killed _ros2_daemon, which forced every subsequent
# launcher to pay a ~26s daemon cold-start before brain controllers came up.
# Splitting cleanup into an explicit operator action lets start_experiment.sh
# warm up the daemon proactively (fast path) and only fail fast when a real
# stale state is detected (slow path → operator runs this script).
#
# See: docs/internals/11_experiment_state_machine.md §6.4
#      docs/experiment/terrain_benchmark_log.md §6.7

set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  bash scripts/preflight_clean.sh [--quiet]

Run before a fresh batch of experiments to sweep stale processes, DDS/zenoh
shared-memory segments, and to free the foxglove_bridge port (8765).

Options:
  --quiet     suppress informational output (only print errors)
  -h|--help   show this message
EOF
}

QUIET=false
while [[ $# -gt 0 ]]; do
  case "$1" in
    --quiet) QUIET=true; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "[preflight][ERROR] unknown argument: $1" >&2; usage; exit 1 ;;
  esac
done

log() {
  if [[ "$QUIET" != true ]]; then
    echo "$@"
  fi
}

# --- 1. Process sweep ------------------------------------------------------
PAT="ros2 launch foxglove_bridge|/foxglove_bridge/foxglove_bridge"
PAT="$PAT|run_zenoh_bridge\.py|sim_holoocean/apps/main\.py|mock_amd_server"
PAT="$PAT|ros2 launch.*auv_stack|ros2 bag record"
PAT="$PAT|scripts/auto_activate_emu\.py|scripts/visual_throttle\.py"
PAT="$PAT|zenoh_viz_bridge_node|zenoh_json_bridge_node"
PAT="$PAT|_ros2_daemon|rclpy\._daemon"

PIDS=$(pgrep -f "$PAT" 2>/dev/null || true)
if [[ -n "$PIDS" ]]; then
  log "[preflight] stale processes found, sweeping (pids: $(echo $PIDS | tr '\n' ' '))"
  pkill -INT  -f "$PAT" 2>/dev/null || true
  sleep 2
  pkill -KILL -f "$PAT" 2>/dev/null || true
  sleep 1
else
  log "[preflight] no stale processes"
fi

# --- 2. Shared-memory sweep -----------------------------------------------
SHM_REMOVED=$(python3 - <<'PY' 2>/dev/null || true
import os, glob
removed = 0
for pat in ("/dev/shm/fastrtps_*", "/dev/shm/sem.fastrtps_*", "/dev/shm/*.zenoh"):
    for p in glob.glob(pat):
        try:
            os.remove(p)
            removed += 1
        except OSError:
            pass
print(removed)
PY
)
if [[ "${SHM_REMOVED:-0}" -gt 0 ]]; then
  log "[preflight] removed $SHM_REMOVED stale shm segment(s)"
else
  log "[preflight] no stale shm segments"
fi

# --- 3. Port 8765 probe (up to 10s) ---------------------------------------
for i in $(seq 1 10); do
  if python3 -c "import socket,sys
s=socket.socket(); s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
try:
  s.bind(('0.0.0.0',8765)); s.close(); sys.exit(0)
except OSError:
  sys.exit(1)" 2>/dev/null; then
    log "[preflight] ok — port 8765 free, ready for start_experiment.sh"
    exit 0
  fi
  sleep 1
done

echo "[preflight][ERROR] port 8765 still busy after sweep; manual intervention needed." >&2
echo "[preflight][ERROR] try: ss -lntp | grep 8765   then kill the holder explicitly." >&2
exit 2

#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRAIN_DIR="$ROOT_DIR/brain_linux"
BAG_DIR="$ROOT_DIR/log/experiments/benchmark_120s"
DURATION=120

mkdir -p "$BAG_DIR"

cleanup() {
    echo "[BENCH] Stopping processes gracefully..."
    if [[ -n "${SIM_PID:-}" ]]; then
        kill "$SIM_PID" 2>/dev/null || true
        wait "$SIM_PID" 2>/dev/null || true
    fi
    if [[ -n "${BRAIN_PID:-}" ]]; then
        kill "$BRAIN_PID" 2>/dev/null || true
        wait "$BRAIN_PID" 2>/dev/null || true
    fi
    if [[ -n "${BAG_PID:-}" ]]; then
        echo "[BENCH] Sending SIGINT to bag recorder for clean finalize..."
        kill -INT "$BAG_PID" 2>/dev/null || true
        sleep 5
        kill "$BAG_PID" 2>/dev/null || true
        wait "$BAG_PID" 2>/dev/null || true
    fi
    echo "[BENCH] All processes stopped."
}

trap cleanup EXIT INT TERM

echo "[BENCH] Starting PVS simulation + Zenoh bridge..."
bash "$ROOT_DIR/scripts/start_lin_sim.sh" both --sim-backend pvs &
SIM_PID=$!

sleep 8

echo "[BENCH] Starting ROS2 brain stack..."
bash "$ROOT_DIR/scripts/start_lin_brain.sh" stack --backend zenoh_json &
BRAIN_PID=$!

sleep 5

echo "[BENCH] Starting bag recorder (sqlite3, ${DURATION}s max)..."
set +u
source /opt/ros/humble/setup.bash
source "$BRAIN_DIR/install/setup.bash"
set -u
ros2 bag record -a -s sqlite3 -o "$BAG_DIR/rosbag" --max-bag-duration $((DURATION - 5)) &
BAG_PID=$!

echo "[BENCH] Running for ${DURATION}s..."
sleep "$DURATION"

echo "[BENCH] Duration reached. Stopping..."
exit 0

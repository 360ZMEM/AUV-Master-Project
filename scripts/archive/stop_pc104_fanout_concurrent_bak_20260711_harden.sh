#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_DIR="${ROOT_DIR}/.runtime/pc104_fanout"
PID_DIR="${RUN_DIR}/pids"

stop_pid_file() {
  local label="$1"
  local pid_file="$2"
  if [[ ! -f "${pid_file}" ]]; then
    return
  fi
  local pid
  pid="$(cat "${pid_file}")"
  if [[ -n "${pid}" ]] && { kill -0 "${pid}" 2>/dev/null || sudo -n kill -0 "${pid}" 2>/dev/null; }; then
    echo "[stop] stopping ${label} pid=${pid}"
    kill "${pid}" 2>/dev/null || sudo -n kill "${pid}" 2>/dev/null || true
    sleep 0.5
    if kill -0 "${pid}" 2>/dev/null || sudo -n kill -0 "${pid}" 2>/dev/null; then
      echo "[stop] force stopping ${label} pid=${pid}"
      kill -9 "${pid}" 2>/dev/null || sudo -n kill -9 "${pid}" 2>/dev/null || true
    fi
  fi
  rm -f "${pid_file}"
}

stop_pid_file "ROS2 bridge" "${PID_DIR}/ros2_bridge.pid"
stop_pid_file "fan-out" "${PID_DIR}/fanout.pid"

# Fallback cleanup for sudo-owned fan-out or shell wrappers.
sudo -n pkill -f 'scripts/pc104_udp_fanout.py' 2>/dev/null || true
pkill -f 'ros2 run auv_bridge zenoh_json_bridge_node' 2>/dev/null || true
pkill -f 'zenoh_json_bridge_node.*params.protocol_udp_pc104_fanout' 2>/dev/null || true

sleep 0.5
echo "[stop] current 21/udp owner:"
ss -lunp 'sport = :21' || true
echo "[stop] done"

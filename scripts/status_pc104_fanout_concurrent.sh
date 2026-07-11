#!/usr/bin/env bash
set -euo pipefail

##
# @brief Show PC104 fan-out concurrent debug stack status.
# @date 2026-07-11
# @author 清华 AUV 课题组
##

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_DIR="${ROOT_DIR}/.runtime/pc104_fanout"
LOG_DIR="${RUN_DIR}/logs"
PID_DIR="${RUN_DIR}/pids"
PORTS=(21 52364 52365 52366)

show_pid() {
  local label="$1"
  local pid_file="$2"
  if [[ ! -f "${pid_file}" ]]; then
    echo "[status] ${label}: no pid file"
    return
  fi
  local pid
  pid="$(cat "${pid_file}")"
  if [[ -n "${pid}" ]] && { kill -0 "${pid}" 2>/dev/null || sudo -n kill -0 "${pid}" 2>/dev/null; }; then
    echo "[status] ${label}: running pid=${pid}"
  else
    echo "[status] ${label}: stale pid=${pid}"
  fi
}

show_port() {
  local port="$1"
  echo "[status] ${port}/udp:"
  ss -lunp "sport = :${port}" 2>/dev/null || true
}

show_pid "fan-out" "${PID_DIR}/fanout.pid"
show_pid "ROS2 bridge" "${PID_DIR}/ros2_bridge.pid"

for port in "${PORTS[@]}"; do
  show_port "${port}"
done

echo "[status] fan-out log tail:"
tail -n 12 "${LOG_DIR}/fanout.log" 2>/dev/null || true
echo "[status] ROS2 bridge log tail:"
tail -n 12 "${LOG_DIR}/ros2_bridge.log" 2>/dev/null || true

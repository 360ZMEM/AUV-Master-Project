#!/usr/bin/env bash
set -euo pipefail

##
# @brief Stop the PC104 fan-out concurrent debug stack and verify UDP ports.
# @date 2026-07-11
# @author 清华 AUV 课题组
##

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_DIR="${ROOT_DIR}/.runtime/pc104_fanout"
PID_DIR="${RUN_DIR}/pids"

PORTS=(21 52364 52365 52366)
FORCE="false"

usage() {
  cat <<USAGE
Usage: $0 [--force]

Stops the fan-out concurrent stack and checks that UDP ports are released.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --force)
      FORCE="true"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "[stop] unknown argument: $1" >&2
      usage
      exit 2
      ;;
  esac
done

port_in_use() {
  local port="$1"
  ss -H -lunp "sport = :${port}" 2>/dev/null | awk 'NF { found=1 } END { exit found ? 0 : 1 }'
}

print_port_owner() {
  local port="$1"
  echo "[stop] current ${port}/udp owner:"
  ss -lunp "sport = :${port}" 2>/dev/null || true
}

wait_port_release() {
  local port="$1"
  local deadline=$((SECONDS + 5))
  while (( SECONDS < deadline )); do
    if ! port_in_use "${port}"; then
      return 0
    fi
    sleep 0.5
  done
  return 1
}

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

if [[ "${FORCE}" == "true" ]]; then
  sudo -n pkill -9 -f 'scripts/pc104_udp_fanout.py' 2>/dev/null || true
  pkill -9 -f 'ros2 run auv_bridge zenoh_json_bridge_node' 2>/dev/null || true
  pkill -9 -f 'zenoh_json_bridge_node.*params.protocol_udp_pc104_fanout' 2>/dev/null || true
fi

sleep 0.5
release_failed="false"
for port in "${PORTS[@]}"; do
  if wait_port_release "${port}"; then
    echo "[stop] ${port}/udp released"
  else
    release_failed="true"
    print_port_owner "${port}"
  fi
done

if [[ "${release_failed}" == "true" ]]; then
  echo "[stop] some UDP ports are still occupied; rerun with --force if this is a stale process." >&2
  exit 1
fi

echo "[stop] done"

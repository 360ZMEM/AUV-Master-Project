#!/usr/bin/env bash
set -euo pipefail

##
# @brief PC104 fan-out concurrent debug launcher.
# @date 2026-07-11
# @author 清华 AUV 课题组
#
# Starts:
#   1) sudo fan-out proxy as the only owner of host 21/udp
#   2) ROS2 protocol_udp bridge on localhost high ports
#
# PySide6 is intentionally launched manually with:
#   cd console_soft/auv_console_pyside6
#   /usr/bin/python3 main.py --config console_config.pc104_fanout.yaml
##

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_DIR="${ROOT_DIR}/.runtime/pc104_fanout"
LOG_DIR="${RUN_DIR}/logs"
PID_DIR="${RUN_DIR}/pids"

ROS_PASSIVE="true"
COMMAND_HZ="2.0"

usage() {
  cat <<USAGE
Usage: $0 [--non-passive] [--passive] [--command-hz HZ]

Default starts ROS2 bridge in passive mode.
Use --non-passive only for zero-actuator fan-out smoke/soak tests.
USAGE
}

port_in_use() {
  local port="$1"
  ss -H -lunp "sport = :${port}" 2>/dev/null | awk 'NF { found=1 } END { exit found ? 0 : 1 }'
}

print_port_owner() {
  local port="$1"
  echo "[start] current ${port}/udp owner:"
  ss -lunp "sport = :${port}" 2>/dev/null || true
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --non-passive)
      ROS_PASSIVE="false"
      shift
      ;;
    --passive)
      ROS_PASSIVE="true"
      shift
      ;;
    --command-hz)
      COMMAND_HZ="${2:?missing value for --command-hz}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "[start] unknown argument: $1" >&2
      usage
      exit 2
      ;;
  esac
done

mkdir -p "${LOG_DIR}" "${PID_DIR}"

for port in 21 52364 52365 52366; do
  if port_in_use "${port}"; then
    echo "[start] ${port}/udp is already occupied; stop existing owner first." >&2
    print_port_owner "${port}" >&2
    exit 1
  fi
done

if ! sudo -n true 2>/dev/null; then
  echo "[start] sudo passwordless check failed; fan-out must bind 21/udp." >&2
  exit 1
fi

echo "[start] launching fan-out proxy..."
sudo -n bash -lc "PYTHONUNBUFFERED=1 /usr/bin/python3 '${ROOT_DIR}/scripts/pc104_udp_fanout.py' \
  --listen-host 192.168.0.11 \
  --listen-port 21 \
  --pc104-host 192.168.0.101 \
  --pc104-port 21 \
  --cmd-host 127.0.0.1 \
  --cmd-port 52364 \
  --subscriber ros2=127.0.0.1:52365 \
  --subscriber pyside6=127.0.0.1:52366 \
  --ros-source-port 52365 \
  --console-source-port 52366 \
  >'${LOG_DIR}/fanout.log' 2>&1 & echo \$! >'${PID_DIR}/fanout.pid'"

sleep 1
if ! port_in_use 21; then
  echo "[start] fan-out did not bind 21/udp; see ${LOG_DIR}/fanout.log" >&2
  exit 1
fi
if ! port_in_use 52364; then
  echo "[start] fan-out did not bind 52364/udp; see ${LOG_DIR}/fanout.log" >&2
  exit 1
fi

echo "[start] launching ROS2 protocol_udp bridge, passive_mode=${ROS_PASSIVE}..."
bash -lc "source /opt/ros/humble/setup.bash; \
  source '${ROOT_DIR}/brain_linux/install/setup.bash'; \
  exec ros2 run auv_bridge zenoh_json_bridge_node --ros-args \
    -p params_file:='${ROOT_DIR}/brain_linux/config/params.protocol_udp_pc104_fanout.yaml' \
    -p bridge_backend:=protocol_udp \
    -p passive_mode:=${ROS_PASSIVE} \
    -p command_publish_hz:=${COMMAND_HZ}" \
  >"${LOG_DIR}/ros2_bridge.log" 2>&1 &
echo "$!" >"${PID_DIR}/ros2_bridge.pid"

sleep 2
if ! kill -0 "$(cat "${PID_DIR}/ros2_bridge.pid")" 2>/dev/null; then
  echo "[start] ROS2 bridge exited early; see ${LOG_DIR}/ros2_bridge.log" >&2
  exit 1
fi

echo "[start] fan-out concurrent stack started."
echo "[start] logs:"
echo "  fan-out: ${LOG_DIR}/fanout.log"
echo "  ROS2:    ${LOG_DIR}/ros2_bridge.log"
echo "[start] PySide6 manual launch:"
echo "  cd ${ROOT_DIR}/console_soft/auv_console_pyside6"
echo "  /usr/bin/python3 main.py --config console_config.pc104_fanout.yaml"

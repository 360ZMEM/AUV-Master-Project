#!/usr/bin/env bash
set -euo pipefail

##
# @brief Run a bounded PC104 fan-out ROS2 non-passive zero-actuator soak test.
# @date 2026-07-11
# @author 清华 AUV 课题组
#
# This script keeps the safety posture explicit:
#   - ROS2 bridge runs in non-passive mode.
#   - fan-out still blocks non-zero actuator packets by default.
#   - stop_pc104_fanout_concurrent.sh is always called on exit.
##

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_DIR="${ROOT_DIR}/.runtime/pc104_fanout"
LOG_DIR="${RUN_DIR}/logs"

DURATION_S="600"
COMMAND_HZ="2.0"

usage() {
  cat <<USAGE
Usage: $0 [--duration SEC] [--command-hz HZ]

Runs the fan-out concurrent stack in ROS2 non-passive mode for a bounded
zero-actuator soak test. Default duration is 600 seconds.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --duration)
      DURATION_S="${2:?missing value for --duration}"
      shift 2
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
      echo "[soak] unknown argument: $1" >&2
      usage
      exit 2
      ;;
  esac
done

cleanup() {
  echo "[soak] stopping concurrent stack..."
  "${ROOT_DIR}/scripts/stop_pc104_fanout_concurrent.sh" || \
    "${ROOT_DIR}/scripts/stop_pc104_fanout_concurrent.sh" --force || true
}
trap cleanup EXIT INT TERM

echo "[soak] starting ROS2 non-passive zero-actuator stack"
"${ROOT_DIR}/scripts/start_pc104_fanout_concurrent.sh" \
  --non-passive \
  --command-hz "${COMMAND_HZ}"

echo "[soak] running for ${DURATION_S}s; logs are under ${LOG_DIR}"
timeout --foreground "${DURATION_S}s" bash -c '
  while true; do
    sleep 5
    date "+[soak] heartbeat %F %T"
  done
' || status=$?

status="${status:-0}"
if [[ "${status}" != "124" && "${status}" != "0" ]]; then
  echo "[soak] timeout loop exited unexpectedly with status=${status}" >&2
  exit "${status}"
fi

echo "[soak] completed bounded duration"
echo "[soak] fan-out tail:"
tail -n 20 "${LOG_DIR}/fanout.log" 2>/dev/null || true
echo "[soak] ROS2 bridge tail:"
tail -n 20 "${LOG_DIR}/ros2_bridge.log" 2>/dev/null || true

#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PARAMS_FILE="${1:-$ROOT_DIR/brain_linux/config/magnetic_wrapper_fangkong.yaml}"
DURATION_S="${WRAPPER_SMOKE_DURATION_S:-8}"

set +u
source /opt/ros/humble/setup.bash
if [[ -f "$ROOT_DIR/brain_linux/install/setup.bash" ]]; then
  source "$ROOT_DIR/brain_linux/install/setup.bash"
fi
set -u

echo "[smoke] params_file=$PARAMS_FILE"
echo "[smoke] duration=${DURATION_S}s"
echo "[smoke] note: 未接 ADC 时应看到明确连接失败日志，但节点应能正常启动到超时退出"

set +e
timeout "$DURATION_S" ros2 run auv_decision_ros magnetic_sensor_wrapper_node \
  --ros-args \
  --params-file "$PARAMS_FILE"
status=$?
set -e

if [[ "$status" -eq 124 ]]; then
  echo "[smoke] wrapper smoke reached timeout as expected"
  exit 0
fi

exit "$status"

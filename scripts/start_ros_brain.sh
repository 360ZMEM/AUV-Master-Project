#!/usr/bin/env bash
set -euo pipefail

# Start the ROS2 brain side only.
#
# This is a thin wrapper around start_lin_brain.sh so that the operational
# meaning is clearer when reading scripts or documentation.
#
# Usage examples:
#   bash start_ros_brain.sh
#   bash start_ros_brain.sh stack
#   bash start_ros_brain.sh decision
#   bash start_ros_brain.sh foxglove

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRAIN_ENTRY="$ROOT_DIR/scripts/start_lin_brain.sh"

if [[ ! -f "$BRAIN_ENTRY" ]]; then
  echo "[AUV][ERROR] start_lin_brain.sh not found: $BRAIN_ENTRY"
  exit 1
fi

MODE="${1:-stack}"
shift || true

echo "[AUV] starting ROS2 brain via start_lin_brain.sh (${MODE})..."
bash "$BRAIN_ENTRY" "$MODE" "$@"

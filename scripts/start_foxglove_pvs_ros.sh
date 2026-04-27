#!/usr/bin/env bash
set -euo pipefail

# Foxglove + PVS + ROS2 unified launcher.
#
# This is the PVS counterpart to start_foxglove_holoocean_ros.sh. It forwards
# the PVS simulation backend to the existing unified launcher while keeping the
# Foxglove / ROS2 / bagging workflow unchanged.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SIM_ENTRY="$ROOT_DIR/scripts/start_foxglove_holoocean_ros.sh"

if [[ ! -f "$SIM_ENTRY" ]]; then
  echo "[AUV][ERROR] start_foxglove_holoocean_ros.sh not found: $SIM_ENTRY"
  exit 1
fi

echo "[AUV] starting PVS Foxglove/ROS stack via start_foxglove_holoocean_ros.sh..."
bash "$SIM_ENTRY" --sim-backend pvs "$@"

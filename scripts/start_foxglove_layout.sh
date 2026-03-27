#!/usr/bin/env bash
set -euo pipefail

# Generate the Foxglove layout JSON without starting simulation or ROS2.
#
# This script is intentionally thin: it only forwards arguments to the layout
# generator so that the layout contract stays centralized in one place.
#
# Usage examples:
#   bash start_foxglove_layout.sh
#   bash start_foxglove_layout.sh --topic-prefix /sim --pretty
#   bash start_foxglove_layout.sh --with-map --layout-output foxglove_layout_project/output/auv_layout.generated.<unix>.json

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GENERATOR="$ROOT_DIR/scripts/build_foxglove_layout.sh"

if [[ ! -f "$GENERATOR" ]]; then
  echo "[AUV][ERROR] Foxglove generator wrapper not found: $GENERATOR"
  exit 1
fi

echo "[AUV] generating Foxglove layout only..."
bash "$GENERATOR" "$@"

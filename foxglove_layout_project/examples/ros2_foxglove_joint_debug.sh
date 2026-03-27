#!/usr/bin/env bash
# AUV Foxglove layout generation helper.
# This script mirrors the Console project style: generate the layout JSON first,
# then print the files that Foxglove Desktop should import.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$PROJECT_DIR/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-/usr/bin/python3}"

if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="python3"
fi

echo "[1/2] Generating Foxglove layout..."
"$PYTHON_BIN" -m foxglove_layout_project.generator.build_layout --pretty

echo "[2/2] Layout ready"
echo "  layout: $PROJECT_DIR/output/auv_layout.generated.<unix>.json"
echo "  meta:   $PROJECT_DIR/output/auv_layout.generated.<unix>.meta.json"
echo "  tip:    import the layout JSON into Foxglove Desktop, not the meta file"

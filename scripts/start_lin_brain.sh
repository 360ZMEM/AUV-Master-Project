#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   ./start_lin_brain.sh bootstrap
#   ./start_lin_brain.sh decision [launch args...]
#   ./start_lin_brain.sh example
#   ./start_lin_brain.sh foxglove
#   ./start_lin_brain.sh stack [launch args...]
#
# Note:
#   If you usually work in conda, this script will try to `conda deactivate`
#   twice before ROS build/launch to avoid Python dependency conflicts.

MODE="${1:-bootstrap}"
if [[ "$#" -gt 0 ]]; then
  shift
fi

handle_sigint() {
  echo "[AUV] received SIGINT, treating as manual termination."
  exit 0
}

handle_sigterm() {
  echo "[AUV] received SIGTERM, treating as manual termination."
  exit 0
}

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRAIN_DIR="$ROOT_DIR/brain_linux"
WORKSPACE_ROOT="$(cd "$ROOT_DIR/.." && pwd)"
FOXGLOVE_SDK_ROS_DIR="${FOXGLOVE_SDK_ROS_DIR:-$WORKSPACE_ROOT/foxglove-sdk/ros}"

if [[ ! -d "$BRAIN_DIR/src" ]]; then
  echo "[AUV][ERROR] brain_linux/src not found"
  exit 1
fi

# Prefer a clean non-conda shell for ROS2 builds.
if [[ -n "${CONDA_SHLVL:-}" ]] && command -v conda >/dev/null 2>&1; then
  echo "[AUV][WARN] detected CONDA_SHLVL=${CONDA_SHLVL}, trying to deactivate twice"
  eval "$(conda shell.bash hook)"
  conda deactivate || true
  conda deactivate || true
fi

set +u
source /opt/ros/humble/setup.bash
set -u

# Avoid conda python breaking ROS interface generation (e.g. missing module `em`).
if command -v python3 >/dev/null 2>&1; then
  PY_BIN="$(command -v python3)"
  if [[ "$PY_BIN" == *"miniconda"* || "$PY_BIN" == *"conda"* ]]; then
    echo "[AUV][WARN] detected conda python: $PY_BIN"
    echo "[AUV][WARN] switching PATH priority to /usr/bin for ROS build compatibility"
    export PATH="/usr/bin:$PATH"
  fi
fi

if [[ -f "$BRAIN_DIR/install/setup.bash" ]]; then
  set +u
  source "$BRAIN_DIR/install/setup.bash"
  set -u
fi

if [[ -f "$FOXGLOVE_SDK_ROS_DIR/install/local_setup.bash" ]]; then
  set +u
  source "$FOXGLOVE_SDK_ROS_DIR/install/local_setup.bash"
  set -u
fi

discover_packages() {
  find "$BRAIN_DIR/src" -name package.xml -type f | sort | while read -r xml; do
    sed -n 's:.*<name>\(.*\)</name>.*:\1:p' "$xml" | head -n 1
  done
}

cd "$BRAIN_DIR"
trap handle_sigint INT
trap handle_sigterm TERM
mapfile -t PKGS < <(discover_packages)
if [[ "${#PKGS[@]}" -eq 0 ]]; then
  echo "[AUV][ERROR] no ROS2 packages found in $BRAIN_DIR/src"
  exit 1
fi

echo "[AUV] discovered packages: ${PKGS[*]}"

if [[ -x "/usr/bin/python3" ]]; then
  ROS_PYTHON="/usr/bin/python3"
else
  ROS_PYTHON="$(command -v python3)"
fi

echo "[AUV] colcon build with PYTHON_EXECUTABLE=$ROS_PYTHON"
colcon build \
  --cmake-clean-cache \
  --packages-select "${PKGS[@]}" \
  --cmake-args \
    -DPython3_EXECUTABLE="$ROS_PYTHON" \
    -DPYTHON_EXECUTABLE="$ROS_PYTHON"

if [[ -f "$BRAIN_DIR/install/setup.bash" ]]; then
  set +u
  source "$BRAIN_DIR/install/setup.bash"
  set -u
fi

case "$MODE" in
  bootstrap)
    echo "[AUV] brain_linux bootstrap done."
    ;;
  decision)
    echo "[AUV] launching decision replay..."
    ros2 launch auv_decision_ros decision_replay.launch.py "$@"
    ;;
  example)
    echo "[AUV] launching example talker..."
    ros2 run my_auv_talker auv_data_publisher
    ;;
  foxglove)
    echo "[AUV] launching foxglove bridge..."
    ros2 launch foxglove_bridge foxglove_bridge_launch.xml
    ;;
  stack)
    echo "[AUV] launching integrated stack (bridge -> localization -> controller -> decision)..."
    STACK_ARGS=()
    if ! "$ROS_PYTHON" -c "import zenoh" >/dev/null 2>&1; then
      echo "[AUV][WARN] python package 'zenoh' is missing, disable bridge node"
      STACK_ARGS+=("enable_bridge:=false")
    fi
    if ! "$ROS_PYTHON" -c "import py_trees" >/dev/null 2>&1; then
      echo "[AUV][WARN] python package 'py_trees' is missing, disable decision node"
      STACK_ARGS+=("enable_decision:=false")
    fi
    ros2 launch "$BRAIN_DIR/launch/auv_stack.launch.py" "${STACK_ARGS[@]}" "$@"
    ;;
  *)
    echo "[AUV][ERROR] invalid mode: $MODE"
    echo "[AUV] valid modes: bootstrap | decision | example | foxglove | stack"
    exit 1
    ;;
esac

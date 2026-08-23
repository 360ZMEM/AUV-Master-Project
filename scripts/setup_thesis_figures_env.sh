#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="${ROOT_DIR}/.venv"
PVS_COMMIT="c717e073d7a839dcb5956cf20c595132f1fa249a"
PVS_DIR="${VENV_DIR}/src/PythonVehicleSimulator"

PYTHON_BIN="${PYTHON_BIN:-python3.14}"
"${PYTHON_BIN}" -m venv "${VENV_DIR}"
"${VENV_DIR}/bin/python" -m pip install --upgrade pip setuptools wheel
"${VENV_DIR}/bin/python" -m pip install \
  -r "${ROOT_DIR}/requirements-thesis-figures.txt"

if [[ ! -d "${PVS_DIR}/.git" ]]; then
  mkdir -p "$(dirname "${PVS_DIR}")"
  git clone https://github.com/cybergalactic/PythonVehicleSimulator.git \
    "${PVS_DIR}"
fi

git -C "${PVS_DIR}" fetch origin "${PVS_COMMIT}"
git -C "${PVS_DIR}" checkout --detach "${PVS_COMMIT}"

# Upstream commit omits this package marker, so its wheel is otherwise empty.
touch "${PVS_DIR}/src/python_vehicle_simulator/__init__.py"
"${VENV_DIR}/bin/python" -m pip install --force-reinstall --no-deps \
  "${PVS_DIR}"

"${VENV_DIR}/bin/python" - <<'PY'
from python_vehicle_simulator.vehicles.remus100 import remus100

vehicle = remus100("depthAutopilot", 5.0, 0.0, 0.0, 30.0)
print(f"thesis figure environment ready: {type(vehicle).__name__}")
PY

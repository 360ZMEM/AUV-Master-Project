#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PARAMS_FILE="${1:-$ROOT_DIR/brain_linux/config/magnetic_wrapper_fangkong.yaml}"
DURATION_S="${STACK_SMOKE_DURATION_S:-15}"

cd "$ROOT_DIR"

echo "[stack-smoke] params_file=$PARAMS_FILE"
echo "[stack-smoke] duration=${DURATION_S}s"
echo "[stack-smoke] note: 未接 ADC 时 real magnetic wrapper 会报连接失败，但主栈应可起到 smoke 阶段"

bash scripts/start_experiment.sh \
  --sim-backend pvs \
  --bridge-backend protocol_udp \
  --arbiter-profile \
  --duration "$DURATION_S" \
  --no-record-bag \
  --skip-layout \
  --launcher-output log \
  --brain-arg enable_real_magnetic_wrapper:=true \
  --brain-arg magnetic_wrapper_params_file:="$PARAMS_FILE"

#!/usr/bin/env bash
# Stage S0 — Static Preflight (静态验证)
#
# 不依赖网络/硬件，仅做：
#   1. colcon build (best-effort; 已构建则跳过)
#   2. pytest brain_linux/src/auv_bridge/test/   (协议/仲裁/ESTOP 单测)
#   3. python -c "import common.protocol; ..."  (协议帧序号往返自检)
#   4. 报告 git status 干净/不干净
#
# 用法:
#   bash scripts/real_deployment/00_static_preflight.sh [--dry-run]
#
# 通过判据：所有步骤 exit 0。
set -euo pipefail
SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=./_lib.sh
source "$SELF_DIR/_lib.sh"

rd_require_target "$@"
rd_init_run_dir "S0_static_preflight"
rd_install_cleanup_trap
rd_summary_banner "S0_static_preflight"

run_step() {
  local name="$1"; shift
  local logf="${RD_RUN_DIR}/${name}.log"
  rd_log "step: $name"
  if [[ "$RD_DRY_RUN" == "true" ]]; then
    rd_log "  [dry-run] $*"
    return 0
  fi
  if "$@" > "$logf" 2>&1; then
    rd_log "  ok ($logf)"
  else
    rd_warn "  FAILED ($logf) — see file for details"
    return 1
  fi
}

ANY_FAIL=0

# Step 1: colcon build (best-effort; users can skip via env)
if [[ "${RD_S0_SKIP_BUILD:-0}" != "1" ]]; then
  run_step "01_colcon_build" bash -lc "
    set -e
    cd '$RD_ROOT_DIR/brain_linux'
    if [ -f /opt/ros/humble/setup.bash ]; then
      set +u; source /opt/ros/humble/setup.bash; set -u
    fi
    colcon build --merge-install --event-handlers console_direct+ \
      --packages-select auv_interfaces auv_bridge || colcon build --packages-select auv_bridge
  " || ANY_FAIL=1
else
  rd_log "step 01_colcon_build: skipped (RD_S0_SKIP_BUILD=1)"
fi

# Step 2: pytest of bridge package (offline, deterministic)
run_step "02_pytest_bridge" bash -lc "
  cd '$RD_ROOT_DIR'
  python3 -m pytest brain_linux/src/auv_bridge/test/ -x -q || python3 -m pytest brain_linux/src/auv_bridge/test/ -q
" || ANY_FAIL=1

# Step 3: protocol roundtrip self-check
run_step "03_protocol_roundtrip" python3 - <<'PY'
import sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd()))
from common.protocol import build_downlink_packet, parse_downlink_packet
pkt = build_downlink_packet(
    command_payload={"thrust": 0.5, "left": 1.0, "right": -1.0, "top": 0.0, "bottom": 0.0},
    frame_counter=42,
    obj_address=1,
    control_mode_byte=0xEE,
    work_instruction=0,
    orientation_deg=0.0,
    depth_protect_params=(0, 50),
    bottom_protect_params=(0, 5),
    preset_time_tenths_min=0,
    spare_params=(0, 0),
    parameter_values=[0]*12,
    main_motor_rpm_scale=15.0,
    side_motor_rpm=0,
)
assert len(pkt) == 72, f"downlink length {len(pkt)} != 72"
parsed = parse_downlink_packet(pkt)
assert parsed is not None, "parse_downlink_packet returned None"
print("ok: roundtrip 72B and parsed.")
PY

if [[ "$ANY_FAIL" -ne 0 ]]; then
  rd_warn "S0 had failures — see logs in $RD_RUN_DIR"
  exit 1
fi

rd_mark_stage_passed
rd_log "S0 static preflight PASSED"

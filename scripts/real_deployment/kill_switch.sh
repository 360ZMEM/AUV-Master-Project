#!/usr/bin/env bash
# kill_switch.sh — 一键急停
#
# 持续向目标 AMD 发送 ESTOP 帧 (Work_Cmd=0x02, Motor_Speed=0, ctrl_mode=0x01) 直到 Ctrl+C。
# 这是“架构智慧 #2 急停重置”的最后一道保险，独立于 ROS2/Zenoh。
#
# 用法:
#   bash scripts/real_deployment/kill_switch.sh --target mock
#   bash scripts/real_deployment/kill_switch.sh --target real --i-have-physical-auv
#
# 期望: AMD 在 ≤1s 内观测到 Motor_Speed=0、Ctrl_Mode=0x01。
# 同时 VxWorks 失联安全机制会作为冗余保险（1s 内自发停机）。

set -euo pipefail
SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=./_lib.sh
source "$SELF_DIR/_lib.sh"

rd_require_target "$@"
rd_require_real_confirm
rd_init_run_dir "KS_kill_switch"
rd_install_cleanup_trap
rd_summary_banner "KS_kill_switch"

case "$RD_TARGET" in
  mock)
    AMD_HOST="${AMD_HOST:-127.0.0.1}"
    AMD_PORT="${AMD_PORT:-52364}"
    ;;
  vxsim)
    AMD_HOST="${AMD_HOST:-127.0.0.1}"
    AMD_PORT="${AMD_PORT:-21}"
    ;;
  real)
    AMD_HOST="${AMD_HOST:-192.168.0.101}"
    AMD_PORT="${AMD_PORT:-21}"
    ;;
esac

rd_log "kill-switch armed: target=$AMD_HOST:$AMD_PORT  rate=20Hz"
rd_log "Press Ctrl+C to release."

if [[ "$RD_DRY_RUN" == "true" ]]; then
  rd_log "[dry-run] would loop: manual_protocol_injector.py --ctrl-mode 0x01 --work-cmd 0x02 --motor1 0 ..."
  exit 0
fi

# We re-implement minimal $CKTH crafting inline to avoid coupling to argparse flags
# of manual_protocol_injector that may evolve. Only depends on common.protocol.
exec python3 - "$AMD_HOST" "$AMD_PORT" "$RD_RUN_DIR" <<'PY'
import socket
import sys
import time
from pathlib import Path

host, port_s, run_dir = sys.argv[1], sys.argv[2], sys.argv[3]
port = int(port_s)

sys.path.insert(0, str(Path.cwd()))
from common.protocol import (
    build_downlink_packet, KEY_THRUST, KEY_LEFT, KEY_RIGHT, KEY_TOP, KEY_BOTTOM,
)

KILL_PAYLOAD = {
    KEY_THRUST: 0.0, KEY_LEFT: 0.0, KEY_RIGHT: 0.0, KEY_TOP: 0.0, KEY_BOTTOM: 0.0,
}
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
counter = 0
log_path = Path(run_dir) / "kill_switch.log"
with log_path.open("w") as f:
    f.write(f"# kill_switch start target={host}:{port}\n")
    try:
        while True:
            pkt = build_downlink_packet(
                command_payload=KILL_PAYLOAD,
                frame_counter=counter & 0xFF,
                obj_address=1,
                control_mode_byte=0x01,    # REMOTE
                work_instruction=0x02,     # ESTOP
                orientation_deg=0.0,
                depth_protect_params=(0, 0),
                bottom_protect_params=(0, 0),
                preset_time_tenths_min=0,
                spare_params=(0, 0),
                parameter_values=[0]*12,
                main_motor_rpm_scale=15.0,
                side_motor_rpm=0,
            )
            sock.sendto(pkt, (host, port))
            if counter % 20 == 0:
                f.write(f"sent counter={counter}\n"); f.flush()
            counter += 1
            time.sleep(0.05)
    except KeyboardInterrupt:
        f.write(f"# stopped by SIGINT after {counter} frames\n")
        print(f"\n[kill_switch] released after {counter} frames")
PY

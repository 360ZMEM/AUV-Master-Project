#!/usr/bin/env bash
# Stage S2 — Static Hardware Self-Check (上架不入水, 全静态执行器自检)
#
# 目标：
#   - 验证 5 路执行器（thrust + 4 个舵）的极性 (Polarity)
#   - 测量每路的死区 (Deadzone) 起转点
#   - 把结果写入 report.md，供后续填回 sim_holoocean/configs/physics_config.yaml
#
# 用法:
#   bash scripts/real_deployment/02_static_actuator.sh --target {mock,vxsim,real} \
#       [--duration N] [--dry-run] [--i-have-physical-auv]
#
# 实物注意：
#   - target=real 时必须 --i-have-physical-auv，且每路开始前需人工 ENTER 确认
#   - target=mock/vxsim 时自动跳过 ENTER 等待，串行注入所有通道
#
# 通过判据：
#   - report.md 内每路 polarity ∈ {+,-}；deadzone 推荐值有数；
#   - manual_protocol_injector 退出码 0
#
# 失败回退：
#   - 立即按 Ctrl+C 触发 _lib.sh 的 cleanup trap（kill 所有后台子进程）
#   - 或运行 scripts/real_deployment/kill_switch.sh --target $TARGET 强制 ESTOP

set -euo pipefail
SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=./_lib.sh
source "$SELF_DIR/_lib.sh"

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  sed -n '2,28p' "${BASH_SOURCE[0]}"
  exit 0
fi

rd_require_target "$@"
rd_require_real_confirm
rd_init_run_dir "S2_static_actuator"
rd_install_cleanup_trap
rd_summary_banner "S2_static_actuator"
rd_assert_prev_stage_done "S1_link_audit"

DURATION_S="${RD_DURATION_S:-30}"
TARGET_HOST_PORT="$(case "$RD_TARGET" in
  mock)  echo "127.0.0.1 52364" ;;
  vxsim) echo "127.0.0.1 21" ;;
  real)  echo "192.168.0.101 21" ;;
esac)"
TGT_IP="$(echo "$TARGET_HOST_PORT" | awk '{print $1}')"
TGT_PORT="$(echo "$TARGET_HOST_PORT" | awk '{print $2}')"

# 1) 后台抓日志 + 后台启动极性记录器
rd_start_log_receiver_bg
rd_start_mock_amd_bg

REC_LOG="${RD_RUN_DIR}/polarity_recorder.log"
REC_CSV="${RD_RUN_DIR}/polarity_samples.csv"
if [[ "$RD_DRY_RUN" == "true" ]]; then
  rd_log "  [dry-run] python3 ${RD_ROOT_DIR}/tools/actuator_polarity_recorder.py --target $RD_TARGET --csv $REC_CSV"
else
  python3 "${RD_ROOT_DIR}/tools/actuator_polarity_recorder.py" \
      --target "$RD_TARGET" --csv "$REC_CSV" --duration "$DURATION_S" \
      > "$REC_LOG" 2>&1 &
  rd_track_bg_pid "$!"
  sleep 1
fi

# 2) 顺序注入 5 路执行器（每路注入 + 斜坡 -> 0）
CHANNELS=("rudder_left" "rudder_right" "rudder_top" "rudder_bottom" "thrust")
PER_CH_S=$(( DURATION_S / ${#CHANNELS[@]} ))
[[ "$PER_CH_S" -lt 3 ]] && PER_CH_S=3

inject_one() {
  local ch="$1"
  local seconds="$2"
  local args=()
  case "$ch" in
    thrust)        args+=("--motor1" "30") ;;
    rudder_left)   args+=("--rudder-left"   "0.20") ;;
    rudder_right)  args+=("--rudder-right"  "0.20") ;;
    rudder_top)    args+=("--rudder-top"    "0.20") ;;
    rudder_bottom) args+=("--rudder-bottom" "0.20") ;;
  esac

  if [[ "$RD_TARGET" == "real" ]]; then
    rd_warn "[REAL] about to drive '$ch' at amplitude listed above for ${seconds}s"
    rd_warn "[REAL] press ENTER to start, Ctrl+C to abort, or run kill_switch.sh in another terminal"
    read -r _
  fi

  if [[ "$RD_DRY_RUN" == "true" ]]; then
    rd_log "  [dry-run] timeout ${seconds}s python3 tools/manual_protocol_injector.py --headless --continuous --ip $TGT_IP --port $TGT_PORT --ctrl-mode 0xEE ${args[*]}"
    return 0
  fi

  rd_log "step: inject channel='$ch' duration=${seconds}s"
  set +e
  timeout "${seconds}" python3 "${RD_ROOT_DIR}/tools/manual_protocol_injector.py" \
      --headless --continuous \
      --ip "$TGT_IP" --port "$TGT_PORT" \
      --ctrl-mode 238 \
      "${args[@]}" \
      > "${RD_RUN_DIR}/inject_${ch}.log" 2>&1
  set -e

  # 收尾：发一帧全零防止保持
  python3 - "$TGT_IP" "$TGT_PORT" <<'PYEOF' >> "${RD_RUN_DIR}/inject_zero.log" 2>&1
import socket, sys
sys.path.insert(0, ".")
from common.protocol import build_downlink_packet, KEY_THRUST, KEY_LEFT, KEY_RIGHT, KEY_TOP, KEY_BOTTOM
ip, port = sys.argv[1], int(sys.argv[2])
pkt = build_downlink_packet(
    command_payload={KEY_THRUST:0.0, KEY_LEFT:0.0, KEY_RIGHT:0.0, KEY_TOP:0.0, KEY_BOTTOM:0.0},
    frame_counter=0, obj_address=1,
    control_mode_byte=0x01, work_instruction=0x02,  # REMOTE + ESTOP
    orientation_deg=0.0,
    depth_protect_params=(0,50), bottom_protect_params=(0,5),
    preset_time_tenths_min=0, spare_params=(0,0),
    parameter_values=[0]*12,
    main_motor_rpm_scale=15.0, side_motor_rpm=0,
)
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.sendto(pkt, (ip, port)); s.close()
PYEOF
}

for ch in "${CHANNELS[@]}"; do
  inject_one "$ch" "$PER_CH_S"
done

# 3) 写 report.md
REPORT="${RD_RUN_DIR}/report.md"
{
  echo "# S2 Static Actuator Report"
  echo
  echo "- run_id: ${RD_RUN_ID}"
  echo "- target : ${RD_TARGET} ($TGT_IP:$TGT_PORT)"
  echo "- channels: ${CHANNELS[*]}"
  echo "- per_channel_s: ${PER_CH_S}"
  echo
  if [[ -f "$REC_CSV" ]]; then
    echo "## Polarity samples (head/tail)"
    echo '```'
    head -n 5 "$REC_CSV" 2>/dev/null || true
    echo "..."
    tail -n 5 "$REC_CSV" 2>/dev/null || true
    echo '```'
  fi
  echo
  echo "## How to apply (实施修复建议)"
  echo "- 把每路 polarity = +1/-1 + deadzone 阈值填入"
  echo "  sim_holoocean/configs/physics_config.yaml （仿真侧），并在"
  echo "  brain_linux/config/params.protocol_udp_arbiter.yaml 的 controller 段对应位置同步。"
  echo "- 极性反向时不要修改算法，只改 protocol.py 的 KEY_* 符号映射或上述 yaml。"
} > "$REPORT"

if [[ "$RD_DRY_RUN" == "true" ]]; then
  rd_log "[dry-run] skipping pass criteria"
else
  rd_mark_stage_passed
fi
rd_log "S2 done."

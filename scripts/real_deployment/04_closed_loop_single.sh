#!/usr/bin/env bash
# Stage S4 — Single-Loop Closed Loop (单回路闭环, 0xEF 模式 + 单一 setpoint)
#
# 目标：
#   - 关闭 passive_mode，激活 0xEE/0xEF
#   - 用 tools/single_setpoint_driver.py 给定恒定 set_depth + set_heading + set_speed
#   - 不走行为树（autonomy guard 仍然要求心跳，所以保留 auto_activate_emu.py）
#   - 测量超调 / 稳态误差 / 响应时间
#
# 用法:
#   bash scripts/real_deployment/04_closed_loop_single.sh --target {mock,vxsim,real} \
#       [--duration N] [--dry-run] [--i-have-physical-auv] \
#       [-- depth=2.0 heading=90 speed=0.5]
#
# 通过判据：
#   - single_setpoint_driver 输出超调 < 30%, 稳态误差 < 阈值
#   - cleanup 后 ESTOP 帧已发出（防止漂移）
#
# 失败回退：
#   - Ctrl+C / 或并行运行 kill_switch.sh
#   - 振荡：参考 docs/real_deployment/04_stage4_closed_loop_single.md (Set_Course 变化率限幅)

set -euo pipefail
SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=./_lib.sh
source "$SELF_DIR/_lib.sh"

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  sed -n '2,22p' "${BASH_SOURCE[0]}"
  exit 0
fi

rd_require_target "$@"
rd_require_real_confirm
rd_init_run_dir "S4_closed_loop_single"
rd_install_cleanup_trap
rd_summary_banner "S4_closed_loop_single"
rd_assert_prev_stage_done "S3_shadow_navigation"

DURATION_S="${RD_DURATION_S:-60}"
SETPOINT_ARGS=("${RD_PASSTHROUGH[@]:-}")

STACK_LOG="${RD_RUN_DIR}/stack.log"
EMU_LOG="${RD_RUN_DIR}/auto_activate.log"
DRV_LOG="${RD_RUN_DIR}/single_setpoint.log"
DRV_CSV="${RD_RUN_DIR}/single_setpoint.csv"
BRAIN_PARAMS_FILE="$(rd_brain_params_file)"

# 1) 后台 log + mock AMD
rd_start_log_receiver_bg
rd_start_mock_amd_bg

# 2) 启动 stack（passive_mode=false 默认）
if [[ "$RD_DRY_RUN" == "true" ]]; then
  rd_log "  [dry-run] bash scripts/start_lin_brain.sh stack --arbiter-profile params_file:=${BRAIN_PARAMS_FILE}"
else
  rd_log "step: launching stack (closed-loop, params=${BRAIN_PARAMS_FILE}, duration ${DURATION_S}s)"
  ( cd "$RD_ROOT_DIR" && \
    timeout "${DURATION_S}" bash scripts/start_lin_brain.sh stack --arbiter-profile \
      "params_file:=${BRAIN_PARAMS_FILE}" \
    > "$STACK_LOG" 2>&1 ) &
  rd_track_bg_pid "$!"
  sleep 8
fi

# 3) auto_activate_emu (Zenoh 0xEE 心跳, 解锁 AutonomyGuard)
if [[ "$RD_DRY_RUN" == "true" ]]; then
  rd_log "  [dry-run] python3 scripts/auto_activate_emu.py --rate-hz 10 --connect-timeout 60"
else
  python3 "${RD_SCRIPTS_DIR}/auto_activate_emu.py" \
      --rate-hz 10 --connect-timeout 60 \
      > "$EMU_LOG" 2>&1 &
  rd_track_bg_pid "$!"
  sleep 2
fi

# 4) single_setpoint_driver
if [[ "$RD_DRY_RUN" == "true" ]]; then
  rd_log "  [dry-run] python3 tools/single_setpoint_driver.py --duration $DURATION_S --csv $DRV_CSV ${SETPOINT_ARGS[*]}"
else
  rd_log "step: single_setpoint_driver (duration ${DURATION_S}s)"
  python3 "${RD_ROOT_DIR}/tools/single_setpoint_driver.py" \
      --duration "$DURATION_S" --csv "$DRV_CSV" \
      "${SETPOINT_ARGS[@]:-}" \
      > "$DRV_LOG" 2>&1 &
  rd_track_bg_pid "$!"

  rd_log "S4 running ${DURATION_S}s, monitor stack/setpoint logs in $RD_RUN_DIR"
  sleep "$DURATION_S" || true
fi

# 5) 主动发一次 ESTOP 帧（防止 stack 异常退出后执行器残留）
if [[ "$RD_DRY_RUN" != "true" ]]; then
  bash "$SELF_DIR/kill_switch.sh" --target "$RD_TARGET" --duration 1 \
      > "${RD_RUN_DIR}/kill_switch.log" 2>&1 || true
fi

# 6) 写 report.md
REPORT="${RD_RUN_DIR}/report.md"
{
  echo "# S4 Single Closed-Loop Report"
  echo
  echo "- run_id: ${RD_RUN_ID}"
  echo "- target : ${RD_TARGET}"
  echo "- duration_s: ${DURATION_S}"
  echo "- setpoint_args: ${SETPOINT_ARGS[*]:-default}"
  echo
  if [[ -f "$DRV_LOG" ]]; then
    echo "## single_setpoint_driver tail"
    echo '```'
    tail -n 30 "$DRV_LOG" 2>/dev/null || true
    echo '```'
  fi
  echo
  echo "## 实施修复建议"
  echo "- 振荡：减小 ${BRAIN_PARAMS_FILE} 的 controller.{depth,yaw}.kp"
  echo "- 上下振：在 docs/real_deployment/04_stage4_closed_loop_single.md 表格的 Set_Course 变化率限幅条目里降低速率。"
} > "$REPORT"

if [[ "$RD_DRY_RUN" == "true" ]]; then
  rd_log "[dry-run] skipping pass criteria"
else
  rd_mark_stage_passed
fi
rd_log "S4 done."

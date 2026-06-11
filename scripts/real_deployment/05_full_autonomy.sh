#!/usr/bin/env bash
# Stage S5 — Full Autonomy (全自主巡检; 行为树 + ros2 bag)
#
# 目标：
#   - 释放完整的 py_trees 行为树
#   - 全程 ros2 bag record -a
#   - mock 路径直接复用 start_experiment.sh（最小破坏）
#   - vxsim/real 路径走 start_lin_brain.sh stack + auto_activate_emu.py 并在外层手工录 bag
#
# 用法:
#   bash scripts/real_deployment/05_full_autonomy.sh --target {mock,vxsim,real} \
#       [--duration N] [--dry-run] [--i-have-physical-auv]
#
# 通过判据：
#   - 退出码 0；bag 文件大小 > 0；report.md 写出 bag 路径
#
# 失败回退：
#   - Ctrl+C；或并行 scripts/real_deployment/kill_switch.sh
#   - 行为树停在 StandbyCheck：检查 auto_activate_emu.py 是否在跑

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
rd_init_run_dir "S5_full_autonomy"
rd_install_cleanup_trap
rd_summary_banner "S5_full_autonomy"
rd_assert_prev_stage_done "S4_closed_loop_single"

DURATION_S="${RD_DURATION_S:-60}"
EXP_LOG="${RD_RUN_DIR}/experiment.log"

case "$RD_TARGET" in
  mock)
    # mock 路径：复用 start_experiment.sh —— 它已包含 PVS sim + brain stack + 录 bag
    if [[ "$RD_DRY_RUN" == "true" ]]; then
      rd_log "  [dry-run] bash scripts/start_experiment.sh --sim-backend pvs --bridge-backend protocol_udp --arbiter-profile --auto-activate --duration ${DURATION_S}"
    else
      rd_log "step: start_experiment.sh (mock, ${DURATION_S}s)"
      ( cd "$RD_ROOT_DIR" && \
        bash scripts/start_experiment.sh \
          --sim-backend pvs \
          --bridge-backend protocol_udp \
          --arbiter-profile \
          --auto-activate \
          --duration "${DURATION_S}" ) > "$EXP_LOG" 2>&1
    fi
    ;;

  vxsim|real)
    rd_start_log_receiver_bg
    if [[ "$RD_DRY_RUN" == "true" ]]; then
      rd_log "  [dry-run] start_lin_brain.sh stack --arbiter-profile + auto_activate_emu + ros2 bag"
    else
      rd_log "step: launching stack (no sim, real/vxsim AMD on the wire)"
      ( cd "$RD_ROOT_DIR" && \
        timeout "${DURATION_S}" bash scripts/start_lin_brain.sh stack --arbiter-profile \
        > "${RD_RUN_DIR}/stack.log" 2>&1 ) &
      rd_track_bg_pid "$!"
      sleep 8

      python3 "${RD_SCRIPTS_DIR}/auto_activate_emu.py" \
          --rate-hz 10 --connect-timeout 60 \
          > "${RD_RUN_DIR}/auto_activate.log" 2>&1 &
      rd_track_bg_pid "$!"

      BAG_DIR="${RD_RUN_DIR}/rosbag"
      rd_log "step: ros2 bag record -a -s mcap -o $BAG_DIR"
      ( source /opt/ros/humble/setup.bash; \
        if [[ -f "${RD_ROOT_DIR}/brain_linux/install/setup.bash" ]]; then \
          source "${RD_ROOT_DIR}/brain_linux/install/setup.bash"; \
        fi; \
        ros2 bag record -a -s mcap -o "$BAG_DIR" ) \
        > "${RD_RUN_DIR}/rosbag.log" 2>&1 &
      rd_track_bg_pid "$!"

      sleep "$DURATION_S" || true
    fi
    ;;
esac

REPORT="${RD_RUN_DIR}/report.md"
{
  echo "# S5 Full Autonomy Report"
  echo
  echo "- run_id : ${RD_RUN_ID}"
  echo "- target : ${RD_TARGET}"
  echo "- duration_s: ${DURATION_S}"
  echo
  if [[ -d "${RD_RUN_DIR}/rosbag" ]]; then
    echo "## rosbag (S5 own bag)"
    echo '```'
    ls -la "${RD_RUN_DIR}/rosbag" 2>/dev/null || true
    echo '```'
  fi
  if [[ -f "$EXP_LOG" ]]; then
    echo "## start_experiment tail"
    echo '```'
    tail -n 40 "$EXP_LOG" 2>/dev/null || true
    echo '```'
  fi
  echo
  echo "## 实施修复建议"
  echo "- 若行为树停在 StandbyCheck：检查 auto_activate_emu 日志，确认 0xEE 心跳进入 bridge"
  echo "- 巡检剖面/应急上浮策略：见 docs/real_deployment/05_stage5_full_autonomy.md（DLT+1278—2025 对接）"
} > "$REPORT"

if [[ "$RD_DRY_RUN" == "true" ]]; then
  rd_log "[dry-run] skipping pass criteria"
else
  rd_mark_stage_passed
fi
rd_log "S5 done."

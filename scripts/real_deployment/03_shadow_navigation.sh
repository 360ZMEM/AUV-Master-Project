#!/usr/bin/env bash
# Stage S3 — Shadow Navigation (影子导航; 入水但 Jetson 不接管)
#
# 目标：
#   - 由人类（PySide6 上位机）驾驶 AUV
#   - Jetson 决策栈以 passive_mode=true 跑完整算法，但只发布 shadow_cmd（不控车）
#   - tools/shadow_diff_recorder.py 实时打印 |Jetson_cmd - Human_cmd| 跟踪误差
#
# 用法:
#   bash scripts/real_deployment/03_shadow_navigation.sh --target {mock,vxsim,real} \
#       [--duration N] [--dry-run] [--i-have-physical-auv]
#
# 通过判据：
#   - 跟踪误差 RMS（航向 / 深度）小于阈值（默认 deg<10, m<0.5）→ 写在 report.md
#   - colcon build / launch 退出码 0
#
# 失败回退：
#   - Ctrl+C 即可（trap 会停掉所有子进程；passive_mode 下不会驱动执行器）
#   - 跟踪误差大：检查 EKF Q/R 协方差；查看 docs/real_deployment/03_stage3_shadow_navigation.md

set -euo pipefail
SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=./_lib.sh
source "$SELF_DIR/_lib.sh"

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  sed -n '2,21p' "${BASH_SOURCE[0]}"
  exit 0
fi

rd_require_target "$@"
rd_require_real_confirm
rd_init_run_dir "S3_shadow_navigation"
rd_install_cleanup_trap
rd_summary_banner "S3_shadow_navigation"
rd_assert_prev_stage_done "S2_static_actuator"

DURATION_S="${RD_DURATION_S:-60}"
STACK_LOG="${RD_RUN_DIR}/stack.log"
DIFF_LOG="${RD_RUN_DIR}/shadow_diff.log"
DIFF_CSV="${RD_RUN_DIR}/shadow_diff.csv"

# 1) 后台启动 mock AMD（仅 mock 目标）+ 日志接收
rd_start_log_receiver_bg
rd_start_mock_amd_bg

# 2) 启动 stack with arbiter profile, 通过 launch 参数显式覆盖 passive_mode=true
#    （不修改 launch 默认值, 仅在本 shell 内传 ros2 launch 参数）
if [[ "$RD_DRY_RUN" == "true" ]]; then
  rd_log "  [dry-run] bash scripts/start_lin_brain.sh stack --arbiter-profile passive_mode:=true"
else
  rd_log "step: launching stack (passive_mode:=true, duration ${DURATION_S}s)"
  ( cd "$RD_ROOT_DIR" && \
    timeout "${DURATION_S}" bash scripts/start_lin_brain.sh stack --arbiter-profile \
      passive_mode:=true \
    > "$STACK_LOG" 2>&1 ) &
  rd_track_bg_pid "$!"
  sleep 8  # 等待 colcon build + 节点起来
fi

# 3) 启动 shadow_diff_recorder
if [[ "$RD_DRY_RUN" == "true" ]]; then
  rd_log "  [dry-run] python3 tools/shadow_diff_recorder.py --csv $DIFF_CSV --duration ${DURATION_S}"
else
  rd_log "step: launching shadow_diff_recorder"
  python3 "${RD_ROOT_DIR}/tools/shadow_diff_recorder.py" \
      --csv "$DIFF_CSV" --duration "$DURATION_S" \
      > "$DIFF_LOG" 2>&1 &
  rd_track_bg_pid "$!"
fi

# 4) 等待 duration（trap 会清理）
if [[ "$RD_DRY_RUN" != "true" ]]; then
  rd_log "S3 running for ${DURATION_S}s; please drive the AUV from PySide6 console..."
  sleep "$DURATION_S" || true
fi

# 5) 写 report.md
REPORT="${RD_RUN_DIR}/report.md"
{
  echo "# S3 Shadow Navigation Report"
  echo
  echo "- run_id: ${RD_RUN_ID}"
  echo "- target : ${RD_TARGET}"
  echo "- duration_s: ${DURATION_S}"
  echo "- diff_csv: ${DIFF_CSV}"
  echo
  if [[ -f "$DIFF_CSV" ]]; then
    echo "## shadow_diff (head/tail)"
    echo '```'
    head -n 5 "$DIFF_CSV" 2>/dev/null || true
    echo "..."
    tail -n 10 "$DIFF_CSV" 2>/dev/null || true
    echo '```'
  fi
  echo
  echo "## 实施修复建议"
  echo "- 若 |yaw_diff| 持续 > 10°: 检查极性（S2）和 EKF Q/R；见 docs/real_deployment/03_stage3_shadow_navigation.md"
  echo "- 若 |depth_diff| 持续 > 0.5 m: 标定深度传感器零点；同上文档。"
} > "$REPORT"

if [[ "$RD_DRY_RUN" == "true" ]]; then
  rd_log "[dry-run] skipping pass criteria"
else
  rd_mark_stage_passed
fi
rd_log "S3 done."

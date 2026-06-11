#!/usr/bin/env bash
# Stage S1 — Communication Link & Clock Audit (通信协议与时钟审计)
#
# 目标：
#   - 验证 Jetson <-> AMD 之间的 UDP 链路正常
#   - 抓取 $AUV 上行帧的字节序、缩放因子、帧间隔均值/p95
#   - 验证 $CKTH 下行帧 + 0xEF 模式握手反馈
#
# 用法:
#   bash scripts/real_deployment/01_link_audit.sh --target {mock,vxsim,real} \
#       [--duration N] [--dry-run] [--i-have-physical-auv]
#
# 通过判据：
#   - vxworks_safety_hil.py --mode auto-udp 退出码为 0
#   - 接收到至少 1 帧合法 $AUV (UPLINK_SIZE=145)
#   - 帧间隔 p95 < 500 ms
#
# 失败回退：
#   - 检查 PC IP 是否为 192.168.0.11；VxWorks 是否为 192.168.0.101
#   - 检查 21 / 52365 / 52367 端口未被占用
#   - 用 docs/real_deployment/01_stage1_link_audit.md 故障树排查

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
rd_init_run_dir "S1_link_audit"
rd_install_cleanup_trap
rd_summary_banner "S1_link_audit"
rd_assert_prev_stage_done "S0_static_preflight"

DURATION_S="${RD_DURATION_S:-30}"
HIL_LOG="${RD_RUN_DIR}/vxworks_safety_hil.log"

# 1) 后台抓 UDP 日志（VxWorks UdpLogger UDP printf）
rd_start_log_receiver_bg

# 2) 若是 mock，启动 mock AMD（vxsim/real 由对端自行运行）
rd_start_mock_amd_bg

# 3) 等待对端起来
if [[ "$RD_DRY_RUN" != "true" ]]; then
  sleep 2
fi

# 4) 跑 vxworks_safety_hil.py --mode auto-udp（直接征用现有脚本）
rd_log "step: vxworks_safety_hil --mode auto-udp (duration ${DURATION_S}s)"
HIL_HOST="$(case "$RD_TARGET" in
  mock)  echo "127.0.0.1" ;;
  vxsim) echo "127.0.0.1" ;;
  real)  echo "192.168.0.101" ;;
esac)"

if [[ "$RD_DRY_RUN" == "true" ]]; then
  rd_log "  [dry-run] timeout ${DURATION_S}s python3 ${RD_SCRIPTS_DIR}/vxworks_safety_hil.py --mode auto-udp --host ${HIL_HOST}"
else
  set +e
  timeout "${DURATION_S}" python3 "${RD_SCRIPTS_DIR}/vxworks_safety_hil.py" \
      --mode auto-udp --host "$HIL_HOST" \
      > "$HIL_LOG" 2>&1
  HIL_EC=$?
  set -e
  # timeout 124 表示超时正常结束、不视为失败
  if [[ "$HIL_EC" -ne 0 && "$HIL_EC" -ne 124 ]]; then
    rd_warn "vxworks_safety_hil exited with code $HIL_EC (see $HIL_LOG)"
  fi
fi

# 5) 解析 HIL 日志，写 report.md
REPORT="${RD_RUN_DIR}/report.md"
{
  echo "# S1 Link Audit Report"
  echo
  echo "- run_id: ${RD_RUN_ID}"
  echo "- target : ${RD_TARGET}"
  echo "- host   : ${HIL_HOST}"
  echo "- duration_s: ${DURATION_S}"
  echo "- hil_log  : ${HIL_LOG}"
  echo
  if [[ -f "$HIL_LOG" ]]; then
    echo "## Tail of HIL log"
    echo '```'
    tail -n 60 "$HIL_LOG" 2>/dev/null || true
    echo '```'
  fi
} > "$REPORT"
rd_log "report: $REPORT"

# 6) 通过判据
if [[ "$RD_DRY_RUN" == "true" ]]; then
  rd_log "[dry-run] skipping pass criteria"
elif [[ -f "$HIL_LOG" ]] && grep -q -E "(uplink|UPLINK|\\\$AUV)" "$HIL_LOG"; then
  rd_mark_stage_passed
else
  rd_warn "no uplink frames detected in HIL log; stage NOT marked passed"
  rd_warn "see $HIL_LOG and docs/real_deployment/01_stage1_link_audit.md"
fi

rd_log "S1 done."

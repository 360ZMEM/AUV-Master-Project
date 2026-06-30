#!/usr/bin/env bash
# sync_thesis_figures.sh
# 将 /auv_data 中的关键主线实验图片同步到仓库内非 .gitignore 目录，
# 使 docs/thesis 文档可以用相对路径引用、随仓库一起同步到其他机器。
#
# 设计原则：
#   - 简洁、整合：只迁移每类实验的关键参考时点，不搬运全部历史 run。
#   - 可覆盖：每次运行清空并重建目标子目录，保证幂等。
#   - 保留实验条件：连同 run 自带的 report/csv 一起复制为 _source_report.*。
#
# 用法：
#   bash scripts/sync_thesis_figures.sh            # 使用默认 /auv_data
#   AUV_DATA=/path/to/auv_data bash scripts/sync_thesis_figures.sh
#   bash scripts/sync_thesis_figures.sh --dry-run  # 只打印将要复制的内容

set -euo pipefail

AUV_DATA="${AUV_DATA:-/auv_data}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST_ROOT="${REPO_ROOT}/docs/thesis/figures/experiments"

DRY_RUN=0
[[ "${1:-}" == "--dry-run" ]] && DRY_RUN=1

# 关键主线清单：  目标子目录 | 源 run 目录（相对 AUV_DATA） | 实验报告文件名（可空）
MANIFEST=(
  "decision_bt_vs_fsm|results/decision/bt_vs_fsm/20260608_173806|decision_architecture_benchmark.md"
  "control_pid_pvs|results/control/pid_pvs_tuning/20260610_142323|report.md"
  "control_mpc|results/control/mpc_test/20260610_170426|report.md"
  "control_mpc_xy_yaw_extreme|results/control/mpc_xy_yaw_extreme/20260620_011831|"
)

log() { printf '[sync-figures] %s\n' "$*"; }

if [[ ! -d "${AUV_DATA}" ]]; then
  echo "ERROR: AUV_DATA 目录不存在: ${AUV_DATA}" >&2
  exit 1
fi

log "源数据根目录 : ${AUV_DATA}"
log "目标目录     : ${DEST_ROOT}"
[[ "${DRY_RUN}" == "1" ]] && log "(dry-run 模式，仅预览)"

total_imgs=0
for entry in "${MANIFEST[@]}"; do
  IFS='|' read -r dest_sub src_rel report <<< "${entry}"
  src_dir="${AUV_DATA}/${src_rel}"
  src_fig="${src_dir}/figures"
  dest_dir="${DEST_ROOT}/${dest_sub}"

  if [[ ! -d "${src_fig}" ]]; then
    log "跳过 (源缺失): ${src_fig}"
    continue
  fi

  n=$(find "${src_fig}" -maxdepth 1 -type f \( -name '*.png' -o -name '*.jpg' -o -name '*.jpeg' \) | wc -l)
  log "同步 ${dest_sub}  <-  ${src_rel}  (${n} 张图)"
  total_imgs=$((total_imgs + n))

  if [[ "${DRY_RUN}" == "1" ]]; then
    continue
  fi

  rm -rf "${dest_dir}"
  mkdir -p "${dest_dir}"
  cp "${src_fig}"/*.png "${dest_dir}/" 2>/dev/null || true
  cp "${src_fig}"/*.jpg "${dest_dir}/" 2>/dev/null || true

  # 记录数据来源，便于追溯实验条件
  {
    echo "# 数据来源"
    echo ""
    echo "- 源 run: \`${src_rel}\`"
    echo "- 同步时间: $(date '+%Y-%m-%d %H:%M:%S')"
    echo "- 来源根: \`${AUV_DATA}\`（不随仓库同步，仅本地存在）"
  } > "${dest_dir}/_SOURCE.md"

  if [[ -n "${report}" && -f "${src_dir}/${report}" ]]; then
    cp "${src_dir}/${report}" "${dest_dir}/_source_report.md"
  fi
  # 附带的指标 csv 一并保留
  find "${src_dir}" -maxdepth 1 -type f -name '*.csv' -exec cp {} "${dest_dir}/" \; 2>/dev/null || true
done

log "完成，共同步 ${total_imgs} 张主线实验图。"
if [[ "${DRY_RUN}" != "1" ]]; then
  log "目标树："
  find "${DEST_ROOT}" -type f | sort | sed 's/^/  /'
fi

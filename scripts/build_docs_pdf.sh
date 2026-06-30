#!/usr/bin/env bash
# build_docs_pdf.sh
# 一键将 Markdown 文档通过 pandoc 转为 PDF。
#
# 特点：
#   - 可控制子文件夹：默认转换整个 docs/，也可只转某个子目录（如 thesis）。
#   - 输出目录与源分离：统一输出到根级 docs_pdf/，并镜像 docs/ 下的目录结构。
#   - 自动探测 PDF 引擎；缺失时按需 apt 安装（wkhtmltopdf）。
#   - 中文友好：xelatex 引擎下使用 WenQuanYi Zen Hei 字体。
#
# 用法：
#   bash scripts/build_docs_pdf.sh                 # 转换 docs/ 下所有 .md
#   bash scripts/build_docs_pdf.sh thesis          # 只转换 docs/thesis/
#   bash scripts/build_docs_pdf.sh thesis/paper    # 只转换 docs/thesis/paper/
#   ENGINE=xelatex bash scripts/build_docs_pdf.sh  # 强制指定引擎
#
# 环境变量：
#   DOCS_DIR   源文档根目录，默认 docs
#   OUT_DIR    输出根目录，默认 docs_pdf
#   ENGINE     pdf 引擎：wkhtmltopdf | xelatex（默认自动探测）
#   NO_INSTALL 设为 1 时不自动安装引擎

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DOCS_DIR="${DOCS_DIR:-docs}"
OUT_DIR="${OUT_DIR:-docs_pdf}"
SUBPATH="${1:-}"
CJK_FONT="WenQuanYi Zen Hei"

cd "${REPO_ROOT}"

log()  { printf '[build-pdf] %s\n' "$*"; }
err()  { printf '[build-pdf][ERROR] %s\n' "$*" >&2; }

if ! command -v pandoc >/dev/null 2>&1; then
  err "未找到 pandoc，请先安装：sudo apt-get install -y pandoc"
  exit 1
fi

SRC_ROOT="${DOCS_DIR}"
[[ -n "${SUBPATH}" ]] && SRC_ROOT="${DOCS_DIR}/${SUBPATH}"
if [[ ! -d "${SRC_ROOT}" ]]; then
  err "源目录不存在: ${SRC_ROOT}"
  exit 1
fi

# ---- 选择 PDF 引擎 ----
detect_engine() {
  if [[ -n "${ENGINE:-}" ]]; then echo "${ENGINE}"; return; fi
  if command -v xelatex   >/dev/null 2>&1; then echo "xelatex";     return; fi
  if command -v wkhtmltopdf >/dev/null 2>&1; then echo "wkhtmltopdf"; return; fi
  echo ""
}

ensure_engine() {
  local eng; eng="$(detect_engine)"
  if [[ -n "${eng}" ]]; then echo "${eng}"; return; fi
  if [[ "${NO_INSTALL:-0}" == "1" ]]; then
    err "无可用 PDF 引擎且 NO_INSTALL=1。请安装 wkhtmltopdf 或 texlive-xetex。"
    return 1
  fi
  log "未探测到 PDF 引擎，尝试 apt 安装 wkhtmltopdf ..."
  if command -v sudo >/dev/null 2>&1; then SUDO=sudo; else SUDO=; fi
  ${SUDO} apt-get update -qq && ${SUDO} apt-get install -y wkhtmltopdf >/dev/null 2>&1
  if command -v wkhtmltopdf >/dev/null 2>&1; then
    echo "wkhtmltopdf"; return
  fi
  err "wkhtmltopdf 安装失败，请手动安装 PDF 引擎。"
  return 1
}

ENGINE_SEL="$(ensure_engine)" || exit 1
log "源目录   : ${SRC_ROOT}"
log "输出目录 : ${OUT_DIR}/${SUBPATH}"
log "PDF 引擎 : ${ENGINE_SEL}"

# ---- 引擎专属 pandoc 参数 ----
engine_args() {
  case "${ENGINE_SEL}" in
    xelatex)
      printf '%s\0' \
        --pdf-engine=xelatex \
        -V "CJKmainfont=${CJK_FONT}" \
        -V mainfont="DejaVu Sans" \
        -V geometry:margin=2.5cm
      ;;
    wkhtmltopdf)
      printf '%s\0' \
        --pdf-engine=wkhtmltopdf \
        -V margin-top=18mm -V margin-bottom=18mm \
        -V margin-left=16mm -V margin-right=16mm
      ;;
  esac
}

mapfile -t ENGINE_ARGS < <(engine_args | xargs -0 -n1 printf '%s\n')

# 将单个 md 转为 PDF。
#   - xelatex   ：pandoc 直接出 PDF，相对路径图片由 --resource-path 解析嵌入。
#   - wkhtmltopdf：wkhtmltopdf 默认禁止访问本地文件，相对路径 ../figures 图片会被
#                  "Blocked access to file" 丢弃。故先用 pandoc --self-contained 把图片
#                  以 base64 内嵌成自包含 HTML，再由 wkhtmltopdf 渲染，确保图片进入 PDF。
convert_one() {
  local md="$1" out="$2" rpath
  rpath="$(dirname "${md}")"
  if [[ "${ENGINE_SEL}" == "wkhtmltopdf" ]]; then
    local html; html="$(mktemp --suffix=.html)"
    pandoc "${md}" \
        --resource-path="${rpath}" \
        --toc --toc-depth=3 \
        --self-contained \
        -H "${REPO_ROOT}/scripts/pdf_style.html" \
        -M title="$(basename "${md}" .md)" \
        -t html5 \
        -o "${html}" 2>/tmp/pandoc_err.log \
      && pandoc "${html}" \
        -H "${REPO_ROOT}/scripts/pdf_style.html" \
        "${ENGINE_ARGS[@]}" \
        -o "${out}" 2>>/tmp/pandoc_err.log
    local rc=$?
    rm -f "${html}"
    return ${rc}
  fi
  pandoc "${md}" \
      --resource-path="${rpath}" \
      --toc --toc-depth=3 \
      --standalone \
      "${ENGINE_ARGS[@]}" \
      -o "${out}" 2>/tmp/pandoc_err.log
}

ok=0; fail=0
while IFS= read -r -d '' md; do
  rel="${md#${DOCS_DIR}/}"
  out="${OUT_DIR}/${rel%.md}.pdf"
  mkdir -p "$(dirname "${out}")"
  if convert_one "${md}" "${out}"; then
    log "OK   ${rel%.md}.pdf"
    ok=$((ok+1))
  else
    err "FAIL ${rel}  ->  $(tail -n1 /tmp/pandoc_err.log)"
    fail=$((fail+1))
  fi
done < <(find "${SRC_ROOT}" -type f -name '*.md' -print0 | sort -z)

log "完成：成功 ${ok}，失败 ${fail}，输出根目录 ${OUT_DIR}/"
[[ "${fail}" -gt 0 ]] && exit 2 || exit 0

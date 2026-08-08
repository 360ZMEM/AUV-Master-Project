#!/usr/bin/env bash
# with_timeout.sh — 便携式命令超时包装器（macOS 无 timeout/gtimeout 时的兜底）
#
# 背景：本机（Darwin）未安装 GNU coreutils，`timeout`/`gtimeout` 均不存在，
#       长命令（尤其网络/CLI 冷启动）易卡死。本脚本用 perl 的 alarm() 强制超时。
#
# 用法：
#   with_timeout.sh <秒数> <命令> [参数...]
#   例：with_timeout.sh 20 drawio --version
#       with_timeout.sh 15 pdftotext in.pdf -
#
# 退出码：命令自身退出码；被超时杀死时约为 142（SIGALRM）。
#
# 备选（按场景优先级）：
#   1) 网络命令优先用自带开关：curl --max-time N / wget --timeout=N
#   2) 任意命令用本脚本（perl alarm）
#   3) Shell 工具自带 timeout 参数（毫秒）作为硬兜底；超时会转后台
#   4) 真·长任务用 run_in_background=true，再 Read 输出日志
#   5) 也可 `brew install coreutils` 获得 gtimeout
set -euo pipefail
if [ "$#" -lt 2 ]; then
  echo "usage: with_timeout.sh <seconds> <command> [args...]" >&2
  exit 2
fi
secs="$1"; shift
exec perl -e 'my $s=shift; alarm $s; exec @ARGV or die "exec failed: $!";' "$secs" "$@"

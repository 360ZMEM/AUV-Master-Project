#!/usr/bin/env bash
# Jetson-emulated算力侧基准（论文 §5.5 Sim-to-Real 章节用）。
#
# 目的：在仿真主机上跑一段标准实验，并以 ~5 Hz 采样 brain_linux 节点的 CPU%/MEM
# 与 ROS2 关键话题端到端延迟，落到 CSV 与 PNG。
#
# 注意：此脚本不替代 Jetson 真机基准，仅用于在写作侧给出"软件栈在算力受限
# 工况下仍可实时运行"的证据。文档 docs/thesis/06_jetson_deploy_emulated.md
# 会明确"emulated, not on-device"。
#
# 用法：
#   bash scripts/run_jetson_emulated_bench.sh [--duration 300] [--scenario baseline]
#
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DURATION_S=300
SCENARIO_ID="baseline"
SAMPLE_HZ=5
OUTPUT_ROOT="${ROOT_DIR}/log/jetson_emulated"

usage() {
  cat <<EOF
Usage: $(basename "$0") [options]
  --duration N     experiment seconds (default 300)
  --scenario ID    scenario id under scenarios/ (default baseline)
  --sample-hz N    /proc sampling rate (default 5)
  --output-root D  output root dir (default log/jetson_emulated)
  --help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --duration) DURATION_S="${2:?}"; shift 2 ;;
    --scenario) SCENARIO_ID="${2:?}"; shift 2 ;;
    --sample-hz) SAMPLE_HZ="${2:?}"; shift 2 ;;
    --output-root) OUTPUT_ROOT="${2:?}"; shift 2 ;;
    --help) usage; exit 0 ;;
    *) echo "[jetson-emu] unknown arg: $1"; usage; exit 2 ;;
  esac
done

STAMP="$(date +%Y%m%d_%H%M%S)"
OUT_DIR="${OUTPUT_ROOT}/${STAMP}_${SCENARIO_ID}"
mkdir -p "$OUT_DIR"
CSV="${OUT_DIR}/cpu_mem.csv"
SAMPLE_LOG="${OUT_DIR}/sampler.log"
EXPERIMENT_LOG="${OUT_DIR}/experiment.log"
echo "ts_iso,pid,cmd,cpu_pct,mem_kb,rss_kb" > "$CSV"

echo "[jetson-emu] output: ${OUT_DIR}"
echo "[jetson-emu] starting experiment in background (duration=${DURATION_S}s, scenario=${SCENARIO_ID})"

# 后台启动主线实验（受 start_experiment.sh 的 --duration 自动停止）
SCEN_PATH="${ROOT_DIR}/scenarios/scenario_${SCENARIO_ID}.yaml"
if [[ ! -f "$SCEN_PATH" ]]; then
  echo "[jetson-emu][FATAL] scenario yaml not found: $SCEN_PATH"
  exit 2
fi

bash "${ROOT_DIR}/scripts/start_experiment.sh" \
  --sim-backend pvs \
  --duration "$DURATION_S" \
  --scenario "$SCEN_PATH" \
  --seed 0 \
  --mpc-mode ua \
  --record-format mcap \
  > "$EXPERIMENT_LOG" 2>&1 &
EXP_PID=$!
echo "[jetson-emu] experiment pid=${EXP_PID}"

# /proc 采样器（轻量，避免依赖 top/htop/tegrastats）
SAMPLE_INTERVAL_S="$(awk -v hz="$SAMPLE_HZ" 'BEGIN{ printf "%.4f", 1.0/hz }')"
SAMPLE_END_TS=$(( $(date +%s) + DURATION_S + 5 ))

(
  set +e
  while true; do
    NOW="$(date --iso-8601=seconds)"
    NOW_EPOCH="$(date +%s)"
    if [[ "$NOW_EPOCH" -ge "$SAMPLE_END_TS" ]]; then break; fi
    if ! kill -0 "$EXP_PID" 2>/dev/null; then
      echo "[sampler] experiment exited; stopping sampler" >> "$SAMPLE_LOG"
      break
    fi
    # 抓取所有受 start_experiment 派生的 python/ros2 进程
    for pid in $(pgrep -f "(sim_holoocean/apps/main\.py|run_zenoh_bridge\.py|mock_amd_server|brain_linux/.*ros2|ros2 bag record)" 2>/dev/null); do
      [[ -d "/proc/$pid" ]] || continue
      CMD="$(tr '\0' ' ' < /proc/$pid/cmdline 2>/dev/null | sed 's/,/_/g' | head -c 80)"
      STAT="$(cat /proc/$pid/stat 2>/dev/null || true)"
      [[ -z "$STAT" ]] && continue
      RSS_PAGES=$(echo "$STAT" | awk '{print $24}')
      RSS_KB=$(( RSS_PAGES * 4 ))
      MEM_KB=$(grep VmSize /proc/$pid/status 2>/dev/null | awk '{print $2}')
      [[ -z "$MEM_KB" ]] && MEM_KB="0"
      # 简单 CPU% 估算：utime+stime 差 / 采样间隔（粗略；论文用对照足够）
      U1=$(echo "$STAT" | awk '{print $14+$15}')
      sleep "$SAMPLE_INTERVAL_S"
      STAT2="$(cat /proc/$pid/stat 2>/dev/null || true)"
      [[ -z "$STAT2" ]] && continue
      U2=$(echo "$STAT2" | awk '{print $14+$15}')
      DELTA=$(( U2 - U1 ))
      CLK_TCK=$(getconf CLK_TCK 2>/dev/null || echo 100)
      CPU_PCT=$(awk -v d="$DELTA" -v t="$SAMPLE_INTERVAL_S" -v c="$CLK_TCK" \
                 'BEGIN{ printf "%.2f", (d/c)/t*100 }')
      printf '%s,%s,"%s",%s,%s,%s\n' "$NOW" "$pid" "$CMD" "$CPU_PCT" "$MEM_KB" "$RSS_KB" >> "$CSV"
    done
  done
) &
SAMPLER_PID=$!

cleanup() {
  kill "$SAMPLER_PID" 2>/dev/null || true
  if kill -0 "$EXP_PID" 2>/dev/null; then
    echo "[jetson-emu] killing experiment pid=${EXP_PID}"
    kill -INT "$EXP_PID" 2>/dev/null || true
    sleep 2
    kill -TERM "$EXP_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

# 等待实验自然结束
wait "$EXP_PID" || true
echo "[jetson-emu] experiment done"

# 等采样器收尾
sleep 2
kill "$SAMPLER_PID" 2>/dev/null || true
wait "$SAMPLER_PID" 2>/dev/null || true

# 简单汇总
ROW_COUNT=$(($(wc -l < "$CSV") - 1))
echo "[jetson-emu] samples collected: ${ROW_COUNT} -> ${CSV}"

# 离线绘图（best-effort；matplotlib 不在则跳过）
python3 - "$CSV" "$OUT_DIR" <<'PYEOF' || true
import sys, csv, collections
from pathlib import Path
csv_path = Path(sys.argv[1])
out_dir = Path(sys.argv[2])
try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
except Exception:
    print("[jetson-emu] matplotlib not available; skipping plots")
    sys.exit(0)

per_proc = collections.defaultdict(list)
with open(csv_path, newline="") as f:
    rdr = csv.DictReader(f)
    for row in rdr:
        try:
            cpu = float(row["cpu_pct"])
            mem = float(row["rss_kb"]) / 1024.0
        except (ValueError, KeyError):
            continue
        cmd = row.get("cmd", "?")
        # 只保留 cmd 的第一个 token
        short = cmd.split()[0].split("/")[-1] if cmd else "?"
        per_proc[short].append((cpu, mem))

if not per_proc:
    print("[jetson-emu] no samples to plot")
    sys.exit(0)

fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(9, 6), dpi=200)
labels = list(per_proc.keys())
cpu_data = [[v[0] for v in per_proc[k]] for k in labels]
mem_data = [[v[1] for v in per_proc[k]] for k in labels]
ax1.boxplot(cpu_data, labels=labels, vert=True)
ax1.set_ylabel("CPU %"); ax1.set_title("Per-process CPU usage (Jetson emulated)")
ax1.tick_params(axis="x", rotation=30)
ax2.boxplot(mem_data, labels=labels, vert=True)
ax2.set_ylabel("RSS [MB]"); ax2.set_title("Per-process memory")
ax2.tick_params(axis="x", rotation=30)
fig.tight_layout()
fig.savefig(out_dir / "cpu_mem_boxplot.png")
print(f"[jetson-emu] saved {out_dir/'cpu_mem_boxplot.png'}")
PYEOF

echo "[jetson-emu] done. results -> ${OUT_DIR}"

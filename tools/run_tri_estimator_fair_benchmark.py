#!/usr/bin/env python3
"""E-2 三估计器公平对比重算驱动脚本（对应 24 号文档 §8.1 ②）。

在 P1 sensor sweep 的多种子 bag 上，以 O-1 修复后的公平初始化口径
（--es-ekf-init fair：Raw DR / Std EKF / ES-EKF 共享同一 truth 起点、同一
frame，无首帧自对齐）重算三估计器对比，按场景与种子聚合出
XY/Z/3D RMSE 的均值±标准差，用于替换 §1.4 不可信开发文档结论
（dvl_fixed_final 深度维 12 m 崩、不同源、单 bag）。

用法：
  python3 tools/run_tri_estimator_fair_benchmark.py \
      --sweep-csv log/thesis_sweep/20260612_170618_p1_sensor_3seed/results.csv \
      --out-root $AUV_DATA_ROOT/results/state_estimation/e2_tri_estimator_fair \
      [--scenarios dvl_dropout_10,combined_stress] [--init fair]

聚合产物写入仓库内 docs 目录（由 --summary-dir 指定），逐 run 原始图表与
report 留在 --out-root（AUV_DATA_ROOT 隔离目录，不随仓库同步）。
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BENCH = PROJECT_ROOT / "tools" / "offline_ekf_benchmark.py"

ENGINES = ("raw_dr", "std_ekf", "es_ekf")
METRIC_ROW_RE = re.compile(
    r"^\s*(raw_dr|std_ekf|es_ekf)\s*:\s*RMSE_XY=([\d.]+)m\s+RMSE_Z=([\d.]+)m\s+"
    r"RMSE_3D=([\d.]+)m\s+CEP50=([\d.]+)m"
)


def parse_metrics_from_stdout(text: str) -> dict[str, dict[str, float]]:
    """Extract per-engine metrics printed by offline_ekf_benchmark stage [4/6]."""
    out: dict[str, dict[str, float]] = {}
    for line in text.splitlines():
        m = METRIC_ROW_RE.match(line)
        if m:
            out[m.group(1)] = {
                "rmse_xy": float(m.group(2)),
                "rmse_z": float(m.group(3)),
                "rmse_3d": float(m.group(4)),
                "cep50": float(m.group(5)),
            }
    return out


def load_sweep_rows(csv_path: Path, scenarios: list[str] | None) -> list[dict]:
    rows = list(csv.DictReader(open(csv_path, encoding="utf-8")))
    rows = [r for r in rows if r.get("status") == "ok" and r.get("mcap")]
    if scenarios:
        keep = set(scenarios)
        rows = [r for r in rows if r["scenario"] in keep]
    return rows


def run_one(mcap: Path, out_dir: Path, init: str) -> dict[str, dict[str, float]]:
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable,
        str(BENCH),
        "--input",
        str(mcap),
        "--output-dir",
        str(out_dir),
        "--es-ekf-init",
        init,
        "--skip-assertions",
        "--verbose",
    ]
    env = dict(os.environ)
    proc = subprocess.run(cmd, capture_output=True, text=True, env=env)
    metrics = parse_metrics_from_stdout(proc.stdout)
    if not metrics:
        sys.stderr.write(proc.stdout[-2000:] + "\n" + proc.stderr[-1000:] + "\n")
    return metrics


def mean_std(vals: list[float]) -> tuple[float, float]:
    vals = [v for v in vals if v is not None and math.isfinite(v)]
    if not vals:
        return float("nan"), float("nan")
    n = len(vals)
    mu = sum(vals) / n
    if n < 2:
        return mu, 0.0
    var = sum((v - mu) ** 2 for v in vals) / (n - 1)
    return mu, math.sqrt(var)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sweep-csv", type=Path, required=True)
    ap.add_argument("--out-root", type=Path, required=True, help="逐 run 输出根（AUV_DATA_ROOT 隔离目录）")
    ap.add_argument("--summary-dir", type=Path, required=True, help="聚合 CSV/JSON 落盘目录（仓库内）")
    ap.add_argument("--scenarios", type=str, default=None, help="逗号分隔场景子集；默认全部")
    ap.add_argument("--init", choices=["fair", "legacy-auto"], default="fair")
    args = ap.parse_args()

    scenarios = [s.strip() for s in args.scenarios.split(",")] if args.scenarios else None
    rows = load_sweep_rows(args.sweep_csv, scenarios)
    if not rows:
        raise SystemExit("No usable rows in sweep CSV")

    args.out_root.mkdir(parents=True, exist_ok=True)
    args.summary_dir.mkdir(parents=True, exist_ok=True)

    raw_records: list[dict] = []
    # scenario -> engine -> metric -> [values]
    agg: dict[str, dict[str, dict[str, list[float]]]] = defaultdict(
        lambda: {e: defaultdict(list) for e in ENGINES}
    )

    for r in rows:
        scenario, seed = r["scenario"], r["seed"]
        mcap = Path(r["mcap"])
        if not mcap.exists():
            print(f"[SKIP] missing bag: {mcap}")
            continue
        out_dir = args.out_root / args.init / f"{scenario}__seed{seed}"
        print(f"[RUN] {scenario} seed={seed} init={args.init}")
        metrics = run_one(mcap, out_dir, args.init)
        if not metrics:
            print(f"[WARN] no metrics parsed for {scenario} seed={seed}")
            continue
        for eng in ENGINES:
            m = metrics.get(eng, {})
            rec = {"scenario": scenario, "seed": seed, "engine": eng, **m}
            raw_records.append(rec)
            for k, v in m.items():
                agg[scenario][eng][k].append(v)
            print(f"    {eng}: XY={m.get('rmse_xy'):.3f} Z={m.get('rmse_z'):.3f} 3D={m.get('rmse_3d'):.3f}")

    # ---- write raw records ----
    raw_csv = args.summary_dir / f"tri_estimator_{args.init}_raw.csv"
    with open(raw_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["scenario", "seed", "engine", "rmse_xy", "rmse_z", "rmse_3d", "cep50"])
        for rec in raw_records:
            w.writerow([
                rec["scenario"], rec["seed"], rec["engine"],
                f"{rec.get('rmse_xy', float('nan')):.4f}",
                f"{rec.get('rmse_z', float('nan')):.4f}",
                f"{rec.get('rmse_3d', float('nan')):.4f}",
                f"{rec.get('cep50', float('nan')):.4f}",
            ])

    # ---- write per-scenario mean±std summary ----
    summary_csv = args.summary_dir / f"tri_estimator_{args.init}_summary.csv"
    with open(summary_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "scenario", "engine", "n_seeds",
            "xy_rmse_mean", "xy_rmse_std",
            "z_rmse_mean", "z_rmse_std",
            "rmse3d_mean", "rmse3d_std",
        ])
        for scenario in sorted(agg):
            for eng in ENGINES:
                d = agg[scenario][eng]
                n = len(d.get("rmse_xy", []))
                xy_m, xy_s = mean_std(d.get("rmse_xy", []))
                z_m, z_s = mean_std(d.get("rmse_z", []))
                d3_m, d3_s = mean_std(d.get("rmse_3d", []))
                w.writerow([
                    scenario, eng, n,
                    f"{xy_m:.4f}", f"{xy_s:.4f}",
                    f"{z_m:.4f}", f"{z_s:.4f}",
                    f"{d3_m:.4f}", f"{d3_s:.4f}",
                ])

    # ---- pooled cross-scenario summary (all seeds x scenarios) ----
    pooled: dict[str, dict[str, list[float]]] = {e: defaultdict(list) for e in ENGINES}
    for scenario in agg:
        for eng in ENGINES:
            for k, vals in agg[scenario][eng].items():
                pooled[eng][k].extend(vals)
    pooled_out = {}
    for eng in ENGINES:
        xy_m, xy_s = mean_std(pooled[eng].get("rmse_xy", []))
        z_m, z_s = mean_std(pooled[eng].get("rmse_z", []))
        d3_m, d3_s = mean_std(pooled[eng].get("rmse_3d", []))
        pooled_out[eng] = {
            "n": len(pooled[eng].get("rmse_xy", [])),
            "xy_rmse_mean": xy_m, "xy_rmse_std": xy_s,
            "z_rmse_mean": z_m, "z_rmse_std": z_s,
            "rmse3d_mean": d3_m, "rmse3d_std": d3_s,
        }
    (args.summary_dir / f"tri_estimator_{args.init}_pooled.json").write_text(
        json.dumps(pooled_out, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print("\n=== Pooled (all scenarios x seeds), init=%s ===" % args.init)
    for eng in ENGINES:
        p = pooled_out[eng]
        print(f"  {eng:8s} n={p['n']:2d}  XY={p['xy_rmse_mean']:.3f}±{p['xy_rmse_std']:.3f}  "
              f"Z={p['z_rmse_mean']:.3f}±{p['z_rmse_std']:.3f}  "
              f"3D={p['rmse3d_mean']:.3f}±{p['rmse3d_std']:.3f}")
    print(f"\nWrote: {raw_csv}\n       {summary_csv}\n       {args.summary_dir}/tri_estimator_{args.init}_pooled.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

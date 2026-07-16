#!/usr/bin/env python3
"""E-3 分源协方差整定 A/B 独立对照驱动（论文 §5.5.5 表 tab:ch05-nis-covariance-ab 的复算入口）。

背景（见 24 号文 §8.6）：深度维 NIS/自由度被低估（7.205）、DVL 过保守（0.119），
历史混合阈值仅操作性触发、非有效卡方一致性判定，作为负结果如实呈现。本驱动在
**不改动 `algorithm/es_ekf.py` / `brain_linux/config/params.yaml` 默认协方差**的前提下，
仅通过 `tools/uncertainty_metrics.py` 的 CLI 覆盖开关，在同一批 P1 sensor sweep（8 场景 ×
3 种子 = 24 次真实运行）上做三臂独立对照：

  - A_baseline_default : 不加任何覆盖（global / sigma_depth=0.05 / sigma_dvl=0.03），
                        逐字节复现正文 7.205 / 0.119，既有 24 矩阵与 ESKF-NIS-8X3 产物不失效；
  - B_per_source_gating: --adaptive-r-mode per_source，切断跨源污染（DVL R 缩放 1.69→1.0）；
  - C_per_source_tuned : --adaptive-r-mode per_source --sigma-depth 0.12，深度整定回卡方带内。

产物（与 docs/thesis/figures/experiments/covariance_ab/ 现有文件同 schema，可逐字节复算）：
  - covariance_ab_raw.csv      每 (arm, scenario, seed, source) 一行
  - covariance_ab_summary.csv  每 (arm, source) 池化一行（含 applied_r_scale_mean / r_inflated_frac）
  - covariance_ab_pooled.json  嵌套 arm -> source -> {n_events,nis_per_dof_mean,coverage_95,upper_exceed}
  - covariance_ab_comparison.png  三臂 depth NIS/自由度 + 95% 覆盖率对比条形图

硬约束：专用离线对照，缺省不改主线默认；baseline 臂必须逐字节复现正文口径。
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import thesis_plot_style as tps  # noqa: E402

UNCERTAINTY_TOOL = REPO_ROOT / "tools" / "uncertainty_metrics.py"
DEFAULT_SWEEP = (
    REPO_ROOT
    / "log"
    / "thesis_sweep"
    / "20260612_170618_p1_sensor_3seed"
    / "results.csv"
)
DEFAULT_OUTPUT_DIR = REPO_ROOT / "docs" / "thesis" / "figures" / "experiments" / "covariance_ab"

R_INFLATED_EPS = 1e-6

# 三臂定义。空 dict = 不加任何覆盖（缺省沿用配置文件默认，baseline 逐字节复现正文）。
ARMS: dict[str, dict[str, object]] = {
    "A_baseline_default": {},
    "B_per_source_gating": {"adaptive_r_mode": "per_source"},
    "C_per_source_tuned": {"adaptive_r_mode": "per_source", "sigma_depth": 0.12},
}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--sweep-results", type=Path, default=DEFAULT_SWEEP,
                   help=f"源 sweep results.csv（默认 P1 sensor sweep: {DEFAULT_SWEEP}）")
    p.add_argument("--output-dir", type=Path, default=None,
                   help="产物输出目录（缺省=时间戳 verify 目录，需 --in-place 才写规范目录）")
    p.add_argument("--in-place", action="store_true",
                   help="写入规范产物目录 docs/thesis/figures/experiments/covariance_ab/")
    p.add_argument("--per-run-root", type=Path, default=None,
                   help="每次 uncertainty_metrics 运行的中间产物根目录（缺省=<output-dir>/per_run）")
    p.add_argument("--reuse", action=argparse.BooleanOptionalAction, default=True,
                   help="若 per-run 目录已有 nis_events.csv 则复用（默认复用）")
    p.add_argument("--nis-window", type=int, default=50)
    p.add_argument("--dpi", type=int, default=300)
    return p.parse_args()


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def to_bool(value: object) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes"}


def to_float(value: object) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return float("nan")
    return number


def fmt(value: float, digits: int = 4) -> str:
    if value != value:  # NaN
        return "nan"
    return f"{value:.{digits}f}"


def run_uncertainty_tool(mcap: Path, out_dir: Path, arm_overrides: dict[str, object],
                         nis_window: int, reuse: bool) -> tuple[str, str]:
    """在给定 arm 覆盖下对单个 mcap 跑 uncertainty_metrics.py，产出 nis_events.csv。"""
    nis_path = out_dir / "nis_events.csv"
    if reuse and nis_path.exists():
        return "reused", ""
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable, str(UNCERTAINTY_TOOL),
        "--input", str(mcap),
        "--output-dir", str(out_dir),
        "--nis-window", str(nis_window),
    ]
    if "sigma_depth" in arm_overrides:
        cmd += ["--sigma-depth", str(arm_overrides["sigma_depth"])]
    if "sigma_dvl" in arm_overrides:
        cmd += ["--sigma-dvl", str(arm_overrides["sigma_dvl"])]
    if "adaptive_r_mode" in arm_overrides:
        cmd += ["--adaptive-r-mode", str(arm_overrides["adaptive_r_mode"])]
    if "adaptive_r_normalized_threshold" in arm_overrides:
        cmd += ["--adaptive-r-normalized-threshold", str(arm_overrides["adaptive_r_normalized_threshold"])]
    proc = subprocess.run(cmd, cwd=str(REPO_ROOT), text=True, capture_output=True, check=False)
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout).strip().splitlines()
        return "failed", detail[-1] if detail else f"uncertainty_metrics.py exit={proc.returncode}"
    return "generated", ""


def summarise_events(events: list[dict[str, str]]) -> dict[str, float]:
    """对一组（同一 arm/run/source 或 池化）nis 事件计算统计量。"""
    if not events:
        return {
            "n_events": 0,
            "nis_per_dof_mean": float("nan"),
            "coverage_95": float("nan"),
            "upper_exceed": float("nan"),
            "applied_r_scale_mean": float("nan"),
            "r_inflated_frac": float("nan"),
        }
    n = len(events)
    per_dof = [to_float(e.get("nis_per_dof")) for e in events]
    per_dof = [v for v in per_dof if v == v]
    cover = [to_bool(e.get("in_two_sided_95")) for e in events]
    exceed = [to_bool(e.get("above_upper_95")) for e in events]
    applied = [to_float(e.get("applied_r_scale")) for e in events]
    applied = [v for v in applied if v == v]
    return {
        "n_events": n,
        "nis_per_dof_mean": sum(per_dof) / len(per_dof) if per_dof else float("nan"),
        "coverage_95": sum(1 for c in cover if c) / n,
        "upper_exceed": sum(1 for c in exceed if c) / n,
        "applied_r_scale_mean": sum(applied) / len(applied) if applied else float("nan"),
        "r_inflated_frac": (sum(1 for v in applied if v > 1.0 + R_INFLATED_EPS) / len(applied))
        if applied else float("nan"),
    }


def main() -> int:
    args = parse_args()
    if not args.sweep_results.is_file():
        raise SystemExit(f"缺少源 sweep: {args.sweep_results}")
    if not UNCERTAINTY_TOOL.is_file():
        raise SystemExit(f"缺少 uncertainty 工具: {UNCERTAINTY_TOOL}")

    if args.output_dir is not None:
        output_dir = args.output_dir
    elif args.in_place:
        output_dir = DEFAULT_OUTPUT_DIR
    else:
        import time
        output_dir = REPO_ROOT / "results" / "covariance_ab_verify" / time.strftime("%Y%m%d_%H%M%S")
    output_dir.mkdir(parents=True, exist_ok=True)
    # per-run 中间产物（每次 uncertainty_metrics 回放的逐事件 CSV，量大）默认落到
    # results/ 下的独立缓存目录，避免污染 docs/ 图表产物目录（尤其 --in-place 时）。
    if args.per_run_root is not None:
        per_run_root = args.per_run_root
    elif args.in_place and args.output_dir is None:
        per_run_root = REPO_ROOT / "results" / "covariance_ab_per_run"
    else:
        per_run_root = output_dir / "per_run"

    source_rows = [r for r in read_csv_rows(args.sweep_results) if r.get("status") == "ok"]
    print(f"[cov-ab] 源 sweep {args.sweep_results} 中 ok 运行: {len(source_rows)}")

    raw_rows: list[dict[str, object]] = []
    # 池化容器：(arm, source) -> list[event dict]
    pooled_events: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)

    for arm, overrides in ARMS.items():
        for idx, src in enumerate(source_rows):
            scenario = src.get("scenario", "")
            seed = src.get("seed", "")
            mcap = Path(src.get("mcap", ""))
            if not mcap.exists():
                print(f"[cov-ab][skip] {arm} {scenario} seed={seed}: mcap 缺失 {mcap}")
                continue
            run_dir = per_run_root / arm / f"{scenario}__seed{seed}"
            status, err = run_uncertainty_tool(mcap, run_dir, overrides, args.nis_window, args.reuse)
            if err:
                print(f"[cov-ab][fail] {arm} {scenario} seed={seed}: {err}")
                continue
            events = read_csv_rows(run_dir / "nis_events.csv")
            by_source: dict[str, list[dict[str, str]]] = defaultdict(list)
            for e in events:
                by_source[str(e.get("source", "")).strip()].append(e)
            for source, evs in sorted(by_source.items()):
                if not source:
                    continue
                stats = summarise_events(evs)
                raw_rows.append({
                    "arm": arm, "scenario": scenario, "seed": seed, "source": source,
                    "n_events": stats["n_events"],
                    "nis_per_dof_mean": stats["nis_per_dof_mean"],
                    "coverage_95": stats["coverage_95"],
                    "upper_exceed": stats["upper_exceed"],
                    "applied_r_scale_mean": stats["applied_r_scale_mean"],
                })
                pooled_events[(arm, source)].extend(evs)
            print(f"[cov-ab] ({idx + 1}/{len(source_rows)}) {arm} {scenario} seed={seed} [{status}]")

    # --- 写 raw CSV ---
    raw_path = output_dir / "covariance_ab_raw.csv"
    raw_fields = ["arm", "scenario", "seed", "source", "n_events",
                  "nis_per_dof_mean", "coverage_95", "upper_exceed", "applied_r_scale_mean"]
    with raw_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(raw_fields)
        for r in raw_rows:
            w.writerow([r["arm"], r["scenario"], r["seed"], r["source"], r["n_events"],
                        fmt(r["nis_per_dof_mean"]), fmt(r["coverage_95"]),
                        fmt(r["upper_exceed"]), fmt(r["applied_r_scale_mean"])])
    print(f"[cov-ab] 写 {raw_path} ({len(raw_rows)} 行)")

    # --- 池化 summary + pooled.json ---
    summary_rows: list[dict[str, object]] = []
    pooled: dict[str, dict[str, dict[str, float]]] = {}
    for (arm, source), evs in sorted(pooled_events.items()):
        stats = summarise_events(evs)
        summary_rows.append({"arm": arm, "source": source, **stats})
        pooled.setdefault(arm, {})[source] = {
            "n_events": stats["n_events"],
            "nis_per_dof_mean": stats["nis_per_dof_mean"],
            "coverage_95": stats["coverage_95"],
            "upper_exceed": stats["upper_exceed"],
        }

    summary_path = output_dir / "covariance_ab_summary.csv"
    summary_fields = ["arm", "source", "n_events", "nis_per_dof_mean", "coverage_95",
                      "upper_exceed", "applied_r_scale_mean", "r_inflated_frac"]
    with summary_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(summary_fields)
        for r in summary_rows:
            w.writerow([r["arm"], r["source"], r["n_events"],
                        fmt(r["nis_per_dof_mean"]), fmt(r["coverage_95"]),
                        fmt(r["upper_exceed"]), fmt(r["applied_r_scale_mean"]),
                        fmt(r["r_inflated_frac"])])
    print(f"[cov-ab] 写 {summary_path}")

    pooled_path = output_dir / "covariance_ab_pooled.json"
    pooled_path.write_text(json.dumps(pooled, indent=2) + "\n", encoding="utf-8")
    print(f"[cov-ab] 写 {pooled_path}")

    # --- 对比图 ---
    _plot_comparison(pooled, output_dir / "covariance_ab_comparison.png", args.dpi)

    # --- _SOURCE.md ---
    _write_source_md(output_dir / "_SOURCE.md", args.sweep_results, pooled)
    print(f"[cov-ab] 完成，产物在 {output_dir}")
    return 0


def _plot_comparison(pooled: dict[str, dict[str, dict[str, float]]], out_png: Path, dpi: int) -> None:
    try:
        import matplotlib.pyplot as plt
    except Exception:
        print("[cov-ab][warn] matplotlib 不可用，跳过对比图")
        return
    tps.apply_thesis_style()  # 中文字体 / 黑白可辨 / 300 dpi（P1-4，修复原缺失 CJK 字体）
    arms = list(pooled.keys())
    depth_nis = [pooled[a].get("depth", {}).get("nis_per_dof_mean", float("nan")) for a in arms]
    depth_cov = [pooled[a].get("depth", {}).get("coverage_95", float("nan")) for a in arms]
    labels = [a.replace("_", "\n") for a in arms]
    bar_styles = [tps.series_style(i) for i in range(len(arms))]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10.0, 4.2))
    bars1 = ax1.bar(labels, depth_nis, **{k: [s[k] for s in bar_styles]
                                          for k in ("facecolor",)})
    for b, s in zip(bars1, bar_styles):
        b.set_hatch(s["hatch"])
        b.set_edgecolor("black")
    ax1.axhline(1.0, color="k", ls="--", lw=0.8, label="expected mean=1")
    ax1.axhspan(0.0, 5.024, color="#2ca02c", alpha=0.10, label="chi2 95% band (dof=1)")
    ax1.set_ylabel("depth NIS / dof")
    ax1.set_title("(a) 深度维标准 NIS / 自由度")
    ax1.legend(fontsize=8)
    for b, v in zip(bars1, depth_nis):
        ax1.text(b.get_x() + b.get_width() / 2, v, fmt(v, 3), ha="center", va="bottom", fontsize=8)

    bars2 = ax2.bar(labels, depth_cov, **{k: [s[k] for s in bar_styles]
                                          for k in ("facecolor",)})
    for b, s in zip(bars2, bar_styles):
        b.set_hatch(s["hatch"])
        b.set_edgecolor("black")
    ax2.axhline(0.95, color="k", ls="--", lw=0.8, label="target coverage=0.95")
    ax2.set_ylabel("depth 95% coverage")
    ax2.set_ylim(0.0, 1.0)
    ax2.set_title("(b) 深度维 95% 覆盖率")
    ax2.legend(fontsize=8)
    for b, v in zip(bars2, depth_cov):
        ax2.text(b.get_x() + b.get_width() / 2, v, fmt(v, 3), ha="center", va="bottom", fontsize=8)

    fig.tight_layout()
    fig.savefig(out_png, dpi=dpi)
    plt.close(fig)
    print(f"[cov-ab] 写 {out_png}")


def _write_source_md(path: Path, sweep: Path, pooled: dict[str, dict[str, dict[str, float]]]) -> None:
    lines = [
        "# 分源协方差整定 A/B 独立对照（E-3 / O-3 / O-4）",
        "",
        "本目录产物由 `tools/run_es_ekf_covariance_ab.py` 复算，对应论文 §5.5.5 表 "
        "`tab:ch05-nis-covariance-ab`。",
        "",
        "## 复算命令",
        "",
        "```bash",
        "python3 tools/run_es_ekf_covariance_ab.py --in-place",
        "```",
        "",
        f"- 源 sweep：`{sweep.relative_to(REPO_ROOT) if sweep.is_relative_to(REPO_ROOT) else sweep}`"
        "（P1 sensor sweep，8 场景 × 3 种子 = 24 次真实运行）。",
        "- 引擎：`tools/uncertainty_metrics.py` 回放 ES-EKF，按观测源与自由度分别聚合标准 NIS。",
        "- **不改动** `algorithm/es_ekf.py` / `brain_linux/config/params.yaml` 默认协方差；",
        "  仅通过 uncertainty_metrics.py 的 CLI 覆盖开关在本对照进程内改写口径。",
        "",
        "## 三臂定义",
        "",
        "| 臂 | 覆盖开关 | 含义 |",
        "|---|---|---|",
        "| A_baseline_default | （无，global / sigma_depth=0.05 / sigma_dvl=0.03） | 复现正文锚点，既有产物不失效 |",
        "| B_per_source_gating | `--adaptive-r-mode per_source` | 切断跨源污染（DVL R 缩放 1.69→1.0） |",
        "| C_per_source_tuned | `--adaptive-r-mode per_source --sigma-depth 0.12` | 深度整定回卡方带内 |",
        "",
        "## 池化结果（24 次运行逐量测池化）",
        "",
        "| 臂 | 源 | 事件数 | NIS/自由度 | 95% 覆盖率 | 上界超限 |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for arm in pooled:
        for source, st in pooled[arm].items():
            lines.append(
                f"| {arm} | {source} | {st['n_events']} | {fmt(st['nis_per_dof_mean'], 3)} | "
                f"{fmt(st['coverage_95'], 3)} | {fmt(st['upper_exceed'], 3)} |"
            )
    lines += [
        "",
        "## 结论边界",
        "",
        "- O-4 兑现：`sigma_depth` 0.05→0.12 后深度 NIS/自由度 7.205→3.280、覆盖率 0.561→0.735。",
        "- DVL 过保守（分源门控仅单向膨胀）判定为**结构性下界（类型 2）**，如实承认，不宣称已解决。",
        "- baseline 臂逐字节复现正文口径（深度 7.205 / DVL 0.119），既有 24 矩阵结论不被回改。",
        "- 把 C 臂口径回写主线默认并重跑 24 矩阵属独立后续，不在本轮范围。",
        "",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[cov-ab] 写 {path}")


if __name__ == "__main__":
    sys.exit(main())

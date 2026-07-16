#!/usr/bin/env python3
"""传感器退化消融图：DVL/磁 dropout + 横流（27 号文 P1-3）。

本脚本\ **不产生新数据**\ ，而是把两批已在盘的、可复算的\ *真实运行*\ 产物汇成
论文 §5.5.5 的图配套件（表 ``tab:ch05-nis-eskf-multiscene`` 的可视化伴随）：

  1. **定位侧**：P1 sensor sweep（8 场景 × 3 种子 = 24 次真实 bag 回放，
     ``log/thesis_sweep/20260612_170618_p1_sensor_3seed/results.csv``）的
     水平/深度 RMSE 均值 ± 标准差，逐字节对应正文表数值；
  2. **一致性侧**：同一 sweep 的 NEES/NIS 聚合
     （``results/uncertainty_aggregates/20260820_p1_nees/summary_by_scenario_mode.csv``）
     的深度子空间 ANEES 与 95% 覆盖率。

诚实边界（必须与图同时写入正文）：
  * 水平 RMSE 不随 DVL 丢包比例单调（60% 反低于 30%），说明 30 s 片段、种子与
    观测时序主导数值差异，不能解读为"丢包越重误差越大"；此为 §5.5.5 既有结论。
  * 深度 ANEES 远大于 1（数百量级），反映\ **深度协方差被显著低估（过乐观）**\ ，
    是如实呈现的负结果（见 §5.5.5 NIS A/B 与语义审计），非精度断言。
  * DVL 底锁测地速，横流不直接偏置其观测；横流对定位的影响见声磁融合消融
    （``tools/run_fusion_ablation.py`` 的 ``current`` 场景，磁斜距系统性偏置）。

用法：
    python3 tools/plot_sensor_dropout_ablation.py            # 写规范 docs 目录
    python3 tools/plot_sensor_dropout_ablation.py --output-dir /tmp/x
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import thesis_plot_style as tps  # noqa: E402

DEFAULT_SWEEP = (
    REPO_ROOT / "log" / "thesis_sweep" / "20260612_170618_p1_sensor_3seed" / "results.csv"
)
DEFAULT_NEES = (
    REPO_ROOT / "results" / "uncertainty_aggregates" / "20260820_p1_nees"
    / "summary_by_scenario_mode.csv"
)
DEFAULT_OUTPUT_DIR = REPO_ROOT / "docs" / "thesis" / "figures" / "experiments" / "sensor_dropout"

# 场景展示顺序与中文标签（与正文 §5.5.5 表一致）。
SCENARIO_ORDER = [
    ("dvl_dropout_10", "DVL 丢包 10%", "dvl"),
    ("dvl_dropout_30", "DVL 丢包 30%", "dvl"),
    ("dvl_dropout_60", "DVL 丢包 60%", "dvl"),
    ("dvl_dropout_90", "DVL 丢包 90%", "dvl"),
    ("mag_distortion_light", "磁畸变·轻度", "mag"),
    ("mag_distortion_heavy", "磁畸变·重度", "mag"),
    ("sonar_clutter", "声呐杂波", "other"),
    ("combined_stress", "综合压力(含横流)", "other"),
]
FAMILY_INDEX = {"dvl": 0, "mag": 1, "other": 2}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--sweep-results", type=Path, default=DEFAULT_SWEEP)
    p.add_argument("--nees-summary", type=Path, default=DEFAULT_NEES)
    p.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return p.parse_args()


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def sweep_stats(sweep_rows: list[dict[str, str]]) -> dict[str, dict[str, float]]:
    """按场景聚合水平/深度 RMSE 与成功率（样本标准差，匹配正文表）。"""
    by: dict[str, list[dict[str, str]]] = {}
    for row in sweep_rows:
        by.setdefault(row["scenario"], []).append(row)
    out: dict[str, dict[str, float]] = {}
    for scenario, items in by.items():
        ok = [it for it in items if it.get("status") == "ok"]
        xy = [float(it["xy_rmse"]) for it in ok if it.get("xy_rmse")]
        z = [float(it["z_rmse"]) for it in ok if it.get("z_rmse")]
        out[scenario] = {
            "n": float(len(items)),
            "n_ok": float(len(ok)),
            "xy_mean": float(np.mean(xy)) if xy else float("nan"),
            "xy_std": float(np.std(xy, ddof=1)) if len(xy) >= 2 else 0.0,
            "z_mean": float(np.mean(z)) if z else float("nan"),
            "z_std": float(np.std(z, ddof=1)) if len(z) >= 2 else 0.0,
        }
    return out


def nees_stats(nees_rows: list[dict[str, str]]) -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {}
    for row in nees_rows:
        out[row["scenario"]] = {
            "anees_depth": float(row.get("anees_depth_mean", "nan") or "nan"),
            "anees_depth_std": float(row.get("anees_depth_std", "0") or "0"),
            "cov95": float(row.get("anees_depth_coverage_95_mean", "nan") or "nan"),
        }
    return out


def build_figure(out_dir: Path, sweep: dict[str, dict[str, float]],
                 nees: dict[str, dict[str, float]]) -> list[Path]:
    import matplotlib.pyplot as plt

    tps.apply_thesis_style()
    scenarios = [(k, lbl, fam) for k, lbl, fam in SCENARIO_ORDER if k in sweep]
    labels = [lbl for _, lbl, _ in scenarios]
    fams = [FAMILY_INDEX[fam] for _, _, fam in scenarios]
    x = np.arange(len(scenarios))

    fig, axes = plt.subplots(1, 3, figsize=(16.0, 4.8))

    # (a) 水平 RMSE，按扰动族着色/纹理，明示"非单调"。
    ax = axes[0]
    for xi, (key, _lbl, _fam), fam_idx in zip(x, scenarios, fams):
        ax.bar(xi, sweep[key]["xy_mean"], 0.72,
               yerr=sweep[key]["xy_std"], capsize=3, **tps.series_style(fam_idx))
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=25, ha="right")
    ax.set_ylabel("水平面 RMSE [m]")
    ax.set_title("(a) 定位误差·多种子（均值±std, n=3）")
    # 图例：三族各一条代理句柄。
    from matplotlib.patches import Patch
    legend_handles = [
        Patch(label="DVL 丢包", **tps.series_style(0)),
        Patch(label="磁畸变", **tps.series_style(1)),
        Patch(label="声呐/综合", **tps.series_style(2)),
    ]
    ax.legend(handles=legend_handles, fontsize=9, loc="upper left")

    # (b) 深度 RMSE（同源同表）。
    ax = axes[1]
    for xi, (key, _lbl, _fam), fam_idx in zip(x, scenarios, fams):
        ax.bar(xi, sweep[key]["z_mean"], 0.72,
               yerr=sweep[key]["z_std"], capsize=3, **tps.series_style(fam_idx))
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=25, ha="right")
    ax.set_ylabel("深度 RMSE [m]")
    ax.set_title("(b) 深度误差·多种子（均值±std, n=3）")

    # (c) 深度子空间 ANEES（对数轴），红线标注理论期望 1，直陈"协方差过乐观"。
    ax = axes[2]
    have_nees = [k for k, _l, _f in scenarios if k in nees]
    if have_nees:
        for xi, (key, _lbl, _fam), fam_idx in zip(x, scenarios, fams):
            val = nees.get(key, {}).get("anees_depth", float("nan"))
            if math.isfinite(val):
                ax.bar(xi, val, 0.72,
                       yerr=nees[key].get("anees_depth_std", 0.0), capsize=3,
                       **tps.series_style(fam_idx))
        ax.set_yscale("log")
        ax.axhline(1.0, color="#c44e52", linestyle="--", linewidth=1.5, label="理论期望 ANEES=1")
        ax.set_xticks(x)
        ax.set_xticklabels(labels, rotation=25, ha="right")
        ax.set_ylabel("深度子空间 ANEES（对数轴）")
        ax.set_title("(c) 深度协方差一致性（>1 即过乐观）")
        ax.legend(fontsize=9, loc="upper right")
    else:
        ax.set_axis_off()
        ax.text(0.5, 0.5, "无 NEES 聚合产物", ha="center", va="center")

    fig.suptitle("传感器退化多场景消融：定位精度与协方差一致性（P1 sensor sweep，24 次真实运行）", y=1.03)
    fig.tight_layout()
    written = tps.save_figure(fig, out_dir / "figures" / "sensor_dropout_ablation")
    plt.close(fig)
    return written


def write_summary_csv(out_dir: Path, sweep: dict[str, dict[str, float]],
                      nees: dict[str, dict[str, float]]) -> Path:
    path = out_dir / "sensor_dropout_summary.csv"
    fields = ["scenario", "label", "family", "n_ok", "xy_rmse_mean", "xy_rmse_std",
              "z_rmse_mean", "z_rmse_std", "anees_depth", "anees_depth_coverage_95"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for key, label, fam in SCENARIO_ORDER:
            if key not in sweep:
                continue
            s = sweep[key]
            nz = nees.get(key, {})
            writer.writerow({
                "scenario": key, "label": label, "family": fam,
                "n_ok": int(s["n_ok"]),
                "xy_rmse_mean": f"{s['xy_mean']:.4f}", "xy_rmse_std": f"{s['xy_std']:.4f}",
                "z_rmse_mean": f"{s['z_mean']:.4f}", "z_rmse_std": f"{s['z_std']:.4f}",
                "anees_depth": f"{nz.get('anees_depth', float('nan')):.4f}",
                "anees_depth_coverage_95": f"{nz.get('cov95', float('nan')):.4f}",
            })
    return path


def main() -> int:
    args = parse_args()
    if not args.sweep_results.is_file():
        raise SystemExit(f"缺少 sweep 结果: {args.sweep_results}")
    sweep = sweep_stats(read_rows(args.sweep_results))
    nees = nees_stats(read_rows(args.nees_summary)) if args.nees_summary.is_file() else {}
    if not nees:
        print(f"[dropout][warn] 无 NEES 聚合 {args.nees_summary}，(c) 面板将留空")

    out_dir = args.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    figs = build_figure(out_dir, sweep, nees)
    csv_path = write_summary_csv(out_dir, sweep, nees)
    (out_dir / "sensor_dropout_summary.json").write_text(
        json.dumps({
            "schema_version": 1,
            "sweep_source": str(args.sweep_results),
            "nees_source": str(args.nees_summary) if nees else None,
            "scenarios": {k: {**sweep[k], **({"nees": nees[k]} if k in nees else {})}
                          for k, _l, _f in SCENARIO_ORDER if k in sweep},
        }, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    print(f"[dropout] 图 -> {figs}")
    print(f"[dropout] 表 -> {csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

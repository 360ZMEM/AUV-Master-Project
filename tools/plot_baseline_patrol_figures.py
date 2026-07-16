#!/usr/bin/env python3
"""Baseline patrol 7-figure set + controller comparison table (27 号文 §2, 组 A).

Consumes the derived tables produced by ``tools/export_sim_run_tables.py`` (one
run's ``tables/`` directory) and renders the seven baseline-patrol figures the
experiment-upgrade plan calls for:

  fig_5_2_1  轨迹 vs 海缆       trajectory.csv  (est/truth XY, optional cable overlay)
  fig_5_2_2  横向误差-t         trajectory.csv  (cross_track_error_m)
  fig_5_2_3  航向误差-t         trajectory.csv  (est_yaw - truth_yaw)
  fig_5_2_4  控制输入-t         controller.csv  (fins + thrust)
  fig_5_2_5  BT 状态时间线      behavior_tree.csv
  fig_5_2_6  EKF 协方差-t       estimator.csv   (cov_trace xy/z)
  fig_5_2_7  控制器对比表       --controller-summary CSV (PID/MPC/UA-MPC)

Design contract:
  * Purely a rendering layer over the derived tables — it does not touch bags,
    estimators or controllers. All plotted values come straight from the CSVs;
    ``not_observed`` / non-finite cells are skipped, never fabricated.
  * Matplotlib style is shared with ``tools/plot_terrain_following_figures.py``
    (CJK font injection, journal-grade rcParams) so figures match the thesis.
  * Every figure is written as both ``.png`` and ``.pdf``; a manifest.json records
    which figures had real data vs were skipped for a missing source column.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Any, Sequence

import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import analyze_bag as ab  # noqa: E402  (reuse matplotlib bootstrap)

NOT_OBSERVED = "not_observed"


# ---------------------------------------------------------------------------
# Style (shared convention with plot_terrain_following_figures.py)
# ---------------------------------------------------------------------------
def setup_style():
    ab.ensure_runtime_dependencies()
    plt = ab.plt
    import os
    import matplotlib.font_manager as fm
    zh_font = "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"
    if os.path.exists(zh_font):
        fm.fontManager.addfont(zh_font)
        plt.rcParams["font.family"] = fm.FontProperties(fname=zh_font).get_name()
    else:
        plt.rcParams["font.sans-serif"] = ["WenQuanYi Zen Hei", "SimHei"] + plt.rcParams["font.sans-serif"]
    plt.rcParams.update({
        "font.size": 12, "axes.titlesize": 14, "axes.labelsize": 12,
        "xtick.labelsize": 11, "ytick.labelsize": 11, "legend.fontsize": 10,
        "figure.dpi": 160, "savefig.dpi": 300,
        "axes.spines.top": False, "axes.spines.right": False,
        "axes.grid": True, "grid.alpha": 0.25, "axes.unicode_minus": False,
    })
    return plt


# ---------------------------------------------------------------------------
# CSV helpers
# ---------------------------------------------------------------------------
def read_table(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def col_float(rows: Sequence[dict[str, str]], key: str) -> list[float]:
    out: list[float] = []
    for row in rows:
        raw = row.get(key, "")
        if raw in ("", NOT_OBSERVED, "nan", None):
            out.append(float("nan"))
            continue
        try:
            out.append(float(raw))
        except (TypeError, ValueError):
            out.append(float("nan"))
    return out


def has_finite(values: Sequence[float]) -> bool:
    return any(math.isfinite(v) for v in values)


def save(fig, out_dir: Path, stem: str) -> list[str]:
    written = []
    for ext in ("png", "pdf"):
        target = out_dir / f"{stem}.{ext}"
        fig.savefig(target, bbox_inches="tight")
        written.append(str(target))
    return written


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------
def fig_trajectory(plt, traj, cable_xy, out_dir, stem) -> bool:
    est_x = col_float(traj, "est_x")
    est_y = col_float(traj, "est_y")
    tru_x = col_float(traj, "truth_x")
    tru_y = col_float(traj, "truth_y")
    if not has_finite(est_x):
        return False
    fig, ax = plt.subplots(figsize=(7.2, 6.0))
    if cable_xy is not None and len(cable_xy):
        ax.plot(cable_xy[:, 0], cable_xy[:, 1], color="#8c8c8c", lw=3.0,
                alpha=0.6, label="海缆参考", zorder=1)
    if has_finite(tru_x):
        ax.plot(tru_x, tru_y, color="#2ca02c", lw=1.8, ls="--",
                label="真值路径", zorder=2)
    ax.plot(est_x, est_y, color="#1f77b4", lw=1.8, label="ES-EKF 估计轨迹", zorder=3)
    ax.scatter([est_x[0]], [est_y[0]], c="#1f77b4", marker="o", s=45,
               zorder=4, label="起点")
    ax.set_xlabel("X [m]"); ax.set_ylabel("Y [m]")
    ax.set_title("基准巡检轨迹与海缆参考")
    ax.set_aspect("equal", adjustable="datalim")
    ax.legend(loc="best")
    save(fig, out_dir, stem); plt.close(fig)
    return True


def fig_cross_track(plt, traj, out_dir, stem) -> bool:
    t = col_float(traj, "t_s")
    err = col_float(traj, "cross_track_error_m")
    if not has_finite(err):
        return False
    finite = [v for v in err if math.isfinite(v)]
    rmse = math.sqrt(sum(v * v for v in finite) / len(finite))
    fig, ax = plt.subplots(figsize=(8.4, 4.2))
    ax.plot(t, err, color="#d62728", lw=1.4)
    ax.axhline(0.0, color="#444444", lw=0.8, ls=":")
    ax.set_xlabel("时间 [s]"); ax.set_ylabel("横向误差 [m]")
    ax.set_title(f"横向跟踪误差（RMSE = {rmse:.3g} m）")
    save(fig, out_dir, stem); plt.close(fig)
    return True


def _wrap_angle(delta: float) -> float:
    return math.atan2(math.sin(delta), math.cos(delta))


def fig_heading_error(plt, traj, out_dir, stem) -> bool:
    t = col_float(traj, "t_s")
    est_yaw = col_float(traj, "est_yaw_rad")
    tru_yaw = col_float(traj, "truth_yaw_rad")
    if not (has_finite(est_yaw) and has_finite(tru_yaw)):
        return False
    err_deg = []
    for e, r in zip(est_yaw, tru_yaw):
        if math.isfinite(e) and math.isfinite(r):
            err_deg.append(math.degrees(_wrap_angle(e - r)))
        else:
            err_deg.append(float("nan"))
    if not has_finite(err_deg):
        return False
    fig, ax = plt.subplots(figsize=(8.4, 4.2))
    ax.plot(t, err_deg, color="#9467bd", lw=1.4)
    ax.axhline(0.0, color="#444444", lw=0.8, ls=":")
    ax.set_xlabel("时间 [s]"); ax.set_ylabel("航向误差 [°]")
    ax.set_title("航向跟踪误差（估计相对真值）")
    save(fig, out_dir, stem); plt.close(fig)
    return True


def fig_control_inputs(plt, ctrl, out_dir, stem) -> bool:
    t = col_float(ctrl, "t_s")
    if not t:
        return False
    fins = {
        "右舵": ("right_fin_deg", "#1f77b4"),
        "上舵": ("top_fin_deg", "#ff7f0e"),
        "左舵": ("left_fin_deg", "#2ca02c"),
        "下舵": ("bottom_fin_deg", "#d62728"),
    }
    thrust = col_float(ctrl, "thrust_percent")
    plotted = False
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(8.4, 6.4), sharex=True)
    for label, (key, color) in fins.items():
        values = col_float(ctrl, key)
        if has_finite(values):
            ax1.plot(t, values, lw=1.3, color=color, label=label)
            plotted = True
    ax1.set_ylabel("舵角 [°]"); ax1.set_title("控制输入时序")
    ax1.legend(loc="upper right", ncol=4)
    if has_finite(thrust):
        ax2.plot(t, thrust, lw=1.4, color="#17becf", label="推力")
        plotted = True
    ax2.set_xlabel("时间 [s]"); ax2.set_ylabel("推力 [%]")
    ax2.legend(loc="upper right")
    if not plotted:
        plt.close(fig)
        return False
    save(fig, out_dir, stem); plt.close(fig)
    return True


def fig_bt_timeline(plt, bt, out_dir, stem) -> bool:
    if not bt:
        return False
    t = col_float(bt, "t_s")
    states = [row.get("state", "") for row in bt]
    if not any(states):
        return False
    unique = list(dict.fromkeys(states))
    y_of = {state: i for i, state in enumerate(unique)}
    fig, ax = plt.subplots(figsize=(8.4, max(2.6, 0.55 * len(unique) + 1.6)))
    # Step plot of active state; hold each state until next sample.
    xs, ys = [], []
    for i, (ti, st) in enumerate(zip(t, states)):
        xs.append(ti); ys.append(y_of[st])
        if i + 1 < len(t):
            xs.append(t[i + 1]); ys.append(y_of[st])
    ax.step(xs, ys, where="post", color="#1f77b4", lw=1.8)
    ax.scatter(t, [y_of[s] for s in states], color="#d62728", s=22, zorder=3)
    ax.set_yticks(range(len(unique)))
    ax.set_yticklabels(unique)
    ax.set_xlabel("时间 [s]"); ax.set_title("行为树状态时间线")
    ax.grid(axis="y", alpha=0.3)
    save(fig, out_dir, stem); plt.close(fig)
    return True


def fig_covariance(plt, est, out_dir, stem) -> bool:
    t = col_float(est, "t_s")
    p_xy = col_float(est, "cov_trace_xy")
    p_z = col_float(est, "cov_trace_z")
    if not (has_finite(p_xy) or has_finite(p_z)):
        return False
    fig, ax = plt.subplots(figsize=(8.4, 4.2))
    if has_finite(p_xy):
        ax.plot(t, p_xy, color="#1f77b4", lw=1.5, label=r"tr$(P_{xy})$")
    if has_finite(p_z):
        ax.plot(t, p_z, color="#d62728", lw=1.5, label=r"$P_{zz}$")
    ax.set_xlabel("时间 [s]"); ax.set_ylabel("协方差迹 [m²]")
    ax.set_title("ES-EKF 位置协方差演化")
    ax.legend(loc="best")
    save(fig, out_dir, stem); plt.close(fig)
    return True


def _fmt_cell(value: str) -> str:
    if value in ("", NOT_OBSERVED, None):
        return "—"
    try:
        f = float(value)
        if math.isnan(f):
            return "—"
        return f"{f:.3g}"
    except (TypeError, ValueError):
        return str(value)


def fig_controller_table(plt, summary_path: Path, out_dir, stem) -> bool:
    rows = read_table(summary_path)
    if not rows:
        return False
    # Pick the columns most relevant to a PID/MPC/UA-MPC comparison; degrade
    # gracefully if some are absent in the provided aggregate.
    label_col = "mpc_mode" if "mpc_mode" in rows[0] else ("mode" if "mode" in rows[0] else None)
    preferred = [
        ("lateral_error_rmse_m_mean", "横向 RMSE [m]"),
        ("lateral_error_mean_abs_m_mean", "横向 MAE [m]"),
        ("mpc_solve_time_mean_ms_mean", "求解均值 [ms]"),
        ("mpc_solve_time_p95_ms_mean", "求解 P95 [ms]"),
        ("fallback_rate_mean", "回退率"),
        ("control_effort_mean_mean", "控制努力"),
        ("safety_violation_rate_mean", "安全越界率"),
    ]
    metric_cols = [(k, h) for k, h in preferred if k in rows[0]]
    if label_col is None or not metric_cols:
        return False

    # Aggregate across scenarios per mode (mean of available means).
    by_mode: dict[str, dict[str, list[float]]] = {}
    for row in rows:
        mode = row.get(label_col, "") or "?"
        bucket = by_mode.setdefault(mode, {k: [] for k, _ in metric_cols})
        for k, _ in metric_cols:
            try:
                val = float(row.get(k, "nan"))
            except (TypeError, ValueError):
                val = float("nan")
            if math.isfinite(val):
                bucket[k].append(val)

    header = ["控制器"] + [h for _, h in metric_cols]
    table_rows = []
    for mode in sorted(by_mode):
        cells = [mode]
        for k, _ in metric_cols:
            vals = by_mode[mode][k]
            cells.append(_fmt_cell(str(sum(vals) / len(vals)) if vals else NOT_OBSERVED))
        table_rows.append(cells)

    fig, ax = plt.subplots(figsize=(max(8.0, 1.5 * len(header)), 0.6 * len(table_rows) + 1.4))
    ax.axis("off")
    tbl = ax.table(cellText=table_rows, colLabels=header, loc="center", cellLoc="center")
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(10)
    tbl.scale(1.0, 1.5)
    for c in range(len(header)):
        tbl[(0, c)].set_facecolor("#e6eef7")
        tbl[(0, c)].set_text_props(weight="bold")
    ax.set_title("控制器对比（PID / MPC / UA-MPC，跨场景均值）", pad=14)
    save(fig, out_dir, stem); plt.close(fig)
    return True


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------
def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--tables-dir", type=Path, required=True,
                        help="export_sim_run_tables.py 产出的 tables/ 目录")
    parser.add_argument("--output-dir", type=Path, required=True,
                        help="图输出目录（建议 docs/thesis/figures/chapter5）")
    parser.add_argument("--prefix", default="fig_5_2",
                        help="图文件名前缀（默认 fig_5_2）")
    parser.add_argument("--controller-summary", type=Path, default=None,
                        help="控制器对比聚合 CSV（如 control_summary_by_scenario_mode.csv）")
    parser.add_argument("--cable-csv", type=Path, default=None,
                        help="可选海缆参考几何 CSV（列 x,y）")
    parser.add_argument("--quiet", action="store_true")
    return parser.parse_args(argv)


def _load_cable(path: Path | None):
    if path is None or not path.is_file():
        return None
    import numpy as np
    rows = read_table(path)
    pts = []
    for row in rows:
        try:
            pts.append((float(row["x"]), float(row["y"])))
        except (KeyError, TypeError, ValueError):
            continue
    return np.asarray(pts, dtype=float) if pts else None


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    plt = setup_style()
    out = args.output_dir
    out.mkdir(parents=True, exist_ok=True)

    tables = args.tables_dir
    traj = read_table(tables / "trajectory.csv")
    est = read_table(tables / "estimator.csv")
    ctrl = read_table(tables / "controller.csv")
    bt = read_table(tables / "behavior_tree.csv")
    cable_xy = _load_cable(args.cable_csv)

    p = args.prefix
    results = {
        f"{p}_1_trajectory": fig_trajectory(plt, traj, cable_xy, out, f"{p}_1_trajectory"),
        f"{p}_2_cross_track": fig_cross_track(plt, traj, out, f"{p}_2_cross_track"),
        f"{p}_3_heading_error": fig_heading_error(plt, traj, out, f"{p}_3_heading_error"),
        f"{p}_4_control_inputs": fig_control_inputs(plt, ctrl, out, f"{p}_4_control_inputs"),
        f"{p}_5_bt_timeline": fig_bt_timeline(plt, bt, out, f"{p}_5_bt_timeline"),
        f"{p}_6_covariance": fig_covariance(plt, est, out, f"{p}_6_covariance"),
        f"{p}_7_controller_table": (
            fig_controller_table(plt, args.controller_summary, out, f"{p}_7_controller_table")
            if args.controller_summary else False
        ),
    }

    manifest = {
        "schema_version": 1,
        "tables_dir": str(tables),
        "controller_summary": str(args.controller_summary) if args.controller_summary else None,
        "cable_csv": str(args.cable_csv) if args.cable_csv else None,
        "figures": {name: ("written" if ok else "skipped_no_data")
                    for name, ok in results.items()},
    }
    (out / f"{p}_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    written = sum(1 for ok in results.values() if ok)
    if not args.quiet:
        print(f"[plot] {written}/{len(results)} figures written -> {out}")
        for name, ok in results.items():
            print(f"  [{'ok ' if ok else '-- '}] {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

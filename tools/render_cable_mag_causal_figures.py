#!/usr/bin/env python3
"""Render the three cable-magnetic causal figures for §5.5.11 (Chinese labels).

Redrawn in the main-repo convention (WenQuanYi CJK) from the dedicated magnetic
detection sub-repo. Data provenance:

  * pure-magnetic failure time series -- re-runs the sub-repo deterministic
    simulation (baseline vs online-prior-correction ablated) under the heavy
    distorted prior; reproduces the +57.5 m lane-shortcut jump and the health /
    completion drop already quoted in the thesis.
  * D4 projection-vs-alignment decoupling -- reads
    results/20260705_lane_shortcut/lane_shortcut_prior_alignment_{70,50}.csv.
  * tuned zig-zag burial trade-off -- reads
    results/20260705_zigzag_burial/zigzag_burial_tuning_focused.csv.

All three describe the *algorithm-level* (single-run, pure-simulation) boundary
of the same-source cable detection algorithm; captions in the thesis keep that
evidence tier explicit.

Output:
  docs/thesis/figures/experiments/cable_mag_integration/<stem>.{png,pdf}
"""
from __future__ import annotations

import copy
import csv
import os
import sys
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

MAIN_ROOT = Path(__file__).resolve().parents[1]
SUBREPO = MAIN_ROOT / "AUV-Master-Mag"
OUT_DIR = MAIN_ROOT / "docs/thesis/figures/experiments/cable_mag_integration"

LANE_CSV = (
    SUBREPO / "results/20260705_lane_shortcut/lane_shortcut_prior_alignment_70.csv",
    SUBREPO / "results/20260705_lane_shortcut/lane_shortcut_prior_alignment_50.csv",
)
ZIGZAG_TUNING_CSV = (
    SUBREPO / "results/20260705_zigzag_burial/zigzag_burial_tuning_focused.csv",
    SUBREPO / "results/20260705_zigzag_burial/zigzag_burial_tuning_shallow_mid.csv",
    SUBREPO / "results/20260705_zigzag_burial/zigzag_burial_tuning_depth2.csv",
)

C_BASE = "#2C6DA4"
C_ABL = "#C0392B"
C_MAP = "#4C8C68"
C_ALIGN = "#8172B3"
C_GRAY = "#5F6368"


def _setup_font() -> None:
    import matplotlib.font_manager as fm

    zh_font = "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"
    if os.path.exists(zh_font):
        fm.fontManager.addfont(zh_font)
        plt.rcParams["font.family"] = fm.FontProperties(fname=zh_font).get_name()
    plt.rcParams["font.sans-serif"] = ["WenQuanYi Zen Hei", "SimHei"] + plt.rcParams["font.sans-serif"]
    plt.rcParams["axes.unicode_minus"] = False
    plt.rcParams["mathtext.fontset"] = "stix"
    plt.rcParams["axes.grid"] = True
    plt.rcParams["grid.alpha"] = 0.25
    plt.rcParams["figure.facecolor"] = "white"
    plt.rcParams["savefig.facecolor"] = "white"


def _save(fig, stem: str) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for ext in ("png", "pdf"):
        fig.savefig(OUT_DIR / f"{stem}.{ext}", dpi=200, bbox_inches="tight")
    plt.close(fig)
    print("wrote", OUT_DIR / f"{stem}.{{png,pdf}}")


# ---------------------------------------------------------------------------
# (1) pure-magnetic failure time series
# ---------------------------------------------------------------------------
def render_failure_timeseries() -> None:
    if str(SUBREPO / "src") not in sys.path:
        sys.path.insert(0, str(SUBREPO / "src"))
    from auv_mag_tracking.viz.recorder import simulate_run
    from auv_mag_tracking.config import build_default_scenarios

    scenarios = build_default_scenarios()
    base = scenarios["case_maze_sonar_dropout_prior_heavy"]
    record_ok = simulate_run(base)

    ablated = copy.deepcopy(base)
    ablated.name = base.name + "__no_prior_correction"
    ablated.tracking.nominal_route_prior_observation_correction_enabled = False
    record_bad = simulate_run(ablated)

    def xt(r):
        return np.hypot(
            np.asarray(r["pos_x_m"]) - np.asarray(r["true_nearest_x_m"]),
            np.asarray(r["pos_y_m"]) - np.asarray(r["true_nearest_y_m"]),
        )

    t_ok = np.asarray(record_ok["time_s"])
    t_bad = np.asarray(record_bad["time_s"])
    xt_ok, xt_bad = xt(record_ok), xt(record_bad)
    rp_ok = np.asarray(record_ok["route_progress_m"])
    rp_bad = np.asarray(record_bad["route_progress_m"])

    deltas = np.diff(rp_bad)
    finite = np.isfinite(deltas)
    j = int(np.argmax(np.where(finite, deltas, -np.inf)))
    jump_t = float(t_bad[j + 1])
    jump_val = float(deltas[j])

    _setup_font()
    fig, (ax_xt, ax_rp) = plt.subplots(2, 1, figsize=(7.2, 5.4), sharex=True)

    ax_xt.plot(t_ok, xt_ok, color=C_BASE, lw=1.5, label="基线（在线先验修正 开）")
    ax_xt.plot(t_bad, xt_bad, color=C_ABL, lw=1.5, label="消融（在线先验修正 关）")
    ax_xt.set_ylabel("横向偏移（m）")
    ax_xt.set_title("重档畸变先验下纯磁失效时序（关闭在线先验修正）")
    ax_xt.legend(loc="upper left")

    ax_rp.plot(t_ok, rp_ok, color=C_BASE, lw=1.5, label="基线 路由进度")
    ax_rp.plot(t_bad, rp_bad, color=C_ABL, lw=1.5, label="消融 路由进度")
    if jump_val > 25.0:
        ax_rp.axvline(jump_t, color="#555555", ls="--", lw=1.0)
        ax_rp.annotate(
            f"跨车道跳变\n+{jump_val:.1f} m @ {jump_t:.0f} s",
            xy=(jump_t, float(rp_bad[j + 1])),
            xytext=(0.5, 0.25), textcoords="axes fraction", fontsize=8.5,
            arrowprops=dict(arrowstyle="->", color="#555555", lw=0.9),
        )
    ax_rp.set_ylabel("路由进度（m）")
    ax_rp.set_xlabel("时间（s）")
    ax_rp.legend(loc="upper left")

    fig.tight_layout()
    _save(fig, "pure_magnetic_failure_timeseries")


# ---------------------------------------------------------------------------
# (2) D4 projection-vs-alignment decoupling
# ---------------------------------------------------------------------------
def _read_lane_rows():
    rows = []
    for path in LANE_CSV:
        with path.open(encoding="utf-8") as fh:
            rows.extend(csv.DictReader(fh))
    rows.sort(key=lambda r: (float(r["lane_spacing_m"]), r["variant"]))
    return rows


def render_prior_alignment_decoupling() -> None:
    rows = _read_lane_rows()
    spacings = sorted({int(float(r["lane_spacing_m"])) for r in rows})
    x = np.arange(len(spacings))
    width = 0.34

    def series(variant, key):
        return [float(r[key]) for r in rows if r["variant"] == variant]

    _setup_font()
    fig, (ax_jump, ax_align) = plt.subplots(1, 2, figsize=(9.0, 3.9),
                                            constrained_layout=True)

    # left: global route jump vs map-frame projection jump (log scale)
    a_route = series("no_prior_correction", "route_progress_max_jump_m")
    a_map = series("no_prior_correction", "map_frame_progress_max_jump_m")
    ax_jump.bar(x - width / 2, a_route, width, color=C_ABL, label="全局路由进度跳变")
    ax_jump.bar(x + width / 2, a_map, width, color=C_MAP, label="地图系投影跳变")
    ax_jump.set_yscale("log")
    ax_jump.set_ylim(0.1, 3.0e3)
    ax_jump.set_ylabel("最大跳变（m，对数轴）")
    ax_jump.set_title("(a) 关闭在线先验修正：投影连续但任务失败")
    ax_jump.set_xticks(x)
    ax_jump.set_xticklabels([f"{s} m 车道间距" for s in spacings])
    ax_jump.legend(loc="center right")
    for xi, yi in zip(x - width / 2, a_route):
        ax_jump.annotate(f"{yi:.1f}", xy=(xi, yi), xytext=(0, 3),
                         textcoords="offset points", ha="center", fontsize=8)
    for xi, yi in zip(x + width / 2, a_map):
        ax_jump.annotate(f"{yi:.1f}", xy=(xi, yi), xytext=(0, 3),
                         textcoords="offset points", ha="center", fontsize=8)

    # right: physical alignment (translation + rotation) is what actually pulls
    b_trans = series("baseline", "prior_alignment_final_translation_m")
    a_trans = series("no_prior_correction", "prior_alignment_final_translation_m")
    b_rot = series("baseline", "prior_alignment_final_rotation_deg")
    ax_align.bar(x - width / 2, b_trans, width, color=C_ALIGN, label="基线 平移修正")
    ax_align.bar(x + width / 2, a_trans, width, color="#D0D0D0", label="消融 平移修正")
    ax_align.set_ylim(0.0, max(b_trans + a_trans) + 2.0)
    ax_align.set_ylabel("累计平移修正（m）")
    ax_align.set_title("(b) 物理配准（平移/旋转）才是把地图拉回的状态")
    ax_align.set_xticks(x)
    ax_align.set_xticklabels([f"{s} m 车道间距" for s in spacings])
    ax_align.legend(loc="upper left")
    ax_rot = ax_align.twinx()
    ax_rot.plot(x, b_rot, "o--", color=C_GRAY, lw=1.3, label="基线 旋转修正")
    ax_rot.set_ylabel("旋转修正（度）")
    ax_rot.grid(False)
    for xi, yi in zip(x - width / 2, b_trans):
        ax_align.annotate(f"{yi:.2f} m", xy=(xi, yi), xytext=(0, 3),
                          textcoords="offset points", ha="center", fontsize=8)
    for xi, yi in zip(x, b_rot):
        ax_rot.annotate(f"{yi:.2f}°", xy=(xi, yi), xytext=(0, -13),
                        textcoords="offset points", ha="center", fontsize=8)

    fig.suptitle("地图系投影安全与在线先验配准的解耦", fontsize=11)
    _save(fig, "prior_alignment_decoupling")


# ---------------------------------------------------------------------------
# (3) tuned zig-zag burial trade-off (full 20--36 deg envelope)
# ---------------------------------------------------------------------------
def _read_zigzag_rows():
    """Merge the tuning sweeps into one (angle, depth) -> metrics table.

    The lat_2p0 (base coverage) variant is the primary operating configuration;
    higher-lat coverage variants in the depth2 sweep are duplicates on the burial
    axis, so we keep lat_2p0 rows to stay comparable across depths.  When both a
    focused and a shallow_mid row exist for the same (angle, depth) they carry the
    same value, so a plain overwrite by key is safe.
    """
    table: dict[tuple[int, float], dict[str, float]] = {}
    for path in ZIGZAG_TUNING_CSV:
        with path.open(encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                if "lat_2p0" not in r["case"]:
                    continue
                ang = int(round(float(r["zigzag_angle_deg"])))
                depth = float(r["burial_depth_true_m"])
                mae = float(r["cycle_burial_mae_m"])
                if not np.isfinite(mae):
                    continue
                table[(ang, depth)] = {
                    "cycle_mae": mae,
                    "track_xt": float(r["track_mean_cross_track_m"]),
                    "completion": float(r["route_completion_ratio"]),
                }
    return table


def render_zigzag_burial_tradeoff() -> None:
    table = _read_zigzag_rows()
    depths = sorted({d for (_, d) in table})

    # Declared best operating points (algorithm-level, n=1) per §5.5.11.
    best_points = {1.0: 36, 1.5: 32, 2.0: 25}

    _setup_font()
    fig, (ax_l, ax_r) = plt.subplots(1, 2, figsize=(9.6, 4.2),
                                     constrained_layout=True)
    markers = {1.0: "o", 1.5: "s", 2.0: "^"}
    colors = {1.0: C_BASE, 1.5: C_MAP, 2.0: C_ALIGN}

    # left: cycle burial MAE vs zig-zag amplitude, full 20--36 deg envelope
    for d in depths:
        pts = sorted((ang, m["cycle_mae"]) for (ang, dd), m in table.items() if dd == d)
        ang = [p[0] for p in pts]
        err = [p[1] for p in pts]
        ax_l.plot(ang, err, marker=markers.get(d, "o"), color=colors.get(d, C_GRAY),
                  lw=1.5, ms=5, label=f"真值埋深 {d:.1f} m")
        best_ang = best_points.get(d)
        if best_ang is not None and (best_ang, d) in table:
            ax_l.scatter([best_ang], [table[(best_ang, d)]["cycle_mae"]], s=120,
                         facecolors="none", edgecolors=colors.get(d, C_GRAY),
                         linewidths=2.0, zorder=5)

    ax_l.axhline(0.15, color="#B8860B", ls="--", lw=1.2)
    ax_l.annotate("行业参考目标 0.15 m", xy=(0.02, 0.15),
                  xycoords=("axes fraction", "data"),
                  xytext=(0.02, 0.55), textcoords=("axes fraction", "axes fraction"),
                  fontsize=8.5, color="#8A6D0B")
    ax_l.set_xlabel("之字形摆幅 / 横切角（度）")
    ax_l.set_ylabel("单周期埋深平均绝对误差（m）")
    ax_l.set_title("(a) 摆幅—单周期埋深误差（圈标为各埋深最优点）")
    ax_l.legend(loc="upper right")

    # right: at each depth's best amplitude, burial gain vs tracking / completion cost
    depth_x = np.arange(len(depths))
    mae_best = [table[(best_points[d], d)]["cycle_mae"] for d in depths]
    xt_best = [table[(best_points[d], d)]["track_xt"] for d in depths]
    comp_best = [100.0 * table[(best_points[d], d)]["completion"] for d in depths]

    width = 0.32
    ax_r.bar(depth_x - width / 2, mae_best, width, color=C_ALIGN,
             label="最优点 单周期埋深 MAE（m）")
    ax_r.bar(depth_x + width / 2, xt_best, width, color=C_BASE,
             label="最优点 TRACK 横偏（m）")
    ax_r.axhline(0.15, color="#B8860B", ls="--", lw=1.0)
    ax_r.set_ylim(0.0, max(xt_best) + 0.35)
    ax_r.set_ylabel("误差 / 横偏（m）")
    ax_r.set_title("(b) 各埋深最优点的精度与跟踪代价权衡")
    ax_r.set_xticks(depth_x)
    ax_r.set_xticklabels([f"{d:.1f} m\n@{best_points[d]}°" for d in depths])
    ax_r.legend(loc="upper left")
    for xi, yi in zip(depth_x - width / 2, mae_best):
        ax_r.annotate(f"{yi:.3f}", xy=(xi, yi), xytext=(0, 3),
                      textcoords="offset points", ha="center", fontsize=8)
    for xi, yi in zip(depth_x + width / 2, xt_best):
        ax_r.annotate(f"{yi:.2f}", xy=(xi, yi), xytext=(0, 3),
                      textcoords="offset points", ha="center", fontsize=8)

    ax_c = ax_r.twinx()
    ax_c.plot(depth_x, comp_best, "D--", color=C_GRAY, lw=1.3, ms=5,
              label="最优点 完成度（%）")
    ax_c.set_ylabel("路线完成度（%）")
    ax_c.set_ylim(50, 75)
    ax_c.grid(False)
    for xi, yi in zip(depth_x, comp_best):
        ax_c.annotate(f"{yi:.0f}%", xy=(xi, yi), xytext=(0, -14),
                      textcoords="offset points", ha="center", fontsize=8, color=C_GRAY)

    fig.suptitle("调优后之字形主动探查的埋深—摆幅—跟踪权衡（算法级，n=1）", fontsize=11)
    _save(fig, "zigzag_burial_tradeoff")


def main() -> None:
    render_prior_alignment_decoupling()
    render_zigzag_burial_tradeoff()
    render_failure_timeseries()


if __name__ == "__main__":
    main()

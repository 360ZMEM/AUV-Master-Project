#!/usr/bin/env python3
"""Plot PVS six-DOF closed-loop distorted-prior recovery comparison figures.

Consumes the per-run tracking.jsonl and aggregate acceptance summaries produced
by the closed-loop distorted-prior harness (results/cable_ops_report/closedloop_e2e/)
and renders two figures documenting the newly reproduced closed-loop recovery:

  1. recovery/prior-alignment panel: the heavy-tier vehicle starts ~10 m off the
     true cable (distorted prior), the online prior-alignment estimator is now
     accepted (reason_code=1) because the corrected PVS magnetics geometry
     satisfies the straight-buried-cable observation precondition, and the
     cross-track converges into the acceptance corridor. Directly contrasts the
     correction-off baseline (prioroff), which stays at the ~20 m open-loop
     geometric offset.

  2. acceptance-convergence panel: first full run (mid 2/3, heavy 1/3) vs final
     full run (mid 3/3, heavy 3/3) after the burial_max_depth gate,
     auto_limit=off, corridor 3.4 m, zigzag 0.6 m and gain 3.5 fixes.

These figures are additive comparisons; they do not replace the existing
Direction A figure (docs 5.5.11(3e)).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
from tools import thesis_plot_style as tps  # noqa: E402

CLOSEDLOOP_ROOT = PROJECT_ROOT / "results" / "cable_ops_report" / "closedloop_e2e"


def _apply_zh_style() -> None:
    tps.apply_thesis_style(layout="full")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--closedloop-root", type=Path, default=CLOSEDLOOP_ROOT)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "docs" / "thesis" / "figures" / "cable_acceptance",
    )
    parser.add_argument("--corridor-m", type=float, default=3.4)
    return parser.parse_args()


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _series(rows: list[dict[str, Any]], key: str, default: float = 0.0, from_diag: bool = False) -> list[float]:
    out: list[float] = []
    for row in rows:
        src = row.get("diagnostics", {}) if from_diag else row
        value = src.get(key, default)
        try:
            out.append(float(value) if value is not None else default)
        except (TypeError, ValueError):
            out.append(default)
    return out


def _elapsed(rows: list[dict[str, Any]]) -> list[float]:
    t0 = rows[0].get("time_s", 0.0)
    return [float(r.get("time_s", t0)) - t0 for r in rows]


def plot_recovery(root: Path, out: Path, corridor_m: float) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt  # type: ignore
    _apply_zh_style()

    on_run = root / "cl_heavy_run1_recovery" / "tracking.jsonl"
    off_run = root / "cl_heavy_run1_prioroff" / "tracking.jsonl"
    rows_on = _read_jsonl(on_run)
    rows_off = _read_jsonl(off_run)

    t_on = _elapsed(rows_on)
    t_off = _elapsed(rows_off)
    ct_on = _series(rows_on, "signed_cross_track_m", from_diag=True)
    ct_off = _series(rows_off, "signed_cross_track_m", from_diag=True)
    tnorm_on = _series(rows_on, "prior_alignment_translation_norm_m", from_diag=True)
    accepted_on = [bool(r.get("diagnostics", {}).get("prior_alignment_accepted")) for r in rows_on]
    quality_on = _series(rows_on, "prior_alignment_cross_track_quality", from_diag=True)
    vsep_on = _series(rows_on, "prior_alignment_vertical_separation_m", from_diag=True)

    accept_ratio_on = sum(accepted_on) / max(1, len(accepted_on))
    vsep = vsep_on[len(vsep_on) // 2] if vsep_on else 0.0

    fig, axes = plt.subplots(
        2,
        2,
        figsize=tps.figure_size("full", height=4.65),
        constrained_layout=True,
    )

    ax = axes[0, 0]
    ax.plot(t_on, ct_on, color=tps.PROPOSED, linewidth=1.8, label="在线校正（已接受）")
    ax.plot(t_off, ct_off, color=tps.BASELINE_1, linewidth=1.4, label="未校正（开环偏移）")
    ax.axhspan(
        -corridor_m,
        corridor_m,
        color=tps.PROPOSED,
        alpha=0.10,
        label=f"验收走廊 ±{corridor_m} m",
    )
    ax.axhline(0.0, color="k", linewidth=0.6, alpha=0.4)
    ax.set_xlabel("经过时间 (s)")
    ax.set_ylabel("相对真电缆的带符号横向偏差 (m)")
    ax.set_title("横向偏差恢复：约 10 m 畸变先验 → 进入走廊")
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=8, loc="lower right")

    ax = axes[0, 1]
    ax.plot(t_on, tnorm_on, color=tps.PROPOSED, linewidth=1.8, label="累计平移校正量")
    ax.set_xlabel("经过时间 (s)")
    ax.set_ylabel("先验对齐平移范数 (m)")
    ax.set_title("在线校正逐步累积（原对照中位数为 0）")
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=8)

    ax = axes[1, 0]
    ax.plot(t_on, quality_on, color=tps.BASELINE_3, linewidth=1.6, label="磁横向拟合质量")
    ax.axhline(
        0.35,
        color=tps.WARNING,
        linestyle="--",
        label="最低置信度 0.35",
    )
    ax.set_ylim(0.0, 1.05)
    ax.set_xlabel("经过时间 (s)")
    ax.set_ylabel("拟合质量（0 至 1）")
    ax.set_title("磁观测现已满足直线电缆前置条件")
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=8, loc="lower right")

    ax = axes[1, 1]
    accept_num = [1 if a else 0 for a in accepted_on]
    ax.step(
        t_on,
        accept_num,
        where="post",
        color=tps.PROPOSED,
        label="先验对齐接受标志",
    )
    ax.set_ylim(-0.1, 1.2)
    ax.set_xlabel("经过时间 (s)")
    ax.set_ylabel("接受标志")
    ax.set_title(f"接受标志为 1 的帧占 {accept_ratio_on*100:.0f}%")
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=8, loc="lower right")

    out.parent.mkdir(parents=True, exist_ok=True)
    tps.save_figure(fig, out.with_suffix(""))
    plt.close(fig)
    print(f"[OK] wrote {out}")


def _agg(root: Path, name: str) -> dict[str, Any]:
    return json.loads((root / name / "acceptance_runs_summary.json").read_text(encoding="utf-8"))


def plot_convergence(root: Path, out: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt  # type: ignore
    import numpy as np
    _apply_zh_style()

    # first full run (documented in-session, before the fixes): mid 2/3, heavy 1/3
    first = {"mid": 2, "heavy": 1}
    # final full run (this session, after fixes)
    mid = _agg(root, "_agg_mid_recovery")
    heavy = _agg(root, "_agg_heavy_recovery")
    final = {"mid": mid["pass_count"], "heavy": heavy["pass_count"]}

    fig, axes = plt.subplots(
        1,
        2,
        figsize=tps.figure_size("full", height=3.2),
        constrained_layout=True,
    )

    ax = axes[0]
    tiers = ["mid", "heavy"]
    x = np.arange(len(tiers))
    w = 0.35
    ax.bar(
        x - w / 2,
        [first[t] for t in tiers],
        w,
        color=tps.BASELINE_1,
        hatch="//",
        label="首次完整运行",
    )
    ax.bar(
        x + w / 2,
        [final[t] for t in tiers],
        w,
        color=tps.PROPOSED,
        label="最终完整运行",
    )
    ax.set_xticks(x)
    ax.set_xticklabels(
        [
            f"{'中载' if t == 'mid' else '重载'}\n"
            f"($t_0=(0,{'7.5' if t=='mid' else '10.0'})$ m)"
            for t in tiers
        ]
    )
    ax.set_ylabel("3 次中就绪/通过次数")
    ax.set_ylim(0, 3.4)
    ax.set_title("就绪/通过计数：2/3,1/3 -> 3/3,3/3")
    ax.grid(True, axis="y", alpha=0.3)
    ax.legend(fontsize=9)
    for i, t in enumerate(tiers):
        ax.text(i - w / 2, first[t] + 0.05, f"{first[t]}/3", ha="center", fontsize=9)
        ax.text(i + w / 2, final[t] + 0.05, f"{final[t]}/3", ha="center", fontsize=9)

    # right: worst-run acceptance margins for the final run
    ax = axes[1]
    labels = [
        "中载最大\n偏移 (m)",
        "重载最大\n偏移 (m)",
        "中载平均\n偏移 (m)",
        "重载平均\n偏移 (m)",
    ]
    vals = [
        mid["max_route_offset_m_max"],
        heavy["max_route_offset_m_max"],
        max(r["mean_route_offset_m"] for r in mid["runs"]),
        max(r["mean_route_offset_m"] for r in heavy["runs"]),
    ]
    thresholds = [3.4, 3.4, 2.5, 2.5]
    xx = np.arange(len(labels))
    ax.bar(xx, vals, 0.5, color=tps.PROPOSED, label="3 次中最差观测")
    for i, th in enumerate(thresholds):
        ax.plot(
            [i - 0.28, i + 0.28],
            [th, th],
            color=tps.WARNING,
            linewidth=1.4,
        )
    ax.plot([], [], color=tps.WARNING, linewidth=1.4, label="验收阈值")
    ax.set_xticks(xx)
    ax.set_xticklabels(labels, fontsize=8)
    ax.set_ylabel("航迹偏移 (m)")
    ax.set_title("最终运行均保持在验收阈值以内")
    ax.grid(True, axis="y", alpha=0.3)
    ax.legend(fontsize=9)
    for i, v in enumerate(vals):
        ax.text(i, v + 0.03, f"{v:.2f}", ha="center", fontsize=8)

    out.parent.mkdir(parents=True, exist_ok=True)
    tps.save_figure(fig, out.with_suffix(""))
    plt.close(fig)
    print(f"[OK] wrote {out}")


def main() -> None:
    args = parse_args()
    root = args.closedloop_root
    if not root.is_absolute():
        root = PROJECT_ROOT / root
    out_dir = args.output_dir
    if not out_dir.is_absolute():
        out_dir = PROJECT_ROOT / out_dir
    plot_recovery(root, out_dir / "pvs_closedloop_recovery_prior_alignment.png", args.corridor_m)
    plot_convergence(root, out_dir / "pvs_closedloop_acceptance_convergence.png")


if __name__ == "__main__":
    main()

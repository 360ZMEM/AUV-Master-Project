#!/usr/bin/env python3
"""Plot the closed-loop target-identity failure and an independent-cue refusal."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from thesis_plot_style import (BASELINE_1, BASELINE_2, PROPOSED, REFERENCE,
                               WARNING, apply_thesis_style, figure_size, save_figure)


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "AUV-Master-Mag/results/v2/inspection_multisource_identity_20260927"
PUBLICATION = ROOT / "AUV-Master-Mag/docs/v2/publication/fwhm_v2_experiment_results"
STEM = "28_multisource_identity_gate"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(name: str) -> tuple[dict, list[dict]]:
    directory = SOURCE / name
    summary_path = directory / "wire_seed_101_summary.json"
    csv_path = directory / "wire_seed_101.csv"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    with csv_path.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    error = np.asarray([abs(float(row["y_m"]) - 6.) for row in rows
                        if row["mode"] == "track" and float(row["x_m"]) >= 0.])
    summary.update({
        "source_summary": str(summary_path.relative_to(ROOT)),
        "source_summary_sha256": sha(summary_path),
        "source_csv": str(csv_path.relative_to(ROOT)),
        "source_csv_sha256": sha(csv_path),
        "true_track_samples": len(error),
        "true_track_mae_m": float(np.mean(error)) if len(error) else None,
        "true_track_max_m": float(np.max(error)) if len(error) else None,
        "final_pid_thrust_percent": float(rows[-1]["thrust_percent"]),
        "final_udp_rpm": int(rows[-1]["rpm"]),
    })
    return summary, rows


def main() -> None:
    broad, broad_rows = load("broad_map")
    narrow, narrow_rows = load("narrow_cue")
    clean, clean_rows = load("narrow_cue_clean")
    assert broad["completed"] and broad["route_quality_valid"]
    assert broad["true_track_mae_m"] > 1. and broad["true_track_max_m"] > 2.
    assert not narrow["completed"] and narrow["first_hold_reason"] == "flythrough_lateral_rejected"
    assert "side_hint_observation_inconsistent" in narrow["last_lateral_reason_codes"]
    assert narrow["final_pid_thrust_percent"] == narrow["final_udp_rpm"] == 0.
    assert clean["completed"] and clean["route_quality_valid"]
    assert clean["true_track_mae_m"] < 1. and clean["true_track_max_m"] < 2.
    assert all(not item["depth_published"] for item in (broad, narrow, clean))

    apply_thesis_style(base_font_size=8.5)
    fig, axes = plt.subplots(2, 2, figsize=figure_size(height=5.2), constrained_layout=True)
    y = np.linspace(-3., 15., 500)
    primary = 20. / np.sqrt(1. + ((y - 6.) / 3.) ** 2)
    secondary = 10. / np.sqrt(1. + ((y - 9.) / 3.) ** 2)
    ax = axes[0, 0]
    ax.plot(y, primary, color=PROPOSED, lw=1.1, label="目标缆异常")
    ax.plot(y, secondary, color=BASELINE_2, lw=1.1, label="合成干扰")
    ax.plot(y, primary + secondary, color=WARNING, lw=1.4, label="标量包络叠加")
    ax.axvline(6., color=REFERENCE, ls="--", lw=.8, label="目标缆真值")
    ax.axvline(broad["last_fwhm_center_m"], color=WARNING, ls=":", lw=1., label="被确认中心")
    ax.axvspan(5.5, 6.4, color=PROPOSED, alpha=.12)
    ax.set(xlabel="横向位置 / m", ylabel="异常包络 / nT", title="(a) 双源可合成单个近对称峰")
    ax.legend(loc="upper left", fontsize=5.5, ncol=2)

    ax = axes[0, 1]
    for rows, color, label in ((broad_rows, WARNING, "宽地图：错误完成"),
                               (narrow_rows, PROPOSED, "窄线索：确认时拒绝"),
                               (clean_rows, BASELINE_2, "窄线索单源：完成")):
        sub = [row for row in rows if float(row["x_m"]) >= -110.]
        ax.plot([float(row["x_m"]) for row in sub], [float(row["y_m"]) for row in sub],
                color=color, lw=1.05, label=label)
    ax.axhline(6., color=REFERENCE, ls="--", lw=.8, label="目标缆")
    ax.axhline(9., color=BASELINE_1, ls=":", lw=.8, label="干扰源")
    ax.scatter([float(narrow_rows[-1]["x_m"])], [float(narrow_rows[-1]["y_m"])],
               color=PROPOSED, marker="x", s=30, zorder=4)
    ax.set(xlim=(-110., 85.), ylim=(-18., 18.), xlabel="沿先验方向 / m",
           ylabel="横向位置 / m", title="(b) 同一 ROS/PID/UDP/PVS 链的任务航迹")
    ax.legend(loc="lower right", fontsize=5.5)

    ax = axes[1, 0]
    labels = ["宽地图\n双源", "窄线索\n单源"]
    x = np.arange(2)
    ax.bar(x - .19, [broad["route_observed_lateral_mae_m"], clean["route_observed_lateral_mae_m"]],
           width=.34, color=PROPOSED, label="在线观测 MAE")
    ax.bar(x + .19, [broad["true_track_mae_m"], clean["true_track_mae_m"]],
           width=.34, color=WARNING, label="目标缆真值 MAE")
    ax.axhline(1., color=REFERENCE, ls="--", lw=.8, label="示例均值门 1 m")
    ax.set(xticks=x, xticklabels=labels, ylabel="完整正向 Track 横偏 / m",
           ylim=(0, 1.3), title="(c) 质量门不能单独证明目标身份")
    ax.legend(loc="upper right", fontsize=6)

    ax = axes[1, 1]
    for i, (name, item, color) in enumerate((("宽地图＋双源", broad, WARNING),
                                             ("窄线索＋双源", narrow, PROPOSED),
                                             ("窄线索＋单源", clean, BASELINE_2))):
        ax.barh(2 - i, item["duration_s"], height=.45, color=color, alpha=.75)
        status = "完成／误认" if name == "宽地图＋双源" else ("拒绝／零推进" if name == "窄线索＋双源" else "完成／合格")
        ax.text(item["duration_s"] + 12, 2 - i, status, va="center", fontsize=6)
    ax.set(yticks=[0, 1, 2], yticklabels=["窄线索＋单源", "窄线索＋双源", "宽地图＋双源"],
           xlabel="任务终态时间 / s", xlim=(0, 1350),
           title="(d) 先验身份佐证改变的是许可结论")
    ax.grid(axis="y", visible=False)

    figures = PUBLICATION / "figures"
    figures.mkdir(parents=True, exist_ok=True)
    save_figure(fig, figures / STEM, dpi=600)
    plt.close(fig)
    data = PUBLICATION / "data"
    payload = {
        "role": "closed_loop_multi_source_identity_audit",
        "source_script_sha256": sha(Path(__file__)),
        "model_caveat": "secondary line is a synthetic scalar-envelope superposition, not a measured multi-cable electromagnetic field",
        "target_cable_lateral_m": 6., "interferer_lateral_m": 9., "interferer_gain_nt": 10.,
        "broad_hint_m": [2., 8.], "narrow_hint_m": [5.5, 6.4],
        "cases": {"broad_map": broad, "narrow_cue": narrow, "narrow_cue_clean": clean},
    }
    summary_path = data / f"{STEM}_summary.json"
    summary_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest = {"script_sha256": sha(Path(__file__)), "summary_sha256": sha(summary_path),
                "png_sha256": sha(figures / f"{STEM}.png"),
                "pdf_sha256": sha(figures / f"{STEM}.pdf")}
    (data / f"{STEM}_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({name: {key: item[key] for key in ("completed", "route_quality_valid",
                 "true_track_mae_m", "true_track_max_m", "first_hold_reason")}
                      for name, item in payload["cases"].items()}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

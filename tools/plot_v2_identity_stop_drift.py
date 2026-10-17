#!/usr/bin/env python3
"""Audit motion after the identity gate has issued zero propulsion."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import yaml

from thesis_plot_style import (BASELINE_2, PROPOSED, REFERENCE, WARNING,
                               apply_thesis_style, figure_size, save_figure)


ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "AUV-Master-Mag/results/v2/inspection_identity_stop_drift_20260927"
PUBLICATION = ROOT / "AUV-Master-Mag/docs/v2/publication/fwhm_v2_experiment_results"
CONFIG = ROOT / "brain_linux/src/auv_cable_tracking_v2/config/cable_tracking_v2_flythrough_sonar_identity_sim.yaml"
STEM = "31_identity_hold_drift"
CASES = (("dropout_zero", "线索丢失，零流", BASELINE_2),
         ("switch_zero", "改指邻线，零流", PROPOSED),
         ("switch_cross", "改指邻线，横流", WARNING))


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(name: str, bounds: tuple[float, float, float, float]) -> tuple[dict, dict]:
    directory = RUNS / name
    summary_path = directory / "wire_seed_101_summary.json"
    csv_path = directory / "wire_seed_101.csv"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    with csv_path.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    t0 = float(summary["first_hold_s"])
    held = [row for row in rows if float(row["time_s"]) >= t0]
    t = np.asarray([float(row["time_s"]) - t0 for row in held])
    x = np.asarray([float(row["x_m"]) for row in held])
    y = np.asarray([float(row["y_m"]) for row in held])
    rpm = np.asarray([int(row["rpm"]) for row in held])
    thrust = np.asarray([float(row["thrust_percent"]) for row in held])
    ground_speed = np.hypot(np.gradient(x, t), np.gradient(y, t))
    displacement = np.hypot(x - x[0], y - y[0])
    xmin, xmax, ymin, ymax = bounds
    clearance = np.minimum.reduce((x - xmin, xmax - x, y - ymin, ymax - y))
    expected_reason = ("flythrough_runtime_identity_lost" if name == "dropout_zero"
                       else "flythrough_runtime_identity_diverged")
    assert summary["first_hold_reason"] == expected_reason
    assert not summary["completed"] and not summary["depth_published"]
    assert len(held) == 241 and t[-1] == 60.
    assert all(row["mode"] == "hold" for row in held)
    assert np.all(rpm == 0) and np.all(thrust == 0.)
    assert summary["post_hold_nonzero_rpm_ticks"] == 0
    assert float(np.min(clearance)) > 0.
    result = {
        "case": name,
        "first_hold_s": t0,
        "last_recorded_elapsed_s": float(t[-1]),
        "post_step_final_elapsed_s": float(t[-1] + .25),
        "reason": summary["first_hold_reason"],
        "zero_rpm_ticks_after_hold": int(len(held)),
        "first_hold_ground_speed_mps": float(ground_speed[0]),
        "last_ground_speed_mps": float(summary["final_ground_speed_mps"]),
        "hold_to_final_displacement_m": float(summary["hold_to_final_displacement_m"]),
        "hold_to_final_lateral_m": float(summary["hold_to_final_lateral_m"]),
        "minimum_boundary_clearance_m": float(np.min(clearance)),
        "boundary_clearance_at_hold_m": float(clearance[0]),
        "current_speed_mps": float(summary["current_speed_mps"]),
        "current_direction_deg": float(summary["current_direction_deg"]),
        "source_summary": str(summary_path.relative_to(ROOT)),
        "source_summary_sha256": sha(summary_path),
        "source_csv": str(csv_path.relative_to(ROOT)),
        "source_csv_sha256": sha(csv_path),
    }
    arrays = {"t": t, "x": x, "y": y, "speed": ground_speed,
              "displacement": displacement, "clearance": clearance}
    return result, arrays


def main() -> None:
    config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))["cable_tracking"]["v2"]
    polygon = np.asarray(config["search_boundary_xy_m"], dtype=float)
    xs, ys = np.unique(polygon[:, 0]), np.unique(polygon[:, 1])
    assert len(xs) == len(ys) == 2 and len(polygon) == 4
    bounds = (float(xs[0]), float(xs[1]), float(ys[0]), float(ys[1]))
    margin = float(config["inspection"]["boundary_stop_margin_m"])
    loaded = [(name, label, color, *load(name, bounds)) for name, label, color in CASES]

    apply_thesis_style(base_font_size=8.2)
    fig, axes = plt.subplots(2, 2, figsize=figure_size(height=5.1), constrained_layout=True)
    for name, label, color, result, values in loaded:
        t = values["t"]
        axes[0, 0].plot(t, values["y"], color=color, lw=1.15, label=label)
        axes[0, 1].plot(t, values["displacement"], color=color, lw=1.15, label=label)
        axes[1, 0].plot(t, values["speed"], color=color, lw=1.15, label=label)
        axes[1, 1].plot(t, values["clearance"], color=color, lw=1.15, label=label)
    axes[0, 0].axhline(bounds[3] - margin, color=REFERENCE, ls="--", lw=.8,
                       label="北边界内侧 10 m")
    axes[0, 0].set(xlim=(0, 60), xlabel="Hold 后时间 / s",
                   ylabel="车辆横向位置 / m", title="(a) 零推力后的横向漂移")
    axes[0, 0].legend(loc="upper left", fontsize=5.8)
    axes[0, 1].axhline(margin, color=REFERENCE, ls="--", lw=.8,
                       label="候选 10 m 停止余量")
    axes[0, 1].set(xlim=(0, 60), xlabel="Hold 后时间 / s",
                   ylabel="距 Hold 点净位移 / m", title="(b) 零转速仍有惯性与海流位移")
    axes[0, 1].legend(loc="upper left", fontsize=5.8)
    axes[1, 0].axhline(.05, color=REFERENCE, ls="--", lw=.8,
                       label="横流输入 0.05 m/s")
    axes[1, 0].set(xlim=(0, 60), xlabel="Hold 后时间 / s",
                   ylabel="地速 / (m/s)", title="(c) 无流减速与有流持续漂移")
    axes[1, 0].legend(loc="upper right", fontsize=5.8)
    axes[1, 1].axhline(margin, color=REFERENCE, ls="--", lw=.8,
                       label="候选 10 m 余量")
    axes[1, 1].set(xlim=(0, 60), xlabel="Hold 后时间 / s",
                   ylabel="距搜索边界最小距离 / m", title="(d) 预留走廊的余量消耗")
    axes[1, 1].legend(loc="lower left", fontsize=5.8)

    figures = PUBLICATION / "figures"
    save_figure(fig, figures / STEM, dpi=600)
    plt.close(fig)
    data = PUBLICATION / "data"
    payload = {
        "role": "synthetic_zero_propulsion_motion_after_identity_hold",
        "corridor_bounds_xy_m": list(bounds),
        "candidate_stop_margin_m": margin,
        "pvs_fixture_caveat": "Native PVS with synthetic magnetics and sonar; not measured AUV stopping distance or PC104 response.",
        "cases": {name: result for name, _label, _color, result, _values in loaded},
        "source_implementation_sha256": {
            path: sha(ROOT / path) for path in (
                "tools/smoke_v2_flythrough_ros_pvs.py",
                "AUV-Master-Mag/src/auv_mag_tracking/v2/flythrough.py",
                "brain_linux/src/auv_cable_tracking_v2/auv_cable_tracking_v2/cable_tracking_v2_node.py",
                "brain_linux/src/auv_cable_tracking_v2/config/cable_tracking_v2_flythrough_sonar_identity_sim.yaml",
            )
        },
    }
    summary_path = data / f"{STEM}_summary.json"
    summary_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest = {"plot_script_sha256": sha(Path(__file__)),
                "summary_sha256": sha(summary_path),
                "png_sha256": sha(figures / f"{STEM}.png"),
                "pdf_sha256": sha(figures / f"{STEM}.pdf")}
    (data / f"{STEM}_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({name: {key: result[key] for key in (
        "hold_to_final_displacement_m", "minimum_boundary_clearance_m",
        "last_ground_speed_mps", "zero_rpm_ticks_after_hold")}
                      for name, _label, _color, result, _values in loaded},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Plot the new opt-in route Hold admission without changing frozen figures."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
import numpy as np
import yaml

from thesis_plot_style import PROPOSED, REFERENCE, WARNING, apply_thesis_style, figure_size, save_figure


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "brain_linux/src/auv_cable_tracking_v2/config"
OLD = CONFIG / "cable_tracking_v2_flythrough_sonar_identity_sim.yaml"
NEW = CONFIG / "cable_tracking_v2_flythrough_sonar_identity_corridor_budget_sim.yaml"
PUBLICATION = ROOT / "AUV-Master-Mag/docs/v2/publication/fwhm_v2_experiment_results"
STEM = "35_route_hold_admission"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path):
    cfg = yaml.safe_load(path.read_text(encoding="utf-8"))["cable_tracking"]["v2"]
    polygon = np.asarray(cfg["search_boundary_xy_m"], dtype=float)
    xlo, ylo = np.min(polygon, axis=0)
    xhi, yhi = np.max(polygon, axis=0)
    assert polygon.shape == (4, 2) and np.allclose(np.sort(polygon[:, 0]), [xlo, xlo, xhi, xhi])
    assert np.allclose(np.sort(polygon[:, 1]), [ylo, ylo, yhi, yhi])
    route = cfg["flythrough"]
    waypoints = np.array([[route["start_along_m"], route["start_lateral_m"]],
                          [route["end_along_m"], route["end_lateral_m"]]], dtype=float)
    budget = cfg["hold_budget"]
    required = (budget["boundary_stop_margin_m"] + budget["zero_effort_coast_bound_m"]
                + budget["navigation_margin_m"] + budget["current_bound_mps"] *
                (budget["maximum_hold_s"] + budget["disposition_delay_s"])
                + cfg.get("route_hold_admission", {}).get("route_deviation_bound_m", 2.))
    return (xlo, ylo, xhi, yhi), waypoints, required


def clearance(points: np.ndarray, bounds) -> np.ndarray:
    xlo, ylo, xhi, yhi = bounds
    return np.min(np.column_stack((points[:, 0] - xlo, xhi - points[:, 0],
                                   points[:, 1] - ylo, yhi - points[:, 1])), axis=1)


def main() -> None:
    old_bounds, route, old_required = load(OLD)
    new_bounds, new_route, required = load(NEW)
    assert np.allclose(route, new_route) and abs(required - old_required) < 1e-9
    fractions = np.linspace(0., 1., 201)
    points = route[0] + fractions[:, None] * (route[1] - route[0])
    old_clearance = clearance(points, old_bounds)
    new_clearance = clearance(points, new_bounds)
    assert np.min(old_clearance) < required < np.min(new_clearance)

    apply_thesis_style(base_font_size=8.4)
    fig, axes = plt.subplots(2, 1, figsize=figure_size(height=5.0), constrained_layout=True)
    ax = axes[0]
    for bounds, color, label, linestyle in (
        (old_bounds, REFERENCE, "原合成走廊", "--"),
        (new_bounds, PROPOSED, "新增准入走廊", "-"),
    ):
        xlo, ylo, xhi, yhi = bounds
        ax.add_patch(Rectangle((xlo, ylo), xhi-xlo, yhi-ylo, fill=False,
                               edgecolor=color, linestyle=linestyle, linewidth=1.4, label=label))
    ax.plot(points[:, 0], points[:, 1], color=WARNING, linewidth=1.7, label="预定穿越段")
    ax.scatter(route[:, 0], route[:, 1], color=WARNING, s=18, zorder=3)
    ax.annotate("起点", route[0], xytext=(7, -13), textcoords="offset points", fontsize=8)
    ax.annotate("终点", route[1], xytext=(-27, 8), textcoords="offset points", fontsize=8)
    ax.set(xlim=(-285, -65), ylim=(-45, 51), xlabel="沿缆方向 $x$ / m", ylabel="横向 $y$ / m",
           title="(a) 已知穿越段与两种声明走廊的局部视图")
    ax.set_aspect("equal", adjustable="box")
    ax.legend(loc="upper center", ncol=3, fontsize=7)

    ax = axes[1]
    ax.plot(fractions * 100, old_clearance, color=REFERENCE, ls="--", lw=1.5,
            label=f"原走廊：最小 {old_clearance.min():.1f} m")
    ax.plot(fractions * 100, new_clearance, color=PROPOSED, lw=1.7,
            label=f"新走廊：最小 {new_clearance.min():.1f} m")
    ax.axhline(required, color=WARNING, lw=1.3, ls=":",
               label=f"Hold + 路线偏差所需 {required:.1f} m")
    ax.fill_between(fractions * 100, old_clearance, required,
                    where=old_clearance < required, color=WARNING, alpha=.12)
    ax.set(xlim=(0, 100), ylim=(14, 48), xlabel="穿越段进度 / %", ylabel="到边界的最小净距 / m",
           title="(b) 起航前检查整条已知线段的最小余量")
    ax.legend(loc="upper center", ncol=2, fontsize=7)
    figures = PUBLICATION / "figures"
    save_figure(fig, figures / STEM, dpi=600)
    plt.close(fig)
    payload = {
        "role": "synthetic_opt_in_route_hold_admission_geometry",
        "old_minimum_clearance_m": float(np.min(old_clearance)),
        "new_minimum_clearance_m": float(np.min(new_clearance)),
        "required_clearance_m": float(required),
        "old_admitted": False, "new_admitted": True,
        "old_config_sha256": sha(OLD), "new_config_sha256": sha(NEW),
        "caveat": "Known initial straight leg only; later rejoin geometry needs online motion guard. Synthetic stop/current bounds are not field measurements.",
    }
    data = PUBLICATION / "data"
    summary = data / f"{STEM}_summary.json"
    summary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest = {"plot_script_sha256": sha(Path(__file__)),
                "summary_sha256": sha(summary),
                "png_sha256": sha(figures / f"{STEM}.png"),
                "pdf_sha256": sha(figures / f"{STEM}.pdf")}
    (data / f"{STEM}_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

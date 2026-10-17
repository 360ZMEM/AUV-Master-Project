#!/usr/bin/env python3
"""Audit the local target-association discrimination budget (synthetic only)."""
from __future__ import annotations

from dataclasses import replace
import hashlib
import json
import math
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import BoundaryNorm, ListedColormap
from matplotlib.patches import Patch
import numpy as np

from auv_mag_tracking.api import CableMap, MagneticInput, NavigationInput
from auv_mag_tracking.v2 import FlythroughConfig, FlythroughInspectionPipelineV2
from auv_mag_tracking.v2.config import InspectionConfig, V2Config
from thesis_plot_style import (PROPOSED, REFERENCE, WARNING, apply_thesis_style,
                               figure_size, save_figure)


ROOT = Path(__file__).resolve().parents[1]
PUBLICATION = ROOT / "AUV-Master-Mag/docs/v2/publication/fwhm_v2_experiment_results"
STEM = "58_target_exclusive_corridor_budget"
ANCHOR = (5.8, 6.2)
EXCLUSIVE = (5.45, 6.55)
HALF_WIDTH = 0.5


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_scan(source_lateral_m: float, exclusive_enabled: bool) -> dict:
    """Exercise the actual v2 Confirm path with one synthetic magnetic source."""
    boundary = np.array([[-270., -30.], [120., -30.], [120., 30.], [-270., 30.]])
    setting = replace(V2Config(), inspection=InspectionConfig(
        enabled=True, maximum_scan_duration_s=600.,
        maximum_observation_age_s=1000., maximum_observation_distance_m=250.,
        boundary_stop_margin_m=10.,
    ))
    policy = FlythroughConfig(
        side_hint_required=True, side_hint_min_m=6.6, side_hint_max_m=7.5,
        side_hint_source="survey_map", minimum_halfmax_tail_m=7.,
        require_runtime_identity_cue=True,
        runtime_identity_supersedes_side_hint_center=True,
        runtime_target_anchor_min_m=ANCHOR[0], runtime_target_anchor_max_m=ANCHOR[1],
        runtime_target_exclusive_min_m=EXCLUSIVE[0] if exclusive_enabled else None,
        runtime_target_exclusive_max_m=EXCLUSIVE[1] if exclusive_enabled else None,
    )
    pipeline = FlythroughInspectionPipelineV2(
        object(), CableMap(np.array([[0., 0.], [80., 0.]])),
        v2_config=setting, search_boundary_xy_m=boundary, flythrough_config=policy,
    )
    start, end = pipeline._fly_start, pipeline._fly_end
    heading = math.degrees(math.atan2(end[1] - start[1], end[0] - start[0]))
    from types import SimpleNamespace
    for index, fraction in enumerate(np.linspace(0., 1., 2300)):
        point = start + fraction * (end - start)
        value = 1. + 20. / math.sqrt(1. + ((float(point[1]) - source_lateral_m) / 3.) ** 2)
        t = index * .25
        pipeline.set_runtime_identity_cue(SimpleNamespace(
            time_s=t, lateral_center_m=source_lateral_m, half_width_m=HALF_WIDTH,
        ))
        output, guidance = pipeline.step_with_guidance(
            NavigationInput(t, np.array([*point, -10.]), heading,
                            speed_mps=.3, position_std_m=.1),
            MagneticInput(t, np.tile([value, 0., 0.], (4, 1)), 50.),
        )
    return {
        "source_lateral_m": source_lateral_m,
        "exclusive_enabled": exclusive_enabled,
        "final_mode": output.mode,
        "last_lateral_center_m": pipeline._last_lateral.center_x_m,
        "last_lateral_reason_codes": list(pipeline._last_lateral.reason_codes),
        "final_guidance_speed_mps": guidance.speed_mps,
        "depth_published": output.burial_depth_m is not None,
    }


def main() -> None:
    cases = {
        "near_neighbor_anchor_only": run_scan(6.6, False),
        "near_neighbor_exclusive": run_scan(6.6, True),
        "true_source_exclusive": run_scan(6.0, True),
    }
    assert cases["near_neighbor_anchor_only"]["final_mode"] == "track"
    assert cases["near_neighbor_exclusive"]["final_mode"] == "hold"
    assert "runtime_target_exclusive_corridor_inconsistent" in cases["near_neighbor_exclusive"]["last_lateral_reason_codes"]
    assert cases["near_neighbor_exclusive"]["final_guidance_speed_mps"] == 0.
    assert cases["true_source_exclusive"]["final_mode"] == "track"
    assert all(not case["depth_published"] for case in cases.values())

    centers = np.linspace(5.5, 7.2, 171)
    widths = np.linspace(.1, .5, 81)
    center, half = np.meshgrid(centers, widths)
    overlap = (center + half >= ANCHOR[0]) & (center - half <= ANCHOR[1])
    contained = (center - half >= EXCLUSIVE[0]) & (center + half <= EXCLUSIVE[1])
    classes = np.where(overlap & contained, 2, np.where(overlap, 1, 0))

    apply_thesis_style(base_font_size=8)
    fig, axes = plt.subplots(1, 2, figsize=figure_size(height=2.55),
                             constrained_layout=True)
    ax = axes[0]
    ax.axvspan(*EXCLUSIVE, color=PROPOSED, alpha=.11, label="经独立测绘的目标专属走廊")
    ax.axvspan(*ANCHOR, color=PROPOSED, alpha=.32, label="局部目标锚点")
    ax.errorbar([6.], [1.], xerr=[HALF_WIDTH], fmt="o", capsize=3,
                color=PROPOSED, label="真目标声呐 $6.0\pm0.5$ m")
    ax.errorbar([6.6], [0.], xerr=[HALF_WIDTH], fmt="x", capsize=3,
                color=WARNING, label="邻线声呐 $6.6\pm0.5$ m")
    ax.set(xlim=(5.25, 7.25), ylim=(-.55, 1.6),
           yticks=[0, 1], yticklabels=["邻线", "目标"],
           xlabel="横向位置 / m", title="(a) 两条声呐区间都碰到锚点")
    ax.legend(fontsize=5.3, ncol=2, loc="upper right")

    ax = axes[1]
    palette = ListedColormap(["#d9d9d9", WARNING, PROPOSED])
    norm = BoundaryNorm([-.5, .5, 1.5, 2.5], palette.N)
    ax.pcolormesh(centers, widths, classes, shading="nearest", cmap=palette, norm=norm)
    ax.axvline(EXCLUSIVE[1], ls="--", lw=.8, color=REFERENCE)
    ax.scatter([6., 6.6], [HALF_WIDTH, HALF_WIDTH],
               c=[PROPOSED, WARNING], s=25, edgecolor="black", linewidth=.4)
    ax.set(xlim=(5.5, 7.2), ylim=(.1, .5),
           xlabel="声呐线中心 / m", ylabel="声呐 2σ 半宽 / m",
           title="(b) 锚点相交与专属走廊的许可域")
    ax.legend(handles=[Patch(facecolor="#d9d9d9", label="两门均拒绝"),
                       Patch(facecolor=WARNING, label="仅相交门许可"),
                       Patch(facecolor=PROPOSED, label="专属走廊也许可")],
              fontsize=5.8, loc="upper right")
    stem = PUBLICATION / "figures" / STEM
    save_figure(fig, stem)
    plt.close(fig)

    payload = {
        "role": "synthetic_local_target_association_discrimination_budget",
        "scope": "three single-source v2 Confirm scans and exact interval geometry; not ROS, a physical survey, or a success probability",
        "target_anchor_m": list(ANCHOR),
        "survey_claimed_exclusive_corridor_m": list(EXCLUSIVE),
        "sonar_half_width_m": HALF_WIDTH,
        "cases": cases,
        "grid": {"centers_m": [float(centers[0]), float(centers[-1]), len(centers)],
                 "half_widths_m": [float(widths[0]), float(widths[-1]), len(widths)],
                 "anchor_only_permitted_cells": int(np.count_nonzero(overlap)),
                 "exclusive_permitted_cells": int(np.count_nonzero(overlap & contained)),
                 "anchor_only_risk_cells_outside_exclusive": int(np.count_nonzero(
                     overlap & (center > EXCLUSIVE[1]))),
                 "exclusive_permitted_cells_outside_exclusive": int(np.count_nonzero(
                     overlap & contained & (center > EXCLUSIVE[1]))),
                 "note": "Cells are a deterministic geometry grid, not stochastic trials."},
        "source_script_sha256": digest(Path(__file__)),
        "flythrough_sha256": digest(ROOT / "AUV-Master-Mag/src/auv_mag_tracking/v2/flythrough.py"),
        "png_sha256": digest(stem.with_suffix(".png")),
        "pdf_sha256": digest(stem.with_suffix(".pdf")),
    }
    data = PUBLICATION / "data" / f"{STEM}.json"
    data.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"cases": cases, "grid": payload["grid"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Finite synthetic audit of single-peak lateral identity under a second source.

This is a sensitivity audit, not a field isolation certificate.  It runs the
unchanged v2 FWHM and lateral geometry gates and records every combination.
"""
from __future__ import annotations

import csv
import hashlib
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import BoundaryNorm, ListedColormap
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "AUV-Master-Mag/src"))
from auv_mag_tracking.v2.config import FwhmConfig, InspectionConfig
from auv_mag_tracking.v2.fwhm import estimate_fwhm
from auv_mag_tracking.v2.lateral import qualify_lateral_center
from thesis_plot_style import (WARNING, apply_thesis_style,
                               figure_size, save_figure)

PUB = ROOT / "AUV-Master-Mag/docs/v2/publication/fwhm_v2_experiment_results"
STEM = "56_magnetic_isolation_envelope"
DISTANCES = np.arange(0.5, 10.01, 0.5)
RATIOS = np.arange(0.0, 0.501, 0.05)
SEEDS = (101, 102, 103)
NOISE_NT = (0.0, 0.05)
FAMILIES = ("physical_single_wire", "thesis_dipole")
TARGET_CENTER_M = 0.0
TARGET_AMPLITUDE_NT = 20.0
VERTICAL_SEPARATION_M = 3.0
BASELINE_NT = 1.0
ERROR_LIMIT_M = 0.5


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def envelope(x: np.ndarray, center: float, family: str) -> np.ndarray:
    q = ((x - center) / VERTICAL_SEPARATION_M) ** 2
    return 1.0 / np.sqrt(1.0 + q) if family == "physical_single_wire" else 1.0 / (1.0 + q)


def evaluate() -> list[dict]:
    x = np.linspace(-15.0, 15.0, 301)
    config = FwhmConfig(altitude_m=0.0)
    policy = InspectionConfig(enabled=True)
    rows = []
    for family in FAMILIES:
        target = TARGET_AMPLITUDE_NT * envelope(x, TARGET_CENTER_M, family)
        for noise_nt in NOISE_NT:
            for seed in (SEEDS if noise_nt else (0,)):
                rng = np.random.default_rng(seed)
                # Identical sampled noise is used for each geometry in a case.
                noise = rng.normal(0.0, noise_nt, x.size)
                for sign in (-1, 1):
                    for distance in DISTANCES:
                        neighbor = envelope(x, sign * distance, family)
                        for ratio in RATIOS:
                            y = BASELINE_NT + target + TARGET_AMPLITUDE_NT * ratio * neighbor + noise
                            fwhm = estimate_fwhm(x, y, config, baseline_nt=BASELINE_NT,
                                                 noise_nt=max(noise_nt, 0.05))
                            lateral = qualify_lateral_center(fwhm, config, policy)
                            rows.append({
                                "family": family, "noise_nt": noise_nt, "seed": seed,
                                "neighbor_side": sign, "separation_m": float(distance),
                                "neighbor_peak_gain_ratio": float(round(ratio, 4)),
                                "lateral_valid": lateral.valid,
                                "center_m": lateral.center_x_m,
                                "target_center_error_m": abs(lateral.center_x_m) if lateral.valid else None,
                                "confidence": lateral.confidence,
                                "reason_codes": "|".join(lateral.reason_codes),
                            })
    return rows


def summarize(rows: list[dict]) -> dict:
    summary = {}
    for family in FAMILIES:
        subset = [row for row in rows if row["family"] == family]
        by_ratio = []
        for ratio in RATIOS:
            group = [row for row in subset if abs(row["neighbor_peak_gain_ratio"] - ratio) < 1e-8]
            errors = [row["target_center_error_m"] for row in group if row["lateral_valid"]]
            by_ratio.append({"ratio": float(round(ratio, 4)), "cases": len(group),
                             "accepted": len(errors),
                             "accepted_error_over_limit": sum(error > ERROR_LIMIT_M for error in errors),
                             "worst_accepted_error_m": max(errors) if errors else None})
        summary[family] = {"by_ratio": by_ratio,
                           "worst_accepted_error_m": max(row["target_center_error_m"] for row in subset
                                                         if row["lateral_valid"])}
    accepted_false = [row for row in rows if row["lateral_valid"]
                      and row["target_center_error_m"] > ERROR_LIMIT_M]
    return {"families": summary, "cases": len(rows), "accepted_false_center_count": len(accepted_false),
            "worst_false_center": max(accepted_false, key=lambda row: row["target_center_error_m"])
            if accepted_false else None}


def plot(rows: list[dict]) -> Path:
    apply_thesis_style(base_font_size=8)
    fig, axes = plt.subplots(2, 2, figsize=figure_size(height=5.1), constrained_layout=True)
    colors = ListedColormap(["#D9D9D9", "#E8F2F8", "#8CBAD3", "#E69F00", WARNING])
    norm = BoundaryNorm([-1.5, -0.5, 0.1, ERROR_LIMIT_M, 1.0, 2.1], colors.N)
    for row_i, family in enumerate(FAMILIES):
        for col_i, noise_nt in enumerate(NOISE_NT):
            subset = [row for row in rows if row["family"] == family and row["noise_nt"] == noise_nt]
            maximum = np.full((len(RATIOS), len(DISTANCES)), -1.0)
            for i, ratio in enumerate(RATIOS):
                for j, distance in enumerate(DISTANCES):
                    accepted = [row["target_center_error_m"] for row in subset
                                if row["lateral_valid"]
                                and abs(row["neighbor_peak_gain_ratio"] - ratio) < 1e-8
                                and abs(row["separation_m"] - distance) < 1e-8]
                    if accepted:
                        maximum[i, j] = max(accepted)
            ax = axes[row_i, col_i]
            image = ax.imshow(maximum, origin="lower", aspect="auto", cmap=colors, norm=norm,
                              extent=(0.25, 10.25, -0.025, 0.525), interpolation="nearest")
            ax.set(xlabel="邻源间距 / m", ylabel="邻源峰幅 / 目标峰幅",
                   title=f"({'abcd'[2 * row_i + col_i]}) {'单直导线' if row_i == 0 else '偶极包络'}"
                         f"，噪声 {noise_nt:g} nT")
            ax.set_xticks([1, 3, 5, 7, 9])
            ax.set_yticks([0, .1, .2, .3, .4, .5])
            ax.grid(False)
    colorbar = fig.colorbar(image, ax=axes.ravel().tolist(), fraction=.025, pad=.02,
                            ticks=[-1, 0.05, .3, .75, 1.5])
    colorbar.ax.set_yticklabels(["全拒绝", "≤0.1", "0.1–0.5", "0.5–1", ">1 m"])
    colorbar.set_label("已放行中心最大真值误差 / m")
    fig.suptitle("邻源融合峰：几何门放行不保证目标身份", fontsize=9)
    destination = PUB / "figures" / STEM
    destination.parent.mkdir(parents=True, exist_ok=True)
    save_figure(fig, destination)
    plt.close(fig)
    return destination


def main() -> None:
    rows = evaluate()
    result = summarize(rows)
    data = PUB / "data"
    data.mkdir(parents=True, exist_ok=True)
    csv_path = data / f"{STEM}.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    figure = plot(rows)
    result.update({
        "scope": "finite synthetic scalar-envelope sensitivity only; no physical target uniqueness or ROS/PVS completion claim",
        "scan_m": [-15, 15], "scan_samples": 301, "baseline_nt": BASELINE_NT,
        "target_amplitude_nt": TARGET_AMPLITUDE_NT,
        "vertical_separation_m": VERTICAL_SEPARATION_M,
        "separations_m": DISTANCES.tolist(), "gain_ratios": [float(round(v, 4)) for v in RATIOS],
        "noise_nt": list(NOISE_NT), "noise_seeds": list(SEEDS), "neighbor_sides": [-1, 1],
        "error_limit_m": ERROR_LIMIT_M,
        "method": "unchanged estimate_fwhm + qualify_lateral_center; target truth at x=0",
        "source_script_sha256": sha(Path(__file__)),
        "fwhm_sha256": sha(ROOT / "AUV-Master-Mag/src/auv_mag_tracking/v2/fwhm.py"),
        "lateral_sha256": sha(ROOT / "AUV-Master-Mag/src/auv_mag_tracking/v2/lateral.py"),
        "csv_sha256": sha(csv_path), "png_sha256": sha(figure.with_suffix(".png")),
        "pdf_sha256": sha(figure.with_suffix(".pdf")),
    })
    (data / f"{STEM}.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                                            encoding="utf-8")
    print(json.dumps({"cases": result["cases"],
                      "accepted_false_center_count": result["accepted_false_center_count"],
                      "worst_false_center": result["worst_false_center"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()

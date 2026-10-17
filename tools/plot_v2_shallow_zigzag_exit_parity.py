#!/usr/bin/env python3
"""Figure 49: active crossing parity determines the downstream rejoin burden."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from thesis_plot_style import (BASELINE_1, BASELINE_2, PROPOSED, REFERENCE,
                               WARNING, apply_thesis_style, figure_size, save_figure)


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "AUV-Master-Mag/src"))
SOURCE = ROOT / "AUV-Master-Mag/results/v2/shallow_zigzag_exit_parity_20260927"
PUB = ROOT / "AUV-Master-Mag/docs/v2/publication/fwhm_v2_experiment_results"
THESIS = ROOT / "docs/thesis/figures/experiments/fwhm_v2"
STEM = "49_shallow_zigzag_exit_parity"
NAMES = ("positive_three_correct_exit", "negative_three_wrong_exit",
         "negative_four_correct_exit", "positive_four_wrong_exit")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(name: str) -> tuple[dict, list[dict]]:
    folder = SOURCE / name
    summary = json.loads((folder / "summary.json").read_text(encoding="utf-8"))
    csv_path = folder / "trajectory.csv"
    if sha(csv_path) != summary["trajectory_sha256"]:
        raise ValueError("trajectory hash mismatch: " + name)
    with csv_path.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    return summary, rows


def col(rows: list[dict], key: str) -> np.ndarray:
    return np.array([float(row[key]) for row in rows])


def last_station_projection(summary: dict, rows: list[dict]) -> dict:
    """Reconstruct exactly the station assignment used by the PVS probe."""
    from auv_mag_tracking.v2 import (
        CorridorSurveyConfig, FwhmConfig, InspectionConfig, ShallowZigzagConfig,
        SurveyProfile, build_shallow_zigzag_survey, estimate_survey_line,
    )
    station_count = summary["station_count"]
    L = summary["half_wavelength_m"]
    A = summary["amplitude_m"]
    length = station_count * L
    policy = ShallowZigzagConfig(station_count=station_count, half_wavelength_m=L,
                                 amplitude_m=A, initial_lateral_sign=summary["start_side"],
                                 waypoint_spacing_m=.5)
    boundary = np.array([[-10., -A - 18.], [length + 10., -A - 18.],
                         [length + 10., A + 18.], [-10., A + 18.]])
    plan = build_shallow_zigzag_survey(np.array([[0., 0.], [length, 0.]]), boundary, policy)
    profiles = []
    for station in range(station_count):
        station_rows = [row for index, row in enumerate(rows)
                        if index % 4 == 0 and row["phase"] == "survey"
                        and 0 <= float(row["x_m"]) <= length
                        and min(int(float(row["x_m"]) // L), station_count - 1) == station]
        positions = np.array([[float(row["x_m"]), float(row["y_m"])] for row in station_rows])
        envelope = col(station_rows, "magnetic_envelope_nt")
        profiles.append(SurveyProfile(station, positions, envelope, .02))
    quality = CorridorSurveyConfig(half_width_m=A, station_spacing_m=L,
                                   station_count=station_count,
                                   maximum_along_excursion_m=L + 2.)
    estimate = estimate_survey_line(plan, profiles, quality,
                                    FwhmConfig(shape_model="thesis_dipole", altitude_m=0.),
                                    InspectionConfig(enabled=True))
    assert estimate.geometry_valid, estimate.reason_codes
    last_center_x = float(estimate.station_centers_xy_m[-1, 0])
    nominal_track_end_x = length + summary["minimum_rejoin_distance_at_10deg_m"] + 80.
    return {"last_measured_center_x_m": last_center_x,
            "hypothetical_track_end_x_m": nominal_track_end_x,
            "hypothetical_line_extrapolation_m": nominal_track_end_x - last_center_x,
            "track_phase_executed": False}


def main() -> None:
    data = {name: load(name) for name in NAMES}
    source_hashes = data[NAMES[0]][0]["source_sha256"]
    assert all(item[0]["source_sha256"] == source_hashes for item in data.values())
    assert all(sha(ROOT / path) == digest for path, digest in source_hashes.items())
    assert all(item[0]["terminal_phase"] == "survey_path_end"
               and item[0]["geometry_valid"] and item[0]["burial_depth_m"] is None
               and item[0]["reference_track_max_m"] < 3.0 for item in data.values())
    assert all(data[name][0]["station_count"] == 3 for name in NAMES[:2])
    assert all(data[name][0]["station_count"] == 4 for name in NAMES[2:])

    apply_thesis_style(base_font_size=8)
    fig, axes = plt.subplots(1, 2, figsize=figure_size(height=3.2), constrained_layout=True)
    colors = (PROPOSED, WARNING, BASELINE_2, BASELINE_1)
    labels = ("+0.05 m/s，三段", "-0.05 m/s，三段",
              "-0.05 m/s，四段", "+0.05 m/s，四段")
    ax = axes[0]
    for name, label, color in zip(NAMES, labels, colors):
        rows = data[name][1]
        ax.plot(col(rows, "x_m"), col(rows, "y_m"), color=color, lw=1.0, label=label)
        ax.plot(float(rows[-1]["x_m"]), float(rows[-1]["y_m"]), "o", color=color, ms=3)
    x = np.linspace(0, 545, 100)
    ax.plot(x, 6. + .02*x, color=REFERENCE, ls=":", lw=1.0, label="目标线真值")
    ax.set(xlim=(-5, 550), ylim=(-32, 38), xlabel="沿先验位置 / m",
           ylabel="横向位置 / m", title="(a) 横流决定起始侧，段数决定退出侧")
    ax.legend(loc="lower left", fontsize=5.9)

    ax = axes[1]
    distances = [data[name][0]["minimum_rejoin_distance_at_10deg_m"] for name in NAMES]
    bars = ax.barh(np.arange(4), distances, height=.56, color=colors, edgecolor=REFERENCE)
    for bar, distance in zip(bars, distances):
        ax.text(distance + 5, bar.get_y() + bar.get_height()/2., f"{distance:.0f} m",
                va="center", fontsize=7)
    ax.set_yticks(np.arange(4), ("正向流 / 三段", "反向流 / 三段",
                                   "反向流 / 四段", "正向流 / 四段"))
    ax.set(xlim=(0, 280), ylim=(3.7, -.6), xlabel="按 10° 相对线向限幅估算的接入距离 / m",
           title="(b) 名义接入距离随退出侧大幅变化")
    ax.text(.02, .02, "忽略动力学；尚未执行 Track 接入", transform=ax.transAxes,
            fontsize=6.2, color=WARNING)
    pub_paths = save_figure(fig, PUB / "figures" / STEM)
    thesis_paths = save_figure(fig, THESIS / STEM)
    plt.close(fig)

    summary = {
        "evidence_level": "native_pvs_protocol_survey_exit_probe",
        "rejoin_distance_is_nominal_geometry_approximation": True,
        "track_phase_executed": False,
        "field_release_authorized": False,
        "cases": {name: {key: item[0][key] for key in
                         ("terminal_phase", "station_count", "amplitude_m", "half_wavelength_m",
                          "current_direction_deg", "start_side", "reference_track_max_m",
                          "geometry_valid", "center_mae_m", "survey_exit_truth_lateral_error_m",
                          "minimum_rejoin_distance_at_10deg_m", "burial_depth_m", "trajectory_sha256")}
                  for name, item in data.items()},
        "source_sha256": source_hashes,
        "raw_summary_sha256": {name: sha(SOURCE / name / "summary.json") for name in NAMES},
        "negative_four_80m_track_projection": last_station_projection(
            *data["negative_four_correct_exit"]),
    }
    summary_path = PUB / "data" / f"{STEM}_summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest = {"summary_sha256": sha(summary_path),
                "figure_sha256": {str(path.relative_to(ROOT)): sha(path)
                                  for path in (*pub_paths, *thesis_paths)},
                "plot_script_sha256": sha(Path(__file__).resolve())}
    (PUB / "data" / f"{STEM}_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"summary": str(summary_path), "case_count": len(NAMES)}))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Normalized boustrophedon coverage sweep for thesis R12."""

from __future__ import annotations

import argparse
import csv
import json
import math
import shutil
import sys
import time
from pathlib import Path
from typing import Iterable

import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.experiment_contract import finalize_bundle, initialize_bundle  # noqa: E402


DEFAULT_BEAM_DEG = (30.0, 45.0, 60.0, 75.0)
DEFAULT_MAGNETIC_WIDTH_RATIOS = (0.5, 0.75, 1.0, 1.25)
DEFAULT_SPACING_RATIOS = (0.6, 0.7, 0.8, 0.9, 1.0)
DEFAULT_SPEED_RATIOS = (0.5, 0.75, 1.0, 1.25)
DEFAULT_ERROR_RATIOS = (0.0, 0.05, 0.10, 0.15)
REFERENCE_BEAM_DEG = 60.0


def parse_values(text: str) -> tuple[float, ...]:
    values = tuple(float(item.strip()) for item in text.split(",") if item.strip())
    if not values:
        raise argparse.ArgumentTypeError("axis must contain at least one value")
    return values


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Sweep normalized sonar beam, magnetic width, track spacing, speed, "
            "and lateral-error ratios without assuming hardware absolute ranges."
        )
    )
    parser.add_argument("--beam-deg", type=parse_values, default=DEFAULT_BEAM_DEG)
    parser.add_argument(
        "--magnetic-width-ratios",
        type=parse_values,
        default=DEFAULT_MAGNETIC_WIDTH_RATIOS,
    )
    parser.add_argument(
        "--spacing-ratios", type=parse_values, default=DEFAULT_SPACING_RATIOS
    )
    parser.add_argument(
        "--speed-ratios", type=parse_values, default=DEFAULT_SPEED_RATIOS
    )
    parser.add_argument(
        "--lateral-error-ratios",
        type=parse_values,
        default=DEFAULT_ERROR_RATIOS,
    )
    parser.add_argument("--area-along-ratio", type=float, default=40.0)
    parser.add_argument("--area-cross-ratio", type=float, default=20.0)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Default: results/coverage_normalized/<timestamp>_r12",
    )
    return parser.parse_args()


def validate_axes(args: argparse.Namespace) -> None:
    if args.area_along_ratio <= 0.0 or args.area_cross_ratio <= 0.0:
        raise SystemExit("normalized area dimensions must be positive")
    for name in (
        "beam_deg",
        "magnetic_width_ratios",
        "spacing_ratios",
        "speed_ratios",
        "lateral_error_ratios",
    ):
        values = getattr(args, name)
        if any(value <= 0.0 for value in values) and name != "lateral_error_ratios":
            raise SystemExit(f"{name} values must be positive")
        if name == "lateral_error_ratios" and any(value < 0.0 for value in values):
            raise SystemExit("lateral error ratios must be non-negative")
    if any(not 0.0 < value <= 1.0 for value in args.spacing_ratios):
        raise SystemExit("spacing ratios must lie in (0, 1]")
    if any(not 0.0 < value < 180.0 for value in args.beam_deg):
        raise SystemExit("beam angles must lie in (0, 180) degrees")


def sonar_width_ratio(beam_deg: float) -> float:
    """Swath ratio at fixed altitude relative to a 60 degree reference beam."""
    numerator = math.tan(math.radians(beam_deg) / 2.0)
    denominator = math.tan(math.radians(REFERENCE_BEAM_DEG) / 2.0)
    return numerator / denominator


def track_count(
    cross_track_width: float,
    effective_width: float,
    spacing: float,
) -> int:
    if cross_track_width <= effective_width:
        return 1
    return int(math.ceil((cross_track_width - effective_width) / spacing)) + 1


def evaluate_configuration(
    *,
    beam_deg: float,
    magnetic_width_ratio: float,
    spacing_ratio: float,
    speed_ratio: float,
    lateral_error_ratio: float,
    area_along_ratio: float,
    area_cross_ratio: float,
) -> dict[str, object]:
    sonar_ratio = sonar_width_ratio(beam_deg)
    effective_width = min(sonar_ratio, magnetic_width_ratio)
    spacing = spacing_ratio * effective_width
    count = track_count(area_cross_ratio, effective_width, spacing)

    # A semicircle of diameter d is the minimum geometric U-turn connection.
    straight_length = count * area_along_ratio
    turn_length = max(count - 1, 0) * math.pi * spacing / 2.0
    path_length = straight_length + turn_length
    mission_time = path_length / speed_ratio
    area = area_along_ratio * area_cross_ratio

    nominal_overlap = max(0.0, 1.0 - spacing_ratio)
    guaranteed_width = max(
        0.0, effective_width * (1.0 - 2.0 * lateral_error_ratio)
    )
    guaranteed_coverage = min(1.0, guaranteed_width / spacing)

    return {
        "scenario": "normalized_boustrophedon",
        "seed": "analytic",
        "mpc_mode": "not_applicable",
        "status": "ok",
        "beam_deg": beam_deg,
        "sonar_width_ratio": sonar_ratio,
        "magnetic_width_ratio": magnetic_width_ratio,
        "effective_width_ratio": effective_width,
        "spacing_ratio": spacing_ratio,
        "spacing_to_reference_width": spacing,
        "speed_ratio": speed_ratio,
        "lateral_error_ratio": lateral_error_ratio,
        "nominal_overlap_ratio": nominal_overlap,
        "guaranteed_coverage_ratio": guaranteed_coverage,
        "guaranteed_gap_ratio": 1.0 - guaranteed_coverage,
        "track_count": count,
        "straight_length_normalized": straight_length,
        "turn_length_normalized": turn_length,
        "path_length_normalized": path_length,
        "mission_time_normalized": mission_time,
        "area_rate_normalized": area / mission_time,
        "effective_sample_count": count,
        "failure_event_count": 0,
        "capability_gate_status": "not_applicable_analytic",
        "solver_wall_time_current_ms": "not_applicable",
        "fallback_type": "not_applicable",
    }


def generate_rows(args: argparse.Namespace) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for beam_deg in args.beam_deg:
        for magnetic_width_ratio in args.magnetic_width_ratios:
            for spacing_ratio in args.spacing_ratios:
                for speed_ratio in args.speed_ratios:
                    for lateral_error_ratio in args.lateral_error_ratios:
                        rows.append(
                            evaluate_configuration(
                                beam_deg=beam_deg,
                                magnetic_width_ratio=magnetic_width_ratio,
                                spacing_ratio=spacing_ratio,
                                speed_ratio=speed_ratio,
                                lateral_error_ratio=lateral_error_ratio,
                                area_along_ratio=args.area_along_ratio,
                                area_cross_ratio=args.area_cross_ratio,
                            )
                        )
    return rows


def write_csv(path: Path, rows: Iterable[dict[str, object]]) -> None:
    rows = list(rows)
    fieldnames = list(rows[0]) if rows else []
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def select_reference_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    selected = [
        dict(row)
        for row in rows
        if row["beam_deg"] == REFERENCE_BEAM_DEG
        and row["magnetic_width_ratio"] == 1.0
        and row["speed_ratio"] == 1.0
        and row["lateral_error_ratio"] == 0.10
    ]
    selected.sort(key=lambda row: float(row["spacing_ratio"]))
    baseline_time = next(
        float(row["mission_time_normalized"])
        for row in selected
        if math.isclose(float(row["spacing_ratio"]), 0.8)
    )
    for row in selected:
        row["mission_time_vs_spacing_0p8"] = (
            float(row["mission_time_normalized"]) / baseline_time
        )
    return selected


def write_plots(output_dir: Path, rows: list[dict[str, object]]) -> list[Path]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    figures_dir = output_dir / "figures"
    reference = [
        row
        for row in rows
        if row["beam_deg"] == REFERENCE_BEAM_DEG
        and row["magnetic_width_ratio"] == 1.0
        and row["speed_ratio"] == 1.0
    ]
    spacings = sorted({float(row["spacing_ratio"]) for row in reference})
    errors = sorted({float(row["lateral_error_ratio"]) for row in reference})
    coverage = np.zeros((len(errors), len(spacings)))
    for row in reference:
        i = errors.index(float(row["lateral_error_ratio"]))
        j = spacings.index(float(row["spacing_ratio"]))
        coverage[i, j] = float(row["guaranteed_coverage_ratio"])

    fig, ax = plt.subplots(figsize=(7.2, 4.5), dpi=180)
    image = ax.imshow(
        coverage,
        origin="lower",
        aspect="auto",
        vmin=0.7,
        vmax=1.0,
        cmap="viridis",
    )
    ax.set_xticks(range(len(spacings)), [f"{value:.1f}" for value in spacings])
    ax.set_yticks(range(len(errors)), [f"{value:.2f}" for value in errors])
    ax.set_xlabel("Track spacing / effective swath")
    ax.set_ylabel("Lateral error / effective swath")
    ax.set_title("Guaranteed normalized coverage")
    for i in range(len(errors)):
        for j in range(len(spacings)):
            color = "white" if coverage[i, j] < 0.86 else "black"
            ax.text(
                j,
                i,
                f"{coverage[i, j]:.3f}",
                ha="center",
                va="center",
                color=color,
                fontsize=8,
            )
    fig.colorbar(image, ax=ax, label="Guaranteed coverage ratio")
    fig.tight_layout()
    heatmap_png = figures_dir / "normalized_coverage_heatmap.png"
    heatmap_pdf = figures_dir / "normalized_coverage_heatmap.pdf"
    fig.savefig(heatmap_png)
    fig.savefig(heatmap_pdf)
    plt.close(fig)

    reference_rows = select_reference_rows(rows)
    fig, ax1 = plt.subplots(figsize=(7.2, 4.5), dpi=180)
    x = [float(row["spacing_ratio"]) for row in reference_rows]
    coverage_y = [float(row["guaranteed_coverage_ratio"]) for row in reference_rows]
    time_y = [float(row["mission_time_vs_spacing_0p8"]) for row in reference_rows]
    ax1.plot(x, coverage_y, "o-", color="#0072B2", label="Guaranteed coverage")
    ax1.axvline(0.8, color="#666666", linestyle="--", linewidth=1.0)
    ax1.set_xlabel("Track spacing / effective swath")
    ax1.set_ylabel("Guaranteed coverage ratio", color="#0072B2")
    ax1.set_ylim(0.75, 1.02)
    ax2 = ax1.twinx()
    ax2.plot(x, time_y, "s-", color="#D55E00", label="Mission time index")
    ax2.set_ylabel("Mission time / 0.8-spacing case", color="#D55E00")
    ax1.set_title("Coverage-time tradeoff at 10% lateral-error ratio")
    fig.tight_layout()
    tradeoff_png = figures_dir / "normalized_coverage_time_tradeoff.png"
    tradeoff_pdf = figures_dir / "normalized_coverage_time_tradeoff.pdf"
    fig.savefig(tradeoff_png)
    fig.savefig(tradeoff_pdf)
    plt.close(fig)
    return [heatmap_png, heatmap_pdf, tradeoff_png, tradeoff_pdf]


def write_report(
    output_dir: Path,
    args: argparse.Namespace,
    rows: list[dict[str, object]],
    reference_rows: list[dict[str, object]],
) -> None:
    robust = [
        row
        for row in rows
        if float(row["lateral_error_ratio"]) == 0.10
        and float(row["guaranteed_coverage_ratio"]) >= 0.95
    ]
    fastest_robust = max(
        robust,
        key=lambda row: float(row["area_rate_normalized"]),
    )
    lines = [
        "# R12 Normalized Coverage Sweep",
        "",
        "## Scope",
        "",
        "- All lengths are normalized by the effective-width reference; no hardware absolute range is asserted.",
        f"- Survey rectangle: `{args.area_along_ratio} x {args.area_cross_ratio}` reference-width units.",
        "- Sonar swath follows `2 h tan(beta/2)` at fixed normalized altitude.",
        "- Joint coverage uses the smaller of sonar and magnetic effective widths.",
        "- U-turn length uses a semicircle with diameter equal to track spacing.",
        "",
        "## Coverage Model",
        "",
        "`lambda = d / W_eff`, `overlap = 1 - lambda`, and",
        "`C_guaranteed = min(1, (1 - 2 epsilon) / lambda)`,",
        "where `epsilon` is lateral error normalized by effective swath.",
        "",
        "## Reference Case",
        "",
        "| spacing ratio | overlap | guaranteed coverage | tracks | path length | time vs 0.8 |",
        "|---:|---:|---:|---:|---:|---:|",
    ]
    for row in reference_rows:
        lines.append(
            "| {spacing:.1f} | {overlap:.1%} | {coverage:.1%} | {tracks} | {path:.2f} | {time:.3f} |".format(
                spacing=float(row["spacing_ratio"]),
                overlap=float(row["nominal_overlap_ratio"]),
                coverage=float(row["guaranteed_coverage_ratio"]),
                tracks=int(row["track_count"]),
                path=float(row["path_length_normalized"]),
                time=float(row["mission_time_vs_spacing_0p8"]),
            )
        )
    lines.extend(
        [
            "",
            "At a 10% lateral-error ratio, `lambda=0.8` is the largest sampled spacing "
            "that retains full guaranteed coverage. Increasing it to 0.9 reduces the "
            "guaranteed coverage ratio to 0.889; reducing it below 0.8 adds overlap "
            "and mission time without increasing the capped coverage ratio.",
            "",
            "The fastest configuration satisfying 95% guaranteed coverage in the full "
            "grid is reported only as a normalized design point:",
            "",
            f"- beam angle: `{fastest_robust['beam_deg']}` deg",
            f"- magnetic width ratio: `{fastest_robust['magnetic_width_ratio']}`",
            f"- spacing ratio: `{fastest_robust['spacing_ratio']}`",
            f"- speed ratio: `{fastest_robust['speed_ratio']}`",
            f"- normalized area rate: `{float(fastest_robust['area_rate_normalized']):.6f}`",
            "",
            "Absolute spacing, distance, and duration require measured sonar altitude, "
            "beam pattern, magnetic detection width, vehicle turn radius, and speed limits.",
            "",
        ]
    )
    (output_dir / "report.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    args = parse_args()
    validate_axes(args)
    stamp = time.strftime("%Y%m%dT%H%M%S")
    output_dir = args.output_dir or (
        REPO_ROOT / "results" / "coverage_normalized" / f"{stamp}_r12"
    )
    initialize_bundle(
        output_dir,
        experiment_id=f"r12_normalized_coverage_{stamp}",
        runner=str(Path(__file__).resolve().relative_to(REPO_ROOT)),
        argv=sys.argv,
        data_layer="analytic_normalized_geometry",
        matrix={
            "beam_deg": args.beam_deg,
            "magnetic_width_ratios": args.magnetic_width_ratios,
            "spacing_ratios": args.spacing_ratios,
            "speed_ratios": args.speed_ratios,
            "lateral_error_ratios": args.lateral_error_ratios,
        },
        duration_s=0,
        config_paths=[Path(__file__)],
        extra_manifest={
            "reference_beam_deg": REFERENCE_BEAM_DEG,
            "area_along_ratio": args.area_along_ratio,
            "area_cross_ratio": args.area_cross_ratio,
            "absolute_hardware_claim": False,
        },
    )
    rows = generate_rows(args)
    reference_rows = select_reference_rows(rows)
    write_csv(output_dir / "coverage_sweep.csv", rows)
    write_csv(output_dir / "reference_spacing_table.csv", reference_rows)
    finalize_bundle(output_dir, rows)
    figures = write_plots(output_dir, rows)
    write_report(output_dir, args, rows, reference_rows)
    summary = {
        "row_count": len(rows),
        "reference_beam_deg": REFERENCE_BEAM_DEG,
        "reference_error_ratio": 0.10,
        "reference_rows": reference_rows,
        "figures": [str(path.relative_to(output_dir)) for path in figures],
        "absolute_hardware_claim": False,
    }
    (output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    thesis_figure = (
        REPO_ROOT
        / "docs"
        / "thesis"
        / "figures"
        / "experiments"
        / "coverage"
        / "normalized_coverage_time_tradeoff.png"
    )
    thesis_figure.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(
        output_dir / "figures" / "normalized_coverage_time_tradeoff.png",
        thesis_figure,
    )
    print(f"[R12] rows={len(rows)} output={output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

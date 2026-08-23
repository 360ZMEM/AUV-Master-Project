#!/usr/bin/env python3
"""Plot magnetometer lever-arm calibration validation artifacts."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
from tools import thesis_plot_style as tps  # noqa: E402

DEFAULT_INPUT = PROJECT_ROOT / "results/mag_extrinsics/fullflow_20260705_2145"
DEFAULT_OUTPUT = (
    PROJECT_ROOT
    / "docs/thesis/figures/experiments/mag_lever_arm_fullflow_20260705_2145"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def _resolve(path: Path) -> Path:
    return path if path.is_absolute() else PROJECT_ROOT / path


def _read_residuals(path: Path) -> tuple[list[float], list[float]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    return (
        [float(row["time_s"]) for row in rows],
        [float(row["residual_m"]) for row in rows],
    )


def main() -> None:
    args = parse_args()
    input_dir = _resolve(args.input_dir)
    output_dir = _resolve(args.output_dir) if args.output_dir else input_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        import matplotlib.pyplot as plt  # type: ignore
    except Exception as exc:
        raise SystemExit(f"matplotlib unavailable: {exc}") from exc

    tps.apply_thesis_style(layout="full")

    summary = json.loads((input_dir / "validation_summary.json").read_text(encoding="utf-8"))
    times, residuals = _read_residuals(input_dir / "residuals.csv")

    fig, axis = plt.subplots(
        figsize=tps.figure_size("full", height=3.0),
        constrained_layout=True,
    )
    axis.plot(times, residuals, color=tps.PROPOSED, label="平移残差")
    axis.set_xlabel("时间 (s)")
    axis.set_ylabel("残差 (m)")
    axis.legend()
    tps.save_figure(fig, output_dir / "01_mag_extrinsics_residual")
    plt.close(fig)

    labels = ["标定前", "标定后"]
    translation_errors = [
        float(summary["initial_translation_error_m"]),
        float(summary["estimated_translation_error_m"]),
    ]
    rotation_errors = [
        float(summary["initial_rotation_error_deg"]),
        float(summary["estimated_rotation_error_deg"]),
    ]

    fig, axes = plt.subplots(
        1,
        2,
        figsize=tps.figure_size("full", height=3.0),
        constrained_layout=True,
    )
    axes[0].bar(
        labels,
        translation_errors,
        color=[tps.BASELINE_1, tps.PROPOSED],
        hatch=["//", ""],
    )
    axes[0].set_title("平移误差")
    axes[0].set_ylabel("m")
    axes[0].grid(True, axis="y", alpha=0.3)

    axes[1].bar(
        labels,
        rotation_errors,
        color=[tps.BASELINE_1, tps.PROPOSED],
        hatch=["//", ""],
    )
    axes[1].set_title("旋转误差")
    axes[1].set_ylabel("deg")
    axes[1].grid(True, axis="y", alpha=0.3)

    tps.save_figure(fig, output_dir / "02_mag_extrinsics_error_reduction")
    plt.close(fig)

    manifest = {
        "input_dir": str(input_dir),
        "generated": [
            "01_mag_extrinsics_residual.pdf",
            "01_mag_extrinsics_residual.png",
            "02_mag_extrinsics_error_reduction.pdf",
            "02_mag_extrinsics_error_reduction.png",
        ],
    }
    (output_dir / "plot_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[OK] wrote magnetometer extrinsics plots to {output_dir}")


if __name__ == "__main__":
    main()

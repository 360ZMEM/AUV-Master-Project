#!/usr/bin/env python3
"""F1 — three-phase helical cable magnetic leakage spatial scan (thesis §2.3.2).

This offline experiment contrasts the magnetic leakage signature of two cable
constructions, both carrying the same HVDC magnitude, as an AUV flies a straight
line at constant altitude above the cable axis:

  - single-core straight conductor: a smooth, slowly varying |B| along travel;
  - three-phase helically-twisted bundle (3 conductors, 120 deg apart, fixed
    pitch): a spatially periodic |B| ripple whose period equals the helix pitch.

The balanced three-phase currents sum to zero at any instant, so the far field
largely cancels; what remains is a near-field signature modulated by the helix
geometry. As the nearest conductor spirals around the axis, the leakage seen by a
fixed-altitude vehicle oscillates with the pitch — a feature that single-core
models cannot reproduce. Reuses perception_engine's MU0 / CablePath /
compute_biot_savart_hvdc Biot-Savart core.
"""

from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import dataclass
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from common.env_utils import get_output_dir  # noqa: E402
from sim_holoocean.interfaces.perception_engine import (  # noqa: E402
    CablePath,
    compute_biot_savart_hvdc,
)

TESLA_TO_NT = 1.0e9


@dataclass(frozen=True)
class ScanConfig:
    # Cable axis is padded well beyond the scan window so the single-core field is
    # quasi-uniform across the scan (finite-wire endpoint effects pushed away) and
    # the three-phase pitch ripple is the dominant remaining feature.
    axis_start_m: float = -15.0
    axis_end_m: float = 25.0
    scan_travel_m: float = 10.0
    scan_samples: int = 400
    altitude_m: float = 2.0
    seabed_z_m: float = 15.0
    helix_radius_m: float = 0.15
    helix_pitch_m: float = 1.2
    helix_segments: int = 6000
    current_amp: float = 500.0


def build_single_core(cfg: ScanConfig) -> CablePath:
    """Straight conductor along +x at the seabed axis.

    Finely discretized to the same segment count as the helix so both share an
    identical Biot-Savart quadrature (compute_biot_savart_hvdc places one current
    element per segment midpoint); a coarse 2-point path would otherwise be a poor
    line-integral approximation and produce spurious ripple.
    """
    x = np.linspace(cfg.axis_start_m, cfg.axis_end_m, cfg.helix_segments)
    pts = np.column_stack([x, np.zeros_like(x), np.full_like(x, cfg.seabed_z_m)])
    return CablePath(pts)


def build_three_phase_helix(cfg: ScanConfig) -> list[tuple[CablePath, float]]:
    """Three conductors spiralling around the +x axis, 120 deg apart.

    Returns (cable, instantaneous_current) per phase. The snapshot phase angle is
    chosen so the three balanced currents sum to zero: [+I, -I/2, -I/2].
    """
    x = np.linspace(cfg.axis_start_m, cfg.axis_end_m, cfg.helix_segments)
    base_angle = 2.0 * np.pi * x / cfg.helix_pitch_m
    phase_offsets = [0.0, 2.0 * np.pi / 3.0, 4.0 * np.pi / 3.0]
    # Balanced three-phase snapshot: I_k = I * cos(offset_k), sum == 0.
    currents = [cfg.current_amp * float(np.cos(off)) for off in phase_offsets]

    cables: list[tuple[CablePath, float]] = []
    for offset, current in zip(phase_offsets, currents):
        theta = base_angle + offset
        y = cfg.helix_radius_m * np.cos(theta)
        z = cfg.seabed_z_m + cfg.helix_radius_m * np.sin(theta)
        pts = np.column_stack([x, y, z])
        cables.append((CablePath(pts), current))
    return cables


def scan_field(
    cfg: ScanConfig,
    single: CablePath,
    helix: list[tuple[CablePath, float]],
) -> dict[str, np.ndarray]:
    x_scan = np.linspace(0.0, cfg.scan_travel_m, cfg.scan_samples)
    auv_z = cfg.seabed_z_m - cfg.altitude_m  # fly altitude_m above the axis
    b_single = np.zeros(x_scan.size, dtype=float)
    b_helix = np.zeros(x_scan.size, dtype=float)
    for i, xq in enumerate(x_scan):
        pos = np.array([xq, 0.0, auv_z], dtype=float)
        b_single[i] = float(np.linalg.norm(
            compute_biot_savart_hvdc(pos, single, current_amp=cfg.current_amp)
        ))
        b_sum = np.zeros(3, dtype=float)
        for cable, current in helix:
            b_sum += compute_biot_savart_hvdc(pos, cable, current_amp=current)
        b_helix[i] = float(np.linalg.norm(b_sum))
    return {
        "x_m": x_scan,
        "b_single_nT": b_single * TESLA_TO_NT,
        "b_threephase_nT": b_helix * TESLA_TO_NT,
    }


def write_csv(path: Path, data: dict[str, np.ndarray]) -> None:
    keys = list(data.keys())
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(keys)
        for row in zip(*[data[k] for k in keys]):
            writer.writerow([f"{v:.9g}" for v in row])


def plot_scan(path: Path, cfg: ScanConfig, data: dict[str, np.ndarray]) -> None:
    fig, ax = plt.subplots(figsize=(8.4, 4.6))
    ax.plot(data["x_m"], data["b_single_nT"], color="#4c72b0", linewidth=1.8,
            label="single-core straight")
    ax.plot(data["x_m"], data["b_threephase_nT"], color="#c44e52", linewidth=1.6,
            label=f"three-phase helix (pitch {cfg.helix_pitch_m:.1f} m)")
    # Mark pitch periods to show the ripple matches the helix pitch.
    n_periods = int(cfg.scan_travel_m / cfg.helix_pitch_m)
    for k in range(1, n_periods + 1):
        ax.axvline(k * cfg.helix_pitch_m, color="#999999", linestyle=":", linewidth=0.7)
    ax.set_xlabel("along-axis travel x (m)")
    ax.set_ylabel("|B| at AUV (nT)")
    ax.set_title(
        f"HVDC cable leakage at {cfg.altitude_m:.0f} m altitude: "
        f"single-core vs three-phase helix"
    )
    ax.grid(True, alpha=0.3)
    ax.legend(frameon=False)
    fig.text(
        0.01, 0.005,
        f"Biot-Savart, I={cfg.current_amp:.0f} A; helix r={cfg.helix_radius_m:.2f} m, "
        f"pitch={cfg.helix_pitch_m:.1f} m; dotted = pitch periods",
        fontsize=7.5, color="#555555", ha="left", va="bottom",
    )
    fig.tight_layout()
    for ext in ("png", "pdf"):
        fig.savefig(path.with_suffix(f".{ext}"), bbox_inches="tight")
    plt.close(fig)


def ripple_metrics(data: dict[str, np.ndarray]) -> dict[str, float]:
    def stats(arr: np.ndarray) -> tuple[float, float, float]:
        mean = float(np.mean(arr))
        ripple = float(np.max(arr) - np.min(arr))
        rel = ripple / mean if mean > 0 else float("nan")
        return mean, ripple, rel

    s_mean, s_ripple, s_rel = stats(data["b_single_nT"])
    h_mean, h_ripple, h_rel = stats(data["b_threephase_nT"])
    return {
        "single_mean_nT": s_mean,
        "single_ripple_nT": s_ripple,
        "single_ripple_ratio": s_rel,
        "threephase_mean_nT": h_mean,
        "threephase_ripple_nT": h_ripple,
        "threephase_ripple_ratio": h_rel,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pitch-m", type=float, default=1.2)
    parser.add_argument("--helix-radius-m", type=float, default=0.15)
    parser.add_argument("--altitude-m", type=float, default=2.0)
    parser.add_argument("--current-amp", type=float, default=500.0)
    parser.add_argument("--output-dir", type=Path, default=None)
    args = parser.parse_args()

    cfg = ScanConfig(
        helix_pitch_m=args.pitch_m,
        helix_radius_m=args.helix_radius_m,
        altitude_m=args.altitude_m,
        current_amp=args.current_amp,
    )
    out = args.output_dir or get_output_dir("results/perception/helical_cable_magnetic_scan")
    out.mkdir(parents=True, exist_ok=True)

    single = build_single_core(cfg)
    helix = build_three_phase_helix(cfg)
    data = scan_field(cfg, single, helix)

    write_csv(out / "magnetic_scan.csv", data)
    plot_scan(out / "helical_cable_magnetic_scan", cfg, data)

    metrics = ripple_metrics(data)
    with (out / "ripple_metrics.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["metric", "value"])
        for key, value in metrics.items():
            writer.writerow([key, f"{value:.9g}"])

    print(f"[OK] output: {out}")
    print(f"[OK] single-core: mean={metrics['single_mean_nT']:.3g} nT, "
          f"ripple={metrics['single_ripple_ratio'] * 100:.1f}%")
    print(f"[OK] three-phase: mean={metrics['threephase_mean_nT']:.3g} nT, "
          f"ripple={metrics['threephase_ripple_ratio'] * 100:.1f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

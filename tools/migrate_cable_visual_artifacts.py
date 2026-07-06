#!/usr/bin/env python3
"""Migrate cable inspection report artifacts into thesis figure assets."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import shutil
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=PROJECT_ROOT / "results/cable_ops_report/smoke")
    parser.add_argument(
        "--target-dir",
        type=Path,
        default=PROJECT_ROOT / "docs/thesis/figures/experiments/cable_mag_integration",
    )
    return parser.parse_args()


def _resolve(path: Path) -> Path:
    return path if path.is_absolute() else PROJECT_ROOT / path


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _plot_outputs(source_dir: Path, target_dir: Path) -> list[str]:
    generated: list[str] = []
    try:
        import matplotlib.pyplot as plt  # type: ignore
    except Exception as exc:
        return [f"matplotlib unavailable, skipped plots: {exc}"]

    burial_rows = _read_csv(source_dir / "burial_profile.csv")
    route_rows = _read_csv(source_dir / "route_deviation.csv")
    ops_rows = _read_csv(source_dir / "cable_ops_points.csv")

    if burial_rows:
        x = [float(r.get("route_progress_m") or 0.0) for r in burial_rows]
        burial = [float(r.get("burial_depth_m") or 0.0) for r in burial_rows]
        sigma = [float(r.get("burial_sigma_m") or 0.0) for r in burial_rows]
        plt.figure(figsize=(7, 4))
        plt.plot(x, burial, label="burial depth m", linewidth=2)
        plt.plot(x, sigma, label="burial sigma m", linewidth=2)
        plt.axhline(0.15, color="tab:red", linestyle="--", label="0.15 m accuracy target")
        plt.xlabel("route progress m")
        plt.ylabel("m")
        plt.title("Cable Burial Profile")
        plt.grid(True, alpha=0.3)
        plt.legend()
        out = target_dir / "01_cable_burial_profile.png"
        plt.tight_layout()
        plt.savefig(out, dpi=180)
        plt.close()
        generated.append(out.name)

    if route_rows:
        x = [float(r.get("route_progress_m") or 0.0) for r in route_rows]
        cross_track = [float(r.get("cross_track_m") or 0.0) for r in route_rows]
        plt.figure(figsize=(7, 4))
        plt.plot(x, cross_track, label="cross-track m", linewidth=2)
        plt.axhline(0.0, color="black", linewidth=1)
        plt.xlabel("route progress m")
        plt.ylabel("m")
        plt.title("Cable Route Deviation")
        plt.grid(True, alpha=0.3)
        plt.legend()
        out = target_dir / "02_cable_route_deviation.png"
        plt.tight_layout()
        plt.savefig(out, dpi=180)
        plt.close()
        generated.append(out.name)

    if ops_rows:
        x = [float(r.get("route_progress_m") or 0.0) for r in ops_rows]
        confidence = [float(r.get("confidence") or 0.0) for r in ops_rows]
        plt.figure(figsize=(7, 4))
        plt.plot(x, confidence, label="tracking confidence", linewidth=2)
        plt.ylim(0.0, 1.05)
        plt.xlabel("route progress m")
        plt.ylabel("confidence")
        plt.title("Cable Tracking Confidence")
        plt.grid(True, alpha=0.3)
        plt.legend()
        out = target_dir / "03_cable_tracking_confidence.png"
        plt.tight_layout()
        plt.savefig(out, dpi=180)
        plt.close()
        generated.append(out.name)

    return generated


def main() -> None:
    args = parse_args()
    source_dir = _resolve(args.source_dir)
    target_dir = _resolve(args.target_dir)
    if not source_dir.is_dir():
        raise SystemExit(f"missing source dir: {source_dir}")
    target_dir.mkdir(parents=True, exist_ok=True)

    copied = []
    for name in [
        "cable_ops_points.csv",
        "burial_profile.csv",
        "route_deviation.csv",
        "inspection_summary.json",
        "dlt1278_report.md",
    ]:
        src = source_dir / name
        if src.is_file():
            shutil.copy2(src, target_dir / name)
            copied.append(name)

    generated = _plot_outputs(source_dir, target_dir)
    source = {
        "source_dir": str(source_dir),
        "copied": copied,
        "generated": generated,
    }
    (target_dir / "_SOURCE.md").write_text(
        "# Cable Magnetic Integration Figures\n\n"
        f"- Source dir: `{source_dir}`\n"
        f"- Copied files: {', '.join(copied) if copied else 'none'}\n"
        f"- Generated files: {', '.join(generated) if generated else 'none'}\n",
        encoding="utf-8",
    )
    (target_dir / "manifest.json").write_text(json.dumps(source, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[OK] migrated artifacts to {target_dir}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Generate a thesis-friendly animated GIF from cable tracking JSONL."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tracking-jsonl", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--last-frame-png", type=Path, default=None)
    parser.add_argument("--fps", type=int, default=12)
    parser.add_argument("--max-frames", type=int, default=180)
    parser.add_argument("--dpi", type=int, default=120)
    parser.add_argument("--route-offset-target-m", type=float, default=2.0)
    parser.add_argument("--burial-target-m", type=float, default=1.5)
    parser.add_argument("--burial-sigma-target-m", type=float, default=0.15)
    parser.add_argument("--confidence-target", type=float, default=0.65)
    parser.add_argument("--title", default="Cable Tracking Dynamic Inspection")
    return parser.parse_args()


def _resolve(path: Path) -> Path:
    return path if path.is_absolute() else PROJECT_ROOT / path


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    if not rows:
        raise SystemExit(f"tracking JSONL has no rows: {path}")
    return rows


def _float(value: Any, default: float = math.nan) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _xy(row: dict[str, Any]) -> tuple[float, float]:
    point = row.get("estimated_cable_xy_m") or row.get("cable_xy_m") or [math.nan, math.nan]
    if not isinstance(point, (list, tuple)) or len(point) < 2:
        return math.nan, math.nan
    return _float(point[0]), _float(point[1])


def _downsample_indices(count: int, max_frames: int) -> list[int]:
    if count <= max_frames:
        return list(range(count))
    step = (count - 1) / float(max_frames - 1)
    return sorted({int(round(i * step)) for i in range(max_frames)})


def _finite_limits(values: list[float], pad_ratio: float = 0.08) -> tuple[float, float]:
    finite = [value for value in values if math.isfinite(value)]
    if not finite:
        return -1.0, 1.0
    lo = min(finite)
    hi = max(finite)
    if abs(hi - lo) < 1.0e-9:
        return lo - 1.0, hi + 1.0
    pad = (hi - lo) * pad_ratio
    return lo - pad, hi + pad


def _series(rows: list[dict[str, Any]], key: str) -> list[float]:
    return [_float(row.get(key)) for row in rows]


def main() -> None:
    args = parse_args()
    tracking_path = _resolve(args.tracking_jsonl)
    output_path = _resolve(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if args.last_frame_png is not None:
        last_frame_path = _resolve(args.last_frame_png)
        last_frame_path.parent.mkdir(parents=True, exist_ok=True)
    else:
        last_frame_path = None

    rows = _read_jsonl(tracking_path)
    frame_indices = _downsample_indices(len(rows), max(2, int(args.max_frames)))

    try:
        import matplotlib.pyplot as plt  # type: ignore
        from matplotlib.animation import FuncAnimation, PillowWriter  # type: ignore
    except Exception as exc:
        raise SystemExit(f"matplotlib animation unavailable: {exc}") from exc

    xs: list[float] = []
    ys: list[float] = []
    for row in rows:
        x, y = _xy(row)
        xs.append(x)
        ys.append(y)
    progress = _series(rows, "route_progress_m")
    cross_track = _series(rows, "cross_track_m")
    burial = _series(rows, "burial_depth_m")
    burial_sigma = _series(rows, "burial_sigma_m")
    confidence = _series(rows, "confidence")
    magnetic_snr = _series(rows, "magnetic_snr_db")

    xlim = _finite_limits(xs)
    ylim = _finite_limits(ys)
    progress_lim = _finite_limits(progress)
    cross_lim = _finite_limits(cross_track + [-args.route_offset_target_m, args.route_offset_target_m])
    burial_lim = _finite_limits(
        [v for v in burial if math.isfinite(v)] + [args.burial_target_m, args.burial_sigma_target_m]
    )

    fig = plt.figure(figsize=(11, 7))
    grid = fig.add_gridspec(2, 2, height_ratios=[1.15, 1.0])
    ax_xy = fig.add_subplot(grid[0, 0])
    ax_offset = fig.add_subplot(grid[0, 1])
    ax_burial = fig.add_subplot(grid[1, 0])
    ax_status = fig.add_subplot(grid[1, 1])

    fig.suptitle(args.title)
    ax_xy.set_title("Estimated cable track")
    ax_xy.set_xlabel("local x m")
    ax_xy.set_ylabel("local y m")
    ax_xy.set_xlim(*xlim)
    ax_xy.set_ylim(*ylim)
    ax_xy.set_aspect("equal", adjustable="box")
    ax_xy.grid(True, alpha=0.3)
    ax_xy.plot(xs, ys, color="lightgray", linewidth=1.0, label="full track")
    xy_line, = ax_xy.plot([], [], color="tab:blue", linewidth=2.0, label="tracked")
    xy_head = ax_xy.scatter([], [], s=60, color="tab:red", zorder=3, label="current")
    ax_xy.legend(loc="best")

    ax_offset.set_title("Route offset")
    ax_offset.set_xlabel("route progress m")
    ax_offset.set_ylabel("cross-track m")
    ax_offset.set_xlim(*progress_lim)
    ax_offset.set_ylim(*cross_lim)
    ax_offset.grid(True, alpha=0.3)
    ax_offset.axhline(args.route_offset_target_m, color="tab:red", linestyle="--", linewidth=1.0)
    ax_offset.axhline(-args.route_offset_target_m, color="tab:red", linestyle="--", linewidth=1.0)
    offset_line, = ax_offset.plot([], [], color="tab:orange", linewidth=2.0)

    ax_burial.set_title("Burial inversion")
    ax_burial.set_xlabel("route progress m")
    ax_burial.set_ylabel("m")
    ax_burial.set_xlim(*progress_lim)
    ax_burial.set_ylim(*burial_lim)
    ax_burial.grid(True, alpha=0.3)
    ax_burial.axhline(args.burial_target_m, color="tab:green", linestyle="--", linewidth=1.0, label="burial target")
    ax_burial.axhline(args.burial_sigma_target_m, color="tab:red", linestyle=":", linewidth=1.0, label="sigma target")
    burial_line, = ax_burial.plot([], [], color="tab:green", linewidth=2.0, label="burial depth")
    sigma_line, = ax_burial.plot([], [], color="tab:red", linewidth=1.5, alpha=0.8, label="burial sigma")
    ax_burial.legend(loc="best")

    ax_status.axis("off")
    status_text = ax_status.text(0.02, 0.98, "", va="top", ha="left", family="monospace", fontsize=10)

    def update(frame_no: int):
        idx = frame_indices[frame_no]
        sl = slice(0, idx + 1)
        xy_line.set_data(xs[sl], ys[sl])
        xy_head.set_offsets([[xs[idx], ys[idx]]])
        offset_line.set_data(progress[sl], cross_track[sl])
        burial_line.set_data(progress[sl], burial[sl])
        sigma_line.set_data(progress[sl], burial_sigma[sl])

        row = rows[idx]
        status = [
            f"sample: {idx + 1}/{len(rows)}",
            f"route progress: {_float(row.get('route_progress_m'), 0.0):7.2f} m",
            f"cross-track:    {_float(row.get('cross_track_m'), 0.0):7.3f} m",
            f"burial depth:  {_float(row.get('burial_depth_m'), 0.0):7.3f} m",
            f"burial sigma:  {_float(row.get('burial_sigma_m'), 0.0):7.3f} m",
            f"confidence:    {_float(row.get('confidence'), 0.0):7.3f}",
            f"mag SNR:       {_float(row.get('magnetic_snr_db'), 0.0):7.2f} dB",
            f"ready:         {bool(row.get('industrial_ready', False))}",
            f"mode:          {row.get('mode', '--')}",
        ]
        if math.isfinite(confidence[idx]) and confidence[idx] < args.confidence_target:
            status.append("status: confidence below target")
        elif math.isfinite(magnetic_snr[idx]):
            status.append("status: magnetic tracking active")
        else:
            status.append("status: tracking")
        status_text.set_text("\n".join(status))
        return xy_line, xy_head, offset_line, burial_line, sigma_line, status_text

    animation = FuncAnimation(fig, update, frames=len(frame_indices), interval=1000 / max(1, args.fps), blit=False)
    animation.save(output_path, writer=PillowWriter(fps=max(1, args.fps)), dpi=args.dpi)
    if last_frame_path is not None:
        update(len(frame_indices) - 1)
        fig.savefig(last_frame_path, dpi=args.dpi)
    plt.close(fig)

    print(f"[OK] wrote GIF: {output_path}")
    if last_frame_path is not None:
        print(f"[OK] wrote last frame: {last_frame_path}")


if __name__ == "__main__":
    main()

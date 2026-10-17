#!/usr/bin/env python3
"""Render a defense-ready cable-inspection tactical replay from tracking.jsonl.

This is the offline fallback for machines where Foxglove login is unavailable.
It visualizes recorded estimator evidence and labels itself as a telemetry
replay; it does not claim to be a Foxglove capture or a real-sea acceptance run.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.animation as animation
import matplotlib.pyplot as plt
from matplotlib import font_manager
import numpy as np

_CJK_FONT = Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc")
if _CJK_FONT.exists():
    font_manager.fontManager.addfont(str(_CJK_FONT))
    _CJK_FAMILY = font_manager.FontProperties(fname=str(_CJK_FONT)).get_name()
else:
    _CJK_FAMILY = "DejaVu Sans"
plt.rcParams["font.sans-serif"] = [_CJK_FAMILY, "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False


ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tracking-jsonl", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--fps", type=int, default=6)
    parser.add_argument("--max-frames", type=int, default=180)
    return parser.parse_args()


def repo_path(path: Path) -> Path:
    return path if path.is_absolute() else ROOT / path


def load_rows(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def sample_indices(count: int, maximum: int) -> list[int]:
    if count <= maximum:
        return list(range(count))
    return np.linspace(0, count - 1, maximum).round().astype(int).tolist()


def number(row: dict, key: str, default: float = 0.0) -> float:
    try:
        value = float(row.get(key, default))
        return value if math.isfinite(value) else default
    except (TypeError, ValueError):
        return default


def main() -> int:
    args = parse_args()
    source = repo_path(args.tracking_jsonl)
    output = repo_path(args.output)
    rows = load_rows(source)
    indices = sample_indices(len(rows), max(2, args.max_frames))
    selected = [rows[index] for index in indices]

    cable = np.asarray([row.get("estimated_cable_xy_m", [0.0, 0.0])[:2] for row in selected], dtype=float)
    headings = np.radians([number(row, "cable_heading_deg") for row in selected])
    cross = np.asarray([number(row, "cross_track_m") for row in selected])
    normals = np.column_stack((-np.sin(headings), np.cos(headings)))
    auv = cable + normals * cross[:, None]

    lo = np.minimum(cable.min(axis=0), auv.min(axis=0)) - [4.0, 8.0]
    hi = np.maximum(cable.max(axis=0), auv.max(axis=0)) + [4.0, 8.0]
    span = max(1.0, hi[0] - lo[0])
    sweep_x = np.linspace(lo[0] + 1.0, hi[0] - 1.0, 11)
    sweep_y = np.where(np.arange(11) % 2 == 0, lo[1] + 1.2, hi[1] - 1.2)

    plt.style.use("dark_background")
    fig = plt.figure(figsize=(10.67, 10.0), dpi=108, facecolor="#07131d")
    grid = fig.add_gridspec(4, 1, height_ratios=[0.13, 0.57, 0.16, 0.14], hspace=0.22)
    ax_title = fig.add_subplot(grid[0])
    ax_map = fig.add_subplot(grid[1])
    ax_cross = fig.add_subplot(grid[2])
    ax_quality = fig.add_subplot(grid[3])

    ax_title.axis("off")
    title = ax_title.text(0.02, 0.72, "AUV 海底电缆自主巡检 · 数字孪生遥测回放", fontsize=20, weight="bold", color="#e6f7ff")
    phase_text = ax_title.text(0.02, 0.18, "", fontsize=15, color="#51cf66")
    metrics_text = ax_title.text(0.98, 0.18, "", fontsize=12, ha="right", color="#b8d8e8")

    ax_map.set_facecolor("#07131d")
    ax_map.grid(color="#1f3542", alpha=0.75, linestyle="--", linewidth=0.7)
    ax_map.set_xlim(lo[0], hi[0])
    ax_map.set_ylim(lo[1], hi[1])
    ax_map.set_aspect("equal", adjustable="box")
    ax_map.set_xlabel("North / m")
    ax_map.set_ylabel("East / m")
    ax_map.fill_between([lo[0], hi[0]], lo[1] + 1.0, hi[1] - 1.0, color="#123846", alpha=0.24, label="搜索廊道")
    ax_map.plot(sweep_x, sweep_y, color="#ff9f43", linewidth=1.5, linestyle="--", alpha=0.75, label="规划 zig-zag")
    ax_map.plot(cable[:, 0], cable[:, 1], color="#f6d64a", linewidth=3.0, alpha=0.9, label="估计海缆")
    trail, = ax_map.plot([], [], color="#4dabf7", linewidth=2.2, label="AUV 轨迹")
    auv_point, = ax_map.plot([], [], marker="o", markersize=10, color="#58a6ff")
    target_point, = ax_map.plot([], [], marker="o", markersize=8, color="#51cf66")
    link, = ax_map.plot([], [], color="#51cf66", linewidth=1.8)
    heading_arrow = ax_map.quiver([], [], [], [], color="#e6f7ff", scale=8.0, width=0.008)
    ax_map.legend(loc="upper right", framealpha=0.55, fontsize=9)

    time_axis = np.arange(len(selected), dtype=float) / max(1, args.fps)
    cross_values = np.asarray([number(row, "cross_track_m") for row in selected])
    confidence = np.asarray([number(row, "confidence") for row in selected])
    snr = np.asarray([number(row, "magnetic_snr_db") for row in selected])
    ax_cross.plot(time_axis, cross_values, color="#ffd166", linewidth=1.4)
    cross_cursor = ax_cross.axvline(0, color="#ffffff", linewidth=1.0)
    ax_cross.axhspan(-1.5, 1.5, color="#2ecc71", alpha=0.10)
    ax_cross.set_ylabel("横偏 / m")
    ax_cross.grid(color="#1f3542", alpha=0.55)
    ax_cross.set_xlim(time_axis[0], max(time_axis[-1], 1.0))

    quality_axis = ax_quality.twinx()
    ax_quality.plot(time_axis, confidence, color="#51cf66", linewidth=1.5, label="置信度")
    quality_axis.plot(time_axis, snr, color="#ff922b", linewidth=1.1, alpha=0.85, label="磁 SNR")
    quality_cursor = ax_quality.axvline(0, color="#ffffff", linewidth=1.0)
    ax_quality.set_ylim(0.0, 1.05)
    quality_axis.set_ylabel("SNR / dB", color="#ff922b")
    ax_quality.set_ylabel("置信度", color="#51cf66")
    ax_quality.set_xlabel("演示时间 / s")
    ax_quality.grid(color="#1f3542", alpha=0.55)
    ax_quality.set_xlim(time_axis[0], max(time_axis[-1], 1.0))

    def update(frame: int):
        row = selected[frame]
        mode = str(row.get("mode", "--")).upper()
        ready = bool(row.get("industrial_ready", False))
        phase_text.set_text(f"MISSION  {mode}   |   {'READY' if ready else 'ALIGNING'}")
        phase_text.set_color("#51cf66" if ready else "#ffbf69")
        metrics_text.set_text(
            f"进度 {number(row, 'route_progress_m'):.1f} m   横偏 {cross_values[frame]:.2f} m\n"
            f"置信度 {confidence[frame]:.3f}   磁 SNR {snr[frame]:.1f} dB"
        )
        trail.set_data(auv[: frame + 1, 0], auv[: frame + 1, 1])
        auv_point.set_data([auv[frame, 0]], [auv[frame, 1]])
        target_point.set_data([cable[frame, 0]], [cable[frame, 1]])
        link.set_data([auv[frame, 0], cable[frame, 0]], [auv[frame, 1], cable[frame, 1]])
        heading_arrow.set_offsets(np.asarray([[auv[frame, 0], auv[frame, 1]]]))
        heading_arrow.set_UVC(np.asarray([math.cos(headings[frame])]), np.asarray([math.sin(headings[frame])]))
        cross_cursor.set_xdata([time_axis[frame], time_axis[frame]])
        quality_cursor.set_xdata([time_axis[frame], time_axis[frame]])
        return title, phase_text, metrics_text, trail, auv_point, target_point, link, heading_arrow, cross_cursor, quality_cursor

    output.parent.mkdir(parents=True, exist_ok=True)
    movie = animation.FuncAnimation(fig, update, frames=len(selected), interval=1000 / max(1, args.fps), blit=False)
    movie.save(str(output), writer=animation.FFMpegWriter(fps=max(1, args.fps), codec="libx264", bitrate=4200), dpi=108)
    plt.close(fig)
    print(f"[OK] tactical replay: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

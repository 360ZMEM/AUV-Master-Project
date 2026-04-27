#!/usr/bin/env python3
"""Generate a lightweight replay video from an AUV MCAP bag.

The script reuses the offline MCAP reader from tools/analyze_bag.py and renders
an animation that shows the estimated and truth trajectories from a top-down
view plus a depth-over-time trace.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = PROJECT_ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import analyze_bag as bag_tools


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Path to a .mcap file or a rosbag2 directory containing .mcap chunks.")
    parser.add_argument("--output", type=Path, default=None, help="Output video path. Defaults to <bag>/replay.gif.")
    parser.add_argument("--format", choices=("gif", "mp4"), default="gif", help="Video container to write.")
    parser.add_argument("--fps", type=int, default=12, help="Playback frame rate.")
    parser.add_argument("--dpi", type=int, default=160, help="Render DPI for the output video.")
    parser.add_argument("--trail", type=int, default=240, help="Maximum number of samples to keep in the trail.")
    parser.add_argument("--estimated-topic", default=bag_tools.DEFAULT_ESTIMATED_TOPIC, help="Estimated pose topic.")
    parser.add_argument("--truth-topic", default=bag_tools.DEFAULT_TRUTH_TOPICS[0], help="Preferred truth pose topic.")
    parser.add_argument("--truth-fallbacks", default=",".join(bag_tools.DEFAULT_TRUTH_TOPICS[1:]), help="Comma-separated truth-topic fallbacks.")
    parser.add_argument("--bt-status-topic", default=bag_tools.DEFAULT_BT_STATUS_TOPIC, help="Behavior-tree status topic.")
    parser.add_argument("--diagnostics-topic", default=bag_tools.DEFAULT_DIAGNOSTICS_TOPIC, help="Diagnostics topic.")
    parser.add_argument("--magnetic-topic", default=bag_tools.DEFAULT_MAGNETIC_TOPIC, help="Magnetic field topic.")
    parser.add_argument("--cable-topic", default=bag_tools.DEFAULT_CABLE_MARKER_TOPIC, help="Cable marker topic.")
    parser.add_argument("--terrain-topic", default=bag_tools.DEFAULT_SEABED_CLOUD_TOPIC, help="Seabed cloud topic.")
    parser.add_argument("--verbose", action="store_true", help="Print readback statistics.")
    return parser.parse_args()


def series_to_numpy(series: bag_tools.PositionSeries) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    if not series.timestamps_ns:
        empty = np.asarray([], dtype=float)
        return empty, empty, empty, empty
    t = np.asarray(series.timestamps_ns, dtype=float)
    t = (t - t[0]) / 1e9
    return t, np.asarray(series.x, dtype=float), np.asarray(series.y, dtype=float), np.asarray(series.z, dtype=float)


def resolve_output_path(input_path: Path, output_path: Path | None, fmt: str) -> Path:
    if output_path is not None:
        return output_path
    anchor = input_path if input_path.is_dir() else input_path.parent
    suffix = ".gif" if fmt == "gif" else ".mp4"
    return anchor / f"replay{suffix}"


def main() -> None:
    args = parse_args()
    bag_tools.ensure_runtime_dependencies()
    bag_tools.configure_matplotlib()

    chunks = bag_tools.resolve_input_chunks(args.input)
    output_path = resolve_output_path(args.input, args.output, args.format)
    truth_topics = bag_tools.candidate_truth_topics(args.truth_topic, args.truth_fallbacks)

    data = bag_tools.read_bag_data(
        chunks=chunks,
        estimated_topic=args.estimated_topic,
        truth_topics=truth_topics,
        bt_status_topic=args.bt_status_topic,
        diagnostics_topic=args.diagnostics_topic,
        magnetic_topic=args.magnetic_topic,
        cable_topic=args.cable_topic,
        terrain_topic=args.terrain_topic,
        verbose=args.verbose,
    )

    estimated_t, estimated_x, estimated_y, estimated_z = series_to_numpy(data.estimated)
    truth_t, truth_x, truth_y, truth_z = series_to_numpy(data.truth)

    if estimated_t.size == 0 and truth_t.size == 0:
        raise SystemExit("No estimated or truth trajectory samples were found in the bag.")

    if estimated_t.size == 0:
        estimated_t, estimated_x, estimated_y, estimated_z = truth_t, truth_x, truth_y, truth_z
    if truth_t.size == 0:
        truth_t, truth_x, truth_y, truth_z = estimated_t, estimated_x, estimated_y, estimated_z

    frames = min(len(estimated_t), len(truth_t))
    if frames <= 1:
        raise SystemExit("Not enough samples to generate a replay animation.")

    if args.trail > 0:
        trail = min(int(args.trail), frames)
    else:
        trail = frames

    import matplotlib.animation as animation
    import matplotlib.pyplot as plt

    fig, (ax_xy, ax_depth) = plt.subplots(2, 1, figsize=(8.4, 7.2), gridspec_kw={"height_ratios": [2.0, 1.0]})
    fig.suptitle("AUV MCAP Replay")

    if data.cable_points_xyz is not None and data.cable_points_xyz.size:
        cable = data.cable_points_xyz
        ax_xy.plot(cable[:, 0], cable[:, 1], color="#7b5", linewidth=2.2, alpha=0.9, label="Cable")

    if data.terrain_points_xyz is not None and data.terrain_points_xyz.size:
        terrain = data.terrain_points_xyz
        sample = terrain[:: max(1, len(terrain) // 4000)]
        ax_xy.scatter(sample[:, 0], sample[:, 1], s=1, alpha=0.08, color="#888", label="Seabed")

    (est_line,) = ax_xy.plot([], [], color="#1f77b4", linewidth=2.0, label="Estimated")
    (truth_line,) = ax_xy.plot([], [], color="#d62728", linewidth=1.8, alpha=0.8, label="Truth")
    (est_point,) = ax_xy.plot([], [], marker="o", color="#1f77b4", markersize=5)
    (truth_point,) = ax_xy.plot([], [], marker="o", color="#d62728", markersize=5)

    ax_xy.set_xlabel("X [m]")
    ax_xy.set_ylabel("Y [m]")
    ax_xy.axis("equal")
    ax_xy.legend(loc="upper right")

    time_axis = np.arange(frames, dtype=float)
    est_depth_series = estimated_z[:frames]
    truth_depth_series = truth_z[:frames]
    (depth_est_line,) = ax_depth.plot([], [], color="#1f77b4", linewidth=1.8, label="Estimated depth")
    (depth_truth_line,) = ax_depth.plot([], [], color="#d62728", linewidth=1.5, alpha=0.8, label="Truth depth")
    (depth_cursor,) = ax_depth.plot([], [], marker="o", color="#222", markersize=5)
    ax_depth.set_xlabel("Frame")
    ax_depth.set_ylabel("Depth [m]")
    ax_depth.legend(loc="upper right")

    all_x = np.concatenate([estimated_x[:frames], truth_x[:frames]])
    all_y = np.concatenate([estimated_y[:frames], truth_y[:frames]])
    if all_x.size and all_y.size:
        pad_x = max(1.0, 0.08 * (float(all_x.max()) - float(all_x.min()) + 1e-9))
        pad_y = max(1.0, 0.08 * (float(all_y.max()) - float(all_y.min()) + 1e-9))
        ax_xy.set_xlim(float(all_x.min()) - pad_x, float(all_x.max()) + pad_x)
        ax_xy.set_ylim(float(all_y.min()) - pad_y, float(all_y.max()) + pad_y)

    all_depth = np.concatenate([est_depth_series, truth_depth_series])
    if all_depth.size:
        depth_min = float(all_depth.min())
        depth_max = float(all_depth.max())
        pad_depth = max(0.5, 0.1 * (depth_max - depth_min + 1e-9))
        ax_depth.set_ylim(depth_min - pad_depth, depth_max + pad_depth)

    status_text = ax_xy.text(0.02, 0.02, "", transform=ax_xy.transAxes, fontsize=10, bbox=dict(facecolor="white", alpha=0.75, edgecolor="none"))

    def update(frame_index: int):
        start = max(0, frame_index - trail)
        est_line.set_data(estimated_x[start:frame_index + 1], estimated_y[start:frame_index + 1])
        truth_line.set_data(truth_x[start:frame_index + 1], truth_y[start:frame_index + 1])
        est_point.set_data([estimated_x[frame_index]], [estimated_y[frame_index]])
        truth_point.set_data([truth_x[frame_index]], [truth_y[frame_index]])

        depth_est_line.set_data(time_axis[:frame_index + 1], est_depth_series[:frame_index + 1])
        depth_truth_line.set_data(time_axis[:frame_index + 1], truth_depth_series[:frame_index + 1])
        depth_cursor.set_data([time_axis[frame_index]], [est_depth_series[frame_index]])

        status_text.set_text(
            f"frame={frame_index}/{frames - 1}  est=({estimated_x[frame_index]:.2f}, {estimated_y[frame_index]:.2f}, {est_depth_series[frame_index]:.2f})"
        )
        return est_line, truth_line, est_point, truth_point, depth_est_line, depth_truth_line, depth_cursor, status_text

    ani = animation.FuncAnimation(fig, update, frames=frames, interval=max(1, int(1000 / max(1, args.fps))), blit=False)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    if args.format == "gif":
        writer = animation.PillowWriter(fps=max(1, args.fps))
        ani.save(str(output_path), writer=writer, dpi=args.dpi)
    else:
        try:
            writer = animation.FFMpegWriter(fps=max(1, args.fps))
        except Exception as exc:
            raise SystemExit("mp4 output requires ffmpeg to be installed and available on PATH") from exc
        ani.save(str(output_path), writer=writer, dpi=args.dpi)

    print(f"Saved replay video to: {output_path}")


if __name__ == "__main__":
    main()

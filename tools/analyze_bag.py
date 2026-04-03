#!/usr/bin/env python3
"""Offline MCAP analysis tool for AUV experiment figures.

Installation:
1. Python dependencies:
   pip install mcap mcap-ros2-support matplotlib numpy
2. This script does not require a running ROS2 graph. It reads ROS2 messages
   directly from MCAP files through `mcap_ros2`.

Examples:
1. Analyze a single MCAP file and export PDF figures:
   python tools/analyze_bag.py /path/to/bag_0.mcap --output-dir ./figures
2. Analyze a rosbag2 directory that contains one or more .mcap chunks:
   python tools/analyze_bag.py /path/to/experiment_bag --format eps
3. Override topic names if a historical bag uses old names:
   python tools/analyze_bag.py /path/to/bag.mcap \
     --topic-diagnostics /auv/diagnostic \
     --topic-magnetic /auv/sensors/mag
"""

from __future__ import annotations

import argparse
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Sequence

import numpy as np

plt = None
read_ros2_messages = None


DEFAULT_ESTIMATED_TOPIC = "/auv/state/filtered"
DEFAULT_TRUTH_TOPICS = (
    "/auv/state/truth",
    "/auv/visual/truth_marker",
    "/auv/sensors/ground_truth",
)
DEFAULT_BT_STATUS_TOPIC = "/auv/bt_status"
DEFAULT_DIAGNOSTICS_TOPIC = "/auv/diagnostics"
DEFAULT_MAGNETIC_TOPIC = "/auv/sensors/magnetic"


def ensure_runtime_dependencies() -> None:
    global plt
    global read_ros2_messages

    if plt is None:
        try:
            import matplotlib

            matplotlib.use("Agg")
            import matplotlib.pyplot as imported_pyplot
        except ImportError as exc:  # pragma: no cover - dependency guard
            raise SystemExit(
                "matplotlib is required. Install it with: pip install matplotlib"
            ) from exc
        plt = imported_pyplot

    if read_ros2_messages is None:
        try:
            from mcap_ros2.reader import read_ros2_messages as imported_reader
        except ImportError as exc:  # pragma: no cover - dependency guard
            raise SystemExit(
                "mcap and mcap-ros2-support are required. Install them with: "
                "pip install mcap mcap-ros2-support"
            ) from exc
        read_ros2_messages = imported_reader


@dataclass
class ScalarSeries:
    timestamps_ns: list[int] = field(default_factory=list)
    values: list[float] = field(default_factory=list)

    def append(self, timestamp_ns: int, value: float) -> None:
        if math.isfinite(value):
            self.timestamps_ns.append(int(timestamp_ns))
            self.values.append(float(value))


@dataclass
class PositionSeries:
    timestamps_ns: list[int] = field(default_factory=list)
    x: list[float] = field(default_factory=list)
    y: list[float] = field(default_factory=list)
    z: list[float] = field(default_factory=list)

    def append(self, timestamp_ns: int, x: float, y: float, z: float) -> None:
        if all(math.isfinite(v) for v in (x, y, z)):
            self.timestamps_ns.append(int(timestamp_ns))
            self.x.append(float(x))
            self.y.append(float(y))
            self.z.append(float(z))


@dataclass
class StringSeries:
    timestamps_ns: list[int] = field(default_factory=list)
    values: list[str] = field(default_factory=list)

    def append(self, timestamp_ns: int, value: str) -> None:
        text = str(value).strip()
        if text:
            self.timestamps_ns.append(int(timestamp_ns))
            self.values.append(text)


@dataclass
class DiagnosticsSeries:
    timestamps_ns: list[int] = field(default_factory=list)
    lateral_error_m: list[float] = field(default_factory=list)
    confidence: list[float] = field(default_factory=list)
    magnetic_magnitude: list[float] = field(default_factory=list)
    mode: list[str] = field(default_factory=list)
    current_behavior: list[str] = field(default_factory=list)
    has_lateral_error: list[bool] = field(default_factory=list)
    has_magnetic_magnitude: list[bool] = field(default_factory=list)

    def append(
        self,
        *,
        timestamp_ns: int,
        lateral_error_m: float,
        confidence: float,
        magnetic_magnitude: float,
        mode: str,
        current_behavior: str,
        has_lateral_error: bool,
        has_magnetic_magnitude: bool,
    ) -> None:
        self.timestamps_ns.append(int(timestamp_ns))
        self.lateral_error_m.append(float(lateral_error_m))
        self.confidence.append(float(confidence))
        self.magnetic_magnitude.append(float(magnetic_magnitude))
        self.mode.append(str(mode))
        self.current_behavior.append(str(current_behavior))
        self.has_lateral_error.append(bool(has_lateral_error))
        self.has_magnetic_magnitude.append(bool(has_magnetic_magnitude))


@dataclass
class BagData:
    estimated: PositionSeries = field(default_factory=PositionSeries)
    truth: PositionSeries = field(default_factory=PositionSeries)
    bt_status: StringSeries = field(default_factory=StringSeries)
    diagnostics: DiagnosticsSeries = field(default_factory=DiagnosticsSeries)
    magnetic: ScalarSeries = field(default_factory=ScalarSeries)
    truth_topic_used: str | None = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "input",
        type=Path,
        help="Path to a .mcap file or a rosbag2 directory that contains .mcap chunks.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Directory to store exported figures. Defaults to <bag>/analysis_figures.",
    )
    parser.add_argument(
        "--format",
        choices=("pdf", "eps"),
        default="pdf",
        help="Vector output format.",
    )
    parser.add_argument(
        "--dpi",
        type=int,
        default=300,
        help="Figure DPI. Kept at 300 by default for print-ready output.",
    )
    parser.add_argument(
        "--topic-estimated-state",
        default=DEFAULT_ESTIMATED_TOPIC,
        help="Estimated odometry topic.",
    )
    parser.add_argument(
        "--topic-truth-state",
        default=DEFAULT_TRUTH_TOPICS[0],
        help="Preferred truth-state topic. If missing, fallback candidates are still tried.",
    )
    parser.add_argument(
        "--topic-truth-fallbacks",
        default=",".join(DEFAULT_TRUTH_TOPICS[1:]),
        help="Comma-separated fallback truth topics.",
    )
    parser.add_argument(
        "--topic-bt-status",
        default=DEFAULT_BT_STATUS_TOPIC,
        help="Behavior-tree markdown status topic.",
    )
    parser.add_argument(
        "--topic-diagnostics",
        default=DEFAULT_DIAGNOSTICS_TOPIC,
        help="Structured diagnostics topic.",
    )
    parser.add_argument(
        "--topic-magnetic",
        default=DEFAULT_MAGNETIC_TOPIC,
        help="Magnetic field vector topic.",
    )
    parser.add_argument(
        "--allow-missing-truth",
        action="store_true",
        help="If set, skip the trajectory comparison figure when no truth source is available.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print additional topic and sample statistics.",
    )
    return parser.parse_args()


def configure_matplotlib() -> None:
    assert plt is not None
    plt.rcParams["font.family"] = "serif"
    plt.rcParams["font.serif"] = ["Times New Roman"]
    plt.rcParams["mathtext.fontset"] = "stix"
    plt.rcParams["font.size"] = 11
    plt.rcParams["axes.labelsize"] = 11
    plt.rcParams["axes.titlesize"] = 12
    plt.rcParams["legend.fontsize"] = 9
    plt.rcParams["xtick.labelsize"] = 10
    plt.rcParams["ytick.labelsize"] = 10
    plt.rcParams["figure.figsize"] = (7.2, 4.8)
    plt.rcParams["axes.grid"] = True
    plt.rcParams["grid.alpha"] = 0.35
    plt.rcParams["grid.linestyle"] = "--"
    plt.rcParams["lines.linewidth"] = 1.6
    plt.rcParams["savefig.bbox"] = "tight"


def resolve_input_chunks(input_path: Path) -> list[Path]:
    if input_path.is_file():
        if input_path.suffix != ".mcap":
            raise SystemExit(f"Expected an .mcap file, got: {input_path}")
        return [input_path]

    if not input_path.is_dir():
        raise SystemExit(f"Input path does not exist: {input_path}")

    mcap_files = sorted(input_path.glob("*.mcap"))
    if not mcap_files:
        raise SystemExit(f"No .mcap files found under: {input_path}")
    return mcap_files


def resolve_output_dir(input_path: Path, explicit_output_dir: Path | None) -> Path:
    if explicit_output_dir is not None:
        explicit_output_dir.mkdir(parents=True, exist_ok=True)
        return explicit_output_dir

    anchor = input_path if input_path.is_dir() else input_path.parent
    output_dir = anchor / "analysis_figures"
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def candidate_truth_topics(preferred: str, fallbacks_csv: str) -> list[str]:
    fallbacks = [item.strip() for item in fallbacks_csv.split(",") if item.strip()]
    topics: list[str] = []
    for topic in [preferred, *fallbacks]:
        if topic and topic not in topics:
            topics.append(topic)
    return topics


def select_timestamp_ns(message_wrapper) -> int:
    publish_time_ns = int(getattr(message_wrapper, "publish_time_ns", 0))
    if publish_time_ns > 0:
        return publish_time_ns
    return int(message_wrapper.log_time_ns)


def nested_attr(obj, path: Sequence[str]):
    value = obj
    for name in path:
        if not hasattr(value, name):
            raise AttributeError(".".join(path))
        value = getattr(value, name)
    return value


def extract_xyz_from_message(msg) -> tuple[float, float, float]:
    position_paths = (
        ("pose", "pose", "position"),
        ("pose", "position"),
        ("position",),
    )
    for path in position_paths:
        try:
            position = nested_attr(msg, path)
        except AttributeError:
            continue
        if all(hasattr(position, axis) for axis in ("x", "y", "z")):
            return float(position.x), float(position.y), float(position.z)

    if hasattr(msg, "position_ned"):
        values = list(getattr(msg, "position_ned"))
        if len(values) >= 3:
            return float(values[0]), float(values[1]), float(values[2])

    if all(hasattr(msg, axis) for axis in ("x", "y", "z")):
        return float(msg.x), float(msg.y), float(msg.z)

    raise ValueError(f"Unsupported position message type: {type(msg).__name__}")


def parse_bt_markdown(markdown_text: str) -> str:
    for line in markdown_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("- Active:"):
            return stripped.split(":", 1)[1].strip()
        if stripped.startswith("- Mode:"):
            return stripped.split(":", 1)[1].strip()
    return markdown_text.strip().splitlines()[0].strip() if markdown_text.strip() else "UNKNOWN"


def read_bag_data(
    *,
    chunks: Sequence[Path],
    estimated_topic: str,
    truth_topics: Sequence[str],
    bt_status_topic: str,
    diagnostics_topic: str,
    magnetic_topic: str,
    verbose: bool,
) -> BagData:
    topics_to_read = {estimated_topic, bt_status_topic, diagnostics_topic, magnetic_topic, *truth_topics}
    data = BagData()

    for chunk in chunks:
        for decoded in read_ros2_messages(str(chunk), topics=topics_to_read):
            topic = decoded.channel.topic
            msg = decoded.ros_msg
            timestamp_ns = select_timestamp_ns(decoded)

            if topic == estimated_topic:
                x, y, z = extract_xyz_from_message(msg)
                data.estimated.append(timestamp_ns, x, y, z)
                continue

            if topic in truth_topics:
                x, y, z = extract_xyz_from_message(msg)
                data.truth.append(timestamp_ns, x, y, z)
                if data.truth_topic_used is None:
                    data.truth_topic_used = topic
                continue

            if topic == bt_status_topic:
                payload = str(getattr(msg, "data", ""))
                data.bt_status.append(timestamp_ns, payload)
                continue

            if topic == diagnostics_topic:
                has_lateral_error = bool(getattr(msg, "has_lateral_error", True))
                has_magnetic_magnitude = bool(getattr(msg, "has_magnetic_magnitude", True))
                data.diagnostics.append(
                    timestamp_ns=timestamp_ns,
                    lateral_error_m=float(getattr(msg, "lateral_error_m", float("nan"))),
                    confidence=float(getattr(msg, "confidence", float("nan"))),
                    magnetic_magnitude=float(getattr(msg, "magnetic_magnitude", float("nan"))),
                    mode=str(getattr(msg, "mode", "")),
                    current_behavior=str(getattr(msg, "current_behavior", "")),
                    has_lateral_error=has_lateral_error,
                    has_magnetic_magnitude=has_magnetic_magnitude,
                )
                continue

            if topic == magnetic_topic:
                magnetic_field = getattr(msg, "magnetic_field", None)
                if magnetic_field is None:
                    continue
                magnitude = math.sqrt(
                    float(magnetic_field.x) ** 2
                    + float(magnetic_field.y) ** 2
                    + float(magnetic_field.z) ** 2
                )
                data.magnetic.append(timestamp_ns, magnitude)

    if verbose:
        print(f"[INFO] Read {len(chunks)} MCAP chunk(s)")
        print(f"[INFO] Estimated samples: {len(data.estimated.timestamps_ns)}")
        print(f"[INFO] Truth samples: {len(data.truth.timestamps_ns)}")
        print(f"[INFO] Diagnostics samples: {len(data.diagnostics.timestamps_ns)}")
        print(f"[INFO] BT status samples: {len(data.bt_status.timestamps_ns)}")
        print(f"[INFO] Magnetic samples: {len(data.magnetic.timestamps_ns)}")

    return data


def as_numpy(values: Sequence[float | int]) -> np.ndarray:
    return np.asarray(values, dtype=float)


def sort_position_series(series: PositionSeries) -> PositionSeries:
    if not series.timestamps_ns:
        return series
    order = np.argsort(series.timestamps_ns)
    series.timestamps_ns = [series.timestamps_ns[i] for i in order]
    series.x = [series.x[i] for i in order]
    series.y = [series.y[i] for i in order]
    series.z = [series.z[i] for i in order]
    return series


def sort_scalar_series(series: ScalarSeries) -> ScalarSeries:
    if not series.timestamps_ns:
        return series
    order = np.argsort(series.timestamps_ns)
    series.timestamps_ns = [series.timestamps_ns[i] for i in order]
    series.values = [series.values[i] for i in order]
    return series


def sort_string_series(series: StringSeries) -> StringSeries:
    if not series.timestamps_ns:
        return series
    order = np.argsort(series.timestamps_ns)
    series.timestamps_ns = [series.timestamps_ns[i] for i in order]
    series.values = [series.values[i] for i in order]
    return series


def sort_diagnostics_series(series: DiagnosticsSeries) -> DiagnosticsSeries:
    if not series.timestamps_ns:
        return series
    order = np.argsort(series.timestamps_ns)
    series.timestamps_ns = [series.timestamps_ns[i] for i in order]
    series.lateral_error_m = [series.lateral_error_m[i] for i in order]
    series.confidence = [series.confidence[i] for i in order]
    series.magnetic_magnitude = [series.magnetic_magnitude[i] for i in order]
    series.mode = [series.mode[i] for i in order]
    series.current_behavior = [series.current_behavior[i] for i in order]
    series.has_lateral_error = [series.has_lateral_error[i] for i in order]
    series.has_magnetic_magnitude = [series.has_magnetic_magnitude[i] for i in order]
    return series


def all_timestamps(data: BagData) -> np.ndarray:
    buffers: list[np.ndarray] = []
    for timestamps in (
        data.estimated.timestamps_ns,
        data.truth.timestamps_ns,
        data.bt_status.timestamps_ns,
        data.diagnostics.timestamps_ns,
        data.magnetic.timestamps_ns,
    ):
        if timestamps:
            buffers.append(np.asarray(timestamps, dtype=np.int64))
    if not buffers:
        raise SystemExit("No samples found in the selected topics.")
    return np.concatenate(buffers)


def normalize_time_ns(timestamps_ns: Sequence[int], start_ns: int) -> np.ndarray:
    return (np.asarray(timestamps_ns, dtype=np.float64) - float(start_ns)) / 1e9


def interpolate_continuous(source_t: np.ndarray, source_v: np.ndarray, target_t: np.ndarray) -> np.ndarray:
    if source_t.size == 0 or source_v.size == 0:
        return np.full_like(target_t, np.nan, dtype=float)
    if source_t.size == 1:
        return np.full_like(target_t, source_v[0], dtype=float)
    return np.interp(target_t, source_t, source_v)


def forward_fill_strings(source_t: np.ndarray, source_values: Sequence[str], target_t: np.ndarray) -> list[str]:
    if source_t.size == 0:
        return ["UNKNOWN"] * len(target_t)
    indices = np.searchsorted(source_t, target_t, side="right") - 1
    indices = np.clip(indices, 0, len(source_values) - 1)
    return [source_values[idx] for idx in indices]


def diagnostic_state_labels(data: BagData, reference_time_s: np.ndarray) -> list[str]:
    diag_t = normalize_time_ns(data.diagnostics.timestamps_ns, int(np.min(all_timestamps(data))))
    labels: list[str] = []
    for behavior, mode in zip(data.diagnostics.current_behavior, data.diagnostics.mode):
        label = behavior.strip() or mode.strip() or "UNKNOWN"
        labels.append(label)
    if diag_t.size and any(label and label != "UNKNOWN" for label in labels):
        return forward_fill_strings(diag_t, labels, reference_time_s)

    bt_t = normalize_time_ns(data.bt_status.timestamps_ns, int(np.min(all_timestamps(data))))
    bt_labels = [parse_bt_markdown(text) for text in data.bt_status.values]
    return forward_fill_strings(bt_t, bt_labels, reference_time_s)


def compute_lateral_rmse(data: BagData) -> float:
    if not data.diagnostics.timestamps_ns:
        return float("nan")

    values = np.asarray(data.diagnostics.lateral_error_m, dtype=float)
    mask = np.asarray(data.diagnostics.has_lateral_error, dtype=bool) & np.isfinite(values)
    if not np.any(mask):
        return float("nan")
    filtered = values[mask]
    return float(np.sqrt(np.mean(filtered * filtered)))


def state_color(label: str) -> str:
    normalized = label.upper()
    if "ZIGZAG" in normalized or "SEARCH" in normalized:
        return "#1f77b4"
    if "TRACK" in normalized or "PARALLEL" in normalized:
        return "#2ca02c"
    if "DIVE" in normalized:
        return "#ff7f0e"
    if "EMERGENCY" in normalized:
        return "#d62728"
    return "#7f7f7f"


def unique_state_handles(labels: Sequence[str]):
    assert plt is not None
    seen: set[str] = set()
    handles = []
    for label in labels:
        cleaned = label.strip() or "UNKNOWN"
        if cleaned in seen:
            continue
        seen.add(cleaned)
        handles.append(
            plt.Line2D(
                [0],
                [0],
                marker="o",
                linestyle="None",
                markerfacecolor=state_color(cleaned),
                markeredgecolor="none",
                label=cleaned,
            )
        )
    return handles


def plot_trajectory_comparison(
    *,
    data: BagData,
    global_start_ns: int,
    output_path: Path,
    dpi: int,
) -> None:
    estimated = sort_position_series(data.estimated)
    truth = sort_position_series(data.truth)
    est_t = normalize_time_ns(estimated.timestamps_ns, global_start_ns)
    truth_t = normalize_time_ns(truth.timestamps_ns, global_start_ns)

    est_xyz = np.column_stack((as_numpy(estimated.x), as_numpy(estimated.y), as_numpy(estimated.z)))
    truth_xyz = np.column_stack((as_numpy(truth.x), as_numpy(truth.y), as_numpy(truth.z)))
    truth_interp = np.column_stack(
        [
            interpolate_continuous(truth_t, truth_xyz[:, axis], est_t)
            for axis in range(3)
        ]
    )

    labels = diagnostic_state_labels(data, est_t)
    switch_indices = [0]
    for idx in range(1, len(labels)):
        if labels[idx] != labels[idx - 1]:
            switch_indices.append(idx)

    fig = plt.figure(figsize=(7.4, 5.6), dpi=dpi)
    ax = fig.add_subplot(111, projection="3d")
    ax.plot(
        truth_interp[:, 0],
        truth_interp[:, 1],
        truth_interp[:, 2],
        color="#111111",
        linestyle="--",
        linewidth=1.3,
        label="Truth trajectory",
    )
    ax.plot(
        est_xyz[:, 0],
        est_xyz[:, 1],
        est_xyz[:, 2],
        color="#4c78a8",
        linewidth=1.6,
        label="Estimated trajectory",
    )

    for idx in switch_indices:
        ax.scatter(
            est_xyz[idx, 0],
            est_xyz[idx, 1],
            est_xyz[idx, 2],
            color=state_color(labels[idx]),
            s=28,
            depthshade=False,
        )

    ax.set_title("3D Trajectory Comparison")
    ax.set_xlabel("X (m)")
    ax.set_ylabel("Y (m)")
    ax.set_zlabel("Z (m)")

    line_handles = [
        plt.Line2D([0], [0], color="#111111", linestyle="--", linewidth=1.3, label="Truth trajectory"),
        plt.Line2D([0], [0], color="#4c78a8", linestyle="-", linewidth=1.6, label="Estimated trajectory"),
    ]
    ax.legend(handles=[*line_handles, *unique_state_handles(labels)], loc="upper left", frameon=True)
    fig.savefig(output_path, dpi=dpi)
    plt.close(fig)


def plot_uncertainty_analysis(
    *,
    data: BagData,
    global_start_ns: int,
    rmse_m: float,
    output_path: Path,
    dpi: int,
) -> None:
    diagnostics = sort_diagnostics_series(data.diagnostics)
    diag_t = normalize_time_ns(diagnostics.timestamps_ns, global_start_ns)
    lateral = np.asarray(diagnostics.lateral_error_m, dtype=float)
    confidence = np.asarray(diagnostics.confidence, dtype=float)
    lateral_mask = np.asarray(diagnostics.has_lateral_error, dtype=bool)
    lateral = np.where(lateral_mask, lateral, np.nan)

    fig, axes = plt.subplots(2, 1, figsize=(7.2, 5.4), dpi=dpi, sharex=True, constrained_layout=True)
    axes[0].plot(diag_t, lateral, color="#c44e52", linewidth=1.6, label="Lateral error")
    if math.isfinite(rmse_m):
        axes[0].axhline(rmse_m, color="#444444", linestyle=":", linewidth=1.0, label=f"RMSE = {rmse_m:.3f} m")
    axes[0].set_ylabel("Lateral Error (m)")
    axes[0].set_title("Uncertainty-Aware Error Analysis")
    axes[0].legend(loc="upper right", frameon=True)

    axes[1].plot(diag_t, confidence, color="#4c78a8", linewidth=1.6, label="Confidence")
    axes[1].set_xlabel("Time (s)")
    axes[1].set_ylabel("Confidence (-)")
    axes[1].set_ylim(-0.02, 1.02)
    axes[1].legend(loc="upper right", frameon=True)

    fig.savefig(output_path, dpi=dpi)
    plt.close(fig)


def select_magnetic_series(data: BagData, global_start_ns: int) -> tuple[np.ndarray, np.ndarray, list[str]]:
    diagnostics = sort_diagnostics_series(data.diagnostics)
    diag_t = normalize_time_ns(diagnostics.timestamps_ns, global_start_ns)
    diag_mag = np.asarray(diagnostics.magnetic_magnitude, dtype=float)
    diag_mask = np.asarray(diagnostics.has_magnetic_magnitude, dtype=bool) & np.isfinite(diag_mag)
    if np.any(diag_mask):
        labels = [behavior.strip() or mode.strip() or "UNKNOWN" for behavior, mode in zip(diagnostics.current_behavior, diagnostics.mode)]
        return diag_t[diag_mask], diag_mag[diag_mask], [labels[idx] for idx in np.nonzero(diag_mask)[0]]

    magnetic = sort_scalar_series(data.magnetic)
    mag_t = normalize_time_ns(magnetic.timestamps_ns, global_start_ns)
    mag_values = np.asarray(magnetic.values, dtype=float)
    labels = diagnostic_state_labels(data, mag_t)
    return mag_t, mag_values, labels


def plot_magnetic_signature(
    *,
    data: BagData,
    global_start_ns: int,
    output_path: Path,
    dpi: int,
) -> None:
    time_s, magnitude, labels = select_magnetic_series(data, global_start_ns)
    if time_s.size == 0:
        raise SystemExit("No magnetic magnitude samples were found in diagnostics or magnetic topic.")

    zigzag_mask = np.asarray(
        [
            ("ZIGZAG" in label.upper()) or ("SEARCH" in label.upper())
            for label in labels
        ],
        dtype=bool,
    )
    if np.any(zigzag_mask):
        plot_t = time_s[zigzag_mask]
        plot_mag = magnitude[zigzag_mask]
        caption = "Magnetic magnitude during Zig-zag / searching segment"
    else:
        plot_t = time_s
        plot_mag = magnitude
        caption = "Magnetic magnitude over full run"

    fig, ax = plt.subplots(1, 1, figsize=(7.2, 4.0), dpi=dpi, constrained_layout=True)
    ax.plot(plot_t, plot_mag, color="#2f6b8a", linewidth=1.7, label=r"$|B|$")
    peak_index = int(np.nanargmax(plot_mag)) if plot_mag.size else 0
    ax.scatter(plot_t[peak_index], plot_mag[peak_index], color="#d62728", s=26, zorder=3, label="Peak")
    ax.set_title("Magnetic Signature Across Cable Crossing")
    ax.set_xlabel("Time (s)")
    ax.set_ylabel(r"$|B|$ (T)")
    ax.legend(loc="upper right", frameon=True, title=caption)
    fig.savefig(output_path, dpi=dpi)
    plt.close(fig)


def validate_required_topics(data: BagData, allow_missing_truth: bool) -> None:
    if not data.estimated.timestamps_ns:
        raise SystemExit("Missing estimated-state samples. Check /auv/state/filtered or override --topic-estimated-state.")
    if not data.diagnostics.timestamps_ns:
        raise SystemExit("Missing diagnostics samples. Check /auv/diagnostics or override --topic-diagnostics.")
    if not data.truth.timestamps_ns and not allow_missing_truth:
        raise SystemExit(
            "No truth trajectory samples were found. Either provide a compatible truth topic or use --allow-missing-truth."
        )


def print_summary(data: BagData, rmse_m: float, global_start_ns: int) -> None:
    latest_time_ns = int(np.max(all_timestamps(data)))
    duration_s = (latest_time_ns - global_start_ns) / 1e9
    print(f"[INFO] Duration: {duration_s:.3f} s")
    print(f"[INFO] Estimated samples: {len(data.estimated.timestamps_ns)}")
    print(f"[INFO] Diagnostics samples: {len(data.diagnostics.timestamps_ns)}")
    print(f"[INFO] BT status samples: {len(data.bt_status.timestamps_ns)}")
    print(f"[INFO] Magnetic samples: {len(data.magnetic.timestamps_ns)}")
    if data.truth.timestamps_ns:
        print(f"[INFO] Truth samples: {len(data.truth.timestamps_ns)} from {data.truth_topic_used}")
    else:
        print("[WARN] Truth trajectory unavailable; trajectory comparison will be skipped.")
    if math.isfinite(rmse_m):
        print(f"[INFO] Lateral error RMSE: {rmse_m:.4f} m")
    else:
        print("[WARN] Lateral error RMSE could not be computed from available diagnostics samples.")


def main() -> None:
    args = parse_args()
    ensure_runtime_dependencies()
    configure_matplotlib()

    truth_topics = candidate_truth_topics(args.topic_truth_state, args.topic_truth_fallbacks)
    chunks = resolve_input_chunks(args.input)
    output_dir = resolve_output_dir(args.input, args.output_dir)

    data = read_bag_data(
        chunks=chunks,
        estimated_topic=args.topic_estimated_state,
        truth_topics=truth_topics,
        bt_status_topic=args.topic_bt_status,
        diagnostics_topic=args.topic_diagnostics,
        magnetic_topic=args.topic_magnetic,
        verbose=args.verbose,
    )
    validate_required_topics(data, allow_missing_truth=args.allow_missing_truth)

    global_start_ns = int(np.min(all_timestamps(data)))
    rmse_m = compute_lateral_rmse(data)
    print_summary(data, rmse_m, global_start_ns)

    exported_paths: list[Path] = []
    if data.truth.timestamps_ns:
        trajectory_path = output_dir / f"trajectory_comparison.{args.format}"
        plot_trajectory_comparison(
            data=data,
            global_start_ns=global_start_ns,
            output_path=trajectory_path,
            dpi=args.dpi,
        )
        exported_paths.append(trajectory_path)

    uncertainty_path = output_dir / f"uncertainty_analysis.{args.format}"
    plot_uncertainty_analysis(
        data=data,
        global_start_ns=global_start_ns,
        rmse_m=rmse_m,
        output_path=uncertainty_path,
        dpi=args.dpi,
    )
    exported_paths.append(uncertainty_path)

    magnetic_path = output_dir / f"magnetic_signature.{args.format}"
    plot_magnetic_signature(
        data=data,
        global_start_ns=global_start_ns,
        output_path=magnetic_path,
        dpi=args.dpi,
    )
    exported_paths.append(magnetic_path)

    for exported_path in exported_paths:
        print(f"[OK] Exported: {exported_path}")


if __name__ == "__main__":
    main()
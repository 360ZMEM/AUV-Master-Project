#!/usr/bin/env python3
"""
MCAP 离线分析工具 - AUV 实验数据可视化与指标提取。

该工具从 ROS2 MCAP 记录中读取消息并生成静态图表，无需运行 ROS2 环境。
支持多种数据源：位姿轨迹估计、真值、磁场数据、行为树状态等。

安装：
  1. 依赖安装：
     pip install mcap mcap-ros2-support matplotlib numpy
  2. 无需运行 ROS2 图，直接从 MCAP 文件读取 ROS2 消息

使用示例：
  # 分析单个 MCAP 文件并导出 PDF 图表
  python tools/analyze_bag.py /path/to/bag_0.mcap --output-dir ./figures

  # 分析包含多个 .mcap 块的 rosbag2 目录
  python tools/analyze_bag.py /path/to/experiment_bag --format eps

  # 覆盖历史 bag 使用的旧 topic 名称
  python tools/analyze_bag.py /path/to/bag.mcap \
    --topic-diagnostics /auv/diagnostic \
    --topic-magnetic /auv/sensors/mag

功能：
  - 从 MCAP 读取多个 topic 的时序数据
  - 计算轨迹误差统计（位置、速度）
  - 绘制 2D 俯视图、深度-时间曲线、磁场读数
  - 支持自定义 topic 映射（兼容历史数据）
"""

from __future__ import annotations

import argparse
import csv
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Sequence
import sys
import os

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(PROJECT_ROOT))
from common.env_utils import get_output_dir

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
DEFAULT_CABLE_MARKER_TOPIC = "/auv/visual/cable_marker"
DEFAULT_SEABED_CLOUD_TOPIC = "/auv/visual/seabed_cloud"


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
    total_voltage_v: list[float] = field(default_factory=list)
    battery_low: list[bool] = field(default_factory=list)
    anomaly_detected: list[bool] = field(default_factory=list)
    depth_m: list[float] = field(default_factory=list)
    target_depth_m: list[float] = field(default_factory=list)
    depth_error_m: list[float] = field(default_factory=list)
    speed_mps: list[float] = field(default_factory=list)
    target_speed_mps: list[float] = field(default_factory=list)
    seabed_clearance_m: list[float] = field(default_factory=list)
    seabed_proximity_warning: list[bool] = field(default_factory=list)
    seabed_penetration_warning: list[bool] = field(default_factory=list)
    high_priority: list[bool] = field(default_factory=list)
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
        total_voltage_v: float,
        battery_low: bool,
        anomaly_detected: bool,
        depth_m: float,
        target_depth_m: float,
        depth_error_m: float,
        speed_mps: float,
        target_speed_mps: float,
        seabed_clearance_m: float,
        seabed_proximity_warning: bool,
        seabed_penetration_warning: bool,
        high_priority: bool,
        mode: str,
        current_behavior: str,
        has_lateral_error: bool,
        has_magnetic_magnitude: bool,
    ) -> None:
        self.timestamps_ns.append(int(timestamp_ns))
        self.lateral_error_m.append(float(lateral_error_m))
        self.confidence.append(float(confidence))
        self.magnetic_magnitude.append(float(magnetic_magnitude))
        self.total_voltage_v.append(float(total_voltage_v))
        self.battery_low.append(bool(battery_low))
        self.anomaly_detected.append(bool(anomaly_detected))
        self.depth_m.append(float(depth_m))
        self.target_depth_m.append(float(target_depth_m))
        self.depth_error_m.append(float(depth_error_m))
        self.speed_mps.append(float(speed_mps))
        self.target_speed_mps.append(float(target_speed_mps))
        self.seabed_clearance_m.append(float(seabed_clearance_m))
        self.seabed_proximity_warning.append(bool(seabed_proximity_warning))
        self.seabed_penetration_warning.append(bool(seabed_penetration_warning))
        self.high_priority.append(bool(high_priority))
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
    cable_points_xyz: np.ndarray | None = None
    terrain_points_xyz: np.ndarray | None = None
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
        "--stats-only",
        action="store_true",
        help="Export statistics tables without generating figures.",
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
    plt.rcParams["font.serif"] = ["Times New Roman", "Liberation Serif", "Nimbus Roman", "DejaVu Serif"]
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

    return get_output_dir("results/analyze_bag")


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


def extract_marker_points(msg) -> np.ndarray:
    points = getattr(msg, "points", None)
    if not points:
        return np.empty((0, 3), dtype=float)
    xyz = np.asarray([(float(point.x), float(point.y), float(point.z)) for point in points], dtype=float)
    if xyz.ndim != 2 or xyz.shape[1] != 3:
        return np.empty((0, 3), dtype=float)
    return xyz


def extract_pointcloud_xyz(msg) -> np.ndarray:
    fields = {getattr(field, "name", ""): int(getattr(field, "offset", -1)) for field in getattr(msg, "fields", [])}
    if not all(name in fields for name in ("x", "y", "z")):
        return np.empty((0, 3), dtype=float)

    width = int(getattr(msg, "width", 0))
    height = int(getattr(msg, "height", 0))
    point_step = int(getattr(msg, "point_step", 0))
    total_points = width * height
    if total_points <= 0 or point_step <= 0:
        return np.empty((0, 3), dtype=float)

    dtype = np.dtype(">f4" if bool(getattr(msg, "is_bigendian", False)) else "<f4")
    values_per_point = point_step // dtype.itemsize
    if values_per_point <= 0:
        return np.empty((0, 3), dtype=float)

    raw = np.frombuffer(msg.data, dtype=dtype, count=total_points * values_per_point)
    if raw.size < total_points * values_per_point:
        return np.empty((0, 3), dtype=float)

    points = raw.reshape(total_points, values_per_point)
    indices = [fields["x"] // dtype.itemsize, fields["y"] // dtype.itemsize, fields["z"] // dtype.itemsize]
    if any(index >= points.shape[1] for index in indices):
        return np.empty((0, 3), dtype=float)
    return np.asarray(points[:, indices], dtype=float)


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
    cable_topic: str,
    terrain_topic: str,
    verbose: bool,
) -> BagData:
    topics_to_read = {estimated_topic, bt_status_topic, diagnostics_topic, magnetic_topic, cable_topic, terrain_topic, *truth_topics}
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
                    total_voltage_v=float(getattr(msg, "total_voltage_v", float("nan"))),
                    battery_low=bool(getattr(msg, "battery_low", False)),
                    anomaly_detected=bool(getattr(msg, "anomaly_detected", False)),
                    depth_m=float(getattr(msg, "depth_m", float("nan"))),
                    target_depth_m=float(getattr(msg, "target_depth_m", float("nan"))),
                    depth_error_m=float(getattr(msg, "depth_error_m", float("nan"))),
                    speed_mps=float(getattr(msg, "speed_mps", float("nan"))),
                    target_speed_mps=float(getattr(msg, "target_speed_mps", float("nan"))),
                    seabed_clearance_m=float(getattr(msg, "seabed_clearance_m", float("nan"))),
                    seabed_proximity_warning=bool(getattr(msg, "seabed_proximity_warning", False)),
                    seabed_penetration_warning=bool(getattr(msg, "seabed_penetration_warning", False)),
                    high_priority=bool(getattr(msg, "high_priority", False)),
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
                continue

            if topic == cable_topic and data.cable_points_xyz is None:
                cable_points = extract_marker_points(msg)
                if cable_points.size:
                    data.cable_points_xyz = cable_points
                continue

            if topic == terrain_topic and data.terrain_points_xyz is None:
                terrain_points = extract_pointcloud_xyz(msg)
                if terrain_points.size:
                    data.terrain_points_xyz = terrain_points

    if verbose:
        print(f"[INFO] Read {len(chunks)} MCAP chunk(s)")
        print(f"[INFO] Estimated samples: {len(data.estimated.timestamps_ns)}")
        print(f"[INFO] Truth samples: {len(data.truth.timestamps_ns)}")
        print(f"[INFO] Diagnostics samples: {len(data.diagnostics.timestamps_ns)}")
        print(f"[INFO] BT status samples: {len(data.bt_status.timestamps_ns)}")
        print(f"[INFO] Magnetic samples: {len(data.magnetic.timestamps_ns)}")
        print(f"[INFO] Cable reference available: {data.cable_points_xyz is not None}")
        print(f"[INFO] Terrain cloud available: {data.terrain_points_xyz is not None}")

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
    series.total_voltage_v = [series.total_voltage_v[i] for i in order]
    series.battery_low = [series.battery_low[i] for i in order]
    series.anomaly_detected = [series.anomaly_detected[i] for i in order]
    series.depth_m = [series.depth_m[i] for i in order]
    series.target_depth_m = [series.target_depth_m[i] for i in order]
    series.depth_error_m = [series.depth_error_m[i] for i in order]
    series.speed_mps = [series.speed_mps[i] for i in order]
    series.target_speed_mps = [series.target_speed_mps[i] for i in order]
    series.seabed_clearance_m = [series.seabed_clearance_m[i] for i in order]
    series.seabed_proximity_warning = [series.seabed_proximity_warning[i] for i in order]
    series.seabed_penetration_warning = [series.seabed_penetration_warning[i] for i in order]
    series.high_priority = [series.high_priority[i] for i in order]
    series.mode = [series.mode[i] for i in order]
    series.current_behavior = [series.current_behavior[i] for i in order]
    series.has_lateral_error = [series.has_lateral_error[i] for i in order]
    series.has_magnetic_magnitude = [series.has_magnetic_magnitude[i] for i in order]
    return series


def diagnostics_state_trace(data: BagData, global_start_ns: int) -> tuple[np.ndarray, list[str], DiagnosticsSeries]:
    diagnostics = sort_diagnostics_series(data.diagnostics)
    diag_t = normalize_time_ns(diagnostics.timestamps_ns, global_start_ns)
    labels = [behavior.strip() or mode.strip() or "UNKNOWN" for behavior, mode in zip(diagnostics.current_behavior, diagnostics.mode)]
    return diag_t, labels, diagnostics


def decimate_points(points: np.ndarray, max_points: int = 1500) -> np.ndarray:
    if points.size == 0:
        return points
    if points.shape[0] <= max_points:
        return points
    step = max(1, int(math.ceil(points.shape[0] / max_points)))
    return points[::step]


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


def compute_lateral_mean_abs(data: BagData) -> float:
    if not data.diagnostics.timestamps_ns:
        return float("nan")

    values = np.asarray(data.diagnostics.lateral_error_m, dtype=float)
    mask = np.asarray(data.diagnostics.has_lateral_error, dtype=bool) & np.isfinite(values)
    if not np.any(mask):
        return float("nan")
    return float(np.mean(np.abs(values[mask])))


def compute_confidence_mean(data: BagData) -> float:
    if not data.diagnostics.timestamps_ns:
        return float("nan")
    confidence = np.asarray(data.diagnostics.confidence, dtype=float)
    valid = np.isfinite(confidence)
    if not np.any(valid):
        return float("nan")
    return float(np.mean(confidence[valid]))


def compute_magnetic_peak(data: BagData) -> float:
    diagnostics = np.asarray(data.diagnostics.magnetic_magnitude, dtype=float)
    if diagnostics.size:
      mask = np.asarray(data.diagnostics.has_magnetic_magnitude, dtype=bool) & np.isfinite(diagnostics)
      if np.any(mask):
          return float(np.max(diagnostics[mask]))

    magnetic = np.asarray(data.magnetic.values, dtype=float)
    valid = np.isfinite(magnetic)
    if np.any(valid):
        return float(np.max(magnetic[valid]))
    return float("nan")


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


def compute_state_duration_rows(data: BagData, global_start_ns: int) -> list[dict[str, float | str | int]]:
    diag_t, labels, _ = diagnostics_state_trace(data, global_start_ns)
    if diag_t.size == 0:
        return []
    rows: list[dict[str, float | str | int]] = []
    segment_start = 0
    segment_id = 1

    for idx in range(1, len(labels)):
        if labels[idx] == labels[idx - 1]:
            continue
        rows.append(
            {
                "segment_id": segment_id,
                "state": labels[segment_start],
                "start_time_s": float(diag_t[segment_start]),
                "end_time_s": float(diag_t[idx - 1]),
                "duration_s": float(max(0.0, diag_t[idx - 1] - diag_t[segment_start])),
                "sample_count": int(idx - segment_start),
            }
        )
        segment_start = idx
        segment_id += 1

    rows.append(
        {
            "segment_id": segment_id,
            "state": labels[segment_start],
            "start_time_s": float(diag_t[segment_start]),
            "end_time_s": float(diag_t[-1]),
            "duration_s": float(max(0.0, diag_t[-1] - diag_t[segment_start])),
            "sample_count": int(len(labels) - segment_start),
        }
    )
    return rows


def compute_state_transition_rows(data: BagData, global_start_ns: int) -> list[dict[str, float | str | int]]:
    diag_t, labels, _ = diagnostics_state_trace(data, global_start_ns)
    if diag_t.size == 0:
        return []

    rows: list[dict[str, float | str | int]] = []
    for idx in range(1, len(labels)):
        if labels[idx] == labels[idx - 1]:
            continue
        rows.append(
            {
                "transition_id": len(rows) + 1,
                "from_state": labels[idx - 1],
                "to_state": labels[idx],
                "transition_time_s": float(diag_t[idx]),
                "sample_index": int(idx),
            }
        )
    return rows


def compute_boolean_ratio(values: Sequence[bool]) -> float:
    if not values:
        return float("nan")
    return float(np.mean(np.asarray(values, dtype=float)))


def compute_numeric_stats(values: Sequence[float], *, positive_only: bool = False) -> tuple[float, float]:
    array = np.asarray(values, dtype=float)
    if positive_only:
        array = array[array > 0.0]
    valid = np.isfinite(array)
    if not np.any(valid):
        return float("nan"), float("nan")
    filtered = array[valid]
    return float(np.min(filtered)), float(np.max(filtered))


def compute_depth_rmse(data: BagData) -> float:
    diagnostics = np.asarray(data.diagnostics.depth_error_m, dtype=float)
    valid = np.isfinite(diagnostics)
    if not np.any(valid):
        return float("nan")
    filtered = diagnostics[valid]
    return float(np.sqrt(np.mean(filtered * filtered)))


def compute_summary_metric_rows(data: BagData) -> list[tuple[str, float | str | bool | int]]:
    diagnostics = sort_diagnostics_series(data.diagnostics)
    unique_state_labels = {
        label.strip()
        for label in [*diagnostics.current_behavior, *diagnostics.mode]
        if label.strip()
    }
    return [
        ("voltage_mean_v", float(np.nanmean(np.asarray(diagnostics.total_voltage_v, dtype=float))) if diagnostics.total_voltage_v else float("nan")),
        ("voltage_min_v", compute_numeric_stats(diagnostics.total_voltage_v)[0]),
        ("battery_low_ratio", compute_boolean_ratio(diagnostics.battery_low)),
        ("anomaly_ratio", compute_boolean_ratio(diagnostics.anomaly_detected)),
        ("depth_error_rmse_m", compute_depth_rmse(data)),
        ("depth_error_mean_abs_m", float(np.nanmean(np.abs(np.asarray(diagnostics.depth_error_m, dtype=float)))) if diagnostics.depth_error_m else float("nan")),
        ("speed_mean_mps", float(np.nanmean(np.asarray(diagnostics.speed_mps, dtype=float))) if diagnostics.speed_mps else float("nan")),
        ("speed_target_mean_mps", float(np.nanmean(np.asarray(diagnostics.target_speed_mps, dtype=float))) if diagnostics.target_speed_mps else float("nan")),
        ("seabed_clearance_min_m", compute_numeric_stats(diagnostics.seabed_clearance_m, positive_only=True)[0]),
        ("seabed_clearance_mean_m", float(np.nanmean(np.asarray(diagnostics.seabed_clearance_m, dtype=float))) if diagnostics.seabed_clearance_m else float("nan")),
        ("seabed_proximity_ratio", compute_boolean_ratio(diagnostics.seabed_proximity_warning)),
        ("seabed_penetration_ratio", compute_boolean_ratio(diagnostics.seabed_penetration_warning)),
        ("high_priority_ratio", compute_boolean_ratio(diagnostics.high_priority)),
        ("state_transition_count", len(compute_state_transition_rows(data, int(np.min(all_timestamps(data))))) if diagnostics.timestamps_ns else 0),
        ("unique_state_count", len(unique_state_labels)),
    ]


def export_statistics_tables(
    *,
    data: BagData,
    global_start_ns: int,
    rmse_m: float,
    output_dir: Path,
) -> list[Path]:
    summary_path = output_dir / "summary_statistics.csv"
    state_path = output_dir / "state_durations.csv"
    transition_path = output_dir / "state_transitions.csv"
    table_path = output_dir / "summary_statistics_table.tex"

    latest_time_ns = int(np.max(all_timestamps(data)))
    duration_s = (latest_time_ns - global_start_ns) / 1e9
    summary_rows = [
        ("duration_s", duration_s),
        ("estimated_sample_count", len(data.estimated.timestamps_ns)),
        ("truth_sample_count", len(data.truth.timestamps_ns)),
        ("truth_topic_used", data.truth_topic_used or ""),
        ("diagnostics_sample_count", len(data.diagnostics.timestamps_ns)),
        ("bt_status_sample_count", len(data.bt_status.timestamps_ns)),
        ("magnetic_sample_count", len(data.magnetic.timestamps_ns)),
        ("lateral_error_rmse_m", rmse_m),
        ("lateral_error_mean_abs_m", compute_lateral_mean_abs(data)),
        ("confidence_mean", compute_confidence_mean(data)),
        ("magnetic_peak_t", compute_magnetic_peak(data)),
    ]
    summary_rows.extend(compute_summary_metric_rows(data))

    with summary_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["metric", "value"])
        writer.writerows(summary_rows)

    with table_path.open("w", encoding="utf-8", newline="") as handle:
        handle.write("% Auto-generated by tools/analyze_bag.py\n")
        handle.write("\\begin{table}[t]\n")
        handle.write("\\centering\n")
        handle.write("\\caption{Summary statistics of the AUV experiment}\n")
        handle.write("\\label{tab:auv_summary_statistics}\n")
        handle.write("\\begin{tabular}{ll}\n")
        handle.write("\\toprule\n")
        handle.write("Metric & Value " + r"\\")
        handle.write("\n")
        handle.write("\\midrule\n")
        for metric, value in summary_rows:
            handle.write(f"{format_metric_label(metric)} & {format_metric_value(metric, value)} " + r"\\")
            handle.write("\n")
        handle.write("\\bottomrule\n")
        handle.write("\\end{tabular}\n")
        handle.write("\\end{table}\n")

    state_rows = compute_state_duration_rows(data, global_start_ns)
    with state_path.open("w", encoding="utf-8", newline="") as handle:
        fieldnames = ["segment_id", "state", "start_time_s", "end_time_s", "duration_s", "sample_count"]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in state_rows:
            writer.writerow(row)

    transition_rows = compute_state_transition_rows(data, global_start_ns)
    with transition_path.open("w", encoding="utf-8", newline="") as handle:
        fieldnames = ["transition_id", "from_state", "to_state", "transition_time_s", "sample_index"]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in transition_rows:
            writer.writerow(row)

    return [summary_path, state_path, transition_path, table_path]


def format_metric_label(metric: str) -> str:
    labels = {
        "duration_s": "Duration (s)",
        "estimated_sample_count": "Estimated sample count",
        "truth_sample_count": "Truth sample count",
        "truth_topic_used": "Truth topic used",
        "diagnostics_sample_count": "Diagnostics sample count",
        "bt_status_sample_count": "BT status sample count",
        "magnetic_sample_count": "Magnetic sample count",
        "lateral_error_rmse_m": "Lateral error RMSE (m)",
        "lateral_error_mean_abs_m": "Lateral error mean abs. (m)",
        "confidence_mean": "Mean confidence",
        "magnetic_peak_t": "Magnetic peak (T)",
        "voltage_mean_v": "Mean voltage (V)",
        "voltage_min_v": "Minimum voltage (V)",
        "battery_low_ratio": "Battery-low ratio",
        "anomaly_ratio": "Anomaly ratio",
        "depth_error_rmse_m": "Depth error RMSE (m)",
        "depth_error_mean_abs_m": "Depth error mean abs. (m)",
        "speed_mean_mps": "Mean speed (m/s)",
        "speed_target_mean_mps": "Target mean speed (m/s)",
        "seabed_clearance_min_m": "Minimum seabed clearance (m)",
        "seabed_clearance_mean_m": "Mean seabed clearance (m)",
        "seabed_proximity_ratio": "Seabed proximity ratio",
        "seabed_penetration_ratio": "Seabed penetration ratio",
        "high_priority_ratio": "High-priority ratio",
        "state_transition_count": "State transition count",
        "unique_state_count": "Unique state count",
    }
    return labels.get(metric, metric)


def format_metric_value(metric: str, value: object) -> str:
    if isinstance(value, str):
        return value or "N/A"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, np.integer)):
        return str(int(value))
    if isinstance(value, (float, np.floating)):
        numeric = float(value)
        if not math.isfinite(numeric):
            return "N/A"
        if metric.endswith("_sample_count"):
            return str(int(round(numeric)))
        if metric.endswith("_ratio"):
            return f"{numeric:.2%}"
        if metric in {
            "duration_s",
            "lateral_error_rmse_m",
            "lateral_error_mean_abs_m",
            "depth_error_rmse_m",
            "depth_error_mean_abs_m",
            "voltage_mean_v",
            "voltage_min_v",
            "speed_mean_mps",
            "speed_target_mean_mps",
            "seabed_clearance_min_m",
            "seabed_clearance_mean_m",
        }:
            return f"{numeric:.3f}"
        if metric == "confidence_mean":
            return f"{numeric:.3f}"
        if metric == "magnetic_peak_t":
            return f"{numeric:.3e}"
        return f"{numeric:.4g}"
    return str(value)


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

    cable_points = np.asarray(data.cable_points_xyz if data.cable_points_xyz is not None else np.empty((0, 3)), dtype=float)
    terrain_points = np.asarray(data.terrain_points_xyz if data.terrain_points_xyz is not None else np.empty((0, 3)), dtype=float)
    terrain_points = decimate_points(terrain_points, max_points=1800)

    fig = plt.figure(figsize=(7.4, 5.6), dpi=dpi)
    ax = fig.add_subplot(111, projection="3d")

    if terrain_points.size:
        try:
            ax.plot_trisurf(
                terrain_points[:, 0],
                terrain_points[:, 1],
                terrain_points[:, 2],
                cmap="Greens",
                alpha=0.18,
                linewidth=0.1,
                antialiased=True,
                shade=False,
            )
        except Exception:
            ax.scatter(
                terrain_points[:, 0],
                terrain_points[:, 1],
                terrain_points[:, 2],
                s=1.0,
                color="#6b8f6a",
                alpha=0.12,
                depthshade=False,
            )

    if cable_points.size:
        ax.plot(
            cable_points[:, 0],
            cable_points[:, 1],
            cable_points[:, 2],
            color="#8c6d31",
            linewidth=3.0,
            alpha=0.95,
            label="Cable reference",
            zorder=4,
        )

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

    ax.view_init(elev=22, azim=-58)
    ax.set_title("3D Trajectory, Cable, and Terrain Comparison")
    ax.set_xlabel("X (m)")
    ax.set_ylabel("Y (m)")
    ax.set_zlabel("Z (m)")

    line_handles = [
        plt.Line2D([0], [0], marker="s", linestyle="None", markerfacecolor="#6b8f6a", markeredgecolor="none", alpha=0.25, label="Reference terrain"),
        plt.Line2D([0], [0], color="#8c6d31", linewidth=3.0, label="Cable reference"),
        plt.Line2D([0], [0], color="#111111", linestyle="--", linewidth=1.3, label="Truth trajectory"),
        plt.Line2D([0], [0], color="#4c78a8", linestyle="-", linewidth=1.6, label="Estimated trajectory"),
    ]
    ax.legend(handles=[*line_handles, *unique_state_handles(labels)], loc="upper left", frameon=True)
    fig.savefig(output_path, dpi=dpi)
    plt.close(fig)


def plot_state_timeline(
    *,
    data: BagData,
    global_start_ns: int,
    output_path: Path,
    dpi: int,
) -> bool:
    diagnostics = sort_diagnostics_series(data.diagnostics)
    diag_t = normalize_time_ns(diagnostics.timestamps_ns, global_start_ns)
    if diag_t.size == 0:
        return False

    behavior_labels = [behavior.strip() or mode.strip() or "UNKNOWN" for behavior, mode in zip(diagnostics.current_behavior, diagnostics.mode)]
    mode_labels = [mode.strip() or behavior.strip() or "UNKNOWN" for behavior, mode in zip(diagnostics.current_behavior, diagnostics.mode)]
    transition_rows = compute_state_transition_rows(data, global_start_ns)

    def render_axis(axis, time_s: np.ndarray, labels: list[str], title: str) -> None:
        ordered_states: list[str] = []
        for label in labels:
            if label not in ordered_states:
                ordered_states.append(label)
        if not ordered_states:
            ordered_states = ["UNKNOWN"]
        state_index = {label: idx for idx, label in enumerate(ordered_states)}
        y_values = np.asarray([state_index[label] for label in labels], dtype=float)

        for label in ordered_states:
            mask = np.asarray([item == label for item in labels], dtype=bool)
            if np.any(mask):
                axis.scatter(time_s[mask], y_values[mask], s=9, alpha=0.82, color=state_color(label), label=label)

        for row in transition_rows:
            axis.axvline(float(row["transition_time_s"]), color="#999999", linewidth=0.7, alpha=0.22)

        axis.set_title(title)
        axis.set_ylabel("State")
        axis.set_yticks(range(len(ordered_states)))
        axis.set_yticklabels(ordered_states)
        axis.set_ylim(-0.5, len(ordered_states) - 0.5)
        axis.legend(handles=unique_state_handles(ordered_states), loc="upper right", frameon=True, ncol=2)

    fig, axes = plt.subplots(2, 1, figsize=(8.0, 5.6), dpi=dpi, sharex=True, constrained_layout=True)
    render_axis(axes[0], diag_t, behavior_labels, "Behavior-State Transition Timeline")
    render_axis(axes[1], diag_t, mode_labels, "Mode Transition Timeline")
    axes[1].set_xlabel("Time (s)")
    fig.savefig(output_path, dpi=dpi)
    plt.close(fig)
    return True


def plot_system_monitoring(
    *,
    data: BagData,
    global_start_ns: int,
    output_path: Path,
    dpi: int,
) -> bool:
    diagnostics = sort_diagnostics_series(data.diagnostics)
    diag_t = normalize_time_ns(diagnostics.timestamps_ns, global_start_ns)
    if diag_t.size == 0:
        return False

    voltage = np.asarray(diagnostics.total_voltage_v, dtype=float)
    confidence = np.asarray(diagnostics.confidence, dtype=float)
    depth = np.asarray(diagnostics.depth_m, dtype=float)
    target_depth = np.asarray(diagnostics.target_depth_m, dtype=float)
    depth_error = np.asarray(diagnostics.depth_error_m, dtype=float)
    speed = np.asarray(diagnostics.speed_mps, dtype=float)
    target_speed = np.asarray(diagnostics.target_speed_mps, dtype=float)
    lateral_error = np.asarray(diagnostics.lateral_error_m, dtype=float)
    lateral_mask = np.asarray(diagnostics.has_lateral_error, dtype=bool)
    lateral_error = np.where(lateral_mask, lateral_error, np.nan)
    seabed_clearance = np.asarray(diagnostics.seabed_clearance_m, dtype=float)

    battery_low = np.asarray(diagnostics.battery_low, dtype=bool)
    anomaly_detected = np.asarray(diagnostics.anomaly_detected, dtype=bool)
    proximity_warning = np.asarray(diagnostics.seabed_proximity_warning, dtype=bool)
    penetration_warning = np.asarray(diagnostics.seabed_penetration_warning, dtype=bool)
    high_priority = np.asarray(diagnostics.high_priority, dtype=bool)

    fig, axes = plt.subplots(5, 1, figsize=(8.0, 10.4), dpi=dpi, sharex=True, constrained_layout=True)

    axes[0].plot(diag_t, voltage, color="#8c564b", linewidth=1.6, label="Total voltage")
    if np.any(battery_low):
        axes[0].scatter(diag_t[battery_low], voltage[battery_low], color="#d62728", s=14, label="battery_low")
    if np.any(anomaly_detected):
        axes[0].scatter(diag_t[anomaly_detected], voltage[anomaly_detected], color="#ff7f0e", s=14, label="anomaly")
    axes[0].set_ylabel("Voltage (V)")
    axes[0].legend(loc="upper right", frameon=True)

    axes[1].plot(diag_t, depth, color="#1f77b4", linewidth=1.5, label="Depth")
    axes[1].plot(diag_t, target_depth, color="#1f77b4", linewidth=1.0, linestyle="--", label="Target depth")
    axes[1].plot(diag_t, depth_error, color="#9467bd", linewidth=1.2, label="Depth error")
    axes[1].set_ylabel("Depth (m)")
    axes[1].legend(loc="upper right", frameon=True, ncol=2)

    axes[2].plot(diag_t, speed, color="#2ca02c", linewidth=1.5, label="Speed")
    axes[2].plot(diag_t, target_speed, color="#2ca02c", linewidth=1.0, linestyle="--", label="Target speed")
    axes[2].plot(diag_t, confidence, color="#4c78a8", linewidth=1.2, label="Confidence")
    axes[2].set_ylabel("Speed / Conf.")
    axes[2].legend(loc="upper right", frameon=True, ncol=2)

    axes[3].plot(diag_t, lateral_error, color="#c44e52", linewidth=1.4, label="Lateral error")
    axes[3].set_ylabel("Lateral (m)")
    axes[3].legend(loc="upper right", frameon=True)

    axes[4].plot(diag_t, seabed_clearance, color="#006d2c", linewidth=1.4, label="Seabed clearance")
    if np.any(proximity_warning):
        axes[4].scatter(diag_t[proximity_warning], seabed_clearance[proximity_warning], color="#ff7f0e", s=14, label="proximity")
    if np.any(penetration_warning):
        axes[4].scatter(diag_t[penetration_warning], seabed_clearance[penetration_warning], color="#d62728", s=14, label="penetration")
    if np.any(high_priority):
        axes[4].scatter(diag_t[high_priority], seabed_clearance[high_priority], color="#111111", s=10, label="high_priority")
    axes[4].set_ylabel("Clearance (m)")
    axes[4].set_xlabel("Time (s)")
    axes[4].legend(loc="upper right", frameon=True, ncol=2)

    fig.savefig(output_path, dpi=dpi)
    plt.close(fig)
    return True


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
) -> bool:
    time_s, magnitude, labels = select_magnetic_series(data, global_start_ns)
    if time_s.size == 0:
        return False

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
    return True


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
        cable_topic=DEFAULT_CABLE_MARKER_TOPIC,
        terrain_topic=DEFAULT_SEABED_CLOUD_TOPIC,
        verbose=args.verbose,
    )
    validate_required_topics(data, allow_missing_truth=args.allow_missing_truth)

    global_start_ns = int(np.min(all_timestamps(data)))
    rmse_m = compute_lateral_rmse(data)
    print_summary(data, rmse_m, global_start_ns)

    exported_paths: list[Path] = []
    exported_paths.extend(
        export_statistics_tables(
            data=data,
            global_start_ns=global_start_ns,
            rmse_m=rmse_m,
            output_dir=output_dir,
        )
    )

    if args.stats_only:
        for exported_path in exported_paths:
            print(f"[OK] Exported: {exported_path}")
        return

    if data.truth.timestamps_ns:
        trajectory_path = output_dir / f"trajectory_comparison.{args.format}"
        plot_trajectory_comparison(
            data=data,
            global_start_ns=global_start_ns,
            output_path=trajectory_path,
            dpi=args.dpi,
        )
        exported_paths.append(trajectory_path)

    state_timeline_path = output_dir / f"state_timeline.{args.format}"
    if plot_state_timeline(
        data=data,
        global_start_ns=global_start_ns,
        output_path=state_timeline_path,
        dpi=args.dpi,
    ):
        exported_paths.append(state_timeline_path)

    system_monitoring_path = output_dir / f"system_monitoring.{args.format}"
    if plot_system_monitoring(
        data=data,
        global_start_ns=global_start_ns,
        output_path=system_monitoring_path,
        dpi=args.dpi,
    ):
        exported_paths.append(system_monitoring_path)

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
    magnetic_exported = plot_magnetic_signature(
        data=data,
        global_start_ns=global_start_ns,
        output_path=magnetic_path,
        dpi=args.dpi,
    )
    if magnetic_exported:
        exported_paths.append(magnetic_path)
    else:
        print("[WARN] No magnetic magnitude samples were found; magnetic signature figure was skipped.")

    for exported_path in exported_paths:
        print(f"[OK] Exported: {exported_path}")


if __name__ == "__main__":
    main()
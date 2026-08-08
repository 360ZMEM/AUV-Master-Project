#!/usr/bin/env python3
"""Collect and plot stamped ROS link latency samples.

The collect subcommand subscribes to stamped ROS topics and writes a CSV with
one row per message. The plot subcommand accepts one or more CSV files, writes
per-run statistics, and generates a time-series plot plus a distribution plot.
"""

from __future__ import annotations

import argparse
import csv
import importlib
import math
import statistics
import time
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


DEFAULT_TOPICS = (
    "/auv/sensors/imu=sensor_msgs.msg:Imu",
    "/auv/sensors/dvl=geometry_msgs.msg:TwistStamped",
    "/auv/sensors/magnetic=sensor_msgs.msg:MagneticField",
    "/auv/state/filtered=nav_msgs.msg:Odometry",
)

CSV_FIELDS = (
    "run_id",
    "topic",
    "sample_index",
    "elapsed_s",
    "latency_ms",
    "stamp_s",
    "receive_s",
)


@dataclass(frozen=True)
class LatencyRow:
    run_id: str
    topic: str
    sample_index: int
    elapsed_s: float
    latency_ms: float
    stamp_s: float
    receive_s: float


def _parse_topic_type(spec: str) -> tuple[str, type]:
    """Parse TOPIC=module:Class into a ROS message class."""
    if "=" not in spec or ":" not in spec:
        raise ValueError(f"invalid topic spec: {spec}")
    topic, type_path = spec.split("=", 1)
    module_name, class_name = type_path.split(":", 1)
    module = importlib.import_module(module_name)
    return topic, getattr(module, class_name)


def _stamp_to_seconds(stamp) -> float:
    """Convert a ROS builtin_interfaces/Time value to seconds."""
    return float(stamp.sec) + float(stamp.nanosec) * 1.0e-9


def collect_latency(args: argparse.Namespace) -> int:
    """Collect stamped topic latency samples from a running ROS graph."""
    import rclpy
    from rclpy.node import Node

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    topic_specs = args.topic or list(DEFAULT_TOPICS)
    parsed_topics = [_parse_topic_type(item) for item in topic_specs]

    rclpy.init(args=None)
    node = Node("link_latency_collector")
    start_monotonic = time.monotonic()
    sample_counts: dict[str, int] = defaultdict(int)
    total_count = 0

    with output_path.open("w", newline="") as fp:
        writer = csv.DictWriter(fp, fieldnames=CSV_FIELDS)
        writer.writeheader()

        def make_callback(topic: str):
            def _callback(msg) -> None:
                nonlocal total_count
                header = getattr(msg, "header", None)
                stamp = getattr(header, "stamp", None)
                if stamp is None:
                    return
                receive_s = float(node.get_clock().now().nanoseconds) * 1.0e-9
                stamp_s = _stamp_to_seconds(stamp)
                latency_ms = (receive_s - stamp_s) * 1000.0
                sample_counts[topic] += 1
                total_count += 1
                writer.writerow(
                    {
                        "run_id": args.run_id,
                        "topic": topic,
                        "sample_index": sample_counts[topic],
                        "elapsed_s": time.monotonic() - start_monotonic,
                        "latency_ms": latency_ms,
                        "stamp_s": stamp_s,
                        "receive_s": receive_s,
                    }
                )
                fp.flush()

            return _callback

        subscriptions = [
            node.create_subscription(msg_type, topic, make_callback(topic), int(args.qos_depth))
            for topic, msg_type in parsed_topics
        ]
        try:
            while rclpy.ok() and (time.monotonic() - start_monotonic) < float(args.duration):
                rclpy.spin_once(node, timeout_sec=0.1)
        finally:
            for subscription in subscriptions:
                node.destroy_subscription(subscription)
            node.destroy_node()
            rclpy.shutdown()

    print(f"[link-latency] collected {total_count} samples -> {output_path}")
    return 0


def _load_rows(paths: Iterable[Path]) -> list[LatencyRow]:
    """Load latency rows from one or more CSV files."""
    rows: list[LatencyRow] = []
    for path in paths:
        with path.open(newline="") as fp:
            reader = csv.DictReader(fp)
            for raw in reader:
                try:
                    latency_ms = float(raw["latency_ms"])
                    if not math.isfinite(latency_ms):
                        continue
                    rows.append(
                        LatencyRow(
                            run_id=raw.get("run_id") or path.stem,
                            topic=raw.get("topic") or "unknown",
                            sample_index=int(float(raw.get("sample_index") or len(rows) + 1)),
                            elapsed_s=float(raw.get("elapsed_s") or 0.0),
                            latency_ms=latency_ms,
                            stamp_s=float(raw.get("stamp_s") or 0.0),
                            receive_s=float(raw.get("receive_s") or 0.0),
                        )
                    )
                except (KeyError, TypeError, ValueError):
                    continue
    return rows


def _percentile(values: list[float], fraction: float) -> float:
    """Return a nearest-rank percentile for a non-empty sorted value list."""
    if not values:
        return float("nan")
    index = min(len(values) - 1, max(0, int(round((len(values) - 1) * fraction))))
    return values[index]


def _write_summary(rows: list[LatencyRow], output_dir: Path) -> Path:
    """Write per-run/topic and aggregate latency statistics."""
    grouped: dict[tuple[str, str], list[float]] = defaultdict(list)
    for row in rows:
        grouped[(row.run_id, row.topic)].append(row.latency_ms)

    summary_path = output_dir / "link_latency_summary.csv"
    with summary_path.open("w", newline="") as fp:
        fields = (
            "run_id",
            "topic",
            "count",
            "mean_ms",
            "std_ms",
            "min_ms",
            "p50_ms",
            "p95_ms",
            "max_ms",
        )
        writer = csv.DictWriter(fp, fieldnames=fields)
        writer.writeheader()
        per_topic_means: dict[str, list[float]] = defaultdict(list)
        for (run_id, topic), values in sorted(grouped.items()):
            values = sorted(values)
            mean_ms = statistics.fmean(values)
            std_ms = statistics.stdev(values) if len(values) > 1 else 0.0
            per_topic_means[topic].append(mean_ms)
            writer.writerow(
                {
                    "run_id": run_id,
                    "topic": topic,
                    "count": len(values),
                    "mean_ms": f"{mean_ms:.6f}",
                    "std_ms": f"{std_ms:.6f}",
                    "min_ms": f"{values[0]:.6f}",
                    "p50_ms": f"{_percentile(values, 0.50):.6f}",
                    "p95_ms": f"{_percentile(values, 0.95):.6f}",
                    "max_ms": f"{values[-1]:.6f}",
                }
            )
        for topic, means in sorted(per_topic_means.items()):
            writer.writerow(
                {
                    "run_id": "MULTI_RUN_MEAN",
                    "topic": topic,
                    "count": len(means),
                    "mean_ms": f"{statistics.fmean(means):.6f}",
                    "std_ms": f"{statistics.stdev(means) if len(means) > 1 else 0.0:.6f}",
                    "min_ms": f"{min(means):.6f}",
                    "p50_ms": f"{_percentile(sorted(means), 0.50):.6f}",
                    "p95_ms": f"{_percentile(sorted(means), 0.95):.6f}",
                    "max_ms": f"{max(means):.6f}",
                }
            )
    return summary_path


def plot_latency(args: argparse.Namespace) -> int:
    """Generate line and distribution plots from latency CSV files."""
    rows = _load_rows([Path(item) for item in args.csv])
    if not rows:
        raise SystemExit("[link-latency] no valid rows found")

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = _write_summary(rows, output_dir)

    by_series: dict[tuple[str, str], list[LatencyRow]] = defaultdict(list)
    for row in rows:
        by_series[(row.run_id, row.topic)].append(row)

    fig, ax = plt.subplots(figsize=(11, 5), dpi=180)
    for (run_id, topic), series in sorted(by_series.items()):
        series = sorted(series, key=lambda item: (item.elapsed_s, item.sample_index))
        label = f"{run_id}:{topic}"
        ax.plot(
            [item.elapsed_s for item in series],
            [item.latency_ms for item in series],
            linewidth=1.0,
            alpha=0.85,
            label=label,
        )
    ax.set_title("Stamped topic link latency over time")
    ax.set_xlabel("elapsed [s]")
    ax.set_ylabel("latency [ms]")
    ax.grid(True, alpha=0.25)
    if len(by_series) <= 12:
        ax.legend(fontsize=7)
    fig.tight_layout()
    line_path = output_dir / "link_latency_timeseries.png"
    fig.savefig(line_path)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(9, 5), dpi=180)
    for (run_id, topic), series in sorted(by_series.items()):
        values = [item.latency_ms for item in series]
        ax.hist(values, bins=int(args.bins), alpha=0.35, density=True, label=f"{run_id}:{topic}")
    ax.set_title("Stamped topic link latency distribution")
    ax.set_xlabel("latency [ms]")
    ax.set_ylabel("density")
    ax.grid(True, alpha=0.25)
    if len(by_series) <= 12:
        ax.legend(fontsize=7)
    fig.tight_layout()
    dist_path = output_dir / "link_latency_distribution.png"
    fig.savefig(dist_path)
    plt.close(fig)

    print(f"[link-latency] summary: {summary_path}")
    print(f"[link-latency] line plot: {line_path}")
    print(f"[link-latency] distribution plot: {dist_path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser."""
    parser = argparse.ArgumentParser(description="Collect and plot ROS link latency CSV files.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    collect = subparsers.add_parser("collect", help="collect stamped ROS topic latency")
    collect.add_argument("--duration", type=float, default=30.0)
    collect.add_argument("--output", required=True)
    collect.add_argument("--run-id", default=time.strftime("%Y%m%d_%H%M%S"))
    collect.add_argument("--qos-depth", type=int, default=10)
    collect.add_argument(
        "--topic",
        action="append",
        help="topic spec TOPIC=module:Class; may be repeated",
    )
    collect.set_defaults(func=collect_latency)

    plot = subparsers.add_parser("plot", help="plot one or more latency CSV files")
    plot.add_argument("csv", nargs="+")
    plot.add_argument("--output-dir", required=True)
    plot.add_argument("--bins", type=int, default=40)
    plot.set_defaults(func=plot_latency)
    return parser


def main() -> int:
    """Run the selected subcommand."""
    parser = build_parser()
    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Lightweight per-topic throttle for /auv/visual/* topics.

Subscribes to the original topics published by the viz bridge and
re-publishes a downsampled copy on ``<topic>_throttled``.  Designed for
the ``--lean-bag-visual`` mode of ``start_experiment.sh``: rosbag is
told to exclude the originals and pick up the throttled copies via
``-a`` discovery, so the bag carries 1 Hz seabed_mesh / seabed_cloud
while the original publishers (and Foxglove subscribers) remain
untouched.

The mapping is fixed because the bridge only emits these two heavy
visual topics; ``history_trail`` is intentionally left out so the bag
keeps its full-rate trail.

Usage::

    python3 scripts/visual_throttle.py --rate-hz 1.0
"""

from __future__ import annotations

import argparse
import signal
import sys
from typing import Tuple

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import PointCloud2
from visualization_msgs.msg import Marker

# (input_topic, output_suffix, msg_class)
DEFAULT_TOPICS: Tuple[Tuple[str, type], ...] = (
    ("/auv/visual/seabed_mesh", Marker),
    ("/auv/visual/seabed_cloud", PointCloud2),
)


class ThrottleRelay(Node):
    def __init__(self, rate_hz: float) -> None:
        super().__init__("auv_visual_throttle")
        self._period_ns = int(1e9 / rate_hz) if rate_hz > 0 else 0
        self._last_pub_ns: dict[str, int] = {}
        self._pubs: dict[str, object] = {}

        for topic, msg_cls in DEFAULT_TOPICS:
            out_topic = f"{topic}_throttled"
            self._pubs[topic] = self.create_publisher(msg_cls, out_topic, 10)
            self.create_subscription(
                msg_cls,
                topic,
                lambda msg, t=topic: self._on_msg(t, msg),
                10,
            )
            self.get_logger().info(
                f"throttling {topic} -> {out_topic} @ {rate_hz} Hz"
            )

    def _on_msg(self, topic: str, msg) -> None:
        now_ns = self.get_clock().now().nanoseconds
        last = self._last_pub_ns.get(topic, 0)
        if self._period_ns > 0 and (now_ns - last) < self._period_ns:
            return
        self._last_pub_ns[topic] = now_ns
        self._pubs[topic].publish(msg)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--rate-hz",
        type=float,
        default=1.0,
        help="Throttle rate in Hz (default: 1.0)",
    )
    args = parser.parse_args(argv)

    rclpy.init()
    node = ThrottleRelay(rate_hz=args.rate_hz)

    def _sigterm(_sig, _frame):
        rclpy.shutdown()
        sys.exit(0)

    signal.signal(signal.SIGINT, _sigterm)
    signal.signal(signal.SIGTERM, _sigterm)

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        if rclpy.ok():
            rclpy.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())

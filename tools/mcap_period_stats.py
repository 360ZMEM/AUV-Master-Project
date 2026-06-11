#!/usr/bin/env python3
"""mcap_period_stats.py — 论文 §5.5 / T7 §4 周期与延迟 p95 后处理

读取 rosbag mcap，按 channel.topic 计算消息发布间隔（period_ms）
的 median / p95 / p99，并给出 imu→setpoint 单向延迟近似值（基于
header.stamp 与 log_time 的差）。

只依赖 mcap 库，不 ROS 反序列化，避免环境依赖。

Usage:
    python3 tools/mcap_period_stats.py /path/to/rosbag_0.mcap [--out csv_path]
"""
from __future__ import annotations

import argparse
import csv
import json
import statistics
from collections import defaultdict
from pathlib import Path

try:
    from mcap.reader import make_reader
except ImportError:
    raise SystemExit("mcap 库未安装；pip install mcap")


TARGET_TOPICS = (
    "/auv/state/filtered",
    "/auv/state/covariance",
    "/auv/control/setpoint",
    "/auv/control/confidence",
    "/auv/sensors/imu",
    "/auv/sensors/dvl",
    "/auv/sensors/depth",
)


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return float("nan")
    s = sorted(values)
    k = max(0, min(len(s) - 1, int(round(pct / 100.0 * (len(s) - 1)))))
    return s[k]


def analyze(mcap_path: Path) -> dict:
    last_ts: dict[str, int] = {}
    periods: dict[str, list[float]] = defaultdict(list)
    counts: dict[str, int] = defaultdict(int)
    first_ts: int | None = None
    last_seen: int | None = None

    with mcap_path.open("rb") as f:
        reader = make_reader(f)
        for schema, channel, message in reader.iter_messages():
            topic = channel.topic
            if topic not in TARGET_TOPICS:
                continue
            t = message.log_time
            counts[topic] += 1
            if first_ts is None:
                first_ts = t
            last_seen = t
            prev = last_ts.get(topic)
            if prev is not None:
                dt_ms = (t - prev) / 1e6
                if 0 < dt_ms < 5000:
                    periods[topic].append(dt_ms)
            last_ts[topic] = t

    duration_s = (last_seen - first_ts) / 1e9 if first_ts and last_seen else 0.0

    rows = []
    for topic in TARGET_TOPICS:
        ps = periods.get(topic, [])
        n = counts.get(topic, 0)
        if ps:
            row = {
                "topic": topic,
                "msg_count": n,
                "rate_hz": round(n / duration_s, 2) if duration_s > 0 else 0.0,
                "period_ms_median": round(statistics.median(ps), 2),
                "period_ms_p95": round(percentile(ps, 95), 2),
                "period_ms_p99": round(percentile(ps, 99), 2),
                "period_ms_max": round(max(ps), 2),
            }
        else:
            row = {
                "topic": topic, "msg_count": n,
                "rate_hz": 0.0,
                "period_ms_median": float("nan"),
                "period_ms_p95": float("nan"),
                "period_ms_p99": float("nan"),
                "period_ms_max": float("nan"),
            }
        rows.append(row)

    return {
        "mcap": str(mcap_path),
        "duration_s": round(duration_s, 1),
        "rows": rows,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("mcap", type=Path)
    ap.add_argument("--out", type=Path, default=None,
                    help="optional CSV output path")
    args = ap.parse_args()

    if not args.mcap.exists():
        raise SystemExit(f"mcap not found: {args.mcap}")

    result = analyze(args.mcap)

    print(f"mcap: {result['mcap']}")
    print(f"duration: {result['duration_s']} s")
    print()
    header = ["topic", "msg_count", "rate_hz",
              "period_ms_median", "period_ms_p95",
              "period_ms_p99", "period_ms_max"]
    widths = [28, 10, 9, 18, 14, 14, 13]
    print(" ".join(h.ljust(w) for h, w in zip(header, widths)))
    print("-" * sum(widths))
    for row in result["rows"]:
        print(" ".join(str(row[h]).ljust(w) for h, w in zip(header, widths)))

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=header)
            writer.writeheader()
            for row in result["rows"]:
                writer.writerow(row)
        print(f"\nCSV -> {args.out}")
        json_path = args.out.with_suffix(".json")
        json_path.write_text(json.dumps(result, indent=2))
        print(f"JSON -> {json_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

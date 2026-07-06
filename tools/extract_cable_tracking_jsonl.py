#!/usr/bin/env python3
"""Extract /auv/cable/tracking JSON payloads from an MCAP rosbag."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bag", type=Path, required=True, help="MCAP file or rosbag directory containing MCAP chunks.")
    parser.add_argument("--output-jsonl", type=Path, required=True)
    parser.add_argument("--summary-json", type=Path, default=None)
    parser.add_argument("--topic", default="/auv/cable/tracking")
    return parser.parse_args()


def _resolve(path: Path) -> Path:
    return path if path.is_absolute() else PROJECT_ROOT / path


def _mcap_chunks(path: Path) -> list[Path]:
    path = _resolve(path)
    if path.is_file():
        return [path]
    chunks = sorted(path.rglob("*.mcap"))
    if not chunks:
        raise SystemExit(f"no .mcap files found under: {path}")
    return chunks


def _read_messages(chunks: list[Path], topic: str) -> list[dict[str, Any]]:
    try:
        from mcap_ros2.reader import read_ros2_messages
    except ImportError as exc:
        raise SystemExit(
            "mcap and mcap-ros2-support are required. Install them with: "
            "pip install mcap mcap-ros2-support"
        ) from exc

    rows: list[dict[str, Any]] = []
    for chunk in chunks:
        for decoded in read_ros2_messages(str(chunk), topics=[topic]):
            msg = decoded.ros_msg
            text = str(getattr(msg, "data", "")).strip()
            if not text:
                continue
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                continue
            payload["_bag_topic"] = topic
            payload["_bag_log_time_ns"] = int(getattr(decoded, "log_time_ns", 0))
            payload["_bag_publish_time_ns"] = int(getattr(decoded, "publish_time_ns", 0))
            rows.append(payload)
    return rows


def _summary(rows: list[dict[str, Any]], chunks: list[Path], topic: str) -> dict[str, Any]:
    confidences = [float(row["confidence"]) for row in rows if row.get("confidence") is not None]
    offsets = [abs(float(row["cross_track_m"])) for row in rows if row.get("cross_track_m") is not None]
    burial_sigma = [float(row["burial_sigma_m"]) for row in rows if row.get("burial_sigma_m") is not None]
    return {
        "source_chunks": [str(chunk) for chunk in chunks],
        "topic": topic,
        "message_count": len(rows),
        "time_s_start": rows[0].get("time_s") if rows else None,
        "time_s_end": rows[-1].get("time_s") if rows else None,
        "confidence_mean": sum(confidences) / len(confidences) if confidences else None,
        "confidence_min": min(confidences) if confidences else None,
        "max_abs_cross_track_m": max(offsets) if offsets else None,
        "max_burial_sigma_m": max(burial_sigma) if burial_sigma else None,
    }


def main() -> None:
    args = parse_args()
    chunks = _mcap_chunks(args.bag)
    rows = _read_messages(chunks, str(args.topic))
    output_jsonl = _resolve(args.output_jsonl)
    output_jsonl.parent.mkdir(parents=True, exist_ok=True)
    output_jsonl.write_text(
        "".join(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n" for row in rows),
        encoding="utf-8",
    )
    summary = _summary(rows, chunks, str(args.topic))
    summary_json = _resolve(args.summary_json) if args.summary_json else output_jsonl.with_suffix(".summary.json")
    summary_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[OK] extracted {len(rows)} messages to {output_jsonl}")
    print(f"[OK] wrote summary to {summary_json}")


if __name__ == "__main__":
    main()

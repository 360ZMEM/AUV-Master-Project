#!/usr/bin/env python3
"""Verify magnetic lever-arm/extrinsics bag proof topics in an MCAP rosbag."""

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
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--magnetic-topic", default="/auv/sensors/magnetic")
    parser.add_argument("--status-topic", default="/auv/sensors/magnetic_extrinsics_status")
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


def _read_topics(chunks: list[Path], topics: list[str]) -> dict[str, list[Any]]:
    try:
        from mcap_ros2.reader import read_ros2_messages
    except ImportError as exc:
        raise SystemExit(
            "mcap and mcap-ros2-support are required. Install them with: "
            "pip install mcap mcap-ros2-support"
        ) from exc

    rows: dict[str, list[Any]] = {topic: [] for topic in topics}
    topic_set = set(topics)
    for chunk in chunks:
        for decoded in read_ros2_messages(str(chunk), topics=topics):
            topic = _decoded_topic(decoded)
            if topic not in topic_set:
                continue
            rows[topic].append(decoded.ros_msg)
    return rows


def _decoded_topic(decoded: Any) -> str:
    channel = getattr(decoded, "channel", None)
    topic = getattr(channel, "topic", None)
    if topic is not None:
        return str(topic)
    topic = getattr(decoded, "topic", None)
    if topic is not None:
        return str(topic)
    return ""


def _status_payloads(messages: list[Any]) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    for msg in messages:
        text = str(getattr(msg, "data", "")).strip()
        if not text:
            continue
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            payloads.append(payload)
    return payloads


def _summarize(
    *,
    chunks: list[Path],
    magnetic_topic: str,
    status_topic: str,
    magnetic_messages: list[Any],
    status_payloads: list[dict[str, Any]],
) -> dict[str, Any]:
    status_text = json.dumps(status_payloads, ensure_ascii=False, sort_keys=True)
    status_count = len(status_payloads)
    magnetic_count = len(magnetic_messages)
    uses_estimated = any(bool(row.get("uses_estimated_extrinsics")) for row in status_payloads)
    source_present = any(bool(row.get("estimated_extrinsics_source")) for row in status_payloads)
    truth_exported = any(bool(row.get("truth_extrinsics_exported")) for row in status_payloads)
    truth_name_leaked = "sensor_extrinsics_truth" in status_text
    raw_sim_position_republished = any("sensor_position_ned" in row for row in status_payloads)
    low_rate_status = status_count > 0 and magnetic_count > status_count
    hashes_present = sum(1 for row in status_payloads if row.get("sensor_position_ned_hash_sha256_16"))
    simulator_position_seen = any(bool(row.get("simulator_position_present")) for row in status_payloads)

    checks = {
        "magnetic_topic_has_samples": magnetic_count > 0,
        "status_topic_has_samples": status_count > 0,
        "status_is_lower_rate_than_magnetic": low_rate_status,
        "uses_estimated_extrinsics": uses_estimated,
        "estimated_extrinsics_source_present": source_present,
        "truth_extrinsics_not_exported": not truth_exported,
        "truth_config_name_not_leaked": not truth_name_leaked,
        "raw_sim_sensor_position_not_republished": not raw_sim_position_republished,
    }
    failed = [name for name, ok in checks.items() if not ok]
    if not magnetic_messages or not status_payloads:
        validation_status = "invalid"
    elif failed:
        validation_status = "limited"
    else:
        validation_status = "pass"

    return {
        "schema_version": "mag_extrinsics_bag_proof.v1",
        "validation_status": validation_status,
        "source_chunks": [str(chunk) for chunk in chunks],
        "magnetic_topic": magnetic_topic,
        "status_topic": status_topic,
        "magnetic_message_count": magnetic_count,
        "status_message_count": status_count,
        "status_to_magnetic_ratio": (status_count / magnetic_count) if magnetic_count else None,
        "checks": checks,
        "failed_checks": failed,
        "simulator_position_seen": simulator_position_seen,
        "simulator_position_hash_count": hashes_present,
        "first_status": status_payloads[0] if status_payloads else None,
        "last_status": status_payloads[-1] if status_payloads else None,
    }


def main() -> None:
    args = parse_args()
    chunks = _mcap_chunks(args.bag)
    rows = _read_topics(chunks, [str(args.magnetic_topic), str(args.status_topic)])
    magnetic_messages = rows[str(args.magnetic_topic)]
    status_payloads = _status_payloads(rows[str(args.status_topic)])
    summary = _summarize(
        chunks=chunks,
        magnetic_topic=str(args.magnetic_topic),
        status_topic=str(args.status_topic),
        magnetic_messages=magnetic_messages,
        status_payloads=status_payloads,
    )
    output_json = _resolve(args.output_json)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    print(f"[OK] wrote bag proof summary to {output_json}")
    print(f"[OK] validation_status={summary['validation_status']}")
    if summary["failed_checks"]:
        print(f"[WARN] failed_checks={','.join(summary['failed_checks'])}")


if __name__ == "__main__":
    main()

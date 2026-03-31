"""Command line entrypoint for generating the Foxglove layout JSON."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

if __package__ is None or __package__ == "":
    _project_root = Path(__file__).resolve().parents[2]
    if str(_project_root) not in sys.path:
        sys.path.insert(0, str(_project_root))

from foxglove_layout_project.config.topics import TOPICS, with_topic_prefix
from foxglove_layout_project.generator.layout_builder import build_auv_layout
from foxglove_layout_project.generator.mock_topics import build_mock_topics_snapshot


def _default_bridge_config_path() -> Path:
    return Path(__file__).resolve().parents[2] / 'config' / 'bridge_params.yaml'


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate an AUV Foxglove layout JSON file")
    parser.add_argument(
        "--output",
        default="",
        help="Output JSON path relative to the repo root; defaults to a timestamped file",
    )
    parser.add_argument(
        "--meta-output",
        default="",
        help="Optional meta JSON path; defaults to the same directory as the layout file",
    )
    parser.add_argument(
        "--topic-prefix",
        default="",
        help="Prefix all topics with a namespace, for example /sim",
    )
    parser.add_argument(
        "--name",
        default="AUV Foxglove Layout",
        help="Layout name stored in the meta file",
    )
    parser.add_argument(
        "--description",
        default="Parameterised Foxglove layout for the AUV stack",
        help="Layout description stored in the meta file",
    )
    parser.add_argument(
        "--profile",
        default="mentor-demo",
        choices=("mentor-demo", "probe", "classic"),
        help="Layout profile to export",
    )
    parser.add_argument(
        "--with-map",
        action="store_true",
        help="Include the 3D map layer in the layout configuration",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Write formatted JSON for easier review in git",
    )
    parser.add_argument(
        "--with-mock-topics",
        action="store_true",
        help="Write a companion mock-topic snapshot for Foxglove visibility checks",
    )
    parser.add_argument(
        "--config",
        default=str(_default_bridge_config_path()),
        help="Bridge config file used for mock scene generation",
    )
    return parser.parse_args()


def _timestamped_output_path(repo_root: Path) -> Path:
    unix_timestamp = int(time.time())
    return repo_root / f"foxglove_layout_project/output/auv_layout.generated.{unix_timestamp}.json"


def main() -> None:
    args = parse_args()

    topics = with_topic_prefix(TOPICS, args.topic_prefix)
    layout = build_auv_layout(
        include_map_layer=args.with_map,
        topics=topics,
        layout_name=args.name,
        layout_description=args.description,
        layout_id="auv-data-visualization",
        profile=args.profile,
    )
    layout_text = json.dumps(layout, ensure_ascii=False, separators=(",", ":"))

    if args.pretty:
        layout_text = json.dumps(json.loads(layout_text), ensure_ascii=False, indent=2)

    repo_root = Path(__file__).resolve().parents[2]
    output_path = repo_root / args.output if args.output else _timestamped_output_path(repo_root)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(layout_text, encoding="utf-8")

    meta_path = (
        repo_root / args.meta_output
        if args.meta_output
        else output_path.with_name(f"{output_path.stem}.meta.json")
    )
    meta = {
        "name": args.name,
        "description": args.description,
        "profile": args.profile,
        "generatedBy": "foxglove_layout_project/generator/build_layout.py",
        "topicPrefix": args.topic_prefix,
        "layoutFile": str(output_path),
    }
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.with_mock_topics:
        mock_path = output_path.with_name(f"{output_path.stem}.mock_topics.json")
        mock_meta_path = output_path.with_name(f"{output_path.stem}.mock_topics.meta.json")
        mock_snapshot = build_mock_topics_snapshot(topics=topics, config_path=args.config)
        mock_path.write_text(json.dumps(mock_snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
        mock_meta_path.write_text(
            json.dumps(
                {
                    "name": "AUV Mock Foxglove Topics",
                    "description": "Deterministic mock topics used to make Foxglove layers visible without live data",
                    "profile": args.profile,
                    "generatedBy": "foxglove_layout_project/generator/mock_topics.py",
                    "topicPrefix": args.topic_prefix,
                    "layoutFile": str(output_path),
                    "mockTopicsFile": str(mock_path),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"[OK] mock topics generated: {mock_path}")
        print(f"[OK] mock meta generated:   {mock_meta_path}")

    print(f"[OK] layout generated: {output_path}")
    print(f"[OK] meta generated:   {meta_path}")


if __name__ == "__main__":
    main()

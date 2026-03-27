"""Deterministic mock topic generation for Foxglove visibility checks.

This module is the canonical fake-data source for the 3D visualization bridge
and the optional layout companion snapshot. It intentionally produces the same
topic shapes as the live digital-twin bridge so Foxglove can render the scene
even when HoloOcean or Zenoh are unavailable.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from foxglove_layout_project.config.topics import TOPICS, TopicConfig
from common.protocol import (
    Z_PATH_CABLE_MARKER,
    Z_PATH_HISTORY_TRAIL,
    Z_PATH_SEABED_CLOUD,
    Z_PATH_TRUTH_POSE,
    Z_PATH_VIEW_RANGE,
)
from sim_holoocean.interfaces.synthetic_sensors import VirtualEnvironment


@dataclass(frozen=True)
class MockTopicSnapshot:
    """Container for a snapshot of mock topics and their summary."""

    summary: dict[str, Any]
    payloads: dict[str, dict[str, Any]]


def _default_digital_twin_config_path() -> Path:
    repo_root = Path(__file__).resolve().parents[2]
    return repo_root / 'config' / 'bridge_params.yaml'


def _load_digital_twin_config(config_path: str | Path | None = None) -> dict[str, Any]:
    path = Path(config_path) if config_path is not None else _default_digital_twin_config_path()
    if not path.exists():
        return {}

    try:
        import yaml
    except Exception:
        return {}

    with path.open('r', encoding='utf-8') as file_handle:
        loaded = yaml.safe_load(file_handle)
    if not isinstance(loaded, dict):
        return {}

    digital_twin = loaded.get('digital_twin', {})
    return digital_twin if isinstance(digital_twin, dict) else {}


def build_mock_topics_snapshot(
    *,
    topics: TopicConfig | None = None,
    sample_index: int = 0,
    digital_twin_config: dict[str, Any] | None = None,
    config_path: str | Path | None = None,
) -> dict[str, Any]:
    """Build a JSON-serializable snapshot that can be written to disk.

    The snapshot includes:
    - a human-readable summary
    - the exact visual payloads used by the mock bridge
    - topic names and a minimal purpose map for quick inspection
    """
    topic_cfg = topics or TOPICS
    env_cfg = digital_twin_config if digital_twin_config is not None else _load_digital_twin_config(config_path)
    env = VirtualEnvironment(env_cfg)
    position_ned, rpy_ned = env.sample_mock_pose(sample_index)
    raw_payloads = env.build_visual_payloads(position_ned=position_ned, rpy_ned=rpy_ned, publish_terrain=True)

    payloads = {
        topic_cfg.seabed_cloud: raw_payloads[Z_PATH_SEABED_CLOUD],
        topic_cfg.cable_marker: raw_payloads[Z_PATH_CABLE_MARKER],
        topic_cfg.truth_pose: raw_payloads[Z_PATH_TRUTH_POSE],
        topic_cfg.history_trail: raw_payloads[Z_PATH_HISTORY_TRAIL],
        topic_cfg.view_range: raw_payloads[Z_PATH_VIEW_RANGE],
    }

    summary = {
        "mode": "mock",
        "sampleIndex": int(sample_index),
        "positionNed": [float(v) for v in position_ned],
        "rpyNed": [float(v) for v in rpy_ned],
        "sceneConfig": {
            "seabedZ": float(env.config.seabed_z_m),
            "terrainExtent": float(env.config.terrain_extent_m),
            "terrainResolution": float(env.config.terrain_resolution_m),
            "cableLength": float(env.config.cable_length_m),
            "viewRadius": float(env.config.view_radius_m),
        },
        "topics": {
            topic_cfg.seabed_cloud: "Seabed point cloud",
            topic_cfg.cable_marker: "Cable line strip",
            topic_cfg.truth_pose: "Ground-truth AUV pose",
            topic_cfg.history_trail: "Historical trajectory trail",
            topic_cfg.view_range: "Observation / risk range marker",
            topic_cfg.mock_scene: "Human-readable mock scene summary",
        },
        "visibleLayers": ["terrain", "cable", "truth_pose", "history_trail", "view_range"],
        "payloadSizes": {
            "seabed_cloud_points": len(payloads[topic_cfg.seabed_cloud]["points_ned"]),
            "cable_points": len(payloads[topic_cfg.cable_marker]["points_ned"]),
            "trail_points": len(payloads[topic_cfg.history_trail]["trail_ned"]),
        },
    }

    mock_scene_payload = {
        "mode": "mock",
        "sample_index": int(sample_index),
        "summary": summary,
    }

    payloads[topic_cfg.mock_scene] = {
        "summary_json": json.dumps(mock_scene_payload, ensure_ascii=False),
        "position_ned": [float(v) for v in position_ned],
        "rpy_ned": [float(v) for v in rpy_ned],
    }

    return {
        "summary": summary,
        "payloads": payloads,
    }

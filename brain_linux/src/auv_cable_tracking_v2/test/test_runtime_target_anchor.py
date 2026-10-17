"""Reviewed tie-point is a software gate, never physical survey proof."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import pytest

from auv_cable_tracking_v2.runtime_target_anchor import (
    runtime_anchor_mission_sha256, validate_runtime_target_anchor,
)
from auv_cable_tracking_v2.static_target_prior import prior_points_sha256


NOW = datetime(2026, 9, 27, tzinfo=timezone.utc)


def fixture(root: Path, **changes):
    prior = {"format": "yaml", "frame": "local_ned",
             "yaml_points_ned": [[0., 0., -1.5], [80., 0., -1.5]]}
    fly = {"end_along_m": -80., "side_hint_min_m": 6.6,
           "side_hint_max_m": 7.5, "require_runtime_identity_cue": True}
    mission = {"prior": prior, "control": {"default_speed_mps": .3},
               "v2": {"mission_geometry": "flythrough", "flythrough": fly,
                      "runtime_target_anchor": {"evidence_file": "to_be_filled"}}}
    source = root / "independent_survey.csv"
    source.write_text("synthetic test fixture, not a physical survey\n", encoding="utf-8")
    evidence = {
        "schema_version": 3, "source_kind": "survey_tie_point",
        "evidence_domain": "physical", "reviewed_for_mission": True,
        "mission_id": "mission_a", "target_id": "target_a", "reviewer": "fixture",
        "reviewed_at_utc": "2026-09-26T00:00:00Z",
        "valid_until_utc": "2026-10-27T00:00:00Z",
        "frame": "local_ned", "prior_points_sha256": prior_points_sha256(prior),
        "mission_config_sha256": runtime_anchor_mission_sha256(mission),
        "lateral_min_m": 5.8, "lateral_max_m": 6.2,
        "exclusive_lateral_min_m": 5.45, "exclusive_lateral_max_m": 6.55,
        "along_min_m": -90., "along_max_m": -70.,
        "exclusive_along_min_m": -90., "exclusive_along_max_m": 85.,
        "source_file": source.name,
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
    }
    evidence.update(changes)
    path = root / "anchor.json"
    path.write_text(json.dumps(evidence), encoding="utf-8")
    mapping = {"evidence_file": path.name,
               "evidence_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    return mapping, fly, prior, mission, source


def verify(root: Path, mapping, fly, prior, mission):
    return validate_runtime_target_anchor(mapping, fly, prior, root,
                                          mission_config=mission, now=NOW)


def test_reviewed_tie_point_binds_exact_mission_and_source(tmp_path: Path) -> None:
    mapping, fly, prior, mission, source = fixture(tmp_path)
    result = verify(tmp_path, mapping, fly, prior, mission)
    assert (result.mission_id, result.target_id) == ("mission_a", "target_a")
    assert (result.lateral_min_m, result.lateral_max_m) == (5.8, 6.2)
    assert (result.exclusive_lateral_min_m,
            result.exclusive_lateral_max_m) == (5.45, 6.55)
    assert (result.exclusive_along_min_m,
            result.exclusive_along_max_m) == (-90., 85.)
    assert result.currently_valid(NOW)
    source.write_text("changed", encoding="utf-8")
    with pytest.raises(ValueError, match="independent source hash mismatch"):
        verify(tmp_path, mapping, fly, prior, mission)


@pytest.mark.parametrize("change,error", [
    ({"evidence_domain": "synthetic"}, "physical review metadata"),
    ({"reviewed_for_mission": False}, "physical review metadata"),
    ({"valid_until_utc": "2026-09-26T00:00:01Z"}, "expired"),
    ({"lateral_min_m": 5.0, "lateral_max_m": 6.2}, "too wide"),
    ({"along_min_m": -70., "along_max_m": -60.}, "Confirm station"),
    ({"frame": "world"}, "route or frame mismatch"),
    ({"schema_version": 2}, "schema_version 3 required"),
    ({"exclusive_lateral_min_m": 5.9}, "exclusive corridor must enclose"),
    ({"exclusive_lateral_max_m": 6.0}, "exclusive corridor must enclose"),
    ({"exclusive_along_min_m": -80.}, "does not cover Confirm and Track"),
    ({"exclusive_along_max_m": 79.}, "does not cover Confirm and Track"),
])
def test_reviewed_tie_point_rejects_missing_claims(tmp_path: Path, change, error) -> None:
    mapping, fly, prior, mission, _ = fixture(tmp_path, **change)
    with pytest.raises(ValueError, match=error):
        verify(tmp_path, mapping, fly, prior, mission)


def test_task_drift_and_artifact_tamper_reject(tmp_path: Path) -> None:
    mapping, fly, prior, mission, _ = fixture(tmp_path)
    mission["control"]["default_speed_mps"] = .4
    with pytest.raises(ValueError, match="mission config hash mismatch"):
        verify(tmp_path, mapping, fly, prior, mission)
    mission["control"]["default_speed_mps"] = .3
    (tmp_path / "anchor.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="evidence hash mismatch"):
        verify(tmp_path, mapping, fly, prior, mission)

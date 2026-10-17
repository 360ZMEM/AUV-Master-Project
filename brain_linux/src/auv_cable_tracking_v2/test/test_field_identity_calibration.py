from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from auv_cable_tracking_v2.field_identity_calibration import (
    validate_field_identity_calibration,
)


def _artifact(root: Path, **changes) -> dict:
    payload = {
        "calibration_id": "field_candidate_01",
        "calibration_domain": "physical",
        "deployment_approved": True,
        "physical_deployment_approved": True,
        "detection": {"score": [0., 1.], "probability": [.1, .9]},
        "track": {"score": [0., 1.], "probability": [.1, .9]},
    }
    payload.update(changes)
    path = root / "calibration.json"
    content = json.dumps(payload).encode()
    path.write_bytes(content)
    return {"calibration_file": path.name,
            "calibration_sha256": hashlib.sha256(content).hexdigest()}


def test_pinned_explicit_physical_artifact_is_accepted_as_configuration(tmp_path: Path) -> None:
    mapping = _artifact(tmp_path)
    path, digest = validate_field_identity_calibration(mapping, "field_candidate_01", tmp_path)
    assert path == tmp_path / "calibration.json"
    assert digest == mapping["calibration_sha256"]


@pytest.mark.parametrize("changes,expected", [
    ({"calibration_domain": "simulation_proxy"}, "physical approval"),
    ({"physical_deployment_approved": False}, "physical approval"),
    ({"physical_deployment_approved": None}, "physical approval"),
    ({"calibration_id": "sim_proxy_sonar_v1"}, "ID mismatch"),
    ({"track": {"score": [1., 0.], "probability": [.1, .9]}}, "curves are invalid"),
])
def test_field_gate_rejects_unapproved_or_mismatched_artifact(
    tmp_path: Path, changes: dict, expected: str,
) -> None:
    mapping = _artifact(tmp_path, **changes)
    with pytest.raises(ValueError, match=expected):
        validate_field_identity_calibration(mapping, "field_candidate_01", tmp_path)


def test_field_gate_rejects_missing_or_changed_artifact(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="requires calibration_file"):
        validate_field_identity_calibration({"calibration_id": "physical_fake"},
                                            "physical_fake", tmp_path)
    mapping = _artifact(tmp_path)
    (tmp_path / "calibration.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="hash mismatch"):
        validate_field_identity_calibration(mapping, "field_candidate_01", tmp_path)


def test_field_gate_rejects_synthetic_id_even_when_artifact_claims_approval(tmp_path: Path) -> None:
    mapping = _artifact(tmp_path, calibration_id="synthetic_forged")
    with pytest.raises(ValueError, match="simulation-only"):
        validate_field_identity_calibration(mapping, "synthetic_forged", tmp_path)

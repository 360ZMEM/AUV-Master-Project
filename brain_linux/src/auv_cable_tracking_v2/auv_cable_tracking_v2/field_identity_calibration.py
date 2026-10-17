"""Fail-closed evidence check for non-simulation sonar identity calibration."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from auv_decision_ros.perception_quality import SourceCalibration


def validate_field_identity_calibration(
    mapping: Mapping[str, Any], expected_id: str, project_root: Path,
) -> tuple[Path, str]:
    """Require a pinned, explicitly field-approved source calibration.

    This validates a deployment artifact's structure and stated approval. It
    cannot establish that the artifact was trained on physical sonar data or
    that an upstream ROS publisher is authentic; those need field acceptance.
    """
    raw_path = str(mapping.get("calibration_file", "")).strip()
    expected_sha256 = str(mapping.get("calibration_sha256", "")).strip().lower()
    if not raw_path or len(expected_sha256) != 64 or any(
        char not in "0123456789abcdef" for char in expected_sha256
    ):
        raise ValueError("field runtime identity requires calibration_file and calibration_sha256")
    path = Path(raw_path).expanduser()
    if not path.is_absolute():
        path = project_root / path
    try:
        content = path.read_bytes()
        actual_sha256 = hashlib.sha256(content).hexdigest()
        payload = json.loads(content)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("field runtime identity calibration cannot be read") from exc
    if actual_sha256 != expected_sha256:
        raise ValueError("field runtime identity calibration hash mismatch")
    if not isinstance(payload, dict):
        raise ValueError("field runtime identity calibration must be an object")
    if (str(payload.get("calibration_id", "")) != expected_id
            or expected_id.lower().startswith(("synthetic", "sim_", "sim-"))):
        raise ValueError("field runtime identity calibration ID mismatch or simulation-only")
    if (payload.get("calibration_domain") != "physical"
            or payload.get("deployment_approved") is not True
            or payload.get("physical_deployment_approved") is not True):
        raise ValueError("field runtime identity calibration lacks explicit physical approval")
    try:
        calibration = SourceCalibration.from_json(path)
    except (KeyError, TypeError, ValueError, OSError) as exc:
        raise ValueError("field runtime identity calibration curves are invalid") from exc
    if calibration.calibration_id != expected_id:
        raise ValueError("field runtime identity calibration ID mismatch")
    return path, actual_sha256

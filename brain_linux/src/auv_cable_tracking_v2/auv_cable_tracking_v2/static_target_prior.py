"""Pin a reviewed static target prior before non-simulation, no-sonar flight.

This checks that the mission YAML still matches the reviewed artifact.  It
cannot establish the physical truth of a survey or the reviewer's authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping


@dataclass(frozen=True)
class StaticTargetPriorEvidence:
    path: Path
    sha256: str
    mission_config_sha256: str
    mission_id: str
    target_id: str
    reviewed_at_utc: datetime
    valid_until_utc: datetime

    def currently_valid(self, now: datetime | None = None) -> bool:
        instant = now or datetime.now(timezone.utc)
        return self.reviewed_at_utc <= instant <= self.valid_until_utc


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def prior_points_sha256(prior: Mapping[str, Any]) -> str:
    """Hash the route coordinates and frame actually passed to the adapter."""
    payload = {
        "frame": prior.get("frame"),
        "yaml_points_ned": prior.get("yaml_points_ned"),
    }
    return _sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"),
                              ensure_ascii=False).encode("utf-8"))


def mission_config_sha256(config: Mapping[str, Any]) -> str:
    """Pin the loaded mission, excluding only its self-referential review link."""
    payload = dict(config)
    v2 = dict(payload.get("v2", {}) or {})
    v2.pop("static_target_prior", None)
    payload["v2"] = v2
    try:
        serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                                ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValueError("static target prior mission config is not canonical JSON") from exc
    return _sha256(serialized.encode("utf-8"))


def _utc(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ValueError("static target prior review time is missing")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("static target prior review time is invalid") from exc
    if parsed.tzinfo is None:
        raise ValueError("static target prior review time needs a timezone")
    return parsed.astimezone(timezone.utc)


def _file_and_hash(path_value: Any, digest_value: Any, root: Path, label: str) -> tuple[Path, bytes]:
    digest = str(digest_value or "").lower()
    if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
        raise ValueError(f"static target prior {label} SHA-256 is missing or invalid")
    raw_path = str(path_value or "").strip()
    if not raw_path:
        raise ValueError(f"static target prior {label} path is missing")
    path = Path(raw_path).expanduser()
    if not path.is_absolute():
        path = root / path
    try:
        content = path.read_bytes()
    except OSError as exc:
        raise ValueError(f"static target prior {label} cannot be read") from exc
    if _sha256(content) != digest:
        raise ValueError(f"static target prior {label} hash mismatch")
    return path, content


def validate_static_target_prior(
    mapping: Mapping[str, Any], flythrough: Mapping[str, Any],
    prior: Mapping[str, Any], project_root: Path,
    *, mission_config: Mapping[str, Any], now: datetime | None = None,
) -> StaticTargetPriorEvidence:
    """Require source data and a current review bound to the exact YAML route.

    Approval and physical provenance remain human field-acceptance questions.
    The returned digest pins the review artifact for a mission log.
    """
    source_kind = str(flythrough.get("side_hint_source", ""))
    if source_kind not in {"survey_map", "previous_track"}:
        raise ValueError("non-sim static target prior source must be survey_map or previous_track")
    points = prior.get("yaml_points_ned")
    if (prior.get("format") != "yaml" or prior.get("frame") != "local_ned"
            or not isinstance(points, list) or len(points) < 2):
        raise ValueError("static target prior requires explicit local_ned YAML route points")
    try:
        if any(len(point) != 3 or not all(math.isfinite(float(value)) for value in point)
               for point in points):
            raise ValueError("static target prior route points are invalid")
    except (TypeError, ValueError) as exc:
        raise ValueError("static target prior route points are invalid") from exc
    evidence_path, content = _file_and_hash(
        mapping.get("evidence_file"), mapping.get("evidence_sha256"),
        project_root, "evidence",
    )
    try:
        evidence = json.loads(content)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("static target prior evidence is not valid JSON") from exc
    if not isinstance(evidence, dict):
        raise ValueError("static target prior evidence must be an object")
    if evidence.get("schema_version") != 2:
        raise ValueError("static target prior schema_version 2 required")
    if (evidence.get("source_kind") != source_kind
            or evidence.get("reviewed_for_mission") is not True
            or not str(evidence.get("mission_id", "")).strip()
            or not str(evidence.get("target_id", "")).strip()
            or not str(evidence.get("reviewer", "")).strip()):
        raise ValueError("static target prior review metadata is incomplete")
    reviewed_at = _utc(evidence.get("reviewed_at_utc"))
    valid_until = _utc(evidence.get("valid_until_utc"))
    current = now or datetime.now(timezone.utc)
    if not reviewed_at <= current <= valid_until:
        raise ValueError("static target prior review is expired or not yet valid")
    if evidence.get("prior_points_sha256") != prior_points_sha256(prior):
        raise ValueError("static target prior route hash mismatch")
    config_digest = mission_config_sha256(mission_config)
    if evidence.get("mission_config_sha256") != config_digest:
        raise ValueError("static target prior mission config hash mismatch")
    if evidence.get("frame") != prior.get("frame"):
        raise ValueError("static target prior frame mismatch")
    for key in ("side_hint_min_m", "side_hint_max_m"):
        try:
            actual = float(flythrough[key])
            reviewed = float(evidence[key])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"static target prior {key} is missing") from exc
        if not math.isfinite(actual) or not math.isfinite(reviewed) or abs(actual - reviewed) > 1e-6:
            raise ValueError(f"static target prior {key} differs from review")
    _file_and_hash(evidence.get("source_file"), evidence.get("source_sha256"),
                   project_root, "source")
    return StaticTargetPriorEvidence(
        path=evidence_path, sha256=_sha256(content), mission_config_sha256=config_digest,
        mission_id=str(evidence['mission_id']).strip(),
        target_id=str(evidence['target_id']).strip(),
        reviewed_at_utc=reviewed_at,
        valid_until_utc=valid_until,
    )

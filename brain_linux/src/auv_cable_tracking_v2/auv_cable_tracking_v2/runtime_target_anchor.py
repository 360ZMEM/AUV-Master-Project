"""Mission-bound independent target tie-point for runtime sonar association.

The reviewed source is external to the sonar line fitter and magnetic peak.
Hashes and metadata make the input auditable, but do not prove survey truth.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping

from .static_target_prior import prior_points_sha256


@dataclass(frozen=True)
class RuntimeTargetAnchorEvidence:
    path: Path
    sha256: str
    mission_id: str
    target_id: str
    lateral_min_m: float
    lateral_max_m: float
    exclusive_lateral_min_m: float
    exclusive_lateral_max_m: float
    exclusive_along_min_m: float
    exclusive_along_max_m: float
    reviewed_at_utc: datetime
    valid_until_utc: datetime

    def currently_valid(self, now: datetime | None = None) -> bool:
        instant = now or datetime.now(timezone.utc)
        return self.reviewed_at_utc <= instant <= self.valid_until_utc


def _hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def runtime_anchor_mission_sha256(config: Mapping[str, Any]) -> str:
    """Bind the complete loaded mission, excluding the anchor's own file link."""
    payload = dict(config)
    v2 = dict(payload.get("v2", {}) or {})
    v2.pop("runtime_target_anchor", None)
    payload["v2"] = v2
    try:
        serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                                ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValueError("runtime target anchor mission config is not canonical JSON") from exc
    return _hash(serialized.encode("utf-8"))


def _read_pinned(path_value: Any, digest_value: Any, root: Path, label: str) -> tuple[Path, bytes]:
    digest = str(digest_value or "").lower()
    if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
        raise ValueError(f"runtime target anchor {label} SHA-256 is missing or invalid")
    raw_path = str(path_value or "").strip()
    if not raw_path:
        raise ValueError(f"runtime target anchor {label} path is missing")
    path = Path(raw_path).expanduser()
    if not path.is_absolute():
        path = root / path
    try:
        content = path.read_bytes()
    except OSError as exc:
        raise ValueError(f"runtime target anchor {label} cannot be read") from exc
    if _hash(content) != digest:
        raise ValueError(f"runtime target anchor {label} hash mismatch")
    return path, content


def _utc(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ValueError("runtime target anchor review time is missing")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("runtime target anchor review time is invalid") from exc
    if result.tzinfo is None:
        raise ValueError("runtime target anchor review time needs a timezone")
    return result.astimezone(timezone.utc)


def _finite_number(value: Any, name: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"runtime target anchor {name} is invalid")
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"runtime target anchor {name} is invalid") from exc
    if not math.isfinite(result):
        raise ValueError(f"runtime target anchor {name} is invalid")
    return result


def validate_runtime_target_anchor(
    mapping: Mapping[str, Any], flythrough: Mapping[str, Any],
    prior: Mapping[str, Any], project_root: Path, *,
    mission_config: Mapping[str, Any], now: datetime | None = None,
) -> RuntimeTargetAnchorEvidence:
    """Check a reviewed local tie-point and its exact task/source binding.

    The original survey, handoff, reviewer and target association must still
    be verified outside this parser. No synthetic artifact grants field use.
    """
    path, content = _read_pinned(mapping.get("evidence_file"),
                                 mapping.get("evidence_sha256"), project_root, "evidence")
    try:
        evidence = json.loads(content)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("runtime target anchor evidence is not valid JSON") from exc
    if not isinstance(evidence, dict) or evidence.get("schema_version") != 3:
        raise ValueError("runtime target anchor schema_version 3 required")
    if (evidence.get("source_kind") not in {"survey_tie_point", "confirmed_handoff"}
            or evidence.get("evidence_domain") != "physical"
            or evidence.get("reviewed_for_mission") is not True
            or not all(str(evidence.get(key, "")).strip()
                       for key in ("mission_id", "target_id", "reviewer"))):
        raise ValueError("runtime target anchor physical review metadata is incomplete")
    reviewed_at = _utc(evidence.get("reviewed_at_utc"))
    valid_until = _utc(evidence.get("valid_until_utc"))
    instant = now or datetime.now(timezone.utc)
    if not reviewed_at <= instant <= valid_until:
        raise ValueError("runtime target anchor review is expired or not yet valid")
    if (prior.get("format") != "yaml" or prior.get("frame") != "local_ned"
            or evidence.get("frame") != "local_ned"
            or evidence.get("prior_points_sha256") != prior_points_sha256(prior)):
        raise ValueError("runtime target anchor prior route or frame mismatch")
    if evidence.get("mission_config_sha256") != runtime_anchor_mission_sha256(mission_config):
        raise ValueError("runtime target anchor mission config hash mismatch")
    lower = _finite_number(evidence.get("lateral_min_m"), "lateral_min_m")
    upper = _finite_number(evidence.get("lateral_max_m"), "lateral_max_m")
    exclusive_lower = _finite_number(evidence.get("exclusive_lateral_min_m"),
                                     "exclusive_lateral_min_m")
    exclusive_upper = _finite_number(evidence.get("exclusive_lateral_max_m"),
                                     "exclusive_lateral_max_m")
    exclusive_along_min = _finite_number(evidence.get("exclusive_along_min_m"),
                                         "exclusive_along_min_m")
    exclusive_along_max = _finite_number(evidence.get("exclusive_along_max_m"),
                                         "exclusive_along_max_m")
    along_min = _finite_number(evidence.get("along_min_m"), "along_min_m")
    along_max = _finite_number(evidence.get("along_max_m"), "along_max_m")
    end_along = _finite_number(flythrough.get("end_along_m"), "end_along_m")
    if not lower < upper or upper - lower > 1.0:
        raise ValueError("runtime target anchor interval is missing or too wide")
    if not exclusive_lower < lower < upper < exclusive_upper:
        raise ValueError("runtime target exclusive corridor must enclose the anchor")
    if not along_min <= end_along <= along_max or along_min >= along_max:
        raise ValueError("runtime target anchor does not cover Confirm station")
    raw_points = prior.get("yaml_points_ned")
    if not isinstance(raw_points, list) or len(raw_points) < 2:
        raise ValueError("runtime target exclusive corridor needs a complete prior route")
    try:
        points_xy = [(_finite_number(point[0], "prior x"),
                      _finite_number(point[1], "prior y")) for point in raw_points]
    except (IndexError, KeyError, TypeError) as exc:
        raise ValueError("runtime target exclusive corridor needs a complete prior route") from exc
    route_length = sum(math.hypot(right[0] - left[0], right[1] - left[1])
                       for left, right in zip(points_xy, points_xy[1:]))
    if (not exclusive_along_min <= along_min
            or not exclusive_along_max >= max(along_max, route_length)
            or exclusive_along_min >= exclusive_along_max):
        raise ValueError("runtime target exclusive corridor does not cover Confirm and Track")
    _read_pinned(evidence.get("source_file"), evidence.get("source_sha256"),
                 project_root, "independent source")
    return RuntimeTargetAnchorEvidence(
        path=path, sha256=_hash(content),
        mission_id=str(evidence["mission_id"]).strip(),
        target_id=str(evidence["target_id"]).strip(),
        lateral_min_m=lower, lateral_max_m=upper,
        exclusive_lateral_min_m=exclusive_lower,
        exclusive_lateral_max_m=exclusive_upper,
        exclusive_along_min_m=exclusive_along_min,
        exclusive_along_max_m=exclusive_along_max,
        reviewed_at_utc=reviewed_at, valid_until_utc=valid_until,
    )

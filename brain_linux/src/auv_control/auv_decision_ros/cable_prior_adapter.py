"""Cable prior loading helpers for the cable tracking node."""

from __future__ import annotations

from pathlib import Path
import sys
from typing import Any

import numpy as np
import yaml


def ensure_auv_master_mag_on_path(project_root: Path, auv_master_mag_root: str | Path = "AUV-Master-Mag") -> Path:
    mag_root = Path(auv_master_mag_root)
    if not mag_root.is_absolute():
        mag_root = project_root / mag_root
    src_root = mag_root / "src"
    if str(src_root) not in sys.path:
        sys.path.insert(0, str(src_root))
    return mag_root


# Static pose-warp presets from AUV-Master-Mag docs 28 表1 (step 2 静态位姿扭曲 only;
# the dynamic θ_drift / navigation-drift channels of step 3 are NOT reproduced here).
_PRIOR_TIER_PROFILES: dict[str, dict[str, Any]] = {
    "light": {"translation_xy_m": [0.0, 3.0], "rotation_deg": 1.5, "scale_xy": [0.995, 1.0]},
    "mid": {"translation_xy_m": [0.0, 7.5], "rotation_deg": 3.0, "scale_xy": [0.99, 1.0]},
    "heavy": {"translation_xy_m": [0.0, 10.0], "rotation_deg": 5.0, "scale_xy": [0.98, 1.0]},
}


def apply_prior_pose_error(cable_map, pose_error_cfg: dict[str, Any] | None):
    """Optionally warp a nominal-route prior CableMap with a static pose error.

    Default behaviour is a no-op: when pose_error_cfg is absent or enabled is false the
    input CableMap is returned unchanged, preserving the clean-prior end-to-end path.
    When enabled, xy points are transformed by S·R(θ0)·P + t0 (via the same
    apply_route_prior_pose_error used by AUV-Master-Mag, code-same-origin) while burial
    depth stays aligned per point. Tier presets follow docs 28 表1; explicit values
    override the tier.
    """
    cfg = dict(pose_error_cfg or {})
    if not bool(cfg.get("enabled", False)):
        return cable_map

    from auv_mag_tracking.math_utils import apply_route_prior_pose_error

    tier = str(cfg.get("tier", "") or "").strip().lower()
    profile = _PRIOR_TIER_PROFILES.get(tier, {})
    translation = cfg.get("translation_xy_m", profile.get("translation_xy_m", [0.0, 0.0]))
    rotation = cfg.get("rotation_deg", profile.get("rotation_deg", 0.0))
    scale = cfg.get("scale_xy", profile.get("scale_xy", [1.0, 1.0]))

    warped_xy = apply_route_prior_pose_error(
        cable_map.points_xy_m,
        translation_xy_m=translation,
        rotation_deg=float(rotation),
        scale_xy=scale,
    )
    cable_map.points_xy_m = np.asarray(warped_xy, dtype=float)
    cable_map.metadata = {
        **dict(getattr(cable_map, "metadata", {}) or {}),
        "prior_pose_error": {
            "enabled": True,
            "tier": tier or None,
            "translation_xy_m": [float(v) for v in translation],
            "rotation_deg": float(rotation),
            "scale_xy": [float(v) for v in scale],
            "note": "static pose warp only (docs 28 step 2); no dynamic drift channel",
        },
    }
    return cable_map


def _infer_format(path: str | Path, explicit_format: str) -> str:
    fmt = explicit_format.strip().lower()
    if fmt and fmt != "auto":
        return fmt
    suffix = Path(path).suffix.lower()
    if suffix == ".csv":
        return "csv"
    if suffix in {".json", ".geojson"}:
        return "geojson"
    if suffix in {".yaml", ".yml"}:
        return "yaml"
    return "yaml"


def yaml_points_to_cable_map(points_ned: list[Any], *, frame: str = "local_ned", burial_depth_m: Any = None):
    from auv_mag_tracking.api import CableMap

    points = np.asarray(points_ned, dtype=float)
    if points.ndim != 2 or points.shape[0] < 2 or points.shape[1] < 2:
        raise ValueError("yaml cable points must be an Nx2 or Nx3 numeric array with N >= 2")
    burial = burial_depth_m
    if burial is None and points.shape[1] >= 3:
        burial = np.abs(points[:, 2].astype(float))
    return CableMap(points_xy_m=points[:, :2], frame=frame, burial_depth_m=burial)


def load_cable_map_from_config(config: dict[str, Any], *, project_root: Path):
    prior_cfg = dict(config.get("prior", {}) or {})
    ensure_auv_master_mag_on_path(project_root, config.get("auv_master_mag_root", "AUV-Master-Mag"))
    from auv_mag_tracking.api import CableMap

    frame = str(prior_cfg.get("frame", "local_ned"))
    fmt = str(prior_cfg.get("format", "auto"))
    path_value = str(prior_cfg.get("path", "") or "")
    yaml_points = prior_cfg.get("yaml_points_ned") or []
    burial_depth = prior_cfg.get("burial_depth_m")
    pose_error_cfg = prior_cfg.get("pose_error")

    if path_value:
        path = Path(path_value)
        if not path.is_absolute():
            path = project_root / path
        inferred = _infer_format(path, fmt)
        if inferred == "csv":
            cable_map = CableMap.from_csv(path, frame=frame)
        elif inferred == "geojson":
            cable_map = CableMap.from_geojson(path, frame=frame)
        elif inferred == "yaml":
            payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            points = (
                payload.get("points_ned")
                or payload.get("yaml_points_ned")
                or payload.get("cable_path", {}).get("points_ned")
                or payload.get("cable_prior", {}).get("points_ned")
            )
            if points is None:
                raise ValueError(f"YAML cable prior has no points_ned: {path}")
            cable_map = yaml_points_to_cable_map(points, frame=frame, burial_depth_m=burial_depth)
        else:
            raise ValueError(f"unsupported cable prior format: {inferred}")
        return apply_prior_pose_error(cable_map, pose_error_cfg)

    if yaml_points:
        cable_map = yaml_points_to_cable_map(yaml_points, frame=frame, burial_depth_m=burial_depth)
        return apply_prior_pose_error(cable_map, pose_error_cfg)

    raise ValueError("cable prior requires prior.path or prior.yaml_points_ned")

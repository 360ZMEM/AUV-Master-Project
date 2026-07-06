#!/usr/bin/env python3
"""Emit a cable_tracking config variant with a chosen prior.pose_error tier.

Reads the canonical brain_linux/config/cable_tracking.yaml and writes a copy whose
prior.pose_error block is set for the requested tier. The on-disk canonical config
is never modified (clean-prior default is preserved); this only produces throwaway
variants used by the replay-driven end-to-end harness.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BASE_CONFIG = PROJECT_ROOT / "brain_linux/config/cable_tracking.yaml"

TIER_PRESETS = {
    "clean": {"enabled": False},
    "light": {"enabled": True, "tier": "light", "translation_xy_m": [0.0, 3.0], "rotation_deg": 1.5, "scale_xy": [0.995, 1.0]},
    "mid": {"enabled": True, "tier": "mid", "translation_xy_m": [0.0, 7.5], "rotation_deg": 3.0, "scale_xy": [0.99, 1.0]},
    "heavy": {"enabled": True, "tier": "heavy", "translation_xy_m": [0.0, 10.0], "rotation_deg": 5.0, "scale_xy": [0.98, 1.0]},
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tier", required=True, choices=sorted(TIER_PRESETS))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    payload = yaml.safe_load(BASE_CONFIG.read_text(encoding="utf-8")) or {}
    prior = payload.setdefault("cable_tracking", {}).setdefault("prior", {})
    prior["pose_error"] = dict(TIER_PRESETS[args.tier])

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")
    print(f"[OK] wrote {args.tier} pose_error config -> {args.output}")


if __name__ == "__main__":
    main()

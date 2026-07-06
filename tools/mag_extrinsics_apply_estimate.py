#!/usr/bin/env python3
"""Apply an estimated magnetometer extrinsic to a new config file."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-config", type=Path, required=True)
    parser.add_argument("--estimate", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def _resolve(path: Path) -> Path:
    return path if path.is_absolute() else PROJECT_ROOT / path


def main() -> None:
    args = parse_args()
    base_path = _resolve(args.base_config)
    estimate_path = _resolve(args.estimate)
    output_path = _resolve(args.output)
    if output_path == base_path:
        raise ValueError("output must be a new file; refusing to overwrite base config")

    base = yaml.safe_load(base_path.read_text(encoding="utf-8")) or {}
    estimate = yaml.safe_load(estimate_path.read_text(encoding="utf-8")) or {}
    mag_estimate = ((estimate.get("sensor_extrinsics_estimated", {}) or {}).get("mag", {}) or {})
    if not mag_estimate:
        raise ValueError(f"estimate has no sensor_extrinsics_estimated.mag: {estimate_path}")

    target = dict(base)
    target.setdefault("sensor_extrinsics_estimated", {})
    target["sensor_extrinsics_estimated"] = dict(target["sensor_extrinsics_estimated"] or {})
    target["sensor_extrinsics_estimated"]["mag"] = mag_estimate
    target.setdefault("metadata", {})
    if isinstance(target["metadata"], dict):
        target["metadata"]["mag_extrinsics_source"] = str(estimate_path)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(yaml.safe_dump(target, sort_keys=False, allow_unicode=True), encoding="utf-8")
    print(f"[OK] wrote {output_path}")


if __name__ == "__main__":
    main()

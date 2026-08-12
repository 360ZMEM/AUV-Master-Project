#!/usr/bin/env python3
"""Validate a thesis experiment bundle and fail on incomplete diagnostics."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.experiment_contract import validate_bundle  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("bundle", type=Path)
    args = parser.parse_args()

    violations = validate_bundle(args.bundle)
    if violations:
        for violation in violations:
            print(f"FAIL  {violation}")
        return 1
    print(f"OK    {args.bundle}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

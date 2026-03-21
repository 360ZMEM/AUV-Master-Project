#!/usr/bin/env python3
"""Compare legacy and unified simulation main-loop behavior.

Phase 2.5 goal: verify structural reshaping does not change core behavior trends.
This script runs both pipelines, parses key metrics from stdout, and reports deltas.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional


METRICS_RE = re.compile(
    r"rms=(?P<rms>[0-9.eE+-]+)m\s+mean_error=(?P<mean>[0-9.eE+-]+)m\s+axis_ratio=(?P<axis>[0-9.eE+-]+)%\s+sat_ratio=(?P<sat>[0-9.eE+-]+)%"
)
FLAGS_RE = re.compile(
    r"safety_event_count=(?P<safety>\d+)\s+pass_rms=(?P<pass_rms>True|False)\s+pass_axis_ratio=(?P<pass_axis>True|False)"
)


@dataclass
class RunMetrics:
    rms: float
    mean_error: float
    axis_ratio: float
    sat_ratio: float
    safety_event_count: int
    pass_rms: bool
    pass_axis_ratio: bool


@dataclass
class CompareResult:
    legacy: RunMetrics
    unified: RunMetrics
    delta_rms: float
    delta_axis_ratio: float
    delta_sat_ratio: float
    delta_safety_events: int
    equivalent: bool


def _parse_metrics(output: str) -> RunMetrics:
    m = METRICS_RE.search(output)
    f = FLAGS_RE.search(output)
    if not m or not f:
        raise ValueError("failed to parse metrics from simulation output")

    return RunMetrics(
        rms=float(m.group("rms")),
        mean_error=float(m.group("mean")),
        axis_ratio=float(m.group("axis")) / 100.0,
        sat_ratio=float(m.group("sat")) / 100.0,
        safety_event_count=int(f.group("safety")),
        pass_rms=(f.group("pass_rms") == "True"),
        pass_axis_ratio=(f.group("pass_axis") == "True"),
    )


def _run_command(cmd: list[str], cwd: Path, timeout: int) -> str:
    completed = subprocess.run(
        cmd,
        cwd=str(cwd),
        text=True,
        capture_output=True,
        timeout=None if timeout <= 0 else timeout,
        check=False,
    )
    merged = (completed.stdout or "") + "\n" + (completed.stderr or "")
    if completed.returncode != 0:
        raise RuntimeError(f"command failed ({completed.returncode}): {' '.join(cmd)}\n{merged}")
    return merged


def _save_log(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Compare legacy and unified simulation behavior")
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument(
        "--legacy-root",
        type=Path,
        default=Path(__file__).resolve().parents[2] / "Master毕业设计代码实现" / "auv_project_new" / "AUV_Software_Stack",
    )
    parser.add_argument("--legacy-config", type=Path, default=None)
    parser.add_argument("--unified-config", type=Path, default=None)
    parser.add_argument("--timeout", type=int, default=0, help="seconds; 0 means no timeout")
    parser.add_argument("--rms-tol", type=float, default=0.10)
    parser.add_argument("--axis-ratio-tol", type=float, default=0.05)
    parser.add_argument("--sat-ratio-tol", type=float, default=0.10)
    parser.add_argument("--safety-event-tol", type=int, default=5)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    project_root = args.project_root.resolve()
    legacy_root = args.legacy_root.resolve()
    unified_apps = project_root / "sim_holoocean" / "apps"

    legacy_cfg = (args.legacy_config.resolve() if args.legacy_config else (legacy_root / "config" / "sim_params.yaml"))
    unified_cfg = (args.unified_config.resolve() if args.unified_config else (project_root / "config" / "sim_params.yaml"))

    legacy_cmd = ["python", "4_codes/main.py", "--config", str(legacy_cfg)]
    unified_cmd = ["python", "main.py", "--config", str(unified_cfg)]

    print("[eq] legacy cwd:", legacy_root)
    print("[eq] unified cwd:", unified_apps)
    print("[eq] legacy cmd:", " ".join(legacy_cmd))
    print("[eq] unified cmd:", " ".join(unified_cmd))

    if args.dry_run:
        return 0

    legacy_out = _run_command(legacy_cmd, legacy_root, args.timeout)
    unified_out = _run_command(unified_cmd, unified_apps, args.timeout)

    logs_dir = project_root / "log"
    _save_log(logs_dir / "phase2_5_legacy.log", legacy_out)
    _save_log(logs_dir / "phase2_5_unified.log", unified_out)

    legacy_metrics = _parse_metrics(legacy_out)
    unified_metrics = _parse_metrics(unified_out)

    result = CompareResult(
        legacy=legacy_metrics,
        unified=unified_metrics,
        delta_rms=abs(legacy_metrics.rms - unified_metrics.rms),
        delta_axis_ratio=abs(legacy_metrics.axis_ratio - unified_metrics.axis_ratio),
        delta_sat_ratio=abs(legacy_metrics.sat_ratio - unified_metrics.sat_ratio),
        delta_safety_events=abs(legacy_metrics.safety_event_count - unified_metrics.safety_event_count),
        equivalent=False,
    )

    result.equivalent = (
        result.delta_rms <= args.rms_tol
        and result.delta_axis_ratio <= args.axis_ratio_tol
        and result.delta_sat_ratio <= args.sat_ratio_tol
        and result.delta_safety_events <= args.safety_event_tol
        and legacy_metrics.pass_rms
        and legacy_metrics.pass_axis_ratio
        and unified_metrics.pass_rms
        and unified_metrics.pass_axis_ratio
    )

    summary = asdict(result)
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    if not result.equivalent:
        print("[eq][FAIL] unified behavior deviates beyond tolerances")
        return 2

    print("[eq][PASS] unified behavior is equivalent within tolerances")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Shared artifact contract for new thesis experiments."""

from __future__ import annotations

import csv
import datetime as dt
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_VERSION = 1
DIAGNOSTIC_FIELDS = (
    "effective_sample_count",
    "failure_event_count",
    "capability_gate_status",
    "solver_wall_time_current_ms",
    "fallback_type",
)


def _utc_now() -> str:
    return dt.datetime.now(tz=dt.timezone.utc).isoformat()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _git(*args: str, cwd: Path = REPO_ROOT) -> str | None:
    proc = subprocess.run(
        ["git", *args],
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
    )
    return proc.stdout.strip() if proc.returncode == 0 else None


def repository_state() -> dict[str, Any]:
    submodules: list[dict[str, str]] = []
    for line in (_git("submodule", "status") or "").splitlines():
        fields = line.strip().split()
        if len(fields) >= 2:
            submodules.append(
                {
                    "path": fields[1],
                    "commit": fields[0].lstrip("-+U"),
                    "status_prefix": line[:1],
                }
            )
    return {
        "commit": _git("rev-parse", "HEAD"),
        "submodules": submodules,
        "worktree_state": "not_evaluated",
        "worktree_note": (
            "Global dirty-state probing is skipped because this workspace "
            "requires an unavailable git-lfs filter. Artifact hashes and "
            "config snapshots remain authoritative."
        ),
    }


def _display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT.resolve()))
    except ValueError:
        return str(path.resolve())


def _snapshot_name(path: Path) -> Path:
    try:
        relative = path.resolve().relative_to(REPO_ROOT.resolve())
    except ValueError:
        relative = Path("external") / path.name
    return relative


def _write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def initialize_bundle(
    output_dir: Path,
    *,
    experiment_id: str,
    runner: str,
    argv: Sequence[str],
    data_layer: str,
    matrix: dict[str, Any],
    duration_s: float | int | None,
    config_paths: Iterable[Path] = (),
    extra_manifest: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create the standard artifact layout before any run starts."""
    output_dir.mkdir(parents=True, exist_ok=True)
    config_dir = output_dir / "config_snapshot"
    figures_dir = output_dir / "figures"
    config_dir.mkdir(exist_ok=True)
    figures_dir.mkdir(exist_ok=True)

    snapshots: list[dict[str, Any]] = []
    for raw_path in sorted({Path(path).resolve() for path in config_paths}):
        record: dict[str, Any] = {
            "source_path": _display_path(raw_path),
            "exists": raw_path.is_file(),
            "snapshot_path": None,
            "size_bytes": None,
            "sha256": None,
        }
        if raw_path.is_file():
            destination = config_dir / _snapshot_name(raw_path)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(raw_path, destination)
            record.update(
                {
                    "snapshot_path": _display_path(destination),
                    "size_bytes": destination.stat().st_size,
                    "sha256": _sha256(destination),
                }
            )
        snapshots.append(record)

    manifest: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "experiment_id": experiment_id,
        "created_at_utc": _utc_now(),
        "runner": runner,
        "argv": list(argv),
        "data_layer": data_layer,
        "matrix": matrix,
        "duration_s": duration_s,
        "repository": repository_state(),
        "config_snapshots": snapshots,
        "required_artifacts": [
            "run_manifest.json",
            "config_snapshot/",
            "metrics.csv",
            "status.json",
            "failure_events.csv",
            "environment.txt",
            "report.md",
            "figures/",
        ],
    }
    if extra_manifest:
        manifest["experiment"] = extra_manifest
    _write_json(output_dir / "run_manifest.json", manifest)
    _write_json(
        output_dir / "status.json",
        {
            "schema_version": SCHEMA_VERSION,
            "state": "running",
            "updated_at_utc": _utc_now(),
            "valid_run_count": 0,
            "invalid_run_count": 0,
            "diagnostic_completeness": {},
        },
    )
    with (output_dir / "failure_events.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "run_id",
                "stage",
                "failure_type",
                "message",
                "wall_time_current_ms",
                "capability_gate_status",
            ],
        )
        writer.writeheader()
    environment = [
        f"captured_at_utc={_utc_now()}",
        f"hostname={platform.node()}",
        f"platform={platform.platform()}",
        f"python={sys.version.replace(os.linesep, ' ')}",
        f"executable={sys.executable}",
        f"cwd={Path.cwd()}",
    ]
    (output_dir / "environment.txt").write_text(
        "\n".join(environment) + "\n", encoding="utf-8"
    )
    (output_dir / "report.md").write_text(
        "# Experiment Bundle Report\n\nStatus: running\n",
        encoding="utf-8",
    )
    return manifest


def _clean_value(value: object) -> object:
    if value is None:
        return ""
    if isinstance(value, float):
        if value != value:
            return "nan"
        return f"{value:.9g}"
    return value


def _run_id(row: dict[str, object], index: int) -> str:
    components = [
        str(row.get("scenario", "")).strip(),
        f"seed{row.get('seed', '')}",
        str(row.get("mpc_mode", "")).strip(),
    ]
    text = "__".join(component for component in components if component)
    return text or f"run_{index:04d}"


def enrich_rows(
    rows: Sequence[dict[str, object]],
    *,
    success_statuses: set[str] | None = None,
) -> list[dict[str, object]]:
    success = success_statuses or {"ok"}
    enriched: list[dict[str, object]] = []
    for index, original in enumerate(rows):
        row = dict(original)
        status = str(row.get("status", "")).strip()
        valid = status in success
        row.setdefault("run_id", _run_id(row, index))
        row.setdefault("valid_run", valid)
        row.setdefault("invalid_reason", "" if valid else row.get("error", status))
        row.setdefault("effective_sample_count", "not_observed")
        row.setdefault("failure_event_count", 0 if valid else 1)
        row.setdefault("capability_gate_status", "not_observed")
        row.setdefault("solver_wall_time_current_ms", "not_observed")
        row.setdefault("fallback_type", "not_observed")
        enriched.append(row)
    return enriched


def _fieldnames(rows: Sequence[dict[str, object]]) -> list[str]:
    preferred = [
        "run_id",
        "scenario",
        "seed",
        "mpc_mode",
        "status",
        "valid_run",
        "invalid_reason",
        *DIAGNOSTIC_FIELDS,
    ]
    seen = set(preferred)
    remaining: list[str] = []
    for row in rows:
        for key in row:
            if key not in seen:
                seen.add(key)
                remaining.append(key)
    return preferred + remaining


def _diagnostic_completeness(
    rows: Sequence[dict[str, object]],
) -> dict[str, dict[str, object]]:
    completeness: dict[str, dict[str, object]] = {}
    for field in DIAGNOSTIC_FIELDS:
        observed = sum(
            1
            for row in rows
            if str(row.get(field, "")).strip()
            not in {"", "not_observed", "unknown", "nan"}
        )
        completeness[field] = {
            "observed_count": observed,
            "total_count": len(rows),
            "complete": bool(rows) and observed == len(rows),
        }
    return completeness


def finalize_bundle(
    output_dir: Path,
    rows: Sequence[dict[str, object]],
    *,
    success_statuses: set[str] | None = None,
) -> dict[str, Any]:
    """Write standard metrics, failures, status and report after all runs."""
    success = success_statuses or {"ok"}
    enriched = enrich_rows(rows, success_statuses=success)
    fields = _fieldnames(enriched)
    with (output_dir / "metrics.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in enriched:
            writer.writerow({key: _clean_value(row.get(key, "")) for key in fields})

    failures: list[dict[str, object]] = []
    for row in enriched:
        if str(row.get("status", "")) in success:
            continue
        failures.append(
            {
                "run_id": row["run_id"],
                "stage": "experiment_or_analysis",
                "failure_type": row.get("status", "unknown"),
                "message": row.get("error") or row.get("invalid_reason") or "",
                "wall_time_current_ms": row.get(
                    "solver_wall_time_current_ms", "not_observed"
                ),
                "capability_gate_status": row.get(
                    "capability_gate_status", "not_observed"
                ),
            }
        )
    failure_fields = [
        "run_id",
        "stage",
        "failure_type",
        "message",
        "wall_time_current_ms",
        "capability_gate_status",
    ]
    with (output_dir / "failure_events.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=failure_fields)
        writer.writeheader()
        writer.writerows(failures)

    valid_count = sum(1 for row in enriched if str(row.get("status")) in success)
    completeness = _diagnostic_completeness(enriched)
    status_payload = {
        "schema_version": SCHEMA_VERSION,
        "state": "complete" if valid_count == len(enriched) else "complete_with_failures",
        "updated_at_utc": _utc_now(),
        "run_count": len(enriched),
        "valid_run_count": valid_count,
        "invalid_run_count": len(enriched) - valid_count,
        "failure_event_count": len(failures),
        "diagnostic_completeness": completeness,
        "contract_complete": all(
            item["complete"] for item in completeness.values()
        ),
    }
    _write_json(output_dir / "status.json", status_payload)

    incomplete = [
        field for field, item in completeness.items() if not item["complete"]
    ]
    report = [
        "# Experiment Bundle Report",
        "",
        f"- State: `{status_payload['state']}`",
        f"- Valid runs: `{valid_count}/{len(enriched)}`",
        f"- Failure events: `{len(failures)}`",
        f"- Diagnostic contract complete: `{status_payload['contract_complete']}`",
        f"- Incomplete diagnostics: `{', '.join(incomplete) if incomplete else 'none'}`",
        "",
        "A successful process exit is not sufficient for contract completeness.",
        "Fields marked `not_observed` remain explicit evidence gaps.",
        "",
    ]
    (output_dir / "report.md").write_text(
        "\n".join(report), encoding="utf-8"
    )
    return status_payload


def validate_bundle(output_dir: Path) -> list[str]:
    """Return contract violations without mutating the bundle."""
    violations: list[str] = []
    required = [
        "run_manifest.json",
        "config_snapshot",
        "metrics.csv",
        "status.json",
        "failure_events.csv",
        "environment.txt",
        "report.md",
        "figures",
    ]
    for name in required:
        if not (output_dir / name).exists():
            violations.append(f"missing artifact: {name}")
    status_path = output_dir / "status.json"
    if status_path.is_file():
        try:
            status = json.loads(status_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            violations.append(f"invalid status.json: {exc}")
        else:
            if status.get("state") not in {
                "running",
                "complete",
                "complete_with_failures",
            }:
                violations.append("invalid status state")
            if status.get("state") != "running" and not status.get(
                "contract_complete", False
            ):
                violations.append("diagnostic contract incomplete")
    return violations

#!/usr/bin/env python3
"""Compose an authoritative sweep table while preserving failed source runs."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from tools.experiment_contract import finalize_bundle, initialize_bundle  # noqa: E402


KEYS = ("scenario", "seed", "mpc_mode")


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def key(row: dict[str, str]) -> tuple[str, ...]:
    return tuple(row[name] for name in KEYS)


def write_rows(path: Path, rows: list[dict[str, str]]) -> None:
    fields: list[str] = []
    for row in rows:
        for field in row:
            if field not in fields:
                fields.append(field)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--primary", type=Path, required=True)
    parser.add_argument("--repair", type=Path, required=True, action="append")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--aggregate-csv", type=Path)
    args = parser.parse_args()

    primary = read_rows(args.primary)
    primary_keys = [key(row) for row in primary]
    if len(set(primary_keys)) != len(primary_keys):
        raise ValueError("primary table contains duplicate scenario/seed/mode keys")
    repairs: dict[tuple[str, ...], tuple[dict[str, str], Path]] = {}
    for repair_path in args.repair:
        for row in read_rows(repair_path):
            row_key = key(row)
            if row_key not in set(primary_keys):
                raise ValueError(f"repair key is absent from primary table: {row_key}")
            if row.get("status") != "ok" or not row.get("mcap"):
                raise ValueError(f"repair row is not valid: {row_key}")
            if row_key in repairs:
                raise ValueError(f"duplicate repair key: {row_key}")
            repairs[row_key] = (row, repair_path)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    authoritative = []
    provenance = []
    for row in primary:
        row_key = key(row)
        if row_key in repairs:
            selected, source = repairs[row_key]
            authoritative.append(selected)
            provenance.append(
                {
                    **dict(zip(KEYS, row_key)),
                    "action": "replaced",
                    "primary_mcap": row.get("mcap", ""),
                    "selected_mcap": selected.get("mcap", ""),
                    "selected_source": str(source.resolve()),
                }
            )
        else:
            authoritative.append(row)
    write_rows(args.output_dir / "authoritative_results.csv", authoritative)
    write_rows(args.output_dir / "repair_provenance.csv", provenance)
    (args.output_dir / "composition_manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "primary": str(args.primary.resolve()),
                "repairs": [str(path.resolve()) for path in args.repair],
                "key_fields": list(KEYS),
                "primary_run_count": len(primary),
                "replacement_count": len(repairs),
                "authoritative_run_count": len(authoritative),
                "failed_source_preserved": True,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    if args.aggregate_csv:
        aggregate_rows = read_rows(args.aggregate_csv)
        if len(aggregate_rows) != len(authoritative):
            raise ValueError("aggregate row count does not match authoritative table")
        contract_rows: list[dict[str, object]] = []
        for row in aggregate_rows:
            contract_rows.append(
                {
                    **row,
                    "run_id": "__".join(key(row)),
                    "status": (
                        "ok"
                        if row.get("control_parse_status", "").startswith(
                            ("generated", "reused")
                        )
                        else "error"
                    ),
                }
            )
        bundle_dir = args.output_dir / "bundle"
        initialize_bundle(
            bundle_dir,
            experiment_id="r13_proxy_cable_authoritative_composite",
            runner="tools/compose_sweep_repair.py",
            argv=sys.argv,
            data_layer="pvs_proxy_mcap_with_explicit_repair_provenance",
            matrix={
                "scenario_count": 6,
                "seed_count": 3,
                "mode_count": 2,
                "run_count": len(contract_rows),
            },
            duration_s=60.0,
            config_paths=[
                args.primary,
                *args.repair,
                args.aggregate_csv,
                Path(__file__),
            ],
            extra_manifest={
                "failed_source_preserved": True,
                "replacement_count": len(repairs),
            },
        )
        finalize_bundle(bundle_dir, contract_rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

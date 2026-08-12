#!/usr/bin/env python3
"""Aggregate ES-EKF uncertainty/NIS metrics from a thesis sweep results.csv."""

from __future__ import annotations

import argparse
import csv
import json
import math
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path
from statistics import mean, stdev
from typing import Iterable, Sequence

import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[1]
UNCERTAINTY_TOOL = REPO_ROOT / "tools" / "uncertainty_metrics.py"
NAN = float("nan")
METRICS = [
    "nis_real_mean",
    "nis_real_p95",
    "nis_dvl_proxy_mean",
    "nis_depth_proxy_mean",
    "r_scale_mean",
    "r_scale_max",
    "r_scale_trigger_ratio",
    "p_trace_xy_mean",
    "p_trace_z_mean",
]
SOURCE_METRICS = [
    "nis_mean",
    "nis_p95",
    "nis_per_dof_mean",
    "coverage_95",
    "upper_exceed_ratio",
    "r_scale_trigger_ratio",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Batch aggregate uncertainty_metrics.py over sweep results.")
    parser.add_argument("--sweep-results", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--reuse", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--nis-window", type=int, default=50)
    return parser.parse_args()


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, fieldnames: Sequence[str], rows: Sequence[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: format_value(row.get(key, "")) for key in fieldnames})


def format_value(value: object) -> object:
    if isinstance(value, float):
        if math.isnan(value):
            return "nan"
        return f"{value:.6g}"
    return value


def to_float(value: object) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return NAN
    return number if math.isfinite(number) else NAN


def sanitize_component(value: object) -> str:
    text = str(value or "").strip()
    clean = "".join(ch if ch.isalnum() or ch in ("-", "_", ".") else "_" for ch in text)
    return clean.strip("_") or "item"


def finite(values: Iterable[float]) -> list[float]:
    return [float(value) for value in values if math.isfinite(float(value))]


def finite_column(rows: list[dict[str, object]], key: str) -> list[float]:
    return finite(to_float(row.get(key)) for row in rows)


def safe_mean(values: list[float]) -> float:
    return mean(values) if values else NAN


def safe_stdev(values: list[float]) -> float:
    return stdev(values) if len(values) >= 2 else 0.0


def safe_p95(values: list[float]) -> float:
    return float(np.percentile(np.asarray(values, dtype=float), 95)) if values else NAN


def read_uncertainty_timeseries(path: Path) -> dict[str, float]:
    if not path.is_file():
        return {metric: NAN for metric in METRICS}
    rows = read_csv_rows(path)
    nis_real = finite(to_float(row.get("nis_real")) for row in rows)
    nis_dvl = finite(to_float(row.get("nis_dvl")) for row in rows)
    nis_depth = finite(to_float(row.get("nis_depth")) for row in rows)
    r_scale = finite(to_float(row.get("r_scale")) for row in rows)
    p_xy = finite(to_float(row.get("p_trace_xy")) for row in rows)
    p_z = finite(to_float(row.get("p_trace_z")) for row in rows)
    return {
        "nis_real_mean": safe_mean(nis_real),
        "nis_real_p95": safe_p95(nis_real),
        "nis_dvl_proxy_mean": safe_mean(nis_dvl),
        "nis_depth_proxy_mean": safe_mean(nis_depth),
        "r_scale_mean": safe_mean(r_scale),
        "r_scale_max": max(r_scale) if r_scale else NAN,
        "r_scale_trigger_ratio": float(np.mean(np.asarray(r_scale) > 1.0 + 1e-6)) if r_scale else NAN,
        "p_trace_xy_mean": safe_mean(p_xy),
        "p_trace_z_mean": safe_mean(p_z),
    }


def to_bool(value: object) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes"}


def read_nis_event_metrics(path: Path) -> list[dict[str, object]]:
    if not path.is_file():
        return []
    grouped: dict[tuple[str, int], list[dict[str, str]]] = defaultdict(list)
    for row in read_csv_rows(path):
        source = str(row.get("source", "")).strip()
        try:
            dimension = int(row.get("dimension", "0"))
        except (TypeError, ValueError):
            continue
        if source and dimension > 0:
            grouped[(source, dimension)].append(row)

    summaries: list[dict[str, object]] = []
    for (source, dimension), rows in sorted(grouped.items()):
        nis = finite(to_float(row.get("nis")) for row in rows)
        nis_per_dof = finite(to_float(row.get("nis_per_dof")) for row in rows)
        r_scale = finite(to_float(row.get("r_scale_after_update")) for row in rows)
        summaries.append(
            {
                "source": source,
                "dimension": dimension,
                "event_count": len(nis),
                "nis_mean": safe_mean(nis),
                "nis_p95": safe_p95(nis),
                "nis_per_dof_mean": safe_mean(nis_per_dof),
                "coverage_95": (
                    float(np.mean([to_bool(row.get("in_two_sided_95")) for row in rows]))
                    if rows
                    else NAN
                ),
                "upper_exceed_ratio": (
                    float(np.mean([to_bool(row.get("above_upper_95")) for row in rows]))
                    if rows
                    else NAN
                ),
                "r_scale_trigger_ratio": (
                    float(np.mean(np.asarray(r_scale) > 1.0 + 1e-6))
                    if r_scale
                    else NAN
                ),
            }
        )
    return summaries


def run_uncertainty_tool(mcap: Path, out_dir: Path, nis_window: int, reuse: bool) -> tuple[str, str]:
    csv_path = out_dir / "uncertainty_timeseries.csv"
    nis_path = out_dir / "nis_events.csv"
    if reuse and csv_path.exists() and nis_path.exists():
        return "reused", ""
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable,
        str(UNCERTAINTY_TOOL),
        "--input",
        str(mcap),
        "--output-dir",
        str(out_dir),
        "--nis-window",
        str(nis_window),
    ]
    proc = subprocess.run(cmd, cwd=str(REPO_ROOT), text=True, capture_output=True, check=False)
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout).strip().splitlines()
        return "failed", detail[-1] if detail else f"uncertainty_metrics.py exit={proc.returncode}"
    return "generated", ""


def make_output_dir(args: argparse.Namespace) -> Path:
    if args.output_dir:
        return args.output_dir
    stamp = time.strftime("%Y%m%d_%H%M%S")
    return REPO_ROOT / "results" / "uncertainty_aggregates" / stamp


def main() -> int:
    args = parse_args()
    if not args.sweep_results.is_file():
        raise SystemExit(f"Missing sweep results: {args.sweep_results}")
    if not UNCERTAINTY_TOOL.is_file():
        raise SystemExit(f"Missing uncertainty tool: {UNCERTAINTY_TOOL}")

    output_dir = make_output_dir(args)
    per_run_root = output_dir / "per_run"
    source_rows = read_csv_rows(args.sweep_results)
    run_rows: list[dict[str, object]] = []
    nis_source_rows: list[dict[str, object]] = []

    for index, source in enumerate(source_rows):
        scenario = source.get("scenario", "")
        seed = source.get("seed", "")
        mode = source.get("mpc_mode", "")
        status = source.get("status", "")
        mcap_text = source.get("mcap", "")
        out_dir = per_run_root / f"{sanitize_component(scenario)}__seed{sanitize_component(seed)}__{sanitize_component(mode)}"
        row: dict[str, object] = {
            "scenario": scenario,
            "seed": seed,
            "mpc_mode": mode,
            "source_status": status,
            "mcap": mcap_text,
            "analysis_dir": str(out_dir),
            "uncertainty_status": "",
            "error": "",
        }
        if status != "ok":
            row["uncertainty_status"] = "skipped_source_not_ok"
            row["error"] = f"source status={status}"
            row.update({metric: NAN for metric in METRICS})
            run_rows.append(row)
            continue
        if not mcap_text:
            row["uncertainty_status"] = "skipped_no_mcap"
            row["error"] = "empty mcap column"
            row.update({metric: NAN for metric in METRICS})
            run_rows.append(row)
            continue
        mcap = Path(mcap_text)
        if not mcap.exists():
            row["uncertainty_status"] = "skipped_missing_mcap"
            row["error"] = f"mcap not found: {mcap}"
            row.update({metric: NAN for metric in METRICS})
            run_rows.append(row)
            continue

        print(f"[uncertainty-agg] ({index + 1}/{len(source_rows)}) {scenario} seed={seed} mode={mode}", flush=True)
        tool_status, error = run_uncertainty_tool(mcap, out_dir, args.nis_window, args.reuse)
        row["uncertainty_status"] = tool_status
        row["error"] = error
        row.update(read_uncertainty_timeseries(out_dir / "uncertainty_timeseries.csv") if not error else {metric: NAN for metric in METRICS})
        run_rows.append(row)
        if not error:
            for source_metrics in read_nis_event_metrics(out_dir / "nis_events.csv"):
                nis_source_rows.append(
                    {
                        "scenario": scenario,
                        "seed": seed,
                        "mpc_mode": mode,
                        "analysis_dir": str(out_dir),
                        **source_metrics,
                    }
                )

    run_fieldnames = [
        "scenario",
        "seed",
        "mpc_mode",
        "source_status",
        "mcap",
        "analysis_dir",
        "uncertainty_status",
        "error",
        *METRICS,
    ]
    write_csv(output_dir / "per_run_uncertainty_results.csv", run_fieldnames, run_rows)

    nis_source_fieldnames = [
        "scenario",
        "seed",
        "mpc_mode",
        "analysis_dir",
        "source",
        "dimension",
        "event_count",
        *SOURCE_METRICS,
    ]
    write_csv(
        output_dir / "per_run_nis_by_source.csv",
        nis_source_fieldnames,
        nis_source_rows,
    )

    groups: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    for row in run_rows:
        groups[(str(row.get("scenario", "")), str(row.get("mpc_mode", "")))].append(row)

    summary_rows: list[dict[str, object]] = []
    for (scenario, mode), group in sorted(groups.items()):
        ok_group = [row for row in group if row.get("uncertainty_status") in {"generated", "reused"} and not row.get("error")]
        summary: dict[str, object] = {
            "scenario": scenario,
            "mpc_mode": mode,
            "run_count": len(group),
            "ok_count": len(ok_group),
        }
        for metric in METRICS:
            vals = finite_column(ok_group, metric)
            summary[f"{metric}_mean"] = safe_mean(vals)
            summary[f"{metric}_std"] = safe_stdev(vals)
            summary[f"{metric}_available_count"] = len(vals)
        summary_rows.append(summary)

    summary_fieldnames = ["scenario", "mpc_mode", "run_count", "ok_count"]
    for metric in METRICS:
        summary_fieldnames.extend([f"{metric}_mean", f"{metric}_std", f"{metric}_available_count"])
    write_csv(output_dir / "summary_by_scenario_mode.csv", summary_fieldnames, summary_rows)

    source_groups: dict[
        tuple[str, str, str, int], list[dict[str, object]]
    ] = defaultdict(list)
    for row in nis_source_rows:
        source_groups[
            (
                str(row["scenario"]),
                str(row["mpc_mode"]),
                str(row["source"]),
                int(row["dimension"]),
            )
        ].append(row)
    source_summary_rows: list[dict[str, object]] = []
    for (scenario, mode, source, dimension), group in sorted(
        source_groups.items()
    ):
        summary: dict[str, object] = {
            "scenario": scenario,
            "mpc_mode": mode,
            "source": source,
            "dimension": dimension,
            "run_count": len(group),
            "event_count": sum(int(row["event_count"]) for row in group),
        }
        for metric in SOURCE_METRICS:
            values = finite_column(group, metric)
            summary[f"{metric}_mean"] = safe_mean(values)
            summary[f"{metric}_std"] = safe_stdev(values)
        source_summary_rows.append(summary)
    source_summary_fields = [
        "scenario",
        "mpc_mode",
        "source",
        "dimension",
        "run_count",
        "event_count",
    ]
    for metric in SOURCE_METRICS:
        source_summary_fields.extend([f"{metric}_mean", f"{metric}_std"])
    write_csv(
        output_dir / "summary_nis_by_scenario_source.csv",
        source_summary_fields,
        source_summary_rows,
    )

    report = [
        "# Uncertainty Aggregate Report",
        "",
        f"- Source sweep: `{args.sweep_results}`",
        f"- Output dir: `{output_dir}`",
        "",
        "## Standard NIS by source",
        "",
        "| scenario | mode | source | dof | runs | events | NIS/dof mean | 95% coverage | upper exceed | R trigger |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in source_summary_rows:
        report.append(
            "| {scenario} | {mode} | {source} | {dimension} | {runs} | {events} | "
            "{nis}±{nis_std} | {coverage}±{coverage_std} | "
            "{exceed}±{exceed_std} | {trigger}±{trigger_std} |".format(
                scenario=row["scenario"],
                mode=row["mpc_mode"],
                source=row["source"],
                dimension=row["dimension"],
                runs=row["run_count"],
                events=row["event_count"],
                nis=format_value(row["nis_per_dof_mean_mean"]),
                nis_std=format_value(row["nis_per_dof_mean_std"]),
                coverage=format_value(row["coverage_95_mean"]),
                coverage_std=format_value(row["coverage_95_std"]),
                exceed=format_value(row["upper_exceed_ratio_mean"]),
                exceed_std=format_value(row["upper_exceed_ratio_std"]),
                trigger=format_value(row["r_scale_trigger_ratio_mean"]),
                trigger_std=format_value(row["r_scale_trigger_ratio_std"]),
            )
        )
    report.extend(
        [
            "",
            "## Semantic audit",
            "",
            "- Standard NIS is reported only at measurement updates and is split by source and dimension.",
            "- `nis_dvl_proxy` and `nis_depth_proxy` remain non-standard diagnostics and are not used for chi-square claims.",
            "- The current ES-EKF adaptive-R window mixes 3-D DVL and 1-D depth raw NIS, then compares the mixed mean with `nis_threshold=9.0`.",
            "- Therefore the historical adaptive-R trigger can be described operationally, but not as a valid chi-square consistency decision.",
        ]
    )
    (output_dir / "aggregate_report.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    audit = {
        "schema_version": 1,
        "standard_nis_source": "per_run/*/nis_events.csv",
        "standard_nis_split_by_source_and_dimension": True,
        "proxy_used_for_chi_square_claims": False,
        "adaptive_r_semantics_valid": False,
        "blocking_reason": (
            "algorithm/es_ekf.py pools raw NIS from dimensions 3 and 1 in "
            "one window and compares their mean against a fixed threshold 9.0"
        ),
        "allowed_claim": (
            "adaptive R was operationally triggered; source-specific NIS "
            "distributions and chi-square coverage are separately auditable"
        ),
        "disallowed_claim": (
            "the historical adaptive-R trigger is a calibrated 95 percent "
            "chi-square consistency test"
        ),
    }
    (output_dir / "nis_semantic_audit.json").write_text(
        json.dumps(audit, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"[uncertainty-agg] wrote {output_dir / 'summary_by_scenario_mode.csv'}", flush=True)
    print(f"[uncertainty-agg] wrote {output_dir / 'aggregate_report.md'}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

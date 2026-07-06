#!/usr/bin/env python3
"""Aggregate multiple cable inspection summaries into an acceptance report."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import statistics
import sys
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("runs", nargs="+", type=Path, help="inspection_summary.json files or report directories")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--min-runs", type=int, default=3)
    parser.add_argument("--min-pass-ratio", type=float, default=0.67)
    return parser.parse_args()


def _resolve(path: Path) -> Path:
    return path if path.is_absolute() else PROJECT_ROOT / path


def _summary_path(path: Path) -> Path:
    resolved = _resolve(path)
    if resolved.is_dir():
        return resolved / "inspection_summary.json"
    return resolved


def _read_summary(path: Path) -> dict[str, Any]:
    summary_path = _summary_path(path)
    data = json.loads(summary_path.read_text(encoding="utf-8"))
    data["_summary_path"] = str(summary_path)
    data["_run_dir"] = str(summary_path.parent)
    return data


def _mean(values: list[float]) -> float | None:
    return statistics.fmean(values) if values else None


def _max(values: list[float]) -> float | None:
    return max(values) if values else None


def _min(values: list[float]) -> float | None:
    return min(values) if values else None


def _float_field(rows: list[dict[str, Any]], key: str) -> list[float]:
    values = []
    for row in rows:
        value = row.get(key)
        if value is not None:
            values.append(float(value))
    return values


def _run_row(summary: dict[str, Any], index: int) -> dict[str, Any]:
    checks = summary.get("acceptance_checks") or {}
    failed_checks = [key for key, value in checks.items() if not bool(value)]
    return {
        "run_index": index,
        "summary_path": summary.get("_summary_path"),
        "readiness": summary.get("industrial_conclusion_readiness"),
        "industrial_acceptance_pass": bool(summary.get("industrial_acceptance_pass", False)),
        "point_count": summary.get("point_count"),
        "max_route_offset_m": summary.get("max_route_offset_m"),
        "mean_route_offset_m": summary.get("mean_route_offset_m"),
        "route_offset_p95_m": summary.get("route_offset_p95_m"),
        "confidence_p05": summary.get("confidence_p05"),
        "valid_burial_ratio": summary.get("valid_burial_ratio"),
        "data_quality_flags": ",".join(summary.get("data_quality_flags") or []),
        "failed_acceptance_checks": ",".join(failed_checks),
        "failed_check_count": len(failed_checks),
    }


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = list(rows[0].keys()) if rows else ["run_index"]
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def main() -> None:
    args = parse_args()
    output_dir = _resolve(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    summaries = [_read_summary(path) for path in args.runs]
    run_rows = [_run_row(summary, index + 1) for index, summary in enumerate(summaries)]

    run_count = len(run_rows)
    pass_count = sum(1 for row in run_rows if row["industrial_acceptance_pass"])
    pass_ratio = pass_count / run_count if run_count else 0.0
    readiness_distribution: dict[str, int] = {}
    for row in run_rows:
        readiness = str(row.get("readiness") or "unknown")
        readiness_distribution[readiness] = readiness_distribution.get(readiness, 0) + 1

    worst_row = max(
        run_rows,
        key=lambda row: (
            int(row.get("failed_check_count") or 0),
            float(row.get("max_route_offset_m") or 0.0),
        ),
        default=None,
    )
    aggregate = {
        "run_count": run_count,
        "pass_count": pass_count,
        "pass_ratio": pass_ratio,
        "min_runs": int(args.min_runs),
        "min_pass_ratio": float(args.min_pass_ratio),
        "preliminary_acceptance_ready": run_count >= int(args.min_runs) and pass_ratio >= float(args.min_pass_ratio),
        "readiness_distribution": readiness_distribution,
        "worst_run": worst_row,
        "max_route_offset_m_mean": _mean(_float_field(run_rows, "max_route_offset_m")),
        "max_route_offset_m_max": _max(_float_field(run_rows, "max_route_offset_m")),
        "route_offset_p95_m_mean": _mean(_float_field(run_rows, "route_offset_p95_m")),
        "route_offset_p95_m_max": _max(_float_field(run_rows, "route_offset_p95_m")),
        "valid_burial_ratio_min": _min(_float_field(run_rows, "valid_burial_ratio")),
        "confidence_p05_min": _min(_float_field(run_rows, "confidence_p05")),
        "runs": run_rows,
    }

    _write_csv(output_dir / "acceptance_runs_summary.csv", run_rows)
    (output_dir / "acceptance_runs_summary.json").write_text(
        json.dumps(aggregate, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    lines = [
        "# Cable Acceptance Multi-run Report",
        "",
        f"- Run count: {run_count}",
        f"- Pass count: {pass_count}",
        f"- Pass ratio: {pass_ratio:.3f}",
        f"- Required runs: {args.min_runs}",
        f"- Required pass ratio: {args.min_pass_ratio:.3f}",
        f"- Preliminary acceptance ready: {aggregate['preliminary_acceptance_ready']}",
        f"- Readiness distribution: {readiness_distribution}",
        "",
        "## Aggregate Metrics",
        f"- Mean max route offset: {aggregate['max_route_offset_m_mean']}",
        f"- Worst max route offset: {aggregate['max_route_offset_m_max']}",
        f"- Mean route offset p95: {aggregate['route_offset_p95_m_mean']}",
        f"- Worst route offset p95: {aggregate['route_offset_p95_m_max']}",
        f"- Minimum valid burial ratio: {aggregate['valid_burial_ratio_min']}",
        f"- Minimum confidence p05: {aggregate['confidence_p05_min']}",
        "",
        "## Runs",
    ]
    for row in run_rows:
        lines.append(
            "- run {run_index}: pass={industrial_acceptance_pass}, readiness={readiness}, "
            "failed={failed_acceptance_checks}, summary={summary_path}".format(**row)
        )
    (output_dir / "acceptance_runs_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[OK] wrote aggregate acceptance report to {output_dir}")


if __name__ == "__main__":
    main()

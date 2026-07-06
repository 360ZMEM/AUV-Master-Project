#!/usr/bin/env python3
"""Generate operator-facing cable inspection image products from a report dir."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import sys
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--burial-target-m", type=float, default=1.5)
    parser.add_argument("--route-offset-target-m", type=float, default=2.0)
    parser.add_argument("--sigma-target-m", type=float, default=0.15)
    return parser.parse_args()


def _resolve(path: Path) -> Path:
    return path if path.is_absolute() else PROJECT_ROOT / path


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise SystemExit(f"missing CSV: {path}")
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _float(value: Any, default: float = 0.0) -> float:
    if value in (None, ""):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _bool(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def _ascii_label(value: Any) -> str:
    text = str(value)
    mapping = {
        "正常状态": "normal",
        "注意状态": "attention",
        "异常状态": "abnormal",
        "严重状态": "severe",
        "无效数据": "invalid data",
        "海缆位移": "cable displacement",
        "海缆埋深不足": "insufficient burial depth",
        "埋深估计精度未达 0.15m": "burial accuracy above 0.15m",
    }
    return mapping.get(text, text.encode("ascii", "ignore").decode("ascii") or "non-ascii item")


def _valid_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    valid = [row for row in rows if _bool(row.get("inspection_window_valid"))]
    return valid if valid else rows


def _series(rows: list[dict[str, str]], key: str) -> list[float]:
    return [_float(row.get(key)) for row in rows]


def _optional_series(rows: list[dict[str, str]], key: str) -> list[float | None]:
    values: list[float | None] = []
    for row in rows:
        raw = row.get(key)
        values.append(None if raw in (None, "") else _float(raw))
    return values


def _save_manifest(output_dir: Path, summary: dict[str, Any], files: list[str], report_dir: Path) -> None:
    manifest = {
        "source_report_dir": str(report_dir),
        "generated_files": files,
        "operator_status": {
            "industrial_conclusion_readiness": summary.get("industrial_conclusion_readiness"),
            "industrial_acceptance_pass": summary.get("industrial_acceptance_pass"),
            "dlt1278_state": summary.get("state"),
            "total_score": summary.get("total_score"),
            "worst_single_score": summary.get("worst_single_score"),
        },
    }
    (output_dir / "operator_products_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def main() -> None:
    args = parse_args()
    report_dir = _resolve(args.report_dir)
    output_dir = _resolve(args.output_dir) if args.output_dir else report_dir / "operator_view"
    output_dir.mkdir(parents=True, exist_ok=True)

    summary_path = report_dir / "inspection_summary.json"
    if not summary_path.is_file():
        raise SystemExit(f"missing inspection summary: {summary_path}")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))

    ops_rows = _read_csv(report_dir / "cable_ops_points.csv")
    burial_rows = _read_csv(report_dir / "burial_profile.csv")
    route_rows = _read_csv(report_dir / "route_deviation.csv")
    valid_ops = _valid_rows(ops_rows)
    valid_burial = _valid_rows(burial_rows)
    valid_route = _valid_rows(route_rows)

    try:
        import matplotlib.pyplot as plt  # type: ignore
    except Exception as exc:
        raise SystemExit(f"matplotlib unavailable: {exc}") from exc

    generated: list[str] = []

    x = _series(valid_ops, "x_m")
    y = _series(valid_ops, "y_m")
    progress = _series(valid_ops, "route_progress_m")
    plt.figure(figsize=(8, 5))
    scatter = plt.scatter(x, y, c=progress, s=18, cmap="viridis", label="accepted inspection points")
    plt.colorbar(scatter, label="route progress m")
    all_x = _series(ops_rows, "x_m")
    all_y = _series(ops_rows, "y_m")
    excluded_x = [px for row, px in zip(ops_rows, all_x) if not _bool(row.get("inspection_window_valid"))]
    excluded_y = [py for row, py in zip(ops_rows, all_y) if not _bool(row.get("inspection_window_valid"))]
    if excluded_x:
        plt.scatter(excluded_x, excluded_y, s=8, color="lightgray", label="excluded/warmup/end samples")
    plt.xlabel("local x m")
    plt.ylabel("local y m")
    plt.title("Operator Cable Map")
    plt.grid(True, alpha=0.3)
    plt.axis("equal")
    plt.legend(loc="best")
    plt.tight_layout()
    out = output_dir / "01_operator_cable_map.png"
    plt.savefig(out, dpi=180)
    plt.close()
    generated.append(out.name)

    progress_b = _series(valid_burial, "route_progress_m")
    burial = _optional_series(valid_burial, "burial_depth_m")
    sigma = _optional_series(valid_burial, "burial_sigma_m")
    plt.figure(figsize=(9, 4.5))
    plt.plot(progress_b, [v if v is not None else float("nan") for v in burial], label="burial depth m", linewidth=2)
    plt.axhline(args.burial_target_m, color="tab:orange", linestyle="--", label="burial target")
    if any(v is not None for v in sigma):
        plt.plot(progress_b, [v if v is not None else float("nan") for v in sigma], label="burial sigma m", alpha=0.8)
        plt.axhline(args.sigma_target_m, color="tab:red", linestyle="--", label="sigma target")
    plt.xlabel("route progress m")
    plt.ylabel("m")
    plt.title("Operator Burial Strip")
    plt.grid(True, alpha=0.3)
    plt.legend(loc="best")
    plt.tight_layout()
    out = output_dir / "02_operator_burial_strip.png"
    plt.savefig(out, dpi=180)
    plt.close()
    generated.append(out.name)

    progress_r = _series(valid_route, "route_progress_m")
    abs_offset = _series(valid_route, "abs_cross_track_m")
    plt.figure(figsize=(9, 4.5))
    plt.plot(progress_r, abs_offset, label="absolute route offset m", linewidth=2)
    plt.axhline(args.route_offset_target_m, color="tab:red", linestyle="--", label="route offset target")
    plt.fill_between(progress_r, 0, abs_offset, alpha=0.2)
    plt.xlabel("route progress m")
    plt.ylabel("m")
    plt.title("Operator Route Deviation")
    plt.grid(True, alpha=0.3)
    plt.legend(loc="best")
    plt.tight_layout()
    out = output_dir / "03_operator_route_deviation.png"
    plt.savefig(out, dpi=180)
    plt.close()
    generated.append(out.name)

    checks = summary.get("acceptance_checks") or {}
    score_items = summary.get("score_items") or []
    score_lines = [
        f"  {_ascii_label(item.get('item'))} | {item.get('level')} | score {item.get('score')}"
        for item in score_items
    ] or ["  none"]
    plt.figure(figsize=(9, 5))
    ax = plt.gca()
    ax.axis("off")
    lines = [
        "Cable Inspection Operator Summary",
        "",
        f"Readiness: {summary.get('industrial_conclusion_readiness')}",
        f"Acceptance pass: {summary.get('industrial_acceptance_pass')}",
        f"DL/T-style state: {_ascii_label(summary.get('state'))}",
        f"Total score: {summary.get('total_score')}    Worst single: {summary.get('worst_single_score')}",
        f"Valid samples: {summary.get('point_count')} / {summary.get('inspection_window', {}).get('raw_point_count')}",
        f"Start health: {summary.get('start_health', {}).get('pass')}",
        f"Burial sigma over-limit ratio: {summary.get('burial_sigma_over_limit_ratio'):.4f}",
        "",
        "Acceptance checks:",
        *[f"  {'PASS' if value else 'FAIL'}  {key}" for key, value in checks.items()],
        "",
        "DL/T-style score items:",
        *score_lines,
    ]
    ax.text(0.02, 0.98, "\n".join(lines), va="top", ha="left", family="monospace", fontsize=10)
    plt.tight_layout()
    out = output_dir / "04_operator_acceptance_summary.png"
    plt.savefig(out, dpi=180)
    plt.close()
    generated.append(out.name)

    _save_manifest(output_dir, summary, generated, report_dir)
    print(f"[OK] wrote operator products to {output_dir}")


if __name__ == "__main__":
    main()

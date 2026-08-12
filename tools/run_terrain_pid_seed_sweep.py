#!/usr/bin/env python3
"""Run terrain-following over multiple terrain seeds and aggregate results."""

from __future__ import annotations

import argparse
import csv
import math
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from statistics import mean, stdev
from typing import Iterable

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

RUNNER = REPO_ROOT / "scripts" / "run_terrain_benchmark.sh"
TERRAIN_CFGS = {
    "low": REPO_ROOT / "config" / "bridge_params.protocol_udp.pvs.terrain_low.yaml",
    "mid": REPO_ROOT / "config" / "bridge_params.protocol_udp.pvs.terrain_mid.yaml",
    "high": REPO_ROOT / "config" / "bridge_params.protocol_udp.pvs.terrain_high.yaml",
}
METRIC_NAMES = [
    "duration_s",
    "clearance_source",
    "seabed_clearance_rmse_to_3m",
    "seabed_clearance_mean_m",
    "seabed_clearance_std_m",
    "seabed_clearance_min_m",
    "seabed_clearance_safety_violation_ratio_1p5m",
    "seabed_penetration_ratio",
    "depth_error_rmse_diag_m",
    "solve_time_p95_ms",
    "solver_fallback_ratio",
    "solver_status_sample_count",
    "estimated_sample_count",
    "diagnostics_sample_count",
]
CBF_METRIC_NAMES = [
    "controller_debug_samples",
    "cbf_enabled_samples",
    "cbf_active_samples",
    "cbf_active_ratio",
    "cbf_speed_scale_min",
    "cbf_speed_scale_max",
    "cbf_filtered_speed_min_mps",
    "cbf_filtered_speed_max_mps",
    "target_depth_min_m",
    "target_depth_max_m",
    "current_depth_min_m",
    "current_depth_max_m",
    "cbf_reasons_json",
]


def parse_csv_list(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def parse_int_list(value: str) -> list[int]:
    return [int(item) for item in parse_csv_list(value)]


def parse_controller_list(value: str) -> list[str]:
    raw = parse_csv_list(value)
    controllers: list[str] = []
    for item in raw:
        if item == "both":
            controllers.extend(["pid", "mpc"])
        else:
            controllers.append(item)
    invalid = [item for item in controllers if item not in {"pid", "mpc"}]
    if invalid:
        raise argparse.ArgumentTypeError(
            f"Unknown controller(s): {','.join(invalid)}; choices: pid,mpc,both"
        )
    deduped: list[str] = []
    for item in controllers:
        if item not in deduped:
            deduped.append(item)
    return deduped


def read_summary_statistics(path: Path) -> dict[str, object]:
    metrics: dict[str, object] = {}
    if not path.is_file():
        return metrics
    with path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            key = row.get("metric", "")
            raw = row.get("value", "")
            if not key:
                continue
            try:
                metrics[key] = float(raw)
            except (TypeError, ValueError):
                metrics[key] = raw
    return metrics


def latest_output_dir(stdout: str) -> Path | None:
    matches = re.findall(r"Results:\s*(\S+)", stdout)
    if not matches:
        return None
    candidate = Path(matches[-1])
    return candidate if candidate.exists() else None


def find_mcap(root: Path | None) -> Path | None:
    if root is None or not root.exists():
        return None
    matches = sorted(root.rglob("*.mcap"))
    return matches[0] if matches else None


def find_phase_mcap(phase_dir: Path | None) -> Path | None:
    if phase_dir is None:
        return None
    bag_path_file = phase_dir / "bag_path.txt"
    if bag_path_file.is_file():
        bag_dir = Path(bag_path_file.read_text(encoding="utf-8").strip())
        found = find_mcap(bag_dir)
        if found:
            return found
    return find_mcap(phase_dir)


def safe_stdev(values: list[float]) -> float:
    return stdev(values) if len(values) >= 2 else 0.0


def finite_values(rows: Iterable[dict[str, object]], key: str) -> list[float]:
    vals: list[float] = []
    for row in rows:
        try:
            value = float(row.get(key, float("nan")))
        except (TypeError, ValueError):
            continue
        if math.isfinite(value):
            vals.append(value)
    return vals


def finite_min(rows: Iterable[dict[str, object]], key: str) -> float:
    values = finite_values(rows, key)
    return min(values) if values else float("nan")


def finite_max(rows: Iterable[dict[str, object]], key: str) -> float:
    values = finite_values(rows, key)
    return max(values) if values else float("nan")


def fmt(value: object) -> object:
    if isinstance(value, float):
        if math.isnan(value):
            return "nan"
        return f"{value:.6g}"
    return value


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: fmt(row.get(key, "")) for key in fieldnames})


def make_seed_config(base_path: Path, out_path: Path, terrain: str, seed: int) -> None:
    with base_path.open("r", encoding="utf-8") as handle:
        cfg = yaml.safe_load(handle) or {}
    cfg.setdefault("stage", {})["name"] = f"auv_zenoh_bridge_pvs_protocol_udp_terrain_{terrain}_seed{seed}"
    cfg.setdefault("digital_twin", {})["terrain_seed"] = int(seed)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(cfg, handle, sort_keys=False, allow_unicode=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Terrain controller multi-seed sweep.")
    parser.add_argument(
        "--controllers",
        type=parse_controller_list,
        default=["pid"],
        help="Comma-separated controllers to run: pid,mpc,both. Default preserves legacy PID-only behavior.",
    )
    parser.add_argument("--terrains", default="low,mid,high")
    parser.add_argument("--seeds", default="0,1,2")
    parser.add_argument("--duration", type=int, default=30)
    parser.add_argument("--label", default="terrain_3seed")
    parser.add_argument("--output-root", type=Path, default=REPO_ROOT / "results" / "control")
    parser.add_argument("--bag-finalize-s", type=int, default=60)
    parser.add_argument(
        "--manual-setpoint",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Enable the manual terrain setpoint driver used by the CBF matrix.",
    )
    parser.add_argument(
        "--include-cbf-debug",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Extract /auv/controller/debug CBF diagnostics from each MCAP.",
    )
    parser.add_argument(
        "--skip-prebuild-after-first",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Set AUV_BENCHMARK_SKIP_PREBUILD=1 after the first run.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    controllers = list(args.controllers)
    terrains = parse_csv_list(args.terrains)
    seeds = parse_int_list(args.seeds)
    for terrain in terrains:
        if terrain not in TERRAIN_CFGS:
            raise SystemExit(f"Unknown terrain {terrain!r}; choices: {','.join(TERRAIN_CFGS)}")
        if not TERRAIN_CFGS[terrain].is_file():
            raise SystemExit(f"Missing terrain config: {TERRAIN_CFGS[terrain]}")
    if not RUNNER.is_file():
        raise SystemExit(f"Missing runner: {RUNNER}")

    stamp = time.strftime("%Y%m%d_%H%M%S")
    output_dir = args.output_root / f"terrain_controller_seed_sweep_{stamp}_{args.label}"
    config_dir = output_dir / "configs"
    log_dir = output_dir / "logs"
    config_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, object]] = []
    first_run = True
    total = len(controllers) * len(terrains) * len(seeds)
    idx = 0
    for controller in controllers:
        for terrain in terrains:
            for seed in seeds:
                idx += 1
                cfg_path = config_dir / f"{terrain}_seed{seed}.yaml"
                if not cfg_path.exists():
                    make_seed_config(TERRAIN_CFGS[terrain], cfg_path, terrain, seed)
                log_path = log_dir / f"{controller}_{terrain}_seed{seed}.log"
                phase_name = f"{controller}_terrain"
                cmd = [
                    "bash",
                    str(RUNNER),
                    str(args.duration),
                    controller,
                    "terrain",
                    str(cfg_path),
                ]
                print(
                    f"[terrain-seed] ({idx}/{total}) controller={controller} terrain={terrain} seed={seed}",
                    flush=True,
                )
                env = os.environ.copy()
                if args.skip_prebuild_after_first and not first_run:
                    env["AUV_BENCHMARK_SKIP_PREBUILD"] = "1"
                if args.manual_setpoint:
                    env["AUV_TERRAIN_MANUAL_SETPOINT"] = "true"
                env["BAG_FINALIZE_S"] = str(args.bag_finalize_s)
                t0 = time.time()
                proc = subprocess.run(
                    cmd,
                    cwd=str(REPO_ROOT),
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    env=env,
                    check=False,
                )
                first_run = False
                elapsed = time.time() - t0
                log_path.write_text(proc.stdout, encoding="utf-8", errors="replace")
                result_dir = latest_output_dir(proc.stdout)
                phase_dir = result_dir / phase_name if result_dir else None
                analysis_dir = phase_dir / "analysis" if phase_dir else None
                summary_path = analysis_dir / "summary_statistics.csv" if analysis_dir else None
                metrics = read_summary_statistics(summary_path) if summary_path else {}
                mcap = find_phase_mcap(phase_dir)
                status = "ok" if proc.returncode == 0 and metrics else "failed"
                cbf_metrics: dict[str, object] = {}
                if args.include_cbf_debug and mcap and Path(mcap).is_file():
                    try:
                        from tools.summarize_cbf_terrain_recheck import extract_debug_metrics

                        cbf_metrics = extract_debug_metrics(Path(mcap))
                    except Exception as exc:  # pragma: no cover - diagnostics only
                        cbf_metrics = {
                            key: float("nan") for key in CBF_METRIC_NAMES if key != "cbf_reasons_json"
                        }
                        cbf_metrics["cbf_reasons_json"] = "{}"
                        status = "failed" if status != "ok" else "ok"
                        print(
                            f"[terrain-seed][WARN] CBF debug extraction failed for {phase_name} {terrain} seed={seed}: {exc}",
                            flush=True,
                        )
                row: dict[str, object] = {
                    "controller": controller,
                    "terrain": terrain,
                    "seed": seed,
                    "status": status,
                    "exit_code": proc.returncode,
                    "duration_s_actual": elapsed,
                    "manual_setpoint": bool(args.manual_setpoint),
                    "config": str(cfg_path),
                    "result_dir": str(result_dir or ""),
                    "phase_dir": str(phase_dir or ""),
                    "analysis_dir": str(analysis_dir or ""),
                    "mcap": str(mcap or ""),
                    "log": str(log_path),
                    "error": "" if status == "ok" else "missing summary_statistics.csv or runner failed",
                }
                for metric in METRIC_NAMES:
                    row[metric] = metrics.get(metric, float("nan"))
                for metric in CBF_METRIC_NAMES:
                    row[metric] = cbf_metrics.get(metric, float("nan"))
                rows.append(row)
                print(
                    f"[terrain-seed] finished controller={controller} terrain={terrain} seed={seed} status={status}",
                    flush=True,
                )

    run_fieldnames = [
        "controller",
        "terrain",
        "seed",
        "status",
        "exit_code",
        "duration_s_actual",
        "manual_setpoint",
        "config",
        "result_dir",
        "phase_dir",
        "analysis_dir",
        "mcap",
        "log",
        "error",
        *METRIC_NAMES,
        *CBF_METRIC_NAMES,
    ]
    write_csv(output_dir / "results.csv", run_fieldnames, rows)

    summary_rows: list[dict[str, object]] = []
    for controller in controllers:
        for terrain in terrains:
            group = [
                row
                for row in rows
                if row["controller"] == controller and row["terrain"] == terrain
            ]
            ok_group = [row for row in group if row["status"] == "ok"]
            summary: dict[str, object] = {
                "controller": controller,
                "terrain": terrain,
                "run_count": len(group),
                "ok_count": len(ok_group),
                "clearance_min_min_m": finite_min(ok_group, "seabed_clearance_min_m"),
                "violation_ratio_max": finite_max(
                    ok_group, "seabed_clearance_safety_violation_ratio_1p5m"
                ),
                "penetration_ratio_max": finite_max(ok_group, "seabed_penetration_ratio"),
                "cbf_speed_scale_min": finite_min(ok_group, "cbf_speed_scale_min"),
                "cbf_active_ratio_mean": (
                    mean(finite_values(ok_group, "cbf_active_ratio"))
                    if finite_values(ok_group, "cbf_active_ratio")
                    else float("nan")
                ),
                "solve_time_p95_ms_max": finite_max(ok_group, "solve_time_p95_ms"),
                "solver_fallback_ratio_max": finite_max(ok_group, "solver_fallback_ratio"),
            }
            for metric in METRIC_NAMES:
                vals = finite_values(ok_group, metric)
                summary[f"{metric}_mean"] = mean(vals) if vals else float("nan")
                summary[f"{metric}_std"] = safe_stdev(vals)
                summary[f"{metric}_min"] = min(vals) if vals else float("nan")
                summary[f"{metric}_max"] = max(vals) if vals else float("nan")
                summary[f"{metric}_available_count"] = len(vals)
            for metric in CBF_METRIC_NAMES:
                vals = finite_values(ok_group, metric)
                if vals:
                    summary[f"{metric}_mean"] = mean(vals)
                    summary[f"{metric}_min"] = min(vals)
                    summary[f"{metric}_max"] = max(vals)
                    summary[f"{metric}_available_count"] = len(vals)
            summary_rows.append(summary)

    summary_fieldnames = [
        "controller",
        "terrain",
        "run_count",
        "ok_count",
        "clearance_min_min_m",
        "violation_ratio_max",
        "penetration_ratio_max",
        "cbf_speed_scale_min",
        "cbf_active_ratio_mean",
        "solve_time_p95_ms_max",
        "solver_fallback_ratio_max",
    ]
    for metric in METRIC_NAMES:
        summary_fieldnames.extend(
            [
                f"{metric}_mean",
                f"{metric}_std",
                f"{metric}_min",
                f"{metric}_max",
                f"{metric}_available_count",
            ]
        )
    for metric in CBF_METRIC_NAMES:
        summary_fieldnames.extend(
            [f"{metric}_mean", f"{metric}_min", f"{metric}_max", f"{metric}_available_count"]
        )
    write_csv(output_dir / "summary_by_terrain.csv", summary_fieldnames, summary_rows)

    lines = [
        "# Terrain Controller Seed Sweep Aggregate Report",
        "",
        f"- Source: `{output_dir}`",
        f"- Controllers: `{','.join(controllers)}`",
        f"- Terrains: `{','.join(terrains)}`",
        f"- Seeds: `{','.join(str(s) for s in seeds)}`",
        f"- Duration per run: `{args.duration}s`",
        f"- Manual setpoint: `{bool(args.manual_setpoint)}`",
        "",
        "| controller | terrain | ok/total | min clearance min | violation max | penetration max | CBF active mean | speed scale min | solver p95 max | fallback max |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in summary_rows:
        ok_total = f"{row['ok_count']}/{row['run_count']}"
        lines.append(
            "| {controller} | {terrain} | {ok_total} | {min_clearance} | {viol} | {penetration} | {active} | {speed_scale} | {p95} | {fallback} |".format(
                controller=row["controller"],
                terrain=row["terrain"],
                ok_total=ok_total,
                min_clearance=fmt(row["clearance_min_min_m"]),
                viol=fmt(row["violation_ratio_max"]),
                penetration=fmt(row["penetration_ratio_max"]),
                active=fmt(row["cbf_active_ratio_mean"]),
                speed_scale=fmt(row["cbf_speed_scale_min"]),
                p95=fmt(row["solve_time_p95_ms_max"]),
                fallback=fmt(row["solver_fallback_ratio_max"]),
            )
        )
    lines.extend(
        [
            "",
            "Boundary: manual-setpoint terrain runs use the kinematic setpoint proxy and do not validate native PVS depthHeadingAutopilot, full cable extreme scenarios, or physical hardware timing.",
        ]
    )
    (output_dir / "aggregate_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[terrain-seed] wrote {output_dir / 'results.csv'}", flush=True)
    print(f"[terrain-seed] wrote {output_dir / 'aggregate_report.md'}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

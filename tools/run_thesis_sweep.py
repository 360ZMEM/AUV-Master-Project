#!/usr/bin/env python3
"""Thesis experiment sweep driver.

Runs `scripts/start_experiment.sh` over the cartesian product of
(scenario yaml, seed, mpc_mode), then invokes `tools/offline_ekf_benchmark.py`
on the resulting bag and aggregates RMSE/CEP50/control-smoothness into a CSV.

Designed for the multi-condition experiments referenced in
`docs/thesis/04_mpc_robustness_ablation.md` and `docs/thesis/02_es_ekf_validation.md`.

Single-run failures do NOT abort the sweep — they are logged to `failures.log`
inside the sweep output directory and the harness keeps going.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.experiment_contract import finalize_bundle, initialize_bundle  # noqa: E402
from tools.aggregate_control_metrics import (  # noqa: E402
    enrich_contract_rows_with_control_diagnostics,
)

SCENARIOS_DIR = REPO_ROOT / "scenarios"
START_SCRIPT = REPO_ROOT / "scripts" / "start_experiment.sh"
BENCH_TOOL = REPO_ROOT / "tools" / "offline_ekf_benchmark.py"


# ---------------------------------------------------------------------------
# Scenario discovery
# ---------------------------------------------------------------------------
def resolve_scenario(name_or_path: str) -> Path:
    """Resolve a scenario reference to an absolute yaml path.

    Accepts either:
      - bare id like "baseline" or "dvl_dropout_30" → maps to
        scenarios/scenario_<id>.yaml
      - full file path
    """
    p = Path(name_or_path)
    if p.is_file():
        return p.resolve()
    candidate = SCENARIOS_DIR / f"scenario_{name_or_path}.yaml"
    if candidate.is_file():
        return candidate.resolve()
    candidate2 = SCENARIOS_DIR / name_or_path
    if candidate2.is_file():
        return candidate2.resolve()
    raise FileNotFoundError(
        f"Scenario '{name_or_path}' not found. Looked at: {p}, {candidate}, {candidate2}"
    )


# ---------------------------------------------------------------------------
# Run-dir discovery
# ---------------------------------------------------------------------------
def parse_run_dir_from_log(log_text: str) -> Path | None:
    """start_experiment.sh prints `[AUV] experiment directory: <path>`."""
    m = re.search(r"\[AUV\] experiment directory:\s*(\S+)", log_text)
    if not m:
        return None
    return Path(m.group(1))


def find_mcap_in(run_dir: Path) -> Path | None:
    candidates = sorted(run_dir.rglob("*.mcap"))
    return candidates[0] if candidates else None


# ---------------------------------------------------------------------------
# Metric extraction from benchmark_results.md
# ---------------------------------------------------------------------------
def parse_benchmark_results(md_path: Path) -> dict[str, float]:
    """Best-effort regex extraction of key metrics from benchmark_results.md.

    The benchmark tool's report format is markdown; we only care about
    es_ekf row (preferred, since it's the thesis main filter).
    Missing values become NaN.
    """
    out = {
        "xy_rmse": float("nan"),
        "z_rmse": float("nan"),
        "cep50": float("nan"),
        "max_drift": float("nan"),
    }
    if not md_path.is_file():
        return out
    try:
        text = md_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return out
    # Look for a row whose first non-empty cell is "ES EKF" or "ES-EKF"
    row_pat = re.compile(
        r"^\s*\|\s*ES[\s\-_]*EKF\s*\|"
        r"\s*([0-9eE.+\-]+)\s*m?\s*\|"
        r"\s*([0-9eE.+\-]+)\s*m?\s*\|"
        r"\s*([0-9eE.+\-]+)\s*m?\s*\|"
        r"\s*([0-9eE.+\-]+)\s*m?\s*\|",
        re.IGNORECASE | re.MULTILINE,
    )
    m = row_pat.search(text)
    if m:
        try:
            out["xy_rmse"] = float(m.group(1))
            out["z_rmse"] = float(m.group(2))
            out["cep50"] = float(m.group(3))
            out["max_drift"] = float(m.group(4))
        except ValueError:
            pass
    return out


# ---------------------------------------------------------------------------
# Run dataclass
# ---------------------------------------------------------------------------
@dataclass
class RunSpec:
    scenario_name: str
    scenario_path: Path
    seed: int
    mpc_mode: str
    duration_s: int


@dataclass
class RunResult:
    spec: RunSpec
    run_dir: Path | None
    mcap: Path | None
    metrics: dict[str, float]
    benchmark_dir: Path | None
    duration_s_actual: float
    status: str  # "ok" | "start_failed" | "no_bag" | "bag_empty" | "bench_failed"
    error: str | None


# ---------------------------------------------------------------------------
# Single run
# ---------------------------------------------------------------------------
def run_one(
    spec: RunSpec,
    sweep_root: Path,
    sim_backend: str,
    record_format: str,
    extra_start_args: list[str],
    benchmark_frame_args: list[str],
    skip_benchmark: bool,
    dry_run: bool,
    param_overrides: dict[str, float] | None = None,
) -> RunResult:
    run_label = f"{spec.scenario_name}__seed{spec.seed}__{spec.mpc_mode}"
    if param_overrides:
        suffix = "_".join(f"{k}{v}" for k, v in sorted(param_overrides.items()))
        run_label = f"{run_label}__{suffix}"
    run_log = sweep_root / "logs" / f"{run_label}.log"
    run_log.parent.mkdir(parents=True, exist_ok=True)

    # ---------------------------------------------------------------------
    # Timing contract P2 (2026-06-09): /auv/sensors/{imu,dvl,depth} are only
    # published when the brain stack reaches its decision/control nodes,
    # which in turn requires (a) bridge in protocol_udp + arbiter profile so
    # mock_amd/zenoh side channel is wired and (b) auto_activate_emu sending
    # 0xEE so AutonomyGuard transitions LOCKED→ACTIVE. Without this triplet
    # the bag is missing IMU/DVL/depth and offline_ekf_benchmark exits with
    # "No IMU samples found in the MCAP file." (D8.1 follow-up)
    #
    # We default the triplet here. Caller can still override via --start-arg
    # if a particular experiment needs a different bridge backend.
    user_args = list(extra_start_args)
    contract_args: list[str] = []
    if not any(a == "--bridge-backend" for a in user_args):
        contract_args += ["--bridge-backend", "protocol_udp"]
    if "--arbiter-profile" not in user_args:
        contract_args += ["--arbiter-profile"]
    if "--auto-activate" not in user_args:
        contract_args += ["--auto-activate"]
    if (
        sim_backend == "pvs"
        and "--enable-mock-forward-sonar-wrapper" not in user_args
        and "--inject-missing-forward-sonar" not in user_args
    ):
        contract_args += ["--enable-mock-forward-sonar-wrapper"]
    if "--bag-arg" not in user_args:
        # Thesis metrics only need sensor/state/control/truth topics. Full
        # visual topics can be large enough to starve rosbag finalization under
        # PVS sweeps, producing non-empty but corrupt MCAP files.
        contract_args += [
            "--bag-arg",
            "--exclude",
            "--bag-arg",
            "^/auv/visual/.*",
        ]
    forwarded_args = contract_args + user_args

    cmd = [
        "bash",
        str(START_SCRIPT),
        "--sim-backend",
        sim_backend,
        "--duration",
        str(spec.duration_s),
        "--scenario",
        str(spec.scenario_path),
        "--seed",
        str(spec.seed),
        "--mpc-mode",
        spec.mpc_mode,
        "--record-format",
        record_format,
        *forwarded_args,
    ]

    print(f"[sweep] >>> {run_label}", flush=True)
    print(f"[sweep]     cmd: {' '.join(cmd)}", flush=True)

    if dry_run:
        return RunResult(
            spec=spec,
            run_dir=None,
            mcap=None,
            metrics={"xy_rmse": float("nan"), "z_rmse": float("nan"),
                     "cep50": float("nan"), "max_drift": float("nan")},
            benchmark_dir=None,
            duration_s_actual=0.0,
            status="dry_run",
            error=None,
        )

    # E6 — env injection of MPC weight overrides for sensitivity sweep
    sub_env = os.environ.copy()
    # Thesis sweeps are timed runtime experiments. Building the ROS workspace
    # inside each run can starve/kill rosbag and move bag T0 before the brain
    # stack is ready; the installed workspace is the runtime contract.
    sub_env.setdefault("AUV_SKIP_BRAIN_BUILD", "1")
    sub_env.setdefault("SIM_DELAY_S", "0")
    sub_env.setdefault("BRAIN_READY_TOPIC", "/auv/control/mpc_cmd")
    sub_env.setdefault("BRAIN_READY_TIMEOUT_S", "90")
    if param_overrides:
        sub_env["AUV_MPC_PARAM_OVERRIDES"] = json.dumps(param_overrides)

    t0 = time.time()
    proc_log_text = ""
    try:
        with open(run_log, "w", encoding="utf-8") as logf:
            proc = subprocess.run(
                cmd,
                cwd=str(REPO_ROOT),
                stdout=logf,
                stderr=subprocess.STDOUT,
                check=False,
                env=sub_env,
            )
        elapsed = time.time() - t0
        proc_log_text = run_log.read_text(encoding="utf-8", errors="replace")
        if proc.returncode != 0:
            return RunResult(
                spec=spec,
                run_dir=parse_run_dir_from_log(proc_log_text),
                mcap=None,
                metrics={"xy_rmse": float("nan"), "z_rmse": float("nan"),
                         "cep50": float("nan"), "max_drift": float("nan")},
                benchmark_dir=None,
                duration_s_actual=elapsed,
                status="start_failed",
                error=f"start_experiment.sh exit={proc.returncode}",
            )
    except Exception as exc:  # noqa: BLE001
        return RunResult(
            spec=spec,
            run_dir=None,
            mcap=None,
            metrics={"xy_rmse": float("nan"), "z_rmse": float("nan"),
                     "cep50": float("nan"), "max_drift": float("nan")},
            benchmark_dir=None,
            duration_s_actual=time.time() - t0,
            status="start_failed",
            error=f"subprocess raise: {exc!r}",
        )

    elapsed = time.time() - t0
    run_dir = parse_run_dir_from_log(proc_log_text)
    if run_dir is None or not run_dir.is_dir():
        return RunResult(
            spec=spec, run_dir=run_dir, mcap=None,
            metrics={"xy_rmse": float("nan"), "z_rmse": float("nan"),
                     "cep50": float("nan"), "max_drift": float("nan")},
            benchmark_dir=None, duration_s_actual=elapsed,
            status="no_bag",
            error="run_dir not parsed from launcher log",
        )

    mcap = find_mcap_in(run_dir)
    if mcap is None:
        return RunResult(
            spec=spec, run_dir=run_dir, mcap=None,
            metrics={"xy_rmse": float("nan"), "z_rmse": float("nan"),
                     "cep50": float("nan"), "max_drift": float("nan")},
            benchmark_dir=None, duration_s_actual=elapsed,
            status="no_bag",
            error="no mcap under run_dir",
        )
    try:
        mcap_size = mcap.stat().st_size
    except OSError as exc:
        return RunResult(
            spec=spec, run_dir=run_dir, mcap=mcap,
            metrics={"xy_rmse": float("nan"), "z_rmse": float("nan"),
                     "cep50": float("nan"), "max_drift": float("nan")},
            benchmark_dir=None, duration_s_actual=elapsed,
            status="no_bag",
            error=f"mcap stat failed: {exc}",
        )
    if mcap_size <= 0:
        return RunResult(
            spec=spec, run_dir=run_dir, mcap=mcap,
            metrics={"xy_rmse": float("nan"), "z_rmse": float("nan"),
                     "cep50": float("nan"), "max_drift": float("nan")},
            benchmark_dir=None, duration_s_actual=elapsed,
            status="bag_empty",
            error=f"mcap file is empty: {mcap}",
        )

    if skip_benchmark:
        return RunResult(
            spec=spec, run_dir=run_dir, mcap=mcap,
            metrics={"xy_rmse": float("nan"), "z_rmse": float("nan"),
                     "cep50": float("nan"), "max_drift": float("nan")},
            benchmark_dir=None, duration_s_actual=elapsed,
            status="ok", error=None,
        )

    # Benchmark phase
    bench_dir = sweep_root / "benchmarks" / run_label
    bench_dir.mkdir(parents=True, exist_ok=True)
    bench_log = sweep_root / "logs" / f"{run_label}.bench.log"
    bench_cmd = [
        sys.executable,
        str(BENCH_TOOL),
        "--input",
        str(mcap),
        "--output-dir",
        str(bench_dir),
        *benchmark_frame_args,
    ]
    try:
        with open(bench_log, "w", encoding="utf-8") as logf:
            bproc = subprocess.run(
                bench_cmd, cwd=str(REPO_ROOT),
                stdout=logf, stderr=subprocess.STDOUT, check=False,
            )
        if bproc.returncode != 0:
            return RunResult(
                spec=spec, run_dir=run_dir, mcap=mcap,
                metrics={"xy_rmse": float("nan"), "z_rmse": float("nan"),
                         "cep50": float("nan"), "max_drift": float("nan")},
                benchmark_dir=bench_dir, duration_s_actual=elapsed,
                status="bench_failed",
                error=f"offline_ekf_benchmark exit={bproc.returncode}",
            )
    except Exception as exc:  # noqa: BLE001
        return RunResult(
            spec=spec, run_dir=run_dir, mcap=mcap,
            metrics={"xy_rmse": float("nan"), "z_rmse": float("nan"),
                     "cep50": float("nan"), "max_drift": float("nan")},
            benchmark_dir=bench_dir, duration_s_actual=elapsed,
            status="bench_failed",
            error=f"benchmark subprocess raise: {exc!r}",
        )

    metrics = parse_benchmark_results(bench_dir / "benchmark_results.md")
    return RunResult(
        spec=spec, run_dir=run_dir, mcap=mcap,
        metrics=metrics, benchmark_dir=bench_dir,
        duration_s_actual=elapsed,
        status="ok", error=None,
    )


# ---------------------------------------------------------------------------
# Main sweep
# ---------------------------------------------------------------------------
def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Sweep driver for thesis experiments.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--scenarios", required=True,
        help="Comma-separated list. Either bare ids (baseline,dvl_dropout_30) "
             "or yaml paths.",
    )
    p.add_argument(
        "--seeds", default="0",
        help="Comma-separated seed list, e.g. 0,1,2,3,4",
    )
    p.add_argument(
        "--mpc-modes", default="ua",
        help="Comma-separated MPC modes: baseline,ua",
    )
    p.add_argument("--duration", type=int, default=120,
                   help="Per-run duration seconds (default 120).")
    p.add_argument("--sim-backend", default="pvs", choices=["pvs", "holoocean"])
    p.add_argument("--record-format", default="mcap", choices=["mcap", "sqlite3"])
    p.add_argument(
        "--output-root", type=Path,
        default=REPO_ROOT / "log" / "thesis_sweep",
        help="Sweep results root (default: log/thesis_sweep)",
    )
    p.add_argument(
        "--label", default=None,
        help="Optional label appended to the timestamped output dir.",
    )
    p.add_argument(
        "--start-arg", action="append", default=[],
        help="Forward arbitrary arg to start_experiment.sh (repeatable).",
    )
    p.add_argument(
        "--skip-benchmark", action="store_true",
        help="Run the experiments but skip offline_ekf_benchmark analysis.",
    )
    p.add_argument(
        "--benchmark-coordinate-transform",
        choices=["auto", "on", "off"],
        default="auto",
        help=(
            "Coordinate-transform mode forwarded to offline_ekf_benchmark. "
            "auto keeps the legacy vector transform for PVS but disables it for "
            "HoloOcean; truth/sensor frame normalization is still controlled by "
            "--benchmark-truth-frame/--benchmark-sensor-frame."
        ),
    )
    p.add_argument(
        "--benchmark-truth-frame",
        choices=["auto", "ned", "ros-up", "ue"],
        default="auto",
        help="Ground-truth position frame forwarded to offline_ekf_benchmark.",
    )
    p.add_argument(
        "--benchmark-sensor-frame",
        choices=["auto", "ned", "ue"],
        default="auto",
        help="IMU/DVL vector frame forwarded to offline_ekf_benchmark.",
    )
    p.add_argument(
        "--dry-run", action="store_true",
        help="Print what would run without executing.",
    )
    p.add_argument(
        "--param-grid", default=None,
        help="E6 sensitivity grid, format "
             "'low_conf_scale:1.5,3.0,5.0;confidence_smoothness_k:4,8,16'. "
             "Each (scenario,seed,mode) is run once per cartesian combo. "
             "Overrides are forwarded to MPC node via env AUV_MPC_PARAM_OVERRIDES.",
    )
    return p.parse_args(argv)


def build_benchmark_frame_args(args: argparse.Namespace) -> list[str]:
    """Build frame-semantics args for offline_ekf_benchmark.

    HoloOcean ROS truth topics are display-frame ROS z-up, while project sensor
    topics are NED. The fixed benchmark logic should always receive explicit
    frame semantics so a formal sweep cannot silently fall back to old Z
    assumptions.
    """
    frame_args = [
        "--truth-frame",
        args.benchmark_truth_frame,
        "--sensor-frame",
        args.benchmark_sensor_frame,
    ]
    coord_mode = args.benchmark_coordinate_transform
    if coord_mode == "auto":
        coord_mode = "off" if args.sim_backend == "holoocean" else "on"
    if coord_mode == "off":
        frame_args.append("--no-coordinate-transform")
    return frame_args


def parse_param_grid(spec: str | None) -> list[dict[str, float]]:
    """Parse 'k1:v1,v2;k2:v3,v4' → list of dicts with cartesian product.

    Empty / None → returns [{}] so callers always iterate at least once.
    """
    if not spec:
        return [{}]
    axes: list[tuple[str, list[float]]] = []
    for chunk in spec.split(";"):
        chunk = chunk.strip()
        if not chunk:
            continue
        if ":" not in chunk:
            raise ValueError(f"param-grid axis missing ':' in {chunk!r}")
        key, vals_s = chunk.split(":", 1)
        key = key.strip()
        vals = [float(v.strip()) for v in vals_s.split(",") if v.strip()]
        if not key or not vals:
            raise ValueError(f"param-grid axis empty in {chunk!r}")
        axes.append((key, vals))
    if not axes:
        return [{}]
    combos: list[dict[str, float]] = [{}]
    for key, vals in axes:
        combos = [{**c, key: v} for c in combos for v in vals]
    return combos


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    if not START_SCRIPT.is_file():
        print(f"[sweep][FATAL] missing {START_SCRIPT}", file=sys.stderr)
        return 2
    if not args.skip_benchmark and not BENCH_TOOL.is_file():
        print(f"[sweep][FATAL] missing {BENCH_TOOL}", file=sys.stderr)
        return 2

    scenarios = [s.strip() for s in args.scenarios.split(",") if s.strip()]
    seeds = [int(s) for s in args.seeds.split(",") if s.strip()]
    modes = [m.strip() for m in args.mpc_modes.split(",") if m.strip()]
    if not scenarios or not seeds or not modes:
        print("[sweep][FATAL] empty scenarios/seeds/mpc-modes", file=sys.stderr)
        return 2
    for m in modes:
        if m not in {"baseline", "ua"}:
            print(f"[sweep][FATAL] unknown mpc-mode: {m}", file=sys.stderr)
            return 2

    resolved = [(name, resolve_scenario(name)) for name in scenarios]
    param_combos = parse_param_grid(args.param_grid)
    param_keys = sorted({k for c in param_combos for k in c.keys()})
    benchmark_frame_args = build_benchmark_frame_args(args)

    stamp = time.strftime("%Y%m%d_%H%M%S")
    label = f"_{args.label}" if args.label else ""
    sweep_root = args.output_root / f"{stamp}{label}"
    sweep_root.mkdir(parents=True, exist_ok=True)
    (sweep_root / "logs").mkdir(parents=True, exist_ok=True)
    (sweep_root / "benchmarks").mkdir(parents=True, exist_ok=True)

    # Manifest
    manifest = {
        "stamp": stamp,
        "label": args.label,
        "scenarios": scenarios,
        "seeds": seeds,
        "mpc_modes": modes,
        "duration_s": args.duration,
        "sim_backend": args.sim_backend,
        "record_format": args.record_format,
        "start_args": args.start_arg,
        "benchmark_coordinate_transform": args.benchmark_coordinate_transform,
        "benchmark_truth_frame": args.benchmark_truth_frame,
        "benchmark_sensor_frame": args.benchmark_sensor_frame,
        "benchmark_frame_args": benchmark_frame_args,
        "param_grid": args.param_grid,
        "param_combos": param_combos,
        "argv": sys.argv,
    }
    (sweep_root / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    initialize_bundle(
        sweep_root,
        experiment_id=f"thesis_sweep_{stamp}{label}",
        runner=_display_runner_path(),
        argv=sys.argv,
        data_layer=f"{args.sim_backend}_closed_loop",
        matrix={
            "scenarios": scenarios,
            "seeds": seeds,
            "mpc_modes": modes,
            "param_combos": param_combos,
        },
        duration_s=args.duration,
        config_paths=[
            *(path for _, path in resolved),
            REPO_ROOT / "brain_linux" / "config" / "params.yaml",
        ],
        extra_manifest={
            "record_format": args.record_format,
            "skip_benchmark": args.skip_benchmark,
            "benchmark_frame_args": benchmark_frame_args,
            "start_args": args.start_arg,
        },
    )

    csv_path = sweep_root / "results.csv"
    fail_path = sweep_root / "failures.log"
    fail_path.write_text("", encoding="utf-8")

    fieldnames = [
        "scenario", "scenario_path", "seed", "mpc_mode",
        *param_keys,
        "status", "duration_s_actual",
        "xy_rmse", "z_rmse", "cep50", "max_drift",
        "run_dir", "mcap", "benchmark_dir", "error",
    ]
    contract_rows: list[dict[str, object]] = []
    with open(csv_path, "w", encoding="utf-8", newline="") as csv_f:
        writer = csv.DictWriter(csv_f, fieldnames=fieldnames)
        writer.writeheader()

        total = len(resolved) * len(seeds) * len(modes) * len(param_combos)
        idx = 0
        ok_count = 0
        for name, path in resolved:
            for seed in seeds:
                for mode in modes:
                    for combo in param_combos:
                        idx += 1
                        spec = RunSpec(
                            scenario_name=name, scenario_path=path,
                            seed=seed, mpc_mode=mode,
                            duration_s=args.duration,
                        )
                        combo_label = (
                            " ".join(f"{k}={v}" for k, v in combo.items())
                            if combo else "(no-override)"
                        )
                        print(f"[sweep] ({idx}/{total}) starting "
                              f"{name} seed={seed} mode={mode} {combo_label}",
                              flush=True)
                        res = run_one(
                            spec=spec, sweep_root=sweep_root,
                            sim_backend=args.sim_backend,
                            record_format=args.record_format,
                            extra_start_args=args.start_arg,
                            benchmark_frame_args=benchmark_frame_args,
                            skip_benchmark=args.skip_benchmark,
                            dry_run=args.dry_run,
                            param_overrides=combo if combo else None,
                        )
                        row = {
                            "scenario": name,
                            "scenario_path": str(path),
                            "seed": seed,
                            "mpc_mode": mode,
                            "status": res.status,
                            "duration_s_actual": f"{res.duration_s_actual:.2f}",
                            "xy_rmse": res.metrics.get("xy_rmse", float("nan")),
                            "z_rmse": res.metrics.get("z_rmse", float("nan")),
                            "cep50": res.metrics.get("cep50", float("nan")),
                            "max_drift": res.metrics.get("max_drift", float("nan")),
                            "run_dir": str(res.run_dir) if res.run_dir else "",
                            "mcap": str(res.mcap) if res.mcap else "",
                            "benchmark_dir":
                                str(res.benchmark_dir) if res.benchmark_dir else "",
                            "error": res.error or "",
                        }
                        for k in param_keys:
                            row[k] = combo.get(k, "")
                        writer.writerow(row)
                        contract_rows.append(dict(row))
                        csv_f.flush()
                        if res.status == "ok":
                            ok_count += 1
                        else:
                            with open(fail_path, "a", encoding="utf-8") as ff:
                                ff.write(
                                    f"{name}\tseed={seed}\tmode={mode}\t"
                                    f"params={combo}\t"
                                    f"status={res.status}\terror={res.error}\n"
                                )
                        print(f"[sweep] ({idx}/{total}) finished "
                              f"{name} seed={seed} mode={mode} {combo_label} "
                              f"status={res.status}",
                              flush=True)

    if param_keys:
        write_sensitivity_summary(csv_path, sweep_root, param_keys)
    contract_rows = enrich_contract_rows_with_control_diagnostics(contract_rows)
    finalize_bundle(
        sweep_root,
        contract_rows,
        success_statuses={"ok", "dry_run"},
    )

    accepted_count = sum(
        1 for row in contract_rows if row.get("status") in {"ok", "dry_run"}
    )
    print(
        f"[sweep] done. {ok_count}/{total} ok, "
        f"{accepted_count}/{total} accepted including dry-run. "
        f"results -> {csv_path}",
        flush=True,
    )
    return 0


def _display_runner_path() -> str:
    return str(Path(__file__).resolve().relative_to(REPO_ROOT))


def write_sensitivity_summary(
    csv_path: Path, sweep_root: Path, param_keys: list[str]
) -> None:
    """E6 — variance-share decomposition (simple ratio, not full ANOVA).

    Reads results.csv, drops failed rows, then for each param_key computes
    the share of total xy_rmse variance explained by group means.
    """
    try:
        import csv as _csv
    except Exception:  # noqa: BLE001
        return
    rows: list[dict[str, str]] = []
    with open(csv_path, "r", encoding="utf-8") as f:
        for r in _csv.DictReader(f):
            if r.get("status") != "ok":
                continue
            try:
                float(r.get("xy_rmse", "nan"))
            except ValueError:
                continue
            rows.append(r)
    if not rows:
        return

    def _f(s: str) -> float:
        try:
            return float(s)
        except (ValueError, TypeError):
            return float("nan")

    xy = [_f(r["xy_rmse"]) for r in rows]
    xy = [v for v in xy if v == v]  # drop NaN
    if not xy:
        return
    mean_total = sum(xy) / len(xy)
    var_total = sum((v - mean_total) ** 2 for v in xy) / max(len(xy) - 1, 1)

    summary_lines = [
        "# Sensitivity Summary (E6)",
        "",
        f"Source: `{csv_path.relative_to(sweep_root.parent.parent)}`",
        f"OK runs: **{len(rows)}**, total xy_rmse variance: **{var_total:.6f}**",
        "",
        "| Parameter | Levels | Between-group var | Share of total |",
        "|---|---|---|---|",
    ]

    for key in param_keys:
        groups: dict[str, list[float]] = {}
        for r in rows:
            v = r.get(key, "")
            if v == "" or v is None:
                continue
            try:
                xy_val = float(r["xy_rmse"])
            except (ValueError, TypeError, KeyError):
                continue
            if xy_val != xy_val:
                continue
            groups.setdefault(str(v), []).append(xy_val)
        if not groups or len(groups) < 2:
            summary_lines.append(
                f"| `{key}` | {len(groups)} | n/a | n/a |"
            )
            continue
        between = 0.0
        for g_vals in groups.values():
            if not g_vals:
                continue
            g_mean = sum(g_vals) / len(g_vals)
            between += len(g_vals) * (g_mean - mean_total) ** 2
        # population-style between-group variance
        between /= max(len(xy), 1)
        share = between / var_total if var_total > 0 else float("nan")
        summary_lines.append(
            f"| `{key}` | {len(groups)} | {between:.6f} | {share*100:.2f}% |"
        )

    summary_path = sweep_root / "sensitivity_summary.md"
    summary_path.write_text("\n".join(summary_lines) + "\n", encoding="utf-8")
    print(f"[sweep] sensitivity summary -> {summary_path}", flush=True)


if __name__ == "__main__":
    sys.exit(main())

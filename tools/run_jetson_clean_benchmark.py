#!/usr/bin/env python3
"""Jetson Orin NX clean benchmark and artifact-recovery handoff for R09."""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.experiment_contract import finalize_bundle, initialize_bundle  # noqa: E402


THESIS_SWEEP = REPO_ROOT / "tools" / "run_thesis_sweep.py"
MPC_BENCH = REPO_ROOT / "tools" / "mpc_solve_microbench.py"
PARAMS = REPO_ROOT / "brain_linux" / "config" / "params.yaml"
SCENARIOS = {
    "baseline": REPO_ROOT / "scenarios" / "scenario_baseline.yaml",
    "combined": REPO_ROOT / "scenarios" / "scenario_combined_stress.yaml",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--system-duration", type=int, default=120)
    parser.add_argument("--soak-duration", type=int, default=1800)
    parser.add_argument("--steady-iters", type=int, default=200)
    parser.add_argument("--stress-iters", type=int, default=50)
    parser.add_argument("--sample-interval-s", type=float, default=1.0)
    parser.add_argument("--tegrastats-interval-ms", type=int, default=500)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Default: results/jetson_clean_benchmark/<timestamp>_r09",
    )
    parser.add_argument(
        "--recover",
        action="append",
        type=Path,
        default=[],
        help="Copy an existing Jetson bag or machine-readable result directory.",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-system", action="store_true")
    parser.add_argument("--skip-microbench", action="store_true")
    parser.add_argument("--skip-soak", action="store_true")
    parser.add_argument(
        "--allow-desktop-load",
        action="store_true",
        help="Do not fail the clean-load gate when browser processes are active.",
    )
    parser.add_argument(
        "--allow-noncanonical-power",
        action="store_true",
        help="Allow execution outside the documented 25 W / 8-core condition.",
    )
    return parser.parse_args()


def run_capture(command: Sequence[str]) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            list(command),
            cwd=str(REPO_ROOT),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
    except OSError as exc:
        return 127, str(exc)
    return proc.returncode, proc.stdout.strip()


def collect_environment(output_dir: Path) -> dict[str, Any]:
    commands = {
        "uname": ["uname", "-a"],
        "nvpmodel": ["nvpmodel", "-q"],
        "nproc": ["nproc"],
        "cpu_online": ["bash", "-lc", "cat /sys/devices/system/cpu/online"],
        "jetson_release": ["bash", "-lc", "cat /etc/nv_tegra_release"],
        "jetson_clocks": ["jetson_clocks", "--show"],
        "python": [sys.executable, "--version"],
        "ros2": ["bash", "-lc", "source /opt/ros/humble/setup.bash && ros2 --version"],
        "tegrastats_path": ["bash", "-lc", "command -v tegrastats"],
        "browser_processes": [
            "bash",
            "-lc",
            "ps -C firefox -C firefox-esr -C chrome -C chromium "
            "-o pid=,comm=,args= --no-headers || true",
        ],
    }
    records: dict[str, Any] = {}
    lines: list[str] = []
    for name, command in commands.items():
        returncode, output = run_capture(command)
        records[name] = {
            "command": command,
            "returncode": returncode,
            "output": output,
        }
        lines.extend(
            [
                f"## {name}",
                f"returncode={returncode}",
                output,
                "",
            ]
        )
    (output_dir / "jetson_environment.txt").write_text(
        "\n".join(lines), encoding="utf-8"
    )
    (output_dir / "jetson_environment.json").write_text(
        json.dumps(records, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return records


def environment_gate(
    records: dict[str, Any],
    *,
    allow_desktop_load: bool,
    allow_noncanonical_power: bool,
) -> tuple[str, list[str]]:
    failures: list[str] = []
    release = str(records["jetson_release"]["output"])
    if records["jetson_release"]["returncode"] != 0 or "R" not in release:
        failures.append("NVIDIA Jetson release file is unavailable")
    if records["tegrastats_path"]["returncode"] != 0:
        failures.append("tegrastats is unavailable")
    nvpmodel = str(records["nvpmodel"]["output"]).upper()
    if "25W" not in nvpmodel and not allow_noncanonical_power:
        failures.append("nvpmodel does not report the canonical 25W mode")
    try:
        cores = int(str(records["nproc"]["output"]).splitlines()[-1])
    except (ValueError, IndexError):
        cores = 0
    if cores < 8 and not allow_noncanonical_power:
        failures.append(f"only {cores} CPU cores are available; expected at least 8")
    browsers = str(records["browser_processes"]["output"]).strip()
    if browsers and not allow_desktop_load:
        failures.append("browser process detected; close it or use --allow-desktop-load")
    return ("passed" if not failures else "blocked"), failures


def process_sampler(
    process: subprocess.Popen,
    output_path: Path,
    interval_s: float,
) -> None:
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            ["timestamp_epoch_s", "pid", "ppid", "cpu_pct", "mem_pct", "rss_kb", "command"]
        )
        while process.poll() is None:
            returncode, output = run_capture(
                ["ps", "-eo", "pid=,ppid=,pcpu=,pmem=,rss=,comm="]
            )
            if returncode == 0:
                now = time.time()
                for line in output.splitlines():
                    fields = line.split(None, 6)
                    if len(fields) == 7:
                        writer.writerow([f"{now:.6f}", *fields])
                handle.flush()
            time.sleep(max(interval_s, 0.1))


def start_tegrastats(output_path: Path, interval_ms: int):
    handle = output_path.open("w", encoding="utf-8")
    try:
        process = subprocess.Popen(
            ["tegrastats", "--interval", str(interval_ms)],
            cwd=str(REPO_ROOT),
            stdout=handle,
            stderr=subprocess.STDOUT,
            text=True,
        )
    except OSError:
        handle.close()
        return None, None
    return process, handle


def parse_tegrastats(raw_path: Path, csv_path: Path) -> int:
    rows: list[dict[str, object]] = []
    if not raw_path.is_file():
        return 0
    temp_pattern = re.compile(r"([A-Za-z0-9_]+)@([0-9.]+)C")
    power_pattern = re.compile(r"([A-Za-z0-9_]+)\s+([0-9]+)mW/([0-9]+)mW")
    ram_pattern = re.compile(r"RAM\s+([0-9]+)/([0-9]+)MB")
    for index, line in enumerate(
        raw_path.read_text(encoding="utf-8", errors="replace").splitlines()
    ):
        temperatures = {
            name: float(value) for name, value in temp_pattern.findall(line)
        }
        powers = {
            name: (float(current), float(average))
            for name, current, average in power_pattern.findall(line)
        }
        ram_match = ram_pattern.search(line)
        rows.append(
            {
                "sample_index": index,
                "ram_used_mb": int(ram_match.group(1)) if ram_match else "",
                "ram_total_mb": int(ram_match.group(2)) if ram_match else "",
                "max_temperature_c": max(temperatures.values())
                if temperatures
                else "",
                "vdd_in_current_mw": powers.get("VDD_IN", ("", ""))[0],
                "vdd_in_average_mw": powers.get("VDD_IN", ("", ""))[1],
                "temperature_json": json.dumps(temperatures, sort_keys=True),
                "power_json": json.dumps(powers, sort_keys=True),
            }
        )
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        fieldnames = [
            "sample_index",
            "ram_used_mb",
            "ram_total_mb",
            "max_temperature_c",
            "vdd_in_current_mw",
            "vdd_in_average_mw",
            "temperature_json",
            "power_json",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def run_phase(
    *,
    name: str,
    command: Sequence[str],
    output_dir: Path,
    environment: dict[str, str] | None,
    sample_interval_s: float,
    tegrastats_interval_ms: int,
) -> tuple[int, float, int]:
    phase_dir = output_dir / "telemetry" / name
    phase_dir.mkdir(parents=True, exist_ok=True)
    log_handle = (phase_dir / "command.log").open("w", encoding="utf-8")
    t0 = time.perf_counter()
    process = subprocess.Popen(
        list(command),
        cwd=str(REPO_ROOT),
        env=environment,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        text=True,
    )
    tegra_process, tegra_handle = start_tegrastats(
        phase_dir / "tegrastats.log", tegrastats_interval_ms
    )
    sampler = threading.Thread(
        target=process_sampler,
        args=(process, phase_dir / "process_samples.csv", sample_interval_s),
        daemon=True,
    )
    sampler.start()
    returncode = process.wait()
    sampler.join(timeout=max(sample_interval_s * 2.0, 1.0))
    if tegra_process is not None:
        tegra_process.terminate()
        try:
            tegra_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            tegra_process.kill()
    if tegra_handle is not None:
        tegra_handle.close()
    log_handle.close()
    sample_count = parse_tegrastats(
        phase_dir / "tegrastats.log",
        phase_dir / "tegrastats.csv",
    )
    return returncode, time.perf_counter() - t0, sample_count


def newest_directory(root: Path) -> Path | None:
    directories = [path for path in root.iterdir() if path.is_dir()] if root.is_dir() else []
    return max(directories, key=lambda path: path.stat().st_mtime) if directories else None


def summarize_nested_sweep(root: Path, phase: str, elapsed_s: float, returncode: int) -> dict[str, object]:
    bundle = newest_directory(root)
    row: dict[str, object] = {
        "scenario": phase,
        "seed": 0,
        "mpc_mode": "ua",
        "status": "ok" if returncode == 0 and bundle else "failed",
        "duration_s_actual": elapsed_s,
        "run_dir": str(bundle or ""),
        "effective_sample_count": "not_observed",
        "failure_event_count": 0,
        "capability_gate_status": "not_observed",
        "solver_wall_time_current_ms": "not_observed",
        "fallback_type": "not_observed",
    }
    metrics_path = bundle / "metrics.csv" if bundle else None
    if metrics_path and metrics_path.is_file():
        with metrics_path.open("r", encoding="utf-8", newline="") as handle:
            metrics = list(csv.DictReader(handle))
        observed = [
            item
            for item in metrics
            if item.get("effective_sample_count") not in ("", "not_observed")
        ]
        if observed:
            row["effective_sample_count"] = sum(
                int(float(item["effective_sample_count"])) for item in observed
            )
            row["failure_event_count"] = sum(
                int(float(item["failure_event_count"])) for item in observed
            )
            wall_values = [
                float(item["solver_wall_time_current_ms"]) for item in observed
            ]
            row["solver_wall_time_current_ms"] = max(wall_values)
            row["fallback_type"] = ";".join(
                sorted({item["fallback_type"] for item in observed})
            )
            gate_values = {item["capability_gate_status"] for item in observed}
            row["capability_gate_status"] = (
                "blocked" if "blocked" in gate_values else ";".join(sorted(gate_values))
            )
    if row["status"] != "ok":
        row["error"] = f"nested sweep exit={returncode}; bundle={bundle}"
    return row


def summarize_microbench(
    output_dir: Path,
    phase: str,
    elapsed_s: float,
    returncode: int,
) -> dict[str, object]:
    raw_paths = [
        output_dir / "mpc_solve_microbench_cold_raw.csv",
        output_dir / "mpc_solve_microbench_warm_raw.csv",
    ]
    samples: list[dict[str, str]] = []
    for path in raw_paths:
        if path.is_file():
            with path.open("r", encoding="utf-8", newline="") as handle:
                samples.extend(csv.DictReader(handle))
    walls = [float(item["wall_ms"]) for item in samples]
    failures = [
        item for item in samples if str(item["solver_status"]).startswith("FAILED")
    ]
    return {
        "scenario": phase,
        "seed": "deterministic",
        "mpc_mode": "ua",
        "status": "ok" if returncode == 0 and samples else "failed",
        "duration_s_actual": elapsed_s,
        "run_dir": str(output_dir),
        "effective_sample_count": len(samples) if samples else "not_observed",
        "failure_event_count": len(failures),
        "capability_gate_status": "not_applicable_microbench",
        "solver_wall_time_current_ms": max(walls) if walls else "not_observed",
        "fallback_type": "solver_failure" if failures else "none",
        "error": "" if returncode == 0 and samples else f"microbench exit={returncode}",
    }


def recover_artifacts(paths: Sequence[Path], output_dir: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    recovery_root = output_dir / "recovered"
    recovery_root.mkdir(exist_ok=True)
    for index, source in enumerate(paths):
        source = source.expanduser().resolve()
        destination = recovery_root / f"{index:02d}_{source.name}"
        if source.is_dir():
            shutil.copytree(source, destination, dirs_exist_ok=True)
        elif source.is_file():
            shutil.copy2(source, destination)
        else:
            rows.append(
                {
                    "scenario": f"recover_{index}",
                    "status": "failed",
                    "error": f"missing recovery source: {source}",
                }
            )
            continue
        file_count = sum(1 for path in destination.rglob("*") if path.is_file()) if destination.is_dir() else 1
        rows.append(
            {
                "scenario": f"recover_{index}",
                "status": "recovered",
                "run_dir": str(destination),
                "effective_sample_count": file_count,
                "failure_event_count": 0,
                "capability_gate_status": "historical_metadata_required",
                "solver_wall_time_current_ms": "not_applicable_recovery",
                "fallback_type": "not_applicable_recovery",
            }
        )
    return rows


def planned_commands(args: argparse.Namespace, output_dir: Path) -> list[tuple[str, list[str], Path, dict[str, str] | None]]:
    phases: list[tuple[str, list[str], Path, dict[str, str] | None]] = []
    runtime_env = os.environ.copy()
    runtime_env["AUV_SKIP_BRAIN_BUILD"] = "1"
    if not args.skip_system:
        root = output_dir / "system_sweep"
        phases.append(
            (
                "system_baseline_combined",
                [
                    sys.executable,
                    str(THESIS_SWEEP),
                    "--scenarios",
                    "baseline,combined_stress",
                    "--seeds",
                    "0",
                    "--mpc-modes",
                    "ua",
                    "--duration",
                    str(args.system_duration),
                    "--output-root",
                    str(root),
                    "--label",
                    "jetson_clean",
                    "--skip-benchmark",
                ],
                root,
                runtime_env,
            )
        )
    if not args.skip_microbench:
        for phase, iters, start_depth in (
            ("mpc_steady", args.steady_iters, 3.0),
            ("mpc_constraint_stress", args.stress_iters, 8.0),
        ):
            root = output_dir / phase
            phases.append(
                (
                    phase,
                    [
                        sys.executable,
                        str(MPC_BENCH),
                        "--iters",
                        str(iters),
                        "--start-depth",
                        str(start_depth),
                        "--target-depth",
                        "3.0",
                        "--output-dir",
                        str(root),
                    ],
                    root,
                    None,
                )
            )
    if not args.skip_soak:
        root = output_dir / "soak_sweep"
        phases.append(
            (
                "combined_soak",
                [
                    sys.executable,
                    str(THESIS_SWEEP),
                    "--scenarios",
                    "combined_stress",
                    "--seeds",
                    "0",
                    "--mpc-modes",
                    "ua",
                    "--duration",
                    str(args.soak_duration),
                    "--output-root",
                    str(root),
                    "--label",
                    "jetson_soak",
                    "--skip-benchmark",
                ],
                root,
                runtime_env,
            )
        )
    return phases


def write_handoff(output_dir: Path, commands: Sequence[tuple[str, list[str], Path, dict[str, str] | None]]) -> None:
    lines = [
        "# Jetson Clean Benchmark Handoff",
        "",
        "Run from the repository root on Jetson Orin NX after closing browser and visualization workloads:",
        "",
        "```bash",
        "bash scripts/run_jetson_clean_benchmark.sh",
        "```",
        "",
        "Planned phases:",
        "",
    ]
    for name, command, _, _ in commands:
        lines.extend([f"## {name}", "", "```bash", " ".join(command), "```", ""])
    lines.extend(
        [
            "The runner requires the documented 25 W / 8-core condition, captures "
            "`tegrastats`, process samples, bags, logs, environment, and both MPC tiers. "
            "Use `--recover PATH` to import historical machine-readable Jetson artifacts.",
            "",
        ]
    )
    (output_dir / "HANDOFF.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    args = parse_args()
    stamp = time.strftime("%Y%m%dT%H%M%S")
    output_dir = args.output_dir or (
        REPO_ROOT / "results" / "jetson_clean_benchmark" / f"{stamp}_r09"
    )
    initialize_bundle(
        output_dir,
        experiment_id=f"r09_jetson_clean_benchmark_{stamp}",
        runner=str(Path(__file__).resolve().relative_to(REPO_ROOT)),
        argv=sys.argv,
        data_layer="jetson_orin_nx_hardware",
        matrix={
            "system_profiles": ["baseline", "combined"],
            "mpc_tiers": ["steady", "constraint_stress"],
            "soak_duration_s": args.soak_duration,
        },
        duration_s=(
            2 * args.system_duration + args.soak_duration
            if not args.dry_run
            else 0
        ),
        config_paths=[PARAMS, *SCENARIOS.values(), Path(__file__)],
        extra_manifest={
            "canonical_power_mode": "25W",
            "canonical_online_cores": 8,
            "dry_run": args.dry_run,
            "emulated_result_accepted": False,
        },
    )
    commands = planned_commands(args, output_dir)
    write_handoff(output_dir, commands)
    records = collect_environment(output_dir)
    gate_status, gate_failures = environment_gate(
        records,
        allow_desktop_load=args.allow_desktop_load,
        allow_noncanonical_power=args.allow_noncanonical_power,
    )
    rows = recover_artifacts(args.recover, output_dir)

    plan = {
        "gate_status": gate_status,
        "gate_failures": gate_failures,
        "dry_run": args.dry_run,
        "phases": [
            {"name": name, "command": command, "output_root": str(root)}
            for name, command, root, _ in commands
        ],
    }
    (output_dir / "benchmark_plan.json").write_text(
        json.dumps(plan, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    if args.dry_run:
        for name, _, _, _ in commands:
            rows.append(
                {
                    "scenario": name,
                    "seed": 0,
                    "mpc_mode": "ua",
                    "status": "dry_run",
                    "effective_sample_count": "not_observed",
                    "failure_event_count": 0,
                    "capability_gate_status": "not_observed",
                    "solver_wall_time_current_ms": "not_observed",
                    "fallback_type": "not_observed",
                }
            )
        finalize_bundle(
            output_dir,
            rows,
            success_statuses={"dry_run", "recovered"},
        )
        write_handoff(output_dir, commands)
        print(f"[R09] dry-run handoff -> {output_dir}")
        return 0

    if gate_status != "passed":
        rows.append(
            {
                "scenario": "environment_gate",
                "status": "blocked",
                "error": "; ".join(gate_failures),
                "capability_gate_status": "blocked",
            }
        )
        finalize_bundle(output_dir, rows, success_statuses={"ok", "recovered"})
        write_handoff(output_dir, commands)
        print("[R09] environment gate blocked:", "; ".join(gate_failures))
        return 2

    for name, command, root, environment in commands:
        returncode, elapsed_s, tegra_samples = run_phase(
            name=name,
            command=command,
            output_dir=output_dir,
            environment=environment,
            sample_interval_s=args.sample_interval_s,
            tegrastats_interval_ms=args.tegrastats_interval_ms,
        )
        if name.startswith("mpc_"):
            row = summarize_microbench(root, name, elapsed_s, returncode)
        else:
            row = summarize_nested_sweep(root, name, elapsed_s, returncode)
        row["tegrastats_sample_count"] = tegra_samples
        rows.append(row)

    finalize_bundle(output_dir, rows, success_statuses={"ok", "recovered"})
    write_handoff(output_dir, commands)
    failed = [row for row in rows if row.get("status") not in {"ok", "recovered"}]
    print(f"[R09] completed {len(rows) - len(failed)}/{len(rows)} phases -> {output_dir}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

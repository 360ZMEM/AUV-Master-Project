#!/usr/bin/env python3
"""Run low-cost proxy cable scenarios with per-scenario bridge configs."""

from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
START_SCRIPT = REPO_ROOT / "scripts" / "start_experiment.sh"


@dataclass(frozen=True)
class ProxyScenario:
    name: str
    bridge_cfg: Path
    thesis_scenario: Path


SCENARIOS = {
    "cable_s_curve_proxy": ProxyScenario(
        name="cable_s_curve_proxy",
        bridge_cfg=REPO_ROOT / "config" / "bridge_params.protocol_udp.pvs.cable_s_curve_proxy.yaml",
        thesis_scenario=REPO_ROOT / "scenarios" / "scenario_baseline.yaml",
    ),
    "cable_hairpin_proxy": ProxyScenario(
        name="cable_hairpin_proxy",
        bridge_cfg=REPO_ROOT / "config" / "bridge_params.protocol_udp.pvs.cable_hairpin_proxy.yaml",
        thesis_scenario=REPO_ROOT / "scenarios" / "scenario_baseline.yaml",
    ),
    "cable_slope_crossing_proxy": ProxyScenario(
        name="cable_slope_crossing_proxy",
        bridge_cfg=REPO_ROOT / "config" / "bridge_params.protocol_udp.pvs.cable_slope_crossing_proxy.yaml",
        thesis_scenario=REPO_ROOT / "scenarios" / "scenario_baseline.yaml",
    ),
    "cable_buried_gap_proxy": ProxyScenario(
        name="cable_buried_gap_proxy",
        bridge_cfg=REPO_ROOT / "config" / "bridge_params.protocol_udp.pvs.cable_buried_gap_proxy.yaml",
        thesis_scenario=REPO_ROOT / "scenarios" / "scenario_baseline.yaml",
    ),
    "cable_cross_current_proxy": ProxyScenario(
        name="cable_cross_current_proxy",
        bridge_cfg=REPO_ROOT / "config" / "bridge_params.protocol_udp.pvs.cable_cross_current_proxy.yaml",
        thesis_scenario=REPO_ROOT / "scenarios" / "scenario_baseline.yaml",
    ),
    "combined_cable_extreme_proxy": ProxyScenario(
        name="combined_cable_extreme_proxy",
        bridge_cfg=REPO_ROOT / "config" / "bridge_params.protocol_udp.pvs.combined_cable_extreme_proxy.yaml",
        thesis_scenario=REPO_ROOT / "scenarios" / "scenario_combined_stress.yaml",
    ),
}


def parse_csv_list(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def parse_int_list(value: str) -> list[int]:
    return [int(item) for item in parse_csv_list(value)]


def parse_run_dir(log_text: str) -> Path | None:
    match = re.search(r"\[AUV\] experiment directory:\s*(\S+)", log_text)
    if not match:
        return None
    path = Path(match.group(1))
    return path if path.exists() else path


def find_mcap(run_dir: Path | None) -> Path | None:
    if run_dir is None or not run_dir.exists():
        return None
    matches = sorted(run_dir.rglob("*.mcap"))
    return matches[0] if matches else None


def fmt(value: object) -> object:
    if isinstance(value, float):
        return f"{value:.2f}"
    return value


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: fmt(row.get(key, "")) for key in fieldnames})


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Proxy cable scenario sweep.")
    parser.add_argument(
        "--scenarios",
        required=True,
        help="Comma-separated proxy scenario ids.",
    )
    parser.add_argument("--seeds", default="0")
    parser.add_argument("--mpc-modes", default="baseline,ua")
    parser.add_argument("--duration", type=int, default=30)
    parser.add_argument("--label", default="cable_proxy_smoke")
    parser.add_argument("--output-root", type=Path, default=REPO_ROOT / "log" / "proxy_cable_sweep")
    parser.add_argument("--record-format", default="mcap", choices=["mcap", "sqlite3"])
    return parser.parse_args()


def validate_inputs(scenarios: list[str], modes: list[str]) -> None:
    if not START_SCRIPT.is_file():
        raise SystemExit(f"Missing start script: {START_SCRIPT}")
    for name in scenarios:
        if name not in SCENARIOS:
            raise SystemExit(f"Unknown proxy scenario {name!r}; choices: {','.join(sorted(SCENARIOS))}")
        spec = SCENARIOS[name]
        if not spec.bridge_cfg.is_file():
            raise SystemExit(f"Missing bridge config for {name}: {spec.bridge_cfg}")
        if not spec.thesis_scenario.is_file():
            raise SystemExit(f"Missing thesis scenario for {name}: {spec.thesis_scenario}")
    for mode in modes:
        if mode not in {"baseline", "ua"}:
            raise SystemExit(f"Unknown mpc mode {mode!r}; choices: baseline,ua")


def main() -> int:
    args = parse_args()
    scenario_names = parse_csv_list(args.scenarios)
    seeds = parse_int_list(args.seeds)
    modes = parse_csv_list(args.mpc_modes)
    validate_inputs(scenario_names, modes)

    stamp = time.strftime("%Y%m%d_%H%M%S")
    label = f"_{args.label}" if args.label else ""
    output_dir = args.output_root / f"{stamp}{label}"
    log_dir = output_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "manifest.json").write_text(
        json.dumps(
            {
                "stamp": stamp,
                "label": args.label,
                "scenarios": scenario_names,
                "seeds": seeds,
                "mpc_modes": modes,
                "duration_s": args.duration,
                "record_format": args.record_format,
                "argv": sys.argv,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    rows: list[dict[str, object]] = []
    failures: list[str] = []
    total = len(scenario_names) * len(seeds) * len(modes)
    idx = 0
    for scenario_name in scenario_names:
        spec = SCENARIOS[scenario_name]
        for seed in seeds:
            for mode in modes:
                idx += 1
                run_label = f"{scenario_name}__seed{seed}__{mode}"
                log_path = log_dir / f"{run_label}.log"
                cmd = [
                    "bash",
                    str(START_SCRIPT),
                    "--sim-backend",
                    "pvs",
                    "--bridge-backend",
                    "protocol_udp",
                    "--bridge-cfg",
                    str(spec.bridge_cfg),
                    "--scenario",
                    str(spec.thesis_scenario),
                    "--seed",
                    str(seed),
                    "--mpc-mode",
                    mode,
                    "--record-format",
                    args.record_format,
                    "--duration",
                    str(args.duration),
                    "--arbiter-profile",
                    "--auto-activate",
                ]
                print(f"[proxy-cable] ({idx}/{total}) {run_label}", flush=True)
                t0 = time.time()
                proc = subprocess.run(
                    cmd,
                    cwd=str(REPO_ROOT),
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    check=False,
                )
                elapsed = time.time() - t0
                log_path.write_text(proc.stdout, encoding="utf-8", errors="replace")
                run_dir = parse_run_dir(proc.stdout)
                mcap = find_mcap(run_dir)
                status = "ok" if proc.returncode == 0 and mcap is not None and mcap.stat().st_size > 0 else "failed"
                error = ""
                if status != "ok":
                    error = f"exit={proc.returncode}; mcap={'missing' if mcap is None else 'empty'}"
                    failures.append(f"{run_label}\t{error}")
                rows.append(
                    {
                        "scenario": scenario_name,
                        "bridge_cfg": str(spec.bridge_cfg),
                        "thesis_scenario": str(spec.thesis_scenario),
                        "seed": seed,
                        "mpc_mode": mode,
                        "status": status,
                        "duration_s_actual": elapsed,
                        "run_dir": str(run_dir or ""),
                        "mcap": str(mcap or ""),
                        "log": str(log_path),
                        "error": error,
                    }
                )
                print(f"[proxy-cable] finished {run_label} status={status}", flush=True)

    fieldnames = [
        "scenario",
        "bridge_cfg",
        "thesis_scenario",
        "seed",
        "mpc_mode",
        "status",
        "duration_s_actual",
        "run_dir",
        "mcap",
        "log",
        "error",
    ]
    write_csv(output_dir / "results.csv", fieldnames, rows)
    (output_dir / "failures.log").write_text("\n".join(failures) + ("\n" if failures else ""), encoding="utf-8")
    ok_count = sum(1 for row in rows if row["status"] == "ok")
    print(f"[proxy-cable] done. {ok_count}/{len(rows)} ok. results -> {output_dir / 'results.csv'}", flush=True)
    return 0 if ok_count == len(rows) else 1


if __name__ == "__main__":
    sys.exit(main())

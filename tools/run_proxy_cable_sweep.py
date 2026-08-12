#!/usr/bin/env python3
"""Run low-cost proxy cable scenarios with per-scenario bridge configs."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.experiment_contract import finalize_bundle, initialize_bundle  # noqa: E402
from tools.aggregate_control_metrics import (  # noqa: E402
    enrich_contract_rows_with_control_diagnostics,
)

START_SCRIPT = REPO_ROOT / "scripts" / "start_experiment.sh"
SIM_QUALITY_PARAMS = (
    REPO_ROOT / "brain_linux/config/perception_quality_sim_r13.yaml"
)
SIM_AUTHORITY_PARAMS = (
    REPO_ROOT / "brain_linux/config/tracking_authority_sim_r13.yaml"
)
SIM_MAGNETIC_CALIBRATION = (
    REPO_ROOT / "brain_linux/config/perception_quality_sim_magnetic.json"
)
SIM_SONAR_CALIBRATION = (
    REPO_ROOT / "brain_linux/config/perception_quality_sim_sonar.json"
)
DEFAULT_COMBINED_CABLE_TRACKING_CONFIG = (
    REPO_ROOT / "brain_linux/config/cable_tracking_combined_extreme.yaml"
)


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


def exogenous_input_hash(spec: ScenarioSpec, seed: int) -> str:
    """Hash mode-independent closed-loop inputs for paired comparisons."""
    digest = hashlib.sha256()
    digest.update(f"scenario_seed={seed}\n".encode())
    for path in (
        spec.bridge_cfg,
        spec.thesis_scenario,
        REPO_ROOT / "sim_holoocean/interfaces/cable_quality_sim.py",
        REPO_ROOT / "sim_holoocean/interfaces/mock_amd_server.py",
    ):
        digest.update(str(path.relative_to(REPO_ROOT)).encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


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
    parser.add_argument(
        "--mpc-param-overrides",
        default="",
        help="JSON object forwarded through AUV_MPC_PARAM_OVERRIDES.",
    )
    parser.add_argument(
        "--mpc-param-overrides-file",
        type=Path,
        help=(
            "JSON file containing either the override object or an "
            "mpc_param_overrides object."
        ),
    )
    parser.add_argument(
        "--confidence-source",
        choices=["legacy_covariance", "source_specific"],
        default="legacy_covariance",
    )
    parser.add_argument(
        "--quality-preflight-report",
        type=Path,
        help="Passing report from tools/preflight_r13_quality.py.",
    )
    parser.add_argument(
        "--full-flow-cable-tracking",
        action="store_true",
        help=(
            "Enable cable_tracking_node + cable mission autostart and let the "
            "controller consume mission heading setpoints."
        ),
    )
    parser.add_argument(
        "--cable-tracking-config",
        type=Path,
        help=(
            "Cable tracking YAML for --full-flow-cable-tracking. Defaults to "
            "the combined extreme proxy prior when only that scenario is run."
        ),
    )
    parser.add_argument("--cable-mission-target-depth", type=float, default=4.0)
    parser.add_argument("--cable-mission-target-speed-mps", type=float, default=0.4)
    parser.add_argument("--cable-mission-start-delay-s", type=float, default=2.0)
    parser.add_argument("--dry-run", action="store_true")
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


def validate_quality_gate(
    *,
    args: argparse.Namespace,
    scenario_names: list[str],
    modes: list[str],
    mpc_param_overrides: dict[str, object],
) -> dict[str, object] | None:
    if "ua" not in modes:
        return None
    if args.confidence_source != "source_specific":
        raise SystemExit(
            "R13 UA is blocked: use --confidence-source source_specific "
            "after generating a passing quality preflight report"
        )
    if not SIM_QUALITY_PARAMS.is_file() or not SIM_AUTHORITY_PARAMS.is_file():
        raise SystemExit("R13 source-specific quality parameter files are missing")
    if args.quality_preflight_report is None:
        raise SystemExit(
            "R13 UA requires --quality-preflight-report from "
            "tools/preflight_r13_quality.py"
        )
    report_path = args.quality_preflight_report.expanduser().resolve()
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SystemExit(f"invalid quality preflight report: {error}") from error
    if not bool(report.get("passed", False)):
        raise SystemExit("R13 UA quality preflight did not pass")
    if report.get("calibration_domain") != "simulation_proxy":
        raise SystemExit("R13 UA preflight calibration domain must be simulation_proxy")
    report_scenarios = {
        str(item.get("scenario", "")).removeprefix(
            "bridge_params.protocol_udp.pvs."
        ): item
        for item in report.get("scenarios", [])
        if isinstance(item, dict)
    }
    for scenario_name in scenario_names:
        item = report_scenarios.get(scenario_name)
        if item is None:
            raise SystemExit(
                f"quality preflight does not cover scenario {scenario_name}"
            )
        expected_hash = hashlib.sha256(
            SCENARIOS[scenario_name].bridge_cfg.read_bytes()
        ).hexdigest()
        if item.get("config_sha256") != expected_hash:
            raise SystemExit(
                f"quality preflight is stale for scenario {scenario_name}"
            )
    if mpc_param_overrides.get("confidence_policy") != "conservative":
        raise SystemExit(
            "R13 UA requires mpc override confidence_policy=conservative"
        )
    delta_weights = (
        "delta_psi_cmd",
        "delta_z_cmd",
        "delta_T_cmd",
    )
    if not any(
        float(mpc_param_overrides.get(key, 0.0)) > 0.0
        for key in delta_weights
    ):
        raise SystemExit(
            "R13 UA conservative mapping requires at least one positive "
            "delta_* control weight"
        )
    report["_report_path"] = str(report_path)
    return report


def main() -> int:
    args = parse_args()
    scenario_names = parse_csv_list(args.scenarios)
    seeds = parse_int_list(args.seeds)
    modes = parse_csv_list(args.mpc_modes)
    validate_inputs(scenario_names, modes)
    if args.mpc_param_overrides_file and args.mpc_param_overrides.strip():
        raise SystemExit(
            "use only one of --mpc-param-overrides and "
            "--mpc-param-overrides-file"
        )
    try:
        if args.mpc_param_overrides_file:
            override_document = json.loads(
                args.mpc_param_overrides_file.read_text(encoding="utf-8")
            )
            mpc_param_overrides = override_document.get(
                "mpc_param_overrides",
                override_document,
            )
        elif args.mpc_param_overrides.strip():
            mpc_param_overrides = json.loads(args.mpc_param_overrides)
        else:
            mpc_param_overrides = {}
    except (OSError, json.JSONDecodeError) as error:
        raise SystemExit(f"Invalid MPC override document: {error}") from error
    if not isinstance(mpc_param_overrides, dict):
        raise SystemExit("--mpc-param-overrides must decode to a JSON object")
    cable_tracking_config = args.cable_tracking_config
    if args.full_flow_cable_tracking:
        if cable_tracking_config is None:
            if scenario_names == ["combined_cable_extreme_proxy"]:
                cable_tracking_config = DEFAULT_COMBINED_CABLE_TRACKING_CONFIG
            else:
                raise SystemExit(
                    "--full-flow-cable-tracking requires --cable-tracking-config "
                    "unless only combined_cable_extreme_proxy is selected"
                )
        cable_tracking_config = cable_tracking_config.expanduser().resolve()
        if not cable_tracking_config.is_file():
            raise SystemExit(f"missing cable tracking config: {cable_tracking_config}")
        if args.cable_mission_target_depth <= 0.0:
            raise SystemExit("--cable-mission-target-depth must be positive")
        if args.cable_mission_target_speed_mps <= 0.0:
            raise SystemExit("--cable-mission-target-speed-mps must be positive")
    quality_preflight = validate_quality_gate(
        args=args,
        scenario_names=scenario_names,
        modes=modes,
        mpc_param_overrides=mpc_param_overrides,
    )

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
                "mpc_param_overrides": mpc_param_overrides,
                "mpc_param_overrides_file": (
                    str(args.mpc_param_overrides_file.resolve())
                    if args.mpc_param_overrides_file
                    else None
                ),
                "confidence_source": args.confidence_source,
                "quality_preflight_report": (
                    quality_preflight.get("_report_path")
                    if quality_preflight
                    else None
                ),
                "full_flow_cable_tracking": bool(args.full_flow_cable_tracking),
                "cable_tracking_config": (
                    str(cable_tracking_config) if cable_tracking_config else None
                ),
                "cable_mission_target_depth": args.cable_mission_target_depth,
                "cable_mission_target_speed_mps": args.cable_mission_target_speed_mps,
                "cable_mission_start_delay_s": args.cable_mission_start_delay_s,
                "argv": sys.argv,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    initialize_bundle(
        output_dir,
        experiment_id=f"proxy_cable_sweep_{stamp}{label}",
        runner=str(Path(__file__).resolve().relative_to(REPO_ROOT)),
        argv=sys.argv,
        data_layer="pvs_proxy_closed_loop",
        matrix={
            "scenarios": scenario_names,
            "seeds": seeds,
            "mpc_modes": modes,
            "mpc_param_overrides": mpc_param_overrides,
            "confidence_source": args.confidence_source,
        },
        duration_s=args.duration,
        config_paths=[
            path
            for name in scenario_names
            for path in (SCENARIOS[name].bridge_cfg, SCENARIOS[name].thesis_scenario)
        ]
        + (
            [
                SIM_QUALITY_PARAMS,
                SIM_AUTHORITY_PARAMS,
                SIM_MAGNETIC_CALIBRATION,
                SIM_SONAR_CALIBRATION,
                Path(quality_preflight["_report_path"]),
            ]
            if quality_preflight
            else []
        )
        + ([cable_tracking_config] if cable_tracking_config else [])
        + ([args.mpc_param_overrides_file] if args.mpc_param_overrides_file else []),
        extra_manifest={
            "record_format": args.record_format,
            "dry_run": args.dry_run,
            "full_flow_cable_tracking": bool(args.full_flow_cable_tracking),
            "quality_preflight_report": (
                quality_preflight.get("_report_path")
                if quality_preflight
                else None
            ),
        },
    )

    rows: list[dict[str, object]] = []
    failures: list[str] = []
    total = len(scenario_names) * len(seeds) * len(modes)
    idx = 0
    for scenario_name in scenario_names:
        spec = SCENARIOS[scenario_name]
        for seed in seeds:
            paired_input_hash = exogenous_input_hash(spec, seed)
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
                    "--brain-arg",
                    f"perception_quality_params_file:={SIM_QUALITY_PARAMS}",
                    "--brain-arg",
                    f"tracking_authority_params_file:={SIM_AUTHORITY_PARAMS}",
                ]
                if args.confidence_source == "source_specific":
                    cmd.extend(
                        [
                            "--brain-arg",
                            "enable_quality_control:="
                            + ("true" if mode == "ua" else "false"),
                            "--brain-arg",
                            "quality_control_accept_shadow:="
                            + ("true" if mode == "ua" else "false"),
                            "--brain-arg",
                            "quality_control_calibration_domain:=simulation_proxy",
                        ]
                    )
                if args.full_flow_cable_tracking:
                    cmd.extend(
                        [
                            "--brain-arg",
                            "enable_decision:=false",
                            "--brain-arg",
                            "enable_cable_tracking:=true",
                            "--brain-arg",
                            f"cable_tracking_config:={cable_tracking_config}",
                            "--brain-arg",
                            "enable_cable_mission_autostart:=true",
                            "--brain-arg",
                            f"cable_mission_target_depth:={args.cable_mission_target_depth}",
                            "--brain-arg",
                            f"cable_mission_target_speed_mps:={args.cable_mission_target_speed_mps}",
                            "--brain-arg",
                            f"cable_mission_start_delay_s:={args.cable_mission_start_delay_s}",
                            "--brain-arg",
                            f"cable_mission_publish_duration_s:={float(max(args.duration, 1))}",
                            "--brain-arg",
                            "heading_mode:=SETPOINT",
                        ]
                    )
                print(f"[proxy-cable] ({idx}/{total}) {run_label}", flush=True)
                if args.dry_run:
                    elapsed = 0.0
                    log_path.write_text(
                        "DRY RUN\n" + " ".join(cmd) + "\n",
                        encoding="utf-8",
                    )
                    run_dir = None
                    mcap = None
                    status = "dry_run"
                    returncode = 0
                else:
                    t0 = time.time()
                    child_env = os.environ.copy()
                    if mpc_param_overrides:
                        child_env["AUV_MPC_PARAM_OVERRIDES"] = json.dumps(
                            mpc_param_overrides,
                            separators=(",", ":"),
                        )
                    proc = subprocess.run(
                        cmd,
                        cwd=str(REPO_ROOT),
                        env=child_env,
                        text=True,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        check=False,
                    )
                    elapsed = time.time() - t0
                    returncode = proc.returncode
                    log_path.write_text(proc.stdout, encoding="utf-8", errors="replace")
                    run_dir = parse_run_dir(proc.stdout)
                    mcap = find_mcap(run_dir)
                    status = "ok" if returncode == 0 and mcap is not None and mcap.stat().st_size > 0 else "failed"
                error = ""
                if status not in {"ok", "dry_run"}:
                    error = f"exit={returncode}; mcap={'missing' if mcap is None else 'empty'}"
                    failures.append(f"{run_label}\t{error}")
                rows.append(
                    {
                        "scenario": scenario_name,
                        "bridge_cfg": str(spec.bridge_cfg),
                        "thesis_scenario": str(spec.thesis_scenario),
                        "seed": seed,
                        "mpc_mode": mode,
                        "exogenous_input_sha256": paired_input_hash,
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
        "exogenous_input_sha256",
        "status",
        "duration_s_actual",
        "run_dir",
        "mcap",
        "log",
        "error",
    ]
    write_csv(output_dir / "results.csv", fieldnames, rows)
    (output_dir / "failures.log").write_text("\n".join(failures) + ("\n" if failures else ""), encoding="utf-8")
    rows = enrich_contract_rows_with_control_diagnostics(rows)
    finalize_bundle(output_dir, rows, success_statuses={"ok", "dry_run"})
    ok_count = sum(1 for row in rows if row["status"] in {"ok", "dry_run"})
    print(f"[proxy-cable] done. {ok_count}/{len(rows)} ok. results -> {output_dir / 'results.csv'}", flush=True)
    return 0 if ok_count == len(rows) else 1


if __name__ == "__main__":
    sys.exit(main())

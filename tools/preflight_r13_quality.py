#!/usr/bin/env python3
"""Offline preflight for R13 source-specific proxy confidence.

This script samples each proxy measurement model and the shared quality
estimators. It does not launch PVS, ROS, MPC, or the R13 closed-loop matrix.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

import numpy as np
import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
for path in (
    REPO_ROOT / "sim_holoocean" / "interfaces",
    REPO_ROOT / "brain_linux" / "src" / "auv_control",
):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from cable_quality_sim import (  # noqa: E402
    build_magnetic_block_payload,
    build_sonar_observation_payload,
)
from perception_engine import CablePath, compute_biot_savart_hvdc  # noqa: E402
from auv_decision_ros.perception_quality import (  # noqa: E402
    MagneticQualityEstimator,
    SonarQualityEstimator,
    SourceCalibration,
)


PROXY_CONFIGS = sorted(
    (REPO_ROOT / "config").glob(
        "bridge_params.protocol_udp.pvs.*proxy.yaml"
    )
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Offline R13 source-specific quality preflight."
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--seed", type=int, default=13045)
    parser.add_argument("--minimum-p-track-span", type=float, default=0.12)
    parser.add_argument(
        "--minimum-magnetic-p-detect-span",
        type=float,
        default=0.05,
    )
    return parser.parse_args()


def _finite(values: list[float]) -> list[float]:
    return [float(value) for value in values if math.isfinite(value)]


def _nullable(values: list[float]) -> list[float | None]:
    return [
        float(value) if math.isfinite(value) else None
        for value in values
    ]


def main() -> int:
    args = parse_args()
    if len(PROXY_CONFIGS) != 6:
        raise SystemExit(
            f"expected 6 R13 proxy configs, found {len(PROXY_CONFIGS)}"
        )
    magnetic_calibration = SourceCalibration.from_json(
        REPO_ROOT
        / "brain_linux/config/perception_quality_sim_magnetic.json"
    )
    sonar_calibration = SourceCalibration.from_json(
        REPO_ROOT
        / "brain_linux/config/perception_quality_sim_sonar.json"
    )
    if {
        magnetic_calibration.calibration_domain,
        sonar_calibration.calibration_domain,
    } != {"simulation_proxy"}:
        raise SystemExit("R13 calibrations must use simulation_proxy domain")
    if (
        magnetic_calibration.physical_deployment_approved
        or sonar_calibration.physical_deployment_approved
    ):
        raise SystemExit("simulation calibration cannot be physical-approved")

    magnetic_estimator = MagneticQualityEstimator(
        calibration=magnetic_calibration,
    )
    sonar_estimator = SonarQualityEstimator(
        calibration=sonar_calibration,
    )
    rng = np.random.default_rng(args.seed)
    scenario_rows: list[dict[str, object]] = []
    all_p_track: list[float] = []
    all_magnetic_p_detect: list[float] = []

    for path in PROXY_CONFIGS:
        config = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        cable_points = np.asarray(
            config["cable_path"]["points_ned"],
            dtype=float,
        )
        cable = CablePath(cable_points)
        perception = dict(config.get("perception", {}) or {})
        noise = dict(perception.get("noise", {}) or {})
        sonar_config = dict(perception.get("sonar", {}) or {})
        quality_sim = dict(perception.get("quality_sim", {}) or {})
        segment = cable_points[1] - cable_points[0]
        heading_rad = math.atan2(float(segment[1]), float(segment[0]))
        normal = np.array(
            [-math.sin(heading_rad), math.cos(heading_rad), 0.0]
        )
        center = 0.5 * (cable_points[0] + cable_points[1])

        sonar_p_track: list[float] = []
        magnetic_p_detect: list[float] = []
        measurement_contract_clean = True
        for sample_index, offset_m in enumerate((0.5, 2.0, 6.0)):
            position = center + normal * offset_m
            position[2] = center[2] - 3.0
            field_t = compute_biot_savart_hvdc(
                auv_pos_ned=position,
                cable=cable,
                current_amp=float(perception.get("hvdc_current_amp", 0.0)),
            )
            block = build_magnetic_block_payload(
                field_amplitude_t=field_t,
                block_end_time_s=1.0 + sample_index,
                magnetic_sigma_t=np.asarray(
                    noise.get("magnetic_sigma", [0.0, 0.0, 0.0]),
                    dtype=float,
                ),
                config=dict(quality_sim.get("magnetic", {}) or {}),
                rng=rng,
            )
            magnetic_result = magnetic_estimator.evaluate(
                samples_nt=np.column_stack(
                    (block["x_nt"], block["y_nt"], block["z_nt"])
                ),
                time_s=np.asarray(block["time_offset_s"], dtype=float),
                age_s=0.0,
                data_completeness=float(block["data_completeness"]),
                clipping_ratio=float(block["clipping_ratio"]),
                calibration_valid=bool(block["calibration_valid"]),
            )
            magnetic_p_detect.append(float(magnetic_result.p_detect))

            observation = build_sonar_observation_payload(
                cable_points_ned=cable_points,
                position_ned=position,
                heading_rad=heading_rad,
                sonar_config=sonar_config,
                quality_config=dict(quality_sim.get("sonar", {}) or {}),
                rng=rng,
            )
            measurement_contract_clean &= not any(
                key in observation for key in ("confidence", "p_detect", "p_track")
            )
            points = np.column_stack(
                (observation["point_x_m"], observation["point_y_m"])
            )
            sonar_result = sonar_estimator.evaluate(
                points_body_m=points,
                point_weight=np.asarray(
                    observation["point_weight"],
                    dtype=float,
                ),
                detector_score=float(observation["detector_score"]),
                contrast_to_noise_ratio=float(
                    observation["contrast_to_noise_ratio"]
                ),
                visible_length_m=float(observation["visible_length_m"]),
                ambiguity_margin=float(observation["ambiguity_margin"]),
                field_of_view_truncated=bool(
                    observation["field_of_view_truncated"]
                ),
                age_s=0.0,
                external_reasons=tuple(observation["quality_flags"]),
            )
            sonar_p_track.append(float(sonar_result.p_track))

        finite_track = _finite(sonar_p_track)
        finite_magnetic = _finite(magnetic_p_detect)
        all_p_track.extend(finite_track)
        all_magnetic_p_detect.extend(finite_magnetic)
        scenario_rows.append(
            {
                "scenario": path.stem,
                "config": str(path.relative_to(REPO_ROOT)),
                "config_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "sonar_p_track": _nullable(sonar_p_track),
                "magnetic_p_detect": _nullable(magnetic_p_detect),
                "source_coverage_ok": bool(
                    len(finite_track) == 3 and len(finite_magnetic) == 3
                ),
                "measurement_contract_clean": measurement_contract_clean,
            }
        )

    p_track_span = (
        max(all_p_track) - min(all_p_track) if all_p_track else 0.0
    )
    magnetic_span = (
        max(all_magnetic_p_detect) - min(all_magnetic_p_detect)
        if all_magnetic_p_detect
        else 0.0
    )
    checks = {
        "six_proxy_scenarios_present": len(scenario_rows) == 6,
        "all_sources_covered": all(
            bool(row["source_coverage_ok"]) for row in scenario_rows
        ),
        "no_truth_probability_leak": all(
            bool(row["measurement_contract_clean"]) for row in scenario_rows
        ),
        "sonar_p_track_dynamic_range": (
            p_track_span >= args.minimum_p_track_span
        ),
        "magnetic_p_detect_dynamic_range": (
            magnetic_span >= args.minimum_magnetic_p_detect_span
        ),
        "simulation_calibration_not_physical_approved": True,
    }
    payload = {
        "schema_version": "r13_quality_preflight.v1",
        "passed": all(checks.values()),
        "seed": args.seed,
        "calibration_domain": "simulation_proxy",
        "checks": checks,
        "metrics": {
            "sonar_p_track_min": min(all_p_track, default=None),
            "sonar_p_track_max": max(all_p_track, default=None),
            "sonar_p_track_span": p_track_span,
            "magnetic_p_detect_min": min(
                all_magnetic_p_detect,
                default=None,
            ),
            "magnetic_p_detect_max": max(
                all_magnetic_p_detect,
                default=None,
            ),
            "magnetic_p_detect_span": magnetic_span,
        },
        "scenarios": scenario_rows,
    }
    text = json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if payload["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

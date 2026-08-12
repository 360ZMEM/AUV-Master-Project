from __future__ import annotations

import csv
import json
from pathlib import Path

from tools.experiment_contract import (
    finalize_bundle,
    initialize_bundle,
    validate_bundle,
)


def test_bundle_records_missing_diagnostics_explicitly(tmp_path: Path) -> None:
    config = tmp_path / "scenario.yaml"
    config.write_text("seed: 1\n", encoding="utf-8")
    bundle = tmp_path / "bundle"

    initialize_bundle(
        bundle,
        experiment_id="unit_contract",
        runner="tests/test_experiment_contract.py",
        argv=["pytest"],
        data_layer="unit_test",
        matrix={"scenarios": ["unit"], "seeds": [1]},
        duration_s=1,
        config_paths=[config],
    )
    status = finalize_bundle(
        bundle,
        [
            {
                "scenario": "unit",
                "seed": 1,
                "mpc_mode": "ua",
                "status": "ok",
                "error": "",
            }
        ],
    )

    assert status["state"] == "complete"
    assert status["contract_complete"] is False
    assert "diagnostic contract incomplete" in validate_bundle(bundle)

    with (bundle / "metrics.csv").open(
        "r", encoding="utf-8", newline=""
    ) as handle:
        row = next(csv.DictReader(handle))
    assert row["valid_run"] == "True"
    assert row["effective_sample_count"] == "not_observed"
    assert row["capability_gate_status"] == "not_observed"


def test_bundle_can_be_diagnostically_complete(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    initialize_bundle(
        bundle,
        experiment_id="unit_complete",
        runner="tests/test_experiment_contract.py",
        argv=["pytest"],
        data_layer="unit_test",
        matrix={"scenarios": ["unit"], "seeds": [2]},
        duration_s=1,
    )
    status = finalize_bundle(
        bundle,
        [
            {
                "scenario": "unit",
                "seed": 2,
                "mpc_mode": "ua",
                "status": "ok",
                "effective_sample_count": 100,
                "failure_event_count": 0,
                "capability_gate_status": "passed",
                "solver_wall_time_current_ms": 4.2,
                "fallback_type": "none",
            }
        ],
    )

    assert status["contract_complete"] is True
    assert validate_bundle(bundle) == []
    parsed = json.loads((bundle / "status.json").read_text(encoding="utf-8"))
    assert parsed["valid_run_count"] == 1

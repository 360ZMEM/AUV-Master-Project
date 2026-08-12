"""Tests for mapping controller diagnostics into the experiment contract."""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from tools.aggregate_control_metrics import (
    ControlTopicMetrics,
    build_run_metrics,
    enrich_contract_rows_with_control_diagnostics,
    has_complete_solver_diagnostics,
)


class TestControlDiagnosticAggregation(unittest.TestCase):
    def test_complete_payload_detection(self) -> None:
        payload = {
            "solver_wall_time_current_ms": 12.0,
            "solver_iterations": 8,
            "warm_start_used": True,
            "initial_constraint_violation_max": 1.0,
            "final_constraint_violation_max": 1e-8,
            "final_active_constraint_count": 20,
            "control_period_blocked": False,
            "fallback_type": "none",
        }
        self.assertTrue(has_complete_solver_diagnostics(payload))
        payload.pop("solver_wall_time_current_ms")
        self.assertFalse(has_complete_solver_diagnostics(payload))

    def test_run_summary_populates_r04_fields(self) -> None:
        control = ControlTopicMetrics(
            debug_available=True,
            solver_wall_times_ms=[12.0, 145.0],
            solver_iterations=[8.0, 100.0],
            control_period_blocked_flags=[False, True],
            warm_start_used_flags=[False, True],
            initial_guess_projection_rms_values=[0.4, 0.1],
            initial_constraint_violations=[1.0, 2.0],
            final_constraint_violations=[1e-8, 0.25],
            constraint_slack_enabled_flags=[True, True],
            slack_maximums=[0.0, 0.2],
            slack_l1_values=[0.0, 0.4],
            slack_active_flags=[False, True],
            solver_diagnostic_complete_flags=[True, True],
            fallback_flags=[False, True],
            fallback_types=["none", "last_output"],
            capability_gate_statuses=["passed", "passed"],
        )
        row = build_run_metrics(
            source_row={
                "scenario": "combined",
                "seed": "42",
                "mpc_mode": "ua",
                "status": "ok",
            },
            bag_path=Path("run.mcap"),
            analysis_dir=Path("analysis"),
            summary_metrics={},
            summary_status="reused",
            control_metrics=control,
        )

        self.assertEqual(row["effective_sample_count"], 2)
        self.assertEqual(row["failure_event_count"], 1)
        self.assertEqual(row["capability_gate_status"], "passed")
        self.assertEqual(row["solver_wall_time_current_ms"], 145.0)
        self.assertEqual(row["fallback_type"], "last_output;none")
        self.assertEqual(row["control_period_block_rate"], 0.5)
        self.assertEqual(row["warm_start_used_rate"], 0.5)
        self.assertEqual(row["initial_guess_projection_rms_max"], 0.4)
        self.assertEqual(row["constraint_slack_enabled_rate"], 1.0)
        self.assertEqual(row["slack_max_max"], 0.2)
        self.assertEqual(row["slack_active_rate"], 0.5)
        self.assertEqual(row["solver_diagnostic_complete_rate"], 1.0)

    def test_sweep_row_enrichment_feeds_contract_fields(self) -> None:
        control = ControlTopicMetrics(
            debug_available=True,
            solver_wall_times_ms=[9.0],
            solver_iterations=[6.0],
            control_period_blocked_flags=[False],
            initial_constraint_violations=[0.5],
            final_constraint_violations=[1e-9],
            solver_diagnostic_complete_flags=[True],
            fallback_flags=[False],
            fallback_types=["none"],
            capability_gate_statuses=["passed"],
        )
        with patch(
            "tools.aggregate_control_metrics.parse_control_topics",
            return_value=control,
        ):
            rows = enrich_contract_rows_with_control_diagnostics(
                [
                    {
                        "scenario": "baseline",
                        "seed": 1,
                        "mpc_mode": "ua",
                        "status": "ok",
                        "mcap": "run.mcap",
                    }
                ]
            )

        self.assertEqual(rows[0]["effective_sample_count"], 1)
        self.assertEqual(rows[0]["failure_event_count"], 0)
        self.assertEqual(rows[0]["solver_wall_time_current_ms"], 9.0)
        self.assertEqual(rows[0]["fallback_type"], "none")

    def test_cumulative_counters_override_sparse_debug_snapshots(self) -> None:
        control = ControlTopicMetrics(
            debug_available=True,
            fallback_flags=[True, True],
            control_period_blocked_flags=[True, True],
            solver_attempt_counts=[12, 100],
            solver_success_counts=[11, 97],
            solver_fallback_counts=[1, 3],
            solver_blocked_counts=[1, 5],
        )
        row = build_run_metrics(
            source_row={"status": "ok"},
            bag_path=Path("run.mcap"),
            analysis_dir=Path("analysis"),
            summary_metrics={},
            summary_status="reused",
            control_metrics=control,
        )

        self.assertEqual(row["effective_sample_count"], 100)
        self.assertEqual(row["failure_event_count"], 3)
        self.assertEqual(row["fallback_rate"], 0.03)
        self.assertEqual(row["control_period_block_rate"], 0.05)
        self.assertEqual(row["solver_counter_rate_source"], "cumulative_counter")


if __name__ == "__main__":
    unittest.main()

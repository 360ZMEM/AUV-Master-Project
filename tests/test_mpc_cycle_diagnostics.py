"""Regression tests for per-cycle MPC solver diagnostics."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest import mock

import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "brain_linux" / "src" / "auv_controller"))

from algorithm.auv_mpc_controller import (  # noqa: E402
    AUVKinematicsModel,
    AUVMPCOptimizer,
    MPCSolveError,
)
from auv_controller.base_controller import ControlOutput  # noqa: E402
from auv_controller.mpc_controller import MPCController  # noqa: E402


def _valid_problem(*, max_iter: int = 100) -> tuple[AUVMPCOptimizer, np.ndarray, np.ndarray]:
    optimizer = AUVMPCOptimizer(
        AUVKinematicsModel({}),
        N=10,
        dt=0.1,
        constraints={"min_speed_ms": 0.1},
        max_iter=max_iter,
    )
    x0 = np.array([0.0, 0.0, 5.0, 0.0, 0.8, 0.0])
    reference = np.tile(x0[:, None], (1, optimizer.N + 1))
    reference[0] = np.arange(optimizer.N + 1) * 0.08
    return optimizer, x0, reference


class TestMpcCycleDiagnostics(unittest.TestCase):
    def test_success_reports_current_cycle_diagnostics(self) -> None:
        optimizer, x0, reference = _valid_problem()
        result = optimizer.solve(x0, reference, confidence=1.0)

        self.assertTrue(result["solver_success"])
        self.assertGreater(result["solver_iterations"], 0)
        self.assertGreater(result["solver_wall_time_current_ms"], 0.0)
        self.assertFalse(result["warm_start_used"])
        self.assertEqual(result["initial_guess_source"], "reference_projected")
        self.assertLess(result["initial_constraint_violation_max"], 1e-6)
        self.assertLess(result["final_constraint_violation_max"], 1e-4)
        self.assertGreater(result["constraint_count"], 0)

        second = optimizer.solve(
            x0 + 0.01,
            reference,
            confidence=1.0,
            warm_start_U=result["U_opt"],
        )
        self.assertTrue(second["warm_start_used"])
        self.assertEqual(second["initial_guess_source"], "warm_shifted_projected")
        self.assertGreater(second["state_initial_jump_l2"], 0.0)

    def test_failure_preserves_wall_time_and_latest_iterate(self) -> None:
        optimizer, x0, reference = _valid_problem(max_iter=1)
        reference[2] = 8.0
        reference[3] = 2.0

        with self.assertRaises(MPCSolveError) as raised:
            optimizer.solve(x0, reference, confidence=0.5)

        diagnostics = raised.exception.diagnostics
        self.assertFalse(diagnostics["solver_success"])
        self.assertEqual(diagnostics["solver_iterations"], 1)
        self.assertGreater(diagnostics["solver_wall_time_current_ms"], 0.0)
        self.assertIsNotNone(diagnostics["final_constraint_violation_max"])
        self.assertEqual(
            diagnostics["solve_time_source"], "wall_perf_counter_failed"
        )

    def test_soft_constraint_slack_is_explicit_and_measured(self) -> None:
        optimizer = AUVMPCOptimizer(
            AUVKinematicsModel({}),
            N=4,
            dt=0.1,
            constraints={
                "min_speed_ms": 0.5,
                "min_thrust_percent": 0.0,
                "max_thrust_percent": 0.0,
                "enable_rate_constraints": False,
                "enable_band_constraints": False,
                "enable_constraint_slack": True,
                "max_speed_slack_ms": 1.0,
                "constraint_slack_weight": 1e3,
            },
        )
        x0 = np.array([0.0, 0.0, 2.0, 0.0, 0.0, 0.0])
        reference = np.tile(x0[:, None], (1, optimizer.N + 1))

        result = optimizer.solve(x0, reference, confidence=1.0)

        self.assertTrue(result["solver_success"])
        self.assertTrue(result["constraint_slack_enabled"])
        self.assertGreater(result["slack_max"], 0.49)
        self.assertGreaterEqual(result["slack_active_count"], optimizer.N)
        self.assertLess(result["final_constraint_violation_max"], 1e-4)

    def test_wrapper_respects_disabled_warm_start(self) -> None:
        controller = MPCController({"mpc": {"warm_start": False}}, {})
        warm_start_arguments = []
        previous_control_arguments = []

        def solve(**kwargs):
            warm_start_arguments.append(kwargs["warm_start_U"])
            previous_control_arguments.append(kwargs["previous_control"])
            return {
                "U_opt": np.zeros((3, controller._N)),
                "X_opt": np.zeros((6, controller._N + 1)),
                "solver_status": "Solve_Succeeded",
                "solve_time_ms": 1.0,
                "solve_time_source": "test",
                "cost_value": 0.0,
                "warm_start_provided": False,
                "warm_start_used": False,
            }

        controller._optimizer.solve = solve
        state = {
            "x": 0.0,
            "y": 0.0,
            "z": 2.0,
            "u": 0.5,
            "v": 0.0,
            "w": 0.0,
            "roll": 0.0,
            "pitch": 0.0,
            "yaw": 0.0,
            "p": 0.0,
            "q": 0.0,
            "r": 0.0,
        }
        setpoint = {
            "target_depth_m": 2.0,
            "target_heading_rad": 0.0,
            "target_speed_mps": 1.0,
        }

        controller.compute(state, setpoint)
        controller.compute(state, setpoint)

        self.assertEqual(warm_start_arguments, [None, None])
        self.assertIsNone(previous_control_arguments[0])
        np.testing.assert_allclose(
            previous_control_arguments[1],
            np.zeros(3),
        )
        self.assertIsNone(controller._prev_U)

    def test_experiment_overrides_route_to_mechanism_configs(self) -> None:
        payload = (
            '{"warm_start": 0, "enable_constraint_slack": 1, '
            '"constraint_slack_weight": 250}'
        )
        with mock.patch.dict(
            os.environ,
            {"AUV_MPC_PARAM_OVERRIDES": payload},
            clear=False,
        ):
            controller = MPCController({}, {})

        self.assertFalse(controller._warm_start_enabled)
        self.assertTrue(controller._optimizer.enable_constraint_slack)
        self.assertEqual(controller._optimizer.constraint_slack_weight, 250.0)

    def test_last_output_fallback_does_not_reuse_old_debug(self) -> None:
        controller = MPCController({}, {})
        last_output = ControlOutput(
            thrust_percent=42.0,
            guidance_heading=0.3,
            guidance_depth=2.0,
            debug={"solver_status": "Solve_Succeeded", "solve_time_ms": 7.0},
        )
        controller._last_output = last_output

        error = RuntimeError("forced failure")
        error.diagnostics = {
            "solver_status": "Maximum_Iterations_Exceeded",
            "solver_iterations": 1,
            "solver_wall_time_current_ms": 123.4,
            "solve_time_source": "wall_perf_counter_failed",
            "control_period_ms": 100.0,
            "control_period_blocked": True,
            "warm_start_used": True,
            "initial_constraint_violation_max": 2.0,
            "final_constraint_violation_max": 1.0,
            "final_active_constraint_count": 5,
        }

        def fail(**_kwargs):
            raise error

        controller._optimizer.solve = fail
        state = {
            "x": 0.0,
            "y": 0.0,
            "z": 2.0,
            "u": 0.5,
            "v": 0.0,
            "w": 0.0,
            "roll": 0.0,
            "pitch": 0.0,
            "yaw": 0.0,
            "p": 0.0,
            "q": 0.0,
            "r": 0.0,
        }
        output = controller.compute(
            state,
            {
                "target_depth_m": 2.0,
                "target_heading_rad": 0.0,
                "target_speed_mps": 1.0,
            },
        )

        self.assertIsNot(output, last_output)
        self.assertEqual(last_output.debug["solver_status"], "Solve_Succeeded")
        self.assertEqual(output.thrust_percent, 42.0)
        self.assertEqual(output.debug["solver_wall_time_current_ms"], 123.4)
        self.assertTrue(output.debug["control_period_blocked"])
        self.assertEqual(output.debug["fallback_type"], "last_output")


if __name__ == "__main__":
    unittest.main()

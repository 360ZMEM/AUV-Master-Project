"""Regression checks for MPC configuration parity across launch profiles."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "brain_linux" / "src" / "auv_controller"))

from auv_controller.mpc_controller import MPCController  # noqa: E402


class TestMpcConfigProfiles(unittest.TestCase):
    def test_arbiter_profile_keeps_canonical_mpc_sections(self) -> None:
        config_dir = PROJECT_ROOT / "brain_linux" / "config"
        canonical = yaml.safe_load(
            (config_dir / "params.yaml").read_text(encoding="utf-8")
        )
        arbiter = yaml.safe_load(
            (config_dir / "params.protocol_udp_arbiter.yaml").read_text(
                encoding="utf-8"
            )
        )

        for section in ("mpc", "mpc_model", "mpc_weights", "mpc_constraints"):
            self.assertEqual(arbiter[section], canonical[section], section)

    def test_canonical_sections_reach_controller(self) -> None:
        config = yaml.safe_load(
            (
                PROJECT_ROOT / "brain_linux" / "config" / "params.yaml"
            ).read_text(encoding="utf-8")
        )
        controller_config = dict(config["control"])
        for section in ("mpc", "mpc_model", "mpc_weights", "mpc_constraints"):
            controller_config[section] = config[section]

        controller = MPCController(controller_config, config["limits"])

        self.assertEqual(controller._N, 20)
        self.assertEqual(controller._dt, 0.2)
        self.assertTrue(controller._warm_start_enabled)
        self.assertEqual(controller._optimizer.W_z, 40.0)
        self.assertEqual(controller._optimizer.W_psi, 80.0)
        self.assertEqual(controller._optimizer.delta_z_max_per_step, 1.0)
        self.assertAlmostEqual(
            controller._optimizer.delta_psi_max_per_step,
            0.0419,
        )


if __name__ == "__main__":
    unittest.main()

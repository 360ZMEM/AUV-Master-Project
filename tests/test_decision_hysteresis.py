"""Regression tests for equivalent BT/FSM confidence filtering."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "brain_linux" / "src"))

from auv_decision.auv_decision_core.bt_engine import DecisionTreeEngine  # noqa: E402
from auv_decision.auv_decision_core.decision_filters import (  # noqa: E402
    ConfidenceHysteresisGate,
)
from auv_decision.auv_decision_core.fsm_baseline import (  # noqa: E402
    FiniteStateMachineEngine,
)
from auv_decision.auv_decision_core.models import SensorStatusData  # noqa: E402


def tick_bt(engine: DecisionTreeEngine, sensor: SensorStatusData) -> str:
    engine.set_sensor_status(sensor)
    engine.tick()
    return str((engine.get_target_motion_state() or {}).get("mode", "UNKNOWN"))


class TestDecisionHysteresis(unittest.TestCase):
    def test_gate_requires_band_crossing_and_consecutive_samples(self) -> None:
        gate = ConfidenceHysteresisGate(
            threshold=0.7,
            hysteresis=0.08,
            debounce_ticks=3,
        )
        self.assertTrue(gate.update(0.8))
        for value in (0.69, 0.65, 0.67, 0.65):
            self.assertTrue(gate.update(value))
        self.assertTrue(gate.update(0.65))
        self.assertFalse(gate.update(0.65))

    def test_bt_and_fsm_use_identical_filtered_modes(self) -> None:
        kwargs = {
            "confidence_threshold": 0.7,
            "confidence_hysteresis": 0.08,
            "confidence_debounce_ticks": 3,
        }
        bt = DecisionTreeEngine(**kwargs)
        fsm = FiniteStateMachineEngine(**kwargs)
        warmup = SensorStatusData(
            confidence=0.8,
            depth_m=4.0,
            auto_state="ACTIVE",
        )
        tick_bt(bt, warmup)
        fsm.tick(warmup)
        fsm.tick(warmup)
        sequence = [0.8, 0.69, 0.65, 0.65, 0.65, 0.71, 0.75, 0.75, 0.75]
        bt_modes = []
        fsm_modes = []
        for confidence in sequence:
            sensor = SensorStatusData(
                confidence=confidence,
                depth_m=4.0,
                auto_state="ACTIVE",
            )
            bt_modes.append(tick_bt(bt, sensor))
            fsm_modes.append(fsm.tick(sensor).mode)
        self.assertEqual(bt_modes, fsm_modes)

    def test_emergency_response_remains_one_tick(self) -> None:
        kwargs = {
            "confidence_threshold": 0.7,
            "confidence_hysteresis": 0.08,
            "confidence_debounce_ticks": 3,
        }
        bt = DecisionTreeEngine(**kwargs)
        fsm = FiniteStateMachineEngine(**kwargs)
        safe = SensorStatusData(
            confidence=0.8,
            depth_m=4.0,
            auto_state="ACTIVE",
        )
        tick_bt(bt, safe)
        fsm.tick(safe)
        sensor = SensorStatusData(
            confidence=0.8,
            depth_m=4.0,
            leak_level=1,
            auto_state="ACTIVE",
        )
        self.assertEqual(tick_bt(bt, sensor), "EMERGENCY_SURFACE")
        self.assertEqual(fsm.tick(sensor).mode, "EMERGENCY_SURFACE")


if __name__ == "__main__":
    unittest.main()

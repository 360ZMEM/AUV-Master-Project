"""Shared stateful decision filters used by BT and FSM implementations."""

from __future__ import annotations


class ConfidenceHysteresisGate:
    """Schmitt trigger with consecutive-sample confirmation."""

    def __init__(
        self,
        *,
        threshold: float = 0.7,
        hysteresis: float = 0.0,
        debounce_ticks: int = 1,
    ) -> None:
        self.threshold = float(threshold)
        self.hysteresis = max(0.0, float(hysteresis))
        self.debounce_ticks = max(1, int(debounce_ticks))
        self.reset()

    def reset(self) -> None:
        self._precise: bool | None = None
        self._pending: bool | None = None
        self._pending_ticks = 0

    def update(self, confidence: float) -> bool:
        value = float(confidence)
        if self._precise is None:
            self._precise = value > self.threshold
            return self._precise

        half_band = self.hysteresis / 2.0
        enter_threshold = self.threshold + half_band
        exit_threshold = self.threshold - half_band
        desired = self._precise
        if self._precise and value < exit_threshold:
            desired = False
        elif not self._precise and value > enter_threshold:
            desired = True

        if desired == self._precise:
            self._pending = None
            self._pending_ticks = 0
            return self._precise

        if self._pending != desired:
            self._pending = desired
            self._pending_ticks = 1
        else:
            self._pending_ticks += 1
        if self._pending_ticks >= self.debounce_ticks:
            self._precise = desired
            self._pending = None
            self._pending_ticks = 0
        return self._precise

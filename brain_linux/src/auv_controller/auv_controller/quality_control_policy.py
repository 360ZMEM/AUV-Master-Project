"""Conservative P6 mapping from tracking authority to controller inputs."""

from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np


MODE_HOLD = 0
MODE_SEARCH = 1
MODE_TRACK = 2


@dataclass(frozen=True)
class AuthoritySnapshot:
    mode: int
    tracking_authorized: bool
    p_track: float
    calibration_domain: str
    shadow_only: bool
    age_s: float


@dataclass(frozen=True)
class QualityControlDecision:
    accepted: bool
    reason: str
    target_speed_mps: float
    confidence: float | None
    delta_u_penalty_scale: float
    safety_margin_scale: float


class ConservativeQualityControlPolicy:
    def __init__(
        self,
        *,
        enabled: bool = False,
        accept_shadow: bool = False,
        allowed_calibration_domain: str = "physical",
        maximum_age_s: float = 0.75,
        minimum_speed_scale: float = 0.35,
        maximum_delta_u_penalty_scale: float = 4.0,
        maximum_safety_margin_scale: float = 1.5,
    ) -> None:
        self.enabled = bool(enabled)
        self.accept_shadow = bool(accept_shadow)
        self.allowed_calibration_domain = str(
            allowed_calibration_domain
        )
        self.maximum_age_s = float(maximum_age_s)
        self.minimum_speed_scale = float(
            np.clip(minimum_speed_scale, 0.0, 1.0)
        )
        self.maximum_delta_u_penalty_scale = max(
            float(maximum_delta_u_penalty_scale),
            1.0,
        )
        self.maximum_safety_margin_scale = max(
            float(maximum_safety_margin_scale),
            1.0,
        )

    def apply(
        self,
        target_speed_mps: float,
        authority: AuthoritySnapshot | None,
    ) -> QualityControlDecision:
        speed = max(float(target_speed_mps), 0.0)
        if not self.enabled:
            return self._rejected("disabled", speed)
        if authority is None:
            return self._rejected("authority_missing", speed)
        if authority.calibration_domain != self.allowed_calibration_domain:
            return self._rejected("calibration_domain_mismatch", speed)
        if authority.shadow_only and not self.accept_shadow:
            return self._rejected("shadow_authority_rejected", speed)
        if not math.isfinite(authority.age_s) or authority.age_s > self.maximum_age_s:
            return self._rejected("authority_stale", speed)

        if authority.mode == MODE_HOLD:
            probability = 0.0
            speed_out = 0.0
        elif authority.mode == MODE_SEARCH:
            probability = (
                float(np.clip(authority.p_track, 0.0, 1.0))
                if math.isfinite(authority.p_track)
                else 0.0
            )
            speed_out = speed * self.minimum_speed_scale
        elif authority.mode == MODE_TRACK and authority.tracking_authorized:
            if not math.isfinite(authority.p_track):
                return self._rejected("track_probability_missing", speed)
            probability = float(np.clip(authority.p_track, 0.0, 1.0))
            speed_scale = self.minimum_speed_scale + (
                1.0 - self.minimum_speed_scale
            ) * probability
            speed_out = speed * speed_scale
        else:
            return self._rejected("tracking_not_authorized", speed)

        uncertainty = 1.0 - probability
        return QualityControlDecision(
            accepted=True,
            reason="accepted",
            target_speed_mps=speed_out,
            confidence=probability,
            delta_u_penalty_scale=1.0
            + (self.maximum_delta_u_penalty_scale - 1.0) * uncertainty,
            safety_margin_scale=1.0
            + (self.maximum_safety_margin_scale - 1.0) * uncertainty,
        )

    @staticmethod
    def _rejected(reason: str, speed: float) -> QualityControlDecision:
        return QualityControlDecision(
            accepted=False,
            reason=reason,
            target_speed_mps=speed,
            confidence=None,
            delta_u_penalty_scale=1.0,
            safety_margin_scale=1.0,
        )

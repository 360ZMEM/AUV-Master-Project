from __future__ import annotations

from auv_controller.quality_control_policy import (
    AuthoritySnapshot,
    ConservativeQualityControlPolicy,
    MODE_HOLD,
    MODE_TRACK,
)


def _authority(
    *,
    mode: int = MODE_TRACK,
    p_track: float = 0.5,
    shadow_only: bool = True,
) -> AuthoritySnapshot:
    return AuthoritySnapshot(
        mode=mode,
        tracking_authorized=mode == MODE_TRACK,
        p_track=p_track,
        calibration_domain="simulation_proxy",
        shadow_only=shadow_only,
        age_s=0.1,
    )


def test_policy_is_disabled_by_default() -> None:
    decision = ConservativeQualityControlPolicy().apply(
        1.0,
        _authority(),
    )
    assert decision.accepted is False
    assert decision.target_speed_mps == 1.0


def test_policy_rejects_shadow_without_explicit_simulation_gate() -> None:
    policy = ConservativeQualityControlPolicy(
        enabled=True,
        allowed_calibration_domain="simulation_proxy",
    )
    decision = policy.apply(1.0, _authority())
    assert decision.accepted is False
    assert decision.reason == "shadow_authority_rejected"


def test_policy_reduces_speed_and_increases_delta_penalty() -> None:
    policy = ConservativeQualityControlPolicy(
        enabled=True,
        accept_shadow=True,
        allowed_calibration_domain="simulation_proxy",
        minimum_speed_scale=0.4,
        maximum_delta_u_penalty_scale=5.0,
    )
    decision = policy.apply(1.0, _authority(p_track=0.5))
    assert decision.accepted is True
    assert abs(decision.target_speed_mps - 0.7) < 1.0e-9
    assert abs(decision.delta_u_penalty_scale - 3.0) < 1.0e-9

    hold = policy.apply(1.0, _authority(mode=MODE_HOLD, p_track=0.0))
    assert hold.accepted is True
    assert hold.target_speed_mps == 0.0

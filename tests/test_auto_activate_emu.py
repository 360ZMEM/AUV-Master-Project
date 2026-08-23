from __future__ import annotations

import json

from scripts.auto_activate_emu import _build_payload


def test_activation_payload_can_carry_valid_hold_depth() -> None:
    payload = json.loads(_build_payload(7, target_depth_m=12.0))

    assert payload["frame_number"] == 7
    assert payload["control_mode_byte"] == 0xEE
    assert payload["target_depth_m"] == 12.0


def test_activation_payload_omits_depth_when_not_configured() -> None:
    payload = json.loads(_build_payload(8))

    assert "target_depth_m" not in payload

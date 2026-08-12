from __future__ import annotations

import json

import numpy as np

from auv_decision_ros.perception_quality_node import _json_safe


def test_json_safe_maps_nested_nonfinite_values_to_null() -> None:
    payload = _json_safe(
        {
            "finite": np.float64(0.75),
            "nested": [float("nan"), np.array([1.0, float("inf")])],
        }
    )

    assert payload == {
        "finite": 0.75,
        "nested": [None, [1.0, None]],
    }
    assert json.dumps(payload, allow_nan=False)

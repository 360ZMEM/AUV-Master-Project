from __future__ import annotations

import json

from auv_bridge.bridge_node import AUVBridgeNode
from common.enums import BridgeBackend


class _DummyPublisher:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def publish(self, msg) -> None:
        self.messages.append(str(msg.data))


def _status_node() -> AUVBridgeNode:
    node = AUVBridgeNode.__new__(AUVBridgeNode)
    node.mag_extrinsics_status_topic = "/auv/sensors/magnetic_extrinsics_status"
    node.magnetic_key = "rt/auv/sensors/magnetic"
    node.backend = BridgeBackend.PROTOCOL_UDP
    node.magnetic_msg_frame_id = "auv/base_link"
    return node


def test_magnetic_extrinsics_static_status_uses_estimated_config_only() -> None:
    node = _status_node()

    status = node._build_magnetic_extrinsics_static_status(
        {
            "sensor_extrinsics_truth": {
                "mag": {
                    "translation_b_m": [9.0, 9.0, 9.0],
                    "rotation_rpy_deg": [9.0, 9.0, 9.0],
                }
            },
            "sensor_extrinsics_estimated": {
                "mag": {
                    "translation_b_m": [0.2, 0.03, -0.02],
                    "rotation_rpy_deg": [0.0, 0.0, 0.5],
                }
            },
            "metadata": {"mag_extrinsics_source": "results/mag_extrinsics/estimated_extrinsics.yaml"},
        },
        "config/bridge_params.protocol_udp.pvs.mag_estimated.yaml",
    )

    assert status["uses_estimated_extrinsics"] is True
    assert status["estimated_translation_b_m"] == [0.2, 0.03, -0.02]
    assert status["estimated_rotation_rpy_deg"] == [0.0, 0.0, 0.5]
    assert status["estimated_extrinsics_source"] == "results/mag_extrinsics/estimated_extrinsics.yaml"
    assert status["truth_extrinsics_exported"] is False
    assert "sensor_extrinsics_truth" not in json.dumps(status)
    assert [9.0, 9.0, 9.0] != status["estimated_translation_b_m"]


def test_magnetic_extrinsics_status_is_low_rate_and_hashes_sim_position() -> None:
    node = _status_node()
    node.mag_extrinsics_status_pub = _DummyPublisher()
    node.mag_extrinsics_status_enabled = True
    node.mag_extrinsics_status_period_s = 1.0
    node.mag_extrinsics_status_include_hash = True
    node._last_mag_extrinsics_status_pub_ts = 0.0
    node._magnetic_sample_count = 50
    node._mag_extrinsics_static_status = node._build_magnetic_extrinsics_static_status(
        {
            "sensor_extrinsics_estimated": {
                "mag": {
                    "translation_b_m": [0.2, 0.03, -0.02],
                    "rotation_rpy_deg": [0.0, 0.0, 0.5],
                }
            }
        },
        "config/bridge_params.protocol_udp.pvs.yaml",
    )

    payload = {
        "sensor_frame": "mag_link",
        "sensor_position_ned": [1.234, 2.0, -3.0],
        "frame_number": 50,
        "sim_time": 12.5,
        "ts": 12.5,
    }
    node._publish_magnetic_extrinsics_status(payload, now=100.0)
    node._publish_magnetic_extrinsics_status(payload, now=100.5)

    assert len(node.mag_extrinsics_status_pub.messages) == 1
    status = json.loads(node.mag_extrinsics_status_pub.messages[0])
    assert status["sample_count"] == 50
    assert status["payload_sensor_frame"] == "mag_link"
    assert status["payload_has_sensor_position_ned"] is True
    assert status["simulator_position_present"] is True
    assert "sensor_position_ned_hash_sha256_16" in status
    assert "sensor_position_ned" not in status
    assert status["truth_extrinsics_exported"] is False

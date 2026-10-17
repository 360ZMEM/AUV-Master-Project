"""Independent sidecar selection must not mix legacy attitude or DVL."""

import pytest

from auv_cable_tracking_v2.inspection_bridge_node import InspectionBridgeNode
from common.enums import BridgeBackend


def test_selected_sidecar_suppresses_legacy_imu_and_legacy_rotated_dvl():
    bridge = InspectionBridgeNode.__new__(InspectionBridgeNode)
    bridge.bridge_cfg = {'inspection_sensor_source': 'imu_sidecar_candidate'}
    bridge.dvl_pub = object()
    assert bridge._publish_protocol_imu(object(), object(), (0., 0., 0., 1.)) is False
    assert bridge._safe_publish_ros(bridge.dvl_pub, object()) is False


def test_sidecar_selection_rejects_nonpassive_before_udp_open():
    bridge = InspectionBridgeNode.__new__(InspectionBridgeNode)
    bridge.bridge_cfg = {'inspection_sensor_source': 'imu_sidecar_candidate'}
    bridge.passive_mode = False
    with pytest.raises(ValueError, match='passive'):
        bridge._create_transport(BridgeBackend.PROTOCOL_UDP)


def test_sidecar_selection_rejects_non_udp_or_non_loopback_before_open():
    bridge = InspectionBridgeNode.__new__(InspectionBridgeNode)
    bridge.bridge_cfg = {
        'inspection_sensor_source': 'imu_sidecar_candidate',
        'protocol_udp': {'local_host': '127.0.0.1', 'remote_host': '127.0.0.1'},
    }
    bridge.passive_mode = True
    with pytest.raises(ValueError, match='loopback protocol UDP'):
        bridge._create_transport(BridgeBackend.ZENOH_JSON)
    bridge.bridge_cfg['protocol_udp']['local_host'] = '0.0.0.0'
    with pytest.raises(ValueError, match='loopback protocol UDP'):
        bridge._create_transport(BridgeBackend.PROTOCOL_UDP)

"""PC104 fault-word propagation into the decision core."""

from types import SimpleNamespace

from auv_decision_ros.decision_node import AUVDecisionNode
from auv_decision_core.bt_engine import DecisionTreeEngine
from auv_decision_core.models import SensorStatusData


class _SensorStatus:
    confidence = 0.9
    leak_level = 0
    battery_low = False
    total_voltage_v = 48.0
    anomaly_detected = False
    depth_m = 4.0
    speed_mps = 0.2
    seabed_depth_m = 10.0
    seabed_clearance_m = 6.0
    seabed_proximity_warning = False
    seabed_penetration_warning = False
    heading_rad = 0.0
    mock_amd_timestamp_us = 0
    debug_level = 0


def _decision_node() -> AUVDecisionNode:
    node = AUVDecisionNode.__new__(AUVDecisionNode)
    node.engine = DecisionTreeEngine(confidence_threshold=0.7)
    node.latest_sensor_status = SensorStatusData(
        confidence=0.9,
        auto_state='ACTIVE',
    )
    node.debug_level = 0
    return node


def test_bit14_survives_sensor_updates_and_forces_safe_hover() -> None:
    node = _decision_node()
    node._on_arbiter_status(
        SimpleNamespace(
            auto_state='DENIED',
            effective_work_instruction=0,
            pc104_sys_abnorm_info=(1 << 14),
            pc104_system_comm_fault=False,
            pc104_dvl_lost=False,
            pc104_jetson_timeout=True,
        )
    )
    node._on_sensor_status(_SensorStatus())
    node.engine.tick()
    goal = node.engine.get_target_motion_state()

    assert node.latest_sensor_status.execution_fault_word == (1 << 14)
    assert node.latest_sensor_status.communication_link_ok is False
    assert goal is not None
    assert goal['mode'] == 'IDLE'
    assert goal['target_speed_mps'] == 0.0


def test_bit13_routes_active_mission_to_relocalization_search() -> None:
    node = _decision_node()
    node._on_arbiter_status(
        SimpleNamespace(
            auto_state='ACTIVE',
            effective_work_instruction=0,
            pc104_sys_abnorm_info=(1 << 13),
            pc104_system_comm_fault=False,
            pc104_dvl_lost=True,
            pc104_jetson_timeout=False,
        )
    )
    node._on_sensor_status(_SensorStatus())
    node.engine.tick()
    goal = node.engine.get_target_motion_state()

    assert node.latest_sensor_status.velocity_aiding_valid is False
    assert goal is not None
    assert goal['mode'] == 'ZIGZAG_SEARCH'

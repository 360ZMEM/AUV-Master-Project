from __future__ import annotations

import sys
from pathlib import Path

PROJECT_SRC = Path(__file__).resolve().parents[1]
project_src_text = str(PROJECT_SRC)
if project_src_text not in sys.path:
    sys.path.insert(0, project_src_text)

INTERFACES_SRC = Path(__file__).resolve().parents[2] / 'auv_interfaces'
interfaces_src_text = str(INTERFACES_SRC)
if interfaces_src_text not in sys.path:
    sys.path.insert(0, interfaces_src_text)

from auv_controller.auv_controller_node import AUVControllerNode
from common.enums import StateEstimateSource
from nav_msgs.msg import Odometry


def _make_odometry(x: float) -> Odometry:
    msg = Odometry()
    msg.pose.pose.position.x = x
    return msg


def test_select_state_prefers_raw_when_bypass_enabled() -> None:
    node = AUVControllerNode.__new__(AUVControllerNode)
    node.bypass_ekf = True
    node.latest_raw_state = _make_odometry(1.0)
    node.latest_filtered_state = _make_odometry(2.0)
    node.latest_raw_state_ts = 3.0
    node.latest_filtered_state_ts = 4.0

    state, source, fallback, timestamp = node._select_state()

    assert state is node.latest_raw_state
    assert source == StateEstimateSource.RAW_DR
    assert fallback is False
    assert timestamp == 3.0


def test_select_state_falls_back_to_filtered_when_raw_missing() -> None:
    node = AUVControllerNode.__new__(AUVControllerNode)
    node.bypass_ekf = True
    node.latest_raw_state = None
    node.latest_filtered_state = _make_odometry(2.0)
    node.latest_raw_state_ts = 0.0
    node.latest_filtered_state_ts = 4.0

    state, source, fallback, timestamp = node._select_state()

    assert state is node.latest_filtered_state
    assert source == StateEstimateSource.FILTERED
    assert fallback is True
    assert timestamp == 4.0


def test_resolve_body_rates_prefers_imu_when_odom_rates_are_zero(monkeypatch) -> None:
    node = AUVControllerNode.__new__(AUVControllerNode)
    node.latest_imu_gyro = (0.1, 0.2, 0.3)
    node.latest_imu_ts = 100.0

    odom = Odometry()
    odom.twist.twist.angular.x = 0.0
    odom.twist.twist.angular.y = 0.0
    odom.twist.twist.angular.z = 0.0

    monkeypatch.setattr("auv_controller.auv_controller_node.time.time", lambda: 100.1)

    p_rate, q_rate, r_rate, source = node._resolve_body_rates(odom)

    assert (p_rate, q_rate, r_rate) == (0.1, 0.2, 0.3)
    assert source == "imu"

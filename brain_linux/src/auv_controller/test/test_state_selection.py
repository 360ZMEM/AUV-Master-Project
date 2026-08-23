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

from auv_controller.auv_controller_node import (
    AUVControllerNode,
    _resolve_guidance_depth,
    _should_publish_semantic_command,
)
from auv_controller.base_controller import ControlOutput
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


def test_guidance_depth_prefers_controller_output() -> None:
    output = ControlOutput(guidance_depth=9.25)

    assert _resolve_guidance_depth(output, fallback_depth_m=11.0) == 9.25


def test_guidance_depth_falls_back_when_output_is_not_finite() -> None:
    output = ControlOutput(guidance_depth=float("nan"))

    assert _resolve_guidance_depth(output, fallback_depth_m=11.0) == 11.0


def test_emergency_depth_override_bypasses_controller_guidance() -> None:
    output = ControlOutput(guidance_depth=11.0)

    assert _resolve_guidance_depth(
        output,
        fallback_depth_m=9.4,
        force_fallback=True,
    ) == 9.4


def test_benchmark_can_route_pid_baseline_through_arbiter() -> None:
    assert _should_publish_semantic_command(
        use_mpc=False,
        is_altitude_follow=False,
        publish_arbiter_command=True,
    )
    assert not _should_publish_semantic_command(
        use_mpc=False,
        is_altitude_follow=False,
        publish_arbiter_command=False,
    )

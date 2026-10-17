"""The candidate gate must fail closed without refreshing estimator provenance."""
import math
from pathlib import Path
import time
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pytest
import rclpy

from auv_interfaces.msg import Setpoint
from nav_msgs.msg import Odometry
from sensor_msgs.msg import MagneticField
from std_msgs.msg import Bool, Float32MultiArray

from auv_cable_tracking_v2.inspection_setpoint_supervisor_node import SetpointAuthority


def ready_authority(now=10.):
    gate = SetpointAuthority()
    candidate = Setpoint()
    candidate.mode = 'CABLE_TRACKING'
    candidate.track_cable = True
    candidate.target_speed_mps = .3
    candidate.target_depth_m = 10.
    candidate.target_heading_rad = .1
    nav = Odometry()
    nav.header.stamp.sec = 10
    nav.pose.pose.orientation.w = 1.
    nav.pose.pose.position.z = -10.
    covariance = [0.] * 225
    covariance[0] = covariance[16] = covariance[48] = covariance[64] = covariance[128] = .01
    gate.update_candidate(candidate, now)
    gate.update_navigation(nav, now)
    magnetic = MagneticField()
    magnetic.header.stamp.sec = 10
    gate.update_magnetic(magnetic, now)
    gate.update_covariance(Float32MultiArray(data=covariance), now)
    gate.update_budget(Bool(data=False), now)
    return gate


def test_stale_candidate_cannot_be_laundered_by_output_heartbeat():
    gate = ready_authority()
    assert gate.problem(10.1) is None
    assert gate.problem(10.36) == 'inspection_candidate_stale'
    invalid = Odometry()
    invalid.pose.pose.position.x = math.nan
    gate.update_navigation(invalid, 10.36)  # Invalid pose must revoke immediately.
    assert gate.problem(10.36) == 'inspection_navigation_stale'


def test_sensor_and_budget_fail_closed_independently():
    gate = ready_authority()
    gate.update_candidate(gate.candidate, 10.55)
    assert gate.problem(10.55) == 'inspection_navigation_stale'
    gate = ready_authority()
    gate.update_magnetic(MagneticField(), 10.49)
    gate.update_covariance(Float32MultiArray(data=[math.nan] * 225), 10.49)
    assert gate.problem(10.49) == 'inspection_covariance_stale'
    gate = ready_authority()
    invalid_cov = [0.] * 225
    invalid_cov[0] = invalid_cov[16] = invalid_cov[128] = .01
    invalid_cov[48] = -.01
    invalid_cov[64] = .01
    gate.update_covariance(Float32MultiArray(data=invalid_cov), 10.1)
    assert gate.problem(10.1) == 'inspection_covariance_stale'
    gate = ready_authority()
    gate.update_budget(Bool(data=True), 10.1)
    gate.update_budget(Bool(data=False), 10.2)
    assert gate.problem(10.2) == 'inspection_recovery_required'


def test_hold_invalid_command_and_budget_status_expiry():
    gate = ready_authority()
    gate.candidate.track_cable = False
    assert gate.problem(10.1) == 'inspection_candidate_hold'
    gate.candidate.track_cable = True
    gate.candidate.target_speed_mps = math.nan
    assert gate.problem(10.1) == 'inspection_candidate_invalid'
    gate = ready_authority()
    gate.update_candidate(gate.candidate, 11.6)
    gate.nav_at = gate.mag_at = gate.cov_at = 11.6
    assert gate.problem(11.6) == 'inspection_budget_status_stale'


def test_longer_candidate_interval_has_displacement_and_sim_clock_limits():
    gate = ready_authority()
    gate.candidate_timeout_s = 1.0
    gate.nav_at = gate.mag_at = gate.cov_at = gate.budget_at = 10.8
    assert gate.problem(10.8, candidate_sim_age_s=.8) is None
    assert gate.problem(10.8, candidate_sim_age_s=1.01) == 'inspection_candidate_source_stale'
    assert gate.problem(10.8, candidate_sim_age_s=float('nan')) == 'inspection_candidate_clock_invalid'
    gate.candidate.target_speed_mps = .8
    assert gate.problem(10.8, candidate_sim_age_s=.8) == 'inspection_candidate_displacement_budget'


def test_late_delivered_navigation_and_magnetic_cannot_refresh_source_age():
    gate = ready_authority()
    late_nav = Odometry()
    late_nav.header.stamp.sec = 10
    late_nav.pose.pose.orientation.w = 1.
    gate.update_navigation(late_nav, 10.7)
    gate.update_candidate(gate.candidate, 10.7)
    gate.mag_at = gate.cov_at = gate.budget_at = 10.7
    assert gate.problem(10.7, source_clock_now_s=10.7) == 'inspection_navigation_source_stale'
    late_nav.header.stamp.sec = 11
    gate.update_navigation(late_nav, 11.)
    late_mag = MagneticField()
    late_mag.header.stamp.sec = 10
    gate.update_magnetic(late_mag, 11.)
    gate.update_candidate(gate.candidate, 11.)
    gate.cov_at = gate.budget_at = 11.
    assert gate.problem(11., source_clock_now_s=11.) == 'inspection_magnetic_source_stale'


def test_snapshot_budget_uses_decision_input_age_and_candidate_source_stamp():
    from auv_cable_tracking_v2.cable_tracking_v2_node import CableTrackingV2Node

    config = Path(__file__).resolve().parents[1] / 'config/cable_tracking_v2_inspection.yaml'
    rclpy.init(args=['--ros-args', '-p', f'config_file:={config}',
                     '-p', 'inspection_snapshot_freshness:=true'])
    try:
        node = CableTrackingV2Node()
        try:
            nav = Odometry()
            nav.header.stamp.sec = 42
            nav.pose.pose.orientation.w = 1.
            nav.pose.pose.position.z = -10.
            snapshot = time.monotonic() - .6
            node.latest_odom = nav
            node._latest_nav_uncertainty = (.1, 1., .01)
            node._tick_snapshot_wall_s = snapshot
            node._tick_snapshot_nav_wall_s = snapshot - .15
            node._tick_snapshot_cov_wall_s = snapshot - .12
            node._tick_snapshot_nav_uncertainty = node._latest_nav_uncertainty
            node._tick_snapshot_nav_msg = nav
            with patch.object(node._hold_budget, 'evaluate', return_value={}) as evaluate:
                node._hold_budget_snapshot('search')
            assert math.isclose(evaluate.call_args.kwargs['navigation_age_s'], .15)
            assert math.isclose(evaluate.call_args.kwargs['covariance_age_s'], .12)
            published = []
            original_pub = node.pub_setpoint
            node.pub_setpoint = SimpleNamespace(publish=published.append)
            try:
                tracking = SimpleNamespace(mode='search', estimated_cable_xy_m=np.array([0., 0.]))
                guidance = SimpleNamespace(safe_lock_active=False, target_depth_m=10.,
                                           desired_heading_deg=0., speed_mps=.3,
                                           guidance_source='test')
                limited = SimpleNamespace(desired_heading_deg=0., speed_mps=.3)
                node._publish_setpoint(tracking, guidance, limited, 10.)
            finally:
                node.pub_setpoint = original_pub
            assert len(published) == 1
            assert published[0].header.stamp.sec == 42
            assert published[0].target_speed_mps > 0.
        finally:
            node.destroy_node()
    finally:
        rclpy.shutdown()


def test_recoverable_input_rejects_direct_final_setpoint_publisher():
    from auv_cable_tracking_v2.cable_tracking_v2_node import CableTrackingV2Node

    config = Path(__file__).resolve().parents[1] / 'config/cable_tracking_v2_flythrough_transient_gate_sim.yaml'
    rclpy.init(args=['--ros-args', '-p', f'config_file:={config}',
                     '-p', 'use_sim_time:=true',
                     '-p', 'inspection_snapshot_freshness:=true',
                     '-p', 'inspection_recoverable_input_stale:=true'])
    try:
        with pytest.raises(ValueError, match='candidate-only Setpoint remap'):
            CableTrackingV2Node()
    finally:
        rclpy.shutdown()

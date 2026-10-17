from types import SimpleNamespace
import time
import pytest
from nav_msgs.msg import Odometry
from auv_interfaces.msg import ArbiterStatus, Setpoint
from auv_cable_tracking_v2.inspection_controller_node import InspectionControllerNode


def fixture():
    odom = Odometry()
    odom.pose.pose.orientation.w = 1.
    sp = Setpoint()
    sp.mode, sp.track_cable = 'CABLE_TRACKING', True
    sp.target_depth_m, sp.target_speed_mps = 10., .5
    status = ArbiterStatus()
    status.active_arbiter, status.autonomy_allowed = 'AUTONOMOUS', True
    now = time.monotonic()
    return SimpleNamespace(latest_setpoint=sp, _inspection_setpoint_received=now,
        _inspection_state_received={'filtered': now, 'raw': now}, _inspection_timeout=1.5,
        _inspection_source_timeout=0.,
        _select_state=lambda: (odom,None,None,None), latest_raw_state=None,
        latest_arbiter_status=status), odom


def test_fresh_valid_tracking_reaches_existing_control_law():
    node, _ = fixture()
    assert InspectionControllerNode._inspection_input_problem(node) is None


@pytest.mark.parametrize('source_s,now_s,expected', [
    (10.0, 10.2, None),
    (10.0, 10.6, 'inspection_setpoint_source_stale'),
    (0.0, 10.2, 'inspection_setpoint_source_clock_invalid'),
    (11.0, 10.2, 'inspection_setpoint_source_clock_invalid'),
])
def test_received_positive_setpoint_retains_source_age(source_s, now_s, expected):
    node, _ = fixture()
    node._inspection_source_timeout = .35
    node.latest_setpoint.header.stamp.sec = int(source_s)
    node.latest_setpoint.header.stamp.nanosec = int((source_s % 1) * 1e9)
    node.get_clock = lambda: SimpleNamespace(
        now=lambda: SimpleNamespace(nanoseconds=int(now_s * 1e9)))
    assert InspectionControllerNode._inspection_input_problem(node) == expected


def test_stale_source_revokes_before_control_law():
    node, _ = fixture()
    node._inspection_source_timeout = .35
    node.latest_setpoint.header.stamp.sec = 10
    node.get_clock = lambda: SimpleNamespace(
        now=lambda: SimpleNamespace(nanoseconds=int(10.6 * 1e9)))
    emitted = []
    node._active_controller = SimpleNamespace(reset=lambda: None)
    node._inspection_last_valid_depth = 10.
    node._publish_zero_effort_hold = lambda **kwargs: emitted.append(kwargs)
    node._inspection_input_problem = lambda: InspectionControllerNode._inspection_input_problem(node)
    InspectionControllerNode._on_timer(node)
    assert emitted[0]['reason'] == 'inspection_setpoint_source_stale'


@pytest.mark.parametrize('fault,reason', [
    ('command_age','inspection_setpoint_stale'), ('state_age','inspection_navigation_stale'),
    ('position_nan','inspection_navigation_invalid'), ('quaternion_zero','inspection_navigation_invalid'),
    ('command_nan','inspection_setpoint_invalid'), ('zero_speed','inspection_requested_hold'),
    ('hold','inspection_requested_hold'), ('wrong_mode','inspection_mission_mode_unavailable'),
    ('arbiter_missing','inspection_autonomy_not_allowed'),
    ('arbiter_remote','inspection_autonomy_not_allowed'),
    ('arbiter_denied','inspection_autonomy_not_allowed'),
])
def test_faults_revoke_control_before_pid_or_mpc(fault,reason):
    node, odom = fixture()
    if fault == 'command_age': node._inspection_setpoint_received -= 2
    if fault == 'state_age': node._inspection_state_received['filtered'] -= 2
    if fault == 'position_nan': odom.pose.pose.position.x = float('nan')
    if fault == 'quaternion_zero': odom.pose.pose.orientation.w = 0.
    if fault == 'command_nan': node.latest_setpoint.target_heading_rad = float('nan')
    if fault == 'zero_speed': node.latest_setpoint.target_speed_mps = 0.
    if fault == 'hold': node.latest_setpoint.track_cable = False
    if fault == 'wrong_mode': node.latest_setpoint.mode = 'OTHER'
    if fault == 'arbiter_missing': node.latest_arbiter_status = None
    if fault == 'arbiter_remote': node.latest_arbiter_status.active_arbiter = 'REMOTE'
    if fault == 'arbiter_denied': node.latest_arbiter_status.autonomy_allowed = False
    assert InspectionControllerNode._inspection_input_problem(node) == reason
    emitted = []
    node._inspection_input_problem = lambda: reason
    node._active_controller = SimpleNamespace(reset=lambda: None)
    node._inspection_last_valid_depth = 10.
    node._publish_zero_effort_hold = lambda **kwargs: emitted.append(kwargs)
    InspectionControllerNode._on_timer(node)
    assert emitted[0]['reason'] == reason
    assert emitted[0]['sp'].target_depth_m == 10.

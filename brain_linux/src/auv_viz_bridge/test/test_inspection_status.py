from auv_viz_bridge.inspection_geometry import inspection_geometry
from auv_viz_bridge.inspection_status import InspectionStatus


def status(**changes):
    return dict(command_sequence=1, timestamp_s=1000., task_status='SOFTWARE_ROUTE_COMPLETE',
                task_status_fresh=True, autonomous_execution_authorized=True,
                authority_reason='', arbiter_mode='AUTONOMOUS',
                arbiter_source='JETSON_MPC', guard_state='ACTIVE', **changes)


def test_completion_expires_and_duplicate_or_old_samples_cannot_refresh_it():
    view = InspectionStatus()
    assert view.accept(status(), 10.)
    assert view.phase(10.1) == 'SOFTWARE_ROUTE_COMPLETE'
    assert not view.accept(status(), 11.4)
    assert view.phase(11.6) == 'STATUS_STALE'
    assert not view.accept({'timestamp_s': 999., 'command_sequence': 0}, 11.7)


def test_unqualified_depth_and_contradictory_authority_are_never_green():
    view = InspectionStatus()
    payload = status()
    payload['guard_state'] = 'DENIED'
    view.accept(payload, 10.)
    geometry = inspection_geometry({'estimated_cable_xy_m': [4.,6.], 'burial_depth_m': 2.,
                                   'diagnostics': {'lateral_valid': True, 'depth_valid': False}}, 12., .1)
    text = view.text(geometry, 10.)
    assert '埋深：UNAVAILABLE' in text and 'DENIED' in text
    assert '软件路线到端 ≠ 艇体停稳' in text
    assert 'UNKNOWN' in view.text(geometry, 12.)


def test_task_freshness_is_independent_of_bridge_receipt():
    view = InspectionStatus()
    payload = status()
    payload['task_status_fresh'] = False
    view.accept(payload, 10.)
    assert view.phase(10.1) == 'STATUS_STALE'

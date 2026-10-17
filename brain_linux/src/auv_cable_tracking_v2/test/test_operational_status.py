from auv_cable_tracking_v2.operational_status import build_operational_status


def status(**changes):
    args = dict(mode='AUTONOMOUS', source='JETSON_MPC', mpc_valid=True,
                guard_state='ACTIVE', guard_reason='NONE', budget_problem=None,
                passive=False, localization_status='LOCALIZED_DEPTH_PENDING',
                localization_fresh=True)
    args.update(changes)
    return build_operational_status(**args)


def test_localized_only_when_bridge_has_authority():
    active = status()
    assert active['autonomous_execution_authorized']
    assert active['localization_status'] == 'LOCALIZED_DEPTH_PENDING'
    for changes, reason in [
        ({'guard_state': 'DENIED', 'guard_reason': 'AMD_UPLINK_STALE'}, 'AMD_UPLINK_STALE'),
        ({'budget_problem': 'inspection_recovery_required'}, 'inspection_recovery_required'),
        ({'mode': 'REMOTE'}, 'remote_mode'),
        ({'source': 'SAFETY_FALLBACK', 'mpc_valid': False}, 'mpc_command_unavailable'),
        ({'passive': True}, 'bridge_passive_mode'),
    ]:
        denied = status(**changes)
        assert not denied['autonomous_execution_authorized']
        assert denied['authority_reason'] == reason
        assert denied['localization_status'] == 'LOCALIZED_DEPTH_PENDING'


def test_stale_localization_is_explicit_without_changing_bridge_authority():
    result = status(localization_fresh=False)
    assert result['localization_status'] == 'UNKNOWN'
    assert not result['localization_status_fresh']
    assert result['autonomous_execution_authorized']

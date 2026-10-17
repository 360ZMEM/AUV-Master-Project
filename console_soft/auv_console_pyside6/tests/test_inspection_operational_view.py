from src.ui.inspection_operational_view import InspectionOperationalView


def make_status(sequence=1, **changes):
    payload = {
        'command_sequence': sequence,
        'timestamp_s': 1000.0 + sequence,
        'autonomous_execution_authorized': True,
        'authority_reason': '',
        'arbiter_mode': 'AUTONOMOUS',
        'arbiter_source': 'JETSON_MPC',
        'guard_state': 'ACTIVE',
        'localization_status': 'LOCALIZED_DEPTH_PENDING',
        'localization_status_fresh': True,
    }
    payload.update(changes)
    return payload


def test_localized_but_bridge_revoked_is_visible():
    view = InspectionOperationalView(timeout_s=1.5)
    assert view.accept(make_status(), now=10.)
    assert view.display(now=10.) == ('定位: 已定位（埋深未许可） | 自治许可: 允许', 'success')
    assert view.accept(make_status(2, autonomous_execution_authorized=False,
                                   authority_reason='AMD_UPLINK_STALE',
                                   arbiter_mode='REMOTE', arbiter_source='PC_RAW',
                                   guard_state='DENIED'), now=10.2)
    assert view.display(now=10.2) == ('定位: 已定位（埋深未许可） | 自治许可: 禁止（上行失鲜）', 'danger')


def test_duplicate_bridge_sample_does_not_refresh_permission():
    view = InspectionOperationalView(timeout_s=1.5)
    old = make_status()
    assert view.accept(old, now=10.)
    assert not view.accept(old, now=11.4)
    assert view.display(now=11.6) == ('定位: 未知 | 自治许可: 未证实（状态失鲜）', 'danger')
    assert view.accept(make_status(1, timestamp_s=1002.), now=11.7)
    assert view.display(now=11.7)[1] == 'success'


def test_malformed_or_stale_localization_never_displays_valid_position():
    view = InspectionOperationalView()
    assert not view.accept({'autonomous_execution_authorized': True}, now=10.)
    assert view.display(now=10.)[0].endswith('未接入')
    assert view.accept(make_status(localization_status_fresh=False), now=10.)
    assert view.display(now=10.) == ('定位: 未知 | 自治许可: 允许', 'success')


def test_out_of_order_or_inconsistent_green_status_is_ignored():
    view = InspectionOperationalView()
    assert view.accept(make_status(3, timestamp_s=1003.,
                                   autonomous_execution_authorized=False,
                                   authority_reason='AMD_UPLINK_STALE',
                                   arbiter_mode='REMOTE', arbiter_source='PC_RAW',
                                   guard_state='DENIED'), now=10.)
    assert not view.accept(make_status(2, timestamp_s=1002.), now=10.1)
    assert not view.accept(make_status(4, timestamp_s=1004., guard_state='DENIED'), now=10.2)
    assert '禁止' in view.display(now=10.2)[0]


def test_task_completion_is_named_as_software_result_and_goes_unknown_when_stale():
    view = InspectionOperationalView()
    assert view.accept(make_status(task_status='SOFTWARE_ROUTE_COMPLETE',
                                   task_status_fresh=True,
                                   localization_status='LOCALIZED_DEPTH_PENDING'), now=10.)
    text, role = view.display(now=10.)
    assert text.startswith('任务: 有限路线到端（软件） | 定位: 已定位（埋深未许可）')
    assert role == 'success'
    assert view.mission_phase_display(now=10.) == ('任务阶段: 有限路线到端（软件）', 'success')
    assert view.accept(make_status(2, task_status='SOFTWARE_ROUTE_COMPLETE',
                                   task_status_fresh=False), now=10.2)
    assert view.display(now=10.2)[0].startswith('任务: 未知 | ')
    assert view.mission_phase_display(now=10.2) == ('任务阶段: 未知（状态失鲜）', 'danger')
    assert view.display(now=11.8)[0] == '定位: 未知 | 自治许可: 未证实（状态失鲜）'
    assert not view.accept(make_status(3, task_status='SOFTWARE_ROUTE_COMPLETE'), now=12.)

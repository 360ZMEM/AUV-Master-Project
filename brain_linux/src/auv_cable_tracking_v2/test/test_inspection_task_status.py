from auv_cable_tracking_v2.inspection_task_status import task_status_from_tracking, task_status_snapshot


def payload(mode, **diagnostics):
    return {"mode": mode, "diagnostics": {
        "inspection_contract_enabled": True, **diagnostics}}


def test_task_outcome_is_separate_from_lateral_and_depth_permission():
    assert task_status_from_tracking(payload(
        "track", endpoint_complete=True, lateral_valid=True,
        depth_valid=False, route_quality_valid=True)) == "SOFTWARE_ROUTE_COMPLETE"
    assert task_status_from_tracking(payload(
        "complete", inspection_enabled=True, endpoint_complete=True,
        depth_valid=False)) == "SOFTWARE_ROUTE_COMPLETE"
    assert task_status_from_tracking(payload(
        "track", endpoint_complete=False, lateral_valid=True,
        depth_valid=False)) == "IN_PROGRESS"


def test_failed_or_unqualified_endpoint_never_becomes_completion():
    assert task_status_from_tracking(payload(
        "hold", endpoint_complete=True, route_quality_valid=True)) == "SUSPENDED"
    assert task_status_from_tracking(payload(
        "track", endpoint_complete=True, route_quality_valid=False)) == "IN_PROGRESS"
    assert task_status_from_tracking(payload(
        "sensor_degraded", endpoint_complete=False)) == "SUSPENDED"
    assert task_status_from_tracking({"mode": "track", "diagnostics": {
        "endpoint_complete": True}}) == "UNKNOWN"
    assert task_status_from_tracking({"mode": "track"}) == "UNKNOWN"


def test_completed_label_expires_without_new_tracking():
    assert task_status_snapshot("SOFTWARE_ROUTE_COMPLETE", 10., 11., 1.5) == (
        "SOFTWARE_ROUTE_COMPLETE", True)
    assert task_status_snapshot("SOFTWARE_ROUTE_COMPLETE", 10., 11.51, 1.5) == (
        "UNKNOWN", False)
    assert task_status_snapshot("SOFTWARE_ROUTE_COMPLETE", 10., 9., 1.5) == (
        "UNKNOWN", False)

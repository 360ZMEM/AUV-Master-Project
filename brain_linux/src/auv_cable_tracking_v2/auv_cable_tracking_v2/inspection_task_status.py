"""A small, fail-closed interpretation of v2 inspection task diagnostics."""
from __future__ import annotations


def task_status_from_tracking(payload: object) -> str:
    """Describe software route progress without implying physical acceptance."""
    if not isinstance(payload, dict):
        return "UNKNOWN"
    diagnostics = payload.get("diagnostics")
    if not isinstance(diagnostics, dict) or not (
            diagnostics.get("inspection_contract_enabled") is True
            or diagnostics.get("inspection_enabled") is True):
        return "UNKNOWN"
    mode = str(payload.get("mode", "")).lower()
    if mode in {"hold", "sensor_degraded"}:
        return "SUSPENDED"
    if (mode in {"track", "complete"}
            and diagnostics.get("endpoint_complete") is True
            and diagnostics.get("route_quality_valid") is not False):
        return "SOFTWARE_ROUTE_COMPLETE"
    if mode in {"search", "confirm", "reacquire", "track"}:
        return "IN_PROGRESS"
    return "UNKNOWN"


def task_status_snapshot(status: str, seen_wall_time_s: float,
                         now_wall_time_s: float, timeout_s: float) -> tuple[str, bool]:
    """Never carry a last-known software completion through a telemetry gap."""
    fresh = 0. <= now_wall_time_s - seen_wall_time_s <= timeout_s
    return (status if fresh else "UNKNOWN"), fresh

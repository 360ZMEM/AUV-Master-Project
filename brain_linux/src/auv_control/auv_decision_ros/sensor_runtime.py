"""Pure-python sensor capability runtime helpers.

Keep mission degradation logic testable without requiring a live ROS runtime.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Any


@dataclass
class SensorWatch:
    name: str
    topic: str
    msg_type: str
    timeout_s: float
    capabilities: list[str] = field(default_factory=list)
    required: bool = False
    description: str = ""
    last_rx_monotonic_s: float | None = None
    message_count: int = 0
    last_error: str | None = None


@dataclass
class SensorGateResult:
    ready: bool
    reason: str
    blocked_sensors: list[str]
    blocked_capabilities: list[str]


def capability_available(runtime_status: dict[str, Any] | None, capability: str) -> bool:
    if not capability:
        return True
    if not isinstance(runtime_status, dict):
        return True
    capabilities = dict(runtime_status.get("capabilities", {}) or {})
    if capability not in capabilities:
        return True
    payload = dict(capabilities.get(capability, {}) or {})
    return bool(payload.get("available", True))


def capability_missing_sensors(runtime_status: dict[str, Any] | None, capability: str) -> list[str]:
    if not capability or not isinstance(runtime_status, dict):
        return []
    capabilities = dict(runtime_status.get("capabilities", {}) or {})
    payload = dict(capabilities.get(capability, {}) or {})
    return [str(item) for item in (payload.get("missing_sensors", []) or [])]


def build_runtime_status_snapshot(
    watches: dict[str, SensorWatch],
    capability_requirements: dict[str, list[str]],
    *,
    now_s: float,
) -> dict[str, Any]:
    sensors: dict[str, Any] = {}
    for name, watch in watches.items():
        age_s = None
        if watch.last_rx_monotonic_s is not None:
            age_s = max(0.0, now_s - float(watch.last_rx_monotonic_s))
        healthy = bool(
            watch.message_count > 0
            and age_s is not None
            and math.isfinite(age_s)
            and age_s <= float(watch.timeout_s)
            and not watch.last_error
        )
        sensors[name] = {
            "topic": watch.topic,
            "msg_type": watch.msg_type,
            "timeout_s": float(watch.timeout_s),
            "healthy": healthy,
            "age_s": age_s,
            "message_count": int(watch.message_count),
            "required": bool(watch.required),
            "capabilities": list(watch.capabilities),
            "description": watch.description,
            "last_error": watch.last_error,
        }

    capabilities: dict[str, Any] = {}
    for capability, required_sensors in capability_requirements.items():
        missing = [
            sensor_name
            for sensor_name in required_sensors
            if not bool(sensors.get(sensor_name, {}).get("healthy", False))
        ]
        capabilities[capability] = {
            "available": not missing,
            "required_sensors": list(required_sensors),
            "missing_sensors": missing,
        }

    required_sensor_names = [name for name, payload in sensors.items() if bool(payload.get("required", False))]
    missing_required = [
        name for name in required_sensor_names if not bool(sensors.get(name, {}).get("healthy", False))
    ]
    autonomy_core = capabilities.get("autonomy_core")
    overall_healthy = bool(
        autonomy_core["available"] if isinstance(autonomy_core, dict) else not missing_required
    )

    return {
        "healthy": overall_healthy,
        "sensors": sensors,
        "capabilities": capabilities,
        "required_sensors": required_sensor_names,
        "missing_required_sensors": missing_required,
        "degraded_capabilities": sorted(
            capability for capability, payload in capabilities.items() if not bool(payload.get("available", False))
        ),
    }


def evaluate_cable_inspection_gate(
    *,
    latest_odom_present: bool,
    latest_odom_wall_time_s: float,
    magnetic_present: bool,
    latest_magnetic_wall_time_s: float,
    latest_runtime_status: dict[str, Any] | None,
    now_s: float,
    navigation_timeout_s: float,
    magnetic_timeout_s: float,
    required_capability: str,
) -> SensorGateResult:
    blocked_sensors: list[str] = []
    blocked_capabilities: list[str] = []

    nav_fresh = bool(
        latest_odom_present
        and latest_odom_wall_time_s > 0.0
        and (now_s - latest_odom_wall_time_s) <= navigation_timeout_s
    )
    if not nav_fresh:
        blocked_sensors.append("navigation")

    magnetic_fresh = bool(
        magnetic_present
        and latest_magnetic_wall_time_s > 0.0
        and (now_s - latest_magnetic_wall_time_s) <= magnetic_timeout_s
    )
    if not magnetic_fresh:
        blocked_sensors.append("magnetic")

    capability_available = True
    if required_capability and isinstance(latest_runtime_status, dict):
        capabilities = dict(latest_runtime_status.get("capabilities", {}) or {})
        capability_payload = dict(capabilities.get(required_capability, {}) or {})
        if capability_payload and not bool(capability_payload.get("available", True)):
            capability_available = False
            blocked_capabilities.append(required_capability)
            for sensor_name in capability_payload.get("missing_sensors", []) or []:
                sensor_name = str(sensor_name)
                if sensor_name and sensor_name not in blocked_sensors:
                    blocked_sensors.append(sensor_name)

    if blocked_sensors or not capability_available:
        if "navigation" in blocked_sensors:
            reason = "navigation_unavailable"
        elif "magnetic" in blocked_sensors:
            reason = "magnetic_unavailable_inspection_blocked"
        elif blocked_capabilities:
            reason = f"{blocked_capabilities[0]}_unavailable"
        else:
            reason = "sensor_capability_degraded"
        return SensorGateResult(
            ready=False,
            reason=reason,
            blocked_sensors=blocked_sensors,
            blocked_capabilities=blocked_capabilities,
        )

    return SensorGateResult(
        ready=True,
        reason="ready",
        blocked_sensors=[],
        blocked_capabilities=[],
    )

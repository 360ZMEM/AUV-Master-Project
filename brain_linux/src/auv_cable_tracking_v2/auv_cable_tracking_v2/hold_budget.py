"""Conservative budget for a cable-inspection Hold.

The monitor only requests an upper-level disposition. It cannot turn zero
thruster effort into station keeping or command a PC104 recovery action.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any

import numpy as np


@dataclass(frozen=True)
class HoldBudgetConfig:
    maximum_hold_s: float
    boundary_stop_margin_m: float
    zero_effort_coast_bound_m: float
    current_bound_mps: float
    disposition_delay_s: float
    navigation_margin_m: float
    maximum_navigation_age_s: float

    @classmethod
    def from_mapping(cls, mapping: dict[str, Any]) -> "HoldBudgetConfig":
        required = tuple(cls.__dataclass_fields__)
        missing = [name for name in required if name not in mapping]
        if missing:
            raise ValueError("hold_budget requires " + ", ".join(missing))
        values = {name: float(mapping[name]) for name in required}
        if not all(math.isfinite(value) and value >= 0 for value in values.values()):
            raise ValueError("hold_budget values must be finite and nonnegative")
        for name in ("maximum_hold_s", "disposition_delay_s", "maximum_navigation_age_s"):
            if values[name] <= 0:
                raise ValueError("hold_budget " + name + " must be positive")
        return cls(**values)


def _clearance_m(point_xy: np.ndarray, polygon_xy: np.ndarray) -> float:
    vertices = np.asarray(polygon_xy, dtype=float)
    point = np.asarray(point_xy, dtype=float)
    if (vertices.ndim != 2 or vertices.shape[1] != 2 or len(vertices) < 3
            or point.shape != (2,) or not np.isfinite(vertices).all()
            or not np.isfinite(point).all()):
        raise ValueError("finite polygon and point required")
    a = vertices
    edges = np.roll(vertices, -1, axis=0) - a
    length2 = np.sum(edges * edges, axis=1)
    if np.any(length2 <= 0):
        raise ValueError("polygon contains zero-length edge")
    # Reject an already-exited polygon; shortest-edge distance alone has no sign.
    x, y = point
    inside = False
    for first, second in zip(vertices, np.roll(vertices, -1, axis=0)):
        if (first[1] > y) != (second[1] > y):
            crossing_x = first[0] + (y - first[1]) * (second[0] - first[0]) / (second[1] - first[1])
            if x < crossing_x:
                inside = not inside
    if not inside:
        return 0.
    fraction = np.clip(np.sum((point - a) * edges, axis=1) / length2, 0., 1.)
    nearest = a + fraction[:, None] * edges
    return float(np.min(np.linalg.norm(nearest - point, axis=1)))


class HoldBudgetMonitor:
    """Latch an alarm for this inspection process lifetime."""

    def __init__(self, config: HoldBudgetConfig | None, boundary_xy_m=None,
                 *, defer_navigation_unavailable: bool = False) -> None:
        self.config = config
        self.boundary_xy_m = None if boundary_xy_m is None else np.asarray(boundary_xy_m, dtype=float)
        self.defer_navigation_unavailable = defer_navigation_unavailable
        self._transient_hold_active = False
        self._hold_start_s: float | None = None
        self._last_hold_now_s: float | None = None
        self._fallback_hold_start_s: float | None = None
        self._last_fallback_now_s: float | None = None
        self._latched_reason: str | None = None

    def reset(self) -> None:
        self._hold_start_s = None
        self._last_hold_now_s = None
        self._fallback_hold_start_s = None
        self._last_fallback_now_s = None
        self._latched_reason = None
        self._transient_hold_active = False

    def latch(self, reason: str) -> None:
        if not reason:
            raise ValueError("nonempty hold budget reason required")
        if self._latched_reason is None:
            self._latched_reason = reason

    def _required_clearance_m(self, horizon_s: float) -> float:
        assert self.config is not None
        return (self.config.boundary_stop_margin_m
                + self.config.zero_effort_coast_bound_m
                + self.config.navigation_margin_m
                + self.config.current_bound_mps *
                (max(0., horizon_s) + self.config.disposition_delay_s))

    def admit_convex_route(self, waypoints_xy_m, *, deviation_bound_m: float) -> dict[str, Any]:
        """Exact minimum clearance along a polyline inside a convex polygon.

        Distance to a convex polygon boundary is concave along each segment,
        so the route minimum occurs at a supplied vertex. Nonconvex boundaries
        are rejected instead of approximated with sparse samples.
        """
        if self.config is None or self.boundary_xy_m is None:
            return {"admitted": False, "reason": "route_hold_budget_unconfigured",
                    "minimum_clearance_m": None, "required_clearance_m": None}
        if not math.isfinite(deviation_bound_m) or deviation_bound_m < 0:
            raise ValueError("finite nonnegative route deviation bound required")
        vertices = self.boundary_xy_m
        try:
            if (vertices.ndim != 2 or vertices.shape[1] != 2 or len(vertices) < 3
                    or not np.isfinite(vertices).all()):
                raise ValueError("invalid boundary")
            edges = np.roll(vertices, -1, axis=0) - vertices
            turns = np.cross(edges, np.roll(edges, -1, axis=0))
            if not (np.all(turns > 1e-9) or np.all(turns < -1e-9)):
                raise ValueError("nonconvex boundary")
            waypoints = np.asarray(waypoints_xy_m, dtype=float)
            if (waypoints.ndim != 2 or waypoints.shape[1] != 2
                    or len(waypoints) < 2 or not np.isfinite(waypoints).all()):
                raise ValueError("invalid route")
            clearance = min(_clearance_m(point, vertices) for point in waypoints)
        except (TypeError, ValueError, OverflowError):
            return {"admitted": False, "reason": "route_boundary_or_geometry_invalid",
                    "minimum_clearance_m": None, "required_clearance_m": None}
        required = self._required_clearance_m(self.config.maximum_hold_s) + deviation_bound_m
        admitted = clearance > required
        return {"admitted": admitted,
                "reason": None if admitted else "route_hold_budget_insufficient",
                "minimum_clearance_m": clearance, "required_clearance_m": required}

    def _assess_position(self, *, position_xy_m, navigation_age_s,
                         navigation_sigma_m, covariance_age_s, horizon_s):
        if self.config is None or self.boundary_xy_m is None:
            return "hold_budget_unconfigured", None, None
        if (navigation_age_s is None or not math.isfinite(navigation_age_s)
                or navigation_age_s < 0
                or navigation_age_s > self.config.maximum_navigation_age_s
                or position_xy_m is None):
            return "hold_navigation_unavailable", None, None
        if (navigation_sigma_m is None or not math.isfinite(navigation_sigma_m)
                or navigation_sigma_m < 0 or covariance_age_s is None
                or not math.isfinite(covariance_age_s) or covariance_age_s < 0
                or covariance_age_s > self.config.maximum_navigation_age_s):
            return "hold_navigation_uncertainty_unavailable", None, None
        if 2. * navigation_sigma_m > self.config.navigation_margin_m:
            return "hold_navigation_uncertainty_exceeds_margin", None, None
        try:
            clearance = _clearance_m(np.asarray(position_xy_m, dtype=float), self.boundary_xy_m)
        except (TypeError, ValueError, OverflowError):
            return "hold_geometry_invalid", None, None
        remaining = clearance - self._required_clearance_m(horizon_s)
        return None, clearance, remaining

    def evaluate_motion(self, *, position_xy_m=None, navigation_age_s=None,
                        navigation_sigma_m=None, covariance_age_s=None,
                        now_s: float | None = None,
                        fallback_now_s: float | None = None) -> dict[str, Any]:
        """Reserve a full Hold response envelope before continuing motion."""
        reason, clearance, remaining = self._assess_position(
            position_xy_m=position_xy_m, navigation_age_s=navigation_age_s,
            navigation_sigma_m=navigation_sigma_m, covariance_age_s=covariance_age_s,
            horizon_s=0. if self.config is None else self.config.maximum_hold_s,
        )
        if reason is None and remaining is not None and remaining <= 0:
            reason = "motion_hold_budget_insufficient"
        if (self.defer_navigation_unavailable and reason in {
                "hold_navigation_unavailable", "hold_navigation_uncertainty_unavailable"}
                and not self.recovery_required):
            if now_s is None:
                raise ValueError("recoverable input Hold requires a time source")
            self._transient_hold_active = True
            return self.evaluate(
                hold=True, now_s=now_s, fallback_now_s=fallback_now_s,
                position_xy_m=position_xy_m, navigation_age_s=navigation_age_s,
                navigation_sigma_m=navigation_sigma_m, covariance_age_s=covariance_age_s,
            )
        if reason is not None:
            self.latch(reason)
        elif self._transient_hold_active and not self.recovery_required:
            # A fresh, valid pose has re-established the full route clearance.
            self._hold_start_s = self._last_hold_now_s = None
            self._fallback_hold_start_s = self._last_fallback_now_s = None
            self._transient_hold_active = False
        return {"state": "RECOVERY_REQUIRED" if self.recovery_required else "MOTION_BUDGET_OK",
                "recovery_required": self.recovery_required, "reason": self.reason,
                "hold_elapsed_s": None, "boundary_clearance_m": clearance,
                "remaining_budget_m": remaining}

    @property
    def recovery_required(self) -> bool:
        return self._latched_reason is not None

    @property
    def reason(self) -> str | None:
        return self._latched_reason

    def evaluate(self, *, hold: bool, now_s: float, fallback_now_s: float | None = None,
                 position_xy_m=None,
                 navigation_age_s: float | None = None,
                 navigation_sigma_m: float | None = None,
                 covariance_age_s: float | None = None) -> dict[str, Any]:
        if not hold:
            # A transient return from Hold must not silently clear escalation.
            return {"state": "RECOVERY_REQUIRED" if self._latched_reason else "INACTIVE",
                    "recovery_required": self._latched_reason is not None,
                    "reason": self._latched_reason,
                    "hold_elapsed_s": None, "boundary_clearance_m": None,
                    "remaining_budget_m": None}
        if not math.isfinite(now_s):
            raise ValueError("finite monotonic time required")
        if fallback_now_s is not None and not math.isfinite(fallback_now_s):
            raise ValueError("finite fallback monotonic time required")
        if self._hold_start_s is None:
            self._hold_start_s = now_s
        if self._last_hold_now_s is not None and now_s < self._last_hold_now_s - 1e-6:
            self.latch("hold_time_regressed")
        self._last_hold_now_s = now_s
        elapsed = max(0., now_s - self._hold_start_s)
        if fallback_now_s is not None:
            if self._fallback_hold_start_s is None:
                self._fallback_hold_start_s = fallback_now_s
            if (self._last_fallback_now_s is not None
                    and fallback_now_s < self._last_fallback_now_s - 1e-6):
                self.latch("hold_fallback_time_regressed")
            self._last_fallback_now_s = fallback_now_s
            elapsed = max(elapsed, fallback_now_s - self._fallback_hold_start_s)
        reason, clearance, remaining = self._assess_position(
            position_xy_m=position_xy_m, navigation_age_s=navigation_age_s,
            navigation_sigma_m=navigation_sigma_m, covariance_age_s=covariance_age_s,
            horizon_s=0. if self.config is None else max(0., self.config.maximum_hold_s - elapsed),
        )
        reason = self._latched_reason or reason
        transient = (self.defer_navigation_unavailable and reason in {
            "hold_navigation_unavailable", "hold_navigation_uncertainty_unavailable"}
            and self._latched_reason is None)
        if transient:
            self._transient_hold_active = True
            if elapsed >= self.config.maximum_hold_s:
                reason = "hold_time_budget_exhausted"
                transient = False
        if reason is None and remaining is not None and remaining <= 0:
            reason = "hold_boundary_budget_exhausted"
        if reason is None and elapsed >= self.config.maximum_hold_s:
            reason = "hold_time_budget_exhausted"
        if reason is not None and not transient:
            self.latch(reason)
        return {"state": ("RECOVERY_REQUIRED" if self._latched_reason else
                          "INPUT_STALE_HOLD" if transient else "WITHIN_BUDGET"),
                "recovery_required": self._latched_reason is not None,
                "reason": self._latched_reason or (reason if transient else None),
                "hold_elapsed_s": elapsed, "boundary_clearance_m": clearance,
                "remaining_budget_m": remaining}

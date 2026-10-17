"""Opt-in, process-isolated Setpoint gate for the inspection algorithm.

The estimator publishes *candidates* only. This small node owns the canonical
Setpoint topic and never extends a candidate's original validity window by
republishing it. The bridge's independent Setpoint watchdog remains in force.
"""

from __future__ import annotations

import math
import threading
import time

import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from auv_interfaces.msg import Setpoint
from nav_msgs.msg import Odometry
from sensor_msgs.msg import MagneticField
from std_msgs.msg import Bool, Float32MultiArray, String


def finite_navigation(msg: Odometry) -> bool:
    p, q = msg.pose.pose.position, msg.pose.pose.orientation
    values = (p.x, p.y, p.z, q.x, q.y, q.z, q.w)
    return (all(math.isfinite(float(value)) for value in values)
            and .9 <= sum(float(value) ** 2 for value in (q.x, q.y, q.z, q.w)) <= 1.1)


def finite_magnetic(msg: MagneticField) -> bool:
    field = msg.magnetic_field
    return all(math.isfinite(float(value)) for value in (field.x, field.y, field.z))


def finite_covariance(msg: Float32MultiArray) -> bool:
    data = msg.data
    if len(data) != 225 or not all(math.isfinite(float(value)) for value in data):
        return False
    for first, second in ((0, 1), (3, 4)):
        a = float(data[first * 15 + first])
        d = float(data[second * 15 + second])
        b = .5 * (float(data[first * 15 + second])
                  + float(data[second * 15 + first]))
        if a <= 0. or d <= 0. or a * d - b * b < -1e-8:
            return False
    return float(data[128]) > 0.


class SetpointAuthority:
    """Wall-clock source-age contract; independent of ROS /clock acceleration."""

    def __init__(self, *, candidate_timeout_s: float = .35,
                 sensor_timeout_s: float = .5, budget_timeout_s: float = 1.5,
                 maximum_candidate_displacement_m: float = .35,
                 declared_current_bound_mps: float = .05):
        values = (candidate_timeout_s, sensor_timeout_s, budget_timeout_s,
                  maximum_candidate_displacement_m)
        if not all(math.isfinite(value) and value > 0. for value in values):
            raise ValueError('supervisor timeouts must be finite and positive')
        if not math.isfinite(declared_current_bound_mps) or declared_current_bound_mps < 0.:
            raise ValueError('declared current bound must be finite and nonnegative')
        self.candidate_timeout_s = candidate_timeout_s
        self.sensor_timeout_s = sensor_timeout_s
        self.budget_timeout_s = budget_timeout_s
        self.maximum_candidate_displacement_m = maximum_candidate_displacement_m
        self.declared_current_bound_mps = declared_current_bound_mps
        self.candidate: Setpoint | None = None
        self.candidate_at = float('-inf')
        self.nav_at = float('-inf')
        self.mag_at = float('-inf')
        self.nav_source_stamp_s = 0.
        self.mag_source_stamp_s = 0.
        self.cov_at = float('-inf')
        self.budget_at = float('-inf')
        self.budget_latched = False
        self.last_depth_m = 0.

    def update_candidate(self, msg: Setpoint, now: float) -> None:
        self.candidate, self.candidate_at = msg, now

    def update_navigation(self, msg: Odometry, now: float) -> None:
        if finite_navigation(msg):
            self.nav_at = now
            stamp = msg.header.stamp
            self.nav_source_stamp_s = stamp.sec + stamp.nanosec * 1e-9
            self.last_depth_m = max(0., min(50., -float(msg.pose.pose.position.z)))
        else:
            self.nav_at = float('-inf')
            self.nav_source_stamp_s = 0.

    def update_magnetic(self, msg: MagneticField, now: float) -> None:
        if finite_magnetic(msg):
            self.mag_at = now
            stamp = msg.header.stamp
            self.mag_source_stamp_s = stamp.sec + stamp.nanosec * 1e-9
        else:
            self.mag_at = float('-inf')
            self.mag_source_stamp_s = 0.

    def update_covariance(self, msg: Float32MultiArray, now: float) -> None:
        self.cov_at = now if finite_covariance(msg) else float('-inf')

    def update_budget(self, msg: Bool, now: float) -> None:
        self.budget_at = now
        self.budget_latched |= bool(msg.data)

    def problem(self, now: float, *, candidate_sim_age_s: float | None = None,
                source_clock_now_s: float | None = None) -> str | None:
        if self.budget_latched:
            return 'inspection_recovery_required'
        if now - self.budget_at > self.budget_timeout_s:
            return 'inspection_budget_status_stale'
        for name, at in (('navigation', self.nav_at), ('magnetic', self.mag_at),
                         ('covariance', self.cov_at)):
            if now - at > self.sensor_timeout_s:
                return f'inspection_{name}_stale'
        if source_clock_now_s is not None:
            for name, stamp_s in (('navigation', self.nav_source_stamp_s),
                                  ('magnetic', self.mag_source_stamp_s)):
                age = source_clock_now_s - stamp_s
                if (not math.isfinite(age) or stamp_s <= 0. or age < -.1):
                    return f'inspection_{name}_source_clock_invalid'
                if age > self.sensor_timeout_s:
                    return f'inspection_{name}_source_stale'
        wall_age = now - self.candidate_at
        if self.candidate is None or wall_age > self.candidate_timeout_s:
            return 'inspection_candidate_stale'
        if candidate_sim_age_s is not None:
            if not math.isfinite(candidate_sim_age_s) or candidate_sim_age_s < -.1:
                return 'inspection_candidate_clock_invalid'
            if candidate_sim_age_s > self.candidate_timeout_s:
                return 'inspection_candidate_source_stale'
        sp = self.candidate
        if sp.mode != 'CABLE_TRACKING' or not sp.track_cable or sp.target_speed_mps <= 0.:
            return 'inspection_candidate_hold'
        values = (sp.target_speed_mps, sp.target_depth_m, sp.target_heading_rad,
                  sp.target_x_m, sp.target_y_m)
        if (not all(math.isfinite(float(value)) for value in values)
                or not 0. < sp.target_speed_mps <= .800001
                or not 0. <= sp.target_depth_m <= 50.):
            return 'inspection_candidate_invalid'
        age = max(wall_age, candidate_sim_age_s or 0.)
        if ((float(sp.target_speed_mps) + self.declared_current_bound_mps) * age
                > self.maximum_candidate_displacement_m):
            return 'inspection_candidate_displacement_budget'
        return None


class InspectionSetpointSupervisorNode(Node):
    def __init__(self) -> None:
        super().__init__('auv_inspection_setpoint_supervisor')
        self.declare_parameter('candidate_timeout_s', .35)
        self.declare_parameter('sensor_timeout_s', .5)
        self.declare_parameter('budget_timeout_s', 1.5)
        self.declare_parameter('maximum_candidate_displacement_m', .35)
        self.declare_parameter('declared_current_bound_mps', .05)
        self.declare_parameter('output_period_s', .1)
        self.declare_parameter('output_thread_enabled', False)
        self._output_thread_enabled = bool(self.get_parameter('output_thread_enabled').value)
        self.authority = SetpointAuthority(**{
            name: float(self.get_parameter(name).value)
            for name in ('candidate_timeout_s', 'sensor_timeout_s', 'budget_timeout_s',
                         'maximum_candidate_displacement_m', 'declared_current_bound_mps')
        })
        period = float(self.get_parameter('output_period_s').value)
        if not math.isfinite(period) or not 0. < period <= self.authority.candidate_timeout_s:
            raise ValueError('output period must be positive and no longer than candidate timeout')
        self._output_period_s = period
        self._authority_lock = threading.Lock()
        self._stop_output = threading.Event()
        self._output_thread = None
        self.pub_setpoint = self.create_publisher(Setpoint, '/auv/control/setpoint', 10)
        self.pub_reason = self.create_publisher(String, '/auv/cable/setpoint_supervisor_reason', 10)
        self.create_subscription(Setpoint, '/auv/control/setpoint_candidate',
                                 lambda msg: self._update_authority('update_candidate', msg), 10)
        self.create_subscription(Odometry, '/auv/state/filtered',
                                 lambda msg: self._update_authority('update_navigation', msg), 10)
        self.create_subscription(MagneticField, '/auv/sensors/magnetic',
                                 lambda msg: self._update_authority('update_magnetic', msg), 10)
        self.create_subscription(Float32MultiArray, '/auv/state/covariance',
                                 lambda msg: self._update_authority('update_covariance', msg), 10)
        self.create_subscription(Bool, '/auv/cable/recovery_required',
                                 lambda msg: self._update_authority('update_budget', msg), 10)
        if self._output_thread_enabled:
            self._output_thread = threading.Thread(target=self._output_loop,
                                                   name='inspection_setpoint_output', daemon=True)
            self._output_thread.start()
        else:
            self.create_timer(period, self._on_tick)

    def _update_authority(self, method: str, msg) -> None:
        with self._authority_lock:
            getattr(self.authority, method)(msg, time.monotonic())

    def _output_loop(self) -> None:
        next_tick = time.monotonic()
        while not self._stop_output.is_set() and rclpy.ok():
            if self._stop_output.wait(max(0., next_tick - time.monotonic())):
                break
            try:
                self._on_tick()
            except Exception as exc:
                self.get_logger().error(f'inspection output thread stopped: {exc}')
                break
            next_tick += self._output_period_s
            if next_tick < time.monotonic():
                next_tick = time.monotonic() + self._output_period_s

    def destroy_node(self):
        self._stop_output.set()
        if self._output_thread is not None:
            self._output_thread.join(timeout=2.)
        return super().destroy_node()

    def _on_tick(self) -> None:
        clock_now_s = self.get_clock().now().nanoseconds * 1e-9
        with self._authority_lock:
            candidate = self.authority.candidate
            stamp = candidate.header.stamp if candidate is not None else None
            stamp_s = (stamp.sec + stamp.nanosec * 1e-9) if stamp is not None else 0.
            source_age_s = (clock_now_s - stamp_s
                            if clock_now_s > 0. and stamp_s > 0. else float('nan'))
            problem = self.authority.problem(time.monotonic(), candidate_sim_age_s=source_age_s,
                                             source_clock_now_s=clock_now_s)
            hold_depth_m = self.authority.last_depth_m
            if problem is None:
                # Preserve the estimator's header stamp to expose true provenance.
                self.pub_setpoint.publish(candidate)
            else:
                hold = Setpoint()
                hold.header.stamp = self.get_clock().now().to_msg()
                hold.mode = 'CABLE_TRACKING_DEGRADED_HOLD'
                hold.bridge_backend = 'protocol_udp'
                hold.target_depth_m = hold_depth_m
                hold.target_speed_mps = 0.
                hold.track_cable = False
                hold.high_priority = True
                hold.note = 'v2_supervisor:' + problem
                self.pub_setpoint.publish(hold)
        self.pub_reason.publish(String(data=problem or ''))


def main() -> None:
    rclpy.init()
    node = InspectionSetpointSupervisorNode()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    except Exception:
        # SIGTERM may invalidate the ROS context while spin constructs its
        # next wait set. Only suppress that shutdown race, not live failures.
        if rclpy.ok():
            raise
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()

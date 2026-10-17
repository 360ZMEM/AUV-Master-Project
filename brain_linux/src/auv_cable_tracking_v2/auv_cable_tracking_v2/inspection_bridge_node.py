"""Inspection bridge with an independent autonomous stop gate."""
from dataclasses import replace
import json
import math
import time

import rclpy
from rclpy.executors import ExternalShutdownException
from std_msgs.msg import Bool, String
from auv_interfaces.msg import Setpoint

from auv_bridge.bridge_node import AUVBridgeNode
from common.enums import ArbiterMode, ArbiterSource, AutoState, BridgeBackend, DenyReason, WorkInstruction
from common.protocol import (KEY_BOTTOM, KEY_LEFT, KEY_NOTE, KEY_RIGHT,
                             KEY_SIDE_MOTOR_RPM, KEY_THRUST, KEY_TOP,
                             KEY_WORK_INSTRUCTION)
from .operational_status import build_operational_status
from .inspection_task_status import task_status_from_tracking, task_status_snapshot


class InspectionBridgeNode(AUVBridgeNode):
    def _create_transport(self, backend):
        # Base construction opens the UDP transport. Reject unsafe source
        # selection before that happens, not after the subclass initializes.
        source = self.bridge_cfg.get('inspection_sensor_source', 'legacy')
        if source not in {'legacy', 'imu_sidecar_candidate'}:
            raise ValueError('inspection_sensor_source must be legacy or imu_sidecar_candidate')
        if source == 'imu_sidecar_candidate' and not self.passive_mode:
            raise ValueError('IMU sidecar candidate requires passive inspection bridge')
        if source == 'imu_sidecar_candidate':
            udp = self.bridge_cfg.get('protocol_udp', {})
            if (backend != BridgeBackend.PROTOCOL_UDP
                    or udp.get('local_host') != '127.0.0.1'
                    or udp.get('remote_host') != '127.0.0.1'
                    or udp.get('zenoh_side_channel_enabled', False)):
                raise ValueError('IMU sidecar candidate requires isolated loopback protocol UDP')
            self.body_dvl_candidate_pub = self.create_publisher(
                String, '/auv/sensors/dvl_body_pc104_candidate', 10)
        return super()._create_transport(backend)

    def __init__(self):
        super().__init__(node_name='auv_inspection_bridge_node', preferred_backend='protocol_udp')
        if not self.arbiter_enabled:
            raise ValueError('inspection bridge requires arbiter.enabled=true')
        self.declare_parameter('inspection_budget_status_timeout_s', 1.5)
        self._budget_timeout_s = float(self.get_parameter('inspection_budget_status_timeout_s').value)
        if not math.isfinite(self._budget_timeout_s) or self._budget_timeout_s <= 0.:
            raise ValueError('inspection_budget_status_timeout_s must be finite and positive')
        self._budget_seen_wall_time_s = float('-inf')
        self._budget_latched = False
        self.declare_parameter('inspection_setpoint_timeout_s', 0.5)
        self._setpoint_timeout_s = float(self.get_parameter('inspection_setpoint_timeout_s').value)
        if not math.isfinite(self._setpoint_timeout_s) or self._setpoint_timeout_s <= 0.:
            raise ValueError('inspection_setpoint_timeout_s must be finite and positive')
        self._setpoint_seen_wall_time_s = float('-inf')
        self.pub_inspection_stop_reason = self.create_publisher(String, '/auv/cable/bridge_stop_reason', 10)
        self.declare_parameter('inspection_status_timeout_s', 1.5)
        self._inspection_status_timeout_s = float(self.get_parameter('inspection_status_timeout_s').value)
        if not math.isfinite(self._inspection_status_timeout_s) or self._inspection_status_timeout_s <= 0.:
            raise ValueError('inspection_status_timeout_s must be finite and positive')
        self._localization_status = 'UNKNOWN'
        self._localization_seen_wall_time_s = float('-inf')
        self._task_status = 'UNKNOWN'
        self._task_status_seen_wall_time_s = float('-inf')
        self._operational_command_sequence = 0
        self._latest_operational_status = None
        self.pub_operational_status = self.create_publisher(String, '/auv/cable/operational_status', 10)
        self.create_subscription(Bool, '/auv/cable/recovery_required', self._on_budget_alarm, 10)
        self.create_subscription(String, '/auv/cable/inspection_status', self._on_localization_status, 10)

    def _sidecar_source_selected(self) -> bool:
        # This consults the already-loaded config even during base construction,
        # before the subclass constructor has finished.
        return getattr(self, 'bridge_cfg', {}).get('inspection_sensor_source') == 'imu_sidecar_candidate'

    def _publish_protocol_imu(self, telemetry, protocol_stamp, quaternion_xyzw):
        if self._sidecar_source_selected():
            return False
        return super()._publish_protocol_imu(telemetry, protocol_stamp, quaternion_xyzw)

    def _safe_publish_ros(self, publisher, message):
        # The legacy DVL velocity has already been rotated using the legacy
        # $AUV attitude. With an independent IMU source it cannot be fused as
        # if both measurements shared the same orientation; fail closed.
        if (self._sidecar_source_selected()
                and publisher is getattr(self, 'dvl_pub', None)):
            return False
        return super()._safe_publish_ros(publisher, message)

    def handle_protocol_telemetry(self, telemetry):
        super().handle_protocol_telemetry(telemetry)
        if (not self._sidecar_source_selected() or not rclpy.ok()
                or not telemetry.pc104_dvl_bi_time_valid):
            return
        self.body_dvl_candidate_pub.publish(String(data=json.dumps({
            'pc104_packet_uptime_ms': int(telemetry.pc104_uptime_ms),
            'pc104_dvl_uptime_ms': int(telemetry.pc104_dvl_bi_uptime_ms),
            'velocity_xyz_mps': [float(telemetry.dvl_body_x_mps),
                                 float(telemetry.dvl_body_y_mps),
                                 float(telemetry.dvl_body_z_mps)],
        })))

    def _on_localization_status(self, msg: String) -> None:
        self._localization_status = msg.data
        self._localization_seen_wall_time_s = time.monotonic()

    def _on_setpoint(self, msg: Setpoint) -> None:
        super()._on_setpoint(msg)
        self._setpoint_seen_wall_time_s = time.monotonic()

    def _on_cable_tracking(self, msg: String) -> None:
        super()._on_cable_tracking(msg)
        try:
            payload = json.loads(msg.data)
        except (TypeError, ValueError):
            return
        if not isinstance(payload, dict):
            return
        self._task_status = task_status_from_tracking(payload)
        self._task_status_seen_wall_time_s = time.monotonic()
        self._attach_operational_status_to_monitor()

    def _attach_operational_status_to_monitor(self) -> None:
        # The protocol side channel forwards this monitor on each uplink.
        # Keep the v1 bridge's monitor schema unchanged.
        if (self.latest_cable_monitor_payload is not None
                and self._latest_operational_status is not None):
            self.latest_cable_monitor_payload['operational_status'] = self._latest_operational_status

    def _on_budget_alarm(self, msg: Bool) -> None:
        self._budget_seen_wall_time_s = time.monotonic()
        if msg.data:
            self._budget_latched = True

    def _budget_problem(self) -> str | None:
        if self._budget_latched:
            return 'inspection_recovery_required'
        if time.monotonic() - self._budget_seen_wall_time_s > self._budget_timeout_s:
            return 'inspection_budget_status_stale'
        return None

    def _setpoint_problem(self) -> str | None:
        if (self.latest_setpoint is None
                or time.monotonic() - self._setpoint_seen_wall_time_s > self._setpoint_timeout_s):
            return 'inspection_setpoint_stale'
        setpoint = self.latest_setpoint
        if (not math.isfinite(float(setpoint.target_speed_mps))
                or not math.isfinite(float(setpoint.target_heading_rad))
                or not math.isfinite(float(setpoint.target_depth_m))):
            return 'inspection_setpoint_invalid'
        if (setpoint.mode != 'CABLE_TRACKING' or not setpoint.track_cable
                or setpoint.target_speed_mps <= 0.):
            return 'inspection_setpoint_hold'
        return None

    def _inspection_authority_problem(self) -> str | None:
        return self._budget_problem() or self._setpoint_problem()

    def _guard_autonomous_decision(self, decision):
        if decision.active_arbiter != ArbiterMode.AUTONOMOUS:
            return decision, None
        problem = self._inspection_authority_problem()
        if problem is None:
            return decision, None
        payload = dict(decision.command_payload)
        for key in (KEY_THRUST, KEY_LEFT, KEY_RIGHT, KEY_TOP, KEY_BOTTOM, KEY_SIDE_MOTOR_RPM):
            payload[key] = 0
        # Do not erase an upstream explicit shutoff/cancel command. Block all
        # starts, actuator-on and other non-shutdown work instructions.
        shutdown_instructions = {
            int(WorkInstruction.TASK_CANCEL), int(WorkInstruction.MAIN_THRUSTER_OFF),
            int(WorkInstruction.SIDE_THRUSTER_OFF),
            int(WorkInstruction.HORIZONTAL_RUDDER_OFF),
            int(WorkInstruction.VERTICAL_RUDDER_OFF),
        }
        original_instruction = int(payload.get(KEY_WORK_INSTRUCTION, WorkInstruction.NONE))
        payload[KEY_WORK_INSTRUCTION] = (
            original_instruction if original_instruction in shutdown_instructions
            else int(WorkInstruction.NONE)
        )
        payload[KEY_NOTE] = problem
        return replace(decision, arbiter_source=ArbiterSource.SAFETY_FALLBACK,
                       command_payload=payload, mpc_command_valid=False), problem

    def _publish_arbiter_decision(self, decision, *, guard_decision=None):
        guarded, problem = self._guard_autonomous_decision(decision)
        self.last_arbiter_decision = guarded
        self._operational_command_sequence += 1
        self.pub_inspection_stop_reason.publish(String(data=problem or ''))
        super()._publish_arbiter_decision(guarded, guard_decision=guard_decision)

    def _publish_arbiter_status(self, *, guard_decision=None):
        super()._publish_arbiter_status(guard_decision=guard_decision)
        # The base constructor can publish before this subclass is initialized.
        if not hasattr(self, 'pub_operational_status'):
            return
        decision = self.last_arbiter_decision
        guard_state = (guard_decision.auto_state if guard_decision is not None
                       else self.autonomy_guard.auto_state if self.autonomy_guard is not None
                       else AutoState.LOCKED)
        guard_reason = (guard_decision.deny_reason if guard_decision is not None
                        else self.autonomy_guard.deny_reason if self.autonomy_guard is not None
                        else DenyReason.NONE)
        fresh = time.monotonic() - self._localization_seen_wall_time_s <= self._inspection_status_timeout_s
        status = build_operational_status(
            mode=decision.active_arbiter.value if decision is not None else ArbiterMode.REMOTE.value,
            source=decision.arbiter_source.value if decision is not None else ArbiterSource.NONE.value,
            mpc_valid=bool(decision.mpc_command_valid) if decision is not None else False,
            guard_state=guard_state.value, guard_reason=guard_reason.value,
            budget_problem=self._inspection_authority_problem(), passive=self.passive_mode,
            localization_status=self._localization_status, localization_fresh=fresh,
        )
        task_status, task_fresh = task_status_snapshot(
            self._task_status, self._task_status_seen_wall_time_s,
            time.monotonic(), self._inspection_status_timeout_s)
        status['task_status'] = task_status
        status['task_status_fresh'] = task_fresh
        status['timestamp_s'] = time.time()
        status['command_sequence'] = self._operational_command_sequence
        self._latest_operational_status = status
        self._attach_operational_status_to_monitor()
        self.pub_operational_status.publish(String(data=json.dumps(status, ensure_ascii=False)))
        # The normal cable monitor travels with AMD uplink telemetry. During
        # an uplink outage there may be no such packet, precisely when the
        # operator needs the guard's current revoke reason. Send the small
        # authority view from the command decision path as well.
        try:
            self.transport.publish_bridge_telemetry({
                'message_type': 'inspection_operational_status',
                'active_arbiter': status['arbiter_mode'],
                'auto_state': status['guard_state'],
                'deny_reason': status['guard_reason'],
                'cable_monitor': {'operational_status': status},
            })
        except Exception as exc:
            # The optional operator side channel must not interrupt the
            # safety decision, local UDP output or ROS status publication.
            self.get_logger().warning(f'inspection status side channel unavailable: {exc}')

    def _on_command_keepalive(self):
        # The base keepalive reuses last_arbiter_decision. When the controller
        # dies without sending an unhealthy MpcCmd that snapshot may retain
        # positive thrust forever. Re-evaluate freshness before each send.
        if self.arbiter_enabled and self.command_arbiter is not None:
            self.last_arbiter_decision = self.command_arbiter.decide(now=time.time())
        super()._on_command_keepalive()


def main():
    rclpy.init()
    node = InspectionBridgeNode()
    try:
        rclpy.spin(node)
    except ExternalShutdownException:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()

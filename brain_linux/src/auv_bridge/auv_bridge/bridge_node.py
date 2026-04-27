#!/usr/bin/env python3
from __future__ import annotations

import math
import json
import time
from pathlib import Path
from typing import Any

import rclpy

from . import PROJECT_ROOT
from auv_interfaces.msg import ArbiterStatus, MpcCmd, SensorStatus, Setpoint
from geometry_msgs.msg import Twist, TwistStamped
from rcl_interfaces.msg import SetParametersResult
from rclpy.node import Node
from sensor_msgs.msg import Imu, MagneticField
from std_msgs.msg import Float32, String
import yaml

from common.enums import ArbiterMode, ArbiterSource, AutoState, BridgeBackend, ControlModeByte, DenyReason, WorkInstruction
from common.protocol import (
    KEY_B_NED,
    KEY_BOTTOM,
    KEY_CONFIDENCE,
    KEY_CONTROL_MODE_BYTE,
    KEY_DENY_REASON,
    KEY_LEAK_LEVEL,
    KEY_LEFT,
    KEY_NOTE,
    KEY_ORIENTATION_DEG,
    KEY_RIGHT,
    KEY_TELEMETRY_FRESHNESS_MS,
    KEY_TOTAL_VOLTAGE_V,
    KEY_TOP,
    KEY_THRUST,
    KEY_WORK_INSTRUCTION,
    ProtocolUplinkTelemetry,
    Z_PATH_AUV_TELEMETRY,
    Z_PATH_AUV_VIZ_INTERNAL,
    Z_PATH_PC_CMD_RAW,
    build_bridge_telemetry_payload,
)

from .arbiter import ArbiterDecision, CommandArbiter
from .autonomy_guard import AutonomyGuard, GuardDecision
from .bridge_backends import BaseBridgeBackend, ProtocolBridgeBackend, TopicBridgeBackend


def _rpy_deg_to_quaternion(roll_deg: float, pitch_deg: float, yaw_deg: float) -> tuple[float, float, float, float]:
    roll = math.radians(roll_deg)
    pitch = math.radians(pitch_deg)
    yaw = math.radians(yaw_deg)
    cy = math.cos(yaw * 0.5)
    sy = math.sin(yaw * 0.5)
    cp = math.cos(pitch * 0.5)
    sp = math.sin(pitch * 0.5)
    cr = math.cos(roll * 0.5)
    sr = math.sin(roll * 0.5)
    qw = cr * cp * cy + sr * sp * sy
    qx = sr * cp * cy - cr * sp * sy
    qy = cr * sp * cy + sr * cp * sy
    qz = cr * cp * sy - sr * sp * cy
    return qx, qy, qz, qw


class AUVBridgeNode(Node):
    """ROS2 bridge node with pluggable transport backend."""

    def __init__(self, *, node_name: str = 'auv_bridge_node', preferred_backend: str | None = None) -> None:
        super().__init__(node_name)

        default_params = str(PROJECT_ROOT / 'brain_linux' / 'config' / 'params.yaml')
        self.declare_parameter('params_file', default_params)
        self.declare_parameter('bridge_backend', preferred_backend or '')
        self.declare_parameter('passive_mode', False)
        self.declare_parameter('command_publish_hz', 10.0)
        self.declare_parameter('cmd_timeout_s', 0.5)
        self.declare_parameter('protocol_control_mode_byte', 0xEE)
        self.declare_parameter('protocol_work_instruction', 0x00)
        self.declare_parameter('main_motor_rpm_scale', 15.0)
        self.declare_parameter('guard_min_total_voltage_v', 47.0)
        self.declare_parameter('guard_min_confidence', 0.5)
        self.declare_parameter('guard_max_uplink_age_ms', 200.0)
        self.declare_parameter('arbiter_mpc_timeout_s', 0.5)
        self.declare_parameter('shadow_cmd_topic', '/auv/bridge/shadow_cmd')
        self.declare_parameter('shadow_telemetry_topic', '/auv/bridge/shadow_telemetry')

        params_file = str(self.get_parameter('params_file').value)
        cfg = self._load_config(params_file)
        self.bridge_cfg = cfg.get('bridge', {})

        configured_backend = str(self.bridge_cfg.get('backend', '')).strip()
        requested_backend = str(self.get_parameter('bridge_backend').value).strip()
        backend_name = requested_backend or configured_backend or preferred_backend or BridgeBackend.ZENOH_JSON.value
        self.backend = BridgeBackend(backend_name)

        self.cmd_timeout_s = float(self.get_parameter('cmd_timeout_s').value)
        self.command_publish_hz = float(self.get_parameter('command_publish_hz').value)
        self.protocol_control_mode_byte = int(self.get_parameter('protocol_control_mode_byte').value)
        self.protocol_work_instruction = int(self.get_parameter('protocol_work_instruction').value)
        self.protocol_send_zero_on_idle = bool(self.bridge_cfg.get('protocol_send_zero_on_idle', True))
        self.passive_mode = bool(self.get_parameter('passive_mode').value)
        self.imu_key = str(self.bridge_cfg.get('imu_key', 'rt/auv/sensors/imu'))
        self.dvl_key = str(self.bridge_cfg.get('dvl_key', 'rt/auv/sensors/dvl'))
        self.depth_key = str(self.bridge_cfg.get('depth_key', 'rt/auv/sensors/depth'))
        self.magnetic_key = str(self.bridge_cfg.get('magnetic_key', 'rt/auv/sensors/magnetic'))
        self.arbiter_cfg = self.bridge_cfg.get('arbiter', {})
        self.arbiter_enabled = bool(self.arbiter_cfg.get('enabled', False))
        self.arbiter_status_topic = str(self.arbiter_cfg.get('arbiter_status_topic', '/auv/arbiter/status'))
        self.mpc_topic = str(self.arbiter_cfg.get('mpc_topic', '/auv/control/mpc_cmd'))
        self.sensor_status_topic = str(self.arbiter_cfg.get('sensor_status_topic', '/auv/sensors/status'))
        self.pc_cmd_raw_key = str(self.arbiter_cfg.get('pc_cmd_raw_key', Z_PATH_PC_CMD_RAW))
        self.telemetry_key = str(self.arbiter_cfg.get('telemetry_key', Z_PATH_AUV_TELEMETRY))
        self.viz_internal_key = str(self.arbiter_cfg.get('viz_internal_key', Z_PATH_AUV_VIZ_INTERNAL))
        self.guard_min_total_voltage_v = float(self.get_parameter('guard_min_total_voltage_v').value)
        self.guard_min_confidence = float(self.get_parameter('guard_min_confidence').value)
        self.guard_max_uplink_age_ms = float(self.get_parameter('guard_max_uplink_age_ms').value)
        self.arbiter_mpc_timeout_s = float(self.get_parameter('arbiter_mpc_timeout_s').value)
        self.shadow_cmd_topic = str(self.get_parameter('shadow_cmd_topic').value)
        self.shadow_telemetry_topic = str(self.get_parameter('shadow_telemetry_topic').value)
        protocol_udp_cfg = self.bridge_cfg.get('protocol_udp', {})
        self.protocol_obj_address = int(protocol_udp_cfg.get('obj_address', 1))

        self.imu_pub = self.create_publisher(Imu, '/auv/sensors/imu', 10)
        self.dvl_pub = self.create_publisher(TwistStamped, '/auv/sensors/dvl', 10)
        self.depth_pub = self.create_publisher(Float32, '/auv/sensors/depth', 10)
        self.magnetic_pub = self.create_publisher(MagneticField, '/auv/sensors/magnetic', 10)
        self.shadow_cmd_pub = self.create_publisher(String, self.shadow_cmd_topic, 10)
        self.shadow_telemetry_pub = self.create_publisher(String, self.shadow_telemetry_topic, 10)

        self.create_subscription(Twist, '/cmd_vel', self._on_cmd_vel, 10)
        self.create_subscription(Setpoint, '/auv/control/setpoint', self._on_setpoint, 10)

        self.arbiter_status_pub = None
        self.command_arbiter: CommandArbiter | None = None
        self.autonomy_guard: AutonomyGuard | None = None
        self.latest_sensor_status_payload: dict[str, Any] = {
            KEY_CONFIDENCE: 0.0,
            KEY_LEAK_LEVEL: 0,
        }
        self.latest_bridge_telemetry_payload: dict[str, Any] | None = None
        self.latest_protocol_telemetry_ts = 0.0
        self.last_arbiter_decision: ArbiterDecision | None = None
        self._command_keepalive_timer = None

        if self.arbiter_enabled:
            self.command_arbiter = CommandArbiter(
                mpc_timeout_s=self.arbiter_mpc_timeout_s,
                default_obj_address=self.protocol_obj_address,
            )
            self.autonomy_guard = AutonomyGuard(
                min_total_voltage_v=self.guard_min_total_voltage_v,
                min_confidence=self.guard_min_confidence,
                max_uplink_age_ms=self.guard_max_uplink_age_ms,
            )
            self.arbiter_status_pub = self.create_publisher(ArbiterStatus, self.arbiter_status_topic, 10)
            self.create_subscription(SensorStatus, self.sensor_status_topic, self._on_sensor_status, 10)
            self.create_subscription(MpcCmd, self.mpc_topic, self._on_mpc_cmd, 10)

        self.latest_setpoint: Setpoint | None = None
        self.latest_command_payload: dict[str, float] | None = None
        self.latest_command_ts = 0.0
        self._rx_count = 0
        self._lat_count = 0
        self._lat_sum = 0.0

        self.transport = self._create_transport(self.backend)
        self.transport.open()

        self._reset_command_keepalive_timer()
        self.create_timer(2.0, self._on_stats_timer)
        self._param_callback = self.add_on_set_parameters_callback(self._on_parameters_changed)

        self.get_logger().info(f'bridge backend started: {self.backend.value}, passive_mode={self.passive_mode}')

    @staticmethod
    def _load_config(path: str) -> dict[str, Any]:
        p = Path(path)
        if not p.exists():
            return {}
        with p.open('r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
        return data if isinstance(data, dict) else {}

    def _create_transport(self, backend: BridgeBackend) -> BaseBridgeBackend:
        if backend == BridgeBackend.ZENOH_JSON:
            return TopicBridgeBackend(node=self, bridge_cfg=self.bridge_cfg)
        if backend == BridgeBackend.PROTOCOL_UDP:
            return ProtocolBridgeBackend(node=self, bridge_cfg=self.bridge_cfg)
        raise RuntimeError(f'unsupported bridge backend: {backend.value}')

    def _reset_command_keepalive_timer(self) -> None:
        if self._command_keepalive_timer is not None:
            self._command_keepalive_timer.cancel()
            self._command_keepalive_timer = None

        if self.transport.requires_command_heartbeat:
            self._command_keepalive_timer = self.create_timer(
                1.0 / max(self.command_publish_hz, 1e-3),
                self._on_command_keepalive,
            )

    def _on_parameters_changed(self, params) -> SetParametersResult:
        for param in params:
            if param.name == 'passive_mode':
                self.passive_mode = bool(param.value)
            elif param.name == 'command_publish_hz':
                new_rate = float(param.value)
                if new_rate <= 0.0:
                    return SetParametersResult(successful=False, reason='command_publish_hz must be positive')
                if abs(new_rate - self.command_publish_hz) > 1e-9:
                    self.command_publish_hz = new_rate
                    self._reset_command_keepalive_timer()
            elif param.name == 'cmd_timeout_s':
                self.cmd_timeout_s = float(param.value)
            elif param.name == 'protocol_control_mode_byte':
                self.protocol_control_mode_byte = int(param.value)
            elif param.name == 'protocol_work_instruction':
                self.protocol_work_instruction = int(param.value)
            elif param.name == 'main_motor_rpm_scale':
                new_scale = float(param.value)
                if new_scale <= 0.0:
                    return SetParametersResult(successful=False, reason='main_motor_rpm_scale must be positive')
                self._update_protocol_scale(new_scale)
            elif param.name == 'guard_min_total_voltage_v':
                self.guard_min_total_voltage_v = float(param.value)
                if self.autonomy_guard is not None:
                    self.autonomy_guard.min_total_voltage_v = self.guard_min_total_voltage_v
            elif param.name == 'guard_min_confidence':
                self.guard_min_confidence = float(param.value)
                if self.autonomy_guard is not None:
                    self.autonomy_guard.min_confidence = self.guard_min_confidence
            elif param.name == 'guard_max_uplink_age_ms':
                self.guard_max_uplink_age_ms = float(param.value)
                if self.autonomy_guard is not None:
                    self.autonomy_guard.max_uplink_age_ms = self.guard_max_uplink_age_ms
            elif param.name == 'arbiter_mpc_timeout_s':
                self.arbiter_mpc_timeout_s = float(param.value)
                if self.command_arbiter is not None:
                    self.command_arbiter.mpc_timeout_s = self.arbiter_mpc_timeout_s
        return SetParametersResult(successful=True)

    def _update_protocol_scale(self, new_scale: float) -> None:
        protocol_transport = self.transport if isinstance(self.transport, ProtocolBridgeBackend) else None
        if protocol_transport is not None:
            protocol_transport.main_motor_rpm_scale = float(new_scale)

    def _publish_shadow_snapshot(
        self,
        *,
        kind: str,
        payload: dict[str, Any],
        control_mode_byte: int,
        work_instruction: int,
        orientation_deg: float,
    ) -> None:
        snapshot = {
            'kind': kind,
            'passive_mode': bool(self.passive_mode),
            'control_mode_byte': int(control_mode_byte),
            'work_instruction': int(work_instruction),
            'orientation_deg': float(orientation_deg),
            'timestamp': time.time(),
            'payload': payload,
        }
        self.shadow_cmd_pub.publish(String(data=json.dumps(snapshot, ensure_ascii=False, sort_keys=True)))

    def _publish_shadow_telemetry(self, payload: dict[str, Any]) -> None:
        self.shadow_telemetry_pub.publish(String(data=json.dumps(payload, ensure_ascii=False, sort_keys=True)))

    def _on_setpoint(self, msg: Setpoint) -> None:
        self.latest_setpoint = msg

    def _on_cmd_vel(self, msg: Twist) -> None:
        payload = {
            KEY_RIGHT: float(msg.angular.x),
            KEY_TOP: float(msg.angular.y),
            KEY_LEFT: float(msg.angular.z),
            KEY_BOTTOM: float(msg.linear.z),
            KEY_THRUST: float(msg.linear.x),
            'ts': time.time(),
        }
        self.latest_command_payload = payload
        self.latest_command_ts = time.time()
        if not self.arbiter_enabled:
            self._publish_command(payload)

    def _on_sensor_status(self, msg: SensorStatus) -> None:
        self.latest_sensor_status_payload = {
            KEY_CONFIDENCE: float(msg.confidence),
            KEY_LEAK_LEVEL: int(msg.leak_level),
        }
        self._refresh_guard_and_fallback(now=time.time())

    def _on_mpc_cmd(self, msg: MpcCmd) -> None:
        if not self.arbiter_enabled or self.command_arbiter is None:
            return

        stamp = self._header_stamp_to_seconds(msg.header.stamp)
        decision = self.command_arbiter.update_mpc_command(
            {
                'right_fin_deg': float(msg.right_fin_deg),
                'top_fin_deg': float(msg.top_fin_deg),
                'left_fin_deg': float(msg.left_fin_deg),
                'bottom_fin_deg': float(msg.bottom_fin_deg),
                'thrust_percent': float(msg.thrust_percent),
                'source': str(msg.source),
                'valid': bool(msg.valid),
                'healthy': bool(msg.healthy),
                'note': str(msg.note),
            },
            now=stamp,
        )
        self.last_arbiter_decision = decision
        guard_decision = self._refresh_guard_and_fallback(now=time.time())
        if self.command_arbiter.active_mode == ArbiterMode.AUTONOMOUS:
            active_decision = self.last_arbiter_decision or decision
            self._publish_arbiter_decision(active_decision, guard_decision=guard_decision)
        else:
            self._publish_arbiter_status(guard_decision=guard_decision)

    def handle_pc_raw_command(self, payload: dict[str, Any]) -> None:
        if not self.arbiter_enabled or self.command_arbiter is None or self.autonomy_guard is None:
            return

        now = time.time()
        control_mode_byte = int(payload.get(KEY_CONTROL_MODE_BYTE, int(ControlModeByte.REMOTE_CONTROL)))
        work_instruction = int(payload.get(KEY_WORK_INSTRUCTION, int(WorkInstruction.NONE)))

        if work_instruction in {int(WorkInstruction.TASK_CANCEL), int(WorkInstruction.CLEAR_FAULT)}:
            guard_decision = self.autonomy_guard.lock(deny_reason=DenyReason.MANUAL_OVERRIDE)
            decision = self.command_arbiter.force_remote(payload, now=now)
        elif control_mode_byte == int(ControlModeByte.JETSON_PROTOCOL):
            guard_decision = self.autonomy_guard.request_activation(
                sensor_status=self.latest_sensor_status_payload,
                telemetry_status=self._current_telemetry_status(now=now),
            )
            if guard_decision.autonomy_allowed:
                decision = self.command_arbiter.update_pc_raw_command(payload, now=now)
            else:
                decision = self.command_arbiter.force_remote(payload, now=now)
        else:
            guard_decision = self.autonomy_guard.lock(deny_reason=DenyReason.NONE)
            decision = self.command_arbiter.update_pc_raw_command(payload, now=now)

        self.last_arbiter_decision = decision
        self._publish_arbiter_decision(decision, guard_decision=guard_decision)

    def _on_command_keepalive(self) -> None:
        if self.arbiter_enabled and self.command_arbiter is not None:
            now = time.time()
            guard_decision = self._refresh_guard_and_fallback(now=now)
            decision = self.last_arbiter_decision or self.command_arbiter.decide(now=now)
            self.last_arbiter_decision = decision
            self._publish_arbiter_decision(decision, guard_decision=guard_decision)
            return

        if self.latest_command_payload is None:
            if not self.protocol_send_zero_on_idle:
                return
            payload = self._zero_command_payload()
        elif time.time() - self.latest_command_ts > self.cmd_timeout_s:
            payload = self._zero_command_payload()
        else:
            payload = dict(self.latest_command_payload)
            payload['ts'] = time.time()
        self._publish_command(payload)

    def _zero_command_payload(self) -> dict[str, float]:
        return {
            KEY_RIGHT: 0.0,
            KEY_TOP: 0.0,
            KEY_LEFT: 0.0,
            KEY_BOTTOM: 0.0,
            KEY_THRUST: 0.0,
            'ts': time.time(),
        }

    def _publish_command(self, payload: dict[str, float]) -> None:
        control_mode_byte = self._resolve_control_mode_byte()
        work_instruction = self.protocol_work_instruction
        orientation_deg = self._resolve_target_heading_deg()
        if self.passive_mode:
            self._publish_shadow_snapshot(
                kind='command',
                payload=dict(payload),
                control_mode_byte=control_mode_byte,
                work_instruction=work_instruction,
                orientation_deg=orientation_deg,
            )
            return

        self.transport.send_command(
            payload,
            control_mode_byte=control_mode_byte,
            work_instruction=work_instruction,
            orientation_deg=orientation_deg,
        )

    def _publish_arbiter_decision(
        self,
        decision: ArbiterDecision,
        *,
        guard_decision: GuardDecision | None = None,
    ) -> None:
        payload = dict(decision.command_payload)
        control_mode_byte = int(payload.get(KEY_CONTROL_MODE_BYTE, int(ControlModeByte.REMOTE_CONTROL)))
        work_instruction = int(payload.get(KEY_WORK_INSTRUCTION, int(WorkInstruction.NONE)))
        orientation_deg = float(payload.get(KEY_ORIENTATION_DEG, self._resolve_target_heading_deg()))
        if self.passive_mode:
            self._publish_shadow_snapshot(
                kind='arbiter',
                payload=payload,
                control_mode_byte=control_mode_byte,
                work_instruction=work_instruction,
                orientation_deg=orientation_deg,
            )
        else:
            self.transport.send_command(
                payload,
                control_mode_byte=control_mode_byte,
                work_instruction=work_instruction,
                orientation_deg=orientation_deg,
            )
        self._publish_arbiter_status(guard_decision=guard_decision)

    def _resolve_control_mode_byte(self) -> int:
        if self.latest_setpoint is not None and int(self.latest_setpoint.control_mode_byte) != 0:
            return int(self.latest_setpoint.control_mode_byte)
        return self.protocol_control_mode_byte if self.backend == BridgeBackend.PROTOCOL_UDP else 0x01

    def _resolve_target_heading_deg(self) -> float:
        if self.latest_setpoint is None:
            return 0.0
        return math.degrees(float(self.latest_setpoint.target_heading_rad))

    def _record_latency(self, payload: dict[str, Any]) -> None:
        ts = payload.get('ts')
        if isinstance(ts, (int, float)):
            dt = time.time() - float(ts)
            if dt >= 0.0:
                self._lat_count += 1
                self._lat_sum += dt

    def _refresh_guard_and_fallback(self, *, now: float) -> GuardDecision | None:
        if not self.arbiter_enabled or self.autonomy_guard is None or self.command_arbiter is None:
            return None

        if self.autonomy_guard.auto_state != AutoState.ACTIVE:
            decision = GuardDecision(
                auto_state=self.autonomy_guard.auto_state,
                deny_reason=self.autonomy_guard.deny_reason,
                autonomy_allowed=self.autonomy_guard.auto_state == AutoState.ACTIVE,
            )
            self._publish_arbiter_status(guard_decision=decision)
            return decision

        guard_decision = self.autonomy_guard.refresh(
            sensor_status=self.latest_sensor_status_payload,
            telemetry_status=self._current_telemetry_status(now=now),
        )
        if not guard_decision.autonomy_allowed and self.command_arbiter.active_mode == ArbiterMode.AUTONOMOUS:
            self.last_arbiter_decision = self.command_arbiter.force_remote(now=now)
            if self.last_arbiter_decision is not None:
                self._publish_arbiter_decision(self.last_arbiter_decision, guard_decision=guard_decision)
                return guard_decision
        self._publish_arbiter_status(guard_decision=guard_decision)
        return guard_decision

    def _current_telemetry_status(self, *, now: float) -> dict[str, Any]:
        freshness_ms = float('inf')
        if self.latest_protocol_telemetry_ts > 0.0:
            freshness_ms = max(0.0, (now - self.latest_protocol_telemetry_ts) * 1000.0)

        status: dict[str, Any] = {
            KEY_TOTAL_VOLTAGE_V: 0.0,
            KEY_TELEMETRY_FRESHNESS_MS: freshness_ms,
        }
        if self.latest_bridge_telemetry_payload is not None:
            status.update(self.latest_bridge_telemetry_payload)
            status[KEY_TELEMETRY_FRESHNESS_MS] = freshness_ms
        return status

    def _publish_arbiter_status(self, *, guard_decision: GuardDecision | None = None) -> None:
        if self.arbiter_status_pub is None:
            return

        active_decision = self.last_arbiter_decision
        guard = guard_decision
        if guard is None and self.autonomy_guard is not None:
            guard = GuardDecision(
                auto_state=self.autonomy_guard.auto_state,
                deny_reason=self.autonomy_guard.deny_reason,
                autonomy_allowed=self.autonomy_guard.auto_state == AutoState.ACTIVE,
            )

        msg = ArbiterStatus()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = 'auv/base_link'
        msg.active_arbiter = (active_decision.active_arbiter.value if active_decision is not None else ArbiterMode.REMOTE.value)
        msg.arbiter_source = (active_decision.arbiter_source.value if active_decision is not None else ArbiterSource.NONE.value)
        msg.auto_state = guard.auto_state.value if guard is not None else AutoState.LOCKED.value
        msg.deny_reason = guard.deny_reason.value if guard is not None else DenyReason.NONE.value
        if active_decision is not None:
            msg.effective_control_mode_byte = int(active_decision.command_payload.get(KEY_CONTROL_MODE_BYTE, 0))
            msg.effective_work_instruction = int(active_decision.command_payload.get(KEY_WORK_INSTRUCTION, 0))
            msg.mpc_command_valid = bool(active_decision.mpc_command_valid)
        else:
            msg.effective_control_mode_byte = 0
            msg.effective_work_instruction = 0
            msg.mpc_command_valid = False
        msg.autonomy_allowed = bool(guard.autonomy_allowed) if guard is not None else False
        msg.telemetry_freshness_ms = float(self._current_telemetry_status(now=time.time()).get(KEY_TELEMETRY_FRESHNESS_MS, 0.0))
        msg.note = str(active_decision.command_payload.get(KEY_NOTE, '')) if active_decision is not None else ''
        self.arbiter_status_pub.publish(msg)

    @staticmethod
    def _header_stamp_to_seconds(stamp) -> float:
        if int(stamp.sec) == 0 and int(stamp.nanosec) == 0:
            return time.time()
        return float(stamp.sec) + float(stamp.nanosec) * 1.0e-9

    def handle_json_sensor_payload(self, keyexpr: str, data: dict[str, Any]) -> None:
        self._rx_count += 1
        self._record_latency(data)

        if keyexpr == self.imu_key:
            accel = data.get('accel_ned', [0.0, 0.0, 0.0])
            gyro = data.get('gyro_ned', [0.0, 0.0, 0.0])
            if not (isinstance(accel, list) and len(accel) == 3 and isinstance(gyro, list) and len(gyro) == 3):
                return
            msg = Imu()
            msg.header.stamp = self.get_clock().now().to_msg()
            msg.header.frame_id = 'auv/base_link'
            msg.linear_acceleration.x = float(accel[0])
            msg.linear_acceleration.y = float(accel[1])
            msg.linear_acceleration.z = float(accel[2])
            msg.angular_velocity.x = float(gyro[0])
            msg.angular_velocity.y = float(gyro[1])
            msg.angular_velocity.z = float(gyro[2])
            self.imu_pub.publish(msg)
            return

        if keyexpr == self.dvl_key:
            vel = data.get('vel_ned', [0.0, 0.0, 0.0])
            if not (isinstance(vel, list) and len(vel) == 3):
                return
            msg = TwistStamped()
            msg.header.stamp = self.get_clock().now().to_msg()
            msg.header.frame_id = 'auv/base_link'
            msg.twist.linear.x = float(vel[0])
            msg.twist.linear.y = float(vel[1])
            msg.twist.linear.z = float(vel[2])
            self.dvl_pub.publish(msg)
            return

        if keyexpr == self.depth_key:
            depth = data.get('depth_m')
            if not isinstance(depth, (int, float)):
                return
            msg = Float32()
            msg.data = float(depth)
            self.depth_pub.publish(msg)
            return

        if keyexpr == self.magnetic_key:
            magnetic_vec = data.get(KEY_B_NED, [0.0, 0.0, 0.0])
            if not (isinstance(magnetic_vec, list) and len(magnetic_vec) == 3):
                return
            msg = MagneticField()
            msg.header.stamp = self.get_clock().now().to_msg()
            msg.header.frame_id = 'auv/base_link'
            msg.magnetic_field.x = float(magnetic_vec[0])
            msg.magnetic_field.y = float(magnetic_vec[1])
            msg.magnetic_field.z = float(magnetic_vec[2])
            self.magnetic_pub.publish(msg)

    def handle_protocol_telemetry(self, telemetry: ProtocolUplinkTelemetry) -> None:
        self._rx_count += 1
        now = time.time()
        self.latest_protocol_telemetry_ts = now

        imu_msg = Imu()
        imu_msg.header.stamp = self.get_clock().now().to_msg()
        imu_msg.header.frame_id = 'auv/base_link'
        qx, qy, qz, qw = _rpy_deg_to_quaternion(telemetry.roll_deg, telemetry.pitch_deg, telemetry.heading_deg)
        imu_msg.orientation.x = qx
        imu_msg.orientation.y = qy
        imu_msg.orientation.z = qz
        imu_msg.orientation.w = qw
        imu_msg.angular_velocity.x = 0.0
        imu_msg.angular_velocity.y = 0.0
        imu_msg.angular_velocity.z = 0.0
        imu_msg.linear_acceleration.x = 0.0
        imu_msg.linear_acceleration.y = 0.0
        imu_msg.linear_acceleration.z = 0.0
        self.imu_pub.publish(imu_msg)

        dvl_msg = TwistStamped()
        dvl_msg.header.stamp = self.get_clock().now().to_msg()
        dvl_msg.header.frame_id = 'auv/base_link'
        dvl_msg.twist.linear.x = float(telemetry.dvl_speed_mps)
        dvl_msg.twist.linear.y = 0.0
        dvl_msg.twist.linear.z = 0.0
        self.dvl_pub.publish(dvl_msg)

        depth_msg = Float32()
        depth_msg.data = float(telemetry.depth_m)
        self.depth_pub.publish(depth_msg)

        guard_decision = None
        if self.arbiter_enabled:
            guard_decision = self._refresh_guard_and_fallback(now=now)

        active_mode = self.command_arbiter.active_mode if self.command_arbiter is not None else ArbiterMode.REMOTE
        active_source = self.last_arbiter_decision.arbiter_source if self.last_arbiter_decision is not None else ArbiterSource.NONE
        auto_state = guard_decision.auto_state if guard_decision is not None else (
            self.autonomy_guard.auto_state if self.autonomy_guard is not None else AutoState.LOCKED
        )
        deny_reason = guard_decision.deny_reason if guard_decision is not None else (
            self.autonomy_guard.deny_reason if self.autonomy_guard is not None else DenyReason.NONE
        )

        bridge_payload = build_bridge_telemetry_payload(
            telemetry,
            ts=now,
            active_arbiter=active_mode,
            arbiter_source=active_source,
            auto_state=auto_state,
            deny_reason=deny_reason,
            telemetry_freshness_ms=0.0,
        )
        self.latest_bridge_telemetry_payload = bridge_payload
        self.transport.publish_bridge_telemetry(bridge_payload)
        if self.passive_mode:
            self._publish_shadow_telemetry(bridge_payload)
        self._publish_arbiter_status(guard_decision=guard_decision)

    def _on_stats_timer(self) -> None:
        if self._rx_count == 0:
            self.get_logger().info('[bridge] waiting for sensor payloads...')
            return
        if self._lat_count == 0:
            self.get_logger().info(f'[bridge] received {self._rx_count} sensor payloads via {self.backend.value}')
            return
        mean_ms = (self._lat_sum / self._lat_count) * 1000.0
        self.get_logger().info(f'[bridge] mean sensor ingress latency: {mean_ms:.2f} ms over {self._lat_count} samples')

    def destroy_node(self):
        self.transport.close()
        return super().destroy_node()


def main(args=None, *, preferred_backend: str | None = None, node_name: str = 'auv_bridge_node') -> None:
    rclpy.init(args=args)
    node = AUVBridgeNode(node_name=node_name, preferred_backend=preferred_backend)
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
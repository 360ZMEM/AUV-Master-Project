import socket
import sys
import time
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[2]
for folder in [PROJECT_ROOT, PROJECT_ROOT / 'common']:
    folder_str = str(folder)
    if folder_str not in sys.path:
        sys.path.insert(0, folder_str)

from common.protocol import build_uplink_packet, parse_downlink_packet
from common.protocol_debug import format_protocol_packet, format_protocol_packet_ascii, format_protocol_packet_raw

from mock_amd_chaos import ChaosInjector, ChaosProfile
from mock_amd_delay import TransportDelayQueue
from mock_amd_sensor_cache import SensorSampleCache, SensorSnapshot
from frame_transform import body_vector_ue_to_ned, pose_matrix_ue_to_ned
from sim_wrapper import create_sim_wrapper, build_scenario, extract_body_velocity, extract_depth, get_agent_state


class MockAmdUdpServer:
    """Mock AMD UDP server that speaks the $CKTH/$AUV binary protocol."""

    def __init__(self, config, command_guard):
        self.config = config
        self.command_guard = command_guard
        self.agent_name = config['simulation']['agent_name']
        self.rate_hz = float(config['bridge']['rate_hz'])
        self.dt = 1.0 / max(1e-6, self.rate_hz)

        protocol_cfg = config['bridge'].get('protocol_udp', {})
        self.bind_host = str(protocol_cfg.get('bind_host', '0.0.0.0'))
        self.bind_port = int(protocol_cfg.get('bind_port', 52364))
        self.default_remote_host = str(protocol_cfg.get('remote_host', '127.0.0.1'))
        self.default_remote_port = int(protocol_cfg.get('remote_port', 52365))
        self.socket_timeout_s = float(protocol_cfg.get('socket_timeout_s', 0.01))
        self.recv_buffer_size = int(protocol_cfg.get('recv_buffer_size', 2048))
        self.main_motor_rpm_scale = float(protocol_cfg.get('main_motor_rpm_scale', 15.0))
        self.side_motor_rpm = int(protocol_cfg.get('side_motor_rpm', 0))
        self.auv_address = int(protocol_cfg.get('auv_address', 1))
        self.default_control_mode_byte = int(protocol_cfg.get('default_control_mode_byte', 0xEE))
        self.telemetry_total_voltage_v = float(protocol_cfg.get('telemetry_total_voltage_v', 48.0))
        self.telemetry_total_current_a = float(protocol_cfg.get('telemetry_total_current_a', 0.0))
        self.telemetry_soc = int(protocol_cfg.get('telemetry_soc', 100))
        self.telemetry_soh = int(protocol_cfg.get('telemetry_soh', 100))
        self.sniffer_mirror_host = str(protocol_cfg.get('sniffer_mirror_host', '127.0.0.1'))
        self.sniffer_mirror_port = int(protocol_cfg.get('sniffer_mirror_port', 0))
        self.log_packets = bool(protocol_cfg.get('log_packets', True))
        self.log_raw_format = bool(protocol_cfg.get('log_raw_format', False))
        self.log_ascii_format = bool(protocol_cfg.get('log_ascii_format', False))
        self.log_packet_hex = bool(protocol_cfg.get('log_packet_hex', False))
        self.log_hex_bytes = int(protocol_cfg.get('log_hex_bytes', 48))
        self.log_every_n = max(1, int(protocol_cfg.get('log_every_n', 1)))

        mock_cfg = dict(config.get('mock_amd', {}) or {})
        delay_ms = float(mock_cfg.get('transport_delay_ms', 0.0))
        jitter_ms = float(mock_cfg.get('transport_jitter_ms', 0.0))
        max_queue_depth = int(mock_cfg.get('transport_max_queue', 64))
        self._delay_queue = None
        if delay_ms > 0.0 or jitter_ms > 0.0:
            self._delay_queue = TransportDelayQueue(
                base_delay_ms=delay_ms,
                jitter_ms=jitter_ms,
                max_queue_depth=max_queue_depth,
            )

        sensor_cfg = dict(mock_cfg.get('sensor_clocks', {}) or {})
        self._sensor_cache = None
        if any(float(sensor_cfg.get(name, 0.0) or 0.0) > 0.0 for name in ('imu_hz', 'dvl_hz', 'depth_hz', 'mag_hz')):
            self._sensor_cache = SensorSampleCache(
                imu_hz=float(sensor_cfg.get('imu_hz', 0.0) or 0.0),
                dvl_hz=float(sensor_cfg.get('dvl_hz', 0.0) or 0.0),
                depth_hz=float(sensor_cfg.get('depth_hz', 0.0) or 0.0),
                mag_hz=float(sensor_cfg.get('mag_hz', 0.0) or 0.0),
            )

        chaos_cfg = dict(mock_cfg.get('chaos', {}) or {})
        self._chaos = None
        if bool(chaos_cfg.get('enabled', False)):
            self._chaos = ChaosInjector(
                ChaosProfile(
                    enabled=True,
                    packet_loss_pct=float(chaos_cfg.get('packet_loss_pct', 0.0)),
                    reorder_enabled=bool(chaos_cfg.get('reorder_enabled', False)),
                    reorder_buffer_ms=float(chaos_cfg.get('reorder_buffer_ms', 50.0)),
                    dvl_freeze_enabled=bool(chaos_cfg.get('dvl_freeze_enabled', False)),
                    dvl_freeze_after_s=float(chaos_cfg.get('dvl_freeze_after_s', 30.0)),
                    imu_drift_enabled=bool(chaos_cfg.get('imu_drift_enabled', False)),
                    imu_drift_rate_deg_per_s=float(chaos_cfg.get('imu_drift_rate_deg_per_s', 0.5)),
                    depth_spike_enabled=bool(chaos_cfg.get('depth_spike_enabled', False)),
                    depth_spike_m=float(chaos_cfg.get('depth_spike_m', 5.0)),
                    depth_spike_after_s=float(chaos_cfg.get('depth_spike_after_s', 60.0)),
                    mag_saturation_enabled=bool(chaos_cfg.get('mag_saturation_enabled', False)),
                    mag_saturation_threshold_t=float(chaos_cfg.get('mag_saturation_threshold_t', 50000.0)),
                    uplink_dropout_enabled=bool(chaos_cfg.get('uplink_dropout_enabled', False)),
                    uplink_dropout_on_pct=float(chaos_cfg.get('uplink_dropout_on_pct', 0.8)),
                    uplink_dropout_period_s=float(chaos_cfg.get('uplink_dropout_period_s', 10.0)),
                )
            )

        self._start_time = 0.0

        self.wrapper = None
        self.sock = None
        self.last_cmd = np.array(config['bridge'].get('default_command', [0, 0, 0, 0, 0]), dtype=float)
        self.last_cmd_msg = None
        self.last_cmd_ts = 0.0
        self.last_client_addr = (self.default_remote_host, self.default_remote_port)
        self.last_work_instruction = 0
        self.last_control_mode_byte = self.default_control_mode_byte
        self.last_mock_amd_timestamp_us = 0

    def open(self):
        scenario = build_scenario(self.config)
        sim_cfg = self.config['simulation']
        self.wrapper = create_sim_wrapper(
            self.config,
            scenario_cfg=scenario,
            agent_name=self.agent_name,
            show_viewport=bool(sim_cfg.get('show_viewport', False)),
            verbose=bool(sim_cfg.get('verbose', False)),
        ).open()
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind((self.bind_host, self.bind_port))
        self.sock.settimeout(self.socket_timeout_s)
        return self

    def close(self):
        if self.sock is not None:
            try:
                self.sock.close()
            except Exception:
                pass
            self.sock = None
        if self.wrapper is not None:
            self.wrapper.close()
            self.wrapper = None

    def _mirror_packet(self, packet: bytes):
        if self.sock is None or self.sniffer_mirror_port <= 0:
            return
        try:
            self.sock.sendto(packet, (self.sniffer_mirror_host, self.sniffer_mirror_port))
        except OSError:
            return

    @staticmethod
    def _build_sensor_raw_state(
        heading_deg: float,
        pitch_deg: float,
        roll_deg: float,
        dvl_speed_mps: float,
        depth_m: float,
        mag_payload: dict | None,
    ) -> dict:
        raw_state = {
            'imu': {
                'heading_deg': float(heading_deg),
                'pitch_deg': float(pitch_deg),
                'roll_deg': float(roll_deg),
            },
            'dvl': {
                'speed_mps': float(dvl_speed_mps),
            },
            'depth': {
                'depth_m': float(depth_m),
            },
        }
        if mag_payload is not None:
            raw_state['mag'] = mag_payload
        return raw_state

    def _poll_command_packet(self):
        if self.sock is None:
            return

        now = time.time()
        ready_packets = []
        if self._delay_queue is not None:
            ready_packets = self._delay_queue.dequeue(now)

        try:
            packet, addr = self.sock.recvfrom(self.recv_buffer_size)
        except socket.timeout:
            packet = None
            addr = None
        except OSError:
            packet = None
            addr = None

        if packet is not None and addr is not None:
            if self._delay_queue is not None:
                self._delay_queue.enqueue((packet, addr), now)
                ready_packets.extend(self._delay_queue.dequeue(now))
            else:
                ready_packets.append((packet, addr))

        for ready_item, ready_recv_ts in ready_packets:
            if isinstance(ready_item, tuple) and len(ready_item) == 2 and isinstance(ready_item[1], tuple):
                ready_packet, ready_addr = ready_item
            else:
                ready_packet = ready_item
                ready_addr = self.last_client_addr
            try:
                downlink = parse_downlink_packet(ready_packet, main_motor_rpm_scale=self.main_motor_rpm_scale)
            except Exception as exc:
                print(f'[mock-amd][warn] invalid downlink packet: {exc}')
                continue

            if self.log_packets:
                if self.log_raw_format:
                    # 紧凑原始格式
                    print(
                        format_protocol_packet_raw(
                            ready_packet,
                            label='mock-amd RX',
                            source=f'{ready_addr[0]}:{ready_addr[1]}',
                        )
                    )
                elif self.log_ascii_format:
                    # 详细 ASCII 格式
                    print(
                        format_protocol_packet_ascii(
                            ready_packet,
                            label='mock-amd RX',
                            source=f'{ready_addr[0]}:{ready_addr[1]}',
                            include_timestamp=True,
                        )
                    )
                    print()  # 空行分隔
                else:
                    # 单行摘要格式
                    print(
                        format_protocol_packet(
                            ready_packet,
                            label='mock-amd RX',
                            source=f'{ready_addr[0]}:{ready_addr[1]}',
                            color=True,
                            include_hex=self.log_packet_hex,
                            max_hex_bytes=self.log_hex_bytes,
                            main_motor_rpm_scale=self.main_motor_rpm_scale,
                        )
                    )

            self._mirror_packet(ready_packet)

            self.last_client_addr = ready_addr
            self.last_work_instruction = downlink.work_instruction
            self.last_control_mode_byte = downlink.control_mode_byte
            self.last_mock_amd_timestamp_us = downlink.mock_amd_timestamp_us
            self.last_cmd_msg = {
                'right': float(downlink.right_fin_deg),
                'top': float(downlink.top_fin_deg),
                'left': float(downlink.left_fin_deg),
                'bottom': float(downlink.bottom_fin_deg),
                'thrust': float(downlink.thrust_percent),
            }
            self.last_cmd_ts = time.time()

    def _build_uplink_packet(self, raw_state, step, command_vector):
        now = time.time()
        elapsed = now - self._start_time

        state = get_agent_state(raw_state, self.agent_name)
        pose = state['PoseSensor']
        tf = pose_matrix_ue_to_ned(pose)

        dvl_ue = extract_body_velocity(state.get('DVLSensor', np.zeros(3)))
        dvl_ned = body_vector_ue_to_ned(dvl_ue)
        depth_raw = extract_depth(state.get('DepthSensor', np.array([-pose[2, 3]])), pose[2, 3])
        depth_ned = float(-depth_raw if depth_raw < 0.0 else depth_raw)
        rpy_deg = np.degrees(tf['rpy_ned'])
        seabed_depth_m = float(self.config.get('digital_twin', {}).get('seabed_z_m', 15.0))

        base_heading_deg = float((rpy_deg[2] + 360.0) % 360.0)
        base_pitch_deg = float(rpy_deg[1])
        base_roll_deg = float(rpy_deg[0])
        base_dvl_speed_mps = float(dvl_ned[0])

        mag_state = state.get('magnetic') or state.get('MagneticSensor') or state.get('mag')
        mag_payload = None
        if isinstance(mag_state, dict):
            mag_payload = {
                'B_ned': list(mag_state.get('B_ned', [0.0, 0.0, 0.0])),
                'B_norm': float(mag_state.get('B_norm', 0.0)),
            }

        sensor_raw_state = self._build_sensor_raw_state(
            heading_deg=base_heading_deg,
            pitch_deg=base_pitch_deg,
            roll_deg=base_roll_deg,
            dvl_speed_mps=base_dvl_speed_mps,
            depth_m=depth_ned,
            mag_payload=mag_payload,
        )

        if self._sensor_cache is not None:
            sensor_snapshot = self._sensor_cache.update(sensor_raw_state, now)
        else:
            sensor_snapshot = SensorSnapshot(
                imu=dict(sensor_raw_state['imu']),
                dvl=dict(sensor_raw_state['dvl']),
                depth=dict(sensor_raw_state['depth']),
                mag=dict(sensor_raw_state['mag']) if sensor_raw_state.get('mag') is not None else None,
                ts=now,
            )

        if self._chaos is not None:
            sensor_snapshot = self._chaos.apply_to_sensors(sensor_snapshot, elapsed)
            if self._chaos.should_drop_uplink(elapsed):
                return None

        imu_snapshot = sensor_snapshot.imu or {}
        dvl_snapshot = sensor_snapshot.dvl or {}
        depth_snapshot = sensor_snapshot.depth or {}

        heading_deg = float(imu_snapshot.get('heading_deg', base_heading_deg))
        pitch_deg = float(imu_snapshot.get('pitch_deg', base_pitch_deg))
        roll_deg = float(imu_snapshot.get('roll_deg', base_roll_deg))
        dvl_speed_mps = float(dvl_snapshot.get('speed_mps', base_dvl_speed_mps))
        depth_ned = float(depth_snapshot.get('depth_m', depth_ned))
        altitude_m = max(0.0, seabed_depth_m - depth_ned)

        # Echo Para1 (Mock AMD timestamp) in uplink for time synchronization
        parameter_values = [0] * 12
        parameter_values[0] = int(self.last_mock_amd_timestamp_us)

        return build_uplink_packet(
            frame_counter=int(step) & 0xFF,
            auv_address=self.auv_address,
            control_mode_byte=self.last_control_mode_byte,
            work_instruction=self.last_work_instruction,
            main_motor_rpm=int(round(float(command_vector[4]) * self.main_motor_rpm_scale)),
            side_motor_rpm=self.side_motor_rpm,
            left_fin_deg=float(command_vector[2]),
            right_fin_deg=float(command_vector[0]),
            top_fin_deg=float(command_vector[1]),
            bottom_fin_deg=float(command_vector[3]),
            depth_m=depth_ned,
            heading_deg=heading_deg,
            pitch_deg=pitch_deg,
            roll_deg=roll_deg,
            gps_heading_deg=heading_deg,
            gps_speed_mps=max(0.0, float(dvl_speed_mps)),
            dvl_speed_mps=dvl_speed_mps,
            altitude_m=altitude_m,
            parameter_values=parameter_values,
            total_voltage_v=self.telemetry_total_voltage_v,
            total_current_a=self.telemetry_total_current_a,
            soc=self.telemetry_soc,
            soh=self.telemetry_soh,
        )

    def run_forever(self):
        self._start_time = time.time()
        state = self.wrapper.reset_and_tick()
        step = 0
        start_wall = time.time()

        while True:
            loop_start = time.time()

            self._poll_command_packet()
            cmd = self.command_guard.sanitize(self.last_cmd_msg, self.last_cmd, self.last_cmd_ts)
            self.last_cmd = cmd

            state = self.wrapper.step(cmd)
            packet = self._build_uplink_packet(state, step, cmd)
            if packet is not None and self.sock is not None:
                self.sock.sendto(packet, self.last_client_addr)
                self._mirror_packet(packet)

            if step % self.log_every_n == 0:
                if self.log_packets:
                    if self.log_raw_format:
                        # 紧凑原始格式
                        print(
                            format_protocol_packet_raw(
                                packet,
                                label='mock-amd TX',
                                source=f'{self.last_client_addr[0]}:{self.last_client_addr[1]}',
                            )
                        )
                    elif self.log_ascii_format:
                        # 详细 ASCII 格式
                        print(
                            format_protocol_packet_ascii(
                                packet,
                                label='mock-amd TX',
                                source=f'{self.last_client_addr[0]}:{self.last_client_addr[1]}',
                                include_timestamp=True,
                            )
                        )
                        print(f'step={step:06d}')
                        print()  # 空行分隔
                    else:
                        # 单行摘要格式
                        uplink_log = format_protocol_packet(
                            packet,
                            label='mock-amd TX',
                            source=f'{self.last_client_addr[0]}:{self.last_client_addr[1]}',
                            color=True,
                            include_hex=self.log_packet_hex,
                            max_hex_bytes=self.log_hex_bytes,
                            main_motor_rpm_scale=self.main_motor_rpm_scale,
                        )
                        print(f'{uplink_log} step={step:06d}')
                else:
                    depth_m = int.from_bytes(packet[38:40], byteorder='big', signed=False) * 0.1
                    print(
                        f'step={step:06d} depth={depth_m:.2f}m '
                        f'cmd=({cmd[0]:.1f},{cmd[1]:.1f},{cmd[2]:.1f},{cmd[3]:.1f},{cmd[4]:.1f})'
                    )

            step += 1
            elapsed = time.time() - loop_start
            sleep_t = self.dt - elapsed
            if sleep_t > 0:
                time.sleep(sleep_t)

            if self.config['bridge'].get('max_steps', 0) > 0 and step >= int(self.config['bridge']['max_steps']):
                break

        print(f'mock amd done, wall_time={time.time() - start_wall:.2f}s')
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

from frame_transform import body_vector_ue_to_ned, pose_matrix_ue_to_ned
from sim_wrapper import (
    HoloOceanSimWrapper,
    build_scenario,
    extract_body_velocity,
    extract_depth,
    get_agent_state,
)


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

        self.wrapper = None
        self.sock = None
        self.last_cmd = np.array(config['bridge'].get('default_command', [0, 0, 0, 0, 0]), dtype=float)
        self.last_cmd_msg = None
        self.last_cmd_ts = 0.0
        self.last_client_addr = (self.default_remote_host, self.default_remote_port)
        self.last_work_instruction = 0
        self.last_control_mode_byte = self.default_control_mode_byte

    def open(self):
        scenario = build_scenario(self.config)
        sim_cfg = self.config['simulation']
        self.wrapper = HoloOceanSimWrapper(
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

    def _poll_command_packet(self):
        if self.sock is None:
            return
        try:
            packet, addr = self.sock.recvfrom(self.recv_buffer_size)
        except socket.timeout:
            return
        except OSError:
            return

        try:
            downlink = parse_downlink_packet(packet, main_motor_rpm_scale=self.main_motor_rpm_scale)
        except Exception as exc:
            print(f'[mock-amd][warn] invalid downlink packet: {exc}')
            return
        self.last_client_addr = addr
        self.last_work_instruction = downlink.work_instruction
        self.last_control_mode_byte = downlink.control_mode_byte
        self.last_cmd_msg = {
            'right': float(downlink.right_fin_deg),
            'top': float(downlink.top_fin_deg),
            'left': float(downlink.left_fin_deg),
            'bottom': float(downlink.bottom_fin_deg),
            'thrust': float(downlink.thrust_percent),
        }
        self.last_cmd_ts = time.time()

    def _build_uplink_packet(self, raw_state, step, command_vector):
        state = get_agent_state(raw_state, self.agent_name)
        pose = state['PoseSensor']
        tf = pose_matrix_ue_to_ned(pose)

        dvl_ue = extract_body_velocity(state.get('DVLSensor', np.zeros(3)))
        dvl_ned = body_vector_ue_to_ned(dvl_ue)
        depth_raw = extract_depth(state.get('DepthSensor', np.array([-pose[2, 3]])), pose[2, 3])
        depth_ned = float(-depth_raw if depth_raw < 0.0 else depth_raw)
        rpy_deg = np.degrees(tf['rpy_ned'])
        seabed_depth_m = float(self.config.get('digital_twin', {}).get('seabed_z_m', 15.0))
        altitude_m = max(0.0, seabed_depth_m - depth_ned)

        heading_deg = float((rpy_deg[2] + 360.0) % 360.0)
        pitch_deg = float(rpy_deg[1])
        roll_deg = float(rpy_deg[0])

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
            gps_speed_mps=max(0.0, float(dvl_ned[0])),
            dvl_speed_mps=float(dvl_ned[0]),
            altitude_m=altitude_m,
            total_voltage_v=self.telemetry_total_voltage_v,
            total_current_a=self.telemetry_total_current_a,
            soc=self.telemetry_soc,
            soh=self.telemetry_soh,
        )

    def run_forever(self):
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
            if self.sock is not None:
                self.sock.sendto(packet, self.last_client_addr)

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
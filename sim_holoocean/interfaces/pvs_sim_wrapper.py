from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PVS_ROOT = PROJECT_ROOT.parent / "PythonVehicleSimulator-master" / "src"
if str(PVS_ROOT) not in sys.path:
    sys.path.insert(0, str(PVS_ROOT))

from python_vehicle_simulator.lib.gnc import Rzyx, attitudeEuler
from python_vehicle_simulator.vehicles.remus100 import remus100


def _build_pose_matrix_ue(position_ned: np.ndarray, rpy_ned: np.ndarray) -> np.ndarray:
    pose = np.eye(4, dtype=float)
    roll_ue = float(rpy_ned[0])
    pitch_ue = float(-rpy_ned[1])
    yaw_ue = float(-rpy_ned[2])
    pose[:3, :3] = Rzyx(roll_ue, pitch_ue, yaw_ue)
    position_ned = np.asarray(position_ned, dtype=float).reshape(3)
    pose[:3, 3] = np.array([position_ned[0], position_ned[1], -position_ned[2]], dtype=float)
    return pose


class PVSSimWrapper:
    """Simulation adapter for PythonVehicleSimulator REMUS 100."""

    def __init__(self, *, config, scenario_cfg, agent_name, show_viewport=False, verbose=False):
        self.config = config or {}
        self.scenario_cfg = scenario_cfg
        self.agent_name = agent_name
        self.show_viewport = bool(show_viewport)
        self.verbose = bool(verbose)

        self.sim_cfg = dict(self.config.get("simulation", {}))
        self.pvs_cfg = dict(self.config.get("pvs", {}))
        self.dt = float(self.sim_cfg.get("dt", 1.0 / max(float(self.sim_cfg.get("ticks_per_sec", 30.0)), 1e-6)))
        self.control_mode = str(self.pvs_cfg.get("control_mode", self.sim_cfg.get("control_mode", "stepInput")))
        self.initial_depth_m = float(self.pvs_cfg.get("initial_depth_m", 12.0))
        self.initial_heading_deg = float(self.pvs_cfg.get("initial_heading_deg", 0.0))
        self.initial_speed_mps = float(self.pvs_cfg.get("initial_speed_mps", 0.5))
        self.initial_rpm = float(self.pvs_cfg.get("initial_rpm", 1200.0))
        self.reference_rpm = float(self.pvs_cfg.get("reference_rpm", self.initial_rpm))
        self.reference_speed_rpm_slope = float(self.pvs_cfg.get("reference_speed_rpm_slope", 581.0))
        self.reference_speed_rpm_offset = float(self.pvs_cfg.get("reference_speed_rpm_offset", -115.0))
        self.reference_rpm_min = float(self.pvs_cfg.get("reference_rpm_min", 300.0))
        self.command_thrust_rpm_scale = float(self.pvs_cfg.get("command_thrust_rpm_scale", 15.0))
        self.max_command_rpm = float(self.pvs_cfg.get("max_command_rpm", 1525.0))
        self.current_speed_mps = float(self.pvs_cfg.get("current_speed_mps", 0.5))
        self.current_direction_deg = float(self.pvs_cfg.get("current_direction_deg", 0.0))

        self.vehicle = None
        self.eta = np.array(
            [0.0, 0.0, self.initial_depth_m, 0.0, 0.0, np.deg2rad(self.initial_heading_deg)],
            dtype=float,
        )
        self.nu = np.array([self.initial_speed_mps, 0.0, 0.0, 0.0, 0.0, 0.0], dtype=float)
        self.u_actual = np.zeros(3, dtype=float)
        self.prev_nu = self.nu.copy()
        self.step_index = 0
        self.reference_depth_m = float(self.initial_depth_m)
        self.reference_heading_deg = float(self.initial_heading_deg)
        self.reference_rpm = float(self.reference_rpm)

    def set_reference(self, *, depth_m: float, heading_rad: float, speed_mps: float | None = None) -> None:
        self.reference_depth_m = float(depth_m)
        self.reference_heading_deg = float(math.degrees(float(heading_rad)))
        if speed_mps is not None:
            mapped_rpm = self.reference_speed_rpm_slope * float(speed_mps) + self.reference_speed_rpm_offset
            self.reference_rpm = float(
                np.clip(
                    mapped_rpm,
                    self.reference_rpm_min,
                    self.max_command_rpm,
                )
            )
        if self.vehicle is not None:
            self.vehicle.ref_z = self.reference_depth_m
            self.vehicle.ref_psi = self.reference_heading_deg
            self.vehicle.ref_n = float(self.reference_rpm)

    def open(self):
        mode = self.control_mode.strip().lower()
        if mode in {"depthheadingautopilot", "depth_heading_autopilot", "autopilot", "reference"}:
            control_system = "depthHeadingAutopilot"
        else:
            control_system = "stepInput"

        self.vehicle = remus100(
            controlSystem=control_system,
            r_z=self.reference_depth_m,
            r_psi=self.reference_heading_deg,
            r_rpm=self.reference_rpm,
            V_current=self.current_speed_mps,
            beta_current=self.current_direction_deg,
        )
        self.vehicle.nu = self.nu.copy()
        self.vehicle.u_actual = self.u_actual.copy()
        self.vehicle.z_d = self.reference_depth_m
        self.vehicle.z_int = 0.0
        self.vehicle.theta_int = 0.0
        self.vehicle.e_psi_int = 0.0
        self.vehicle.psi_d = np.deg2rad(self.reference_heading_deg)
        self.vehicle.r_d = 0.0
        self.vehicle.a_d = 0.0

        if self.verbose:
            print(
                f"[pvs] backend open: mode={control_system} depth={self.initial_depth_m:.2f}m "
                f"heading={self.initial_heading_deg:.1f}deg rpm={self.reference_rpm:.1f}"
            )
        return self

    def __enter__(self):
        return self.open()

    def __exit__(self, exc_type, exc, tb):
        self.close()
        return False

    def reset_and_tick(self):
        self.step_index = 0
        self.prev_nu = self.nu.copy()
        return self._build_state()

    def _command_to_actuators(self, command5) -> np.ndarray:
        cmd = np.asarray(command5, dtype=float).reshape(-1)
        if cmd.size != 5:
            raise ValueError("command must be length 5: [right,top,left,bottom,thrust]")

        rudder_deg = 0.5 * (float(cmd[2]) - float(cmd[0]))
        stern_deg = 0.5 * (float(cmd[3]) - float(cmd[1]))
        thrust_rpm = float(np.clip(float(cmd[4]) * self.command_thrust_rpm_scale, 0.0, self.max_command_rpm))
        return np.array([np.deg2rad(rudder_deg), np.deg2rad(stern_deg), thrust_rpm], dtype=float)

    def _build_state(self):
        position_ned = self.eta[:3].copy()
        rpy_ned = self.eta[3:6].copy()
        pose = _build_pose_matrix_ue(position_ned, rpy_ned)

        accel_ned = (self.nu[:3] - self.prev_nu[:3]) / max(self.dt, 1e-6)
        gyro_ned = self.nu[3:6].copy()
        accel_ue = np.array([accel_ned[0], accel_ned[1], -accel_ned[2]], dtype=float)
        gyro_ue = np.array([gyro_ned[0], gyro_ned[1], -gyro_ned[2]], dtype=float)
        return {
            self.agent_name: {
                "PoseSensor": pose,
                "DVLSensor": np.array([self.nu[0], self.nu[1], -self.nu[2]], dtype=float),
                "IMUSensor": np.concatenate([accel_ue, gyro_ue]),
                "DepthSensor": np.array([float(position_ned[2])], dtype=float),
            }
        }

    def step(self, command5):
        if self.vehicle is None:
            raise RuntimeError("PVS wrapper is not open")

        mode = self.control_mode.strip().lower()
        if mode in {"depthheadingautopilot", "depth_heading_autopilot", "autopilot", "reference"}:
            u_control = self.vehicle.depthHeadingAutopilot(self.eta, self.nu, self.dt)
        else:
            u_control = self._command_to_actuators(command5)

        self.prev_nu = self.nu.copy()
        self.nu, self.u_actual = self.vehicle.dynamics(self.eta, self.nu, self.u_actual, u_control, self.dt)
        self.eta = attitudeEuler(self.eta, self.nu, self.dt)
        self.step_index += 1
        return self._build_state()

    def close(self):
        self.vehicle = None

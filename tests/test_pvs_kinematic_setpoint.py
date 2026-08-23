import math

import numpy as np

from sim_holoocean.interfaces.pvs_sim_wrapper import PVSSimWrapper


def _minimal_config():
    return {
        "simulation": {
            "dt": 0.02,
            "ticks_per_sec": 50.0,
        },
        "environment": {
            "current": {"enabled": False},
        },
        "pvs": {
            "control_mode": "stepInput",
            "autonomy_motion_model": "kinematic_setpoint",
            "initial_depth_m": 12.0,
            "initial_heading_deg": 0.0,
            "initial_speed_mps": 0.5,
            "initial_rpm": 0.0,
            "reference_rpm": 520.0,
            "reference_speed_rpm_slope": 581.0,
            "reference_speed_rpm_offset": -115.0,
            "reference_rpm_min": 300.0,
            "command_thrust_rpm_scale": 15.0,
            "max_command_rpm": 1525.0,
            "kinematic_max_yaw_rate_deg_s": 12.0,
            "kinematic_depth_time_constant_s": 4.0,
        },
        "sensor_extrinsics_truth": {},
        "perception": {},
    }


def test_pvs_wrapper_kinematic_autonomy_moves_yaw_y_and_depth():
    wrapper = PVSSimWrapper(
        config=_minimal_config(),
        scenario_cfg={},
        agent_name="auv0",
        show_viewport=False,
        verbose=False,
    ).open()
    try:
        wrapper.control_mode = "depthHeadingAutopilot"
        wrapper.set_reference(
            depth_m=16.0,
            heading_rad=math.radians(25.0),
            speed_mps=0.8,
        )
        initial_eta = wrapper.eta.copy()
        for _ in range(100):
            wrapper.step([0.0, 0.0, 0.0, 0.0, 0.0])

        assert wrapper.eta[1] > initial_eta[1] + 0.2
        assert wrapper.eta[5] > initial_eta[5] + math.radians(5.0)
        assert wrapper.eta[2] > initial_eta[2] + 0.5
    finally:
        wrapper.close()


def test_pvs_wrapper_preserves_protocol_propeller_rpm_below_speed_profile_floor():
    wrapper = PVSSimWrapper(
        config=_minimal_config(),
        scenario_cfg={},
        agent_name="auv0",
        show_viewport=False,
        verbose=False,
    ).open()
    try:
        wrapper.set_reference(
            depth_m=12.0,
            heading_rad=0.0,
            propeller_rpm=75.0,
        )

        assert wrapper.reference_rpm == 75.0
        assert wrapper.vehicle.ref_n == 75.0
        assert wrapper.reference_speed_mps > 0.0
    finally:
        wrapper.close()


class _SaturatingDepthAutopilot:
    def __init__(self) -> None:
        self.z_int = 3.0
        self.theta_int = -0.5

    def depthHeadingAutopilot(self, eta, nu, sample_time):
        self.z_int += sample_time * 10.0
        self.theta_int -= sample_time * 5.0
        return np.array([0.0, math.radians(35.0), 700.0])


def test_pvs_depth_anti_windup_freezes_integrators_on_saturation():
    wrapper = PVSSimWrapper.__new__(PVSSimWrapper)
    wrapper.vehicle = _SaturatingDepthAutopilot()
    wrapper.eta = np.zeros(6)
    wrapper.nu = np.zeros(6)
    wrapper.dt = 0.02
    wrapper.deltaMax = math.radians(20.0)
    wrapper.depth_anti_windup_enabled = True
    wrapper.z_integral_limit = 10.0
    wrapper.theta_integral_limit = 2.0
    wrapper.depth_anti_windup_active = False
    wrapper.last_stern_command_raw_deg = 0.0

    control = wrapper._depth_heading_autopilot_control()

    assert math.degrees(control[1]) == 35.0
    assert wrapper.depth_anti_windup_active is True
    assert wrapper.vehicle.z_int == 3.0
    assert wrapper.vehicle.theta_int == -0.5

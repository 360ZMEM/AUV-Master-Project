import math

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

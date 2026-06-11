"""Tests for the hybrid control engine: mappers, base controller, PID wrapper, and MPC placeholder."""

import sys
import os
import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, 'common'))
sys.path.insert(0, os.path.join(PROJECT_ROOT, 'brain_linux', 'src', 'auv_controller'))

from auv_controller.mappers import (
    clamp_int16,
    rudder_deg_to_protocol,
    thrust_to_rpm,
    rudders_to_protocol_dict,
)
from auv_controller.base_controller import BaseController, ControlOutput
from auv_controller.mpc_controller import MPCController


class TestClampInt16:
    def test_normal_value(self):
        assert clamp_int16(100.0) == 100

    def test_zero(self):
        assert clamp_int16(0.0) == 0

    def test_rounding(self):
        assert clamp_int16(10.5) == 10
        assert clamp_int16(10.6) == 11

    def test_max_boundary(self):
        assert clamp_int16(32767.0) == 32767

    def test_min_boundary(self):
        assert clamp_int16(-32768.0) == -32768

    def test_above_max(self):
        assert clamp_int16(40000.0) == 32767

    def test_below_min(self):
        assert clamp_int16(-40000.0) == -32768


class TestRudderDegToProtocol:
    def test_zero_angle_no_bias(self):
        config = {"center_bias": 0.0, "gain": 1.0, "flip": False}
        assert rudder_deg_to_protocol(0.0, config) == 0

    def test_positive_angle(self):
        config = {"center_bias": 0.0, "gain": 1.0, "flip": False}
        assert rudder_deg_to_protocol(10.0, config) == 10000

    def test_negative_angle(self):
        config = {"center_bias": 0.0, "gain": 1.0, "flip": False}
        assert rudder_deg_to_protocol(-10.0, config) == -10000

    def test_center_bias(self):
        config = {"center_bias": 2.0, "gain": 1.0, "flip": False}
        assert rudder_deg_to_protocol(10.0, config) == 12000

    def test_gain(self):
        config = {"center_bias": 0.0, "gain": 1.5, "flip": False}
        assert rudder_deg_to_protocol(10.0, config) == 15000

    def test_flip(self):
        config = {"center_bias": 0.0, "gain": 1.0, "flip": True}
        assert rudder_deg_to_protocol(10.0, config) == -10000

    def test_combined_bias_and_gain(self):
        config = {"center_bias": 2.0, "gain": 1.2, "flip": False}
        expected = int(round((10.0 + 2.0) * 1.2 * 1000))
        assert rudder_deg_to_protocol(10.0, config) == expected

    def test_default_config(self):
        result = rudder_deg_to_protocol(5.0, {})
        assert result == 5000


class TestThrustToRpm:
    def test_zero_thrust(self):
        config = {"deadzone_percent": 5.0, "rpm_per_percent": 15.0, "voltage_nominal": 24.0, "voltage_compensation": False}
        assert thrust_to_rpm(0.0, config) == 0

    def test_below_deadzone(self):
        config = {"deadzone_percent": 5.0, "rpm_per_percent": 15.0, "voltage_nominal": 24.0, "voltage_compensation": False}
        result = thrust_to_rpm(1.0, config)
        assert result == int(round(5.0 * 15.0))

    def test_at_deadzone_boundary(self):
        config = {"deadzone_percent": 5.0, "rpm_per_percent": 15.0, "voltage_nominal": 24.0, "voltage_compensation": False}
        result = thrust_to_rpm(5.0, config)
        assert result == int(round(5.0 * 15.0))

    def test_above_deadzone(self):
        config = {"deadzone_percent": 5.0, "rpm_per_percent": 15.0, "voltage_nominal": 24.0, "voltage_compensation": False}
        result = thrust_to_rpm(10.0, config)
        assert result == int(round(10.0 * 15.0))

    def test_negative_thrust(self):
        config = {"deadzone_percent": 5.0, "rpm_per_percent": 15.0, "voltage_nominal": 24.0, "voltage_compensation": False}
        result = thrust_to_rpm(-10.0, config)
        assert result == -int(round(10.0 * 15.0))

    def test_voltage_compensation_low_voltage(self):
        config = {"deadzone_percent": 5.0, "rpm_per_percent": 15.0, "voltage_nominal": 24.0, "voltage_compensation": True}
        result = thrust_to_rpm(10.0, config, feedback_voltage=20.0)
        expected_base = 10.0 * 15.0
        voltage_ratio = 24.0 / 20.0
        expected = int(round(expected_base * voltage_ratio))
        assert result == expected

    def test_voltage_compensation_high_voltage(self):
        config = {"deadzone_percent": 5.0, "rpm_per_percent": 15.0, "voltage_nominal": 24.0, "voltage_compensation": True}
        result = thrust_to_rpm(10.0, config, feedback_voltage=28.0)
        expected_base = 10.0 * 15.0
        voltage_ratio = 24.0 / 28.0
        expected = int(round(expected_base * voltage_ratio))
        assert result == expected

    def test_voltage_compensation_clamped(self):
        config = {"deadzone_percent": 5.0, "rpm_per_percent": 15.0, "voltage_nominal": 24.0, "voltage_compensation": True}
        result = thrust_to_rpm(10.0, config, feedback_voltage=10.0)
        expected_base = 10.0 * 15.0
        voltage_ratio = max(0.8, min(1.5, 24.0 / 10.0))
        expected = int(round(expected_base * voltage_ratio))
        assert result == expected

    def test_default_config(self):
        result = thrust_to_rpm(10.0, {})
        assert result == int(round(10.0 * 15.0))


class TestRuddersToProtocolDict:
    def test_all_none(self):
        config = {"center_bias": 0.0, "gain": 1.0, "flip": False}
        result = rudders_to_protocol_dict(None, None, None, None, config)
        assert result == {"right": 0, "top": 0, "left": 0, "bottom": 0}

    def test_all_values(self):
        config = {"center_bias": 0.0, "gain": 1.0, "flip": False}
        result = rudders_to_protocol_dict(10.0, -5.0, 3.0, -2.0, config)
        assert result == {"right": 10000, "top": -5000, "left": 3000, "bottom": -2000}


class TestControlOutput:
    def test_default_values(self):
        output = ControlOutput()
        assert output.thrust_percent == 0.0
        assert output.right_fin_deg is None
        assert output.guidance_heading is None

    def test_to_dict(self):
        output = ControlOutput(thrust_percent=50.0, guidance_heading=1.57)
        d = output.to_dict()
        assert d["thrust_percent"] == 50.0
        assert d["guidance_heading"] == 1.57


class TestMPCController:
    def test_initial_state(self):
        """验证 MPC 控制器初始化后内部状态正确。"""
        ctrl = MPCController({}, {})
        assert ctrl._prev_U is None
        assert ctrl._solver_status == "NOT_RUN"
        assert ctrl._solve_time_ms == 0.0

    def test_reset_clears_warm_start(self):
        """验证 reset() 清除热启动缓存和求解状态。"""
        ctrl = MPCController({}, {})
        # 模拟已有热启动数据
        import numpy as np
        ctrl._prev_U = np.zeros((3, 20))
        ctrl._solver_status = "Solve_Succeeded"
        ctrl._solve_time_ms = 12.5
        ctrl._last_cost = 0.42
        ctrl.reset()
        assert ctrl._prev_U is None
        assert ctrl._solver_status == "NOT_RUN"
        assert ctrl._solve_time_ms == 0.0
        assert ctrl._last_cost == 0.0

    def test_compute_returns_control_output(self):
        """验证 compute() 返回 ControlOutput 且 debug 包含必要字段。"""
        ctrl = MPCController({}, {})
        state = {"x": 0, "y": 0, "z": 0, "u": 0, "v": 0, "w": 0,
                 "roll": 0, "pitch": 0, "yaw": 0, "p": 0, "q": 0, "r": 0}
        setpoint = {"target_depth_m": 2.0, "target_heading_rad": 0.0, "target_speed_mps": 1.0}
        result = ctrl.compute(state, setpoint)
        assert isinstance(result, ControlOutput)
        assert result.debug["controller_type"] == "MPC"
        assert "solver_status" in result.debug
        assert "solve_time_ms" in result.debug
        assert 0.0 <= result.thrust_percent <= 100.0

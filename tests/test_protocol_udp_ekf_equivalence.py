"""Protocol UDP vs Zenoh 模式下 ES-EKF 等价性验证。

本测试通过纯数值仿真（无 ROS2）对比两种后端数据流经过 ES-EKF 的输出差异，
诊断以下已知问题：
  1. DVL 坐标系错配：Protocol UDP 发送 body-frame 速度，但 EKF 用 correct_dvl_world()
  2. linear_acceleration 为零：Protocol UDP 模式缺失加速度输入
  3. 时间戳差异的影响

验收标准：
  - 在零 pitch/roll 条件下，两种模式 XY RMSE 差异 < 5%
  - 在非零 pitch (15°) 条件下，量化 DVL 坐标系错配造成的误差

用法：
  python -m pytest tests/test_protocol_udp_ekf_equivalence.py -v
"""

import sys
import os
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / 'algorithm'))

from algorithm.es_ekf import ES_EKF


def _make_default_ekf_cfg():
    return {
        "gravity": 9.81,
        "sigma_acc": 0.08,
        "sigma_gyro": 0.01,
        "sigma_ba": 0.001,
        "sigma_bg": 0.0005,
        "sigma_dvl": 0.03,
        "sigma_depth": 0.05,
        "imu_acc_is_linear": True,
        "init_pos": [0.0, 0.0, 0.0],
        "init_vel": [0.0, 0.0, 0.0],
        "init_quat_wxyz": [1.0, 0.0, 0.0, 0.0],
        "init_ba": [0.0, 0.0, 0.0],
        "init_bg": [0.0, 0.0, 0.0],
        "init_P_diag": [0.5]*3 + [0.5]*3 + [0.2]*3 + [0.05]*3 + [0.05]*3,
    }


def _euler_to_quat_wxyz(roll, pitch, yaw):
    """RPY (rad) -> quaternion [w, x, y, z]."""
    cr, sr = np.cos(roll/2), np.sin(roll/2)
    cp, sp = np.cos(pitch/2), np.sin(pitch/2)
    cy, sy = np.cos(yaw/2), np.sin(yaw/2)
    w = cr*cp*cy + sr*sp*sy
    x = sr*cp*cy - cr*sp*sy
    y = cr*sp*cy + sr*cp*sy
    z = cr*cp*sy - sr*sp*cy
    return [w, x, y, z]


def _quat_to_rotmat(q_wxyz):
    """quaternion [w, x, y, z] -> 3x3 rotation matrix R_nb."""
    w, x, y, z = q_wxyz
    return np.array([
        [1 - 2*(y**2 + z**2), 2*(x*y - w*z), 2*(x*z + w*y)],
        [2*(x*y + w*z), 1 - 2*(x**2 + z**2), 2*(y*z - w*x)],
        [2*(x*z - w*y), 2*(y*z + w*x), 1 - 2*(x**2 + y**2)],
    ])


def _simulate_straight_line(duration_s=30.0, dt=0.05, speed_mps=1.5,
                            pitch_rad=0.0, heading_rad=0.0):
    """生成一段直线运动的真值轨迹。

    返回:
        times: (N,) 时间序列
        true_positions: (N, 3) NED 真值位置
        true_velocities_world: (N, 3) 世界系速度
        true_velocities_body: (N, 3) 机体系速度
        true_accels_body: (N, 3) 机体系加速度（线性，已去重力）
        true_gyros_body: (N, 3) 机体系角速度
    """
    N = int(duration_s / dt)
    times = np.arange(N) * dt

    # 机体系速度: 前向 speed_mps，侧向/垂向为 0
    vel_body = np.array([speed_mps, 0.0, 0.0])

    # 旋转矩阵 body->world
    q = _euler_to_quat_wxyz(0.0, pitch_rad, heading_rad)
    R_nb = _quat_to_rotmat(q)

    vel_world = R_nb @ vel_body

    true_positions = np.zeros((N, 3))
    for i in range(1, N):
        true_positions[i] = true_positions[i-1] + vel_world * dt

    true_velocities_world = np.tile(vel_world, (N, 1))
    true_velocities_body = np.tile(vel_body, (N, 1))

    # 匀速: 线性加速度为 0
    true_accels_body = np.zeros((N, 3))
    true_gyros_body = np.zeros((N, 3))

    return times, true_positions, true_velocities_world, true_velocities_body, true_accels_body, true_gyros_body


def _run_ekf_zenoh_mode(times, true_pos, vel_world, accel_body, gyro_body, pitch_rad, heading_rad):
    """模拟 Zenoh 模式数据流。

    Zenoh 模式特征:
      - DVL: 世界系 NED 速度 (vel_ned)
      - IMU: body 系加速度 + 角速度（命名为 accel_ned/gyro_ned，实为 body）
      - 时间戳: 传感器原始时间
    """
    cfg = _make_default_ekf_cfg()
    cfg["init_quat_wxyz"] = _euler_to_quat_wxyz(0.0, pitch_rad, heading_rad)
    ekf = ES_EKF(cfg)

    dt = times[1] - times[0]
    estimated_positions = []

    for i in range(len(times)):
        # predict: body frame accel + gyro
        ekf.predict(accel_body[i], gyro_body[i], dt)

        # correct DVL: 世界系速度 (Zenoh 模式)
        if i % 10 == 0:  # DVL at 2Hz (every 10 steps @ 20Hz)
            ekf.correct_dvl_world(vel_world[i])

        # correct depth
        if i % 4 == 0:  # depth at 5Hz
            ekf.correct_depth(-true_pos[i, 2])  # depth = -z in NED

        state = ekf.get_state()
        estimated_positions.append(state['p'].copy())

    return np.array(estimated_positions)


def _run_ekf_protocol_udp_mode(times, true_pos, vel_body, pitch_rad, heading_rad):
    """模拟 Protocol UDP 模式数据流（当前 BUG 版本）。

    Protocol UDP 模式特征:
      - DVL: body 系速度 (dvl_body_x/y/z_mps)
      - IMU: angular_velocity 正常，linear_acceleration = [0,0,0]
      - 但 EKF 仍调用 correct_dvl_world() (BUG!)
    """
    cfg = _make_default_ekf_cfg()
    cfg["init_quat_wxyz"] = _euler_to_quat_wxyz(0.0, pitch_rad, heading_rad)
    ekf = ES_EKF(cfg)

    dt = times[1] - times[0]
    estimated_positions = []
    zero_accel = np.zeros(3)
    zero_gyro = np.zeros(3)

    for i in range(len(times)):
        # predict: Protocol UDP 模式 accel=0, gyro 正常（匀速直线时 gyro=0 是真值）
        ekf.predict(zero_accel, zero_gyro, dt)

        # correct DVL: body 系速度但错误地用 correct_dvl_world() (当前BUG)
        if i % 10 == 0:
            ekf.correct_dvl_world(vel_body[i])  # BUG: body frame → world API

        # correct depth
        if i % 4 == 0:
            ekf.correct_depth(-true_pos[i, 2])

        state = ekf.get_state()
        estimated_positions.append(state['p'].copy())

    return np.array(estimated_positions)


def _run_ekf_protocol_udp_fixed(times, true_pos, vel_body, pitch_rad, heading_rad):
    """Protocol UDP 模式修复方案B：bridge_node 预旋转 DVL 到世界系。

    修复策略：在 bridge_node 中利用已有的 roll/pitch/heading 把 body-frame DVL
    旋转到世界系后再发布到 /auv/sensors/dvl，localization_node 无需改动。
    """
    cfg = _make_default_ekf_cfg()
    cfg["init_quat_wxyz"] = _euler_to_quat_wxyz(0.0, pitch_rad, heading_rad)
    ekf = ES_EKF(cfg)

    dt = times[1] - times[0]
    estimated_positions = []
    zero_accel = np.zeros(3)
    zero_gyro = np.zeros(3)

    # 预计算 R_nb（实际 bridge_node 中每帧从 telemetry RPY 计算）
    q = _euler_to_quat_wxyz(0.0, pitch_rad, heading_rad)
    R_nb = _quat_to_rotmat(q)

    for i in range(len(times)):
        ekf.predict(zero_accel, zero_gyro, dt)

        # 修复: bridge_node 预旋转 body→world，然后 EKF 照常用 correct_dvl_world()
        if i % 10 == 0:
            vel_world_rotated = R_nb @ vel_body[i]
            ekf.correct_dvl_world(vel_world_rotated)

        # correct depth
        if i % 4 == 0:
            ekf.correct_depth(-true_pos[i, 2])

        state = ekf.get_state()
        estimated_positions.append(state['p'].copy())

    return np.array(estimated_positions)


def _run_ekf_protocol_udp_fixed_body_api(times, true_pos, vel_body, pitch_rad, heading_rad):
    """Protocol UDP 模式修复方案A：localization_node 改用 correct_dvl()。

    修复策略：localization_node 根据参数切换到 correct_dvl()（body frame API）。
    需要 EKF 内部姿态准确维护。
    """
    cfg = _make_default_ekf_cfg()
    cfg["init_quat_wxyz"] = _euler_to_quat_wxyz(0.0, pitch_rad, heading_rad)
    ekf = ES_EKF(cfg)

    dt = times[1] - times[0]
    estimated_positions = []
    zero_accel = np.zeros(3)
    zero_gyro = np.zeros(3)

    for i in range(len(times)):
        ekf.predict(zero_accel, zero_gyro, dt)

        # 方案A: 直接用 body frame API
        if i % 10 == 0:
            ekf.correct_dvl(vel_body[i])

        if i % 4 == 0:
            ekf.correct_depth(-true_pos[i, 2])

        state = ekf.get_state()
        estimated_positions.append(state['p'].copy())

    return np.array(estimated_positions)


def _compute_rmse(estimated, truth):
    """计算 XY 平面 RMSE。"""
    err = estimated[:, :2] - truth[:, :2]
    return float(np.sqrt(np.mean(np.sum(err**2, axis=1))))


def _compute_3d_rmse(estimated, truth):
    """计算 3D RMSE。"""
    err = estimated - truth
    return float(np.sqrt(np.mean(np.sum(err**2, axis=1))))


class TestProtocolUdpEkfEquivalence:
    """Protocol UDP 与 Zenoh 模式 ES-EKF 等价性对比。"""

    def test_level_flight_equivalence(self):
        """零 pitch/roll, heading=0: Protocol UDP 与 Zenoh 应完全等价。

        当 heading=0 且 pitch=0 时，body frame 完全等于 world frame。
        """
        times, true_pos, vel_world, vel_body, accel_body, gyro_body = \
            _simulate_straight_line(duration_s=30.0, pitch_rad=0.0, heading_rad=0.0)

        est_zenoh = _run_ekf_zenoh_mode(times, true_pos, vel_world, accel_body, gyro_body, 0.0, 0.0)
        est_udp = _run_ekf_protocol_udp_mode(times, true_pos, vel_body, 0.0, 0.0)

        rmse_zenoh = _compute_rmse(est_zenoh, true_pos)
        rmse_udp = _compute_rmse(est_udp, true_pos)

        print(f"\n[Level h=0] Zenoh XY RMSE: {rmse_zenoh:.4f} m")
        print(f"[Level h=0] Protocol UDP XY RMSE: {rmse_udp:.4f} m")

        # heading=0, pitch=0: body == world, 两者应完全等价
        assert abs(rmse_udp - rmse_zenoh) < 0.01

    def test_heading_causes_dvl_error(self):
        """heading=30°, pitch=0: 仅航向即可暴露 DVL 坐标系 bug。

        body_vel=[1.5, 0, 0] ≠ world_vel=[1.5*cos30, 1.5*sin30, 0]
        correct_dvl_world(body_vel) 将 EKF 速度拉向错误方向。
        """
        heading_rad = np.radians(30.0)
        times, true_pos, vel_world, vel_body, accel_body, gyro_body = \
            _simulate_straight_line(duration_s=30.0, pitch_rad=0.0, heading_rad=heading_rad)

        est_zenoh = _run_ekf_zenoh_mode(times, true_pos, vel_world, accel_body, gyro_body, 0.0, heading_rad)
        est_udp_buggy = _run_ekf_protocol_udp_mode(times, true_pos, vel_body, 0.0, heading_rad)
        est_udp_fixed = _run_ekf_protocol_udp_fixed(times, true_pos, vel_body, 0.0, heading_rad)

        rmse_zenoh = _compute_rmse(est_zenoh, true_pos)
        rmse_udp_buggy = _compute_rmse(est_udp_buggy, true_pos)
        rmse_udp_fixed = _compute_rmse(est_udp_fixed, true_pos)

        print(f"\n[Heading 30°] Zenoh XY RMSE: {rmse_zenoh:.4f} m")
        print(f"[Heading 30°] Protocol UDP (buggy): {rmse_udp_buggy:.4f} m")
        print(f"[Heading 30°] Protocol UDP (fix B: pre-rotate): {rmse_udp_fixed:.4f} m")

        # 修复后应接近 Zenoh 水平
        assert rmse_udp_fixed < rmse_udp_buggy * 0.1, \
            f"Fix B should reduce error 10x: fixed={rmse_udp_fixed:.4f}, buggy={rmse_udp_buggy:.4f}"

    def test_pitched_flight_dvl_mismatch(self):
        """15° pitch, heading=0: 量化 pitch 导致的 DVL 坐标系错配。"""
        pitch_rad = np.radians(15.0)
        times, true_pos, vel_world, vel_body, accel_body, gyro_body = \
            _simulate_straight_line(duration_s=30.0, pitch_rad=pitch_rad, heading_rad=0.0)

        est_zenoh = _run_ekf_zenoh_mode(times, true_pos, vel_world, accel_body, gyro_body, pitch_rad, 0.0)
        est_udp_buggy = _run_ekf_protocol_udp_mode(times, true_pos, vel_body, pitch_rad, 0.0)
        est_udp_fixed = _run_ekf_protocol_udp_fixed(times, true_pos, vel_body, pitch_rad, 0.0)
        est_udp_body_api = _run_ekf_protocol_udp_fixed_body_api(times, true_pos, vel_body, pitch_rad, 0.0)

        rmse_zenoh = _compute_rmse(est_zenoh, true_pos)
        rmse_buggy = _compute_rmse(est_udp_buggy, true_pos)
        rmse_fix_b = _compute_rmse(est_udp_fixed, true_pos)
        rmse_fix_a = _compute_rmse(est_udp_body_api, true_pos)

        print(f"\n[Pitched 15°] Zenoh XY RMSE: {rmse_zenoh:.4f} m")
        print(f"[Pitched 15°] UDP buggy: {rmse_buggy:.4f} m")
        print(f"[Pitched 15°] UDP fix B (pre-rotate): {rmse_fix_b:.4f} m")
        print(f"[Pitched 15°] UDP fix A (correct_dvl body API): {rmse_fix_a:.4f} m")

        # 方案B (pre-rotate) 应接近 Zenoh
        assert rmse_fix_b < 0.01, f"Fix B should be near-zero: {rmse_fix_b:.4f}"

    def test_combined_heading_pitch(self):
        """heading=45° + pitch=10°: 组合姿态的典型实际场景。"""
        heading_rad = np.radians(45.0)
        pitch_rad = np.radians(10.0)
        times, true_pos, vel_world, vel_body, accel_body, gyro_body = \
            _simulate_straight_line(duration_s=30.0, pitch_rad=pitch_rad,
                                    heading_rad=heading_rad, speed_mps=1.2)

        est_zenoh = _run_ekf_zenoh_mode(times, true_pos, vel_world, accel_body, gyro_body, pitch_rad, heading_rad)
        est_udp_buggy = _run_ekf_protocol_udp_mode(times, true_pos, vel_body, pitch_rad, heading_rad)
        est_udp_fixed = _run_ekf_protocol_udp_fixed(times, true_pos, vel_body, pitch_rad, heading_rad)

        rmse_zenoh = _compute_rmse(est_zenoh, true_pos)
        rmse_buggy = _compute_rmse(est_udp_buggy, true_pos)
        rmse_fixed = _compute_rmse(est_udp_fixed, true_pos)

        print(f"\n[h=45° p=10°] Zenoh RMSE: {rmse_zenoh:.4f} m")
        print(f"[h=45° p=10°] UDP buggy: {rmse_buggy:.4f} m")
        print(f"[h=45° p=10°] UDP fix B: {rmse_fixed:.4f} m")
        print(f"[h=45° p=10°] Error reduction: {rmse_buggy / max(rmse_fixed, 1e-6):.0f}x")

        assert rmse_fixed < rmse_buggy * 0.1


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v", "-s"])

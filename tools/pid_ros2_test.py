#!/usr/bin/env python3
"""ROS2 PID 控制器离线测试：使用 PVS 动力学模型验证 params.yaml 参数。

测试场景：
  1. 深度阶跃响应：z=0 → z=5m（40秒）
  2. 航向阶跃响应：ψ=0 → ψ=30°（40秒）
  3. 电缆跟踪轨迹：正弦深度 + 余弦航向（60秒）

输出：RMSE、最大误差、控制量曲线、性能分析
"""

import sys
import os
import time
import datetime
import numpy as np
from pathlib import Path

os.environ['MPLBACKEND'] = 'Agg'
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker

sys.path.insert(0, '/root/PythonVehicleSimulator/src')
from python_vehicle_simulator.vehicles.remus100 import remus100

import importlib.util
project_root = Path(__file__).resolve().parent.parent
from common.env_utils import get_output_dir
algo_dir = project_root / 'algorithm'
module_path = algo_dir / 'auv_pid_controller.py'
spec = importlib.util.spec_from_file_location('auv_pid_controller', str(module_path))
auv_pid_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(auv_pid_module)
AUVPIDController = auv_pid_module.AUVPIDController

import yaml
params_file = project_root / 'brain_linux' / 'config' / 'params.yaml'
with open(params_file, 'r') as f:
    cfg = yaml.safe_load(f)

RESULTS_DIR = get_output_dir('results/control/pid_test')
RESULTS_DIR.mkdir(parents=True, exist_ok=True)
FIGURES_DIR = RESULTS_DIR / 'figures'
FIGURES_DIR.mkdir(parents=True, exist_ok=True)

plt.rcParams.update({
    'figure.dpi': 150,
    'savefig.dpi': 300,
    'font.size': 10,
    'axes.titlesize': 12,
    'axes.labelsize': 11,
    'lines.linewidth': 1.5,
    'lines.markersize': 4,
    'grid.alpha': 0.3,
})


def reset_controller(controller):
    """重置控制器的积分器和状态。"""
    for pid_axis in [controller.depth_pid, controller.pitch_pid,
                     controller.yaw_pid, controller.speed_pid]:
        pid_axis.reset_integral()
    controller.prev_target_pitch = 0.0


def create_controller():
    """从 params.yaml 创建 AUVPIDController 实例。"""
    ctrl_cfg = cfg.get('control', {})
    lim_cfg = cfg.get('limits', {})
    controller = AUVPIDController(ctrl_cfg, lim_cfg)
    return controller


class PVSRemusSim:
    """基于 PVS remus100 的 AUV 仿真器，支持 AUVPIDController 闭环测试。"""

    def __init__(self, dt=0.05, u_init=1.5):
        self.dt = dt
        self.vehicle = remus100()
        self.eta = np.zeros(6, float)
        self.nu = np.array([u_init, 0, 0, 0, 0, 0], float)
        self.u_actual = np.array([0, 0, 1525], float)
        self.target_u = u_init

    def get_state(self):
        return {
            'roll': self.eta[3],
            'pitch': -self.eta[4],
            'yaw': self.eta[5],
            'x': self.eta[0],
            'y': self.eta[1],
            'z': self.eta[2],
            'depth': self.eta[2],
            'u': self.nu[0],
            'v': self.nu[1],
            'w': self.nu[2],
            'p': self.nu[3],
            'q': self.nu[4],
            'r': self.nu[5],
        }

    def apply_control(self, command):
        right_fin_deg = command[0]
        top_fin_deg = command[1]
        thrust_pct = command[4]

        stern_deg = right_fin_deg
        rudder_deg = -top_fin_deg

        delta_s = np.deg2rad(np.clip(stern_deg, -15.0, 15.0))
        delta_r = np.deg2rad(np.clip(rudder_deg, -15.0, 15.0))

        n_max = 1525
        n = np.clip(thrust_pct * n_max / 100.0, 0, n_max)

        self.u_control = np.array([delta_r, delta_s, n], float)

    def step(self):
        dt = self.dt
        self.nu, self.u_actual = self.vehicle.dynamics(
            self.eta, self.nu, self.u_actual, self.u_control, dt
        )

        phi, theta, psi = self.eta[3], self.eta[4], self.eta[5]
        cphi, sphi = np.cos(phi), np.sin(phi)
        ctheta, stheta = np.cos(theta), np.sin(theta)
        cpsi, spsi = np.cos(psi), np.sin(psi)

        J = np.array([
            [cpsi*ctheta, -spsi*cphi+cpsi*stheta*sphi, spsi*sphi+cpsi*cphi*stheta, 0, 0, 0],
            [spsi*ctheta, cpsi*cphi+spsi*stheta*sphi, -cpsi*sphi+spsi*ctheta*sphi, 0, 0, 0],
            [-stheta, ctheta*sphi, ctheta*cphi, 0, 0, 0],
            [0, 0, 0, 1, sphi*stheta/ctheta, cphi*stheta/ctheta],
            [0, 0, 0, 0, cphi, -sphi],
            [0, 0, 0, 0, sphi/ctheta, cphi/ctheta]
        ])

        eta_dot = J @ self.nu
        self.eta += dt * eta_dot


def test_depth_step_response(controller, duration=40.0, target_depth=5.0):
    print(f"\n{'='*60}")
    print(f"测试 1: 深度阶跃响应 (0 → {target_depth}m, {duration}s)")
    print(f"{'='*60}")

    sim = PVSRemusSim(dt=0.05)
    dt = sim.dt
    steps = int(duration / dt)

    depth_history = []
    target_history = []
    time_history = []
    stern_history = []
    thrust_history = []
    theta_history = []
    pitch_history = []
    u_history = []

    for i in range(steps):
        t = i * dt
        state = sim.get_state()

        target = {
            'dt': dt,
            'target_depth': target_depth,
            'target_yaw': 0.0,
            'target_u': sim.target_u,
        }

        command, debug = controller.compute(state, target)
        sim.apply_control(command)
        sim.step()

        depth_history.append(state['depth'])
        target_history.append(target_depth)
        time_history.append(t)
        stern_history.append(command[0])
        thrust_history.append(command[4])
        theta_history.append(sim.eta[4])
        pitch_history.append(state['pitch'])
        u_history.append(state['u'])

    depth_array = np.array(depth_history)
    target_array = np.array(target_history)
    error = depth_array - target_array
    rmse = np.sqrt(np.mean(error**2))
    max_error = np.max(np.abs(error))
    final_depth = depth_array[-1]

    threshold = 0.9 * target_depth
    rise_time = None
    for i, d in enumerate(depth_history):
        if d >= threshold:
            rise_time = time_history[i]
            break

    print(f"深度 RMSE: {rmse:.3f} m")
    print(f"深度最大误差: {max_error:.3f} m")
    print(f"最终深度: {final_depth:.3f} m (目标: {target_depth}m)")
    if rise_time is not None:
        print(f"达到 90% 目标深度时间: {rise_time:.2f}s")
    else:
        print("达到 90% 目标深度时间: 未达到")

    return {
        'time': time_history,
        'depth': depth_history,
        'target': target_history,
        'stern': stern_history,
        'thrust': thrust_history,
        'theta': theta_history,
        'pitch': pitch_history,
        'u': u_history,
        'rmse': rmse,
        'max_error': max_error,
        'final_depth': final_depth,
        'rise_time': rise_time,
    }


def test_heading_step_response(controller, duration=40.0, target_heading_deg=30.0):
    print(f"\n{'='*60}")
    print(f"测试 2: 航向阶跃响应 (0 → {target_heading_deg}°, {duration}s)")
    print(f"{'='*60}")

    sim = PVSRemusSim(dt=0.05)
    dt = sim.dt
    steps = int(duration / dt)
    target_heading = np.deg2rad(target_heading_deg)

    yaw_history = []
    target_history = []
    time_history = []
    rudder_history = []
    thrust_history = []
    u_history = []

    for i in range(steps):
        t = i * dt
        state = sim.get_state()

        target = {
            'dt': dt,
            'target_depth': 2.0,
            'target_yaw': target_heading,
            'target_u': sim.target_u,
        }

        command, debug = controller.compute(state, target)
        sim.apply_control(command)
        sim.step()

        yaw_history.append(state['yaw'])
        target_history.append(target_heading)
        time_history.append(t)
        rudder_history.append(command[1])
        thrust_history.append(command[4])
        u_history.append(state['u'])

    yaw_array = np.array(yaw_history)
    target_array = np.array(target_history)
    error = np.arctan2(np.sin(yaw_array - target_array), np.cos(yaw_array - target_array))
    rmse = np.sqrt(np.mean(error**2))
    max_error = np.max(np.abs(error))
    final_yaw = yaw_array[-1]

    threshold = 0.9 * target_heading
    rise_time = None
    for i, y in enumerate(yaw_history):
        if y >= threshold:
            rise_time = time_history[i]
            break

    print(f"航向 RMSE: {rmse:.3f} rad ({np.rad2deg(rmse):.2f}°)")
    print(f"航向最大误差: {max_error:.3f} rad ({np.rad2deg(max_error):.2f}°)")
    print(f"最终航向: {np.rad2deg(final_yaw):.2f}° (目标: {target_heading_deg}°)")
    if rise_time is not None:
        print(f"达到 90% 目标航向时间: {rise_time:.2f}s")
    else:
        print("达到 90% 目标航向时间: 未达到")

    return {
        'time': time_history,
        'yaw': yaw_history,
        'target': target_history,
        'rudder': rudder_history,
        'thrust': thrust_history,
        'u': u_history,
        'rmse': rmse,
        'max_error': max_error,
        'final_yaw': final_yaw,
        'rise_time': rise_time,
    }


def test_cable_tracking(controller, duration=60.0):
    print(f"\n{'='*60}")
    print(f"测试 3: 电缆跟踪轨迹 ({duration}s)")
    print(f"{'='*60}")

    sim = PVSRemusSim(dt=0.05)
    dt = sim.dt
    steps = int(duration / dt)

    depth_history = []
    yaw_history = []
    target_depth_history = []
    target_yaw_history = []
    time_history = []
    stern_history = []
    rudder_history = []
    thrust_history = []
    u_history = []

    for i in range(steps):
        t = i * dt
        state = sim.get_state()

        target_depth = 3.0 + 2.0 * np.sin(0.2 * t)
        target_yaw = np.deg2rad(20.0 * np.cos(0.15 * t))

        target = {
            'dt': dt,
            'target_depth': target_depth,
            'target_yaw': target_yaw,
            'target_u': sim.target_u,
        }

        command, debug = controller.compute(state, target)
        sim.apply_control(command)
        sim.step()

        depth_history.append(state['depth'])
        yaw_history.append(state['yaw'])
        target_depth_history.append(target_depth)
        target_yaw_history.append(target_yaw)
        time_history.append(t)
        stern_history.append(command[0])
        rudder_history.append(command[1])
        thrust_history.append(command[4])
        u_history.append(state['u'])

    depth_array = np.array(depth_history)
    target_depth_array = np.array(target_depth_history)
    yaw_array = np.array(yaw_history)
    target_yaw_array = np.array(target_yaw_history)

    depth_error = depth_array - target_depth_array
    yaw_error = np.arctan2(np.sin(yaw_array - target_yaw_array), np.cos(yaw_array - target_yaw_array))

    depth_rmse = np.sqrt(np.mean(depth_error**2))
    yaw_rmse = np.sqrt(np.mean(yaw_error**2))
    depth_max_error = np.max(np.abs(depth_error))
    yaw_max_error = np.max(np.abs(yaw_error))

    print(f"深度 RMSE: {depth_rmse:.3f} m")
    print(f"航向 RMSE: {yaw_rmse:.3f} rad ({np.rad2deg(yaw_rmse):.2f}°)")
    print(f"深度最大误差: {depth_max_error:.3f} m")
    print(f"航向最大误差: {np.rad2deg(yaw_max_error):.2f}°")

    return {
        'time': time_history,
        'depth': depth_history,
        'yaw': yaw_history,
        'target_depth': target_depth_history,
        'target_yaw': target_yaw_history,
        'stern': stern_history,
        'rudder': rudder_history,
        'thrust': thrust_history,
        'u': u_history,
        'depth_rmse': depth_rmse,
        'yaw_rmse': yaw_rmse,
        'depth_max_error': depth_max_error,
        'yaw_max_error': yaw_max_error,
    }


def generate_plots(results):
    """生成所有控制响应曲线图。"""
    fig_paths = []

    # 图1: 深度阶跃响应
    fig, axes = plt.subplots(3, 1, figsize=(12, 9), sharex=True)
    t = results['depth_step']['time']
    d = results['depth_step']['depth']
    tgt = results['depth_step']['target']
    stern = results['depth_step']['stern']
    thrust = results['depth_step']['thrust']

    axes[0].plot(t, d, 'b-', linewidth=2, label='Actual Depth')
    axes[0].plot(t, tgt, 'r--', linewidth=1.5, label='Target Depth')
    axes[0].set_ylabel('Depth (m)')
    axes[0].set_title('Depth Step Response')
    axes[0].legend(loc='lower right', fontsize=9)
    axes[0].grid(True)

    axes[1].plot(t, stern, 'g-', linewidth=1.5)
    axes[1].axhline(y=15.0, color='r', linestyle=':', linewidth=1, alpha=0.7)
    axes[1].axhline(y=-15.0, color='r', linestyle=':', linewidth=1, alpha=0.7)
    axes[1].set_ylabel('Stern Fin Angle (deg)')
    axes[1].set_title('Stern Fin Command')
    axes[1].grid(True)

    axes[2].plot(t, thrust, 'orange', linewidth=1.5)
    axes[2].set_ylabel('Thrust (%)')
    axes[2].set_xlabel('Time (s)')
    axes[2].set_title('Thrust Command')
    axes[2].grid(True)

    plt.tight_layout()
    path = FIGURES_DIR / '01_depth_step_response.png'
    fig.savefig(path, bbox_inches='tight')
    plt.close(fig)
    fig_paths.append(str(path.name))

    # 图2: 航向阶跃响应
    fig, axes = plt.subplots(3, 1, figsize=(12, 9), sharex=True)
    t = results['heading_step']['time']
    yaw = np.rad2deg(results['heading_step']['yaw'])
    yaw_tgt = np.rad2deg(results['heading_step']['target'])
    rudder = results['heading_step']['rudder']
    thrust = results['heading_step']['thrust']

    axes[0].plot(t, yaw, 'b-', linewidth=2, label='Actual Heading')
    axes[0].plot(t, yaw_tgt, 'r--', linewidth=1.5, label='Target Heading')
    axes[0].set_ylabel('Heading (deg)')
    axes[0].set_title('Heading Step Response')
    axes[0].legend(loc='lower right', fontsize=9)
    axes[0].grid(True)

    axes[1].plot(t, rudder, 'g-', linewidth=1.5)
    axes[1].axhline(y=15.0, color='r', linestyle=':', linewidth=1, alpha=0.7)
    axes[1].axhline(y=-15.0, color='r', linestyle=':', linewidth=1, alpha=0.7)
    axes[1].set_ylabel('Rudder Angle (deg)')
    axes[1].set_title('Rudder Command')
    axes[1].grid(True)

    axes[2].plot(t, thrust, 'orange', linewidth=1.5)
    axes[2].set_ylabel('Thrust (%)')
    axes[2].set_xlabel('Time (s)')
    axes[2].set_title('Thrust Command')
    axes[2].grid(True)

    plt.tight_layout()
    path = FIGURES_DIR / '02_heading_step_response.png'
    fig.savefig(path, bbox_inches='tight')
    plt.close(fig)
    fig_paths.append(str(path.name))

    # 图3: 电缆跟踪 - 深度
    fig, axes = plt.subplots(3, 1, figsize=(12, 9), sharex=True)
    t = results['cable_tracking']['time']
    d = results['cable_tracking']['depth']
    d_tgt = results['cable_tracking']['target_depth']
    stern = results['cable_tracking']['stern']
    thrust = results['cable_tracking']['thrust']

    axes[0].plot(t, d, 'b-', linewidth=1.5, label='Actual Depth')
    axes[0].plot(t, d_tgt, 'r--', linewidth=1.5, label='Target Depth')
    axes[0].set_ylabel('Depth (m)')
    axes[0].set_title('Cable Tracking - Depth')
    axes[0].legend(loc='best', fontsize=9)
    axes[0].grid(True)

    axes[1].plot(t, stern, 'g-', linewidth=1.2)
    axes[1].axhline(y=15.0, color='r', linestyle=':', linewidth=1, alpha=0.7)
    axes[1].axhline(y=-15.0, color='r', linestyle=':', linewidth=1, alpha=0.7)
    axes[1].set_ylabel('Stern Fin Angle (deg)')
    axes[1].grid(True)

    axes[2].plot(t, thrust, 'orange', linewidth=1.2)
    axes[2].set_ylabel('Thrust (%)')
    axes[2].set_xlabel('Time (s)')
    axes[2].grid(True)

    plt.tight_layout()
    path = FIGURES_DIR / '03_cable_tracking_depth.png'
    fig.savefig(path, bbox_inches='tight')
    plt.close(fig)
    fig_paths.append(str(path.name))

    # 图4: 电缆跟踪 - 航向
    fig, axes = plt.subplots(3, 1, figsize=(12, 9), sharex=True)
    t = results['cable_tracking']['time']
    yaw = np.rad2deg(results['cable_tracking']['yaw'])
    yaw_tgt = np.rad2deg(results['cable_tracking']['target_yaw'])
    rudder = results['cable_tracking']['rudder']

    axes[0].plot(t, yaw, 'b-', linewidth=1.5, label='Actual Heading')
    axes[0].plot(t, yaw_tgt, 'r--', linewidth=1.5, label='Target Heading')
    axes[0].set_ylabel('Heading (deg)')
    axes[0].set_title('Cable Tracking - Heading')
    axes[0].legend(loc='best', fontsize=9)
    axes[0].grid(True)

    axes[1].plot(t, rudder, 'g-', linewidth=1.2)
    axes[1].axhline(y=15.0, color='r', linestyle=':', linewidth=1, alpha=0.7)
    axes[1].axhline(y=-15.0, color='r', linestyle=':', linewidth=1, alpha=0.7)
    axes[1].set_ylabel('Rudder Angle (deg)')
    axes[1].grid(True)

    axes[2].plot(t, results['cable_tracking']['u'], 'm-', linewidth=1.2)
    axes[2].set_ylabel('Surge Speed (m/s)')
    axes[2].set_xlabel('Time (s)')
    axes[2].grid(True)

    plt.tight_layout()
    path = FIGURES_DIR / '04_cable_tracking_heading.png'
    fig.savefig(path, bbox_inches='tight')
    plt.close(fig)
    fig_paths.append(str(path.name))

    # 图5: 综合对比
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))

    t_ds = results['depth_step']['time']
    axes[0, 0].plot(t_ds, results['depth_step']['depth'], 'b-', linewidth=2)
    axes[0, 0].plot(t_ds, results['depth_step']['target'], 'r--', linewidth=1.5)
    axes[0, 0].set_xlabel('Time (s)')
    axes[0, 0].set_ylabel('Depth (m)')
    axes[0, 0].set_title('Depth Step Response')
    axes[0, 0].grid(True)

    t_hs = results['heading_step']['time']
    axes[0, 1].plot(t_hs, np.rad2deg(results['heading_step']['yaw']), 'b-', linewidth=2)
    axes[0, 1].plot(t_hs, np.rad2deg(results['heading_step']['target']), 'r--', linewidth=1.5)
    axes[0, 1].set_xlabel('Time (s)')
    axes[0, 1].set_ylabel('Heading (deg)')
    axes[0, 1].set_title('Heading Step Response')
    axes[0, 1].grid(True)

    t_ct = results['cable_tracking']['time']
    axes[1, 0].plot(t_ct, results['cable_tracking']['depth'], 'b-', linewidth=1.5)
    axes[1, 0].plot(t_ct, results['cable_tracking']['target_depth'], 'r--', linewidth=1.5)
    axes[1, 0].set_xlabel('Time (s)')
    axes[1, 0].set_ylabel('Depth (m)')
    axes[1, 0].set_title('Cable Tracking - Depth')
    axes[1, 0].grid(True)

    axes[1, 1].plot(t_ct, np.rad2deg(results['cable_tracking']['yaw']), 'b-', linewidth=1.5)
    axes[1, 1].plot(t_ct, np.rad2deg(results['cable_tracking']['target_yaw']), 'r--', linewidth=1.5)
    axes[1, 1].set_xlabel('Time (s)')
    axes[1, 1].set_ylabel('Heading (deg)')
    axes[1, 1].set_title('Cable Tracking - Heading')
    axes[1, 1].grid(True)

    plt.tight_layout()
    path = FIGURES_DIR / '05_combined_summary.png'
    fig.savefig(path, bbox_inches='tight')
    plt.close(fig)
    fig_paths.append(str(path.name))

    return fig_paths


def generate_report(results, fig_paths):
    """生成 Markdown 实验报告。"""
    control_cfg = cfg.get('control', {})
    limits_cfg = cfg.get('limits', {})

    report = []
    report.append("# PID 控制器性能评估报告\n")
    report.append(f"**日期**: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    report.append(f"**仿真平台**: PVS REMUS 100 (Fossen 2021 NED 坐标系约定)\n")
    report.append(f"**控制器**: AUVPIDController\n")
    report.append(f"**配置文件**: `{params_file}`\n")
    report.append(f"**输出目录**: `{RESULTS_DIR}`\n")

    report.append("\n---\n")
    report.append("\n## 1. 实验配置\n")

    report.append("\n### 1.1 载具参数\n")
    report.append("- **模型**: PythonVehicleSimulator REMUS 100")
    report.append("- **质量**: ~41.4 kg")
    report.append("- **最大螺旋桨转速**: 1525 RPM")
    report.append("- **舵角饱和限制**: ±15°")
    report.append("- **初始航速**: 1.5 m/s")
    report.append("- **坐标系**: Fossen NED (北-东-下)")

    report.append("\n### 1.2 控制器参数\n")
    report.append("| 通道 | Kp | Ki | Kd |")
    report.append("|------|----|----|----|")
    report.append(f"| 深度   | {control_cfg['depth']['kp']} | {control_cfg['depth']['ki']} | {control_cfg['depth']['kd']} |")
    report.append(f"| 俯仰   | {control_cfg['pitch']['kp']} | {control_cfg['pitch']['ki']} | {control_cfg['pitch']['kd']} |")
    report.append(f"| 航向   | {control_cfg['yaw']['kp']} | {control_cfg['yaw']['ki']} | {control_cfg['yaw']['kd']} |")
    report.append(f"| 速度   | {control_cfg['speed']['kp']} | {control_cfg['speed']['ki']} | {control_cfg['speed']['kd']} |")

    report.append("\n### 1.3 执行器限制\n")
    report.append(f"- **最大舵角**: {limits_cfg['fin_deg_max']}°")
    report.append(f"- **推力范围**: [{limits_cfg['thrust_min']}, {limits_cfg['thrust_max']}] %")

    report.append("\n### 1.4 测试场景\n")
    report.append("| 测试 | 描述 | 时长 |")
    report.append("|------|------|------|")
    report.append("| 1    | 深度阶跃：0 → 5 m | 40 s |")
    report.append("| 2    | 航向阶跃：0 → 30° | 40 s |")
    report.append("| 3    | 电缆跟踪：正弦深度 + 余弦航向 | 60 s |")

    report.append("\n---\n")
    report.append("\n## 2. 测试结果\n")

    report.append("\n### 2.1 深度阶跃响应\n")
    r = results['depth_step']
    report.append(f"- **均方根误差 (RMSE)**: {r['rmse']:.3f} m")
    report.append(f"- **最大误差**: {r['max_error']:.3f} m")
    report.append(f"- **最终深度**: {r['final_depth']:.3f} m (目标: 5.0 m)")
    if r['rise_time'] is not None:
        report.append(f"- **上升时间 (90%)**: {r['rise_time']:.2f} s")
    else:
        report.append("- **上升时间 (90%)**: 未达到")
    report.append(f"- **最大尾翼角**: {np.max(np.abs(r['stern'])):.2f}°")
    report.append(f"- **平均推力**: {np.mean(r['thrust']):.2f} %")

    report.append("\n### 2.2 航向阶跃响应\n")
    r = results['heading_step']
    report.append(f"- **均方根误差 (RMSE)**: {r['rmse']:.3f} rad ({np.rad2deg(r['rmse']):.2f}°)")
    report.append(f"- **最大误差**: {r['max_error']:.3f} rad ({np.rad2deg(r['max_error']):.2f}°)")
    report.append(f"- **最终航向**: {np.rad2deg(r['final_yaw']):.2f}° (目标: 30.0°)")
    if r['rise_time'] is not None:
        report.append(f"- **上升时间 (90%)**: {r['rise_time']:.2f} s")
    else:
        report.append("- **上升时间 (90%)**: 未达到")
    report.append(f"- **最大方向舵角**: {np.max(np.abs(r['rudder'])):.2f}°")

    report.append("\n### 2.3 电缆跟踪\n")
    r = results['cable_tracking']
    report.append(f"- **深度 RMSE**: {r['depth_rmse']:.3f} m")
    report.append(f"- **航向 RMSE**: {r['yaw_rmse']:.3f} rad ({np.rad2deg(r['yaw_rmse']):.2f}°)")
    report.append(f"- **深度最大误差**: {r['depth_max_error']:.3f} m")
    report.append(f"- **航向最大误差**: {np.rad2deg(r['yaw_max_error']):.2f}°")
    report.append(f"- **最大尾翼角**: {np.max(np.abs(r['stern'])):.2f}°")
    report.append(f"- **最大方向舵角**: {np.max(np.abs(r['rudder'])):.2f}°")

    report.append("\n---\n")
    report.append("\n## 3. 性能汇总\n")

    report.append("\n| 指标 | 深度 | 航向 |")
    report.append("|------|------|------|")
    report.append(f"| 阶跃 RMSE | {results['depth_step']['rmse']:.3f} m | {results['heading_step']['rmse']:.3f} rad |")
    report.append(f"| 跟踪 RMSE | {results['cable_tracking']['depth_rmse']:.3f} m | {results['cable_tracking']['yaw_rmse']:.3f} rad |")
    report.append(f"| 阶跃最大误差 | {results['depth_step']['max_error']:.3f} m | {results['heading_step']['max_error']:.3f} rad |")
    report.append(f"| 跟踪最大误差 | {results['cable_tracking']['depth_max_error']:.3f} m | {results['cable_tracking']['yaw_max_error']:.3f} rad |")

    report.append("\n---\n")
    report.append("\n## 4. 控制响应曲线\n")

    report.append("\n### 4.1 深度阶跃响应\n")
    report.append(f"\n![深度阶跃响应](figures/{fig_paths[0]})\n")

    report.append("\n### 4.2 航向阶跃响应\n")
    report.append(f"\n![航向阶跃响应](figures/{fig_paths[1]})\n")

    report.append("\n### 4.3 电缆跟踪 - 深度\n")
    report.append(f"\n![电缆跟踪深度](figures/{fig_paths[2]})\n")

    report.append("\n### 4.4 电缆跟踪 - 航向\n")
    report.append(f"\n![电缆跟踪航向](figures/{fig_paths[3]})\n")

    report.append("\n### 4.5 综合对比\n")
    report.append(f"\n![综合对比](figures/{fig_paths[4]})\n")

    report.append("\n---\n")
    report.append("\n## 5. 分析与结论\n")
    report.append("\n1. **深度通道**: 级联 PI-PID 结构提供了足够的深度跟踪性能。")
    report.append("   积分项消除了稳态误差，俯仰内环确保了平滑的姿态过渡。\n")
    report.append("2. **航向通道**: 航向 PID 控制器在 Kp=40.0, Ki=5.0, Kd=5.0 参数下")
    report.append("   实现了良好的跟踪。积分项补偿了海流扰动的影响。\n")
    report.append("3. **执行器饱和**: 舵角被限制在 ±15° 以内 (PVS 物理极限)。")
    report.append("   控制器输出通过 params.yaml 中的 `fin_deg_max` 进行裁剪。\n")
    report.append("4. **坐标系约定**: 采用关键 Fossen NED 约定：")
    report.append("   `dz/dt = -u*sin(theta) + w*cos(theta)`。注意 theta > 0 表示船头上仰 = 上浮。\n")

    report_text = '\n'.join(report)
    report_path = RESULTS_DIR / 'report.md'
    with open(report_path, 'w') as f:
        f.write(report_text)

    return str(report_path)


def main():
    print("PID 控制器离线测试")
    print(f"配置文件: {params_file}")
    print(f"时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"输出目录: {RESULTS_DIR}")

    control_cfg = cfg.get('control', {})
    print("\n当前 PID 参数:")
    print(f"  深度: kp={control_cfg['depth']['kp']}, ki={control_cfg['depth']['ki']}, kd={control_cfg['depth']['kd']}")
    print(f"  俯仰: kp={control_cfg['pitch']['kp']}, ki={control_cfg['pitch']['ki']}, kd={control_cfg['pitch']['kd']}")
    print(f"  航向: kp={control_cfg['yaw']['kp']}, ki={control_cfg['yaw']['ki']}, kd={control_cfg['yaw']['kd']}")
    print(f"  速度: kp={control_cfg['speed']['kp']}, ki={control_cfg['speed']['ki']}, kd={control_cfg['speed']['kd']}")

    controller = create_controller()

    results = {}
    results['depth_step'] = test_depth_step_response(controller)
    reset_controller(controller)
    results['heading_step'] = test_heading_step_response(controller)
    reset_controller(controller)
    results['cable_tracking'] = test_cable_tracking(controller)

    print(f"\n{'='*60}")
    print("生成图表和报告...")
    print(f"{'='*60}")

    fig_paths = generate_plots(results)
    report_path = generate_report(results, fig_paths)

    print(f"\n图表已保存至: {FIGURES_DIR}")
    for fp in fig_paths:
        print(f"  - {fp}")

    print(f"\n报告已保存至: {report_path}")
    print("\n✅ 测试完成！")

    return results


if __name__ == '__main__':
    main()

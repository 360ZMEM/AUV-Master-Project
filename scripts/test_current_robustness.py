#!/usr/bin/env python3
"""洋流鲁棒性测试脚本: 对比无洋流/有洋流两种场景下的控制性能。

用途:
  1. 验证洋流干扰模型是否正确注入到 PVS/HoloOcean 仿真器中
  2. 量化洋流对 PID/MPC 控制器的性能影响 (RMSE、横向误差、漂移距离)
  3. 观察欠驱动 AUV 在侧向洋流中的"蟹行 (Crabbing)" 姿态

输出指标:
  - RMSE: 均方根位置误差 (m)
  - Max Cross-track Error: 最大横向误差 (m)
  - Drift Distance: 沿洋流方向的累计漂移距离 (m)
  - Mean Crabbing Angle: 平均蟹行角 (°)，航向角与航迹角之差

用法:
  python scripts/test_current_robustness.py --config config/sim_params.yaml
"""

from __future__ import annotations

import argparse
import math
import sys
import time
from pathlib import Path

import numpy as np
import yaml

SIM_ROOT = Path(__file__).resolve().parents[1] / "sim_holoocean"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
for folder_path in [
    PROJECT_ROOT,
    PROJECT_ROOT / "common",
    PROJECT_ROOT / "algorithm",
    SIM_ROOT / "behavior",
    SIM_ROOT / "interfaces",
    SIM_ROOT / "apps",
    SIM_ROOT / "experiments",
]:
    folder_path = str(folder_path)
    if folder_path not in sys.path:
        sys.path.insert(0, folder_path)

from auv_pid_controller import AUVPIDController
from guidance import clamp_reference, compute_los_target, find_nearest_index
from metrics import compute_metrics
from safety_monitor import apply_safety
from sim_wrapper import (
    create_sim_wrapper,
    build_scenario,
    extract_body_velocity,
    extract_depth,
    extract_gyro,
    get_agent_state,
    rotation_matrix_to_euler,
)
from trajectory_generator import TrajectoryGenerator


def load_config(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def deep_merge(base: dict, override: dict) -> dict:
    """深度合并配置字典。"""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def run_single_scenario(
    cfg: dict,
    current_vector: list[float],
    label: str,
) -> dict:
    """
    运行单次仿真场景，返回历史数据和指标。

    参数:
        cfg: 基础配置
        current_vector: 洋流矢量 [北, 东, 地] (m/s)
        label: 场景标签

    返回:
        {"history": dict, "metrics": dict, "label": str}
    """
    # 修改洋流配置
    sim_cfg = cfg.copy()
    sim_cfg["environment"] = {
        "current": {
            "enabled": True,
            "type": "CONSTANT",
            "vector_ned": list(current_vector),
            "noise_std": 0.0,  # 测试时使用零噪声以便复现
            "max_t": 5.0,
        }
    }

    # 如果洋流为零，禁用洋流
    if np.allclose(current_vector, 0.0):
        sim_cfg["environment"]["current"]["enabled"] = False

    inner_cfg = cfg.copy()
    for k, v in sim_cfg.items():
        inner_cfg[k] = v

    sim_cfg_inner = inner_cfg["simulation"]
    ctrl_cfg = inner_cfg["control"]
    guide_cfg = inner_cfg["guidance"]
    lim_cfg = inner_cfg["limits"]
    eval_cfg = inner_cfg["evaluation"]

    dt = float(sim_cfg_inner["dt"])
    max_steps = int(sim_cfg_inner["max_steps"])
    agent_name = sim_cfg_inner["agent_name"]

    scenario = build_scenario(inner_cfg)
    controller = AUVPIDController(ctrl_cfg, lim_cfg)
    traj_gen = TrajectoryGenerator(inner_cfg["trajectory"])

    ref_bundle = traj_gen.generate()
    points = ref_bundle["points"]
    points_xy = points[:, :2]

    history = {
        "t": [],
        "pos": [],
        "ref": [],
        "cmd": [],
        "u": [],
        "target_u": [],
        "saturated_any": [],
        "safety_event_count": 0,
        "heading": [],
        "course": [],
        "crabbing_angle": [],
    }

    nearest_idx = 0

    wrapper = create_sim_wrapper(
        inner_cfg,
        scenario_cfg=scenario,
        agent_name=agent_name,
        show_viewport=False,
        verbose=False,
    ).open()
    state_raw = wrapper.reset_and_tick()

    for step in range(max_steps):
        t_sec = step * dt
        state = get_agent_state(state_raw, agent_name)

        pose = state["PoseSensor"]
        position = pose[:3, 3].astype(float)
        rpy = rotation_matrix_to_euler(pose[:3, :3])

        body_vel = extract_body_velocity(state.get("DVLSensor", np.zeros(3)))
        gyro = extract_gyro(state.get("IMUSensor", np.zeros(3)))
        depth_from_sensor = extract_depth(
            state.get("DepthSensor", np.array([-position[2]])), position[2]
        )

        nearest_idx = find_nearest_index(
            points_xy=points_xy,
            current_xy=position[:2],
            last_index=nearest_idx,
            search_window=int(guide_cfg["nearest_search_window"]),
        )
        los_point, los_idx = compute_los_target(
            points=points,
            nearest_index=nearest_idx,
            lookahead_distance=float(guide_cfg["lookahead_distance"]),
        )

        los_yaw = float(np.arctan2(los_point[1] - position[1], los_point[0] - position[0]))

        nearest_point = points[nearest_idx]
        nearest_ref = clamp_reference(nearest_point, lim_cfg)
        tangential = np.array([np.cos(los_yaw), np.sin(los_yaw)], dtype=float)
        normal_left = np.array([-tangential[1], tangential[0]], dtype=float)
        cross_track = float(np.dot(position[:2] - nearest_point[:2], normal_left))
        yaw_correction = -float(guide_cfg["cross_track_gain"]) * np.arctan2(
            cross_track, float(guide_cfg["lookahead_distance"])
        )
        target_yaw = los_yaw + yaw_correction

        target_ref = clamp_reference(los_point, lim_cfg)
        control_state = {
            "roll": rpy[0],
            "pitch": rpy[1],
            "yaw": rpy[2],
            "x": position[0],
            "y": position[1],
            "z": position[2],
            "depth": -position[2],
            "depth_sensor": depth_from_sensor,
            "u": body_vel[0],
            "v": body_vel[1],
            "w": body_vel[2],
            "p": gyro[0],
            "q": gyro[1],
            "r": gyro[2],
        }
        target = {
            "dt": dt,
            "target_depth": -target_ref[2],
            "target_yaw": target_yaw,
            "target_u": float(ctrl_cfg["target_u"]),
        }

        command, debug = controller.compute(control_state, target)
        command, safety_events = apply_safety(command, position, lim_cfg)
        state_raw = wrapper.step(command)

        if safety_events:
            history["safety_event_count"] += len(safety_events)

        # 计算航迹角 (course over ground)
        if len(history["pos"]) > 0:
            prev_pos = history["pos"][-1]
            course = float(np.arctan2(position[1] - prev_pos[1], position[0] - prev_pos[0]))
        else:
            course = rpy[2]

        # 蟹行角 = 航向角 - 航迹角
        crabbing = float(rpy[2] - course)
        # 归一化到 [-pi, pi]
        while crabbing > math.pi:
            crabbing -= 2 * math.pi
        while crabbing < -math.pi:
            crabbing += 2 * math.pi

        history["t"].append(t_sec)
        history["pos"].append(position.copy())
        history["ref"].append(nearest_ref.copy())
        history["cmd"].append(command.copy())
        history["u"].append(float(body_vel[0]))
        history["target_u"].append(float(ctrl_cfg["target_u"]))
        history["saturated_any"].append(
            bool(debug["pitch_saturated"] or debug["yaw_saturated"] or debug["thrust_saturated"])
        )
        history["heading"].append(float(rpy[2]))
        history["course"].append(course)
        history["crabbing_angle"].append(crabbing)

        if step % 15 == 0:
            pos_txt = f"pos=({position[0]:6.2f},{position[1]:6.2f},{position[2]:6.2f})"
            ref_txt = f"ref=({target_ref[0]:6.2f},{target_ref[1]:6.2f},{target_ref[2]:6.2f})"
            rpy_txt = f"rpy=({np.degrees(rpy[0]):6.1f},{np.degrees(rpy[1]):6.1f},{np.degrees(rpy[2]):6.1f})deg"
            crab_txt = f"crab={np.degrees(crabbing):6.1f}deg"
            print(f"  [{label}] step={step:04d} t={t_sec:6.2f}s {pos_txt} {ref_txt} {rpy_txt} {crab_txt}")

        if los_idx >= len(points) - 1:
            print(f"  [{label}] Reach end of reference path at step={step}, early stop.")
            break

    wrapper.close()

    eval_metrics = compute_metrics(history, eval_cfg)
    return {
        "history": history,
        "metrics": eval_metrics,
        "label": label,
    }


def compute_drift_metrics(history: dict, current_vector: list[float]) -> dict:
    """
    计算洋流鲁棒性指标。

    返回:
        dict: 包含 RMSE、Drift Distance、Cross-track Error、Crabbing Angle 等
    """
    positions = np.array(history["pos"])
    refs = np.array(history["ref"])
    crabbing_angles = np.array(history["crabbing_angle"])

    # 水平位置误差
    errors_xy = positions[:, :2] - refs[:, :2]
    rmse = float(np.sqrt(np.mean(np.sum(errors_xy ** 2, axis=1))))
    max_cross_track = float(np.max(np.abs(errors_xy[:, 1])))

    # 漂移距离: 沿洋流方向的累计偏移
    cv = np.asarray(current_vector, dtype=np.float64)
    cv_mag = np.linalg.norm(cv)
    if cv_mag > 1e-6:
        cv_unit = cv / cv_mag
        # 投影到洋流方向
        drift_along_current = np.dot(positions[:, :2] - refs[:, :2], cv_unit[:2])
        drift_distance = float(np.max(drift_along_current) - np.min(drift_along_current))
    else:
        drift_distance = 0.0

    mean_crabbing_deg = float(np.degrees(np.mean(crabbing_angles)))
    max_crabbing_deg = float(np.degrees(np.max(np.abs(crabbing_angles))))

    return {
        "rmse_m": rmse,
        "max_cross_track_m": max_cross_track,
        "drift_distance_m": drift_distance,
        "mean_crabbing_angle_deg": mean_crabbing_deg,
        "max_crabbing_angle_deg": max_crabbing_deg,
        "safety_event_count": history.get("safety_event_count", 0),
        "total_steps": len(history["t"]),
    }


def print_report(scenarios: list[dict], current_vectors: list[list[float]]) -> None:
    """打印洋流鲁棒性对比报告。"""
    print("\n" + "=" * 72)
    print("洋流鲁棒性测试报告")
    print("=" * 72)

    baseline_rmse = None
    baseline_ct = None

    for i, scenario in enumerate(scenarios):
        label = scenario["label"]
        cv = current_vectors[i]
        dm = compute_drift_metrics(scenario["history"], cv)

        print(f"\n场景 {i + 1}: {label} | 洋流 = {cv} m/s")
        print(f"  - RMSE:                  {dm['rmse_m']:.3f} m")
        print(f"  - Max Cross-track Error: {dm['max_cross_track_m']:.3f} m")
        print(f"  - Drift Distance:        {dm['drift_distance_m']:.3f} m")
        print(f"  - Mean Crabbing Angle:   {dm['mean_crabbing_angle_deg']:.1f}°")
        print(f"  - Max Crabbing Angle:    {dm['max_crabbing_angle_deg']:.1f}°")
        print(f"  - Total Steps:           {dm['total_steps']}")

        if baseline_rmse is None:
            baseline_rmse = dm["rmse_m"]
            baseline_ct = dm["max_cross_track_m"]
        else:
            if baseline_rmse > 1e-6:
                rmse_increase = ((dm["rmse_m"] - baseline_rmse) / baseline_rmse) * 100.0
                print(f"  - RMSE Increase:         {rmse_increase:+.0f}%")
            if baseline_ct > 1e-6:
                ct_increase = ((dm["max_cross_track_m"] - baseline_ct) / baseline_ct) * 100.0
                print(f"  - CT Error Increase:     {ct_increase:+.0f}%")

    print("\n" + "-" * 72)
    # 验收判断
    if baseline_rmse is not None and len(scenarios) > 1:
        last_dm = compute_drift_metrics(scenarios[-1]["history"], current_vectors[-1])
        if last_dm["rmse_m"] > 0.5:
            print("⚠ 洋流场景下 RMSE > 0.5m，建议: 启用 MPC/带前馈的 PID 实现侧滑补偿")
        else:
            print("✓ 洋流场景下 RMSE < 0.5m，控制器抗扰性能达标")
    print("=" * 72)


def main() -> None:
    parser = argparse.ArgumentParser(description="洋流鲁棒性测试: 对比无洋流/有洋流场景")
    parser.add_argument(
        "--config",
        type=str,
        default=str(PROJECT_ROOT / "config" / "sim_params.yaml"),
        help="Path to sim yaml config",
    )
    parser.add_argument(
        "--current-strong",
        type=float,
        nargs=3,
        default=[0.5, 0.5, 0.0],
        help="Strong current vector [north, east, down] in m/s",
    )
    parser.add_argument(
        "--current-weak",
        type=float,
        nargs=3,
        default=[0.3, 0.2, 0.0],
        help="Weak current vector [north, east, down] in m/s",
    )
    args = parser.parse_args()

    print(f"加载配置: {args.config}")
    cfg = load_config(args.config)

    # 使用 PVS 后端进行快速测试
    cfg["simulation"]["backend"] = "pvs"
    cfg["simulation"]["max_steps"] = min(int(cfg["simulation"]["max_steps"]), 3000)

    scenarios = []

    # 场景 1: 无洋流
    print("\n" + "=" * 72)
    print("场景 1: 无洋流 [0.0, 0.0, 0.0]")
    print("=" * 72)
    result = run_single_scenario(cfg, [0.0, 0.0, 0.0], "no_current")
    scenarios.append(result)

    # 场景 2: 弱洋流
    print("\n" + "=" * 72)
    print(f"场景 2: 弱洋流 {args.current_weak} m/s")
    print("=" * 72)
    result = run_single_scenario(cfg, list(args.current_weak), "weak_current")
    scenarios.append(result)

    # 场景 3: 强洋流
    print("\n" + "=" * 72)
    print(f"场景 3: 强洋流 {args.current_strong} m/s")
    print("=" * 72)
    result = run_single_scenario(cfg, list(args.current_strong), "strong_current")
    scenarios.append(result)

    current_vectors = [
        [0.0, 0.0, 0.0],
        list(args.current_weak),
        list(args.current_strong),
    ]

    print_report(scenarios, current_vectors)


if __name__ == "__main__":
    main()

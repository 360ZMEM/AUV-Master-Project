#!/usr/bin/env python3
"""WP-C 深度补偿离线 A/B 回查 - buoyancy_term / ki_z 的去留判定。

背景（P0-3）：v2 诊断怀疑 WP-C 的模型级浮力补偿（buoyancy_term=-0.5）与输出级
积分补偿（ki_z=0.1）可能是在"修一个 datum 度量 bug 制造的假漂移"。但真 bag 的
depth_m 是压力派生、与 datum bug 无关，已证明"上漂"是真实物理运动（baseline 的
缓慢收敛 + terrain 的跟随起伏），而非测量伪影。

本脚本做一个受控的离线闭环 A/B，把"是否存在真浮力"与"控制器是否补偿"解耦：
  - Plant（被控对象）：AUVKinematicsModel 前向积分，注入一个可配置的"真实浮力"
    B_true（NED z+下，负值=上推/正浮力）。
  - Controller A（现状 WP-C）：MPC buoyancy_term=-0.5 + ki_z=0.1。
  - Controller B（回退）：MPC buoyancy_term=0.0 + ki_z=0.0。
  对一个可达的恒定保深任务（start=target），测稳态深度误差。

判据：
  - 若 plant 有真浮力时 A 显著优于 B（稳态误差更小）→ WP-C 补偿真实物理，保留。
  - 若 plant 无浮力时 A 反而引入稳态偏置/超调 → WP-C 过补偿，建议回退或仅按真物理校核。

用法：
  python3 tools/wp_c_depth_ab.py
  python3 tools/wp_c_depth_ab.py --steps 240 --output-dir ./wpc_ab
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import sys
from pathlib import Path

import numpy as np
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(PROJECT_ROOT))
from common.env_utils import get_output_dir  # noqa: E402

DEFAULT_PARAMS = PROJECT_ROOT / "brain_linux" / "config" / "params.yaml"


def load_mpc_classes():
    module_path = PROJECT_ROOT / "algorithm" / "auv_mpc_controller.py"
    spec = importlib.util.spec_from_file_location("auv_algorithm_mpc_wpc", str(module_path))
    if spec is None or spec.loader is None:
        raise SystemExit(f"无法加载 MPC 模块: {module_path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.AUVMPCOptimizer, mod.AUVKinematicsModel


def load_params(params_path: Path) -> dict:
    with params_path.open("r", encoding="utf-8") as handle:
        cfg = yaml.safe_load(handle) or {}
    return cfg


def constant_reference(x0, heading, depth, speed, n, dt):
    ref = np.zeros((6, n + 1), dtype=np.float64)
    for k in range(n + 1):
        t_k = k * dt
        ref[0, k] = x0[0] + speed * np.cos(heading) * t_k
        ref[1, k] = x0[1] + speed * np.sin(heading) * t_k
        ref[2, k] = depth
        ref[3, k] = heading
        ref[4, k] = speed
        ref[5, k] = 0.0
    return ref


def simulate(
    *,
    AUVMPCOptimizer,
    AUVKinematicsModel,
    model_cfg: dict,
    weights_cfg: dict,
    constraints_cfg: dict,
    controller_buoyancy: float,
    ki_z: float,
    integral_clamp_m: float,
    plant_buoyancy: float,
    n: int,
    dt: float,
    steps: int,
    target_depth: float,
    target_speed: float,
    substeps: int = 5,
) -> dict:
    """单工况闭环仿真，返回深度时序与稳态误差统计。"""
    ctrl_model = dict(model_cfg)
    ctrl_model["buoyancy_term"] = controller_buoyancy
    kin_ctrl = AUVKinematicsModel(ctrl_model)
    optimizer = AUVMPCOptimizer(kin_ctrl, N=n, dt=dt, weights=weights_cfg, constraints=constraints_cfg)

    plant_model = dict(model_cfg)
    plant_model["buoyancy_term"] = plant_buoyancy
    plant = AUVKinematicsModel(plant_model)

    min_z = float(constraints_cfg.get("min_z_cmd_m", 0.0))
    max_z = float(constraints_cfg.get("max_z_cmd_m", 50.0))

    x = np.array([0.0, 0.0, target_depth, 0.0, target_speed, 0.0], dtype=np.float64)
    z_integral = 0.0
    prev_U = None
    depth_hist = []
    sub_dt = dt / substeps

    for _ in range(steps):
        ref = constant_reference(x, 0.0, target_depth, target_speed, n, dt)
        try:
            result = optimizer.solve(x, ref, 1.0, warm_start_U=prev_U)
            prev_U = result["U_opt"].copy()
            U0 = result["U_opt"][:, 0]
            psi_cmd, z_opt, T_cmd = float(U0[0]), float(U0[1]), float(U0[2])
        except RuntimeError:
            z_integral = 0.0
            prev_U = None
            psi_cmd, z_opt, T_cmd = 0.0, x[2], 15.0

        # WP-C C2: 输出级积分补偿（与 brain mpc_controller 一致）
        if ki_z != 0.0:
            z_integral += (target_depth - x[2]) * dt
            z_integral = float(np.clip(z_integral, -integral_clamp_m, integral_clamp_m))
            z_cmd = float(np.clip(z_opt + ki_z * z_integral, min_z, max_z))
        else:
            z_cmd = z_opt

        U = np.array([psi_cmd, z_cmd, T_cmd], dtype=np.float64)
        # 前向积分 plant（含真实浮力）
        xf = x.astype(np.float64)
        for _ in range(substeps):
            dX = np.array(plant.compute_dynamics(xf, U)).flatten()
            xf = xf + sub_dt * dX
        x = xf
        depth_hist.append(float(x[2]))

    depth_hist = np.asarray(depth_hist)
    tail = depth_hist[int(len(depth_hist) * 2 / 3):]
    err = tail - target_depth
    return {
        "depth_hist": depth_hist,
        "ss_depth_mean": float(tail.mean()),
        "ss_err_mean": float(err.mean()),
        "ss_err_mean_abs": float(np.abs(err).mean()),
        "ss_err_rmse": float(np.sqrt((err ** 2).mean())),
        "final_depth": float(depth_hist[-1]),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--params", type=Path, default=DEFAULT_PARAMS)
    parser.add_argument("--steps", type=int, default=240, help="Control steps per scenario.")
    parser.add_argument("--target-depth", type=float, default=5.0, help="Reachable constant hold depth (m).")
    parser.add_argument("--target-speed", type=float, default=1.0)
    parser.add_argument("--plant-buoyancy-true", type=float, default=-0.5, help="Plant true buoyancy term (NED, <0=upward push).")
    parser.add_argument("--output-dir", type=Path, default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    AUVMPCOptimizer, AUVKinematicsModel = load_mpc_classes()
    cfg = load_params(args.params)
    model_cfg = cfg.get("mpc_model", {})
    weights_cfg = cfg.get("mpc_weights", {})
    constraints_cfg = cfg.get("mpc_constraints", {})
    mpc_cfg = cfg.get("mpc", {})
    n = int(mpc_cfg.get("prediction_horizon", 20))
    dt = float(mpc_cfg.get("dt", 0.2))
    integral_clamp = float(mpc_cfg.get("z_integral_clamp_m", 2.0))

    # 2(controller) x 2(plant) 网格
    controllers = {
        "A_wpc_on": dict(buoyancy=-0.5, ki_z=0.1),
        "B_wpc_off": dict(buoyancy=0.0, ki_z=0.0),
    }
    plants = {
        "plant_buoyant": args.plant_buoyancy_true,  # 真实存在正浮力
        "plant_neutral": 0.0,                        # 中性，无浮力
    }

    rows = []
    print(f"[wp_c_ab] N={n} dt={dt} steps={args.steps} target_depth={args.target_depth}")
    for pname, pbuoy in plants.items():
        for cname, c in controllers.items():
            res = simulate(
                AUVMPCOptimizer=AUVMPCOptimizer,
                AUVKinematicsModel=AUVKinematicsModel,
                model_cfg=model_cfg,
                weights_cfg=weights_cfg,
                constraints_cfg=constraints_cfg,
                controller_buoyancy=c["buoyancy"],
                ki_z=c["ki_z"],
                integral_clamp_m=integral_clamp,
                plant_buoyancy=pbuoy,
                n=n,
                dt=dt,
                steps=args.steps,
                target_depth=args.target_depth,
                target_speed=args.target_speed,
            )
            row = {
                "plant": pname,
                "plant_buoyancy": pbuoy,
                "controller": cname,
                "buoyancy_term": c["buoyancy"],
                "ki_z": c["ki_z"],
                "ss_err_mean_m": round(res["ss_err_mean"], 4),
                "ss_err_mean_abs_m": round(res["ss_err_mean_abs"], 4),
                "ss_err_rmse_m": round(res["ss_err_rmse"], 4),
                "final_depth_m": round(res["final_depth"], 3),
            }
            rows.append(row)
            print(
                f"  {pname:>14} | {cname:>10}  ss_err_mean={row['ss_err_mean_m']:+.4f}m "
                f"abs={row['ss_err_mean_abs_m']:.4f}m rmse={row['ss_err_rmse_m']:.4f}m "
                f"final={row['final_depth_m']:.3f}m"
            )

    output_dir = args.output_dir
    if output_dir is None:
        output_dir = get_output_dir("results/wp_c_depth_ab")
    else:
        output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "wp_c_depth_ab.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "plant", "plant_buoyancy", "controller", "buoyancy_term", "ki_z",
                "ss_err_mean_m", "ss_err_mean_abs_m", "ss_err_rmse_m", "final_depth_m",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)
    print(f"[wp_c_ab] table -> {csv_path}")


if __name__ == "__main__":
    main()

import argparse
import math
import sys
import time
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import yaml

STACK_ROOT = Path(__file__).resolve().parents[1]
for folder in ["1_algos", "2_behavior", "3_interfaces", "5_experiment"]:
    p = str(STACK_ROOT / folder)
    if p not in sys.path:
        sys.path.insert(0, p)

from auv_pid_controller import AUVPIDController
from es_ekf import ES_EKF, quat_to_euler
from sim_wrapper import (
    HoloOceanSimWrapper,
    extract_body_velocity,
    extract_depth,
    get_agent_state,
)
from state_machine import WaypointStateMachine


def load_config(path):
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def read_imu(sensor):
    imu = np.asarray(sensor)
    if imu.ndim == 1 and imu.size >= 6:
        return imu[:3].astype(float), imu[3:6].astype(float)
    if imu.ndim >= 2 and imu.shape[0] >= 2 and imu.shape[1] >= 3:
        return np.asarray(imu[0]).reshape(-1)[:3].astype(float), np.asarray(imu[1]).reshape(-1)[:3].astype(float)
    flat = imu.reshape(-1)
    if flat.size >= 6:
        return flat[:3].astype(float), flat[3:6].astype(float)
    return np.zeros(3, dtype=float), np.zeros(3, dtype=float)


def read_gps_xy(sensor):
    gps = np.asarray(sensor).reshape(-1)
    if gps.size < 2:
        return None
    if not np.isfinite(gps[0]) or not np.isfinite(gps[1]):
        return None
    return gps[:2].astype(float)


def compute_error_metrics(gt_xyz, ekf_xyz, gps_on_flags):
    gt = np.asarray(gt_xyz, dtype=float)
    est = np.asarray(ekf_xyz, dtype=float)
    flags = np.asarray(gps_on_flags, dtype=bool)
    if gt.size == 0:
        return {"rmse_all": np.nan, "rmse_gps_on": np.nan, "rmse_gps_off": np.nan, "final_error": np.nan}
    err = np.linalg.norm(gt - est, axis=1)
    return {
        "rmse_all": float(np.sqrt(np.mean(err * err))),
        "rmse_gps_on": float(np.sqrt(np.mean(err[flags] * err[flags]))) if np.any(flags) else float("nan"),
        "rmse_gps_off": float(np.sqrt(np.mean(err[~flags] * err[~flags]))) if np.any(~flags) else float("nan"),
        "final_error": float(err[-1]),
    }


def build_es_ekf_scenario(cfg):
    sim = cfg["simulation"]
    exp = cfg.get("es_ekf_experiment", {})
    world = exp.get("world", "OpenWater")
    gps_depth_gate = float(exp.get("gps_depth_gate", 1.0))
    imu_sigma = exp.get("imu_sigma", {})
    dvl_sigma = exp.get("dvl_sigma", {})
    depth_sigma = exp.get("depth_sigma", {})
    gps_sigma = exp.get("gps_sigma", {})

    return {
        "name": "auv_es_ekf_experiment",
        "world": world,
        "package_name": sim["package_name"],
        "main_agent": sim["agent_name"],
        "ticks_per_sec": sim["ticks_per_sec"],
        "frames_per_sec": sim["frames_per_sec"],
        "agents": [
            {
                "agent_name": sim["agent_name"],
                "agent_type": "TorpedoAUV",
                "control_scheme": 0,
                "location": exp.get("initial_location", [0.0, 0.0, -0.2]),
                "rotation": exp.get("initial_rotation", [0.0, 0.0, 0.0]),
                "sensors": [
                    {"sensor_type": "PoseSensor", "socket": "COM"},
                    {
                        "sensor_type": "IMUSensor",
                        "socket": "IMUSocket",
                        "configuration": {
                            "AccelSigma": float(imu_sigma.get("accel", 0.01)),
                            "AngVelSigma": float(imu_sigma.get("gyro", 0.001)),
                            "AccelBiasSigma": float(imu_sigma.get("accel_bias", 0.0001)),
                            "AngVelBiasSigma": float(imu_sigma.get("gyro_bias", 0.00005)),
                        },
                    },
                    {
                        "sensor_type": "DVLSensor",
                        "socket": "COM",
                        "configuration": {
                            "VelSigma": float(dvl_sigma.get("vel", 0.02)),
                            "RangeSigma": float(dvl_sigma.get("range", 0.02)),
                        },
                    },
                    {
                        "sensor_type": "DepthSensor",
                        "socket": "COM",
                        "configuration": {"Sigma": float(depth_sigma.get("sigma", 0.03))},
                    },
                    {
                        "sensor_type": "GPSSensor",
                        "socket": "GPS",
                        "configuration": {
                            "Sigma": float(gps_sigma.get("sigma", 0.5)),
                            "Depth": gps_depth_gate,
                            "DepthSigma": float(gps_sigma.get("depth_sigma", 0.02)),
                        },
                    },
                ],
            }
        ],
    }


def run_experiment(cfg, enable_plot=True, max_steps_override=None):
    sim_cfg = cfg["simulation"]
    ctrl_cfg = cfg["control"]
    exp_cfg = cfg.get("es_ekf_experiment", {})

    scenario = build_es_ekf_scenario(cfg)
    agent_name = sim_cfg["agent_name"]
    dt = float(sim_cfg["dt"])
    max_steps = int(max_steps_override if max_steps_override is not None else exp_cfg.get("max_steps", 900))
    print_every = int(exp_cfg.get("print_every_n_steps", 20))

    controller = AUVPIDController(ctrl_cfg, cfg["limits"])
    sm = WaypointStateMachine(exp_cfg)

    p0 = np.array(exp_cfg.get("initial_location", [0.0, 0.0, -0.2]), dtype=float)
    ekf = ES_EKF(
        {
            "gravity": exp_cfg.get("gravity", 9.81),
            "sigma_acc": exp_cfg.get("sigma_acc", 0.08),
            "sigma_gyro": exp_cfg.get("sigma_gyro", 0.01),
            "sigma_ba": exp_cfg.get("sigma_ba", 0.001),
            "sigma_bg": exp_cfg.get("sigma_bg", 0.0005),
            "sigma_dvl": exp_cfg.get("sigma_dvl", 0.03),
            "sigma_depth": exp_cfg.get("sigma_depth", 0.05),
            "sigma_gps_xy": exp_cfg.get("sigma_gps_xy", 0.5),
            "imu_acc_is_linear": exp_cfg.get("imu_acc_is_linear", True),
            "init_pos": p0.tolist(),
            "init_vel": [0.0, 0.0, 0.0],
            "init_quat_wxyz": [1.0, 0.0, 0.0, 0.0],
            "init_P_diag": exp_cfg.get("init_P_diag", [0.5] * 15),
        }
    )
    dvl_frame = str(exp_cfg.get("dvl_frame", "world")).lower()

    t_hist, gt_xyz, ekf_xyz, gps_on = [], [], [], []

    fig = None
    if enable_plot:
        plt.ion()
        fig, ax = plt.subplots(figsize=(7, 6), dpi=100)
        gt_line, = ax.plot([], [], "k-", lw=1.4, label="Ground Truth")
        ekf_line, = ax.plot([], [], "tab:blue", lw=1.2, label="ES-EKF")
        loss_marker = ax.scatter([], [], c="red", s=40, marker="x", label="GPS Loss")
        ax.set_title("Realtime XY Map (GT vs ES-EKF)")
        ax.set_xlabel("X (m)")
        ax.set_ylabel("Y (m)")
        ax.grid(True, alpha=0.3)
        ax.legend()
        plt.show()
    gps_loss_mark = None

    wrapper = HoloOceanSimWrapper(scenario, agent_name, show_viewport=False, verbose=bool(sim_cfg.get("verbose", False))).open()
    state_raw = wrapper.reset_and_tick()
    wall_start = time.time()

    for step in range(max_steps):
        t_sec = step * dt
        state = get_agent_state(state_raw, agent_name)
        pose = state["PoseSensor"]
        gt_pos = pose[:3, 3].astype(float)

        imu_acc, imu_gyro = read_imu(state.get("IMUSensor", np.zeros(6)))
        dvl_vel = extract_body_velocity(state.get("DVLSensor", np.zeros(3)))
        depth_raw = extract_depth(state.get("DepthSensor", np.array([-gt_pos[2]])), gt_pos[2])
        depth = -depth_raw if depth_raw < 0.0 else depth_raw
        gps_xy = read_gps_xy(state.get("GPSSensor", np.array([np.nan, np.nan, np.nan])))

        ekf.predict(imu_acc, imu_gyro, dt)
        if dvl_frame == "world":
            ekf.correct_dvl_world(dvl_vel)
        else:
            ekf.correct_dvl(dvl_vel)
        ekf.correct_depth(depth)
        if gps_xy is not None:
            ekf.correct_gps(gps_xy)
        elif gps_loss_mark is None:
            gps_loss_mark = gt_pos[:2].copy()

        est = ekf.get_state()
        est_rpy = quat_to_euler(est["q"])

        bt = sm.tick({"t": t_sec, "p_est": est["p"], "q_est": est["q"]})
        target_xyz = np.asarray(bt["target_xyz"], dtype=float)
        target_yaw = math.atan2(target_xyz[1] - est["p"][1], target_xyz[0] - est["p"][0])

        control_state = {
            "roll": est_rpy[0], "pitch": est_rpy[1], "yaw": est_rpy[2],
            "x": est["p"][0], "y": est["p"][1], "z": est["p"][2],
            "depth": -est["p"][2], "depth_sensor": depth,
            "u": dvl_vel[0], "v": dvl_vel[1], "w": dvl_vel[2],
            "p": imu_gyro[0], "q": imu_gyro[1], "r": imu_gyro[2],
        }
        target = {"dt": dt, "target_depth": -target_xyz[2], "target_yaw": target_yaw, "target_u": float(bt["target_u"]) }
        command, _ = controller.compute(control_state, target)

        state_raw = wrapper.step(command)

        t_hist.append(t_sec)
        gt_xyz.append(gt_pos.copy())
        ekf_xyz.append(est["p"].copy())
        gps_on.append(gps_xy is not None)

        if enable_plot and step % int(exp_cfg.get("plot_every_n_steps", 3)) == 0:
            gt_arr = np.asarray(gt_xyz)
            ekf_arr = np.asarray(ekf_xyz)
            gt_line.set_data(gt_arr[:, 0], gt_arr[:, 1])
            ekf_line.set_data(ekf_arr[:, 0], ekf_arr[:, 1])
            if gps_loss_mark is not None:
                loss_marker.set_offsets(gps_loss_mark.reshape(1, 2))
            ax = fig.axes[0]
            ax.relim(); ax.autoscale_view()
            fig.canvas.draw(); fig.canvas.flush_events(); plt.pause(0.001)

        if step % print_every == 0:
            print(f"step={step:04d} t={t_sec:6.2f}s gt=({gt_pos[0]:6.2f},{gt_pos[1]:6.2f},{gt_pos[2]:6.2f}) ekf=({est['p'][0]:6.2f},{est['p'][1]:6.2f},{est['p'][2]:6.2f}) depth={depth:5.2f} gps_on={gps_xy is not None}")

    wrapper.close()

    if enable_plot:
        save_path = exp_cfg.get("save_plot", "es_ekf_xy_map.png")
        fig.savefig(save_path)
        print(f"ES-EKF plot saved: {save_path}")
        plt.ioff()

    metrics = compute_error_metrics(gt_xyz, ekf_xyz, gps_on)
    print(
        "ES-EKF metrics: "
        f"rmse_all={metrics['rmse_all']:.3f}m "
        f"rmse_gps_on={metrics['rmse_gps_on']:.3f}m "
        f"rmse_gps_off={metrics['rmse_gps_off']:.3f}m "
        f"final_error={metrics['final_error']:.3f}m"
    )

    np.savez(exp_cfg.get("save_results", "es_ekf_results.npz"), t=np.asarray(t_hist), gt_xyz=np.asarray(gt_xyz), ekf_xyz=np.asarray(ekf_xyz), gps_on=np.asarray(gps_on))
    print(f"ES-EKF experiment done, wall_time={time.time() - wall_start:.2f}s")


def parse_args():
    parser = argparse.ArgumentParser(description="Run standalone ES-EKF experiment")
    parser.add_argument("--config", type=str, default=str(STACK_ROOT / "config" / "sim_params.yaml"))
    parser.add_argument("--no-plot", action="store_true")
    parser.add_argument("--max-steps", type=int, default=None)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    cfg = load_config(args.config)
    run_experiment(cfg, enable_plot=not args.no_plot, max_steps_override=args.max_steps)

import threading
import time
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

SIM_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = Path(__file__).resolve().parents[2]
for folder_path in [
    PROJECT_ROOT,
    PROJECT_ROOT / "common",
    PROJECT_ROOT / "algorithm",
    SIM_ROOT / "behavior",
    SIM_ROOT / "interfaces",
    SIM_ROOT / "experiments",
]:
    folder_path = str(folder_path)
    if folder_path not in sys.path:
        sys.path.insert(0, folder_path)

from auv_pid_controller import AUVPIDController
from guidance import clamp_reference, compute_los_target, find_nearest_index
from metrics import compute_metrics
from plot_runtime import initialize_plot, render_plot, update_live_plot
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


def run_main(cfg, config_path, enable_plot, enable_interactive=False):
    sim_cfg = cfg["simulation"]
    ctrl_cfg = cfg["control"]
    guide_cfg = cfg["guidance"]
    lim_cfg = cfg["limits"]
    eval_cfg = cfg["evaluation"]

    dt = float(sim_cfg["dt"])
    max_steps = int(sim_cfg["max_steps"])
    agent_name = sim_cfg["agent_name"]
    print_every = int(cfg["debug"]["print_every_n_steps"])

    scenario = build_scenario(cfg)
    controller = AUVPIDController(ctrl_cfg, lim_cfg)
    traj_gen = TrajectoryGenerator(cfg["trajectory"])

    ref_bundle = traj_gen.generate()
    radius_check = traj_gen.validate_turn_radius(ref_bundle["turn_radius"])

    interactive_mode = bool(cfg.get("plot", {}).get("interactive", False)) or (enable_plot and enable_interactive)
    live_storage = None
    live_lines = None
    fig_live = None
    ref_points = None
    if interactive_mode:
        plt.ion()
        dpi_int = int(cfg.get("plot", {}).get("interactive_dpi", cfg.get("plot", {}).get("dpi", 140)))
        fig_live, live_lines, live_storage = initialize_plot(ref_bundle, dpi_int)
        live_storage["ref_z"] = []
        ref_points = ref_bundle["points"]
        plt.show()

    print("=" * 72)
    print("Phase 4: Main Simulation Loop (LOS + Cascaded PID)")
    print(f"config={config_path}")
    print(f"simulation_backend={sim_cfg.get('backend', 'holoocean')}")
    print(f"control_scheme={cfg['agent']['control_scheme']} command=[right,top,left,bottom,thrust]")
    print(
        f"turn_radius_check: min_actual={radius_check['min_radius_actual']:.3f}, "
        f"required={radius_check['min_radius_required']:.3f}, pass={radius_check['passed']}"
    )
    print("=" * 72)

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
    }

    nearest_idx = 0
    sim_done = threading.Event()
    sim_exception = [None]
    wall_start = time.time()
    pvs_reference_mode = str(cfg.get("pvs", {}).get("control_mode", "stepInput")).strip().lower()
    use_pvs_reference = str(sim_cfg.get("backend", "holoocean")).strip().lower() == "pvs" and pvs_reference_mode in {
        "depthheadingautopilot",
        "depth_heading_autopilot",
        "autopilot",
        "reference",
    }

    def sim_loop():
        nonlocal history, nearest_idx
        try:
            wrapper = create_sim_wrapper(
                cfg,
                scenario_cfg=scenario,
                agent_name=agent_name,
                show_viewport=bool(sim_cfg["show_viewport"]),
                verbose=bool(sim_cfg.get("verbose", False)),
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
                depth_from_sensor = extract_depth(state.get("DepthSensor", np.array([-position[2]])), position[2])

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
                yaw_correction = -float(guide_cfg["cross_track_gain"]) * np.arctan2(cross_track, float(guide_cfg["lookahead_distance"]))
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

                if use_pvs_reference and hasattr(wrapper, "set_reference"):
                    wrapper.set_reference(
                        depth_m=float(target["target_depth"]),
                        heading_rad=float(target["target_yaw"]),
                        speed_mps=float(target["target_u"]),
                    )
                    command = np.zeros(5, dtype=float)
                    debug = {
                        "gain_scale": 1.0,
                        "yaw_error": 0.0,
                        "pitch_saturated": False,
                        "yaw_saturated": False,
                        "thrust_saturated": False,
                    }
                    safety_events = []
                    state_raw = wrapper.step(command)
                else:
                    command, debug = controller.compute(control_state, target)
                    command, safety_events = apply_safety(command, position, lim_cfg)
                    state_raw = wrapper.step(command)

                if safety_events:
                    history["safety_event_count"] += len(safety_events)

                history["t"].append(t_sec)
                history["pos"].append(position.copy())
                history["ref"].append(nearest_ref.copy())
                history["cmd"].append(command.copy())
                history["u"].append(float(body_vel[0]))
                history["target_u"].append(float(ctrl_cfg["target_u"]))
                history["saturated_any"].append(bool(debug["pitch_saturated"] or debug["yaw_saturated"] or debug["thrust_saturated"]))

                if interactive_mode:
                    live_storage["t"].append(t_sec)
                    live_storage["x"].append(position[0])
                    live_storage["y"].append(position[1])
                    live_storage["z"].append(position[2])
                    live_storage["u"].append(body_vel[0])
                    live_storage["target_u"].append(float(ctrl_cfg["target_u"]))
                    live_storage["ref_z"].append(nearest_ref[2])
                    live_storage.setdefault("cmd_history", []).append(command.copy())

                if step % print_every == 0:
                    pos_txt = f"pos=({position[0]:6.2f},{position[1]:6.2f},{position[2]:6.2f})"
                    ref_txt = f"ref=({target_ref[0]:6.2f},{target_ref[1]:6.2f},{target_ref[2]:6.2f})"
                    rpy_txt = f"rpy=({np.degrees(rpy[0]):6.1f},{np.degrees(rpy[1]):6.1f},{np.degrees(rpy[2]):6.1f})deg"
                    cmd_txt = f"cmd=[{command[0]:6.2f},{command[1]:6.2f},{command[2]:6.2f},{command[3]:6.2f},{command[4]:6.2f}]"
                    aux_txt = f"u={body_vel[0]:5.2f} gain_scale={debug['gain_scale']:5.2f} yaw_err={np.degrees(debug['yaw_error']):6.2f}deg"
                    evt_txt = (" | events=" + ",".join(safety_events)) if safety_events else ""
                    print(f"step={step:04d} t={t_sec:6.2f}s {pos_txt} {ref_txt} {rpy_txt} {aux_txt} {cmd_txt}{evt_txt}")

                if los_idx >= len(points) - 1:
                    print(f"Reach end of reference path at step={step}, early stop.")
                    break

            wrapper.close()
        except Exception as e:
            sim_exception[0] = e
        finally:
            sim_done.set()

    sim_thread = threading.Thread(target=sim_loop, daemon=True)
    sim_thread.start()

    gui_timer = None
    if interactive_mode and fig_live is not None:
        def gui_update():
            try:
                update_live_plot(fig_live, live_lines, live_storage, ref_points)
            except Exception:
                pass

        gui_timer = fig_live.canvas.new_timer(interval=50)
        gui_timer.add_callback(gui_update)
        gui_timer.start()

    try:
        while not sim_done.is_set():
            plt.pause(0.05)
    except KeyboardInterrupt:
        sim_done.set()

    if gui_timer is not None:
        try:
            gui_timer.stop()
        except Exception:
            pass
    sim_thread.join(timeout=1.0)

    if sim_exception[0] is not None:
        raise sim_exception[0]

    elapsed = time.time() - wall_start
    metrics = compute_metrics(history, eval_cfg)

    print("=" * 72)
    print(f"仿真完成: wall_time={elapsed:.2f}s")
    print(f"rms={metrics['rms']:.4f}m mean_error={metrics['mean_error']:.4f}m axis_ratio={metrics['axis_ratio']:.4%} sat_ratio={metrics['sat_ratio']:.2%}")
    print(f"safety_event_count={metrics['safety_event_count']} pass_rms={metrics['pass_rms']} pass_axis_ratio={metrics['pass_axis_ratio']}")
    print("=" * 72)

    if enable_plot:
        save_path = cfg.get("plot", {}).get("save_main_plot", "stage2_main_plot.png")
        if interactive_mode and fig_live is not None:
            try:
                update_live_plot(fig_live, live_lines, live_storage, ref_points)
            except Exception:
                pass
            fig_live.savefig(save_path)
            print(f"Plot saved: {save_path}")
        else:
            render_plot(history=history, ref_bundle=ref_bundle, save_path=save_path, dpi=int(cfg.get("plot", {}).get("dpi", 140)))
            print(f"Plot saved: {save_path}")

    if interactive_mode and fig_live is not None:
        plt.ioff()
    return metrics

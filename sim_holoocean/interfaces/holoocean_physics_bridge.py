import time
import numpy as np
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
for folder in [PROJECT_ROOT, PROJECT_ROOT / "common"]:
    folder = str(folder)
    if folder not in sys.path:
        sys.path.insert(0, folder)

from common.protocol import (
    KEY_ACCEL_NED,
    KEY_B_NED,
    KEY_B_NORM,
    KEY_CABLE_CLOSEST_NED,
    KEY_CABLE_DISTANCE_M,
    KEY_DEPTH_M,
    KEY_GYRO_NED,
    KEY_POSITION_NED,
    KEY_RPY_NED,
    KEY_SONAR_BINS,
    KEY_VEL_NED,
    enrich_meta,
    validate_sensor_payload,
)

from frame_transform import body_vector_ue_to_ned, pose_matrix_ue_to_ned
from perception_engine import (
    CablePath,
    compute_biot_savart_hvdc,
    inject_gaussian_noise,
    inject_sonar_cable_peak,
)
from sim_wrapper import (
    HoloOceanSimWrapper,
    build_scenario,
    extract_body_velocity,
    extract_depth,
    extract_gyro,
    get_agent_state,
)
from zenoh_bridge import ZenohBridge


class HoloOceanPhysicsZenohBridge:
    def __init__(self, config, command_guard):
        self.config = config
        self.command_guard = command_guard
        self.agent_name = config["simulation"]["agent_name"]
        self.rate_hz = float(config["bridge"]["rate_hz"])
        self.dt = 1.0 / max(1e-6, self.rate_hz)

        cable_points = config["cable_path"]["points_ned"]
        self.cable = CablePath(cable_points)

        self.wrapper = None
        self.zbridge = None
        self.last_cmd = np.array(config["bridge"].get("default_command", [0, 0, 0, 0, 0]), dtype=float)

    def open(self):
        scenario = build_scenario(self.config)
        sim_cfg = self.config["simulation"]
        self.wrapper = HoloOceanSimWrapper(
            scenario_cfg=scenario,
            agent_name=self.agent_name,
            show_viewport=bool(sim_cfg.get("show_viewport", False)),
            verbose=bool(sim_cfg.get("verbose", False)),
        ).open()
        self.zbridge = ZenohBridge(self.config["zenoh"]).open()
        return self

    def close(self):
        if self.zbridge is not None:
            self.zbridge.close()
            self.zbridge = None
        if self.wrapper is not None:
            self.wrapper.close()
            self.wrapper = None

    def _build_sensor_packet(self, raw_state, step, sim_time):
        state = get_agent_state(raw_state, self.agent_name)
        pose = state["PoseSensor"]
        tf = pose_matrix_ue_to_ned(pose)

        imu_sensor = np.asarray(state.get("IMUSensor", np.zeros(6)), dtype=float).reshape(-1)
        gyro_ue = extract_gyro(state.get("IMUSensor", np.zeros(3)))
        dvl_ue = extract_body_velocity(state.get("DVLSensor", np.zeros(3)))
        depth_raw = extract_depth(state.get("DepthSensor", np.array([-pose[2, 3]])), pose[2, 3])

        gyro_ned = body_vector_ue_to_ned(gyro_ue)
        dvl_ned = body_vector_ue_to_ned(dvl_ue)

        accel_ue = imu_sensor[:3] if imu_sensor.size >= 3 else np.zeros(3, dtype=float)
        accel_ned = body_vector_ue_to_ned(accel_ue)

        pos_ned = tf["position_ned"]
        cable_p, cable_dist = self.cable.closest_point_and_distance(pos_ned)

        p_cfg = self.config["perception"]
        b_vec = compute_biot_savart_hvdc(
            auv_pos_ned=pos_ned,
            cable=self.cable,
            current_amp=float(p_cfg["hvdc_current_amp"]),
        )
        b_noisy = inject_gaussian_noise(b_vec, p_cfg["noise"]["magnetic_sigma"]) 
        dvl_noisy = inject_gaussian_noise(dvl_ned, p_cfg["noise"]["dvl_sigma"]) 

        depth_ned = float(-depth_raw if depth_raw < 0.0 else depth_raw)
        depth_noisy = float(inject_gaussian_noise(np.array([depth_ned]), p_cfg["noise"]["depth_sigma"])[0])

        sonar_cfg = p_cfg["sonar"]
        sonar = inject_sonar_cable_peak(
            n_bins=int(sonar_cfg["n_bins"]),
            max_range_m=float(sonar_cfg["max_range_m"]),
            cable_distance_m=float(cable_dist),
            base_noise_sigma=float(sonar_cfg["base_noise_sigma"]),
            peak_gain=float(sonar_cfg["peak_gain"]),
            peak_width_bins=float(sonar_cfg["peak_width_bins"]),
        )

        base = enrich_meta({}, step=int(step), sim_time=float(sim_time), ts=time.time())
        packets = {
            "ground_truth": {
                **base,
                KEY_POSITION_NED: pos_ned.tolist(),
                KEY_RPY_NED: tf["rpy_ned"].tolist(),
                KEY_CABLE_CLOSEST_NED: cable_p.tolist(),
                KEY_CABLE_DISTANCE_M: float(cable_dist),
            },
            "imu": {
                **base,
                KEY_ACCEL_NED: accel_ned.tolist(),
                KEY_GYRO_NED: gyro_ned.tolist(),
            },
            "dvl": {
                **base,
                KEY_VEL_NED: dvl_noisy.tolist(),
            },
            "depth": {
                **base,
                KEY_DEPTH_M: depth_noisy,
            },
            "magnetic": {
                **base,
                KEY_B_NED: b_noisy.tolist(),
                KEY_B_NORM: float(np.linalg.norm(b_noisy)),
            },
            "sonar": {
                **base,
                KEY_SONAR_BINS: sonar.tolist(),
            },
        }
        return packets

    def run_forever(self):
        state = self.wrapper.reset_and_tick()
        step = 0
        start_wall = time.time()

        while True:
            loop_start = time.time()
            sim_time = step * self.dt

            cmd_msg, cmd_ts = self.zbridge.get_latest_cmd()
            cmd = self.command_guard.sanitize(cmd_msg, self.last_cmd, cmd_ts)
            self.last_cmd = cmd

            state = self.wrapper.step(cmd)
            packets = self._build_sensor_packet(state, step, sim_time)

            for ch_name, payload in packets.items():
                topic = self.zbridge.get_uplink_topic(ch_name)
                ok, errors = validate_sensor_payload(topic, payload)
                if not ok:
                    print(f"[bridge][warn] invalid payload for {ch_name} ({topic}): {errors}")
                    continue
                self.zbridge.publish(ch_name, payload)

            print(
                f"step={step:06d} depth={packets['depth'][KEY_DEPTH_M]:.3f}m "
                f"|B|={packets['magnetic'][KEY_B_NORM]:.6e}T"
            )

            step += 1
            elapsed = time.time() - loop_start
            sleep_t = self.dt - elapsed
            if sleep_t > 0:
                time.sleep(sleep_t)

            if self.config["bridge"].get("max_steps", 0) > 0 and step >= int(self.config["bridge"]["max_steps"]):
                break

        print(f"bridge done, wall_time={time.time() - start_wall:.2f}s")

import holoocean
import numpy as np


class HoloOceanSimWrapper:
    """Simulation data adapter for HoloOcean.

    API:
    - open()
    - reset_and_tick()
    - step(command5)
    - close()
    - parse_state(raw_state)
    """

    def __init__(self, scenario_cfg, agent_name, show_viewport=False, verbose=False):
        self.scenario_cfg = scenario_cfg
        self.agent_name = agent_name
        self.show_viewport = bool(show_viewport)
        self.verbose = bool(verbose)
        self.env = None

    def open(self):
        self.env = holoocean.make(
            scenario_cfg=self.scenario_cfg,
            show_viewport=self.show_viewport,
            verbose=self.verbose,
        )
        return self

    def __enter__(self):
        return self.open()

    def __exit__(self, exc_type, exc, tb):
        self.close()
        return False

    def reset_and_tick(self):
        self.env.reset()
        return self.env.tick()

    def step(self, command5):
        cmd = np.asarray(command5, dtype=float).reshape(-1)
        if cmd.size != 5:
            raise ValueError("command must be length 5: [right,top,left,bottom,thrust]")
        self.env.act(self.agent_name, cmd)
        return self.env.tick()

    def close(self):
        if self.env is not None:
            if hasattr(self.env, "close"):
                try:
                    self.env.close()
                except Exception:
                    pass
            elif hasattr(self.env, "__exit__"):
                self.env.__exit__(None, None, None)
            self.env = None


def build_scenario(cfg):
    sim = cfg["simulation"]
    agent_cfg = cfg["agent"]
    limits = cfg["limits"]
    return {
        "name": cfg["stage"]["name"],
        "world": sim["world"],
        "package_name": sim["package_name"],
        "main_agent": sim["agent_name"],
        "ticks_per_sec": sim["ticks_per_sec"],
        "frames_per_sec": sim["frames_per_sec"],
        "env_min": limits["env_min"],
        "env_max": limits["env_max"],
        "agents": [
            {
                "agent_name": sim["agent_name"],
                "agent_type": agent_cfg["type"],
                "control_scheme": agent_cfg["control_scheme"],
                "sensors": agent_cfg["sensors"],
                "location": agent_cfg["location"],
                "rotation": agent_cfg["rotation"],
            }
        ],
    }


def get_agent_state(state, agent_name):
    if agent_name in state and isinstance(state[agent_name], dict):
        return state[agent_name]
    return state


def rotation_matrix_to_euler(matrix):
    sy = np.sqrt(matrix[0, 0] ** 2 + matrix[1, 0] ** 2)
    singular = sy < 1e-6
    if not singular:
        roll = np.arctan2(matrix[2, 1], matrix[2, 2])
        pitch = np.arctan2(-matrix[2, 0], sy)
        yaw = np.arctan2(matrix[1, 0], matrix[0, 0])
    else:
        roll = np.arctan2(-matrix[1, 2], matrix[1, 1])
        pitch = np.arctan2(-matrix[2, 0], sy)
        yaw = 0.0
    return np.array([roll, pitch, yaw], dtype=float)


def extract_body_velocity(dvl_sensor):
    dvl = np.asarray(dvl_sensor)
    if dvl.ndim == 1 and dvl.size >= 3:
        return dvl[:3].astype(float)
    if dvl.ndim >= 2 and dvl.shape[-1] >= 3:
        return np.asarray(dvl[0]).reshape(-1)[:3].astype(float)
    return np.zeros(3, dtype=float)


def extract_gyro(imu_sensor):
    imu = np.asarray(imu_sensor)
    if imu.ndim == 1:
        if imu.size >= 6:
            return imu[3:6].astype(float)
        if imu.size >= 3:
            return imu[:3].astype(float)
    if imu.ndim >= 2 and imu.shape[-1] >= 3:
        if imu.shape[0] >= 2:
            return np.asarray(imu[1]).reshape(-1)[:3].astype(float)
        return np.asarray(imu[0]).reshape(-1)[:3].astype(float)
    flat = imu.reshape(-1)
    if flat.size >= 3:
        return flat[-3:].astype(float)
    return np.zeros(3, dtype=float)


def extract_depth(depth_sensor, fallback_z):
    depth = np.asarray(depth_sensor).reshape(-1)
    if depth.size >= 1:
        return float(depth[0])
    return float(-fallback_z)

import numpy as np


def apply_safety(command, position, limits_cfg):
    cmd = np.array(command, dtype=float)
    pos = np.array(position, dtype=float)
    events = []

    env_min = np.array(limits_cfg["env_min"], dtype=float)
    env_max = np.array(limits_cfg["env_max"], dtype=float)
    margin_xy = float(limits_cfg["safety_margin_xy"])
    margin_z = float(limits_cfg["safety_margin_z"])

    x_min_safe = env_min[0] + margin_xy
    x_max_safe = env_max[0] - margin_xy
    y_min_safe = env_min[1] + margin_xy
    y_max_safe = env_max[1] - margin_xy
    z_min_safe = env_min[2] + margin_z
    z_max_safe = env_max[2] - margin_z

    near_xy_boundary = (
        pos[0] <= x_min_safe
        or pos[0] >= x_max_safe
        or pos[1] <= y_min_safe
        or pos[1] >= y_max_safe
    )
    if near_xy_boundary:
        cmd[4] *= 0.6
        events.append("near_xy_boundary_thrust_reduce")

    if pos[2] > z_max_safe:
        cmd[0] += 6.0
        cmd[2] -= 6.0
        events.append("too_shallow_pitch_down")
    elif pos[2] < z_min_safe:
        cmd[0] -= 6.0
        cmd[2] += 6.0
        events.append("too_deep_pitch_up")

    cmd[:4] = np.clip(cmd[:4], -float(limits_cfg["fin_deg_max"]), float(limits_cfg["fin_deg_max"]))
    cmd[4] = np.clip(cmd[4], float(limits_cfg["thrust_min"]), float(limits_cfg["thrust_max"]))
    return cmd, events

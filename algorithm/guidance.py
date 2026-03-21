import numpy as np


def clamp_reference(ref_xyz, limits_cfg):
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

    ref = np.array(ref_xyz, dtype=float)
    ref[0] = np.clip(ref[0], x_min_safe, x_max_safe)
    ref[1] = np.clip(ref[1], y_min_safe, y_max_safe)
    ref[2] = np.clip(ref[2], z_min_safe, z_max_safe)
    return ref


def find_nearest_index(points_xy, current_xy, last_index, search_window):
    start = max(0, int(last_index))
    end = min(len(points_xy), start + int(search_window))
    if end <= start + 1:
        end = len(points_xy)

    segment = points_xy[start:end]
    d = np.linalg.norm(segment - current_xy.reshape(1, 2), axis=1)
    offset = int(np.argmin(d))
    return start + offset


def compute_los_target(points, nearest_index, lookahead_distance):
    if nearest_index >= len(points) - 1:
        return points[-1], len(points) - 1

    acc = 0.0
    for idx in range(nearest_index, len(points) - 1):
        seg = np.linalg.norm(points[idx + 1, :2] - points[idx, :2])
        acc += seg
        if acc >= lookahead_distance:
            return points[idx + 1], idx + 1
    return points[-1], len(points) - 1

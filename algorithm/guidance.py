import numpy as np


def clamp_reference(ref_xyz, limits_cfg):
    """将参考点裁剪到带安全裕度的环境边界内。

    Args:
        ref_xyz (array-like): 目标参考点，按 NED 坐标表示。
        limits_cfg (dict): 环境范围与安全裕度配置。

    Returns:
        np.ndarray: 已裁剪的三维参考点。
    """
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
    """在给定搜索窗口内寻找当前点最近的参考路径索引。

    Args:
        points_xy (np.ndarray): 参考轨迹的二维投影点，形状为 (N, 2)。
        current_xy (np.ndarray): 当前位置的二维坐标，形状为 (2,)。
        last_index (int): 上一次命中的索引，用于窗口搜索加速。
        search_window (int): 搜索窗口大小。

    Returns:
        int: 最近路径点的索引。
    """
    start = max(0, int(last_index))
    end = min(len(points_xy), start + int(search_window))
    if end <= start + 1:
        end = len(points_xy)

    segment = points_xy[start:end]
    d = np.linalg.norm(segment - current_xy.reshape(1, 2), axis=1)
    offset = int(np.argmin(d))
    return start + offset


def compute_los_target(points, nearest_index, lookahead_distance):
    """计算 LOS 导引的前视目标点。

    Args:
        points (np.ndarray): 三维参考点序列，形状为 (N, 3)。
        nearest_index (int): 当前最近点索引。
        lookahead_distance (float): 前视距离，单位米。

    Returns:
        tuple[np.ndarray, int]: 前视目标点及其索引。
    """
    if nearest_index >= len(points) - 1:
        return points[-1], len(points) - 1

    acc = 0.0
    for idx in range(nearest_index, len(points) - 1):
        seg = np.linalg.norm(points[idx + 1, :2] - points[idx, :2])
        acc += seg
        if acc >= lookahead_distance:
            return points[idx + 1], idx + 1
    return points[-1], len(points) - 1

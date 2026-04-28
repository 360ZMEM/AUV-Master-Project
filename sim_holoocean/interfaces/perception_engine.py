"""
感知引擎 - 高级传感器建模和信号处理。

该模块实现水下 AUV 仿真中的物理和传感器模型：
  1. 电缆几何和距离计算（分段线段最近点）
  2. HVDC 电缆磁场（Biot-Savart 定律）
  3. 声纳仿真（电缆检测峰值）
  4. 传感器噪声注入（高斯白噪声）

应用场景：
  - 导航：AUV 通过磁场强度判断与电缆的相对位置
  - 避碰：声纳感知附近的电缆
  - 故障模拟：注入现实的测量噪声
"""

import numpy as np

# 真空磁导率（单位：H/m）
MU0 = 4.0e-7 * np.pi


class CablePath:
    """
    分段线性电缆路径 - 用于几何查询和磁场计算。

    表示电缆为多个直线段的连接，可用于：
      1. 最近点查询：给定 AUV 位置，找电缆上离它最近的点
      2. 距离计算：测量 AUV 到电缆的最短距离
      3. 磁场计算：基于 Biot-Savart 定律的分段积分

    参数：
        control_points: ndarray，形状 (N, 3)，N >= 2
            电缆的控制点列表（NED 坐标）。相邻两点间为一段直线。
            示例：
              points = [
                  [0.0, 0.0, 14.0],    # 岸边起点
                  [30.0, 0.0, 14.5],   # 中间点
                  [60.0, 0.0, 15.0],   # 海底终点
              ]
    """

    def __init__(self, control_points):
        """初始化电缆路径。"""
        points = np.asarray(control_points, dtype=float)
        if points.ndim != 2 or points.shape[1] != 3 or points.shape[0] < 2:
            raise ValueError("CABLE_PATH must be N x 3 with N >= 2")
        self.points = points

    def segments(self):
        """
        迭代所有线段。

        产出：
            (start_point, end_point) 元组，每段两个端点
        """
        for i in range(len(self.points) - 1):
            yield self.points[i], self.points[i + 1]

    def closest_point_and_distance(self, p):
        """
        找电缆上离给定点最近的点及距离。

        算法：
          遍历每一段，使用投影法：
            1. 计算点 p 在线段上的投影参数 t ∈ [0, 1]
            2. 限制 t 在 [0, 1] 内（点到线段，非无限线）
            3. 计算候选点及距离
            4. 保留最小距离的点

        参数：
            p: array-like，形状 (3,)
                查询点（NED 坐标）

        返回值：
            (closest_point, min_distance)
              - closest_point: ndarray (3,)
              - min_distance: float（米）
        """
        p = np.asarray(p, dtype=float).reshape(3)
        min_dist = np.inf
        best_point = self.points[0]
        for a, b in self.segments():
            # 线段向量
            ab = b - a
            denom = float(np.dot(ab, ab))
            if denom <= 1e-12:
                # 退化段（两点几乎相同），使用起点
                q = a
            else:
                # 投影参数：t = (p-a)·(b-a) / |b-a|²
                t = np.clip(float(np.dot(p - a, ab) / denom), 0.0, 1.0)
                q = a + t * ab
            # 距离
            d = float(np.linalg.norm(p - q))
            if d < min_dist:
                min_dist = d
                best_point = q
        return best_point, min_dist


def compute_biot_savart_hvdc(auv_pos_ned, cable: CablePath, current_amp=500.0, epsilon=1e-3):
    """
    计算 HVDC 海底电缆产生的磁场（Biot-Savart 定律）。

    物理原理：
      电流元素 Idl 在距离 r 处产生的磁场：
        dB = (μ₀/4π) * I * (dl × r) / |r|³

    近似：
      将电缆分段视为直线段，每段中点处放置电流元素，
      使用 Biot-Savart 公式累加。

    参数：
        auv_pos_ned: array-like，形状 (3,)
            AUV 位置（NED 坐标）
        cable: CablePath
            电缆定义
        current_amp: float
            电流幅度（安培），默认 500A（典型 HVDC 值）
        epsilon: float
            避免奇异性的最小距离（米），默认 1mm

    返回值：
        ndarray，形状 (3,)：磁场向量（特斯拉，NED 坐标）
    """
    p = np.asarray(auv_pos_ned, dtype=float).reshape(3)
    b_total = np.zeros(3, dtype=float)

    # Biot-Savart 系数： μ₀I / 4π
    coeff = MU0 * float(current_amp) / (4.0 * np.pi)

    # 遍历所有线段
    for a, c in cable.segments():
        dl = c - a              # 线段方向和长度
        mid = 0.5 * (a + c)     # 近似点：线段中点
        r = p - mid             # 从电缆到查询点的向量
        r_norm = float(np.linalg.norm(r))

        # 避免极端情况
        if r_norm < epsilon:
            continue

        # dB = (μ₀I/4π) * (dl × r) / |r|³
        b_total += coeff * np.cross(dl, r) / (r_norm ** 3)

    return b_total


def inject_gaussian_noise(vec, sigma):
    """
    为向量注入高斯白噪声（逐元素独立）。

    参数：
        vec: array-like，任意形状
            基值向量
        sigma: float 或 array-like
            标准差（σ）：
              - 标量：所有分量使用相同的 σ
              - 数组：逐分量的 σ

    返回值：
        ndarray，与 vec 相同形状：vec + N(0, σ²)
    """
    vec = np.asarray(vec, dtype=float)
    sigma_arr = np.asarray(sigma, dtype=float)
    if sigma_arr.ndim == 0:
        sigma_arr = np.full_like(vec, float(sigma_arr))
    return vec + np.random.normal(0.0, sigma_arr, size=vec.shape)


def inject_sonar_cable_peak(n_bins, max_range_m, cable_distance_m, base_noise_sigma=0.01, peak_gain=1.0, peak_width_bins=3.0):
    """
    模拟声纳扫描电缆时的回波。

    原理：
      声纳返回强度与距离的函数。如果电缆在实际距离 d，则：
        1. 将 d 映射到波束的索引 idx = floor((d / max_range) * (n_bins - 1))
        2. 以 idx 为中心产生高斯峰（代表真实回波）
        3. 加入高斯噪声（背景）

    参数：
        n_bins: int
            声纳波束分辨率（返回的 bin 数）
        max_range_m: float
            声纳最大感知距离（米）
        cable_distance_m: float
            AUV 到电缆的实际距离（米）
        base_noise_sigma: float
            背景噪声标准差
        peak_gain: float
            回波峰值增益（幅度）
        peak_width_bins: float
            回波峰值宽度（bin 数，以标准差衡量）

    返回值：
        ndarray，形状 (n_bins,)：声纳返回强度（无量纲）
    """
    n_bins = int(n_bins)
    if n_bins <= 0:
        raise ValueError("n_bins must be > 0")

    # 背景噪声
    sonar = np.random.normal(0.0, float(base_noise_sigma), size=n_bins)

    # 距离映射：定步化距离
    cable_distance_m = max(0.0, float(cable_distance_m))
    max_range_m = max(1e-6, float(max_range_m))

    # 电缆对应的 bin 索引
    idx_center = int(np.clip(round((cable_distance_m / max_range_m) * (n_bins - 1)), 0, n_bins - 1))

    # 高斯峰：以 idx_center 为中心，宽度为 peak_width_bins
    idx = np.arange(n_bins, dtype=float)
    peak = float(peak_gain) * np.exp(-0.5 * ((idx - idx_center) / max(float(peak_width_bins), 1e-6)) ** 2)
    sonar += peak

    return sonar

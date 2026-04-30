"""
数字孪生场景生成 - 为 Foxglove 可视化生成虚拟环境数据。

该模块实现可复用的地形和电缆生成逻辑，用于：
  1. 仿真侧可视化（HoloOcean 桥接）
  2. Mock 可视化（快照生成）

特点：
  - 参数化配置：支持自定义地形、电缆、可视化参数
  - 确定性随机数：相同种子生成相同的地形（用于对齐）
  - 流式更新：历史轨迹、视椎体范围等动态生成
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any

import numpy as np

from common.physics import CABLE_SUSPENSION_HEIGHT, SEA_BOTTOM_Z
from common.protocol import (
    KEY_CENTER_NED,
    KEY_HEIGHT_M,
    KEY_POINTS_NED,
    KEY_POSITION_NED,
    KEY_RADIUS_M,
    KEY_RPY_NED,
    KEY_TRAIL_NED,
    Z_PATH_CABLE_MARKER,
    Z_PATH_HISTORY_TRAIL,
    Z_PATH_SEABED_CLOUD,
    Z_PATH_TRUTH_POSE,
    Z_PATH_VIEW_RANGE,
)


@dataclass(slots=True)
class VirtualEnvironmentConfig:
    """
    数字孪生环境配置参数。

    地形生成：
      terrain_extent_m: float，地形范围（米），以 AUV 为中心
      terrain_resolution_m: float，地形网格分辨率（米）
      terrain_noise_amplitude_m: float，地形起伏振幅（米）
      terrain_noise_scale_m: float，噪声波长（米）
      terrain_noise_octaves: int，Perlin 噪声的噪声层数
      terrain_seed: int，确定性随机数种子

    电缆配置：
      seabed_z_m: float，海底深度（米）
      cable_suspension_height_m: float，电缆悬浮高度（米，相对海底）
      cable_origin_ned: tuple (3,)，电缆起点（NED）
      cable_direction_ned: tuple (3,)，电缆方向（单位向量）
      cable_length_m: float，电缆总长（米）
      cable_step_m: float，电缆采样步长（米）

    可视化参数：
      view_radius_m: float，视椎体球体半径（米）
      view_height_m: float，视椎体高度（米）
      trail_limit: int，历史轨迹最大点数
    """
    terrain_extent_m: float = 50.0
    terrain_resolution_m: float = 1.0
    terrain_noise_amplitude_m: float = 1.0
    terrain_noise_scale_m: float = 8.0
    terrain_noise_octaves: int = 3
    terrain_seed: int = 7
    terrain_slope_deg: float = 0.0  # 新增：地形斜坡角度（度），正值表示下坡（深度增加），负值表示上坡（深度减小）
    seabed_z_m: float = SEA_BOTTOM_Z
    cable_suspension_height_m: float = CABLE_SUSPENSION_HEIGHT
    cable_origin_ned: tuple[float, float, float] = (0.0, 0.0, 14.0)
    cable_direction_ned: tuple[float, float, float] = (1.0, 0.0, 0.0)
    cable_length_m: float = 60.0
    cable_step_m: float = 1.0
    view_radius_m: float = 3.0
    view_height_m: float = 0.1
    trail_limit: int = 800


def _smoothstep(value: float) -> float:
    """平滑阶跃函数 f(t) = t²(3-2t)，用于 Perlin 噪声插值。"""
    return value * value * (3.0 - 2.0 * value)


def _value_noise_2d(x: float, y: float, seed: int) -> float:
    """格值噪声（Perlin-style value noise）在 2D 单位格点上。"""
    x0 = math.floor(x)
    y0 = math.floor(y)
    x1 = x0 + 1
    y1 = y0 + 1

    def _hash(ix: int, iy: int) -> float:
        value = (ix * 374761393 + iy * 668265263 + seed * 1442695040888963407) & 0xFFFFFFFFFFFFFFFF
        value ^= value >> 13
        value *= 1274126177
        value &= 0xFFFFFFFFFFFFFFFF
        return ((value >> 11) & 0xFFFF) / 0x7FFF - 1.0

    sx = _smoothstep(x - x0)
    sy = _smoothstep(y - y0)
    n00 = _hash(x0, y0)
    n10 = _hash(x1, y0)
    n01 = _hash(x0, y1)
    n11 = _hash(x1, y1)
    ix0 = n00 + sx * (n10 - n00)
    ix1 = n01 + sx * (n11 - n01)
    return ix0 + sy * (ix1 - ix0)


def berlin_noise_2d(x: float, y: float, *, seed: int = 7, octaves: int = 3, scale: float = 8.0, persistence: float = 0.5) -> float:
    """
    柏林噪声（分形布朗运动 fBm）：多层叠加的格值噪声。

    用于生成自然外观的地形：
      - 大尺度：海底宽缓起伏
      - 中尺度：沙丘和沟渠
      - 小尺度：细节纹理

    参数：
        x, y: float，查询点
        seed: int，随机种子
        octaves: int，噪声层数（越多越细致）
        scale: float，基础噪声波长（米）
        persistence: float，各层振幅衰减系数（< 1 时衰减）

    返回值：
        float，范围 [-1, 1] 的噪声值
    """
    if octaves <= 0:
        raise ValueError("octaves must be > 0")
    total = 0.0
    amplitude = 1.0
    frequency = 1.0 / max(scale, 1e-6)
    max_amplitude = 0.0
    for octave in range(octaves):
        total += amplitude * _value_noise_2d(x * frequency, y * frequency, seed + octave * 101)
        max_amplitude += amplitude
        amplitude *= persistence
        frequency *= 2.0
    return total / max_amplitude if max_amplitude > 1e-12 else 0.0


def euler_to_quaternion(roll: float, pitch: float, yaw: float) -> tuple[float, float, float, float]:
    """
    欧拉角 (roll, pitch, yaw) 转四元数 (x, y, z, w)。

    用于 Foxglove 的姿态显示（3D 模型旋转）。
    """
    cr = math.cos(roll * 0.5)
    sr = math.sin(roll * 0.5)
    cp = math.cos(pitch * 0.5)
    sp = math.sin(pitch * 0.5)
    cy = math.cos(yaw * 0.5)
    sy = math.sin(yaw * 0.5)
    return (
        sr * cp * cy - cr * sp * sy,
        cr * sp * cy + sr * cp * sy,
        cr * cp * sy - sr * sp * cy,
        cr * cp * cy + sr * sp * sy,
    )


class VirtualEnvironment:
    """
    数字孪生环境生成器 - 海底、电缆、实时轨迹等。

    职责：
      1. 地形采样：在 AUV 周围生成 Perlin 噪声的海底，用于可视化
      2. 电缆路径：生成地面真实电缆的分段点，用于标记和路线规划
      3. 历史轨迹：维护 AUV 运动历史（环形缓冲）
      4. 视椎体：定义 AUV 的感知范围（用于 Foxglove 中的视锥体）
      5. 姿态数据：打包位置、旋转为 Foxglove 消息

    设计特点：
      - 确定性：同一种子的地形总是相同，便于调试和可复现性
      - 高效：只在需要时采样地形（而非预生成）
      - 遗忘缓冲：轨迹有限制长度，避免内存溢出
    """

    def __init__(self, config: dict[str, Any] | None = None):
        """
        初始化虚拟环境。

        参数：
            config: dict or None
                配置字典，映射到 VirtualEnvironmentConfig 的字段
        """
        cfg = config or {}
        self.config = VirtualEnvironmentConfig(
            terrain_extent_m=float(cfg.get("terrain_extent_m", 50.0)),
            terrain_resolution_m=float(cfg.get("terrain_resolution_m", 1.0)),
            terrain_noise_amplitude_m=float(cfg.get("terrain_noise_amplitude_m", 1.0)),
            terrain_noise_scale_m=float(cfg.get("terrain_noise_scale_m", 8.0)),
            terrain_noise_octaves=int(cfg.get("terrain_noise_octaves", 3)),
            terrain_seed=int(cfg.get("terrain_seed", 7)),
            terrain_slope_deg=float(cfg.get("terrain_slope_deg", 0.0)),
            seabed_z_m=float(cfg.get("seabed_z_m", SEA_BOTTOM_Z)),
            cable_suspension_height_m=float(cfg.get("cable_suspension_height_m", CABLE_SUSPENSION_HEIGHT)),
            cable_origin_ned=tuple(float(v) for v in cfg.get("cable_origin_ned", (0.0, 0.0, 14.0))[:3]),
            cable_direction_ned=tuple(float(v) for v in cfg.get("cable_direction_ned", (1.0, 0.0, 0.0))[:3]),
            cable_length_m=float(cfg.get("cable_length_m", 60.0)),
            cable_step_m=float(cfg.get("cable_step_m", 1.0)),
            view_radius_m=float(cfg.get("view_radius_m", 3.0)),
            view_height_m=float(cfg.get("view_height_m", 0.1)),
            trail_limit=int(cfg.get("trail_limit", 800)),
        )
        self._trail: list[list[float]] = []  # 环形缓冲：AUV 历史位置

    def _terrain_height(self, x: float, y: float) -> float:
        """
        查询给定 (x, y) 位置的地形高度（Z 坐标）。

        算法：
          z = seabed_z + noise_amplitude * perlin_noise_2d(x, y)

        参数：
            x, y: float，水平位置（NED 坐标的 X、Y）

        返回值：
            float，该位置的 Z 坐标（深度，正向下）
        """
        noise = berlin_noise_2d(
            x,
            y,
            seed=self.config.terrain_seed,
            octaves=self.config.terrain_noise_octaves,
            scale=self.config.terrain_noise_scale_m,
        )
        # 添加基于 X 轴的线性斜坡：正的 slope_deg 表示随着 X 增加深度变浅（上坡，z变小）
        # z 轴正方向朝下，因此上坡是减去高度
        slope_offset = -math.tan(math.radians(self.config.terrain_slope_deg)) * max(0.0, x - 10.0) # 假设斜坡从 x=10 处开始
        return self.config.seabed_z_m + self.config.terrain_noise_amplitude_m * noise + slope_offset

    def sample_seabed_points(self, center_ned: np.ndarray | list[float]) -> list[list[float]]:
        """
        采样以 AUV 为中心的海底点云。

        用于 Foxglove 中的点云可视化（表示地形）。

        参数：
            center_ned: array-like (3,)，AUV 当前位置

        返回值：
            list of [x, y, z] 坐标，NED 系下的地形采样点
        """
        center = np.asarray(center_ned, dtype=float).reshape(3)
        half = self.config.terrain_extent_m * 0.5
        step = max(self.config.terrain_resolution_m, 0.2)
        xs = np.arange(center[0] - half, center[0] + half + 1e-6, step, dtype=float)
        ys = np.arange(center[1] - half, center[1] + half + 1e-6, step, dtype=float)
        points: list[list[float]] = []
        for x in xs:
            for y in ys:
                z = self._terrain_height(float(x), float(y))
                points.append([float(x), float(y), float(z)])
        return points

    def cable_points(self) -> list[list[float]]:
        """
        生成电缆的分段点（路径）。

        参数化线段：
          point[i] = origin + direction * step * i，i = 0, 1, ..., N

        返回值：
            list of [x, y, z] 坐标，电缆上的采样点
        """
        origin = np.asarray(self.config.cable_origin_ned, dtype=float).reshape(3)
        direction = np.asarray(self.config.cable_direction_ned, dtype=float).reshape(3)
        norm = float(np.linalg.norm(direction))
        if norm <= 1e-9:
            direction = np.array([1.0, 0.0, 0.0], dtype=float)
        else:
            direction = direction / norm

        cable_height = self.config.seabed_z_m - self.config.cable_suspension_height_m
        start_z = float(origin[2]) if abs(float(origin[2])) > 1e-9 else float(cable_height)
        start = np.array([origin[0], origin[1], start_z], dtype=float)
        step = max(self.config.cable_step_m, 0.2)
        count = max(2, int(math.ceil(self.config.cable_length_m / step)) + 1)
        return [
            [float(start[0] + direction[0] * step * i), float(start[1] + direction[1] * step * i), float(start[2] + direction[2] * step * i)]
            for i in range(count)
        ]

    def update_trail(self, position_ned: np.ndarray | list[float]) -> list[list[float]]:
        """
        更新 AUV 运动轨迹（环形缓冲）。

        参数：
            position_ned: array-like (3,)，当前位置

        返回值：
            list of [x, y, z]，整个轨迹的点序列（最多 trail_limit 点）
        """
        point = np.asarray(position_ned, dtype=float).reshape(3).tolist()
        self._trail.append([float(point[0]), float(point[1]), float(point[2])])
        if len(self._trail) > self.config.trail_limit:
            self._trail = self._trail[-self.config.trail_limit :]
        return list(self._trail)

    def sample_mock_pose(self, sample_index: int) -> tuple[list[float], list[float]]:
        """
        生成确定性的 mock AUV 位姿（用于可视化截图）。

        参数：
            sample_index: int，采样索引（步号）

        返回值：
            (position_ned, rpy_ned)，位置和欧拉角
        """
        phase = float(sample_index) * 0.1
        x = 2.5 * math.sin(0.13 * phase)
        y = 1.2 * math.sin(0.07 * phase)
        z = float(self.config.seabed_z_m) - 3.0 + 0.18 * math.sin(0.05 * phase)
        roll = 0.03 * math.sin(0.17 * phase)
        pitch = 0.05 * math.sin(0.11 * phase)
        yaw = 0.2 * math.sin(0.08 * phase)
        return [x, y, z], [roll, pitch, yaw]

    def build_truth_pose_payload(self, position_ned: np.ndarray | list[float], rpy_ned: np.ndarray | list[float]) -> dict[str, Any]:
        """构造位置和姿态的数据包。"""
        position = np.asarray(position_ned, dtype=float).reshape(3).tolist()
        rpy = np.asarray(rpy_ned, dtype=float).reshape(3).tolist()
        return {
            KEY_POSITION_NED: [float(v) for v in position],
            KEY_RPY_NED: [float(v) for v in rpy],
        }

    def build_view_range_payload(self, position_ned: np.ndarray | list[float]) -> dict[str, Any]:
        """构造视椎体（感知范围）的数据包。"""
        center = np.asarray(position_ned, dtype=float).reshape(3).tolist()
        return {
            KEY_CENTER_NED: [float(v) for v in center],
            KEY_RADIUS_M: float(self.config.view_radius_m),
            KEY_HEIGHT_M: float(self.config.view_height_m),
        }

    def build_visual_payloads(
        self,
        *,
        position_ned: np.ndarray | list[float],
        rpy_ned: np.ndarray | list[float],
        publish_terrain: bool = True,
    ) -> dict[str, dict[str, Any]]:
        """
        生成所有可视化数据包。

        参数：
            position_ned: (3,)，AUV 位置
            rpy_ned: (3,)，AUV 欧拉角
            publish_terrain: bool，是否包含地形点云（降采样用）

        返回值：
            dict，键为 Zenoh topic 路径，值为数据包
        """
        position = np.asarray(position_ned, dtype=float).reshape(3)
        payloads: dict[str, dict[str, Any]] = {
            Z_PATH_CABLE_MARKER: {KEY_POINTS_NED: self.cable_points()},
            Z_PATH_TRUTH_POSE: self.build_truth_pose_payload(position, rpy_ned),
            Z_PATH_HISTORY_TRAIL: {KEY_TRAIL_NED: self.update_trail(position)},
            Z_PATH_VIEW_RANGE: self.build_view_range_payload(position),
        }
        if publish_terrain:
            payloads[Z_PATH_SEABED_CLOUD] = {KEY_POINTS_NED: self.sample_seabed_points(position)}
        return payloads

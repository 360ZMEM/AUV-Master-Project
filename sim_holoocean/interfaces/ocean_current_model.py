"""
三维洋流干扰模型 — 用于 AUV 仿真环境的抗扰性评估。

功能:
  1. 生成基础洋流矢量 (CONSTANT 或 SINE_WAVE 模式)
  2. 注入低通滤波的脉动噪声，模拟真实海洋湍流特性
  3. 提供当前时刻的世界系洋流速度
  4. 计算 AUV 对水速度 (water-relative velocity)

坐标系约定:
  - NED (北东地): x=北, y=东, z=地 (正向下)
  - UE4: x=前, y=右, z=上
  - 洋流矢量在 NED 世界系下定义

低通滤波:
  使用一阶 IIR 滤波器: y[n] = α·x[n] + (1-α)·y[n-1]
  其中 α = dt / (τ + dt), τ 为时间常数
  截止频率 fc = 1/(2πτ)
"""

from __future__ import annotations

from typing import Any

import numpy as np


class FirstOrderLPF:
    """
    一阶低通滤波器 (IIR 实现)。

    差分方程:
      y[n] = α · x[n] + (1 - α) · y[n-1]

    其中 α = dt / (τ + dt)
    截止频率 fc = 1 / (2π·τ)

    用于对洋流脉动噪声进行低通滤波，确保波动频率 ≤ 1/5 Hz，
    模拟真实海洋环境中的缓慢湍流特性。
    """

    def __init__(self, tau: float, dt: float, dim: int = 1):
        """
        参数:
            tau: 时间常数 (秒), τ
            dt: 采样间隔 (秒)
            dim: 滤波信号维度
        """
        if tau <= 0.0:
            raise ValueError(f"tau must be positive, got {tau}")
        if dt <= 0.0:
            raise ValueError(f"dt must be positive, got {dt}")

        self.alpha = dt / (tau + dt)
        self._state = np.zeros(dim, dtype=np.float64)
        self._initialized = False

    def reset(self, value: np.ndarray | None = None) -> None:
        """重置滤波器状态。"""
        if value is not None:
            self._state = np.asarray(value, dtype=np.float64).copy()
        else:
            self._state = np.zeros_like(self._state)
        self._initialized = True

    def filter(self, x: np.ndarray) -> np.ndarray:
        """
        应用低通滤波。

        参数:
            x: 输入信号 (dim,)

        返回:
            滤波后的输出信号 (dim,)
        """
        x = np.asarray(x, dtype=np.float64).reshape(-1)
        if not self._initialized:
            self._state = x.copy()
            self._initialized = True
            return self._state.copy()

        self._state = self.alpha * x + (1.0 - self.alpha) * self._state
        return self._state.copy()


class OceanCurrentModel:
    """
    三维洋流干扰模型。

    支持的洋流类型:
      - CONSTANT: 恒定洋流矢量 + 低通滤波的脉动噪声
      - SINE_WAVE: 正弦波时变洋流 (潮汐模拟) + 低通滤波噪声

    物理原理:
      AUV 的对水速度 (water-relative velocity) 为:
        ν_rel = ν_body - R_b2n^T @ v_current_ned
      其中:
        - ν_body: AUV 体坐标系速度
        - R_b2n: 从体坐标系到 NED 世界系的旋转矩阵
        - v_current_ned: NED 世界系下的洋流速度

      阻力项 (Damping) 使用 ν_rel 计算，而运动学积分使用原始 ν。
    """

    def __init__(self, config: dict[str, Any], dt: float):
        """
        参数:
            config: 洋流配置字典，包含:
                - enabled: bool, 是否启用洋流模型
                - type: str, 'CONSTANT' 或 'SINE_WAVE'
                - vector_ned: list[float], [v_north, v_east, v_down] (m/s)
                - noise_std: float, 脉动噪声标准差
                - max_t: float, 低通滤波时间常数 τ (秒)
            dt: 仿真步长 (秒)
        """
        self._enabled = bool(config.get("enabled", False))
        self._current_type = str(config.get("type", "CONSTANT")).strip().upper()
        self._vector_ned = np.asarray(config.get("vector_ned", [0.0, 0.0, 0.0]), dtype=np.float64)
        self._noise_std = float(config.get("noise_std", 0.0))
        self._tau = float(config.get("max_t", 5.0))
        self._dt = float(dt)

        # 潮汐参数 (SINE_WAVE 模式)
        self._sine_amplitude = self._vector_ned.copy()
        self._sine_period = 300.0  # 默认 5 分钟周期 (模拟半日潮的慢变化)
        self._sine_phase = 0.0

        # 低通滤波器 (用于脉动噪声)
        self._noise_lpf = FirstOrderLPF(tau=self._tau, dt=self._dt, dim=3)

        # 确定性随机数生成器 (可复现)
        self._rng = np.random.default_rng(seed=42)

        # 上一帧的低通滤波噪声 (用于保持状态连续性)
        self._last_filtered_noise = np.zeros(3, dtype=np.float64)

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def current_type(self) -> str:
        return self._current_type

    def reset(self) -> None:
        """重置洋流模型状态。"""
        self._noise_lpf.reset()
        self._last_filtered_noise = np.zeros(3, dtype=np.float64)

    def get_current_world(self, t: float) -> np.ndarray:
        """
        获取当前时刻世界系 (NED) 下的洋流速度。

        参数:
            t: 当前仿真时间 (秒)

        返回:
            v_current_ned: [v_north, v_east, v_down] (m/s)
        """
        if not self._enabled:
            return np.zeros(3, dtype=np.float64)

        # 1. 基础洋流矢量
        if self._current_type == "SINE_WAVE":
            base_current = self._compute_sine_wave_current(t)
        else:
            base_current = self._vector_ned.copy()

        # 2. 脉动噪声 (经低通滤波)
        raw_noise = self._rng.normal(0.0, self._noise_std, size=3)
        filtered_noise = self._noise_lpf.filter(raw_noise)
        self._last_filtered_noise = filtered_noise

        return base_current + filtered_noise

    def get_relative_velocity(
        self,
        nu_body: np.ndarray,
        rpy_ned: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray]:
        """
        计算 AUV 对水速度 (water-relative velocity)。

        公式:
          ν_rel_body = ν_body - R_n2b @ v_current_ned
          其中 R_n2b = R_b2n^T 是 NED→体坐标系的旋转矩阵

        参数:
            nu_body: 体坐标系速度 [u, v, w, p, q, r] (m/s, rad/s)
            rpy_ned: NED 系欧拉角 [roll, pitch, yaw] (rad)

        返回:
            (nu_rel_body, v_current_ned):
                - nu_rel_body: 对水速度 (体坐标系)
                - v_current_ned: 当前世界系洋流速度
        """
        v_current_ned = self.get_current_world(0.0)  # t 由调用方管理

        if not self._enabled or np.allclose(v_current_ned, 0.0):
            return nu_body.copy(), v_current_ned

        # 构建 NED→体坐标系旋转矩阵
        R_n2b = self._build_r_ned_to_body(rpy_ned)

        # 将洋流速度转换到体坐标系
        v_current_body = R_n2b @ v_current_ned

        # 计算对水速度 (只考虑线速度部分)
        nu_rel = nu_body.copy()
        nu_rel[:3] = nu_body[:3] - v_current_body

        return nu_rel, v_current_ned

    def get_current_magnitude(self, t: float) -> float:
        """获取当前洋流速度的模值 (m/s)。"""
        return float(np.linalg.norm(self.get_current_world(t)))

    def _compute_sine_wave_current(self, t: float) -> np.ndarray:
        """
        计算正弦波时变洋流 (潮汐模拟)。

        公式:
          v(t) = amplitude · sin(2π·t / period + phase)
        """
        omega = 2.0 * np.pi / self._sine_period
        modulation = np.sin(omega * t + self._sine_phase)
        return self._sine_amplitude * modulation

    @staticmethod
    def _build_r_ned_to_body(rpy_ned: np.ndarray) -> np.ndarray:
        """
        构建从 NED 世界系到体坐标系的旋转矩阵。

        R_n2b = Rz(-yaw) · Ry(-pitch) · Rx(-roll)

        参数:
            rpy_ned: [roll, pitch, yaw] (rad)

        返回:
            R_n2b: 3×3 旋转矩阵
        """
        roll, pitch, yaw = rpy_ned

        cr, sr = np.cos(roll), np.sin(roll)
        cp, sp = np.cos(pitch), np.sin(pitch)
        cy, sy = np.cos(yaw), np.sin(yaw)

        # R_n2b = (R_b2n)^T
        # R_b2n = Rz(yaw) · Ry(pitch) · Rx(roll)
        # 直接计算 R_n2b:
        R = np.array([
            [cy * cp,  sy * cp,     -sp],
            [cy * sp * sr - sy * cr,
             sy * sp * sr + cy * cr,
             cp * sr],
            [cy * sp * cr + sy * sr,
             sy * sp * cr - cy * sr,
             cp * cr],
        ], dtype=np.float64)

        return R

"""
异步多速率传感器采样缓存 - 模拟真实 AUV 传感器的独立时钟。

概述：
  不同的 AUV 传感器采样速率各异：
    - IMU（惯性测量单元）:   ~100 Hz，高速反应，噪声大
    - DVL（多普勒速度测头）：~6 Hz，低频但精度高，需时间处理
    - 深度传感器：           ~50 Hz，中等速率
    - 磁力计：               ~20 Hz，地磁导航

  本模块模拟这种多速率架构：仿真循环以 60 Hz 运行，但每个传感器遵循各自的
  采样周期。只有当某传感器的时钟嘀嗒时，才从原始状态中提取其最新值，否则
  返回上次缓存的值。这使得决策系统能体验到真实硬件的 "时间同步困难"。

功能：
  1. 独立的采样时钟：每传感器一个
  2. 时钟滴答时采样更新，否则缓存复用
  3. 线程安全的快照机制（深拷贝）
  4. 纯标准库实现，无外部依赖
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field


@dataclass
class SensorSnapshot:
    """
    传感器值的即时快照 - 不可变（某种程度上）。

    表示某一时刻所有传感器的采样值。后续若需修改，应调用 .copy() 生成副本。

    属性：
      imu: dict | None
          IMU 数据，包含：
            - heading_deg: 航向 [0-360)
            - pitch_deg: 俯仰角 [-90, 90]
            - roll_deg: 横滚角 [-180, 180]
      dvl: dict | None
          DVL（多普勒速度测头）数据，包含：
            - speed_mps: 前向速度（m/s）
      depth: dict | None
          深度传感器数据，包含：
            - depth_m: 深度（米）
      mag: dict | None
          磁力计数据，包含：
            - B_ned: 磁场矢量 [Bx, By, Bz]（特斯拉）
            - B_norm: 磁场强度（特斯拉）
      ts: float
          快照的时间戳（秒，通常为 time.time()）
    """

    imu: dict | None = None
    dvl: dict | None = None
    depth: dict | None = None
    mag: dict | None = None
    ts: float = 0.0
    imu_ts: float = 0.0
    dvl_ts: float = 0.0
    depth_ts: float = 0.0
    mag_ts: float = 0.0

    def copy(self) -> SensorSnapshot:
        """
        返回完整深拷贝。

        调用者可安全修改副本而不影响原快照。这是传感器缓存向外部
        暴露数据的标准方式（防止意外共享状态）。
        """
        return SensorSnapshot(
            imu=deepcopy(self.imu) if self.imu else None,
            dvl=deepcopy(self.dvl) if self.dvl else None,
            depth=deepcopy(self.depth) if self.depth else None,
            mag=deepcopy(self.mag) if self.mag else None,
            ts=self.ts,
            imu_ts=self.imu_ts,
            dvl_ts=self.dvl_ts,
            depth_ts=self.depth_ts,
            mag_ts=self.mag_ts,
        )


class SensorSampleCache:
    """
    独立时钟的多速率传感器采样缓存。

    工作原理：
      1. 外部以高频率（如 60 Hz）调用 update(raw_state, now)
      2. 内部维护各传感器的采样周期和上次采样时刻
      3. 仅当 now - last_sample_ts >= period 时，才从 raw_state 提取新值
      4. 否则返回缓存的旧值（模拟传感器尚未就绪）
      5. 应用层得到的是 "仿真快照+缓存的真实数据混合"

    参数：
      imu_hz: IMU 采样频率（Hz），0 表示禁用缓存 / 每帧更新
      dvl_hz: DVL 采样频率（Hz），0 表示禁用缓存 / 每帧更新
      depth_hz: 深度传感器采样频率（Hz），0 表示禁用缓存 / 每帧更新
      mag_hz: 磁力计采样频率（Hz），0 表示禁用缓存 / 每帧更新

    示例：
      cache = SensorSampleCache(imu_hz=100, dvl_hz=6, depth_hz=50, mag_hz=20)
      # 现在 update() 每 100Hz 才更新 IMU，每 6Hz 才更新 DVL，等等
      for t in times:
          snapshot = cache.update(raw_physics_state, t)
          # snapshot 中的 IMU 可能已更新，但 DVL 仍是 10 帧前的值
    """

    def __init__(
        self,
        imu_hz: float = 100.0,
        dvl_hz: float = 6.0,
        depth_hz: float = 50.0,
        mag_hz: float = 20.0,
    ) -> None:
        """
        初始化多速率缓存。

        参数：
          *_hz: 各传感器的采样频率（Hz）。0 或负值表示禁用，每帧都更新。
        """
        def _period(hz: float) -> float:
            """将频率转换为周期（秒）。若 hz ≤ 0，返回 0（表示禁用缓存）。"""
            return 1.0 / max(0.1, hz) if hz > 0 else 0.0

        # ────────────────────────────────────────
        # 各传感器的采样周期（秒）
        # ────────────────────────────────────────
        self._imu_period = _period(imu_hz)
        self._dvl_period = _period(dvl_hz)
        self._depth_period = _period(depth_hz)
        self._mag_period = _period(mag_hz)

        # ────────────────────────────────────────
        # 各传感器的上次采样时刻
        # 初始化为 -999.0，保证首次调用时条件 (now - last_ts) >= period 必成立
        # ────────────────────────────────────────
        self._last_imu_ts = -999.0
        self._last_dvl_ts = -999.0
        self._last_depth_ts = -999.0
        self._last_mag_ts = -999.0

        # ────────────────────────────────────────
        # 内部缓存的快照
        # ────────────────────────────────────────
        self._snapshot = SensorSnapshot()

    # ────────────────────────────────────────────────────────────────
    # 公共 API
    # ────────────────────────────────────────────────────────────────

    def update(
        self,
        raw_state: dict,
        now: float,
    ) -> SensorSnapshot:
        """
        根据各传感器的独立时钟更新缓存，并返回最新快照。

        算法：
          对每个传感器：
            1. 尝试从 raw_state 中提取其值
            2. 若提取失败或值缺失，跳过此传感器（保持缓存）
            3. 若提取成功：
               a. 检查 now - last_sample_ts >= period
               b. 若是，则更新内部 _snapshot，并记录本次采样时刻
               c. 若否，保持缓存不变
            4. 返回 _snapshot 的深拷贝（防止外部修改）

        参数：
          raw_state: 字典，包含各传感器的原始数据
                   预期键：'imu', 'dvl', 'depth', 'mag'
                   缺失键会被忽略（传感器保持上次缓存值）
          now: 当前时刻（秒，通常 time.time()）

        返回值：
          SensorSnapshot：快照的深拷贝，包含：
            - 已更新的传感器（超过采样周期）
            - 缓存的传感器（周期未满）
            - 从未有过数据的传感器（为 None）
        """
        # ── IMU ──
        imu_data = self._extract_imu(raw_state)
        if imu_data is not None:
            if self._imu_period <= 0 or (now - self._last_imu_ts) >= self._imu_period:
                # 周期已满，更新缓存
                self._snapshot.imu = imu_data
                self._last_imu_ts = now
                self._snapshot.imu_ts = now

        # ── DVL ──
        dvl_data = self._extract_dvl(raw_state)
        if dvl_data is not None:
            if self._dvl_period <= 0 or (now - self._last_dvl_ts) >= self._dvl_period:
                self._snapshot.dvl = dvl_data
                self._last_dvl_ts = now
                self._snapshot.dvl_ts = now

        # ── Depth ──
        depth_data = self._extract_depth(raw_state)
        if depth_data is not None:
            if self._depth_period <= 0 or (now - self._last_depth_ts) >= self._depth_period:
                self._snapshot.depth = depth_data
                self._last_depth_ts = now
                self._snapshot.depth_ts = now

        # ── Mag ──
        mag_data = self._extract_mag(raw_state)
        if mag_data is not None:
            if self._mag_period <= 0 or (now - self._last_mag_ts) >= self._mag_period:
                self._snapshot.mag = mag_data
                self._last_mag_ts = now
                self._snapshot.mag_ts = now

        # 更新快照时间戳并返回副本
        self._snapshot.ts = now
        return self._snapshot.copy()

    def snapshot(self) -> SensorSnapshot:
        """
        返回当前缓存的快照（不更新）。

        用于查询状态而无需提供新的原始数据。与 update() 不同的是，
        此方法不会触发任何采样时钟逻辑。
        """
        return self._snapshot.copy()

    def reset(self) -> None:
        """
        清空所有缓存值并重置采样时钟。

        用于实验重启或故障恢复场景。调用后，下一次 update() 会立即
        为所有传感器提取新值（因为所有 last_ts 都被重置为 -999.0）。
        """
        self._last_imu_ts = -999.0
        self._last_dvl_ts = -999.0
        self._last_depth_ts = -999.0
        self._last_mag_ts = -999.0
        self._snapshot = SensorSnapshot()

    # ────────────────────────────────────────────────────────────────
    # 私有 API：数据提取辅助函数（可在子类中重写用于测试）
    # ────────────────────────────────────────────────────────────────

    @staticmethod
    def _extract_imu(raw_state: dict) -> dict | None:
        """从原始状态提取 IMU 数据。"""
        imu = raw_state.get("imu")
        if imu is None:
            return None
        return {
            "heading_deg": float(imu.get("heading_deg", 0.0)),
            "pitch_deg": float(imu.get("pitch_deg", 0.0)),
            "roll_deg": float(imu.get("roll_deg", 0.0)),
        }

    @staticmethod
    def _extract_dvl(raw_state: dict) -> dict | None:
        """从原始状态提取 DVL 数据。"""
        dvl = raw_state.get("dvl")
        if dvl is None:
            return None
        return {"speed_mps": float(dvl.get("speed_mps", 0.0))}

    @staticmethod
    def _extract_depth(raw_state: dict) -> dict | None:
        """从原始状态提取深度数据。"""
        depth = raw_state.get("depth")
        if depth is None:
            return None
        return {"depth_m": float(depth.get("depth_m", 0.0))}

    @staticmethod
    def _extract_mag(raw_state: dict) -> dict | None:
        """从原始状态提取磁力计数据。"""
        mag = raw_state.get("mag")
        if mag is None:
            return None
        return {
            "B_ned": list(mag.get("B_ned", [0.0, 0.0, 0.0])),
            "B_norm": float(mag.get("B_norm", 0.0)),
        }

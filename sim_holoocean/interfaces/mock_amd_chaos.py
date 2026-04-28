"""
故障注入层 - 为 Mock AMD 注入真实环境的故障以增强仿真保真度。

应用场景：
  水下 AUV 面临多种故障模式：
    1. 传感器故障：漂移（陀螺仪老化）、冻结（水进入）、饱和（强磁场）
    2. 通信故障：丢包、重排序、延迟突增、上行中断
    3. 组合故障：漏水导致供电不稳，进而导致传感器失效

  本模块通过 ChaosProfile 配置这些故障，并在运行时注入到仿真数据中，
  用于验证控制系统的故障恢复能力和鲁棒性。

故障分类：
  - 传输层：丢包、重排序
  - 传感器层：DVL 冻结、IMU 漂移、深度尖峰、磁力计饱和
  - 上行链路：通信中断（周期性）

特点：
  - 纯标准库，无外部依赖
  - 有状态的注入器（累积漂移、记忆冻结值）
  - 不修改原输入（深拷贝返回）

故障策略：
  1. DVL 冻结：在 dvl_freeze_after_s 秒后，速度值冻结为当时值
  2. IMU 漂移：航向值线性增长，模拟陀螺仪偏置累积
  3. 深度尖峰：在 depth_spike_after_s 秒后，深度值突增指定量
  4. 磁力计饱和：磁场分量限幅在阈值，模拟强磁场干扰
  5. 上行中断：周期性地丢弃整个上行包（上位机无法接收）
  6. 丢包：以概率随机丢弃下行命令包
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any

from common.physics import clamp

try:
    from .mock_amd_sensor_cache import SensorSnapshot
except ImportError:
    from mock_amd_sensor_cache import SensorSnapshot


@dataclass
class ChaosProfile:
    """
    故障注入配置 - 定义所有可能的故障模式及其参数。

    所有故障都由独立的 *_enabled 开关控制。主开关 enabled 为总开关：
    当 enabled=False 时，所有注入都被禁用（无论子开关如何）。

    属性说明：

    主开关：
      enabled: bool
          全局总开关。若为 False，整个故障注入被禁用。

    传输层故障：
      packet_loss_pct: float [0.0-1.0]
          下行命令包丢失概率（0% ~ 100%）。
      reorder_enabled: bool
          是否启用包重排序（随机延迟某些包）。
      reorder_buffer_ms: float
          重排序缓冲窗口（毫秒）。

    传感器层故障：
      dvl_freeze_enabled: bool
          DVL 冻结故障（模拟进水）。
      dvl_freeze_after_s: float
          在仿真开始 N 秒后触发冻结。

      imu_drift_enabled: bool
          IMU 陀螺仪漂移（模拟陀螺仪偏置温漂）。
      imu_drift_rate_deg_per_s: float
          漂移速率（度/秒）。例如 0.5 表示每秒航向误差增加 0.5°。

      depth_spike_enabled: bool
          深度传感器尖峰故障（模拟气泡、声速异常）。
      depth_spike_m: float
          尖峰大小（米）。例如 5.0 表示深度读数会增加 5 米。
      depth_spike_after_s: float
          触发时间（秒）。

      mag_saturation_enabled: bool
          磁力计饱和（模拟强磁场干扰、内部磁体失效）。
      mag_saturation_threshold_t: float
          饱和阈值（特斯拉）。所有分量将被限制在 [-threshold, +threshold]。

    上行链路故障：
      uplink_dropout_enabled: bool
          周期性上行中断（模拟上位机与 AUV 的通信丢失）。
      uplink_dropout_on_pct: float [0.0-1.0]
          周期中处于 "中断" 状态的百分比。例如 0.8 表示 80% 的时间无通信。
      uplink_dropout_period_s: float
          周期长度（秒）。例如 10.0 与 uplink_dropout_on_pct=0.8 表示
          每 10 秒中，前 8 秒中断，后 2 秒恢复。
    """

    # 主开关
    enabled: bool = False

    # ────────────────────────────────────────
    # 传输层故障
    # ────────────────────────────────────────
    packet_loss_pct: float = 0.0              # [0.0, 1.0]
    reorder_enabled: bool = False
    reorder_buffer_ms: float = 50.0

    # ────────────────────────────────────────
    # 传感器层故障
    # ────────────────────────────────────────
    dvl_freeze_enabled: bool = False
    dvl_freeze_after_s: float = 30.0

    imu_drift_enabled: bool = False
    imu_drift_rate_deg_per_s: float = 0.5

    depth_spike_enabled: bool = False
    depth_spike_m: float = 5.0
    depth_spike_after_s: float = 60.0

    mag_saturation_enabled: bool = False
    mag_saturation_threshold_t: float = 50000.0

    # ────────────────────────────────────────
    # 上行链路故障
    # ────────────────────────────────────────
    uplink_dropout_enabled: bool = False
    uplink_dropout_on_pct: float = 0.8
    uplink_dropout_period_s: float = 10.0


class ChaosInjector:
    """
    有状态的故障注入器 - 根据 ChaosProfile 实时注入故障。

    工作流程：
      1. 在 MockAmdUdpServer 初始化时创建 ChaosInjector 实例
      2. 在 _build_uplink_packet() 中调用 apply_to_sensors()
         将传感器故障应用于当前快照
      3. 在 _poll_command_packet() 或 run_forever() 中调用
         should_drop_uplink() 和 should_lose_packet() 决定是否丢弃包

    状态：
      本注入器维护累积状态（如 DVL 冻结值、IMU 漂移累积、深度尖峰标志），
      因此是有状态的。若需重置实验，调用 reset() 方法。

    参数：
      profile: ChaosProfile
          故障配置对象。
      start_time: float
          起始时刻（秒），通常为 0.0 或 time.time()。
          用于计算 elapsed_s = t - start_time。
      _rng: random.Random or None
          随机数生成器（单元测试用）。
    """

    def __init__(
        self,
        profile: ChaosProfile,
        start_time: float = 0.0,
        *,
        _rng: random.Random | None = None,
    ) -> None:
        """初始化故障注入器。"""
        self._profile = profile
        self._start_time = start_time
        self._rng = _rng or random.Random()

        # ────────────────────────────────────────
        # 有状态的故障累积变量
        # ────────────────────────────────────────

        # DVL 冻结：一旦被触发，冻结值保存在此
        self._dvl_frozen: dict | None = None

        # IMU 漂移：累积的漂移角度（度）
        self._imu_drift_accum: float = 0.0

        # 深度尖峰：标志位和地层值
        self._depth_spike_applied: bool = False
        self._depth_spike_offset: float = 0.0
        self._depth_spike_reset_elapsed: float | None = None

    # ────────────────────────────────────────────────────────────────
    # 公共 API：传感器级故障注入
    # ────────────────────────────────────────────────────────────────

    def apply_to_sensors(
        self,
        snapshot: SensorSnapshot,
        elapsed_s: float,
    ) -> SensorSnapshot:
        """
        为传感器快照应用所有故障，返回新快照（原快照不变）。

        应用顺序（重要！影响最终结果）：
          1. DVL 冻结（速度变常数）
          2. IMU 漂移（航向线性增长）
          3. 深度尖峰（深度增加固定值）
          4. 磁力计饱和（磁场分量限幅）

        参数：
          snapshot: 原始快照（不被修改）
          elapsed_s: 仿真开始以来的经过时间（秒）

        返回值：
          新的 SensorSnapshot，包含应用后的故障数据
        """
        if not self._profile.enabled:
            return snapshot

        result = snapshot.copy()

        result = self._apply_dvl_freeze(result, elapsed_s)
        result = self._apply_imu_drift(result, elapsed_s)
        result = self._apply_depth_spike(result, elapsed_s)
        result = self._apply_mag_saturation(result)

        return result

    # ────────────────────────────────────────────────────────────────
    # 公共 API：上行链路层决策
    # ────────────────────────────────────────────────────────────────

    def should_drop_uplink(self, elapsed_s: float) -> bool:
        """
        判断当前上行帧是否应被丢弃（模拟与上位机通信中断）。

        返回 True 时，整个上行包被舍弃，上位机无法接收此帧遥测。

        参数：
          elapsed_s: 仿真开始以来的经过时间（秒）

        返回值：
          True: 应丢弃此帧
          False: 正常发送
        """
        if not self._profile.enabled:
            return False
        p = self._profile
        if not p.uplink_dropout_enabled:
            return False
        if p.uplink_dropout_period_s <= 0:
            return False
        # 计算周期内的相位 [0, 1)
        phase = (elapsed_s % p.uplink_dropout_period_s) / p.uplink_dropout_period_s
        # 若相位在前 uplink_dropout_on_pct% 则丢弃
        return phase < p.uplink_dropout_on_pct

    def should_lose_packet(self) -> bool:
        """
        随机判断下行命令包是否应被丢弃。

        返回 True 的概率为 packet_loss_pct%。

        返回值：
          True: 应丢弃此包（AUV 无法接收命令）
          False: 正常处理
        """
        if not self._profile.enabled:
            return False
        pct = clamp(self._profile.packet_loss_pct, 0.0, 1.0)
        return self._rng.random() < pct

    def should_reorder(self, elapsed_s: float) -> bool:
        """
        判断当前帧是否应被延迟（重排序）。

        返回 True 时，此帧会在延迟队列中滞留，可能被后续帧超越。

        返回值：
          True: 此帧应延迟
          False: 此帧立即处理
        """
        if not self._profile.enabled:
            return False
        if not self._profile.reorder_enabled:
            return False
        # 大约 5% 的概率
        return self._rng.random() < 0.05

    # ────────────────────────────────────────────────────────────────
    # 公共 API：重置
    # ────────────────────────────────────────────────────────────────

    def reset(self, elapsed_s: float | None = None) -> None:
        """
        清空所有累积状态，为新实验做准备。

        参数：
          elapsed_s: 重置时的经过时间。若提供，深度尖峰会在此之后的
                     depth_spike_after_s 秒才重新触发。
        """
        self._dvl_frozen = None
        self._imu_drift_accum = 0.0
        self._depth_spike_applied = False
        self._depth_spike_offset = 0.0
        self._depth_spike_reset_elapsed = elapsed_s

    # ────────────────────────────────────────────────────────────────
    # 私有 API：单个故障注入函数
    # ────────────────────────────────────────────────────────────────

    def _apply_dvl_freeze(self, snap: SensorSnapshot, elapsed_s: float) -> SensorSnapshot:
        """
        DVL 冻结：一旦被触发，速度值固定在被冻结时的值。

        模拟场景：进水导致 DVL 无法更新。
        """
        p = self._profile
        if not p.dvl_freeze_enabled:
            return snap
        if elapsed_s < p.dvl_freeze_after_s:
            return snap
        # 冻结：第一次超过触发时间时，记下当前值
        if self._dvl_frozen is None and snap.dvl is not None:
            self._dvl_frozen = dict(snap.dvl)  # 浅拷贝足够
        if self._dvl_frozen is not None and snap.dvl is not None:
            snap.dvl = dict(self._dvl_frozen)
        return snap

    def _apply_imu_drift(self, snap: SensorSnapshot, elapsed_s: float) -> SensorSnapshot:
        """
        IMU 漂移：航向值随时间线性增长。

        模拟场景：陀螺仪偏置温漂，初始对准后逐渐发散。
        """
        p = self._profile
        if not p.imu_drift_enabled:
            return snap
        if snap.imu is None:
            return snap
        # 累积漂移 = 经过时间 × 漂移速率
        drift = elapsed_s * p.imu_drift_rate_deg_per_s
        snap.imu = dict(snap.imu)  # 拷贝以避免修改输入
        snap.imu["heading_deg"] = (snap.imu.get("heading_deg", 0.0) + drift) % 360.0
        return snap

    def _apply_depth_spike(self, snap: SensorSnapshot, elapsed_s: float) -> SensorSnapshot:
        """
        深度尖峰：一旦被触发，深度值持续增加固定量。

        模拟场景：气泡进入传感器膜盒 / 水温变化导致声速计算误差。
        """
        p = self._profile
        if not p.depth_spike_enabled:
            return snap
        # 重置后，需等待新的触发时间
        if self._depth_spike_reset_elapsed is not None:
            reset_at = self._depth_spike_reset_elapsed
            self._depth_spike_reset_elapsed = None
            if elapsed_s - reset_at < max(p.depth_spike_after_s, 1e-6):
                return snap
        if elapsed_s < p.depth_spike_after_s:
            return snap
        # 第一次超过后，标记为已应用
        if not self._depth_spike_applied:
            self._depth_spike_offset = p.depth_spike_m
            self._depth_spike_applied = True
        if snap.depth is not None:
            snap.depth = dict(snap.depth)  # 拷贝
            snap.depth["depth_m"] = snap.depth.get("depth_m", 0.0) + self._depth_spike_offset
        return snap

    def _apply_mag_saturation(self, snap: SensorSnapshot) -> SensorSnapshot:
        """
        磁力计饱和：限幅磁场分量。

        模拟场景：强外磁场（如船舶结构、陆基磁暴）干扰地磁罗盘。
        """
        p = self._profile
        if not p.mag_saturation_enabled:
            return snap
        if snap.mag is None:
            return snap
        threshold = p.mag_saturation_threshold_t
        snap.mag = dict(snap.mag)  # 拷贝顶层
        b_ned = list(snap.mag.get("B_ned", [0.0, 0.0, 0.0]))
        snap.mag["B_ned"] = [clamp(v, -threshold, threshold) for v in b_ned]
        return snap


"""
传输层延迟队列 - 模拟 UDP 延迟和抖动。

作用：
  在网络测试中，水下通信通常面临固有延迟（声学传播、设备处理）和变动性
  抖动（多路径、干扰）。此模块在应用层注入这些延迟效应，而无需实际改动
  网络栈。

特点：
  1. 基于 FIFO 的数据包队列（保证顺序）
  2. 每收一个包，分配 release_ts = recv_ts + base_delay + jitter
  3. 仅当 release_ts <= now 时包才被取出
  4. 队列满时，自动淘汰最旧的包（确保新鲜数据优先）
  5. 纯标准库实现，无依赖

应用场景：
  - 水下通信（固有声学延迟 ~1-20ms）
  - 跨地域通信（星链延迟 ~100ms）
  - 网络故障恢复测试
"""

from __future__ import annotations

import random
from collections import deque
from dataclasses import dataclass
from typing import Any


@dataclass
class _QueuedPacket:
    """
    内部队列项 - 存储排队等待中的数据包。

    属性：
      packet: 原始数据包（bytes 或其他序列化对象）
      recv_ts: 接收时刻（秒）
      release_ts: 应释放的时刻（秒）= recv_ts + 延迟 + 抖动
    """

    packet: Any
    recv_ts: float
    release_ts: float


class TransportDelayQueue:
    """
    FIFO 延迟队列 - 模拟 UDP 传输延迟和抖动。

    工作原理：
      每个入队的数据包被分配一个释放时刻：
        release_ts = recv_ts + base_delay_ms/1000 + uniform(-jitter_ms, +jitter_ms)/1000

      队列保证：
        1. 顺序性：出队时总是按入队顺序（先进先出）
        2. 及时性：仅返回 release_ts <= now 的包
        3. 有界性：当队列满时，最旧的包被静默丢弃（模拟缓冲溢出）

    参数：
      base_delay_ms: 基础延迟（毫秒）
                   对所有包均匀应用
      jitter_ms: 抖动范围（毫秒）
                 每包的额外延迟从 [-jitter_ms, +jitter_ms] 均匀分布
                 总延迟 ~ [base_delay - jitter, base_delay + jitter]
      max_queue_depth: 最大缓存包数
                      超过此数时，最早入队的包被丢弃
      _rng: 随机数生成器（用于单元测试的可控性）

    示例：
      # 模拟 20ms 基础延迟和 5ms 抖动的水下通信
      queue = TransportDelayQueue(base_delay_ms=20.0, jitter_ms=5.0)

      # 在循环中：
      queue.enqueue(packet, time.time())  # 入队
      ready = queue.dequeue(time.time())   # 取出所有已就绪的包
      for pkt, ts in ready:
          process(pkt)
    """

    def __init__(
        self,
        base_delay_ms: float = 20.0,
        jitter_ms: float = 5.0,
        max_queue_depth: int = 64,
        *,
        _rng: random.Random | None = None,
    ) -> None:
        """
        初始化延迟队列。

        参数：
          base_delay_ms: 基础延迟（毫秒），最小 0
          jitter_ms: 抖动范围（毫秒），最小 0
          max_queue_depth: 最大队列深度，最小 1
          _rng: 随机数生成器（测试用）
        """
        self._base_delay_s = max(0.0, base_delay_ms) / 1000.0
        self._jitter_s = max(0.0, jitter_ms) / 1000.0
        self._max_depth = max(1, int(max_queue_depth))
        # deque 具有自动淘汰最旧项的特性（maxlen）
        self._queue: deque[_QueuedPacket] = deque(maxlen=self._max_depth)
        self._rng = _rng or random.Random()

    # ────────────────────────────────────────────────────────────────
    # 公共 API
    # ────────────────────────────────────────────────────────────────

    def enqueue(self, packet: Any, recv_ts: float) -> None:
        """
        将数据包加入队列，分配释放时刻。

        若队列已满（_max_depth），最旧的项自动被淘汰，新包被添加。

        参数：
          packet: 数据包对象（通常是 bytes）
          recv_ts: 接收时刻（秒）
        """
        # 生成随机抖动（在 [-jitter_s, +jitter_s] 范围内）
        jitter = self._rng.uniform(-self._jitter_s, self._jitter_s) if self._jitter_s > 0 else 0.0
        release_ts = recv_ts + self._base_delay_s + jitter
        entry = _QueuedPacket(packet=packet, recv_ts=recv_ts, release_ts=release_ts)
        # deque.append() 在队列满时自动 popleft()
        self._queue.append(entry)

    def dequeue(self, now: float) -> list[tuple[Any, float]]:
        """
        取出所有已就绪的数据包（release_ts <= now）。

        返回值为列表，包含所有已就绪包的 (packet, recv_ts) 元组，
        按入队顺序排列。未就绪的包留在队列中。

        参数：
          now: 当前时刻（秒）

        返回值：
          列表，每项为 (packet, recv_ts) 元组
          若无就绪包，返回空列表 []
        """
        ready: list[tuple[bytes, float]] = []
        while self._queue and self._queue[0].release_ts <= now:
            entry = self._queue.popleft()
            ready.append((entry.packet, entry.recv_ts))
        return ready

    def peek_count(self) -> int:
        """返回当前队列中等待的包数。"""
        return len(self._queue)

    def reset(self) -> None:
        """清空队列中的所有待处理包。用于实验重启或故障恢复。"""
        self._queue.clear()

    def __repr__(self) -> str:
        """调试表示，显示配置和当前待处理包数。"""
        return (
            f"TransportDelayQueue(base_delay_ms={self._base_delay_s * 1000:.1f}, "
            f"jitter_ms={self._jitter_s * 1000:.1f}, "
            f"pending={self.peek_count()})"
        )


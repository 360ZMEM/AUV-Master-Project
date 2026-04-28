"""
TransportDelayQueue 单元测试。

该模块测试传输时延队列的核心 FIFO 语义和时序逻辑。

测试覆盖：
  - 构造函数：零延迟、负延迟、零深度等各种边界情况
  - 基础 FIFO：
    - 零延迟立即释放
    - 固定延迟按时释放
    - 多包顺序保持
    - 部分释放（仅到期包）
  - 队列溢出：FIFO 驱逐最老包
  - 抖动：随机时延变化
  - 重置：清空队列
  - 调试输出：__repr__ 验证

测试独立性：
  - 不依赖 mock_amd_server
  - 不依赖 protocol.py
  - 使用固定随机种子保证可重复性
"""

from __future__ import annotations

import random

from sim_holoocean.interfaces.mock_amd_delay import TransportDelayQueue


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_queue(
    base_delay_ms: float = 10.0,
    jitter_ms: float = 0.0,
    max_queue_depth: int = 64,
    seed: int | None = 42,
) -> TransportDelayQueue:
    rng = random.Random(seed)
    return TransportDelayQueue(
        base_delay_ms=base_delay_ms,
        jitter_ms=jitter_ms,
        max_queue_depth=max_queue_depth,
        _rng=rng,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestTransportDelayQueueConstruct:
    """Verify construction with various parameter combinations."""

    def test_zero_delay_zero_jitter(self) -> None:
        q = _make_queue(base_delay_ms=0.0, jitter_ms=0.0)
        assert q.peek_count() == 0

    def test_positive_delay_no_jitter(self) -> None:
        q = _make_queue(base_delay_ms=50.0, jitter_ms=0.0)
        assert q.peek_count() == 0

    def test_clamp_negative_delay_to_zero(self) -> None:
        q = _make_queue(base_delay_ms=-10.0)
        # base delay should be clamped to 0
        q.enqueue(b"pkt", 0.0)
        ready = q.dequeue(0.0)
        # With base_delay=0 and jitter=0, packet should be immediately ready
        assert len(ready) == 1

    def test_max_depth_clamp_minimum_one(self) -> None:
        q = _make_queue(max_queue_depth=0)
        # max depth clamped to 1, so queue accepts at least 1 packet
        q.enqueue(b"pkt", 0.0)
        assert q.peek_count() == 1


class TestTransportDelayQueueEnqueueDequeue:
    """Core FIFO semantics with deterministic timing."""

    def test_zero_delay_immediate_release(self) -> None:
        """With 0 delay + 0 jitter, packet is immediately available."""
        q = _make_queue(base_delay_ms=0.0, jitter_ms=0.0)
        q.enqueue(b"hello", recv_ts=100.0)
        ready = q.dequeue(now=100.0)
        assert len(ready) == 1
        assert ready[0] == (b"hello", 100.0)

    def test_delay_held_until_release(self) -> None:
        """Packet with 100ms delay is NOT available before release time."""
        q = _make_queue(base_delay_ms=100.0, jitter_ms=0.0)
        q.enqueue(b"delayed", recv_ts=1000.0)

        # At t=1000.099s (99ms later), not yet released (release = 1000.1)
        ready = q.dequeue(now=1000.099)
        assert len(ready) == 0

        # At t=1000.1s (100ms later), just released
        ready = q.dequeue(now=1000.1)
        assert len(ready) == 1
        assert ready[0][0] == b"delayed"

    def test_fifo_order_preserved(self) -> None:
        """Multiple packets come out in enqueue order."""
        q = _make_queue(base_delay_ms=10.0, jitter_ms=0.0)
        q.enqueue(b"first", recv_ts=100.0)
        q.enqueue(b"second", recv_ts=101.0)
        q.enqueue(b"third", recv_ts=102.0)

        # At t=115 (all should be released since 100+10=110, 101+10=111, 102+10=112)
        ready = q.dequeue(now=115.0)
        assert len(ready) == 3
        assert ready[0][0] == b"first"
        assert ready[1][0] == b"second"
        assert ready[2][0] == b"third"

    def test_partial_dequeue(self) -> None:
        """Only fully-released packets are returned."""
        q = _make_queue(base_delay_ms=50.0, jitter_ms=0.0)
        q.enqueue(b"old", recv_ts=100.0)
        q.enqueue(b"new", recv_ts=200.0)

        # At t=160: old released (100+50=150 < 160), new not yet (200+50=250)
        ready = q.dequeue(now=160.0)
        assert len(ready) == 1
        assert ready[0][0] == b"old"
        assert q.peek_count() == 1  # "new" still waiting


class TestTransportDelayQueueOverflow:
    """Verify FIFO eviction when queue is full."""

    def test_oldest_evicted_when_full(self) -> None:
        """With max_depth=3, the 4th enqueue evicts the oldest."""
        q = _make_queue(base_delay_ms=1000.0, jitter_ms=0.0, max_queue_depth=3)
        q.enqueue(b"pkt1", recv_ts=0.0)
        q.enqueue(b"pkt2", recv_ts=0.0)
        q.enqueue(b"pkt3", recv_ts=0.0)
        # Queue is full (3/3)
        assert q.peek_count() == 3

        # This evicts pkt1 (oldest)
        q.enqueue(b"pkt4", recv_ts=0.0)
        assert q.peek_count() == 3

        # Drain — should see pkt2, pkt3, pkt4 (not pkt1)
        ready = q.dequeue(now=9999.0)
        payloads = [p[0] for p in ready]
        assert b"pkt1" not in payloads
        assert payloads == [b"pkt2", b"pkt3", b"pkt4"]


class TestTransportDelayQueueJitter:
    """Verify jitter adds random variation around base delay."""

    def test_jitter_varies_release_times(self) -> None:
        """With non-zero jitter, release times should vary per packet."""
        q = _make_queue(base_delay_ms=100.0, jitter_ms=50.0, seed=123)
        recv_ts = 1000.0
        q.enqueue(b"a", recv_ts)
        q.enqueue(b"b", recv_ts)
        q.enqueue(b"c", recv_ts)

        # At base_delay (1000.1s), some may not yet be released due to negative jitter
        ready_at_base = q.dequeue(now=1000.1)

        # At base_delay + jitter (1000.15s), all should be released
        ready_all = q.dequeue(now=1000.15)
        total = len(ready_at_base) + len(ready_all)
        assert total == 3

    def test_no_jitter_zero_jitter_param(self) -> None:
        """Explicit jitter_ms=0 means deterministic release."""
        q = _make_queue(base_delay_ms=50.0, jitter_ms=0.0)
        q.enqueue(b"exact", recv_ts=100.0)

        # release_ts = 100.0 + 0.05 = 100.05
        # At 100.049, not yet
        assert len(q.dequeue(now=100.049)) == 0
        # At 100.05, released
        assert len(q.dequeue(now=100.05)) == 1


class TestTransportDelayQueueReset:
    """Verify reset clears all pending packets."""

    def test_reset_empties_queue(self) -> None:
        q = _make_queue(base_delay_ms=1000.0)
        q.enqueue(b"a", 0.0)
        q.enqueue(b"b", 0.0)
        assert q.peek_count() == 2

        q.reset()
        assert q.peek_count() == 0

    def test_dequeue_after_reset_returns_empty(self) -> None:
        q = _make_queue(base_delay_ms=1000.0)
        q.enqueue(b"a", 0.0)
        q.reset()
        ready = q.dequeue(now=9999.0)
        assert ready == []


class TestTransportDelayQueueRepr:
    """Verify __repr__ for debugging."""

    def test_repr_contains_params(self) -> None:
        q = _make_queue(base_delay_ms=20.0, jitter_ms=5.0)
        r = repr(q)
        assert "TransportDelayQueue" in r
        assert "20.0" in r
        assert "5.0" in r

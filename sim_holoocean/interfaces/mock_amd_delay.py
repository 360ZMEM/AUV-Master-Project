"""Transport delay queue for simulating UDP latency and jitter.

Pure-stdlib module with no external dependencies.  FIFO semantics ensure
packet ordering is preserved within the configured jitter window.
"""

from __future__ import annotations

import random
from collections import deque
from dataclasses import dataclass
from typing import Any


@dataclass
class _QueuedPacket:
    """Internal entry in the delay queue."""

    packet: Any
    recv_ts: float
    release_ts: float


class TransportDelayQueue:
    """FIFO delay queue that simulates UDP transport latency and jitter.

    Each enqueued packet is assigned a *release timestamp* equal to::

        recv_ts + base_delay_ms / 1000 + uniform(-jitter_ms, +jitter_ms) / 1000

    The queue guarantees in-order delivery: :meth:`dequeue` only returns
    packets whose release time has passed, in the order they were enqueued.

    When the queue is full the *oldest* packet is silently dropped so that
    the newest data (most relevant to the controller) survives.
    """

    def __init__(
        self,
        base_delay_ms: float = 20.0,
        jitter_ms: float = 5.0,
        max_queue_depth: int = 64,
        *,
        _rng: random.Random | None = None,
    ) -> None:
        self._base_delay_s = max(0.0, base_delay_ms) / 1000.0
        self._jitter_s = max(0.0, jitter_ms) / 1000.0
        self._max_depth = max(1, int(max_queue_depth))
        self._queue: deque[_QueuedPacket] = deque(maxlen=self._max_depth)
        self._rng = _rng or random.Random()

    # -- public API --------------------------------------------------------

    def enqueue(self, packet: Any, recv_ts: float) -> None:
        """Place *packet* into the queue with a computed release time.

        If the queue is already at *max_queue_depth*, the oldest entry is
        evicted (FIFO discard) before the new one is appended.
        """
        jitter = self._rng.uniform(-self._jitter_s, self._jitter_s) if self._jitter_s > 0 else 0.0
        release_ts = recv_ts + self._base_delay_s + jitter
        entry = _QueuedPacket(packet=packet, recv_ts=recv_ts, release_ts=release_ts)
        # deque with maxlen auto-evicts the oldest when full
        self._queue.append(entry)

    def dequeue(self, now: float) -> list[tuple[Any, float]]:
        """Return all packets whose release time ≤ *now*.

        Returns a list of ``(packet, recv_ts)`` tuples in enqueue order.
        Packets that have not yet reached their release time remain in the
        queue for a future call.
        """
        ready: list[tuple[bytes, float]] = []
        while self._queue and self._queue[0].release_ts <= now:
            entry = self._queue.popleft()
            ready.append((entry.packet, entry.recv_ts))
        return ready

    def peek_count(self) -> int:
        """Number of packets currently waiting in the queue."""
        return len(self._queue)

    def reset(self) -> None:
        """Clear all pending packets."""
        self._queue.clear()

    # -- repr ---------------------------------------------------------------

    def __repr__(self) -> str:
        return (
            f"TransportDelayQueue(base_delay_ms={self._base_delay_s * 1000:.1f}, "
            f"jitter_ms={self._jitter_s * 1000:.1f}, "
            f"pending={self.peek_count()})"
        )

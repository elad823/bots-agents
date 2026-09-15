from __future__ import annotations

import asyncio
import time

try:
    import pytest
except ImportError:
    class _MockMark:
        @staticmethod
        def asyncio(fn):
            return fn
    class _MockPytest:
        mark = _MockMark()
    pytest = _MockPytest()


from backend.core.rate_limiter import SlidingWindowRateLimiter


@pytest.mark.asyncio
async def test_rate_limiter_immediate_acquire() -> None:
    """Test that requests within max_rpm acquire immediately with zero wait."""
    limiter = SlidingWindowRateLimiter(max_rpm=5, window_seconds=2)
    limiter.reset()

    for i in range(5):
        waited = await limiter.acquire(caller_id=f"test_{i}")
        assert waited == 0.0

    status = limiter.get_status()
    assert status["current_window_requests"] == 5
    assert status["remaining_slots"] == 0
    assert status["is_cooling_down"] is True


@pytest.mark.asyncio
async def test_rate_limiter_throttles_when_saturated() -> None:
    """Test that when window is saturated, the 6th call waits until the oldest expires."""
    # Use a small window for fast unit testing (0.5s window)
    limiter = SlidingWindowRateLimiter(max_rpm=2, window_seconds=1)
    limiter.reset()

    # Consume 2 slots
    await limiter.acquire("caller_1")
    await limiter.acquire("caller_2")

    start = time.monotonic()
    # 3rd request should be throttled
    waited = await limiter.acquire("caller_3")
    elapsed = time.monotonic() - start

    assert waited > 0.0
    assert elapsed >= 0.8  # Must wait for window to clear
    assert limiter.get_status()["current_window_requests"] <= 2


@pytest.mark.asyncio
async def test_rate_limiter_concurrent_burst() -> None:
    """Test concurrent coroutines vying for rate-limited slots."""
    limiter = SlidingWindowRateLimiter(max_rpm=3, window_seconds=1)
    limiter.reset()

    async def worker(idx: int) -> float:
        return await limiter.acquire(f"worker_{idx}")

    # Launch 6 workers concurrently
    results = await asyncio.gather(*(worker(i) for i in range(6)))
    assert len(results) == 6
    # First 3 workers acquire immediately (waited == 0)
    assert sum(1 for w in results if w == 0.0) == 3
    # Remaining 3 workers had to wait
    assert sum(1 for w in results if w > 0.0) == 3

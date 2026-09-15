from __future__ import annotations

import asyncio
import collections
import time
from typing import Any, Deque
import logging

from backend.core.config import settings

logger = logging.getLogger("mas.rate_limiter")


class SlidingWindowRateLimiter:
    """Thread-safe asynchronous sliding-window rate limiter for Gemini 15 RPM compliance.

    Guarantees outbound API calls never exceed max_rpm (default 14 requests)
    within any rolling 60-second window.
    """

    def __init__(self, max_rpm: int | None = None, window_seconds: int | None = None) -> None:
        self.max_rpm: int = max_rpm or settings.max_rpm_limit
        self.window_seconds: int = window_seconds or settings.rate_limit_window_seconds
        self._timestamps: Deque[float] = collections.deque()
        self._lock: asyncio.Lock | None = None

    @property
    def lock(self) -> asyncio.Lock:
        """Lazily initialize the asyncio.Lock within the active event loop."""
        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            current_loop = None

        lock_loop = getattr(self._lock, "_loop", None)
        if self._lock is None or (
            current_loop is not None
            and lock_loop is not None
            and (lock_loop is not current_loop or lock_loop.is_closed())
        ):
            self._lock = asyncio.Lock()
        return self._lock

    def _purge_expired(self, current_time: float) -> None:
        """Evict timestamps older than the sliding window."""
        threshold = current_time - self.window_seconds
        while self._timestamps and self._timestamps[0] <= threshold:
            self._timestamps.popleft()

    async def acquire(self, caller_id: str = "anonymous") -> float:
        """Acquire permission to make an LLM call.

        If the rate limit window is full, asynchronously sleeps until a slot opens.
        Returns the duration waited in seconds (0.0 if slot was immediately available).
        """
        waited_seconds = 0.0

        while True:
            time_until_free = 0.0
            async with self.lock:
                now = time.monotonic()
                self._purge_expired(now)

                if len(self._timestamps) < self.max_rpm:
                    # Slot available immediately
                    self._timestamps.append(now)
                    logger.debug(
                        "RateLimiter slot granted for '%s'. In-flight window: %d/%d",
                        caller_id,
                        len(self._timestamps),
                        self.max_rpm,
                    )
                    return waited_seconds

                # Window is saturated. Compute wait duration until oldest timestamp expires.
                oldest_timestamp = self._timestamps[0]
                time_until_free = (oldest_timestamp + self.window_seconds) - now + 0.05
                if time_until_free <= 0:
                    time_until_free = 0.05

                logger.warning(
                    "RateLimiter saturated (%d/%d for caller '%s'). Queuing for %.2fs...",
                    len(self._timestamps),
                    self.max_rpm,
                    caller_id,
                    time_until_free,
                )

            # Lock is released while sleeping so other callers can queue concurrently
            await asyncio.sleep(time_until_free)
            waited_seconds += time_until_free


    def get_status(self) -> dict[str, Any]:
        """Return real-time diagnostic status for the UI dashboard."""
        now = time.monotonic()
        self._purge_expired(now)
        current_count = len(self._timestamps)
        remaining = max(0, self.max_rpm - current_count)
        return {
            "current_window_requests": current_count,
            "max_rpm": self.max_rpm,
            "remaining_slots": remaining,
            "window_seconds": self.window_seconds,
            "is_cooling_down": current_count >= self.max_rpm,
        }

    def reset(self) -> None:
        """Reset internal queue state (primarily for test fixture isolation)."""
        self._timestamps.clear()
        self._lock = None


# Global Singleton Rate Limiter
rate_limiter = SlidingWindowRateLimiter()

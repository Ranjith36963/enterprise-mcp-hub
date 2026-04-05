"""Tests for async rate limiter.

Covers: concurrent limit enforcement, delay between requests,
acquire/release cycle, and async context manager usage.
"""

import asyncio
import time

import pytest

from src.utils.rate_limiter import RateLimiter


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


class TestRateLimiter:

    def test_acquire_release_cycle(self):
        """Basic acquire → release cycle completes without error."""
        limiter = RateLimiter(concurrent=2, delay=0.01)

        async def _test():
            await limiter.acquire()
            limiter.release()

        _run(_test())

    def test_concurrent_limit_respected(self):
        """Only N tasks can hold the limiter concurrently."""
        limiter = RateLimiter(concurrent=2, delay=0.01)
        active = []
        max_active = [0]

        async def _task(task_id):
            await limiter.acquire()
            active.append(task_id)
            max_active[0] = max(max_active[0], len(active))
            await asyncio.sleep(0.05)
            active.remove(task_id)
            limiter.release()

        async def _test():
            await asyncio.gather(*[_task(i) for i in range(5)])

        _run(_test())
        assert max_active[0] <= 2, f"Max concurrent was {max_active[0]}, expected ≤ 2"

    def test_delay_enforced(self):
        """Each acquire sleeps for the configured delay."""
        limiter = RateLimiter(concurrent=5, delay=0.1)

        async def _test():
            t0 = time.monotonic()
            await limiter.acquire()
            elapsed = time.monotonic() - t0
            limiter.release()
            return elapsed

        elapsed = _run(_test())
        assert elapsed >= 0.08, f"Delay was {elapsed:.3f}s, expected ≥ 0.08s"

    def test_context_manager(self):
        """Async context manager acquire/release works."""
        limiter = RateLimiter(concurrent=1, delay=0.01)

        async def _test():
            async with limiter:
                pass  # Should acquire and release cleanly
            # After exit, another acquire should work immediately
            async with limiter:
                pass

        _run(_test())

    def test_zero_delay(self):
        """Delay=0 means no waiting between acquires."""
        limiter = RateLimiter(concurrent=10, delay=0.0)

        async def _test():
            t0 = time.monotonic()
            for _ in range(5):
                await limiter.acquire()
                limiter.release()
            elapsed = time.monotonic() - t0
            return elapsed

        elapsed = _run(_test())
        assert elapsed < 0.5, f"Zero-delay took {elapsed:.3f}s, expected < 0.5s"

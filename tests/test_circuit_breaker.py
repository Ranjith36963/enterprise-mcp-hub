"""Tests for persistent circuit breaker + source health.

Covers: safe_fetch() tripping, reset, exponential backoff (1hr/6hr/24hr),
load_source_health(), and DB persistence via record_source_failure/success.
"""

import asyncio
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.models import Job
from src.sources.base import (
    BaseJobSource,
    _circuit_breaker,
    _CIRCUIT_BREAKER_THRESHOLD,
    _source_health,
    load_source_health,
)
from src.storage.database import JobDatabase


# ── Helpers ───────────────────────────────────────────────────────────


class _DummySource(BaseJobSource):
    """Concrete subclass for testing safe_fetch() without real HTTP."""
    name = "dummy_test"

    async def fetch_jobs(self) -> list[Job]:
        raise NotImplementedError("Override in test")


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


@pytest.fixture(autouse=True)
def _clear_circuit_breaker():
    """Reset module-level circuit breaker state between tests."""
    _circuit_breaker.clear()
    _source_health.clear()
    yield
    _circuit_breaker.clear()
    _source_health.clear()


@pytest.fixture
def dummy_source():
    session = MagicMock()
    return _DummySource(session, search_config=None)


@pytest.fixture
def db():
    database = JobDatabase(":memory:")
    _run(database.init_db())
    yield database
    _run(database.close())


# ── Tests ─────────────────────────────────────────────────────────────


class TestCircuitBreaker:

    def test_safe_fetch_trips_after_3_failures(self, dummy_source):
        """After 3 consecutive failures, safe_fetch returns [] without calling fetch_jobs."""
        dummy_source.fetch_jobs = AsyncMock(side_effect=Exception("Network error"))

        for _ in range(_CIRCUIT_BREAKER_THRESHOLD):
            result = _run(dummy_source.safe_fetch())
            assert result == []

        # 4th call — circuit is open, fetch_jobs should NOT be called again
        dummy_source.fetch_jobs = AsyncMock(return_value=[])
        result = _run(dummy_source.safe_fetch())
        assert result == []
        dummy_source.fetch_jobs.assert_not_called()

    def test_safe_fetch_resets_on_success(self, dummy_source):
        """After 2 failures + 1 success, counter resets; source isn't blocked."""
        dummy_source.fetch_jobs = AsyncMock(side_effect=Exception("Timeout"))
        _run(dummy_source.safe_fetch())
        _run(dummy_source.safe_fetch())
        assert _circuit_breaker.get("dummy_test", 0) == 2

        # Succeed — counter should reset
        dummy_source.fetch_jobs = AsyncMock(return_value=[])
        result = _run(dummy_source.safe_fetch())
        assert result == []
        assert _circuit_breaker.get("dummy_test", 0) == 0

        # Should still be able to fetch after reset
        dummy_source.fetch_jobs = AsyncMock(return_value=[])
        result = _run(dummy_source.safe_fetch())
        assert result == []

    def test_record_source_failure_increments_db(self, db):
        """record_source_failure increments consecutive_failures in DB."""
        _run(db.record_source_failure("test_src", "connection refused"))
        health = _run(db.get_source_health())
        assert health["test_src"]["consecutive_failures"] == 1

        _run(db.record_source_failure("test_src", "timeout"))
        health = _run(db.get_source_health())
        assert health["test_src"]["consecutive_failures"] == 2

    def test_record_source_success_resets_db(self, db):
        """record_source_success resets consecutive_failures to 0 and clears skip_until."""
        # First record failures
        for _ in range(4):
            _run(db.record_source_failure("test_src", "error"))
        health = _run(db.get_source_health())
        assert health["test_src"]["consecutive_failures"] == 4
        assert health["test_src"]["skip_until"] is not None

        # Success resets
        _run(db.record_source_success("test_src"))
        health = _run(db.get_source_health())
        assert health["test_src"]["consecutive_failures"] == 0
        assert health["test_src"]["skip_until"] is None

    def test_exponential_backoff_1hr(self, db):
        """3 failures → skip_until = now + ~1hr."""
        for _ in range(3):
            _run(db.record_source_failure("test_src", "error"))
        health = _run(db.get_source_health())
        skip = datetime.fromisoformat(health["test_src"]["skip_until"])
        now = datetime.now(timezone.utc)
        # skip_until should be roughly 1hr from now (within a few seconds)
        diff_minutes = (skip - now).total_seconds() / 60
        assert 55 <= diff_minutes <= 65

    def test_exponential_backoff_6hr(self, db):
        """5 failures → skip_until = now + ~6hr."""
        for _ in range(5):
            _run(db.record_source_failure("test_src", "error"))
        health = _run(db.get_source_health())
        skip = datetime.fromisoformat(health["test_src"]["skip_until"])
        now = datetime.now(timezone.utc)
        diff_hours = (skip - now).total_seconds() / 3600
        assert 5.5 <= diff_hours <= 6.5

    def test_exponential_backoff_24hr(self, db):
        """8 failures → skip_until = now + ~24hr."""
        for _ in range(8):
            _run(db.record_source_failure("test_src", "error"))
        health = _run(db.get_source_health())
        skip = datetime.fromisoformat(health["test_src"]["skip_until"])
        now = datetime.now(timezone.utc)
        diff_hours = (skip - now).total_seconds() / 3600
        assert 23 <= diff_hours <= 25

    def test_load_source_health_pre_skips(self, dummy_source):
        """load_source_health with active skip_until pre-opens circuit breaker."""
        future = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
        load_source_health({
            "dummy_test": {
                "consecutive_failures": 5,
                "skip_until": future,
            }
        })
        # Circuit should be pre-opened
        assert _circuit_breaker.get("dummy_test", 0) >= _CIRCUIT_BREAKER_THRESHOLD

        # safe_fetch should return [] without calling fetch_jobs
        dummy_source.fetch_jobs = AsyncMock(return_value=[])
        result = _run(dummy_source.safe_fetch())
        assert result == []

    def test_expired_cooldown_retries(self, dummy_source):
        """load_source_health with past skip_until resets breaker — source retries."""
        past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        load_source_health({
            "dummy_test": {
                "consecutive_failures": 5,
                "skip_until": past,
            }
        })
        # Circuit breaker should be reset (cooldown expired)
        assert _circuit_breaker.get("dummy_test", 0) == 0

        # safe_fetch should actually call fetch_jobs
        dummy_source.fetch_jobs = AsyncMock(return_value=[])
        result = _run(dummy_source.safe_fetch())
        assert result == []
        dummy_source.fetch_jobs.assert_called_once()

    def test_safe_fetch_persists_to_db(self, dummy_source, db):
        """When db is passed, safe_fetch persists success/failure to source_health table."""
        # Failure → DB updated
        dummy_source.fetch_jobs = AsyncMock(side_effect=Exception("error"))
        _run(dummy_source.safe_fetch(db=db))
        health = _run(db.get_source_health())
        assert health["dummy_test"]["consecutive_failures"] == 1

        # Success → DB reset
        dummy_source.fetch_jobs = AsyncMock(return_value=[])
        _run(dummy_source.safe_fetch(db=db))
        health = _run(db.get_source_health())
        assert health["dummy_test"]["consecutive_failures"] == 0

"""Tests for robots.txt compliance checker.

Covers: allowed/blocked URLs, missing robots.txt (fail-open),
domain-level caching, and network error handling.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.utils.robots_checker import fetch_robots, is_allowed, clear_cache, _cache


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


@pytest.fixture(autouse=True)
def _clear_robots_cache():
    """Clear robots.txt cache between tests."""
    clear_cache()
    yield
    clear_cache()


def _mock_session(status=200, text=""):
    """Create a mock aiohttp session returning a specific robots.txt response."""
    resp = AsyncMock()
    resp.status = status
    resp.text = AsyncMock(return_value=text)

    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=resp)
    ctx.__aexit__ = AsyncMock(return_value=False)

    session = MagicMock()
    session.get = MagicMock(return_value=ctx)
    return session


class TestRobotsChecker:

    def test_allowed_url_proceeds(self):
        """robots.txt explicitly allows path → is_allowed returns True."""
        robots_txt = "User-agent: *\nAllow: /jobs/"
        session = _mock_session(status=200, text=robots_txt)
        result = _run(is_allowed(session, "https://example.com/jobs/123", "Job360Bot"))
        assert result is True

    def test_blocked_url_returns_false(self):
        """robots.txt disallows path → is_allowed returns False."""
        robots_txt = "User-agent: *\nDisallow: /private/"
        session = _mock_session(status=200, text=robots_txt)
        result = _run(is_allowed(session, "https://example.com/private/data", "Job360Bot"))
        assert result is False

    def test_no_robots_txt_allows_all(self):
        """404 on robots.txt → fail-open, is_allowed returns True."""
        session = _mock_session(status=404, text="")
        result = _run(is_allowed(session, "https://example.com/anything", "Job360Bot"))
        assert result is True

    def test_cache_per_domain(self):
        """Robots.txt is fetched once per domain; second call uses cache."""
        robots_txt = "User-agent: *\nAllow: /"
        session = _mock_session(status=200, text=robots_txt)

        # First call — fetches
        _run(is_allowed(session, "https://example.com/page1", "Bot"))
        assert session.get.call_count == 1

        # Second call (same domain) — uses cache
        _run(is_allowed(session, "https://example.com/page2", "Bot"))
        assert session.get.call_count == 1  # No new fetch

    def test_network_error_allows(self):
        """Network error fetching robots.txt → fail-open (returns True)."""
        session = MagicMock()
        ctx = AsyncMock()
        ctx.__aenter__ = AsyncMock(side_effect=Exception("Connection refused"))
        ctx.__aexit__ = AsyncMock(return_value=False)
        session.get = MagicMock(return_value=ctx)

        result = _run(is_allowed(session, "https://down.example.com/path", "Bot"))
        assert result is True
        # Should also cache the failure (None entry)
        assert "https://down.example.com" in _cache
        assert _cache["https://down.example.com"] is None

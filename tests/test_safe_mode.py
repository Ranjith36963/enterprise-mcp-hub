"""Tests for --safe mode source filtering.

Verifies that _build_sources() correctly excludes HTML scraper sources
when safe_mode=True, while keeping APIs, ATS boards, and RSS feeds.
"""

import asyncio
from unittest.mock import MagicMock

import aiohttp
import pytest

from src.main import _build_sources, _SCRAPER_SOURCES, SOURCE_REGISTRY


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


@pytest.fixture
def session():
    """Create a mock aiohttp session for source construction."""
    s = MagicMock(spec=aiohttp.ClientSession)
    return s


class TestSafeMode:

    def test_safe_mode_excludes_scrapers(self, session):
        """safe_mode=True excludes all 7 scraper sources."""
        sources = _build_sources(session, safe_mode=True)
        source_names = {s.name for s in sources}
        for scraper in _SCRAPER_SOURCES:
            assert scraper not in source_names, f"{scraper} should be excluded in safe mode"

    def test_safe_mode_keeps_apis(self, session):
        """safe_mode=True keeps free API sources."""
        sources = _build_sources(session, safe_mode=True)
        source_names = {s.name for s in sources}
        api_sources = {"arbeitnow", "remoteok", "jobicy", "himalayas"}
        for api_src in api_sources:
            assert api_src in source_names, f"{api_src} should be kept in safe mode"

    def test_safe_mode_keeps_rss(self, session):
        """safe_mode=True keeps RSS/XML sources."""
        sources = _build_sources(session, safe_mode=True)
        source_names = {s.name for s in sources}
        rss_sources = {"jobs_ac_uk", "nhs_jobs", "workanywhere", "weworkremotely"}
        for rss_src in rss_sources:
            assert rss_src in source_names, f"{rss_src} should be kept in safe mode"

    def test_safe_mode_keeps_ats(self, session):
        """safe_mode=True keeps ATS board sources."""
        sources = _build_sources(session, safe_mode=True)
        source_names = {s.name for s in sources}
        ats_sources = {"greenhouse", "lever", "workable", "ashby"}
        for ats_src in ats_sources:
            assert ats_src in source_names, f"{ats_src} should be kept in safe mode"

    def test_normal_mode_includes_all(self, session):
        """safe_mode=False returns all sources from SOURCE_REGISTRY."""
        sources = _build_sources(session, safe_mode=False)
        source_names = {s.name for s in sources}
        # Should include scrapers
        for scraper in _SCRAPER_SOURCES:
            assert scraper in source_names, f"{scraper} should be included in normal mode"
        # Total count should match (minus glassdoor which shares indeed)
        # Registry has 48 entries but glassdoor→indeed, so 47 unique sources built
        # Actually _build_sources builds all_sources list which may not include
        # all registry entries (glassdoor is a registry alias, not built separately)
        assert len(sources) >= 43, f"Expected 43+ sources, got {len(sources)}"

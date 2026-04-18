"""Tests for BaseJobSource conditional-fetch layer (ETag / Last-Modified).

Verifies that sources can opt into bandwidth-saving conditional GETs.
Per pillar_3_batch_3.md §"Conditional fetching can cut bandwidth 60-90%":
many servers honour `If-None-Match` / `If-Modified-Since` even when
their API docs don't advertise it.

Contract: `BaseJobSource._get_json_conditional(url, ...)` returns the
body from the server on first fetch (storing ETag/Last-Modified) and
returns the cached body on subsequent 304 responses.
"""
import asyncio

import aiohttp
import pytest
from aioresponses import aioresponses

from src.sources.base import BaseJobSource


def _run(coro):
    asyncio.new_event_loop().run_until_complete(coro)


class _Probe(BaseJobSource):
    """Minimal concrete subclass for exercising BaseJobSource helpers."""
    name = "probe"
    category = "free_json"

    async def fetch_jobs(self):
        return []


def test_first_fetch_stores_etag():
    async def _t():
        session = aiohttp.ClientSession()
        try:
            with aioresponses() as m:
                m.get(
                    "https://api.example.test/jobs",
                    payload={"jobs": [{"id": 1}]},
                    headers={"ETag": 'W/"abc-123"'},
                )
                src = _Probe(session)
                body = await src._get_json_conditional("https://api.example.test/jobs")
                assert body == {"jobs": [{"id": 1}]}
                entry = src._conditional_cache.get(
                    ("https://api.example.test/jobs", ())
                )
                assert entry is not None
                assert entry.etag == 'W/"abc-123"'
        finally:
            await session.close()
    _run(_t())


def test_second_fetch_sends_if_none_match_and_gets_304_returns_cached_body():
    async def _t():
        session = aiohttp.ClientSession()
        try:
            url = "https://api.example.test/jobs"
            captured_headers = []

            def _capture(url_, **kwargs):
                captured_headers.append(kwargs.get("headers") or {})

            with aioresponses() as m:
                # First response: 200 with ETag + body
                m.get(url, payload={"jobs": [{"id": 1}]},
                      headers={"ETag": 'W/"v1"'}, callback=_capture)
                # Second response: 304 with no body
                m.get(url, status=304, callback=_capture)

                src = _Probe(session)
                first = await src._get_json_conditional(url)
                second = await src._get_json_conditional(url)

                assert first == {"jobs": [{"id": 1}]}
                # 304 → returns the cached body, not None
                assert second == {"jobs": [{"id": 1}]}

                # Second call must have sent If-None-Match
                assert len(captured_headers) == 2
                assert captured_headers[1].get("If-None-Match") == 'W/"v1"'
        finally:
            await session.close()
    _run(_t())


def test_last_modified_roundtrip():
    async def _t():
        session = aiohttp.ClientSession()
        try:
            url = "https://api.example.test/feed.xml"
            captured_headers = []

            def _capture(url_, **kwargs):
                captured_headers.append(kwargs.get("headers") or {})

            with aioresponses() as m:
                m.get(url, payload={"ok": True},
                      headers={"Last-Modified": "Wed, 15 Jan 2026 12:00:00 GMT"},
                      callback=_capture)
                m.get(url, status=304, callback=_capture)

                src = _Probe(session)
                first = await src._get_json_conditional(url)
                second = await src._get_json_conditional(url)

                assert first == {"ok": True}
                assert second == {"ok": True}
                assert (captured_headers[1].get("If-Modified-Since")
                        == "Wed, 15 Jan 2026 12:00:00 GMT")
        finally:
            await session.close()
    _run(_t())


def test_no_cache_when_no_validator_header():
    """Server returned neither ETag nor Last-Modified → nothing cached."""
    async def _t():
        session = aiohttp.ClientSession()
        try:
            url = "https://api.example.test/nocache"
            with aioresponses() as m:
                m.get(url, payload={"jobs": []})
                src = _Probe(session)
                body = await src._get_json_conditional(url)
                assert body == {"jobs": []}
                entry = src._conditional_cache.get((url, ()))
                assert entry is None
        finally:
            await session.close()
    _run(_t())

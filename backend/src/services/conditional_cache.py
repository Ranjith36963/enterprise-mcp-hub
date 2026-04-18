"""Tiny in-memory ETag / Last-Modified cache for conditional HTTP fetches.

Used by `BaseJobSource._get_json_conditional`. Per Batch 3 §Conditional,
many sources honour `If-None-Match` / `If-Modified-Since` even when the
docs don't advertise it; caching the validator + body lets us turn a
repeat 200 into a zero-body 304 plus a local cache hit.

Capacity is bounded via a simple FIFO eviction policy — 256 distinct
(url, params) keys is plenty for even the most over-polled deployment.
"""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from typing import Any


@dataclass
class CachedEntry:
    body: Any
    etag: str | None = None
    last_modified: str | None = None


class ConditionalCache:
    """(url, params) -> CachedEntry, bounded FIFO."""

    def __init__(self, max_entries: int = 256) -> None:
        self._store: OrderedDict[tuple[str, tuple], CachedEntry] = OrderedDict()
        self._max_entries = max_entries

    def get(self, key: tuple[str, tuple]) -> CachedEntry | None:
        return self._store.get(key)

    def set(self, key: tuple[str, tuple], entry: CachedEntry) -> None:
        if key in self._store:
            self._store.move_to_end(key)
        self._store[key] = entry
        while len(self._store) > self._max_entries:
            self._store.popitem(last=False)

    def __len__(self) -> int:
        return len(self._store)

"""Dev helper: probe the Job360 ARQ worker side.

Checks (all best-effort, all failures are non-fatal):
    1. Is REDIS_URL reachable? (stdlib socket TCP connect)
    2. If `arq` importable: print WorkerSettings class attrs.
    3. If `redis` importable: try LLEN arq:queue for queue depth.

Usage:
    python backend/scripts/check_worker.py
"""

from __future__ import annotations

import os
import socket
import sys
from urllib.parse import urlparse


def _probe_redis_url() -> tuple[str, bool, str]:
    url = os.environ.get("REDIS_URL", "redis://localhost:6379")
    parsed = urlparse(url)
    host = parsed.hostname or "localhost"
    port = parsed.port or 6379
    try:
        with socket.create_connection((host, port), timeout=2.0):
            return url, True, f"tcp {host}:{port} reachable"
    except OSError as exc:
        return url, False, f"tcp {host}:{port} unreachable: {exc}"


def _probe_worker_settings() -> None:
    try:
        from src.workers import settings as worker_settings  # type: ignore
    except Exception as exc:
        print(f"  arq WorkerSettings: import failed ({exc})")
        return
    ws = getattr(worker_settings, "WorkerSettings", None)
    if ws is None:
        print("  arq WorkerSettings: class not found in src.workers.settings")
        return
    print("  WorkerSettings attrs:")
    for attr in (
        "functions",
        "queue_name",
        "max_jobs",
        "job_timeout",
        "keep_result",
        "cron_jobs",
        "on_startup",
        "on_shutdown",
    ):
        if hasattr(ws, attr):
            val = getattr(ws, attr)
            if callable(val) and not isinstance(val, type):
                val = f"<callable {getattr(val, '__name__', repr(val))}>"
            elif isinstance(val, (list, tuple)):
                val = [getattr(f, "__name__", repr(f)) if callable(f) else repr(f) for f in val]
            print(f"    {attr} = {val}")


def _probe_queue_depth(url: str) -> None:
    try:
        import redis  # type: ignore
    except Exception as exc:
        print(f"  redis lib: not installed ({exc}) — skipping LLEN probe")
        return
    try:
        client = redis.Redis.from_url(url, socket_connect_timeout=2.0)
        depth = client.llen("arq:queue")
        print(f"  arq:queue LLEN = {depth}")
    except Exception as exc:
        print(f"  arq:queue LLEN: failed ({exc})")


def main() -> int:
    print("== Redis ==")
    url, ok, detail = _probe_redis_url()
    print(f"  REDIS_URL = {url}")
    print(f"  {'OK' if ok else 'FAIL'}: {detail}")

    print("\n== ARQ ==")
    try:
        import arq  # type: ignore  # noqa: F401

        print("  arq: importable")
        _probe_worker_settings()
    except Exception as exc:
        print(f"  arq: not installed ({exc}) — skipping WorkerSettings probe")

    print("\n== Queue depth ==")
    if ok:
        _probe_queue_depth(url)
    else:
        print("  skipped (Redis unreachable)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Step-1 B1+B2 roundtrip smoke test.

Run under `make verify-step-1`. Creates an in-memory DB, inserts a Job with an
explicit historic `first_seen_at`, reads it back via `get_recent_jobs(days=9999)`,
and asserts the value was preserved (i.e. NOT silently overwritten by
`datetime('now')` inside insert_job).

Exits 0 on success, 1 on failure.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Allow running as `python scripts/verify_dataclass_roundtrip.py` from backend/
_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from src.models import Job  # noqa: E402
from src.repositories.database import JobDatabase  # noqa: E402


async def _run() -> int:
    db = JobDatabase(":memory:")
    await db.init_db()
    try:
        job = Job(
            title="Historic Role",
            company="TimeMachine",
            apply_url="https://example.com/historic",
            source="reed",
            date_found="2020-01-01T00:00:00+00:00",
            location="London",
            description="Role from 2020",
            first_seen_at="2020-01-01T00:00:00Z",
            last_seen_at="2020-06-01T00:00:00Z",
            staleness_state="active",
        )
        inserted = await db.insert_job(job)
        if not inserted:
            print("FAIL: insert_job returned False (duplicate?)", file=sys.stderr)
            return 1
        rows = await db.get_recent_jobs(days=9999)
        if not rows:
            print("FAIL: get_recent_jobs returned no rows", file=sys.stderr)
            return 1
        row = rows[0]
        first_seen_at = row["first_seen_at"]
        if first_seen_at is None or not first_seen_at.startswith("2020-01-01"):
            print(
                f"FAIL: first_seen_at was overwritten. Expected prefix '2020-01-01', " f"got {first_seen_at!r}",
                file=sys.stderr,
            )
            return 1
        last_seen_at = row["last_seen_at"]
        if last_seen_at is None or not last_seen_at.startswith("2020-06-01"):
            print(
                f"FAIL: last_seen_at was overwritten. Expected prefix '2020-06-01', " f"got {last_seen_at!r}",
                file=sys.stderr,
            )
            return 1
        print("OK: dataclass roundtrip preserved first_seen_at / last_seen_at")
        return 0
    finally:
        await db.close()


def main() -> int:
    return asyncio.run(_run())


if __name__ == "__main__":
    sys.exit(main())

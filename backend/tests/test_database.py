import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from src.models import Job
from src.repositories.database import JobDatabase


@pytest.fixture
def db():
    database = JobDatabase(":memory:")
    asyncio.run(database.init_db())
    yield database
    asyncio.run(database.close())


def _make_job(**overrides):
    defaults = dict(
        title="AI Engineer",
        company="DeepMind",
        apply_url="https://example.com/job",
        source="reed",
        date_found=datetime.now(timezone.utc).isoformat(),
        location="London",
        description="AI role",
    )
    defaults.update(overrides)
    return Job(**defaults)


@pytest.mark.fast
def test_init_creates_tables(db):
    tables = asyncio.run(db.get_tables())
    assert "jobs" in tables
    assert "run_log" in tables


def test_insert_and_check_seen(db):
    job = _make_job()
    key = job.normalized_key()
    assert asyncio.run(db.is_job_seen(key)) is False
    asyncio.run(db.insert_job(job))
    assert asyncio.run(db.is_job_seen(key)) is True


def test_duplicate_insert_ignored(db):
    job = _make_job()
    asyncio.run(db.insert_job(job))
    asyncio.run(db.insert_job(job))  # should not raise
    count = asyncio.run(db.count_jobs())
    assert count == 1


def test_insert_different_jobs(db):
    j1 = _make_job(title="AI Engineer", company="DeepMind")
    j2 = _make_job(title="ML Engineer", company="Revolut")
    asyncio.run(db.insert_job(j1))
    asyncio.run(db.insert_job(j2))
    count = asyncio.run(db.count_jobs())
    assert count == 2


def test_log_run(db):
    stats = {
        "total_found": 50,
        "new_jobs": 10,
        "per_source": {"reed": 20, "adzuna": 30},
    }
    asyncio.run(db.log_run(stats))
    runs = asyncio.run(db.get_run_logs())
    assert len(runs) == 1
    assert runs[0]["total_found"] == 50


def test_get_new_jobs_since(db):
    j1 = _make_job(title="AI Engineer", company="DeepMind")
    asyncio.run(db.insert_job(j1))
    jobs = asyncio.run(db.get_new_jobs_since(hours=1))
    assert len(jobs) == 1


def test_migrate_no_op_on_fresh_db(db):
    """Migration on a fresh database should be a no-op (all columns already exist)."""
    # _migrate() is called during init_db(), so just verify it didn't break anything
    tables = asyncio.run(db.get_tables())
    assert "jobs" in tables
    assert "run_log" in tables


def test_insert_job_preserves_caller_first_seen_at(db):
    """Step-1 B2: caller-supplied first_seen_at must NOT be overwritten with now.

    Bug-reproduction test: before the fix, insert_job silently replaced any
    caller value with datetime('now'). Post-fix, the explicit 2020 timestamp
    should round-trip unchanged.
    """
    job = _make_job(
        title="Historic Role",
        company="TimeMachine",
        first_seen_at="2020-01-01T00:00:00+00:00",
        last_seen_at="2020-06-01T00:00:00+00:00",
    )
    asyncio.run(db.insert_job(job))
    rows = asyncio.run(db.get_recent_jobs(days=9999))
    # Find our specific job (other tests may share the db fixture — but :memory: is per-test)
    row = next(r for r in rows if r["title"] == "Historic Role")
    assert row["first_seen_at"].startswith("2020-01-01"), f"first_seen_at was overwritten: got {row['first_seen_at']}"
    assert row["last_seen_at"].startswith("2020-06-01"), f"last_seen_at was overwritten: got {row['last_seen_at']}"


def test_insert_job_defaults_first_seen_at_to_now_when_none(db):
    """Step-1 B2: when caller leaves first_seen_at/last_seen_at as None, insert_job
    falls back to datetime('now'). Preserves pre-fix behaviour for default callers.
    """
    job = _make_job(title="Fresh Role", company="NowCo")
    # Sanity: the Job dataclass defaults these to None
    assert job.first_seen_at is None
    assert job.last_seen_at is None
    before = datetime.now(timezone.utc)
    asyncio.run(db.insert_job(job))
    rows = asyncio.run(db.get_recent_jobs(days=9999))
    row = next(r for r in rows if r["title"] == "Fresh Role")
    assert row["first_seen_at"] is not None
    assert row["last_seen_at"] is not None
    # first_seen_at should be >= `before` (i.e. set during the insert, not 2020)
    got = datetime.fromisoformat(row["first_seen_at"])
    assert got >= before - timedelta(seconds=5), f"first_seen_at not defaulted to now: got {row['first_seen_at']}"


def test_get_last_source_counts_empty(db):
    """get_last_source_counts should return empty dict when no runs exist."""
    result = asyncio.run(db.get_last_source_counts(5))
    assert result == {}


def test_get_last_source_counts_with_data(db):
    """get_last_source_counts should return per-source history from run_log."""
    stats1 = {"total_found": 10, "new_jobs": 5, "per_source": {"reed": 5, "adzuna": 3}}
    stats2 = {"total_found": 8, "new_jobs": 2, "per_source": {"reed": 0, "adzuna": 4}}
    asyncio.run(db.log_run(stats1))
    asyncio.run(db.log_run(stats2))
    result = asyncio.run(db.get_last_source_counts(5))
    # Most recent run first
    assert "reed" in result
    assert "adzuna" in result
    assert 0 in result["reed"]
    assert 5 in result["reed"]

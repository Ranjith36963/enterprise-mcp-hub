import pytest
import asyncio
from datetime import datetime, timezone

from src.models import Job
from src.storage.database import JobDatabase


@pytest.fixture
def db():
    database = JobDatabase(":memory:")
    loop = asyncio.get_event_loop()
    loop.run_until_complete(database.init_db())
    yield database
    loop.run_until_complete(database.close())


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


def test_init_creates_tables(db):
    loop = asyncio.get_event_loop()
    tables = loop.run_until_complete(db.get_tables())
    assert "jobs" in tables
    assert "run_log" in tables


def test_insert_and_check_seen(db):
    loop = asyncio.get_event_loop()
    job = _make_job()
    key = job.normalized_key()
    assert loop.run_until_complete(db.is_job_seen(key)) is False
    loop.run_until_complete(db.insert_job(job))
    assert loop.run_until_complete(db.is_job_seen(key)) is True


def test_duplicate_insert_ignored(db):
    loop = asyncio.get_event_loop()
    job = _make_job()
    loop.run_until_complete(db.insert_job(job))
    loop.run_until_complete(db.insert_job(job))  # should not raise
    count = loop.run_until_complete(db.count_jobs())
    assert count == 1


def test_insert_different_jobs(db):
    loop = asyncio.get_event_loop()
    j1 = _make_job(title="AI Engineer", company="DeepMind")
    j2 = _make_job(title="ML Engineer", company="Revolut")
    loop.run_until_complete(db.insert_job(j1))
    loop.run_until_complete(db.insert_job(j2))
    count = loop.run_until_complete(db.count_jobs())
    assert count == 2


def test_log_run(db):
    loop = asyncio.get_event_loop()
    stats = {
        "total_found": 50,
        "new_jobs": 10,
        "per_source": {"reed": 20, "adzuna": 30},
    }
    loop.run_until_complete(db.log_run(stats))
    runs = loop.run_until_complete(db.get_run_logs())
    assert len(runs) == 1
    assert runs[0]["total_found"] == 50


def test_get_new_jobs_since(db):
    loop = asyncio.get_event_loop()
    j1 = _make_job(title="AI Engineer", company="DeepMind")
    loop.run_until_complete(db.insert_job(j1))
    jobs = loop.run_until_complete(db.get_new_jobs_since(hours=1))
    assert len(jobs) == 1


# ── Enhanced database tests (gap fill) ──


def test_schema_version_set(db):
    """Schema version is set after init_db migrations."""
    loop = asyncio.get_event_loop()
    version = loop.run_until_complete(db._get_schema_version())
    assert version >= 7  # Current schema version


def test_source_health_table_exists(db):
    """Source health table (v7 migration) is created."""
    loop = asyncio.get_event_loop()
    tables = loop.run_until_complete(db.get_tables())
    assert "source_health" in tables


def test_source_health_round_trip(db):
    """Record failures → load health → verify round-trip."""
    loop = asyncio.get_event_loop()
    loop.run_until_complete(db.record_source_failure("test_src", "timeout"))
    loop.run_until_complete(db.record_source_failure("test_src", "connection"))

    health = loop.run_until_complete(db.get_source_health())
    assert "test_src" in health
    assert health["test_src"]["consecutive_failures"] == 2


def test_reset_source_health(db):
    """reset_source_health removes the record entirely."""
    loop = asyncio.get_event_loop()
    loop.run_until_complete(db.record_source_failure("test_src", "error"))
    loop.run_until_complete(db.reset_source_health("test_src"))

    health = loop.run_until_complete(db.get_source_health())
    assert "test_src" not in health


def test_get_recent_jobs_with_min_score(db):
    """get_recent_jobs respects min_score filter."""
    loop = asyncio.get_event_loop()
    j_low = _make_job(title="Low Job", company="LowCo", match_score=10)
    j_high = _make_job(title="High Job", company="HighCo", match_score=80)
    loop.run_until_complete(db.insert_job(j_low))
    loop.run_until_complete(db.insert_job(j_high))

    jobs = loop.run_until_complete(db.get_recent_jobs(days=7, min_score=50))
    assert len(jobs) == 1
    assert jobs[0]["title"] == "High Job"


def test_get_job_by_id(db):
    """get_job_by_id returns the correct job by primary key."""
    loop = asyncio.get_event_loop()
    j = _make_job(title="Specific Job", company="SpecificCorp")
    loop.run_until_complete(db.insert_job(j))

    # Get all jobs and extract the ID
    jobs = loop.run_until_complete(db.get_new_jobs_since(hours=1))
    job_id = jobs[0]["id"]

    result = loop.run_until_complete(db.get_job_by_id(job_id))
    assert result is not None
    assert result["title"] == "Specific Job"


def test_get_job_by_id_not_found(db):
    """get_job_by_id returns None for nonexistent ID."""
    loop = asyncio.get_event_loop()
    result = loop.run_until_complete(db.get_job_by_id(99999))
    assert result is None


def test_count_jobs(db):
    """count_jobs returns accurate count."""
    loop = asyncio.get_event_loop()
    assert loop.run_until_complete(db.count_jobs()) == 0
    loop.run_until_complete(db.insert_job(_make_job(title="J1", company="C1")))
    loop.run_until_complete(db.insert_job(_make_job(title="J2", company="C2")))
    assert loop.run_until_complete(db.count_jobs()) == 2

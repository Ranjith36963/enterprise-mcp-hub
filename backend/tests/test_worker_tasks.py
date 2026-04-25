"""Phase 5 worker task tests — no Redis, direct function calls."""

import os
import tempfile
from datetime import datetime, timezone

import aiosqlite
import pytest

from migrations import runner
from src.services.prefilter import FilterProfile
from src.workers.tasks import (
    idempotency_key,
    mark_ledger_failed,
    mark_ledger_sent,
    score_and_ingest,
)


@pytest.fixture
async def worker_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    async with aiosqlite.connect(path) as db:
        await db.executescript(
            """
            CREATE TABLE jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                company TEXT NOT NULL,
                location TEXT DEFAULT '',
                salary_min REAL,
                salary_max REAL,
                description TEXT DEFAULT '',
                apply_url TEXT NOT NULL,
                source TEXT NOT NULL,
                date_found TEXT NOT NULL,
                match_score INTEGER DEFAULT 0,
                visa_flag INTEGER DEFAULT 0,
                experience_level TEXT DEFAULT '',
                normalized_company TEXT NOT NULL,
                normalized_title TEXT NOT NULL,
                first_seen TEXT NOT NULL,
                first_seen_at TEXT,
                UNIQUE(normalized_company, normalized_title)
            );
            CREATE TABLE user_actions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id INTEGER NOT NULL,
                action TEXT NOT NULL,
                notes TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                UNIQUE(job_id)
            );
            CREATE TABLE applications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id INTEGER NOT NULL,
                stage TEXT NOT NULL DEFAULT 'applied',
                notes TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(job_id)
            );
            """
        )
        await db.commit()
    await runner.up(path)
    async with aiosqlite.connect(path) as db:
        await db.execute(
            "INSERT INTO users(id, email, password_hash) VALUES(?, ?, ?)",
            ("alice", "a@x", "!"),
        )
        await db.execute(
            "INSERT INTO users(id, email, password_hash) VALUES(?, ?, ?)",
            ("bob", "b@x", "!"),
        )
        now = datetime.now(timezone.utc).isoformat()
        await db.execute(
            """
            INSERT INTO jobs (title, company, apply_url, source, date_found,
                              normalized_company, normalized_title, first_seen,
                              first_seen_at, match_score, description)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "Senior Python Engineer",
                "Acme Ltd",
                "https://acme.example/jobs/1",
                "test",
                now,
                "acme",
                "senior python engineer",
                now,
                now,
                85,
                "Python, Django, AWS",
            ),
        )
        await db.commit()
    yield path
    try:
        os.unlink(path)
    except OSError:
        pass


def test_idempotency_key_is_deterministic():
    a = idempotency_key("u1", 1, "email")
    b = idempotency_key("u1", 1, "email")
    assert a == b
    assert idempotency_key("u1", 1, "slack") != a
    assert idempotency_key("u2", 1, "email") != a


@pytest.mark.asyncio
async def test_score_and_ingest_creates_feed_rows_for_each_passing_user(worker_db):
    async with aiosqlite.connect(worker_db) as db:
        enqueued: list[tuple] = []
        # Inject a per-user scorer — the Phase 5 task MUST call it for every
        # user. Deliberately returning distinct scores per user proves the
        # score_and_ingest is genuinely scoring per user (not reusing the
        # catalog-level match_score).
        calls: list[tuple[str, str]] = []

        def scorer(user_id: str, job):
            calls.append((user_id, job.title))
            return {"alice": 85, "bob": 70}.get(user_id, 0)

        ctx = {
            "db": db,
            "enqueue": lambda *args: _append(enqueued, args),
            "scorer": scorer,
        }
        result = await score_and_ingest(
            ctx,
            job_id=1,
            users_override=[
                ("alice", FilterProfile(skills={"python"}), 80),
                ("bob", FilterProfile(skills={"python"}), 80),
            ],
        )
        cur = await db.execute("SELECT user_id, score, bucket FROM user_feed")
        rows = sorted([tuple(r) for r in await cur.fetchall()])
    assert result == {"ingested": 2, "notifications_queued": 1}  # only alice ≥ 80
    assert [(r[0], r[1]) for r in rows] == [("alice", 85), ("bob", 70)]
    # Prove per-user scorer invocation
    assert sorted(calls) == [
        ("alice", "Senior Python Engineer"),
        ("bob", "Senior Python Engineer"),
    ]


@pytest.mark.asyncio
async def test_score_and_ingest_skips_users_failing_prefilter(worker_db):
    async with aiosqlite.connect(worker_db) as db:
        enqueued: list[tuple] = []
        ctx = {
            "db": db,
            "enqueue": lambda *args: _append(enqueued, args),
            "scorer": lambda user_id, job: 85,
        }
        result = await score_and_ingest(
            ctx,
            job_id=1,
            users_override=[
                ("alice", FilterProfile(skills={"python"}), 80),  # passes
                ("bob", FilterProfile(skills={"haskell"}), 80),  # skill miss — filtered
            ],
        )
        cur = await db.execute("SELECT user_id FROM user_feed")
        rows = await cur.fetchall()
    assert result["ingested"] == 1
    assert {r[0] for r in rows} == {"alice"}


@pytest.mark.asyncio
async def test_score_and_ingest_is_idempotent(worker_db):
    async with aiosqlite.connect(worker_db) as db:
        ctx = {
            "db": db,
            "enqueue": lambda *a: None,
            "scorer": lambda user_id, job: 85,
        }
        await score_and_ingest(ctx, job_id=1, users_override=[("alice", FilterProfile(), 80)])
        await score_and_ingest(ctx, job_id=1, users_override=[("alice", FilterProfile(), 80)])
        cur = await db.execute("SELECT COUNT(*) FROM user_feed WHERE user_id = 'alice'")
        (count,) = await cur.fetchone()
    assert count == 1


@pytest.mark.asyncio
async def test_ledger_idempotent_per_channel(worker_db):
    async with aiosqlite.connect(worker_db) as db:
        ctx = {
            "db": db,
            "enqueue": lambda *a: None,
            "scorer": lambda user_id, job: 85,
        }
        # Two runs with same (user, job, channel='instant') — ledger unique
        await score_and_ingest(ctx, job_id=1, users_override=[("alice", FilterProfile(), 80)])
        await score_and_ingest(ctx, job_id=1, users_override=[("alice", FilterProfile(), 80)])
        cur = await db.execute("SELECT COUNT(*) FROM notification_ledger WHERE user_id='alice' AND job_id=1")
        (count,) = await cur.fetchone()
    assert count == 1  # UNIQUE(user_id, job_id, channel) held


@pytest.mark.asyncio
async def test_instant_notification_suppressed_below_threshold(worker_db):
    async with aiosqlite.connect(worker_db) as db:
        enqueued: list[tuple] = []
        ctx = {
            "db": db,
            "enqueue": lambda *args: _append(enqueued, args),
            "scorer": lambda user_id, job: 85,
        }
        result = await score_and_ingest(
            ctx,
            job_id=1,
            users_override=[("alice", FilterProfile(), 90)],  # job scores 85 < 90
        )
        cur = await db.execute("SELECT COUNT(*) FROM notification_ledger WHERE user_id='alice'")
        (count,) = await cur.fetchone()
    assert result["notifications_queued"] == 0
    assert count == 0


@pytest.mark.asyncio
async def test_mark_ledger_sent_updates_status(worker_db):
    async with aiosqlite.connect(worker_db) as db:
        ctx = {
            "db": db,
            "enqueue": lambda *a: None,
            "scorer": lambda user_id, job: 85,
        }
        await score_and_ingest(ctx, job_id=1, users_override=[("alice", FilterProfile(), 80)])
        await mark_ledger_sent(db, user_id="alice", job_id=1, channel="instant")
        cur = await db.execute("SELECT status, sent_at FROM notification_ledger WHERE user_id='alice'")
        row = await cur.fetchone()
    assert row[0] == "sent"
    assert row[1] is not None


@pytest.mark.asyncio
async def test_mark_ledger_failed_increments_retry(worker_db):
    async with aiosqlite.connect(worker_db) as db:
        ctx = {
            "db": db,
            "enqueue": lambda *a: None,
            "scorer": lambda user_id, job: 85,
        }
        await score_and_ingest(ctx, job_id=1, users_override=[("alice", FilterProfile(), 80)])
        await mark_ledger_failed(db, user_id="alice", job_id=1, channel="instant", error="503")
        await mark_ledger_failed(db, user_id="alice", job_id=1, channel="instant", error="503")
        cur = await db.execute("SELECT status, error_message, retry_count FROM notification_ledger")
        row = await cur.fetchone()
    assert tuple(row) == ("failed", "503", 2)


async def _append(lst, args):
    lst.append(args)


# Step-1 B5 — multi-dim wiring at the worker JobScorer call site.


@pytest.mark.asyncio
async def test_score_and_ingest_passes_user_prefs_and_enrichment_lookup(worker_db, monkeypatch):
    """The worker MUST construct each per-user JobScorer with both
    `user_preferences` (from that user's loaded profile) AND a callable
    `enrichment_lookup`. This activates the Pillar 2 Batch 2.9 multi-dim
    scoring path. Without these kwargs, score_and_ingest silently drops to
    the legacy 4-component formula and the upgrade is invisible.
    """
    from src.services.profile.models import CVData, UserPreferences, UserProfile
    from src.services.skill_matcher import ScoreBreakdown

    # The worker's _scorer_for() loads the user's profile. We inject a fake
    # so the test is deterministic and doesn't depend on a seeded
    # user_profiles table.
    fake_profile = UserProfile(
        cv_data=CVData(raw_text="dummy CV"),
        preferences=UserPreferences(target_job_titles=["Engineer"], salary_min=50000),
    )
    monkeypatch.setattr("src.workers.tasks._user_profile_for", lambda user_id: fake_profile)

    captured: list[dict] = []

    class _SpyScorer:
        def __init__(self, config, *, user_preferences=None, enrichment_lookup=None):
            captured.append(
                {
                    "user_preferences": user_preferences,
                    "enrichment_lookup": enrichment_lookup,
                }
            )

        def score(self, job):
            return ScoreBreakdown(match_score=99)

    monkeypatch.setattr("src.workers.tasks.JobScorer", _SpyScorer)

    async with aiosqlite.connect(worker_db) as db:
        ctx = {"db": db, "enqueue": lambda *a: None}  # NB: no 'scorer' override
        result = await score_and_ingest(
            ctx,
            job_id=1,
            users_override=[("alice", FilterProfile(), 80)],
        )

    assert result["ingested"] == 1
    assert len(captured) == 1
    assert (
        captured[0]["user_preferences"] is fake_profile.preferences
    ), "JobScorer must receive the loaded user's preferences"
    assert callable(captured[0]["enrichment_lookup"]), "enrichment_lookup must be a callable (job)->Enrichment|None"

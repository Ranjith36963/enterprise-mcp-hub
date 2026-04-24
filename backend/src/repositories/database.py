import json
import os
import re
from datetime import datetime, timedelta, timezone

import aiosqlite

_VALID_COL_NAME = re.compile(r"^[a-z_][a-z0-9_]{0,63}$")
_VALID_COL_TYPES = {"TEXT", "INTEGER", "REAL", "BLOB", "NUMERIC"}

from src.models import Job  # noqa: E402  # after the regex constants to avoid circular import


class JobDatabase:
    def __init__(self, db_path: str):
        self._path = db_path
        self._conn: aiosqlite.Connection | None = None

    async def init_db(self):
        # Ensure parent directory exists for fresh clones where data/ isn't yet created.
        parent = os.path.dirname(os.path.abspath(self._path))
        if parent:
            os.makedirs(parent, exist_ok=True)
        self._conn = await aiosqlite.connect(self._path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA journal_mode=WAL")
        await self._conn.execute("PRAGMA busy_timeout=5000")
        await self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS jobs (
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
                posted_at TEXT,
                first_seen_at TEXT,
                last_seen_at TEXT,
                last_updated_at TEXT,
                date_confidence TEXT DEFAULT 'low',
                date_posted_raw TEXT,
                consecutive_misses INTEGER DEFAULT 0,
                staleness_state TEXT DEFAULT 'active',
                UNIQUE(normalized_company, normalized_title)
            );
            CREATE TABLE IF NOT EXISTS run_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                total_found INTEGER DEFAULT 0,
                new_jobs INTEGER DEFAULT 0,
                sources_queried INTEGER DEFAULT 0,
                per_source TEXT DEFAULT '{}'
            );
            CREATE INDEX IF NOT EXISTS idx_jobs_date_found ON jobs(date_found);
            CREATE INDEX IF NOT EXISTS idx_jobs_first_seen ON jobs(first_seen);
            CREATE INDEX IF NOT EXISTS idx_jobs_match_score ON jobs(match_score);
            CREATE INDEX IF NOT EXISTS idx_jobs_staleness_state ON jobs(staleness_state);
            CREATE INDEX IF NOT EXISTS idx_jobs_last_seen_at ON jobs(last_seen_at);
            CREATE TABLE IF NOT EXISTS user_actions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id INTEGER NOT NULL,
                action TEXT NOT NULL,
                notes TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                UNIQUE(job_id)
            );
            CREATE TABLE IF NOT EXISTS applications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id INTEGER NOT NULL,
                stage TEXT NOT NULL DEFAULT 'applied',
                notes TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(job_id)
            );
        """)
        await self._conn.commit()
        await self._migrate()

    async def _migrate(self):
        """Add any missing columns to existing tables (forward-compatible schema migration).

        Runs every init_db(). Safe on both fresh schemas (just created above)
        and on legacy DBs lazy-upgraded in place. Mirrors the forward
        direction of the SQL migrations under backend/migrations/ so tests
        and CLI tools that bypass the external runner still see the full
        schema.
        """
        jobs_migrations = [
            # Pillar 3 Batch 1 — 5-column date model + ghost detection hooks.
            ("posted_at", "TEXT"),
            ("first_seen_at", "TEXT"),
            ("last_seen_at", "TEXT"),
            ("last_updated_at", "TEXT"),
            ("date_confidence", "TEXT DEFAULT 'low'"),
            ("date_posted_raw", "TEXT"),
            ("consecutive_misses", "INTEGER DEFAULT 0"),
            ("staleness_state", "TEXT DEFAULT 'active'"),
        ]
        run_log_migrations = [
            # Step-0 pre-flight — migration 0010 observability columns.
            # Mirrored here so init_db() alone produces the full run_log
            # schema even when the external migration runner hasn't run.
            ("run_uuid", "TEXT"),
            ("per_source_errors", "TEXT DEFAULT '{}'"),
            ("per_source_duration", "TEXT DEFAULT '{}'"),
            ("total_duration", "REAL"),
            ("user_id", "TEXT"),
        ]

        await self._add_missing_columns("jobs", jobs_migrations)
        await self._add_missing_columns("run_log", run_log_migrations)
        await self._conn.commit()

    async def _add_missing_columns(self, table: str, migrations: list[tuple[str, str]]) -> None:
        """Apply `ALTER TABLE ... ADD COLUMN` for each entry not yet present."""
        if not _VALID_COL_NAME.match(table):
            raise ValueError(f"Invalid migration table name: {table}")
        cursor = await self._conn.execute(f"PRAGMA table_info({table})")
        existing = {row[1] for row in await cursor.fetchall()}
        for col_name, col_def in migrations:
            if col_name in existing:
                continue
            if not _VALID_COL_NAME.match(col_name):
                raise ValueError(f"Invalid migration column name: {col_name}")
            col_type_word = col_def.split()[0].upper()
            if col_type_word not in _VALID_COL_TYPES:
                raise ValueError(f"Invalid migration column type: {col_type_word}")
            await self._conn.execute(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_def}")

    async def get_tables(self) -> list[str]:
        cursor = await self._conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        rows = await cursor.fetchall()
        return [row[0] for row in rows]

    async def is_job_seen(self, normalized_key: tuple[str, str]) -> bool:
        company, title = normalized_key
        cursor = await self._conn.execute(
            "SELECT 1 FROM jobs WHERE normalized_company = ? AND normalized_title = ?",
            (company, title),
        )
        return await cursor.fetchone() is not None

    async def insert_job(self, job: Job) -> bool:
        """Insert job, returning True if it was actually inserted (not a duplicate).

        Step-1 B2: lifecycle timestamps (`first_seen_at`, `last_seen_at`) are honoured
        when the caller supplies them on the Job dataclass; they fall back to
        `datetime('now')` only when the Job attribute is None. This mirrors the
        pattern already used for `posted_at`. `scraped_at` equivalent (the
        internal `first_seen` audit column) stays always-now — it's an ingestion
        timestamp, not a lifecycle timestamp.
        """
        company, title = job.normalized_key()
        now = datetime.now(timezone.utc).isoformat()
        first_seen_at = job.first_seen_at if job.first_seen_at is not None else now
        last_seen_at = job.last_seen_at if job.last_seen_at is not None else now
        cursor = await self._conn.execute(
            """INSERT OR IGNORE INTO jobs
            (title, company, location, salary_min, salary_max, description,
             apply_url, source, date_found, match_score, visa_flag,
             experience_level, normalized_company, normalized_title, first_seen,
             posted_at, first_seen_at, last_seen_at, date_confidence,
             date_posted_raw)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                job.title,
                job.company,
                job.location,
                job.salary_min,
                job.salary_max,
                job.description,
                job.apply_url,
                job.source,
                job.date_found,
                job.match_score,
                int(job.visa_flag),
                job.experience_level,
                company,
                title,
                now,
                job.posted_at,
                first_seen_at,
                last_seen_at,
                job.date_confidence,
                job.date_posted_raw,
            ),
        )
        return cursor.rowcount > 0

    async def update_last_seen(self, normalized_key: tuple[str, str]) -> None:
        """Mark a job as re-seen this scrape cycle. Resets ghost-detection counters."""
        now = datetime.now(timezone.utc).isoformat()
        await self._conn.execute(
            "UPDATE jobs SET last_seen_at = ?, consecutive_misses = 0, "
            "staleness_state = 'active' "
            "WHERE normalized_company = ? AND normalized_title = ?",
            (now, normalized_key[0], normalized_key[1]),
        )
        await self._conn.commit()

    async def mark_missed_for_source(self, source: str, seen_keys: set[tuple[str, str]]) -> int:
        """Increment consecutive_misses for every job of `source` not in `seen_keys`.

        Scrape-completeness gates (rolling-average checks) are the CALLER's
        responsibility — only call this after a scrape is deemed healthy, per
        pillar_3_batch_1.md §3 Step 1. Returns the count of jobs marked missed.
        """
        cursor = await self._conn.execute(
            "SELECT id, normalized_company, normalized_title " "FROM jobs WHERE source = ?",
            (source,),
        )
        rows = await cursor.fetchall()
        missed_ids = [row[0] for row in rows if (row[1], row[2]) not in seen_keys]
        for job_id in missed_ids:
            await self._conn.execute(
                "UPDATE jobs SET consecutive_misses = consecutive_misses + 1 " "WHERE id = ?",
                (job_id,),
            )
        await self._conn.commit()
        return len(missed_ids)

    async def commit(self):
        """Commit pending changes."""
        if self._conn:
            await self._conn.commit()

    async def count_jobs(self) -> int:
        cursor = await self._conn.execute("SELECT COUNT(*) FROM jobs")
        row = await cursor.fetchone()
        return row[0]

    async def log_run(
        self,
        stats: dict,
        *,
        run_uuid: str | None = None,
        per_source_errors: dict | None = None,
        per_source_duration: dict | None = None,
        total_duration: float | None = None,
        user_id: str | None = None,
    ):
        """Insert a run-log row.

        Extra keyword-only params were added by migration 0010
        (``run_uuid``, ``per_source_errors``, ``per_source_duration``,
        ``total_duration``, ``user_id``). All default to ``None`` so legacy
        callers that pass only ``stats`` continue to work unchanged. Dict
        payloads are JSON-encoded; None is stored as SQL NULL for the text
        columns and as NULL for REAL.
        """
        now = datetime.now(timezone.utc).isoformat()
        errors_json = json.dumps(per_source_errors) if per_source_errors is not None else None
        duration_json = json.dumps(per_source_duration) if per_source_duration is not None else None
        await self._conn.execute(
            "INSERT INTO run_log ("
            " timestamp, total_found, new_jobs, sources_queried, per_source,"
            " run_uuid, per_source_errors, per_source_duration,"
            " total_duration, user_id"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                now,
                stats.get("total_found", 0),
                stats.get("new_jobs", 0),
                stats.get("sources_queried", 0),
                json.dumps(stats.get("per_source", {})),
                run_uuid,
                errors_json,
                duration_json,
                total_duration,
                user_id,
            ),
        )
        await self._conn.commit()

    async def get_run_logs(self, limit: int = 100) -> list[dict]:
        cursor = await self._conn.execute(
            "SELECT timestamp, total_found, new_jobs, per_source FROM run_log ORDER BY id DESC LIMIT ?",
            (limit,),
        )
        rows = await cursor.fetchall()
        return [
            {
                "timestamp": row[0],
                "total_found": row[1],
                "new_jobs": row[2],
                "per_source": json.loads(row[3]),
            }
            for row in rows
        ]

    async def get_new_jobs_since(self, hours: int = 12) -> list[dict]:
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        cursor = await self._conn.execute(
            "SELECT * FROM jobs WHERE first_seen >= ? ORDER BY match_score DESC",
            (cutoff,),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def purge_old_jobs(self, days: int = 30) -> int:
        """Delete jobs where first_seen is older than `days` ago. Returns count deleted."""
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        cursor = await self._conn.execute("DELETE FROM jobs WHERE first_seen < ?", (cutoff,))
        await self._conn.commit()
        return cursor.rowcount

    async def get_recent_jobs(self, days: int = 7, min_score: int = 0) -> list[dict]:
        """Return jobs from the last `days` with match_score >= min_score."""
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        cursor = await self._conn.execute(
            "SELECT * FROM jobs WHERE first_seen >= ? AND match_score >= ? ORDER BY date_found DESC",
            (cutoff, min_score),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def get_last_source_counts(self, n: int = 5) -> dict[str, list[int]]:
        """Get per-source job counts from the last N runs for health tracking."""
        cursor = await self._conn.execute("SELECT per_source FROM run_log ORDER BY id DESC LIMIT ?", (n,))
        rows = await cursor.fetchall()
        source_history: dict[str, list[int]] = {}
        for row in rows:
            per_source = json.loads(row[0]) if row[0] else {}
            for name, count in per_source.items():
                source_history.setdefault(name, []).append(count)
        return source_history

    # --- User Actions ---
    #
    # Batch 3.5 Deliverable C: every method now takes user_id and scopes
    # queries by it. Schema UNIQUE(user_id, job_id) is from migration
    # 0002_multi_tenant; this layer is the matching read/write surface.

    async def insert_action(self, job_id: int, action: str, user_id: str, notes: str = "") -> dict:
        now = datetime.now(timezone.utc).isoformat()
        await self._conn.execute(
            """INSERT INTO user_actions (user_id, job_id, action, notes, created_at)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(user_id, job_id)
               DO UPDATE SET action = excluded.action,
                             notes = excluded.notes,
                             created_at = excluded.created_at""",
            (user_id, job_id, action, notes, now),
        )
        await self._conn.commit()
        return {"job_id": job_id, "action": action, "notes": notes, "created_at": now}

    async def delete_action(self, job_id: int, user_id: str) -> None:
        await self._conn.execute(
            "DELETE FROM user_actions WHERE user_id = ? AND job_id = ?",
            (user_id, job_id),
        )
        await self._conn.commit()

    async def get_actions(self, user_id: str) -> list[dict]:
        cursor = await self._conn.execute(
            """SELECT job_id, action, notes, created_at
               FROM user_actions
               WHERE user_id = ?
               ORDER BY created_at DESC""",
            (user_id,),
        )
        return [{"job_id": r[0], "action": r[1], "notes": r[2], "created_at": r[3]} for r in await cursor.fetchall()]

    async def get_action_counts(self, user_id: str) -> dict[str, int]:
        cursor = await self._conn.execute(
            """SELECT action, COUNT(*) FROM user_actions
               WHERE user_id = ? GROUP BY action""",
            (user_id,),
        )
        return {r[0]: r[1] for r in await cursor.fetchall()}

    async def get_action_for_job(self, job_id: int, user_id: str) -> str | None:
        cursor = await self._conn.execute(
            "SELECT action FROM user_actions WHERE user_id = ? AND job_id = ?",
            (user_id, job_id),
        )
        row = await cursor.fetchone()
        return row[0] if row else None

    # --- Applications (Pipeline) ---
    #
    # Batch 3.5 Deliverable C: same user_id-scoping treatment as actions.

    async def create_application(self, job_id: int, user_id: str) -> dict:
        now = datetime.now(timezone.utc).isoformat()
        await self._conn.execute(
            """INSERT OR IGNORE INTO applications
               (user_id, job_id, stage, created_at, updated_at)
               VALUES (?, ?, 'applied', ?, ?)""",
            (user_id, job_id, now, now),
        )
        await self._conn.commit()
        return await self._get_application(job_id, user_id)

    async def advance_application(self, job_id: int, stage: str, user_id: str) -> dict:
        now = datetime.now(timezone.utc).isoformat()
        await self._conn.execute(
            """UPDATE applications SET stage = ?, updated_at = ?
               WHERE user_id = ? AND job_id = ?""",
            (stage, now, user_id, job_id),
        )
        await self._conn.commit()
        return await self._get_application(job_id, user_id)

    async def _get_application(self, job_id: int, user_id: str) -> dict:
        cursor = await self._conn.execute(
            """SELECT a.job_id, a.stage, a.created_at, a.updated_at, a.notes,
                      j.title, j.company
               FROM applications a LEFT JOIN jobs j ON a.job_id = j.id
               WHERE a.user_id = ? AND a.job_id = ?""",
            (user_id, job_id),
        )
        row = await cursor.fetchone()
        if not row:
            return {}
        return {
            "job_id": row[0],
            "stage": row[1],
            "created_at": row[2],
            "updated_at": row[3],
            "notes": row[4] or "",
            "title": row[5] or "",
            "company": row[6] or "",
        }

    async def get_applications(self, user_id: str, stage: str | None = None) -> list[dict]:
        if stage:
            cursor = await self._conn.execute(
                """SELECT a.job_id, a.stage, a.created_at, a.updated_at, a.notes,
                          j.title, j.company
                   FROM applications a LEFT JOIN jobs j ON a.job_id = j.id
                   WHERE a.user_id = ? AND a.stage = ?
                   ORDER BY a.updated_at DESC""",
                (user_id, stage),
            )
        else:
            cursor = await self._conn.execute(
                """SELECT a.job_id, a.stage, a.created_at, a.updated_at, a.notes,
                          j.title, j.company
                   FROM applications a LEFT JOIN jobs j ON a.job_id = j.id
                   WHERE a.user_id = ?
                   ORDER BY a.updated_at DESC""",
                (user_id,),
            )
        return [
            {
                "job_id": r[0],
                "stage": r[1],
                "created_at": r[2],
                "updated_at": r[3],
                "notes": r[4] or "",
                "title": r[5] or "",
                "company": r[6] or "",
            }
            for r in await cursor.fetchall()
        ]

    async def get_application_counts(self, user_id: str) -> dict[str, int]:
        cursor = await self._conn.execute(
            """SELECT stage, COUNT(*) FROM applications
               WHERE user_id = ? GROUP BY stage""",
            (user_id,),
        )
        return {r[0]: r[1] for r in await cursor.fetchall()}

    async def get_stale_applications(self, user_id: str, days: int = 7) -> list[dict]:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        cursor = await self._conn.execute(
            """SELECT a.job_id, a.stage, a.created_at, a.updated_at, a.notes,
                      j.title, j.company
               FROM applications a LEFT JOIN jobs j ON a.job_id = j.id
               WHERE a.user_id = ?
                 AND a.updated_at < ?
                 AND a.stage NOT IN ('offer', 'rejected')
               ORDER BY a.updated_at ASC""",
            (user_id, cutoff),
        )
        return [
            {
                "job_id": r[0],
                "stage": r[1],
                "created_at": r[2],
                "updated_at": r[3],
                "notes": r[4] or "",
                "title": r[5] or "",
                "company": r[6] or "",
            }
            for r in await cursor.fetchall()
        ]

    async def get_job_by_id(self, job_id: int) -> dict | None:
        cursor = await self._conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
        row = await cursor.fetchone()
        if not row:
            return None
        cols = [d[0] for d in cursor.description]
        return dict(zip(cols, row))

    async def close(self):
        if self._conn:
            await self._conn.close()

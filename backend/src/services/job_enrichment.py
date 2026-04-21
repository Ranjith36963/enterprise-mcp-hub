"""Pillar 2 Batch 2.5 — LLM job enrichment pipeline.

Given a `Job`, produces a `JobEnrichment` via the shared Gemini→Groq→Cerebras
provider chain and persists it to the `job_enrichment` table. Idempotent —
a second call on a `job_id` that already has a row is a no-op unless the
caller passes `force=True`.

CLAUDE.md compliance:
  * Rule #4 — no live HTTP calls during tests. Tests inject a mock
    `llm_extract_validated_fn` to avoid touching providers.
  * Rule #10 — `job_enrichment` is a **shared catalog** table (no user_id
    column). Per-user state continues to live in `user_feed` / `user_actions`.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Awaitable, Callable, Optional

import aiosqlite

from src.models import Job
from src.services.job_enrichment_schema import JobEnrichment
from src.services.profile.llm_provider import llm_extract_validated

logger = logging.getLogger("job360.services.job_enrichment")

# Feature flag — plan Appendix B. Default-off behaviour must exactly match
# pre-Batch-2.5 (no enrichment calls, no DB writes).
ENRICHMENT_ENABLED = os.getenv("ENRICHMENT_ENABLED", "false").lower() in {
    "1", "true", "yes", "on"
}


# The callable type of `llm_extract_validated` — declared so test doubles can
# be passed through `_extract_fn` without the import loop that would occur if
# tests patched the module-level function directly.
LLMExtractFn = Callable[[str, type, str], Awaitable[JobEnrichment]]


_SYSTEM_PROMPT = (
    "You are a job-posting structurer. Return ONLY valid JSON matching the "
    "schema. Do not wrap in prose. If a field is unknown, use the explicit "
    "enum value 'unknown' (never omit required fields)."
)


def _build_prompt(job: Job) -> str:
    """Render a concise prompt for the LLM. Truncation keeps token budget
    bounded for weak providers (Cerebras 8K context)."""
    desc = (job.description or "")[:4000]
    return (
        "Extract structured fields from the following job posting and return "
        "JSON matching the JobEnrichment schema.\n\n"
        f"Title: {job.title}\n"
        f"Company: {job.company}\n"
        f"Location: {job.location}\n"
        f"Description:\n{desc}\n"
    )


async def enrich_job(
    job: Job,
    *,
    llm_extract_validated_fn: Optional[LLMExtractFn] = None,
) -> JobEnrichment:
    """Call the LLM to structure a job posting.

    Args:
        job: the job to enrich.
        llm_extract_validated_fn: optional override — tests pass a mock here
            to avoid live HTTP. Defaults to the real
            :func:`llm_extract_validated`.

    Raises:
        RuntimeError: if all LLM providers fail or the response can't be
        validated into the `JobEnrichment` schema after the default retry
        budget. Callers should catch and log; they should NOT use a partial
        enrichment — the row stays absent rather than polluted.
    """
    fn = llm_extract_validated_fn or llm_extract_validated
    prompt = _build_prompt(job)
    enrichment = await fn(prompt, JobEnrichment, _SYSTEM_PROMPT)
    return enrichment


# ---------------------------------------------------------------------------
# Persistence helpers (shared-catalog table, no user_id column — rule #10)
# ---------------------------------------------------------------------------


async def has_enrichment(conn: aiosqlite.Connection, job_id: int) -> bool:
    """True if `job_enrichment` already has a row for this job."""
    cur = await conn.execute(
        "SELECT 1 FROM job_enrichment WHERE job_id = ? LIMIT 1",
        (job_id,),
    )
    row = await cur.fetchone()
    return row is not None


async def save_enrichment(
    conn: aiosqlite.Connection,
    job_id: int,
    enrichment: JobEnrichment,
) -> None:
    """Insert or replace the enrichment row for a given job.

    JSON-serialises every list/nested-model field. Uses `INSERT OR REPLACE`
    so re-enrichment is a clean upsert without requiring a DELETE first.
    """
    await conn.execute(
        """
        INSERT OR REPLACE INTO job_enrichment (
            job_id, title_canonical, category, employment_type, workplace_type,
            locations, salary, required_skills, preferred_skills,
            experience_min_years, experience_level, requirements_summary,
            language, employer_type, visa_sponsorship, seniority,
            remote_region, apply_instructions, red_flags, enriched_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
        """,
        (
            job_id,
            enrichment.title_canonical,
            enrichment.category.value,
            enrichment.employment_type.value,
            enrichment.workplace_type.value,
            json.dumps(enrichment.locations),
            enrichment.salary.model_dump_json(),
            json.dumps(enrichment.required_skills),
            json.dumps(enrichment.preferred_skills),
            enrichment.experience_min_years,
            enrichment.experience_level.value,
            enrichment.requirements_summary,
            enrichment.language,
            enrichment.employer_type.value,
            enrichment.visa_sponsorship.value,
            enrichment.seniority.value,
            enrichment.remote_region,
            enrichment.apply_instructions,
            json.dumps(enrichment.red_flags),
        ),
    )
    await conn.commit()


async def load_enrichment(
    conn: aiosqlite.Connection,
    job_id: int,
) -> Optional[JobEnrichment]:
    """Deserialise an enrichment row back into a `JobEnrichment` model.

    Used by the dedup tiebreaker in `services/deduplicator.py` and by the
    Batch 2.6 embedding builder.
    """
    cur = await conn.execute(
        """
        SELECT title_canonical, category, employment_type, workplace_type,
               locations, salary, required_skills, preferred_skills,
               experience_min_years, experience_level, requirements_summary,
               language, employer_type, visa_sponsorship, seniority,
               remote_region, apply_instructions, red_flags
        FROM job_enrichment
        WHERE job_id = ?
        """,
        (job_id,),
    )
    row = await cur.fetchone()
    if row is None:
        return None
    (
        title_canonical, category, employment_type, workplace_type,
        locations_json, salary_json, required_json, preferred_json,
        experience_min_years, experience_level, requirements_summary,
        language, employer_type, visa_sponsorship, seniority,
        remote_region, apply_instructions, red_flags_json,
    ) = row
    return JobEnrichment(
        title_canonical=title_canonical,
        category=category,
        employment_type=employment_type,
        workplace_type=workplace_type,
        locations=json.loads(locations_json) if locations_json else [],
        salary=json.loads(salary_json) if salary_json else {},
        required_skills=json.loads(required_json) if required_json else [],
        preferred_skills=json.loads(preferred_json) if preferred_json else [],
        experience_min_years=experience_min_years,
        experience_level=experience_level,
        requirements_summary=requirements_summary or "",
        language=language,
        employer_type=employer_type,
        visa_sponsorship=visa_sponsorship,
        seniority=seniority,
        remote_region=remote_region,
        apply_instructions=apply_instructions,
        red_flags=json.loads(red_flags_json) if red_flags_json else [],
    )

import re

from src.models import Job

# Seniority prefixes to strip for fuzzy title matching
_SENIORITY_RE = re.compile(
    r'^(senior|sr\.?|junior|jr\.?|lead|principal|staff|head\s+of)\s+',
    re.IGNORECASE,
)

# Trailing job codes like "- 12345" or "/ REQ-123"
_TRAILING_CODE_RE = re.compile(r'\s*[-/]\s*[A-Z0-9]{2,}[-_]?\d+\s*$', re.IGNORECASE)

# Parentheticals like "(London)" or "(Remote)"
_PAREN_RE = re.compile(r'\s*\([^)]*\)\s*$')


def _normalize_title(title: str) -> str:
    """Normalize a job title for dedup grouping.

    NOTE: This is intentionally MORE aggressive than Job.normalized_key().
    The DB UNIQUE constraint uses normalized_key() (company suffix + lowercase only),
    while dedup uses this function (also strips seniority, job codes, parentheticals).
    This means dedup groups are wider than DB unique keys — by design:
    - Dedup merges "Senior ML Engineer" and "ML Engineer" within a single run
    - DB preserves them as separate records across runs
    Do NOT unify these without a full DB migration (see CLAUDE.md Rule 1).
    """
    t = title.strip()
    t = _TRAILING_CODE_RE.sub('', t)
    t = _PAREN_RE.sub('', t)
    t = _SENIORITY_RE.sub('', t)
    return t.strip().lower()


def _completeness(job: Job) -> int:
    score = 0
    if job.salary_min is not None:
        score += 10
    if job.salary_max is not None:
        score += 10
    if job.description:
        score += min(len(job.description), 20)
    if job.location:
        score += 5
    return score


def _enrichment_bonus(job: Job, enrichments: dict | None) -> int:
    """Pillar 2 Batch 2.5 tiebreaker — reward jobs whose `id` has an LLM
    enrichment row, so when two candidates in a dedup group tie on
    match_score + completeness, the enriched one wins and carries the
    structured fields downstream (scoring, embeddings).

    `enrichments` is a ``dict[int, object]`` (or any truthy mapping) passed
    in by callers that have already loaded enrichments for the candidate
    set. Callers who don't opt in pass ``None`` and this returns 0 —
    preserves pre-Batch-2.5 ordering exactly.
    """
    if not enrichments:
        return 0
    job_id = getattr(job, "id", None)
    return 5 if job_id is not None and job_id in enrichments else 0


def deduplicate(
    jobs: list[Job],
    enrichments: dict | None = None,
) -> list[Job]:
    """Group jobs by normalized (company, title) and keep the best per group.

    Ranking (high → low):
      1. `match_score` — the original Pillar-1 primary key.
      2. enrichment bonus — if `enrichments` is provided and the job has a
         row in it, +5. Encourages the enriched candidate to win a tie.
      3. `_completeness` — salary/description/location fullness.
    """
    if not jobs:
        return []
    groups: dict[tuple[str, str], list[Job]] = {}
    for job in jobs:
        company, _ = job.normalized_key()
        title = _normalize_title(job.title)
        key = (company, title)
        groups.setdefault(key, []).append(job)
    result = []
    for group in groups.values():
        best = max(
            group,
            key=lambda j: (
                j.match_score,
                _enrichment_bonus(j, enrichments),
                _completeness(j),
            ),
        )
        result.append(best)
    return result

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Problem-Solving Integrity

Fix root causes, never patch symptoms. No silent workarounds.

**NEVER:**
- Bare `try/except` to silence errors
- Skip or delete failing tests
- Hardcode values to bypass logic
- Suppress warnings with `noqa` / `type: ignore`

**When stuck:** State the root cause before writing any fix. After 3 failed attempts, stop and ask — don't force a workaround.

**Always:** Run relevant tests after a fix. Explain what was wrong and why the fix is correct.

## Project Overview

Job360 is an automated UK job search system supporting **any professional domain**. Aggregates jobs from 50 sources, scores them 0-100 against a user profile, deduplicates, and delivers via CLI/email/Slack/Discord/CSV/Streamlit dashboard. A user profile with CV is **mandatory** — no CV = no search. All keywords come from the user's profile via `SearchConfig`. No hard-coded domain defaults.

## Commands

```bash
# Run
python -m src.cli run                              # Full pipeline
python -m src.cli run --source arbeitnow           # Single source
python -m src.cli run --dry-run --log-level DEBUG   # Debug mode
python -m src.cli run --no-email                    # Skip notifications
python -m src.cli run --safe                        # Safe mode: API+RSS only, no scrapers

# Profile
python -m src.cli setup-profile --cv path/to/cv.pdf
python -m src.cli setup-profile --cv cv.pdf --linkedin export.zip --github username

# Other
python -m src.cli dashboard                        # Streamlit UI
python -m src.cli status                           # Last run stats
python -m src.cli sources                          # List all 50 sources
python -m src.cli view --hours 24 --min-score 50   # Browse jobs
python -m src.cli pipeline --reminders             # Application tracking

# Validation & QA Benchmark
python -m src.cli validate                         # Validate last 7d, 3 per source
python -m src.cli validate --days 14 --per-source 5  # Deeper check, wider window
python -m src.cli validate --source greenhouse     # Single source deep-check
python -m src.cli validate --min-score 40          # Only validate decent matches

# Tests (all HTTP mocked via aioresponses)
python -m pytest tests/ -v                         # All 843 tests (3 skip on Windows)
python -m pytest tests/test_scorer.py -v           # Single file
python -m pytest tests/test_scorer.py::test_name -v  # Single test

# Automation tests (WP1)
python -m pytest tests/test_circuit_breaker.py -v  # Circuit breaker (10 tests)
python -m pytest tests/test_robots_checker.py -v   # robots.txt (5 tests)
python -m pytest tests/test_evidence.py -v         # Evidence tagging (7 tests)
python -m pytest tests/test_deal_breakers.py -v    # Deal-breakers (5 tests)
python -m pytest tests/test_safe_mode.py -v        # Safe mode (5 tests)

# E2E browser tests (Playwright — excluded from default runs)
python -m pytest tests/e2e/ --no-header -v         # All 15 E2E tests
python -m pytest tests/e2e/ --headed --slowmo 500  # Debug with visible browser

# Validation
python scripts/validate_rules.py                   # Checks 3 core rules (pure stdlib)
```

## Architecture

### Full Pipeline (in execution order)

```
CLI (Click) → Orchestrator (src/main.py)
  1. load_profile() → UserProfile (returns early if no CV)
  2. generate_search_config(profile) → SearchConfig
  3. _build_sources(session, search_config, safe_mode) → 50 source instances (--safe excludes 7 scrapers)
  4. Load persistent source_health from DB → pre-skip sources in cooldown
  5. asyncio.gather → all sources safe_fetch(db) concurrently (rate-limited, persistent circuit-breaker, 60s timeout)
  6. Foreign filter: is_foreign_only() hard-removes non-UK jobs
  7. Short description filter: skip scoring for <100 char descriptions (broken scrapes)
  8. Embeddings: all-MiniLM-L6-v2 encodes job text → 384-dim vectors
  9. JD parse: parse_jd(description, user_skills) → skills/experience/salary(daily/hourly/OTE)/emails
 10. Detailed 8D score: scorer.score_detailed(job, parsed_jd, cv_data) → with evidence reasons
     Deal-breakers: negative title → cap at 15, excluded company → zero-out
 11. Feedback: liked/rejected history adjusts score ±10
 12. Rerank: cross-encoder (ms-marco-MiniLM-L-6-v2) re-scores top-50
 13. Dedup: two-pass — normalized key, then description similarity ≥ 0.80 (with text normalization)
 14. Per-source quality metrics: fetched/above_threshold/stored per source
 15. Store: SQLite + FTS5 sync → Notifications + Reports + CSV
```

### Key Modules

| Module | Purpose |
|--------|---------|
| `src/main.py` | Orchestrator: `run_search()`, `SOURCE_REGISTRY` dict, `_build_sources()` |
| `src/config/settings.py` | Env vars, paths, `RATE_LIMITS`, `MIN_MATCH_SCORE=30` |
| `src/config/keywords.py` | Domain-agnostic only: `LOCATIONS`, `VISA_KEYWORDS`, `KNOWN_SKILLS`, `KNOWN_TITLE_PATTERNS` |
| `src/config/companies.py` | ATS company slugs (104 companies across 10 platforms) |
| `src/profile/models.py` | `CVData`, `UserPreferences`, `UserProfile`, `SearchConfig` dataclasses |
| `src/profile/keyword_generator.py` | `generate_search_config(UserProfile)` → `SearchConfig` |
| `src/profile/skill_graph.py` | Skill inference graph: 210 relationships, 563 edges |
| `src/sources/base.py` | `BaseJobSource` ABC — `_get_json()`, `_get_text()`, `safe_fetch()` (circuit breaker), `_gather_queries()` (parallel batch), `_relevance_match()` |
| `src/filters/skill_matcher.py` | `JobScorer` class: `score()` (legacy) + `score_detailed()` (8D), `is_foreign_only()` |
| `src/filters/description_matcher.py` | 424 synonym groups for fuzzy skill matching |
| `src/filters/embeddings.py` | Bi-encoder (all-MiniLM-L6-v2, 384-dim), profile embedding includes about_me |
| `src/filters/jd_parser.py` | JD parsing: skills/experience/salary(daily/hourly/OTE)/emails, profile-aware via `user_skills` |
| `src/storage/database.py` | Async SQLite (aiosqlite), schema v7, 7 tables (incl. `source_health`) |
| `src/llm/client.py` | Multi-provider LLM pool: Groq, Cerebras, Gemini, DeepSeek, OpenRouter, SambaNova |
| `src/diagnostics.py` | `PipelineDiagnostics` — timing, score distribution, funnel, per-source stats |

### Scoring

**Legacy `score()`:** Title 0-40 + Skill 0-40 + Location 0-10 + Recency 0-10. Penalties: negative titles (-30), foreign location (-15).

**Detailed `score_detailed()`** (8 dimensions, overwrites legacy in pipeline):

| Dimension | Max | What |
|-----------|-----|------|
| Role | 15 | Title match — word-overlap scoring with core domain word weighting |
| Skill | 20 | Skill overlap with synonym matching |
| Seniority | 10 | Experience level alignment (prefers user-stated over CV-inferred) |
| Experience | 10 | Years requirement vs CV |
| Credentials | 5 | Degree/certification match |
| Location | 10 | Geographic match + work arrangement bonus (±2 for remote/onsite pref) |
| Recency | 10 | Posting freshness |
| Semantic | 20 | Embedding cosine similarity + industry mention bonus (+2) |

**Penalties:** negative title keywords (-30 + hard ceiling at 15), negative description keywords (-15), excluded skills (-5/match, cap -15), excluded companies (zero-out).

**Evidence:** Each dimension produces a `*_reason` string in `match_data` JSON explaining why it scored that value (e.g., `"JD=senior, You=mid, gap=1 → 7/10"`).

### Profile → SearchConfig Flow

```
UserProfile
  ├─ cv_data (raw_text, skills, job_titles, education, certifications)
  ├─ preferences (target_titles, additional_skills, locations, ...)
  └─ [optional] LinkedIn + GitHub enrichment
        │
        ▼ keyword_generator.generate_search_config()
  SearchConfig
  ├─ job_titles: prefs.titles + cv.titles (deduped)
  ├─ primary_skills: ALL proven (CV + prefs + LinkedIn + GitHub), secondary_skills: inferred by skill graph
  ├─ relevance_keywords: lowercased words from titles + skills + industries + domains
  ├─ negative_title_keywords: from prefs.negative_keywords
  ├─ locations: UK defaults + prefs.preferred_locations
  ├─ core_domain_words / supporting_role_words: from title analysis
  ├─ search_queries: 3 types (title×location, skill-combo, title+skill hybrid), capped at 15
  ├─ excluded_skills: from prefs.excluded_skills
  ├─ work_arrangement: from prefs ("remote"/"hybrid"/"onsite")
  ├─ target_experience_level: from prefs (overrides CV-inferred)
  ├─ about_me: from prefs (used in profile embedding)
  ├─ industries: from prefs (relevance keywords + scoring bonus)
  ├─ detected_domains: auto-detected from profile via domain_detector
  └─ excluded_companies: from prefs (zero-out score for these companies)
```

Profile completeness: `is_complete` requires `cv_data.raw_text` OR `target_job_titles` OR `additional_skills`.

### Sources: 50 Total

All extend `BaseJobSource`, use `self.relevance_keywords`/`self.job_titles`/`self.search_queries` from SearchConfig. When `search_config=None`, these return `[]`.

- **7 keyed APIs** (Reed, Adzuna, JSearch, Jooble, GoogleJobs, Careerjet, Findwork) — accept `api_key`, return `[]` if missing
- **10 free APIs** (Arbeitnow, RemoteOK, Jobicy, Himalayas, Remotive, DevITJobs, LandingJobs, AIJobs, TheMuse, NoFluffJobs)
- **10 ATS boards** (Greenhouse, Lever, Workable, Ashby, SmartRecruiters, Pinpoint, Recruitee, Workday, Personio, SuccessFactors)
- **10 RSS/XML** (jobs.ac.uk, NHS, WorkAnywhere, WeWorkRemotely, RealWorkFromAnywhere, BioSpace, UniJobs, FindAJob, Jobspresso, PythonJobs)
- **7 HTML scrapers** (LinkedIn, JobTensor, Climatebase, 80KHours, BCSJobs, AIJobsGlobal, AIJobsAI)
- **5 other** (HackerNews, HNJobs, YCCompanies, JobSpy/Glassdoor, Nomis) — note: `glassdoor` is a registry alias for `JobSpySource` (same class as `indeed`)
- **1 market intel** (Nomis/ONS vacancy statistics)

### Database (schema v7)

7 tables: `jobs` (with `job_type`, `match_data`, `embedding` columns), `jobs_fts` (FTS5 virtual table), `run_log`, `user_actions`, `applications`, `schema_version`, `source_health` (persistent circuit breaker). Dedup via `UNIQUE(normalized_company, normalized_title)`.

## Workflow — Read, Write, Verify

Every code change must follow this order:

1. **Read & Explore** — Before editing ANY file, read it fully. Understand what the code does, how it connects to the rest of the system. Never edit blind. When working with any library or framework (Streamlit, aiohttp, Click, aiosqlite, sentence-transformers, etc.), use **Context7 MCP** to fetch the latest documentation so you're coding with up-to-date APIs, not outdated knowledge.
2. **Write** — Make the change (implementation, bug fix, refactor, whatever).
3. **Test & Verify** — After completing a logical change, run the relevant tests. Confirm they pass. Then update any affected MD files (CLAUDE.md, STATUS.md, ARCHITECTURE.md, etc.) if facts changed (test count, source count, scoring rules, architecture).

This is non-negotiable. No shortcuts.

## Core Rules (see RULES.md for detail)

1. **All keywords dynamic and personalized** — nothing hard-coded, no static imports; everything from the job seeker's profile via SearchConfig
2. **CV mandatory** — no CV = no search. Preferences, LinkedIn, GitHub are primary inputs.
3. **Single scoring path** — only `JobScorer(config).score()` and `JobScorer(config).score_detailed()`

## Important Patterns

- **Adding a source:** See `SOURCES.md` — 9-step checklist + 5 templates (free/keyed/ATS/RSS/scraper). Touches 5-7 files including `main.py` (import + registry + `_build_sources`), `settings.py` (rate limits), `test_sources.py`, `test_main.py` (`_mock_free_sources`), `test_cli.py` (registry count)
- **Dynamic keywords:** `self.relevance_keywords`, `self.job_titles`, `self.search_queries` — empty when no config
- **Keyed source:** Accept `api_key` + `search_config=None` in `__init__`, return `[]` if no key
- **No CV = no search:** `main.py` returns early if no profile loaded
- **BaseJobSource helpers:** `_get_json()` (2 retries, exp backoff), `_get_text()`, `_post_json()`, `safe_fetch(db)` (persistent circuit breaker — skips after 3 failures, exponential cooldown 1hr→6hr→24hr persisted to DB), `_gather_queries()` (parallel batch), robots.txt compliance (cached per domain)
- **Speed tuning:** `REQUEST_TIMEOUT=15s`, `MAX_RETRIES=2`, `RETRY_BACKOFF=[1,3]`, per-source timeout=60s. Slow sources (AIJobsGlobal, JobSpy) use `_gather_queries(batch_size=3)` for concurrent fetching.
- **Testing patterns:** See `TESTING.md` — `_TEST_CONFIG`, `_patch_profile()`, `aioresponses` mocking, `_run()` async helper, `_mock_free_sources()` for integration tests
- **Shared fixtures** (`tests/conftest.py`): `sample_ai_job`, `sample_unrelated_job`, `sample_duplicate_jobs`, `sample_visa_job`

## Environment

- Python 3.9+, deps in `requirements.txt` (prod) / `requirements-dev.txt` (test)
- `.env` for API keys (see `.env.example`); 43 of 50 sources work without keys
- Data: `data/` (gitignored) — `jobs.db`, `user_profile.json`, `exports/`, `reports/`, `logs/`
- CI: `.github/workflows/tests.yml` — pytest on push/PR (Python 3.9/3.11/3.13)
- 3 tests skip on Windows (bash-only tests for `setup.sh` and `cron_run.sh`)

## Tools

### MCP Servers

- **Context7** — Fetches latest library/framework documentation. **When to use**: During explore/plan stages whenever you're about to write code that uses a library (Streamlit, aiohttp, Click, aiosqlite, sentence-transformers, etc.). Always check Context7 before assuming API syntax — outdated knowledge causes first-attempt failures.
- **SQLite** — Direct SQL queries on `data/jobs.db`. **When to use**: When inspecting actual job data, debugging scoring results, checking run history, verifying DB state, or answering questions about stored jobs. Tables: `jobs`, `run_log`, `user_actions`, `applications`, `schema_version`, `jobs_fts`, `source_health`.

## Live Debugging

When the user reports issues ("it's stuck", "dashboard crashed", "scores look wrong"), check these outputs:

- `data/logs/job360.log` — pipeline: source fetching, scoring, dedup, DB, `PIPELINE_HEALTH` JSON summary
- `data/logs/dashboard.log` — Streamlit: profile save, search trigger, UI errors
- `data/exports/*.csv` — per-job scores, URLs, salary, visa
- `data/reports/*.md` — per-source funnel (fetched→filtered→scored→stored)

During testing sessions, use `tail -f` via `run_in_background` on both log files. The user does not need to paste logs — pull them directly.

### Known slow sources

- `aijobs_global` — WordPress AJAX, parallelized (batch_size=3, capped at 5 queries)
- `indeed` (JobSpy) — blocking scraper, parallelized (batch_size=3, capped at 4 queries)
- `linkedin` — anti-ban delays, 1.5s between queries

## QA & Validation

Quality depends on **three independent pillars** — when something fails, diagnose WHICH pillar and WHY:

1. **Pillar 1 — CV Parsing:** Is the parser extracting skills/titles/education correctly? Fix the parser, not the engine.
2. **Pillar 2 — Source Data:** Is each source providing clean data? Validate via `python -m src.cli validate`. Per-source confidence = URL(0.30) + Title(0.25) + Date(0.25) + Description(0.20). Target: 90%+.
3. **Pillar 3 — Match Engine:** Given correct inputs, are results relevant? Fix scoring/synonyms/embeddings.

**Benchmark:** `data/reports/BENCHMARK.md` (living doc, updated each iteration). Focus on free sources first (43 of 50).

**Known limitations:** Workday URLs expire in 1-4 hours (session-based). Some sites (climatebase, weworkremotely) block bots with 403s. Many sites lack parseable posting dates.

## Related Documentation

| File | Unique Purpose |
|------|---------------|
| `RULES.md` | Invariant rules — "What must NEVER change?" |
| `TESTING.md` | Test patterns — "How do I write/run tests?" |
| `SOURCES.md` | Source patterns — "How do I add/modify sources?" (also `/add-source` skill) |
| `CHANGELOG.md` | Version history — "What changed and when?" |
| `FUTURE_PLAN.md` | Startup roadmap — FastAPI → Next.js → Deploy → Multi-user → Monetize |

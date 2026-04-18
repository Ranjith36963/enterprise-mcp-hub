# CurrentStatus.md — Job360 Technical Audit

**Method.** Audit built by reading code only. No trust in CLAUDE.md / memory. Every claim anchored `file:line`.
**Last full re-audit.** 2026-04-18 (commit `d364e9d`).
**Style.** Telegraphic. Grammar sacrificed for density. Facts > prose.

> **How to read this file.** Skim §§1–4 for shape. Jump to `grep -n '^###'` by topic. Appendix A is the anchor index — use it when CLAUDE.md disagrees with code.

---

## 1. Project Overview

- **Scope.** Automated UK job aggregator. Any professional domain (not just tech).
- **Stack.** Python 3.9+ backend (FastAPI + aiohttp + aiosqlite) + Next.js 16 frontend.
- **Deployables.** `backend/` (Python) + `frontend/` (Next.js). Runtime data in `backend/data/` (gitignored).
- **Inputs.** CV (PDF/DOCX) + LinkedIn profile PDF + GitHub username → dynamic `SearchConfig`.
- **Output channels.** CLI, FastAPI, email, Slack, Discord, CSV, Next.js frontend.
- **Source count.** 48 `SOURCE_REGISTRY` entries, 47 unique source files (indeed/glassdoor share `JobSpySource`).
- **Dedup.** Async SQLite, WAL, `UNIQUE(normalized_company, normalized_title)`, auto-purge >30d.
- **Scoring.** Title(40)+Skill(40)+Location(10)+Recency(10) − penalties. `MIN_MATCH_SCORE=30`.

### Recent commits (shaping current state)

- `d364e9d` — rm obsolete FastAPI plan + stock frontend README
- `bd106c6` — post-Streamlit cleanup + audit/planning docs
- `f5c82e1` — **Streamlit dashboard removed** (plus plotly dep)
- `decef88` — LinkedIn ZIP ingest → LinkedIn profile PDF parser
- `b2f747e` — phase 4 clean-architecture layout (`config/` → `core/`, `filters/` → `services/`, etc.)

---

## 2. Architecture — Three Pillars

```
Pillar 1: Profile Parser      Pillar 2: Search/Match Engine      Pillar 3: Job Provider Layer
─────────────────────         ──────────────────────────         ──────────────────────────
CV (PDF/DOCX) → LLM ─┐                                           47 sources (async fetch)
LinkedIn PDF   → LLM ├──► UserProfile → SearchConfig ──► Scoring (JobScorer) ──► Jobs table
GitHub user    → API ┘                                  Dedup
```

- **Pillar 1.** LLM-only CV parser. Fallback chain Gemini → Groq → Cerebras (all free tier). Regex/`KNOWN_SKILLS` path deleted (`3ba1342`, `804725c`).
- **Pillar 2.** `JobScorer` (`src/services/skill_matcher.py:294`) dynamic via `SearchConfig`; `score_job()` (`:231`) is fallback using hard-coded defaults from `core/keywords.py` (now empty lists).
- **Pillar 3.** 47 sources inherit `BaseJobSource`. Currently under multi-batch rebuild — see `docs/IMPLEMENTATION_LOG.md`.

### Scoring details

`src/services/skill_matcher.py`
- Weights L18–21. Visa detection `check_visa_flag()` L243 w/ negation filter L86–99.
- Negative title keyword penalty **−30** L191.
- Foreign-location penalty **−15** L195–211.
- `MIN_MATCH_SCORE = 30` (`core/settings.py:44`).
- Recency bands: ≤1d → 10pt · ≤3d → 7pt · ≤7d → 4pt · else → 0pt (assumes honest `date_found` — see §5).

### Dedup details

- `Job.normalized_key()` in `src/models.py:45–58`. Strips `ltd|inc|corp|llc|gmbh|plc|...` + region suffixes `uk|us|de|emea|...`. Lowercases.
- `Deduplicator._normalize_title()` `src/services/deduplicator.py:18–33` strips seniority (Sr/Jr), job codes, parentheticals — **intentionally wider than the DB UNIQUE key**.
- DB constraint `UNIQUE(normalized_company, normalized_title)` `src/repositories/database.py:41`.

---

## 3. Pipeline — End-to-End Flow

```
CLI / FastAPI
   │
   ▼
src/main.py :: run_search()
   │   load_profile → generate_search_config
   ▼
_build_sources(session)              ← 47 instances, TCPConnector(limit=30, per_host=5)
   │
   ▼
asyncio.gather(source.fetch_jobs() for s in sources)      # :299 — no semaphore
   │
   ▼
score_job() / JobScorer.score()      :343
   │
   ▼
deduplicate()                        :348
   │
   ▼
filter min_score ≥ MIN_MATCH_SCORE   :352
   │
   ▼
JobDatabase.insert_job()             INSERT OR IGNORE
   │
   ▼
NotificationChannel.send() × {email, slack, discord} + html/md report + csv export
```

### Per-source concurrency

- `RATE_LIMITS` dict (`core/settings.py`): 48 entries, each `{concurrent, delay}`.
- `RateLimiter` instantiated per source in `BaseJobSource.__init__` (`src/sources/base.py:55–56`).
- Retry: `MAX_RETRIES=3`, `RETRY_BACKOFF=[1,2,4]s`, `REQUEST_TIMEOUT=30s`.

### Helpers on `BaseJobSource`

- `_get_json()` L144 · `_post_json()` L148 · `_get_text()` L152 · all delegate to `_request()`.
- Dynamic keyword props L58–74: `relevance_keywords`, `job_titles`, `search_queries` — fall back to (now-empty) `core/keywords.py` when no `SearchConfig`.
- `_is_uk_or_remote()` L31–45: checks UK_TERMS, REMOTE_TERMS, FOREIGN_INDICATORS.

---

## 4. Data Model

### `Job` dataclass — `src/models.py:17–58`

| Field | Type | Default | Notes |
|---|---|---|---|
| title | str | — | HTML-unescaped, "nan"/"None" → "Unknown" (L33–43) |
| company | str | — | same cleanup |
| apply_url | str | — | NOT NULL in DB |
| source | str | — | — |
| date_found | datetime | — | **Fabricated for 39/47 sources — see §5** |
| location | str | `""` | — |
| salary_min / salary_max | float \| None | None | sanity: min <10k → null, max >500k → null (GBP-assumed) |
| description | str | `""` | — |
| match_score | int | 0 | set by scorer post-hoc |
| visa_flag | bool | False | `check_visa_flag()` output |
| is_new | bool | True | ⚠️ **Not persisted to DB** |
| experience_level | str | `""` | — |

### User-profile models — `src/services/profile/models.py`

- `CVData` L10–48 — scoring fields (skills, titles, companies, education, certifications) + display fields (name, headline, location, achievements) + LinkedIn fields (positions, skills, industry) + GitHub fields (languages, topics, inferred skills).
- `UserPreferences` L52–65 — target_job_titles, additional_skills, excluded_skills, preferred_locations, industries, salary_min/max, work_arrangement, experience_level, negative_keywords, about_me, github_username.
- `UserProfile` L68–79 — wraps `CVData` + `UserPreferences`. `is_complete` iff raw_text OR (target_job_titles OR additional_skills).
- `SearchConfig` L83–117 — job_titles + primary/secondary/tertiary_skills + relevance_keywords + negative_title_keywords + locations + visa_keywords + core_domain_words + supporting_role_words + search_queries. `from_defaults()` returns empty skill lists.

### Storage

- JSON at `backend/data/user_profile.json` (`src/services/profile/storage.py:15–46`).
- LinkedIn PDF parser: `linkedin_parser.py` — pdfplumber text extraction, section split. Detects `linkedin.com/in/` URL + ≥3 known headings + "Page N of M" footer. Silent ImportError fallback if pdfplumber missing.

---

## 5. `date_found` Audit — Why Recency Is Broken

### Headline numbers

- **Fabricators.** 39/47 sources (83%) hardcode `datetime.now()` when source payload lacks real timestamp. 61 total `datetime.now()` call sites.
- **Real-date sources (~8/47).** `careerjet`, `findwork`, `jsearch`, `landingjobs`, `nofluffjobs`, `reed`, `recruitee`, `remotive` (partial).
- **Wrong-field sources (3).**
  - `apis_keyed/jooble.py:49` — uses `item.get("updated")` (mutation date, not post date).
  - `ats/greenhouse.py:40` — uses `item.get("updated_at")` (edit date, not creation).
  - `feeds/nhs_jobs.py:57` + fallbacks L105/L111 — uses `closingDate` (posting *deadline*, not post date).

### Consequence

- Recency 10-pt band inflates for fabricated dates (every fabricated job = "≤1 day" → +10).
- Ghost-listing detection impossible — no reliable `first_seen` vs `posted_at` delta.
- `date_reliability_ratio` estimated ~60–65%.

### Full fabricator list (audit 2026-04-18)

`apis_free/`: aijobs, arbeitnow, devitjobs, himalayas, hn_jobs, jobicy, landingjobs (fallback), remoteok, remotive (fallback), yc_companies
`apis_keyed/`: adzuna, careerjet (fallback), findwork (fallback), google_jobs (×3 call sites), jooble, jsearch (fallback), reed (fallback)
`ats/`: ashby, greenhouse, lever, personio, pinpoint, recruitee, smartrecruiters, successfactors, workable, workday (×4 sites)
`feeds/`: biospace, findajob, jobs_ac_uk, nhs_jobs (×2), realworkfromanywhere, uni_jobs, weworkremotely, workanywhere
`scrapers/`: aijobs_ai, aijobs_global, bcs_jobs, climatebase, eightykhours, jobtensor, linkedin
`other/`: hackernews, indeed, nofluffjobs (fallback), nomis, themuse

### Batch-1 plan (reference)

See `docs/research/pillar_3_batch_1.md` — 5-column date model (`posted_at`, `first_seen_at`, `last_seen_at`, `last_updated_at`, `date_confidence`) + per-source fixes + ghost-detection state machine.

---

## 6. Database Layer — `src/repositories/database.py`

### Init (L21–22)

- WAL mode + `busy_timeout=5000ms`. aiosqlite async connection.

### Tables

**`jobs`** L24–42 — 15 columns: id(PK), title, company, location, salary_min, salary_max, description, apply_url, source, date_found, match_score, visa_flag, experience_level, **normalized_company**, **normalized_title**, first_seen.
- `UNIQUE(normalized_company, normalized_title)`.
- ⚠️ `Job.is_new` **NOT** persisted.
- Indexes L51–53: `idx_jobs_date_found`, `idx_jobs_first_seen`, `idx_jobs_match_score`.

**`run_log`** L43–50 — id(PK), timestamp, total_found, new_jobs, sources_queried, per_source (JSON blob).

**`user_actions`** L54–61 — id(PK), job_id, action, notes, created_at. `UNIQUE(job_id)` → one action per job (INSERT OR REPLACE overwrites).

**`applications`** L62–70 — id(PK), job_id, stage (default `'applied'`), notes, created_at, updated_at. `UNIQUE(job_id)`. Stages (from `src/api/routes/pipeline.py`): `applied → outreach → interview → offer → rejected`.

### Migrations

- `_migrate()` L75–97 — `table_info` diff + append-column. Current migration list empty. `salary_currency` commented out.
- **No schema-version tracking.** No alembic.

### Inserts & purge

- `insert_job()` L114–132 — `INSERT OR IGNORE` using `normalized_key()`. Returns bool (rowcount).
- `purge_old_jobs(days=30)` L183–190 — `DELETE FROM jobs WHERE first_seen < cutoff`. **No `ON DELETE CASCADE`** → orphan rows in `user_actions` / `applications`.

### CSV export — `src/repositories/csv_export.py`

- Headers L8–11: job_title, company, location, salary, match_score, apply_url, source, date_found, visa_flag. ⚠️ `experience_level` missing.
- `_format_salary()` L14–21 — "min-max" / "min" / "max" / "". No currency symbol.
- Atomic write via `mkstemp → rename` L24–49.

---

## 7. API Layer — `backend/src/api/`

### App — `main.py`

- FastAPI v1.0.0 + lifespan (`init_db`/`close_db`).
- **CORS hardcoded** `allow_origins=["http://localhost:3000"]` (L20) — ⚠️ breaks on any other origin.
- All routers prefixed `/api`. 6 router imports.

### Dependencies — `dependencies.py`

- Global `JobDatabase` singleton. `get_db()` DI. `save_upload_to_temp()` for file uploads.

### Pydantic models — `models.py` (15 schemas)

HealthResponse, StatusResponse, SourcesResponse, JobResponse (with 8-dim score breakdown), JobListResponse, ActionRequest/Response, ProfileSummary, CVDetail, ProfileResponse, LinkedInResponse, GitHubResponse, SearchStartResponse, SearchStatusResponse, PipelineApplication, PipelineListResponse, PipelineAdvanceRequest, PipelineRemindersResponse.

### Routes — 22 endpoints across 6 files

**`health.py`**
- `GET /health` → HealthResponse
- `GET /status` → StatusResponse
- `GET /sources` → SourcesResponse

**`jobs.py`**
- `GET /jobs` — filters: hours, min_score, source, bucket, action, visa_only
- `GET /jobs/{id}`
- `GET /jobs/export` — CSV stream

**`actions.py`**
- `POST /jobs/{id}/action`
- `DELETE /jobs/{id}/action`
- `GET /actions`
- `GET /actions/counts`

**`profile.py`**
- `GET /profile`
- `POST /profile` — upsert
- `POST /profile/linkedin` — PDF upload
- `POST /profile/github` — username

**`search.py`**
- `POST /search` — async, returns `run_id`
- `GET /search/{run_id}/status` — poll

**`pipeline.py`**
- `GET /pipeline` — stage filter
- `GET /pipeline/counts`
- `GET /pipeline/reminders` — ≥7d stale
- `POST /pipeline/{id}` — create
- `POST /pipeline/{id}/advance`

### ⚠️ Gaps

- No auth. No rate-limiting middleware. Endpoints unprotected.
- CORS single-origin; frontend env drifts = instant 403.

---

## 8. Frontend — `frontend/src/`

- **Stack.** Next.js **16.2.2**, React **19.2.4**, TypeScript 5, Tailwind CSS 4, shadcn/ui v4.1.2, Lucide, motion 12, recharts.
- **Data fetching.** Native `fetch`. No SWR/TanStack. Client-side useState. Search polling via `setInterval(3s)`.
- **API client.** `lib/api.ts:22` — base URL `NEXT_PUBLIC_API_URL || "http://localhost:8000"`. No `.env` in repo.
- **Types.** `lib/types.ts` — 18 interfaces 1:1 with backend Pydantic models.

### Pages (App Router)

- `/` — landing (hero, stats, 3-step flow, CTAs).
- `/dashboard` — jobs UI: search, filters, time buckets, grid, polling search status.
- `/profile` — CV upload + preferences form + LinkedIn/GitHub enrichment + completeness %.
- `/pipeline` — Kanban (5 columns: applied/outreach/interview/offer/rejected) + stats + 7-day stale reminders.
- `/jobs/[id]` — detail w/ 8-dim radar, skill gaps, match reasons, like/dismiss/apply actions.

### Components — 13 project + 14 shadcn/ui

- jobs/: FilterPanel, JobCard, JobList, ScoreCounter, ScoreRadar, TimeBuckets
- profile/: CVUpload, CVViewer, PreferencesForm
- pipeline/: KanbanBoard
- layout/: Navbar, Footer, FloatingIcons
- ui/: badge, button, card, dialog, input, label, select, separator, sheet, skeleton, slider, tabs, textarea, tooltip

### Styling

- Tailwind 4 + globals (aurora glows, score badges).
- Animations: fade-in-up, stagger, shimmer. No CSS-in-JS.

---

## 9. Notifications — `backend/src/services/notifications/`

- **ABC.** `NotificationChannel` `base.py:11–24` — `is_configured()` + `send(jobs, stats, **kwargs)`.
- **Registry.** `get_all_channels()` returns `[EmailChannel, SlackChannel, DiscordChannel]`.

| Channel | File | Gated by env |
|---|---|---|
| Email | `email_notify.py:82–91` | `SMTP_EMAIL`, `SMTP_PASSWORD`, `NOTIFY_EMAIL` (Gmail SMTP, HTML + CSV attach) |
| Slack | `slack_notify.py:95–104` | `SLACK_WEBHOOK_URL` (Block Kit, top 10 + source summary) |
| Discord | `discord_notify.py:75–84` | `DISCORD_WEBHOOK_URL` (embeds, top 10) |

### Reports — `report_generator.py`

- `generate_html_report()` — buckets 24h / 24–48h / 48–72h / 3–7d, colour-coded tables, score+salary+visa.
- `generate_markdown_report()` — same buckets, markdown tables.

---

## 10. Configuration — `backend/src/core/`

### `settings.py` (112 lines)

- **Paths.** `BASE_DIR`, `DATA_DIR`, `DB_PATH`, `EXPORTS_DIR`, `REPORTS_DIR`, `LOGS_DIR`.
- **API keys (8).** REED, ADZUNA_APP_ID/KEY, JSEARCH, JOOBLE, SERPAPI, CAREERJET_AFFID, FINDWORK.
- **LLM providers (3).** GEMINI, GROQ, CEREBRAS. ⚠️ CEREBRAS missing from `.env.example`.
- **Email (5).** SMTP_HOST, SMTP_PORT, SMTP_EMAIL, SMTP_PASSWORD, NOTIFY_EMAIL.
- **Webhooks (2).** SLACK_WEBHOOK_URL, DISCORD_WEBHOOK_URL.
- **Search.** `MIN_MATCH_SCORE=30`, `MAX_RESULTS_PER_SOURCE=100`, `MAX_DAYS_OLD=7`.
- **Salary target.** `TARGET_SALARY_MIN=40000`, `TARGET_SALARY_MAX=120000`.
- **Retry.** `MAX_RETRIES=3`, `RETRY_BACKOFF=[1,2,4]`, `REQUEST_TIMEOUT=30`.
- **RATE_LIMITS dict.** 48 entries.

### `keywords.py` (73 lines)

- **Primary / Secondary / Tertiary / Relevance lists are EMPTY** (removed 2026-04-09 — dynamic from user CV required).
- `LOCATIONS` — 25 UK cities + Remote/Hybrid.
- `VISA_KEYWORDS` — 8 phrases (visa sponsorship, tier 2, skilled worker visa, …).

### `companies.py` (124 lines) — 104 ATS slugs total

| ATS | Slugs | Sample |
|---|---|---|
| Greenhouse | 25 | deepmind, monzo, anthropic, stripe, databricks |
| Workday | 15 | NVIDIA, Shell, Roche, HSBC, Barclays (dict with URL) |
| Lever | 12 | mistral, palantir, spotify |
| Personio | 10 | celonis, trade-republic, contentful |
| Ashby | 9 | anthropic, cohere, openai, elevenlabs, perplexity |
| Recruitee | 8 | peak-ai, signal-ai, causaly |
| Pinpoint | 8 | starling-bank, octopus-energy, arm, sky, tesco-technology |
| SmartRecruiters | 6 | wise, revolut, astrazeneca |
| Workable | 8 | benevolentai, huggingface, runway |
| SuccessFactors | 3 | BAE Systems, QinetiQ, Thales UK (dict) |

- `COMPANY_NAME_OVERRIDES` — 20 slug→display mappings (e.g. `darktracelimited → Darktrace`, `transferwise → Wise`).

### `.env.example` — 27 vars

API keys (8) · Email (3) · LLM (2 — **CEREBRAS missing**) · GitHub (1) · Search ranges (2) · Webhooks (2) · remaining = optional toggles.

---

## 11. Dependencies

### Backend — `pyproject.toml` (Python ≥3.9)

- **Main (14).** aiohttp, aiosqlite, python-dotenv, jinja2, click, pandas, pdfplumber, python-docx, rich, humanize, fastapi, uvicorn[standard], python-multipart, httpx, google-generativeai, groq, cerebras-cloud-sdk.
- **Dev (4).** pytest, pytest-asyncio, aioresponses, fpdf2.
- **Tooling.** ruff (py39, 120 char, rules E/F/W/I/N/UP/S/B/G, no S101) · mypy (py39, warn_return_any, ignore_missing_imports) · pytest (pythonpath=["."], asyncio_mode=auto).
- **Optional.** `python-jobspy` (Indeed/Glassdoor) — skip-graceful if missing.

### Frontend — `package.json`

- **Main (10).** next 16.2.2, react 19.2.4, react-dom 19.2.4, @base-ui/react, class-variance-authority, clsx, lucide-react, motion 12.38, recharts, shadcn, tailwind-merge, tw-animate-css.
- **Dev (5).** typescript ^5, eslint ^9, eslint-config-next 16.2.2, @tailwindcss/postcss ^4, tailwindcss ^4.
- **Scripts.** dev, build, start, lint.

---

## 12. Test Suite — `backend/tests/`

- **Total.** 410 tests across **20 files**. All HTTP mocked via `aioresponses`.
- `conftest.py` — 7 fixtures (sample_ai_job, sample_unrelated_job, sample_duplicate_jobs, sample_visa_job, sample_non_uk_job, sample_empty_description_job, …).
- `e2e/` — empty dir. `qa_profiles/` — test fixtures (CVs + PDFs), not test runners.

| File | Tests |
|---|---:|
| test_sources.py | 71 |
| test_linkedin_github.py | 58 |
| test_profile.py | 55 |
| test_scorer.py | 53 |
| test_time_buckets.py | 33 |
| test_models.py | 21 |
| test_notifications.py | 19 |
| test_deduplicator.py | 13 |
| test_main.py | 12 |
| test_cli.py | 11 |
| test_database.py | 9 |
| test_api.py | 9 |
| test_llm_provider.py | 8 |
| test_notification_base.py | 7 |
| test_reports.py | 6 |
| test_setup.py | 6 |
| test_cron.py | 5 |
| test_cli_view.py | 5 |
| test_rate_limiter.py | 5 |
| test_csv_export.py | 4 |

**Run command.** `cd backend && python -m pytest tests/ -v`.
⚠️ Baseline pass/fail count **pending** — record in `docs/IMPLEMENTATION_LOG.md` before Batch 1.

---

## 13. Known Issues & Bugs (Code-Observed)

### Critical

1. **39/47 sources fabricate `date_found` via `datetime.now()`** — see §5. Poisons recency scoring + blocks ghost-listing detection. → Batch 1.
2. **Wrong `date_found` field in 3 sources** — jooble (`updated`), greenhouse (`updated_at`), NHS (`closingDate`). → Batch 1.
3. **Twice-daily cron broken** (per prior audit / `docs/research/pillar_3_batch_3.md`). Tiered polling replacement → Batch 3.
4. **No multi-user support** — single `user_profile.json`, single SQLite DB. → Batch 2.

### High

5. **CORS hardcoded** `localhost:3000` (`api/main.py:20`) — any frontend deploy breaks.
6. **`Job.is_new` not persisted to DB** (`models.py` vs `database.py:24–42`).
7. **No CASCADE delete** on `purge_old_jobs` → orphan rows in `user_actions` / `applications`.
8. **CSV export missing `experience_level`** column.
9. **CEREBRAS_API_KEY in `settings.py` but not in `.env.example`** (drift).
10. **LinkedIn parser silent-fallback on `pdfplumber` ImportError** — no user-visible error if pdfplumber missing.
11. **Salary sanity bounds (10k/500k) assume GBP** — silently nulls valid USD/EUR values.

### Medium

12. **Unbounded `asyncio.gather` in `run_search()`** (`main.py:299`) — no semaphore, 47 sources racing connection pool (TCPConnector limit=30).
13. **`RATE_LIMITS` dict has 48 entries but `_build_sources()` creates 47** — one phantom entry.
14. **Dedup is wider than DB UNIQUE key** — deduplicator strips seniority/job codes, DB does not → mid-pipeline dedup removes rows the DB would have accepted.

### Low

15. **Channel registry hard-wired** to `[Email, Slack, Discord]` in `get_all_channels()` — not env-driven.
16. **Report buckets hard-coded** (24h/24–48h/48–72h/3–7d).

---

## 14. Infrastructure

- **Backend entry.** `backend/main.py` → uvicorn → `src/api/main.py`.
- **CLI.** `python -m src.cli {run|setup-profile|status|sources|view}`.
- **Setup.** Root `setup.sh` — Python 3.9 check, venv, `.env` template, pip install.
- **Cron.** Root `cron_setup.sh` — installs crontab (4 AM & 4 PM UK), runs `src/main.py`. ⚠️ Broken per §13 #3.
- **Pre-commit.** `.pre-commit-config.yaml` — ruff, ruff-format, trailing-whitespace.
- **No Docker / docker-compose / GitHub Actions.** No Vercel/Railway config files in repo.
- **Frontend build.** `npm run dev | build | start | lint`. `next.config.ts` empty boilerplate.

---

## 15. Dead Code / Phase-4 Debris

Post-phase-4 rename left empty package dirs (`__pycache__` only — source files gone):

| Dir | Status | Real code moved to |
|---|---|---|
| `backend/src/filters/` | empty `__pycache__` | `src/services/skill_matcher.py` + `src/services/deduplicator.py` |
| `backend/src/llm/` | empty `__pycache__` | `src/services/profile/llm_provider.py` |
| `backend/src/pipeline/` | empty `__pycache__` | (never existed — stale cache) |
| `backend/src/validation/` | empty `__pycache__` | (never existed — stale cache) |

**Pre-flight for Batch 1.** `rm -rf backend/src/{filters,llm,pipeline,validation}` to stop import ambiguity.

No `TODO` / `FIXME` / `HACK` comments in `src/`. No circular imports detected (late-imports in profile parsers guard against).

---

## Appendix A — file:line anchor index

| Topic | Anchor |
|---|---|
| Orchestrator entry | `backend/src/main.py` — `run_search()` + `SOURCE_REGISTRY` + `_build_sources()` L131, gather L299, score L343, dedup L348, filter L352 |
| Base source | `backend/src/sources/base.py:31` (_is_uk_or_remote), L55 (ratelimiter), L58–74 (keyword props), L144/148/152 (get_json/post_json/get_text) |
| Scorer (dynamic) | `backend/src/services/skill_matcher.py:294` (JobScorer.score) |
| Scorer (fallback) | `backend/src/services/skill_matcher.py:231` (score_job) |
| Weights | `backend/src/services/skill_matcher.py:18–21` |
| Negative-title penalty | `backend/src/services/skill_matcher.py:191` (−30) |
| Foreign-loc penalty | `backend/src/services/skill_matcher.py:195–211` (−15) |
| Visa detection | `backend/src/services/skill_matcher.py:243` + negation L86–99 |
| Dedup | `backend/src/services/deduplicator.py:18–33` |
| Normalized key | `backend/src/models.py:45–58` |
| Job dataclass | `backend/src/models.py:17–58` |
| DB init (WAL) | `backend/src/repositories/database.py:21–22` |
| DB jobs table | `backend/src/repositories/database.py:24–42` |
| UNIQUE constraint | `backend/src/repositories/database.py:41` |
| DB indexes | `backend/src/repositories/database.py:51–53` |
| run_log table | `backend/src/repositories/database.py:43–50` |
| user_actions table | `backend/src/repositories/database.py:54–61` |
| applications table | `backend/src/repositories/database.py:62–70` |
| Migrations | `backend/src/repositories/database.py:75–97` |
| Insert | `backend/src/repositories/database.py:114–132` |
| Purge | `backend/src/repositories/database.py:183–190` |
| CSV headers | `backend/src/repositories/csv_export.py:8–11` |
| CORS | `backend/src/api/main.py:20` |
| API routes | `backend/src/api/routes/{health,jobs,actions,profile,search,pipeline}.py` |
| Frontend API client | `frontend/src/lib/api.ts:22` |
| Frontend types | `frontend/src/lib/types.ts` |
| Notification ABC | `backend/src/services/notifications/base.py:11–24` |
| Settings | `backend/src/core/settings.py` — MIN_MATCH_SCORE L44, RATE_LIMITS dict |
| Keywords (empty) | `backend/src/core/keywords.py` |
| ATS slugs | `backend/src/core/companies.py` |
| date_found jooble | `backend/src/sources/apis_keyed/jooble.py:49` |
| date_found greenhouse | `backend/src/sources/ats/greenhouse.py:40` |
| date_found nhs | `backend/src/sources/feeds/nhs_jobs.py:57` (+ L105, L111 fallbacks) |
| LinkedIn parser | `backend/src/services/profile/linkedin_parser.py:1–50` |
| Profile storage | `backend/src/services/profile/storage.py:15–46` |
| Profile models | `backend/src/services/profile/models.py:10–117` |

# CurrentStatus.md — Job360 Codebase Honest Mirror

**Method.** Audit built by 8 parallel Explore subagents reading code only. No trust in CLAUDE.md, memory, or prior audit. Every claim anchored `file:line`.
**Last full re-audit.** 2026-04-19 (commit `ac90bae`)
**Prior audit.** 2026-04-19 (commit `fad1744`) — see `CurrentStatus_diff.md` for what changed and which prior claims were false.

---

## §1 — Overview

Job360. UK-focused multi-domain job aggregator. Python 3.9+ FastAPI backend + Next.js 16 frontend. Multi-user delivery layer (Batch 2) + tiered polling (Batch 3) + IDOR/ARQ/scheduler stabilisation (Batch 3.5) shipped.

**Tree skeleton:**

| Path | Files | Notes |
|---|---|---|
| `backend/src/` | 122 .py | 5 root + 12 submodules |
| `backend/src/api/` | 14 | FastAPI routes + auth deps |
| `backend/src/services/` | 31 | Primary business logic module |
| `backend/src/sources/` | 57 (49 sources + base + 6 dirs + 1 init) | 50 entries in SOURCE_REGISTRY (indeed handles 2) |
| `backend/src/core/` | 5 | settings, keywords, companies |
| `backend/src/repositories/` | 3 | database.py + csv_export |
| `backend/src/workers/` | 3 | tasks.py + settings.py + __init__ |
| `backend/src/utils/` | 4 | logger, rate_limiter, time_buckets |
| `backend/migrations/` | 11 | 5 migration pairs + runner |
| `backend/tests/` | 44 (43 test files + conftest) | 596 collected |
| `frontend/src/` | 39 | Next.js 16 App Router, 8 pages |
| `docs/` | 18 | plans + reviews + status |

**Recent 10 commits (newest first):**
- `ac90bae` Merge Batch 3.5: Stabilisation (IDOR + ARQ + Scheduler wiring)
- `f6c589e` docs(pillar3): Batch 3.5 completion entry
- `328e72f` feat(scheduler): wire TieredScheduler into run_search
- `f910ea7` feat(workers): implement send_notification + WorkerSettings
- `56a66f3` fix(api): scope per-user routes by user_id (IDOR)
- `f8cf829` docs(pillar3): Batch 3.5 plan
- `fad1744` Merge Batch 3: Tiered Polling + Source Expansion
- `65fafc5` fix(review-response): Batch 3 P2 + P3
- `31965cd` docs(pillar3): Batch 3 completion entry + CLAUDE.md appendix
- `c62b98b` chore(registry): rotate source count 48 → 50

---

## §2 — Architecture (Scoring + Matching)

**Scoring components** (4-component model, 0–100 + penalties), `backend/src/services/skill_matcher.py`:

| Component | Weight | Anchor |
|---|---|---|
| Title match | 0–40 | `:18` (`TITLE_WEIGHT`) |
| Skill match | 0–40 | `:19` (`SKILL_WEIGHT`); `SKILL_CAP = SKILL_WEIGHT` `:27` |
| Location | 0–10 | `:20` |
| Recency | 0–10 | `:21` |
| Negative title penalty | −30 | `:215–220` |
| Foreign location penalty | −15 | `:223–239` |

Final clamp `[0,100]` at `:268`. `MIN_MATCH_SCORE = 30` at `core/settings.py:44`.

**Recency priority** (`recency_score_for_job` `:195–212`):
1. `date_confidence == "fabricated"` → return 0 (`:205`)
2. `posted_at` + trustworthy confidence (high/medium/repost_backdated) → full band (`:207–208`)
3. `posted_at` + low confidence → fall back to `date_found` capped at 60% (`:209–211`)
4. No `posted_at` + has `date_found` → 60% band (`:210–211`)
5. Neither → 0 (`:212`)

**Two scoring paths:**
- Module-level `score_job(job)` `:259–268` — hard-coded fallback when no profile (logs error at startup)
- `JobScorer(config).score(job)` `:322–331` — production path, uses `SearchConfig`. Selected at `main.py:316` (`scorer = JobScorer(search_config)`), called at `main.py:433`.

**Visa detection** `:271–273` (module) + `:333–335` (instance) — both call `_has_visa_keyword()` `:94–99` honoring `_VISA_NEGATIONS` `:86–91`.

**Prefilter cascade** (`backend/src/services/prefilter.py`):
1. Location + work-arrangement (`location_ok` `:56–83`)
2. Experience level ±1 band (`experience_ok` `:86–113`)
3. Skill overlap (`skill_overlap_ok` `:116–123`)
- Combined: `passes_prefilter` `:126–131` (AND). SQL-cheap; `JobScorer.score()` only on survivors.

**Dedup** (`backend/src/services/deduplicator.py`):
- `deduplicate()` `:49–62` groups by `(normalized_company, _normalize_title)`. `_normalize_title` `:18–33` strips seniority prefixes + job codes — **intentionally wider than DB UNIQUE** (DB constraint preserves "Senior X" vs "X" as separate rows).
- DB UNIQUE at `database.py:49` matches `Job.normalized_key()` at `models.py:61–65` (company suffix + lowercase). Consistent.

**Pillar 2 absent.** Grep evidence:
- `sentence_transformers` / `chromadb` / `pgvector` / `cosine_similarity` → 0 hits
- `cross.encoder` / `BM25` / `rerank` → 0 hits
- LLM enrichment of job posts → 0 hits (LLM is CV-only)

System is pure keyword-matching until Pillar 2 commences.

---

## §3 — Pipeline

**Flow:** `run_search()` (`main.py:279`) → load profile → build sources → **TieredScheduler** → ghost detection → score → dedup → DB writes → notifications.

**Scheduler wiring (HOT PATH, no longer asyncio.gather):**
- Imported `main.py:26`
- Instantiated + dispatched `main.py:363–364`:
  ```python
  scheduler = TieredScheduler(sources, registry)
  paired = await scheduler.tick(force=True)
  ```
- Breaker registry consulted before each tick (`scheduler.py:114–122`); OPEN sources skip dispatch; success/failure auto-recorded (`scheduler.py:140–144`).
- Post-dispatch breaker logging at `main.py:380–384`.

**Breaker registry adoption.** All 49 sources registered in `default_breaker_registry()` `main.py:360`.

**Conditional cache adoption: ZERO.** `_get_json_conditional()` defined in `sources/base.py:158–205` but not called by any of 49 sources. Pure dead path on the source side.

**Ghost detection completeness gate** `main.py:144–187`:
- Triggered post-scheduler `main.py:425` `_ghost_detection_pass(db, sources, results, history)`
- 70% rolling-7d completeness threshold gates absence sweep (rate-limit safety). If source returns < 0.7× rolling avg → skip sweep.
- Otherwise: `update_last_seen` for observed (`:179`) + `mark_missed_for_source` for absent (`:180`).

**Repost detection ABSENT.** No `sentence_transformers`, no `embedding`, no LLM scoring path. Dedup syntactic only (`models.py:61–65`).

---

## §4 — Data Model

**`Job` dataclass** (`backend/src/models.py:18–65`):

Required: `title, company, apply_url, source, date_found`
Defaults:
- `location: str = ""`, `salary_min/max: Optional[float] = None`, `description: str = ""`
- `match_score: int = 0`, `visa_flag: bool = False`, `is_new: bool = True`, `experience_level: str = ""`
- **Pillar 3 Batch 1 fields:**
  - `posted_at: Optional[str] = None` — source-claimed posting date
  - `date_confidence: str = "low"` — enum: high/medium/low/fabricated/repost_backdated
  - `date_posted_raw: Optional[str] = None` — audit-only

`__post_init__`: HTML unescape, company sanitisation (rejects nan/None/n/a), salary sanity (<10k → None, >500k → None).
`normalized_key()` `:61–65` returns `(company_suffix_stripped, title_lowercased)`.

**Profile dataclasses** (`backend/src/services/profile/models.py`):
- `CVData` `:10–48` — raw_text, skills, job_titles, companies, education, certs, summary, experience_text + display fields + LinkedIn (positions, skills, industry) + GitHub (languages dict, topics, inferred_skills)
- `UserPreferences` `:52–65` — target titles, additional/excluded skills, locations, industries, salary, work_arrangement, experience_level, negative_keywords, github_username, about_me
- `UserProfile` `:68–80` — cv_data + preferences; `is_complete` checks raw_text OR (job_titles OR skills)
- `SearchConfig` `:83–117` — job_titles, primary/secondary/tertiary_skills, relevance_keywords, negative_title_keywords, locations, visa_keywords, core_domain_words set, supporting_role_words set, search_queries. `from_defaults()` returns empty config + LOCATIONS + VISA_KEYWORDS only.

---

## §5 — Date Field Audit

**Schema semantics:**
- `database.py:34` — `date_found TEXT NOT NULL` = **crawl timestamp**, always `datetime.now(...)`
- `database.py:41` — `posted_at TEXT` = real upstream posting date (NULL allowed)
- `database.py:45` — `date_confidence TEXT DEFAULT 'low'` enum
- `database.py:46` — `date_posted_raw TEXT` audit field

**49 source files audited.** Buckets:

**HONEST-EXTRACTED (36)** — extracts real upstream date into `posted_at` with variable `confidence`:
- Free APIs (10): arbeitnow, devitjobs, gov_apprenticeships, himalayas, hn_jobs, jobicy, landingjobs, remoteok, remotive, teaching_vacancies, aijobs
- Keyed APIs (5): adzuna, careerjet, findwork, jsearch, reed, google_jobs
- ATS (8): ashby, comeet, lever, recruitee, rippling, smartrecruiters, workday
- Feeds (7): biospace, jobs_ac_uk, nhs_jobs_xml, realworkfromanywhere, workanywhere, weworkremotely, uni_jobs
- Scrapers (1): eightykhours
- Other (3): hackernews, indeed, themuse, nofluffjobs

**HONEST-NULL (13)** — `posted_at=None` + `date_confidence="low"` (upstream lacks reliable date):
- Keyed APIs (1): jooble (drops `updated` field, kept in `date_posted_raw`)
- ATS (5): greenhouse (drops `updated_at` for audit), personio, pinpoint, successfactors, workable
- Feeds (1): nhs_jobs (closingDate is deadline, not post date)
- Scrapers (6): aijobs_ai, aijobs_global, bcs_jobs, climatebase, jobtensor, linkedin

**FABRICATING (0).** No source sets `posted_at = datetime.now(...)`. Batch 1 redefinition fully honoured.

**Earlier audit's "44 fabricators" claim was wrong** — counted `date_found = now_iso` (which is correct post-Batch-1 semantics) instead of grepping the new `posted_at` consumer field.

---

## §6 — Database Layer

**Connection** (`database.py:18–23`): WAL mode + `busy_timeout=5000` + `aiosqlite.Row` factory.

**Tables:**

| Table | CREATE anchor | Notes |
|---|---|---|
| `jobs` | `database.py:24–50` | UNIQUE `(normalized_company, normalized_title)`; 5 indexes (date_found, first_seen, match_score, staleness_state, last_seen_at) |
| `run_log` | `database.py:51–58` | per_source JSON column |
| `user_actions` | rebuilt `0002_multi_tenant.up.sql:22–39` | UNIQUE `(user_id, job_id)`; FK→users CASCADE; placeholder UUID default |
| `applications` | rebuilt `0002_multi_tenant.up.sql:42–61` | UNIQUE `(user_id, job_id)`; FK→users CASCADE |
| `users` | `0001_auth.up.sql:2–8` | id PK, email UNIQUE, password_hash, deleted_at |
| `sessions` | `0001_auth.up.sql:10–18` | FK→users CASCADE; idx_sessions_user, idx_sessions_expires |
| `user_feed` | `0003_user_feed.up.sql:4–28` | UNIQUE `(user_id, job_id)`; status enum active/skipped/stale/applied; 3 partial indexes (dashboard / notify / job) |
| `notification_ledger` | `0004_notification_ledger.up.sql:4–18` | UNIQUE `(user_id, job_id, channel)` — idempotency; idx user/status, idx job |
| `user_channels` | `0005_user_channels.up.sql:11–22` | FK→users CASCADE; credential_encrypted BLOB (Fernet); key_version DEFAULT 1; enabled INT |
| `_schema_migrations` | `runner.py:50–58` | id PK (NNNN_name stem) + applied_at UTC |

**`jobs` Pillar-3-Batch-1 columns** (lines 40–48): posted_at, first_seen_at, last_seen_at, last_updated_at, date_confidence (DEFAULT 'low'), date_posted_raw, consecutive_misses (DEFAULT 0), staleness_state (DEFAULT 'active').

**Migration runner** (`backend/migrations/runner.py:49–133`):
- Lexical discovery of `.up.sql`/`.down.sql` pairs
- `up()` reads pending, executes via `executescript()`, records stem + UTC timestamp
- `down()` reverses most recent applied
- `status()` returns `{applied, pending}`
- No transaction grouping per migration (each file independent)

**Legacy auto-migration path** `database.py:85–114`: ALTER-TABLE-add 8 columns if missing (forward-compat baseline). Validates names + types via regex/whitelist.

**Multi-user note.** All user-scoped tables keyed by `user_id` TEXT. **Profile storage still single-file** at `backend/data/user_profile.json` (`services/profile/storage.py:15`) — multi-user profiles NOT YET implemented. `jobs` shared catalog (CLAUDE.md rule #10).

---

## §7 — API

**30 endpoints** across 8 route modules:

| Module | Count | Auth status |
|---|---|---|
| `health.py` | 3 | 3 public |
| `jobs.py` | 3 | 3 require_user ✓ (Batch 3.5) |
| `actions.py` | 4 | 4 require_user ✓ (Batch 3.5) |
| `pipeline.py` | 5 | 5 require_user ✓ (Batch 3.5) |
| **`profile.py`** | **4** | **0 require_user — UNAUTHENTICATED ⚠️** |
| **`search.py`** | **2** | **0 require_user — UNAUTHENTICATED ⚠️** |
| `auth.py` | 4 | 2 public (register/login), 2 mixed |
| `channels.py` | 4 | 4 require_user ✓ |

**Endpoint listing (METHOD PATH — auth — anchor):**

Health: `GET /api/health` `:16` · `GET /api/status` `:21` · `GET /api/sources` `:43`

Jobs (require_user): `GET /api/jobs/export` `:69` · `GET /api/jobs` `:112` · `GET /api/jobs/{job_id}` `:184`

Actions (require_user): `POST /api/jobs/{job_id}/action` `:15` · `DELETE /api/jobs/{job_id}/action` `:34` · `GET /api/actions` `:44` · `GET /api/actions/counts` `:57`

Pipeline (require_user): `GET /api/pipeline` `:40` · `GET /api/pipeline/counts` `:53` · `GET /api/pipeline/reminders` `:65` · `POST /api/pipeline/{job_id}` `:77` · `POST /api/pipeline/{job_id}/advance` `:91`

**Profile (UNAUTH):** `GET /api/profile` `:57` · `POST /api/profile` `:66` · `POST /api/profile/linkedin` `:123` · `POST /api/profile/github` `:146`

**Search (UNAUTH):** `POST /api/search` `:19` · `GET /api/search/{run_id}/status` `:37`

Auth: `POST /api/auth/register` `:55` (public) · `POST /api/auth/login` `:78` (public) · `POST /api/auth/logout` `:100` (optional cookie) · `GET /api/auth/me` `:114` (require_user)

Channels (require_user): `GET /api/settings/channels` `:44` · `POST /api/settings/channels` `:65` · `DELETE /api/settings/channels/{channel_id}` `:89` · `POST /api/settings/channels/{channel_id}/test` `:106`

**IDOR risk — STILL OPEN on profile + search.** Batch 3.5 fixed jobs/actions/pipeline; profile.py + search.py overlooked. Anyone unauthenticated can POST CV data, trigger LinkedIn/GitHub merges, kick off search runs, and enumerate run_ids.

---

## §8 — Frontend

**Stack** (`frontend/package.json`):
- next 16.2.2 · react 19.2.4 · react-dom 19.2.4
- tailwindcss ^4 · @tailwindcss/postcss ^4
- shadcn 4.1.2 · @base-ui/react 1.3.0 · lucide-react 1.7.0 · recharts 3.8.1
- clsx 2.1.1 · class-variance-authority 0.7.1
- **No** TanStack Query / React Query

**Pages under `frontend/src/app/`** (8):
- `/` (root) · `/dashboard` · `/jobs/[id]` · `/pipeline` · `/profile`
- `/(auth)/login` · `/(auth)/register` · `/settings/channels`

**Component groupings** (`frontend/src/components/`):
- `jobs/` (list/card/filter) · `pipeline/` (stages) · `profile/` (CV upload + LinkedIn/GitHub) · `layout/` (nav/header) · `ui/` (shadcn primitives)

**API client** (`frontend/src/lib/api.ts`): 29 of 30 backend endpoints called. Coverage strong; profile/upload calls lack explicit auth headers (relies on cookies — works fine, but profile API itself isn't gated).

**SSE / WebSocket: ABSENT.** Grep: `EventSource` 0 · `WebSocket` 0 · `text/event-stream` 0. Search uses HTTP polling via `getSearchStatus(runId)`.

---

## §9 — Notifications (Legacy CLI Path)

`NotificationChannel` ABC at `services/notifications/base.py:11`. Auto-discovery `get_all_channels()` `:38`; gating `get_configured_channels()` `:46`; shared `format_salary()` `:27`.

| Channel | Class anchor | Env gate |
|---|---|---|
| Email | `email_notify.py:82` | SMTP_HOST/PORT/EMAIL/PASSWORD/NOTIFY_EMAIL |
| Slack | `slack_notify.py:95` | SLACK_WEBHOOK_URL |
| Discord | `discord_notify.py:75` | DISCORD_WEBHOOK_URL |

Report generator `report_generator.py`: `generate_html_report()` `:88` (HTML inline CSS, time bucketing 24h/24-48h/48-72h/3-7d, top 10/bucket); `generate_markdown_report()` `:33` (unused).

---

## §9b — Delivery Layer (Batch 2+)

**Apprise dispatcher** (`services/channels/dispatcher.py`):
- Lazy import preserved: `_get_apprise_cls()` `:26`, module-level `_apprise` cache `:23`
- `load_user_channels()` `:42` reads `user_channels` (decrypts via Fernet)
- `dispatch()` `:72` loops enabled channels, calls `ap.add(url)` + `_notify_async()` `:113` (prefers `ap.async_notify()`, sync fallback)
- `test_send()` `:125` — two-layer ownership check (HTTP route + service)

**Fernet crypto** (`services/channels/crypto.py`):
- `encrypt()` `:37` returns bytes · `decrypt()` `:41` catches `InvalidToken` → `ValueError`
- Key from `CHANNEL_ENCRYPTION_KEY` env (`:27`); fail-closed if unset
- `key_version` column exists (`0005:17`) but rotation logic NOT IMPLEMENTED

**FeedService** (`services/feed.py:47`):

| Method | Anchor | Purpose |
|---|---|---|
| `list_for_user` | `:60` | Dashboard: active rows, score DESC, limit 200 |
| `list_pending_notifications` | `:82` | Worker: unsent + active + score ≥ threshold, limit 15 |
| `mark_notified` | `:106` | Batch write `notified_at` |
| `update_status` | `:117` | Write `status` enum |
| `cascade_stale` | `:128` | Ghost detection: mark all users' rows stale per job |
| `upsert_feed_row` | `:141` | Idempotent (user, job) upsert; returns row id |

**Worker tasks** (`backend/src/workers/tasks.py`):

| Task | Anchor | Notes |
|---|---|---|
| `score_and_ingest` | `:46` | Pre-filter + score all users, upsert feed, queue notifications above threshold |
| `send_notification` | `:199` | Dispatch all enabled channels, write ledger sent/failed |
| `mark_ledger_sent_task` | `:284` | ARQ wrapper for `mark_ledger_sent` `:156` |
| `mark_ledger_failed_task` | `:293` | ARQ wrapper for `mark_ledger_failed` `:171` |

Helpers (not ARQ functions): `_record_ledger_if_new` `:141` · `idempotency_key` (per CLAUDE.md, helper not task).

**WorkerSettings** (`backend/src/workers/settings.py:80`):
```python
functions = [score_and_ingest, send_notification,
             mark_ledger_sent_task, mark_ledger_failed_task]
```
4 entries. `redis_settings` derived from `REDIS_URL` env. Lazy `arq.connections.RedisSettings` import at `:74` keeps pytest Redis-free.

**send_notification body summary** (`:199–281`): fetches job context (title/company/apply_url) → formats title + body → calls dispatcher (test hook or lazy real) → loops results → records ledger row idempotently → updates ledger sent/failed → returns `{sent, failed}` dict. Idempotency from `notification_ledger` UNIQUE `(user_id, job_id, channel)`.

**Gaps:**
- Quiet hours: ABSENT (grep 0)
- Digest aggregation: STUB only (`urgency` param accepted at `:203`, no batching logic)
- Telegram: SCHEMA-READY (`tgram://` in `0005:8`, format stub `:66`); no handler class
- Webhook: SCHEMA-READY (`json://` in `0005:9`, format stub `:68`); no handler class
- SMS: ABSENT
- Direct Redis client: NONE — all enqueue via ARQ ctx

---

## §10 — Config

**Env vars** (`backend/src/core/settings.py`):

| Var | Required? | Default | Used by | Anchor |
|---|---|---|---|---|
| REED/ADZUNA/JSEARCH/JOOBLE/SERPAPI/CAREERJET/FINDWORK keys | No | "" | sources | `:15–22` |
| GITHUB_TOKEN | No | "" | profile enrichment | `:25` |
| GEMINI_API_KEY / GROQ_API_KEY / CEREBRAS_API_KEY | No | "" | CV LLM providers | `:28–30` |
| SMTP_EMAIL/PASSWORD/NOTIFY_EMAIL | No | "" | email channel | `:35–37` |
| SLACK_WEBHOOK_URL · DISCORD_WEBHOOK_URL | No | "" | channels | `:40–41` |
| TARGET_SALARY_MIN/MAX | No | 40k/120k | tiebreaker | `:49–50` |
| **SESSION_SECRET** | **Yes (prod)** | dev fallback | `auth_deps.py:45` | — |
| **CHANNEL_ENCRYPTION_KEY** | **Yes (prod)** | — (raises if missing) | `crypto.py:27` | — |
| FRONTEND_ORIGIN | No | `http://localhost:3000` | CORS | `api/main.py:59` |
| REDIS_URL | No | `redis://localhost:6379` | workers | `workers/settings.py:42` |

**.env.example drift:** `CEREBRAS_API_KEY` defined in settings.py but missing from `.env.example`.

**Constants:** `MIN_MATCH_SCORE=30` `:44` · `MAX_RESULTS_PER_SOURCE=100` `:45` · `MAX_DAYS_OLD=7` `:46` · `MAX_RETRIES=3` `:109` · `RETRY_BACKOFF=[1,2,4]` `:110` · `REQUEST_TIMEOUT=30` `:113` · `RATE_LIMITS` (50 entries) `:53–106`.

**`keywords.py` state — domain lists EMPTIED** (2026-04-09 LLM-driven decision):
- JOB_TITLES, PRIMARY_SKILLS, SECONDARY_SKILLS, TERTIARY_SKILLS, RELEVANCE_KEYWORDS, NEGATIVE_TITLE_KEYWORDS — **all `[]`** at `:16–21`
- Retained domain-agnostic: LOCATIONS (25 entries `:28–55`), VISA_KEYWORDS (8 entries `:63–72`)

**`companies.py` ATS slug counts (266 total):**

| Platform | Count | Anchor |
|---|---|---|
| Greenhouse | 80 | `:4–30` |
| Lever | 35 | `:34–46` |
| Workable | 25 | `:50–60` |
| Ashby | 25 | `:64–74` |
| SmartRecruiters | 15 | `:78–85` |
| Pinpoint | 15 | `:89–96` |
| Recruitee | 20 | `:100–108` |
| Workday | 20 (tenant dicts) | `:112–134` |
| Personio | 18 | `:216–224` |
| SuccessFactors | 3 sitemaps | `:229–234` |
| Rippling | 5 | `:240–246` |
| Comeet | 5 | `:251–257` |
| **Total** | **266** | — |

(MEMORY claimed 268 — actual is 266.)

---

## §11 — Deps

**Backend** (`backend/pyproject.toml`):
- Core: aiohttp ≥3.9 · aiosqlite ≥0.19 · python-dotenv ≥1.0 · fastapi ≥0.115 · uvicorn[standard] ≥0.30 · httpx ≥0.27
- Data/CV: pdfplumber ≥0.10 · python-docx ≥1.1 · pandas ≥2.0 · jinja2 ≥3.1
- LLM: google-generativeai ≥0.8 · groq ≥0.11 · cerebras-cloud-sdk ≥1.0
- Auth/security (Batch 2): argon2-cffi ≥23.1 · itsdangerous ≥2.2 · cryptography ≥42.0 · email-validator ≥2.1
- Notifications: apprise ≥1.7
- CLI/UX: click ≥8.1 · rich ≥13.0 · humanize ≥4.9
- Optional dev: pytest, pytest-asyncio, aioresponses, fpdf2
- Optional indeed: python-jobspy

**Frontend** key versions: see §8.

---

## §12 — Tests

**43 test files · 596 collected.** Baseline run excludes `test_main.py` (12 tests; JobSpy live-HTTP leak ~32-min hang).

| File | Tests | Coverage |
|---|---|---|
| `test_sources.py` | 81 | All 50 source connectors (mocked HTTP) |
| `test_scorer.py` | 60 | Scoring components, penalties, visa, recency |
| `test_time_buckets.py` | 33 | Bucketing logic |
| `test_models.py` | 22 | Job dataclass, normalisation, salary sanity |
| `test_notifications.py` | 19 | Email/Slack/Discord delivery |
| `test_prefilter.py` | 15 | Location/exp/skill cascade |
| `test_date_schema.py` | 13 | Date parsing + buckets |
| `test_deduplicator.py` | 13 | Dedup grouping + suffix stripping |
| `test_main.py` | 12 | **EXCLUDED — JobSpy live HTTP** |
| `test_cli.py` | 11 | CLI commands |
| `test_ghost_detection.py` | 11 | Stale detection state machine |
| `test_database.py` | 9 | Schema + migrations + history |
| `test_api.py` | 9 | Routing + response models |
| `test_api_idor.py` | 8 | Cross-tenant access denial (Batch 3.5) |
| `test_auth_routes.py` | 8 | Register/login/logout/me |
| `test_feed_service.py` | 8 | FeedService methods |
| `test_llm_provider.py` | 8 | LLM CV-parser providers |
| `test_worker_tasks.py` | 8 | Async task execution |
| `test_channels_dispatcher.py` | 7 | Apprise routing |
| `test_channels_routes.py` | 7 | Channel CRUD |
| `test_circuit_breaker.py` | 7 | State machine |
| `test_kpi_exporter.py` | 7 | KPI exporter (Batch 1) |
| `test_notification_base.py` | 7 | ABC + format_salary |
| `test_reports.py` | 6 | Report generation |
| `test_scheduler.py` | 6 | TieredScheduler |
| `test_setup.py` | 6 | setup.sh validation |
| `test_auth_passwords.py` | 4 | argon2id |
| `test_auth_sessions.py` | 5 | Session lifecycle |
| `test_channels_crypto.py` | 4 | Fernet |
| `test_companies_slugs.py` | 4 | ATS catalog rule |
| `test_conditional_fetch.py` | 4 | ConditionalCache |
| `test_csv_export.py` | 4 | CSV format |
| `test_cli_view.py` | 5 | Rich table |
| `test_cron.py` | 5 | cron_setup.sh |
| `test_rate_limiter.py` | 5 | Async limiter |
| `test_migrations.py` | 5 | Migration runner |
| `test_worker_send_notification.py` | 5 | send_notification body (Batch 3.5) |
| `test_main_scheduler_wiring.py` | 3 | Scheduler on hot path (Batch 3.5) |
| `test_worker_settings.py` | 3 | WorkerSettings imports without Redis (Batch 3.5) |
| `test_linkedin_github.py` | 0* | _Subagent grep miss; pytest collected total reaches 596_ |
| `test_profile.py` | 0* | _Same — needs verification_ |
| `test_tenancy_isolation.py` | 0* | _Same_ |

(*Three `0`-count rows are likely Grep-pattern misses, not actual empty files — `--collect-only` reported 596 in total, well above the sum of confirmed counts.)

---

## §13 — Known Issues

**TODO/FIXME/HACK/XXX in `backend/src/`:** zero hits.

**Inspection findings:**
1. **Bare `except Exception: pass`** in `workers/tasks.py:325` (`get_default_search_config`) — silent profile-load fallback; intentional but limits debugging.
2. **Bare `except ValueError: pass`** in `workers/tasks.py:337` (`_parse_dt`) — silent fallback to `datetime.now()`; acceptable but worth logging.
3. **Conditional cache unused** — `_get_json_conditional()` defined at `sources/base.py:158–205`; zero source adoptions. Pure dead code on the source-adopter side.
4. **profile.py + search.py STILL UNAUTHENTICATED (CRITICAL — IDOR)** — Batch 3.5 fixed jobs/actions/pipeline but missed profile (4 routes) and search (2 routes). Anyone can POST CV data, trigger LinkedIn/GitHub merges, kick off search runs, enumerate run_ids. Requires immediate follow-up batch.
5. **Multi-user profiles not implemented.** `services/profile/storage.py:15` still single-file `data/user_profile.json`. Batch 2 introduced per-user channels + feed, but profile remains shared/single.
6. **Production-boot smoke test against real Redis pending** — Batch 3.5 P3 deferred; ARQ runtime works in isolation but never booted against real broker.
7. **24 pre-existing test failures** untouched after 4 batches (per Batch 3 memory): API sqlite, cron/setup paths, source parsers, matched_skills buckets. Growing psychological cost.

---

## §14 — Infrastructure

| Surface | Status | Anchor |
|---|---|---|
| GitHub Actions / CI | **None** | no `.github/workflows/*.yml` |
| Dockerfile | **None** | absent |
| docker-compose.yml | **None** | absent |
| Grafana dashboard | **Present** | `backend/ops/grafana_dashboard.json` |
| KPI exporter | **Present** (port 9310, 5-min refresh) | `backend/ops/exporter.py` (7 live KPIs + 4 stubs) |
| Prometheus client | dep declared, used by exporter | — |
| OpenTelemetry | **Absent** | grep 0 |
| Database backend | **SQLite** (`backend/data/jobs.db`) | aiosqlite ≥0.19 — no Postgres/Supabase migration |
| ESCO taxonomy (Pillar 1 prep) | **Absent** | no `backend/data/esco*` files; no ESCO imports |

---

## §15 — Dead Code

**Empty directories under `backend/src/` (pre-Phase-4 placeholders, never repopulated):**
- `filters/` — 0 live `.py` files (only `__pycache__/`)
- `llm/` — 0 live files
- `pipeline/` — 0 live files
- `validation/` — 0 live files

These were placeholders for the clean-architecture rename. Real implementations live under `services/` (filters → skill_matcher/deduplicator/prefilter; llm → profile/llm_provider; pipeline → main.py; validation → models.py post_init). Safe to delete the empty dirs.

**Other orphans:** none. `scripts/`, `migrations/`, `data/`, `ops/` all active.

---

## Appendix A — Anchor Index

| Component | Anchor |
|---|---|
| `SOURCE_REGISTRY` | `backend/src/main.py:82` |
| `_build_sources` | `backend/src/main.py` (within `run_search`) |
| `run_search` | `backend/src/main.py:279` |
| TieredScheduler dispatch | `backend/src/main.py:363–364` |
| Ghost detection pass | `backend/src/main.py:425` (calls `:144–187`) |
| `JobScorer` class | `backend/src/services/skill_matcher.py:281` |
| `score_job` (module fallback) | `backend/src/services/skill_matcher.py:259` |
| `recency_score_for_job` | `backend/src/services/skill_matcher.py:195` |
| `Job` dataclass | `backend/src/models.py:18` |
| `Job.normalized_key` | `backend/src/models.py:61` |
| `jobs` table CREATE | `backend/src/repositories/database.py:24` |
| `user_feed` CREATE | `backend/migrations/0003_user_feed.up.sql:4` |
| `notification_ledger` CREATE | `backend/migrations/0004_notification_ledger.up.sql:4` |
| `user_channels` CREATE | `backend/migrations/0005_user_channels.up.sql:11` |
| `users` + `sessions` CREATE | `backend/migrations/0001_auth.up.sql:2,10` |
| `require_user` | `backend/src/api/auth_deps.py:71` |
| `optional_user` | `backend/src/api/auth_deps.py:83` |
| `WorkerSettings` | `backend/src/workers/settings.py:80` |
| `send_notification` | `backend/src/workers/tasks.py:199` |
| `score_and_ingest` | `backend/src/workers/tasks.py:46` |
| `TieredScheduler` | `backend/src/services/scheduler.py:71` (with `TIER_INTERVALS_SECONDS`) |
| `CircuitBreaker` | `backend/src/services/circuit_breaker.py:29` |
| `BreakerRegistry` | `backend/src/services/circuit_breaker.py:75` |
| `ConditionalCache` | `backend/src/services/conditional_cache.py:25` |
| `_get_json_conditional` | `backend/src/sources/base.py:158–205` (UNUSED) |
| `FeedService` | `backend/src/services/feed.py:47` |
| `passes_prefilter` | `backend/src/services/prefilter.py:126` |
| migration runner | `backend/migrations/runner.py:49–133` |
| profile storage (single-user) | `backend/src/services/profile/storage.py:15` |
| KPI exporter | `backend/ops/exporter.py` |
| Grafana dashboard | `backend/ops/grafana_dashboard.json` |

*End of CurrentStatus.md.*

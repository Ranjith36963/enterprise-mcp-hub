# CurrentStatus_diff.md — Change Log

**From.** Prior audit at `d364e9d` (2026-04-18) — partially superseded by stale 2026-04-19 diff at `fad1744`.
**To.** Re-audit at `ac90bae` (2026-04-19, post-Batch-3.5).
**Method.** 8 parallel Explore subagents, code only, no memory.

> Paired with `CurrentStatus.md` — this file tracks deltas + Batch 1/2/3/3.5 implementation status. For full picture read that.

---

## §1 — Net change since prior audits

### Source layer

| Item | Prior | Now | Anchor |
|---|---|---|---|
| `SOURCE_REGISTRY` count | 48 → 50 | **50** | `backend/src/main.py:82` |
| Source files on disk | 47 → 49 | **49** | `backend/src/sources/**` |
| ATS slug catalog | 104 → 268 (claimed) | **266 (actual)** | `backend/src/core/companies.py` (per-platform breakdown in §10 of CurrentStatus.md) |
| Sources fabricating dates | claimed "44" | **0** | `posted_at` audit in §5 |
| Sources extracting real `posted_at` | claimed 5 | **36** | §5 |
| Sources honestly setting `posted_at=None` | not counted | **13** | §5 |

### Pipeline / scheduler

| Item | Prior | Now | Anchor |
|---|---|---|---|
| Hot-path dispatch | `asyncio.gather` | **`TieredScheduler.tick(force=True)`** | `main.py:363–364` |
| Circuit breakers | wired | **wired (49 sources registered)** | `main.py:360` |
| Conditional cache adoption | 0 | **0 (unchanged — pure dead path)** | `sources/base.py:158–205` |
| Ghost detection completeness gate | shipped | **shipped** | `main.py:144–187` |

### Delivery layer / ARQ

| Item | Prior | Now | Anchor |
|---|---|---|---|
| `WorkerSettings` module | MISSING | **shipped — 4 functions** | `backend/src/workers/settings.py:80` |
| `send_notification` task body | undefined (enqueued by string) | **implemented** | `workers/tasks.py:199–281` |
| Apprise dispatcher (lazy import) | shipped | shipped | `services/channels/dispatcher.py:26,72` |
| Fernet crypto | shipped | shipped | `services/channels/crypto.py:37,41` |

### API / auth

| Item | Prior | Now | Anchor |
|---|---|---|---|
| Total endpoints | 22 → 30 | **30** | per-route table in §7 |
| `require_user` on jobs/actions/pipeline | NOT DONE | **DONE (Batch 3.5)** | `routes/{jobs,actions,pipeline}.py` all `:Depends(require_user)` |
| `require_user` on profile.py | NOT DONE | **STILL NOT DONE ⚠️** | `routes/profile.py:57,66,123,146` — 4 unauthenticated routes |
| `require_user` on search.py | NOT DONE | **STILL NOT DONE ⚠️** | `routes/search.py:19,37` — 2 unauthenticated routes |
| Multi-user profile storage | NOT DONE | **STILL NOT DONE** | `services/profile/storage.py:15` — single JSON file |

### Tests

| Item | Prior | Now |
|---|---|---|
| Test files | 21 → 38 | **43** |
| Collected tests | 397 → 568 (claimed) | **596 (actual via `--collect-only`)** |
| Excluded from baseline | `test_main.py` | unchanged (JobSpy live-HTTP) |

### Infrastructure

Unchanged: still no CI, no Docker, no Postgres migration, no ESCO files. Grafana + KPI exporter present (`backend/ops/`).

---

## §2 — Verified-false prior claims

The earlier `CurrentStatus_diff.md` (also dated 2026-04-19, written before this re-audit) contained two errors that this re-audit corrects:

1. **"Scorer still reads `date_found` not `posted_at`"** — FALSE. `recency_score_for_job` at `services/skill_matcher.py:195–212` reads `posted_at` first when confidence is trustworthy, falls back to `date_found` capped at 60% otherwise. The framing error mistook the legacy module-level `_recency_score(date_found)` (single-arg helper) for the hot path.

2. **"44/49 sources still fabricate dates"** — FALSE. Counted `date_found = now_iso` writes (which are *correct* post-Batch-1 — `date_found` is now crawl-time by design). Of 49 sources: 36 extract real upstream date into `posted_at`, 13 honestly set `posted_at=None` + `date_confidence="low"`, **0** fabricate.

**The earlier diff doc's other 3 headline gaps were correct** at time of writing and are now closed by Batch 3.5 (TieredScheduler wired, `WorkerSettings` + `send_notification` shipped). The IDOR claim was *partially* closed — only 3 of 5 vulnerable route modules patched.

---

## §3 — Batch 1/2/3/3.5 implementation matrix

Each row: **IMPLEMENTED / PARTIAL / NOT DONE — evidence**.

### Batch 1 — Date-model rebuild + ghost detection + KPI exporter (merged `31124fa`)

| Feature | Status | Anchor |
|---|---|---|
| `posted_at` column on `jobs` | **IMPLEMENTED** | `database.py:41` |
| `first_seen_at`/`last_seen_at`/`last_updated_at` columns | **IMPLEMENTED** | `database.py:42–44` (DB-only, not on `Job` dataclass) |
| `date_confidence`/`date_posted_raw` | **IMPLEMENTED** | `database.py:45–46` + `models.py:37–38` |
| `consecutive_misses`/`staleness_state` | **IMPLEMENTED** | `database.py:47–48` |
| Ghost detection (absence sweep) | **IMPLEMENTED** | `main.py:144–187` |
| Completeness gate (70% rolling 7d) | **IMPLEMENTED** | `main.py:168–175` |
| 10-KPI exporter | **IMPLEMENTED** (7 live + 4 stubs) | `backend/ops/exporter.py` |
| Scorer reads `posted_at` first | **IMPLEMENTED** | `skill_matcher.py:195–212` |
| Per-source date-handling (`posted_at` extraction) | **IMPLEMENTED (36/49 extract; 13/49 honest-null; 0 fabricate)** | §5 of CurrentStatus.md |
| Embedding-based repost detection | **NOT DONE** | grep 0 hits |
| LLM repost detection | **NOT DONE** | no scoring path |

### Batch 2 — Multi-user delivery layer (merged earlier — see Batch 2 memory)

| Feature | Status | Anchor |
|---|---|---|
| Migration runner | **IMPLEMENTED** | `backend/migrations/runner.py:49–133` |
| `users` + `sessions` tables | **IMPLEMENTED** | `0001_auth.up.sql` |
| Multi-tenant rebuild of `user_actions` + `applications` | **IMPLEMENTED** | `0002_multi_tenant.up.sql` |
| `user_feed` SSOT | **IMPLEMENTED** | `0003_user_feed.up.sql:4–28` |
| `notification_ledger` | **IMPLEMENTED** | `0004_notification_ledger.up.sql:4–18` |
| `user_channels` (Fernet) | **IMPLEMENTED** | `0005_user_channels.up.sql:11–22` |
| argon2id passwords | **IMPLEMENTED** | `services/auth/passwords.py` |
| Signed session cookies | **IMPLEMENTED** | `services/auth/sessions.py` |
| `require_user`/`optional_user` deps | **IMPLEMENTED** | `api/auth_deps.py:71,83` |
| `/api/auth/*` (4 routes) | **IMPLEMENTED** | `routes/auth.py:55,78,100,114` |
| `/api/settings/channels/*` (4 routes) | **IMPLEMENTED** | `routes/channels.py:44,65,89,106` |
| Apprise dispatcher (lazy) | **IMPLEMENTED** | `services/channels/dispatcher.py:26,72` |
| Fernet crypto | **IMPLEMENTED** | `services/channels/crypto.py:37,41` |
| FeedService (6 methods) | **IMPLEMENTED** | `services/feed.py:47,60,82,106,117,128,141` |
| Prefilter cascade (3 stages) | **IMPLEMENTED** | `services/prefilter.py:56,86,116,126` |
| `score_and_ingest` task | **IMPLEMENTED** | `workers/tasks.py:46` |
| `mark_ledger_*` helpers + ARQ wrappers | **IMPLEMENTED** | `workers/tasks.py:156,171,284,293` |
| `send_notification` task body | **IMPLEMENTED (Batch 3.5)** | `workers/tasks.py:199–281` |
| `WorkerSettings` + Redis pool | **IMPLEMENTED (Batch 3.5)** | `workers/settings.py:80` |
| Per-user scoping on jobs/actions/pipeline | **IMPLEMENTED (Batch 3.5)** | `routes/{jobs,actions,pipeline}.py` |
| Per-user scoping on profile.py | **NOT DONE ⚠️** | `routes/profile.py:57,66,123,146` |
| Per-user scoping on search.py | **NOT DONE ⚠️** | `routes/search.py:19,37` |
| Quiet-hours filter | **NOT DONE** | grep 0 |
| Digest aggregation | **STUB** (urgency param accepted, no batching) | `workers/tasks.py:203` |
| Telegram channel handler | **PARTIAL** (schema-ready `tgram://`, no dedicated handler) | `0005:8` + `dispatcher.py:66` stub |
| Webhook channel handler | **PARTIAL** (schema-ready `json://`, no dedicated handler) | `0005:9` + `dispatcher.py:68` stub |
| SMS channel | **NOT DONE** | absent |
| Multi-user profile storage | **NOT DONE** | `services/profile/storage.py:15` (single JSON) |
| Production-boot smoke against real Redis | **NOT DONE (P3 from Batch 3.5)** | deferred to Batch 4 |

### Batch 3 — Tiered polling + source expansion (merged `fad1744`)

| Feature | Status | Anchor |
|---|---|---|
| 5 new sources (teaching_vacancies, gov_apprenticeships, nhs_jobs_xml, rippling, comeet) | **IMPLEMENTED** | `SOURCE_REGISTRY` `:82` + per-source files |
| 3 dropped sources (yc_companies, nomis, findajob) | **IMPLEMENTED** | files removed |
| Registry rotation 48 → 50 (5 surfaces) | **IMPLEMENTED** | `SOURCE_REGISTRY` + `_build_sources` + `RATE_LIMITS` + `test_cli.py` + `test_api.py` |
| ATS catalogue 104 → 266 | **IMPLEMENTED** | `core/companies.py` |
| `TieredScheduler` + `TIER_INTERVALS_SECONDS` | **IMPLEMENTED** | `services/scheduler.py:71` |
| Per-source circuit breakers | **IMPLEMENTED** | `services/circuit_breaker.py` + `main.py:360` |
| ETag/Last-Modified conditional fetch | **PARTIAL (built, ZERO source adoption)** | `services/conditional_cache.py:25` + `sources/base.py:158–205` |
| New rate-limit entries for 5 new sources | **IMPLEMENTED** | `core/settings.py:53–106` |
| `category` tier on each new source | **IMPLEMENTED** | per CLAUDE.md rule #15 |

### Batch 3.5 — Stabilisation (merged `ac90bae`)

| Feature | Status | Anchor |
|---|---|---|
| IDOR fix on jobs/actions/pipeline | **IMPLEMENTED** | `routes/{jobs,actions,pipeline}.py` (all 12 routes `Depends(require_user)`) |
| IDOR fix on profile.py | **NOT DONE ⚠️ — overlooked in scope** | `routes/profile.py:57,66,123,146` |
| IDOR fix on search.py | **NOT DONE ⚠️ — overlooked in scope** | `routes/search.py:19,37` |
| `WorkerSettings` module | **IMPLEMENTED** | `workers/settings.py:80` |
| `send_notification` body | **IMPLEMENTED** | `workers/tasks.py:199–281` |
| `TieredScheduler` wired into `run_search` | **IMPLEMENTED** | `main.py:363–364` |
| Test coverage for above | **IMPLEMENTED** (4 new test files, ~24 tests) | `tests/test_{api_idor,worker_settings,worker_send_notification,main_scheduler_wiring}.py` |
| Production-boot smoke against real Redis | **DEFERRED (P3 → Batch 4)** | n/a |

---

## §4 — Net implementation score (this audit)

| Batch | Core features | IMPLEMENTED | PARTIAL | NOT DONE |
|---|---|---|---|---|
| Batch 1 | 11 | **9** | 0 | 2 (embedding/LLM repost detection) |
| Batch 2 | 26 | **18** | 3 (digest stub, Telegram, Webhook) | 5 (quiet hours, SMS, multi-user profiles, profile/search IDOR, prod-Redis smoke) |
| Batch 3 | 9 | **8** | 1 (conditional cache unused) | 0 |
| Batch 3.5 | 6 | **4** | 0 | 2 (profile/search IDOR overlooked) |

**Headline gaps ranked by impact today:**

1. **profile.py + search.py IDOR — STILL OPEN (CRITICAL).** Batch 3.5 scope missed two route modules. Any unauthenticated user can POST CV data, kick off LinkedIn/GitHub merges, trigger search runs, enumerate run_ids. Requires immediate follow-up patch (call it Batch 3.5.1 or fold into Batch 4).
2. **Multi-user profile storage NOT DONE.** Per-user channels + feed exist (Batch 2), but profile remains shared `data/user_profile.json`. Two users on the same instance overwrite each other's CV data.
3. **Conditional cache fully unused.** Built in Batch 3, zero source adoptions. Pure dead path until at least one feed-style source migrates.
4. **24 pre-existing test failures untouched after 4 batches.** Growing psychological cost.
5. **Production-boot smoke against real Redis** — deferred from Batch 3.5 P3.
6. **No CI / Docker / observability beyond Grafana JSON.** Batch 4 territory.
7. **ESCO taxonomy absent.** Pillar 1 prerequisite — not yet present.

**Things that are fine** (against earlier alarm):
- Date-model fully shipped (Batch 1). Scorer reads `posted_at` correctly. No fabrication.
- ARQ runtime executable (Batch 3.5).
- TieredScheduler is on the hot path (Batch 3.5).
- Jobs/actions/pipeline IDOR closed (Batch 3.5).

---

## §5 — Recommended next moves

In priority order:

1. **Batch 3.5.1 (security patch, ≤1 day):** Add `Depends(require_user)` + `user_id` scoping to `profile.py` (4 routes) and `search.py` (2 routes). Same pattern as Batch 3.5. Single tight batch.
2. **Multi-user profile migration (≤2 days):** Move `data/user_profile.json` → `user_profiles` table keyed by `user_id`. Backfill placeholder. Unblocks real multi-tenant operation.
3. **Conditional-cache adoption pilot (≤1 day):** Migrate 2–3 RSS feed sources (jobs_ac_uk, biospace, weworkremotely) to `_get_json_conditional()` to validate the cache works under live ETag conditions. If green, broaden.
4. **Test cleanup batch (≤2 days):** Tackle the 24 pre-existing failures. Either fix or explicitly mark `xfail` with reason.
5. **Then Batch 4 (launch readiness):** scope-down, freemium, ICO, privacy/LIA, ASA copy, SES, prod-Redis smoke (carries the Batch 3.5 P3).

Pillar 1 (ESCO + better matching) only after #1–#5 — building richer matching on top of unauthenticated profile uploads is unsafe.

---

*End of diff.*

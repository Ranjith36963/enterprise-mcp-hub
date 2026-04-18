# Pillar 3 Implementation Log

> **Purpose.** Single rolling record of pillar 3's batch-by-batch implementation. Each batch appends one section below when it merges. Future Claude sessions (and future-Ranjith) read this file *first* before starting any pillar 3 work — it bridges the 1,800 lines of research in `docs/research/` to the actual state of the code.
>
> **Scope.** Tracks pillar 3 main report + 4 batches:
> - `pillar_3_report.md` — Job provider layer (sources, slugs, new APIs)
> - `pillar_3_batch_1.md` — Date model + ghost detection (freshness)
> - `pillar_3_batch_2.md` — Multi-user delivery layer (push, scoring, parity)
> - `pillar_3_batch_3.md` — Tiered polling + source expansion
> - `pillar_3_batch_4.md` — Risk, economics, launchable plan
>
> **Do not delete entries.** This is an append-only log. If a batch is reverted, append a new entry recording the revert — never edit the original.

---

## Cross-Batch Foundation

### Branching strategy

- Each batch lives on a dedicated branch: `pillar3/batch-1`, `pillar3/batch-2`, etc.
- Strictly sequential: Batch N+1 does not start until Batch N is merged to `main` and this log is updated.

### Worktree convention (constant directories, rotating branches)

Two persistent worktrees live under `.claude/worktrees/`:

| Worktree | Path | Role |
|---|---|---|
| **generator** | `.claude/worktrees/generator/` | One Claude session writes batch code here |
| **reviewer** | `.claude/worktrees/reviewer/` | A *separate, independent* Claude session reviews the generator's diff here |

**These two directories never get deleted.** Only the branches inside them rotate per batch.

**Per-batch lifecycle:**

```
# At start of Batch N:
cd .claude/worktrees/generator && git checkout -B pillar3/batch-N main
cd .claude/worktrees/reviewer  && git checkout -B pillar3/batch-N-review main

# During Batch N:
#   - Generator session writes implementation in generator/
#   - When generator commits, reviewer session pulls that branch into reviewer/
#     and produces a review report (NEVER edits code that ships).

# At end of Batch N (merged to main):
git branch -d pillar3/batch-N pillar3/batch-N-review
# Worktree directories stay put — ready for Batch N+1.
```

The reviewer worktree is read-only with respect to shipped code. Its only output is review findings (saved as `docs/_archive/reviews/batch-N-review.md` or similar). All code changes that ship come from the generator worktree.

### Backup branches (one-time, pre-Batch-1)

The previous worktree branches contained 7 (generator) and 11 (reviewer) commits of unmerged work plus untracked plans. Preserved via:

- `backup/old-generator` branch — old generator commits (mostly Streamlit cleanup)
- `backup/old-reviewer` branch — old reviewer commits (security/scoring fixes — worth a triage pass to see if any should be cherry-picked to main)
- `docs/_archive/HARDCODED_REMOVAL_REPORT.md` — preserved untracked report
- `docs/_archive/old-plans/` — preserved untracked implementation plans (FastAPI build, LLM CV parser, hardcoded category removal)
- `git stash` entries — preserved local `settings.local.json` edits

### Test contract

Every batch's "done" criterion is:
1. **All previously-passing tests still pass** (no regressions)
2. **New tests for this batch pass** (TDD-first per `superpowers:test-driven-development`)
3. **HTTP mocked everywhere** per CLAUDE.md rule #4 — no live requests in CI

Run from `backend/`: `python -m pytest tests/ -v`

### Verification gates per batch

Before merging to `main`, each batch must:
- Pass full pytest suite from `backend/`
- Get a `coderabbit:code-review` pass on the diff
- Append a completion entry to this log (see template at the bottom)
- Update CLAUDE.md if any rules changed (e.g., new source counts, new load-bearing files)
- Save a memory file (`project_pillar3_batch_N_done.md`) so future sessions resume with full context

---

## Baseline (pre-Batch-1)

> Numbers below verified by 2026-04-18 fresh code-audit (see `docs/CurrentStatus.md`). Supersedes any earlier counts.

| Field | Value |
|---|---|
| Date | 2026-04-18 |
| Branch | `main` |
| Commit | `d364e9d` (chore: remove obsolete FastAPI plan and stock frontend README) |
| Worktrees aligned | ✅ generator + reviewer both at `d364e9d` |
| Total tests | 410 collected across 20 test files (per `CurrentStatus.md` §12) |
| Passing | _baseline pytest run still pending — must complete before Batch 1 starts_ |
| Failing | _to be filled in_ |
| Skipped | _to be filled in_ |
| Source count | 48 in `SOURCE_REGISTRY`, 47 unique source instances (`indeed`+`glassdoor` share `JobSpySource`) |
| Source breakdown | 7 keyed APIs · 10 free APIs · 10 ATS · 8 feeds · 7 scrapers · 5 other |
| ATS slugs | 104 across 10 ATS platforms (per `CurrentStatus.md` §10 / `companies.py`) |
| Date-fabricating sources | **39/47 (83%)** hardcode `datetime.now()` — 61 total call sites (revised up from earlier 14 estimate; per `CurrentStatus.md` §5) |
| Real-date sources | ~8/47 — careerjet, findwork, jsearch, landingjobs, nofluffjobs, reed, recruitee, remotive (partial) |
| Wrong-field sources | 3 — Jooble `updated` (L49), Greenhouse `updated_at` (L40), NHS Jobs `closingDate` (L57 + fallbacks L105/L111) |
| `bucket_accuracy_24h` | Unmeasured (no observability) |
| `date_reliability_ratio` | ~60–65% estimated |
| Multi-user support | None — single `user_profile.json`, single SQLite DB |
| Push notification channels | Email / Slack / Discord (per-installation env vars, not per-user) |
| Polling cadence | Twice-daily cron (currently broken — see `CurrentStatus.md` §13 Issue #3) |
| Dead phase-4 dirs | `backend/src/{filters,llm,pipeline,validation}/` — empty, only `__pycache__`. To be removed in Batch-1 pre-flight. |
| `keywords.py` keyword lists | Primary/Secondary/Tertiary/Relevance all **empty** (removed 2026-04-09); dynamic from CV required |
| `Job.is_new` field | Defined in dataclass, **not persisted to DB** — known schema gap |
| Frontend | Next.js 16.2.2 + React 19.2.4 — 5 pages incl. Kanban pipeline, CORS hardcoded `localhost:3000` (`api/main.py:20`) |

---

## Batch 1 — Date Model + Ghost Detection

**Status:** Not started

**Reference:** `docs/research/pillar_3_batch_1.md`

**Scope:** 5-column date model migration, fix 14 fabricating sources + 3 wrong-field sources, recency-scoring update for `None` dates, ghost detection state machine, 10 KPI exporter for Prometheus + Grafana.

**Branch:** `pillar3/batch-1`

**Pre-flight:**
1. **Delete phase-4 debris dirs first** — `rm -rf backend/src/{filters,llm,pipeline,validation}/` (all empty `__pycache__`-only, leftover from phase-4 rename per `CurrentStatus.md` §15). Prevents stale-bytecode import ambiguity during schema work.
2. **Schema migration agent must run first and alone** — touches `models.py` + `database.py` (load-bearing per CLAUDE.md rules #1 and #3).
3. **Scope reminder** — 39 fabricator sources to fix (not 14 as earlier docs claimed), plus 3 wrong-field sources. Plan agent split accordingly.

_Completion entry will be appended here when merged._

---

## Batch 2 — Multi-User Delivery Layer

**Status:** Blocked on Batch 1

**Reference:** `docs/research/pillar_3_batch_2.md`

**Scope:** Auth + multi-tenant schema, `user_feed` SSOT table + FeedService, ARQ worker + Apprise notifications, 99% pre-filter cascade, channel config UI.

**Branch:** `pillar3/batch-2`

**Pre-flight:** REQUIRES `superpowers:brainstorming` skill before plan — too many irreversible design choices (ARQ vs Celery, Apprise vs Novu, polling vs SSE, when to migrate auth).

_Completion entry will be appended here when merged._

---

## Batch 3 — Tiered Polling + Source Expansion

**Status:** Blocked on Batch 2

**Reference:** `docs/research/pillar_3_batch_3.md`

**Scope:** Tiered polling scheduler (60s for ATS / 5min for Reed / 15min for Workday / etc.), conditional fetching layer, 5 new sources (Teaching Vacancies, GOV.UK Apprenticeships, NHS XML, Rippling, Comeet), slug expansion 104 → 500+, drop YC Companies + Nomis + FindAJob, circuit breakers replacing "newly_empty".

**Branch:** `pillar3/batch-3`

**Pre-flight:** Update `len(SOURCE_REGISTRY) == N` assertion in `test_cli.py` per CLAUDE.md rule #8.

_Completion entry will be appended here when merged._

---

## Batch 4 — Launch Readiness

**Status:** Blocked on Batch 3

**Reference:** `docs/research/pillar_3_batch_4.md`

**Scope:** Scope down to top 10–15 sources for MVP, freemium metering, pricing page, ICO registration (£40), privacy notice + LIA, ASA-compliant marketing copy, Amazon SES setup.

**Branch:** `pillar3/batch-4`

**Pre-flight:** Update PRD's "all UK white-collar domains" claim — currently fails CAP Code rule 3.7 substantiation.

_Completion entry will be appended here when merged._

---

## Completion Entry Template

When a batch merges, append a section using this template:

```markdown
## Batch N — Completion Entry

**Merged:** YYYY-MM-DD
**Branch:** `pillar3/batch-N` → merged to `main` at commit `<short-hash>`
**Commit range:** `<base-hash>..<merge-hash>` (`git log <base>..<merge> --oneline`)

### Test deltas
- Tests before: X passing / Y total
- Tests after: X' passing / Y' total
- New tests added: Z
- Tests removed/replaced: W (with reason)

### KPI deltas (where measurable)
- `bucket_accuracy_24h`: before → after
- `date_reliability_ratio`: before → after
- Source count: before → after
- (other batch-specific metrics)

### What shipped
- (bullet list of merged features)

### What got deferred
- (bullet list of items punted to a follow-up — explicit names)

### Surprises / lessons
- (anything that diverged from the research recommendation, with reason)

### CLAUDE.md / docs updated
- (which canonical docs were updated as part of this batch)

### Memory file saved
- `project_pillar3_batch_N_done.md`
```

# Pillar 2 Progress Log

Mirrors the Pillar 1 format. One section per batch in the execution order fixed
by `docs/pillar2_implementation_plan.md` §7 (2.2 → 2.1 → 2.3 → 2.4 → 2.5 → 2.9 →
2.6 → 2.7 → 2.8 → 2.10).

Generator worktree: `C:\Users\Ranjith\OneDrive\Documents\job360\.claude\worktrees\generator` on branch `worktree-generator` rebased onto local `main @ cdf6aaf`.

---

## Environment note — pre-existing test hang on `tests/test_sources.py`

Under Python 3.13 on Windows the 81 tests in `tests/test_sources.py` hang
indefinitely inside asyncio's Windows IOCP selector (`_overlapped.GetQueuedCompletionStatus`)
even with `pytest-timeout`. This predates Pillar 2 work (the same hang reproduces
against baseline `1730bf6`, and was flagged in `memory/project_test_http_leak.md`
under a slightly different guise — "JobSpy hits live Indeed"). It does **not**
block Pillar 2 batches because:

1. Every Pillar 2 batch touches the scoring / enrichment / retrieval layers,
   none of which are imported by `test_sources.py`.
2. The source tests are mocked with `aioresponses` — the hang is in the Python
   3.13 × Windows IOCP × aiohttp-shutdown interaction, not in any production
   code path.

Going forward each batch runs:

```bash
# Broad clean baseline (68x passing, no failures)
python -m pytest tests/ \
  --ignore=tests/test_main.py \
  --ignore=tests/test_sources.py \
  -p no:randomly --timeout=10

# Scoped verification for scoring-adjacent batches (2.2, 2.3, 2.9)
python -m pytest tests/test_scorer.py tests/test_profile.py -p no:randomly
```

`test_main.py` is also excluded per the established Pillar-3 pattern (live HTTP
leak in JobSpy against Indeed/Glassdoor).

---

## Batch 2.2 — Gate-pass scoring — MERGED

**Merged:** `aa13554` on 2026-04-21

**Plan coverage:**
- Plan §4 Batch 2.2 — gate-pass scoring
- Report item(s): #2 (gate-pass eliminates false positives)

**Touches:**
- `backend/src/core/settings.py`: +11 lines (added `MIN_TITLE_GATE` and
  `MIN_SKILL_GATE` as `float(os.getenv(...))` constants defaulting to `0.15`,
  with a comment block explaining the gate semantics).
- `backend/src/services/skill_matcher.py`: +18 lines
  - widened the `src.core.settings` import to pull in the two new constants,
  - added module-level `_gate_suppressed_score(title_pts, skill_pts) -> int | None`
    which returns `max(10, int((title_pts+skill_pts)*0.25))` when either gate
    fails, else `None`,
  - called it from `score_job()` (legacy module-level path) and from
    `JobScorer.score()` (dynamic path) before the linear accumulation of
    location / recency / penalties, so gate-fail jobs cannot be inflated by
    those components.
- `backend/tests/test_scorer.py`: +192 / -24 lines
  - added `TestGatePass` class with 12 gate-aware tests (8 on `JobScorer`,
    4 on the module-level `score_job` path),
  - rewrote 7 pre-existing tests (`test_title_match_contributes_points`,
    `test_location_match_contributes_points`, `test_remote_location_gets_points`,
    `test_more_skills_higher_score`, `test_recency_today_gets_full_points`,
    `test_us_ai_job_scores_lower_than_uk`, `test_score_job_uses_recency_for_job_helper`)
    to use `JobScorer` with a gate-clearing `SearchConfig`. Their original
    invariants (UK > US, today > old, many-skills > few-skills, honest >
    fabricated) are preserved but observable only on the non-suppressed
    linear path — which is Batch 2.2's explicit intent.

**Tests added:** `tests/test_scorer.py` TestGatePass (+12 tests).

**Test delta (scoped to scoring + profile):** 110p → 122p (0 failures, 0 skips).

**Test delta (broad, minus `test_main` / `test_sources`):** 633p/3s → 645p/3s
(+12). No pre-existing test regressed.

**API + IDOR tests (separate run):** 37p / 0f / 0s (unchanged by this batch).

**Deferred from this batch:**
- None. The batch landed exactly as the plan's Touches / Test surface sections
  specified. User-configurable gates (per-profile tuning) are correctly
  deferred to Batch 2.9 per the plan's "Out of scope".

**Post-merge notes:**
- The 7 existing-test rewrites are a direct consequence of the gate's
  semantic intent: without a profile, location/recency alone can no longer
  distinguish jobs, and the old tests encoded the pre-gate bug. Each rewrite
  preserves the original invariant on the JobScorer path where the gate
  passes. This is not scope creep — it is the test-surface evolution named
  in the plan ("Test surface: tests/test_scorer.py — new class TestGatePass").
- `test_score_job_with_patched_keywords_can_pass_gate` uses `monkeypatch` to
  inject non-empty `JOB_TITLES` / `PRIMARY_SKILLS` so the module-level path
  can demonstrate gate-pass. This is the only path inside `score_job()` that
  is observable as non-suppressed under the current (empty-defaults) keyword
  policy.
- Both constants are env-overridable (`MIN_TITLE_GATE=0.10` / `MIN_SKILL_GATE=0.20`
  etc.) so ops can retune without code edits if the 15 % default ever proves
  too aggressive.
- The per-component gate thresholds are absolute, not fractions of the
  user's weighted max. If a future batch introduces user-configurable weights
  (e.g. raising `TITLE_WEIGHT` to 60) the 0.15 fraction would scale with it,
  preserving the intended "15 % of component max" meaning.

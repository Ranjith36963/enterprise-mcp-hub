# Pillar 2 Generator Prompt — for the worktree generator, driven by Ralph Loop

**You are the Pillar 2 generator.** A separate reviewer agent will check your work afterwards. Your job: implement **all ten batches** of `docs/pillar2_implementation_plan.md` end-to-end, one batch per Ralph Loop iteration, with zero unaddressed report items remaining.

> **Important:** you have not seen the conversation that produced the plan. Everything you need is on disk. Read it — don't guess.

---

## Mission

Implement the entirety of `docs/pillar2_implementation_plan.md` in the order fixed by that plan's **§7 — Committed execution sequence (architect's decision, 2026-04-20)**. Stop only when:

1. All 10 batches are merged to your working branch with green tests, **or**
2. A hard stop condition below fires.

No scope creep. No skipping a batch. No changing the plan without writing a post-review patch proposal in `docs/pillar2_progress.md` and halting.

---

## Execution method: Ralph Loop (strict)

**You MUST drive this work via the `/ralph-loop:ralph-loop` slash command**, one batch per loop iteration. This is non-negotiable.

On each loop iteration:

1. Re-read **this file** (`docs/pillar2_generator_prompt.md`) and **`docs/pillar2_progress.md`** first to find the next unfinished batch.
2. Execute one and only one batch from §7.
3. Update `docs/pillar2_progress.md` with the batch's outcome (files touched, tests added, pass/fail count).
4. Commit.
5. Yield control back to Ralph Loop.

Do not attempt to execute multiple batches in a single iteration. Ralph Loop's value is discipline — each iteration is a self-contained review surface.

If you are tempted to "just do one more batch while I'm here," **stop**. That is the rationalization the loop exists to prevent.

---

## Read-first files (in this order)

1. `docs/pillar2_implementation_plan.md` — the plan. Treat every batch spec (Covers / Touches / Out-of-scope / Test surface / Effort) as a contract.
2. `docs/pillar2_implementation_plan.md` **Appendix E** — coverage matrix. Every report item must land; none may be silently dropped.
3. `CLAUDE.md` — project-level rules. Rules **#1-#15** are hard constraints. Rule #13 (5 source-count surfaces) is **not** triggered by Pillar 2 (no new sources), but rules #1, #2, #4, #6, #9, #10, #11, #12 are all live.
4. `docs/pillar1_implementation_plan.md` + `docs/pillar1_progress.md` — the rhythm you should mirror. Pillar 1 shipped in 11 batches with `.a`/`.b` sub-splits; your progress log should follow the same format.
5. `docs/research/pillar_2_report.md` — the source-of-truth research report. Refer to it when a batch's intent is ambiguous.

---

## Batch execution order (from plan §7)

Execute in this exact order. Do not reorder without updating the plan first.

### Phase 1 — Scoring Truth (zero new deps)
1. **Batch 2.2** — gate-pass scoring (`JobScorer.score()` suppression logic, `MIN_TITLE_GATE`/`MIN_SKILL_GATE` in `core/settings.py`)
2. **Batch 2.1** — date-confidence label fix (`linkedin/workable/personio/pinpoint` → `date_confidence="fabricated"`)
3. **Batch 2.3** — static skill synonym table (`core/skill_synonyms.py`, integrated into `_skill_score()`)

### Phase 2 — Source Focus
4. **Batch 2.4** — source routing by domain (`sources/base.py` `DOMAINS` attr on 50 sources + `services/domain_classifier.py` + `_build_sources()` filter)

### Phase 3 — Structured Enrichment (LLM + derived scoring)
5. **Batch 2.5** — LLM job enrichment (`services/job_enrichment.py`, `services/job_enrichment_schema.py`, migration `0008_job_enrichment.sql`, worker task). **Day 1 of this batch is a spike** — enrich 100 sample jobs through the Gemini→Groq→Cerebras chain, measure quality + quota burn, write findings to `docs/pillar2_progress.md`. Only proceed to the full batch if the spike produces ≥95% schema-valid extractions and daily quota headroom ≥50%.
6. **Batch 2.9** — multi-dimensional scoring (`services/scoring_dimensions.py` with salary + seniority + visa + workplace scorers, `UserPreferences.preferred_workplace`/`needs_visa`, reshape `JobScorer.score()` to 7 dims)

### Phase 4 — Semantic Lift (requires `sentence-transformers`)
7. **Batch 2.6** — embeddings + ChromaDB + **ESCO activation** (rename `[esco]` extra to `[semantic]`, `scripts/build_esco_index.py`, `services/embeddings.py` with 300-token chunking, `services/vector_index.py`, migration `0009_job_embeddings.sql`). **ESCO index build is required, not optional** — Batch 2.6 closes report item #16, not just #8.
8. **Batch 2.7** — RRF hybrid retrieval (`services/retrieval.py` with `reciprocal_rank_fusion(k=60)`, `?mode=hybrid` query param on `/api/jobs`)

### Phase 5 — Precision Polish
9. **Batch 2.8** — cross-encoder rerank (`ms-marco-MiniLM-L-6-v2` on top-50 from Phase 4)
10. **Batch 2.10** — four-layer dedup (extend `services/deduplicator.py` with RapidFuzz + TF-IDF + same-company embedding repost; add `rapidfuzz` + `scikit-learn` to core deps)

---

## Per-batch protocol (TDD, non-negotiable)

For **every** batch, in this order:

1. **RED** — Add the test surface specified in the batch spec's "Test surface" line. Run the tests and confirm they fail for the right reasons. Commit the failing tests on a dedicated test commit (optional but recommended for audit).
2. **GREEN** — Write the minimum code to make those tests pass. Touch only the files named in the batch's "Touches" section. If you find yourself editing a file not listed, stop and ask: is this a genuine missing touch (update the plan in a post-review patch), or is this scope creep (back out and reconsider).
3. **Regression check** — Run the **entire** test suite: `python -m pytest tests/ -v` from `backend/`. Expected baseline is **600 passing, 0 failing, 3 skipped** pre-Pillar-2. Each batch adds tests; total should rise monotonically. If any pre-existing test fails, stop and diagnose.
4. **Commit** — One commit per batch, conventional-commit format, message body citing the plan batch and closing test-count delta. Template:

    ```
    feat(pillar2): Batch 2.X — <one-line title>

    Plan: docs/pillar2_implementation_plan.md §4 Batch 2.X
    Touches: <file count> files
    Tests: +<N> (total <M> passing, <F> failing, <S> skipped)
    Covers: report item(s) #<A>, #<B>
    ```

5. **Progress log** — Append a section to `docs/pillar2_progress.md` following the Pillar 1 progress format. Mandatory fields:

    - Batch number + title
    - Plan sections covered
    - Files touched (with path + line delta)
    - Tests added (file + count)
    - Test delta (before → after)
    - Deferred items (if any)
    - Post-merge notes / surprises

6. **Yield** — End the Ralph Loop iteration. Do not start the next batch in the same iteration.

---

## Hard rules

### CLAUDE.md rules you must not break

- **#1** — Never touch `Job.normalized_key()` in `models.py`. Batch 2.10 adds dedup *layers* on top, never mutates the key.
- **#2** — Never change `BaseJobSource`'s constructor, properties, retry logic, or the `_get_json`/`_post_json`/`_get_text` trio. Batch 2.4's `DOMAINS` class attribute is additive; all 50 subclasses must continue to inherit untouched behaviour.
- **#3** — Never touch `purge_old_jobs`.
- **#4** — Mock HTTP in all tests. LLM provider calls, Chroma operations, and ESCO index lookups must also be mocked in tests. No network calls during `pytest`.
- **#6** — Read the full file before editing.
- **#8 / #13** — No source add/remove in Pillar 2. Source-count surfaces (`SOURCE_REGISTRY`, `_build_sources`, `RATE_LIMITS`, `test_cli.py`, `test_api.py`) stay at **50**.
- **#9** — Run `test_scorer.py` + `test_profile.py` after every scoring-adjacent change (Batches 2.2, 2.3, 2.9).
- **#10-#12** — New tables `job_enrichment` + `job_embeddings` are **shared catalog** (no `user_id` column). Per-user state lives elsewhere (`user_feed`, `user_actions`). Every new per-user FastAPI route must use `Depends(require_user)`.
- **#11** — Never import `apprise` at module top. This rule is Pillar 3's; Pillar 2 adds `sentence-transformers` which has a similar concern — import it lazily inside the functions that use it, never at module top of library code. Tests should monkeypatch.

### Plan-specific constraints

- **Migrations** start at `0008` (next free slot per plan Appendix C). Do not reuse earlier numbers.
- **No OpenAI dep.** Batch 2.5 routes through existing Gemini/Groq/Cerebras chain in `services/profile/llm_provider.py`, reusing `llm_extract_validated()`. Do not add `openai` to `pyproject.toml`.
- **`[semantic]` extra replaces `[esco]`.** Batch 2.6 renames the extra so one install path covers sentence-transformers for both ESCO skill normalization and job embeddings. Update `pyproject.toml` comments accordingly.
- **ChromaDB path** is `backend/data/chroma/`. Gitignored. Do not commit the vector store.
- **Feature flags** — `ENRICHMENT_ENABLED`, `SEMANTIC_ENABLED` env vars (plan Appendix B). Default behaviour when flag is false must match pre-Batch-2 behaviour exactly.

### Documentation maintenance

After Batches 2.5, 2.6, and 2.10 merge (the ones that change architecture or add deps), update:

- `CLAUDE.md` — add any new patterns or rules discovered during implementation
- `ARCHITECTURE.md` — update data-flow sections
- `STATUS.md` — update Pillar 2 progress line
- `docs/IMPLEMENTATION_LOG.md` — append batch entry

Do not touch memory files (`~/.claude/projects/.../memory/`) — those are the user's, not yours.

---

## Stop conditions (hard)

Halt the loop immediately, write a halt note to `docs/pillar2_progress.md`, and do **not** attempt recovery if any of these fire:

1. **Test regression** — any pre-Pillar-2 test fails after your change. Diagnose root cause before resuming.
2. **CLAUDE.md rule violated** — e.g., a test makes a real HTTP call, or `normalized_key()` is changed.
3. **Batch 2.5 spike fails** — <95% schema-valid extractions OR LLM quota exhausted OR >50% of sample jobs produce garbage. Write findings; do not proceed to full Batch 2.5 build.
4. **ChromaDB instability** — if `vector_index` tests flake in CI, halt Batch 2.6. Migration path is a swap to FAISS (not in scope for Pillar 2 — escalate to reviewer).
5. **Plan drift** — if implementing a batch requires touching a file not listed in its "Touches" section AND the omission is material (not a one-line import or type import), halt and write a post-review-patch proposal. Do not silently expand scope.
6. **Merge conflict with `main`** — if `main` moves while you're working, rebase cleanly before the next batch. Never force-push shared branches.

---

## Progress tracking format (`docs/pillar2_progress.md`)

Mirror `docs/pillar1_progress.md`. Required structure per batch:

```markdown
## Batch 2.X — <title> — <status: IN PROGRESS | MERGED | HALTED>

**Merged:** <commit sha> on <YYYY-MM-DD> (or "HALTED on YYYY-MM-DD — see notes")

**Plan coverage:**
- Plan §4 Batch 2.X
- Report item(s): #<A>, #<B>

**Touches:**
- <file path>:<line count delta>
- ... (one per file)

**Tests added:**
- <test file>: +<N> tests
- ... (one per file)

**Test delta:** <before>p/<before>f → <after>p/<after>f

**Deferred from this batch (if any):**
- <item> — reason: <...>

**Post-merge notes:**
- <surprises, gotchas, things the reviewer should know>
```

---

## Done criteria (whole Pillar 2 complete)

You are done when **all** of these are true:

1. 10 batches in §7 are present as individual merged commits in `git log`, in order.
2. `python -m pytest tests/` shows ≥ **700 passing, 0 failing, 3 skipped** (baseline 600 + ~100 new tests across batches).
3. `docs/pillar2_progress.md` has a MERGED entry for every batch.
4. Plan Appendix E coverage matrix — walk every row; every ✅ row has a `git log --grep` match on a merged commit, every ⏸️ row has a matching entry in plan §9.
5. `docs/IMPLEMENTATION_LOG.md` has a Pillar 2 section with 10 entries.
6. `CLAUDE.md` / `ARCHITECTURE.md` / `STATUS.md` reflect Pillar 2 state.
7. `git tag` a lightweight tag `pillar2-generator-complete` on the final commit.
8. Append a hand-off note to `docs/pillar2_progress.md` titled **"Generator hand-off to reviewer"** listing the tag, the HEAD sha, and any known-open questions.

Then stop. Do not start Pillar 3 work, do not touch the frontend, do not trigger the reviewer — the human will dispatch the reviewer worktree separately.

---

## If Ralph Loop asks "what's next?"

Read this file. Read `docs/pillar2_progress.md`. The next batch is the first one without a MERGED entry. If all 10 are MERGED, the "Done criteria" checklist above is your next pass — walk it top-to-bottom, fix any gaps, then tag and stop.

---

## One-line sanity check before each iteration

Before touching any code in an iteration, answer this silently: **"What batch am I doing, what does the plan say its Touches list is, and what is my first test going to be?"** If you cannot answer all three in one sentence, you have not read enough.

---

**End of generator prompt.**

# Job360 Docs Index

Landing page for everything in `docs/`. Start here when you need to find a
plan, a status snapshot, a reference, or an architectural decision.

## Getting started

- [`../CONTRIBUTING.md`](../CONTRIBUTING.md) — branch naming, commit
  convention, PR flow, test-before-merge gate.
- [`../backend/README.md`](../backend/README.md) — install, run API, CLI,
  tests, migrations, ARQ worker.
- [`../frontend/README.md`](../frontend/README.md) — install, dev server,
  build, backend wiring.

## Current state

- [`CurrentStatus.md`](CurrentStatus.md) — latest re-audit of source counts,
  test counts, slug catalogs, known gaps. Updated ad-hoc after each stabilisation
  batch.
- [`IMPLEMENTATION_LOG.md`](IMPLEMENTATION_LOG.md) — batch-by-batch completion
  log for Pillars 1–3. Read this first if you are picking up a thread.
- [`../STATUS.md`](../STATUS.md) — project phase summary, what's done, what's
  next, known issues.

## Product / strategy

- [`PRD.md`](PRD.md) — product requirements + vision.
- [`References.md`](References.md) — source-of-truth list of external
  references and research links.

## Execution plans

- [`plans/batch-1-plan.md`](plans/batch-1-plan.md) — Pillar 3 Batch 1
  (date-model rebuild, fabricator fixes, ghost detection, KPI exporter).
- [`plans/batch-2-plan.md`](plans/batch-2-plan.md) — Pillar 3 Batch 2 TDD
  plan for the multi-user delivery layer.
- [`plans/batch-2-decisions.md`](plans/batch-2-decisions.md) — irreversible
  architectural choices (ARQ, Apprise, polling, session cookies).
- [`plans/batch-3-plan.md`](plans/batch-3-plan.md) — tiered polling +
  source expansion.
- `plans/batch-3.5*.md` — stabilisation sub-batches (IDOR fix,
  multi-user profile storage, conditional-cache pilot, test cleanup).

## Architecture

- [`../CLAUDE.md`](../CLAUDE.md) — the load-bearing architecture doc. Data
  flow, module map, hard rules (19 of them), scoring algorithm, env vars,
  Batch 2 + Batch 3 + Pillar 2 additions.
- [`../ARCHITECTURE.md`](../ARCHITECTURE.md) — deeper technical reference with
  diagrams, DB schema, config variables, dependency list.

## Archive

- [`_archive/`](_archive/) — pillar 1 + pillar 2 plans and progress logs,
  and any superseded status diffs.

**Warning:** Files here reflect the state of a past pillar; they have not
been kept current.

## Research

- [`research/`](research/) — pillar-level research reports
  (`pillar_1_report.md`, `pillar_2_report.md`, `pillar_3_report.md`, and
  per-batch Pillar-3 reports).

## Superpowers workflows

- [`superpowers/`](superpowers/) — skill-driven plan artefacts produced by
  the `superpowers:*` workflows (brainstorming, plan writing, plan execution).

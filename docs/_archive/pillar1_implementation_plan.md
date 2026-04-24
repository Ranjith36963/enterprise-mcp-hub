# Pillar 1 Implementation Plan — Profile Parser Upgrade

> **Source report:** `docs/research/pillar_1_report.md` (the file the user referenced as `Open-Source_Patterns_to_Supercharge_Job360_Profile_Parser.md` does not exist on disk — `pillar_1_report.md` is the same document, verified by matching the title on line 1).
> **Audit anchor commit:** `13d4305` (post-Batch-3.5.4). All code claims below cite `file:line` evidence, not memory.
> **Scope:** Pillar 1 = profile understanding (CV + LinkedIn + GitHub → `CVData` → `SearchConfig`). Pillar 2 (semantic matching, embeddings, rerank) is **out of scope** for this plan.
> **Output discipline:** Plan only — no code changes. No TDD cadence. This document exists to scope, sequence, and estimate.

---

## §0 — TL;DR

The Pillar 1 report lists 10 ranked improvements. Of those, **three are fully shipped** (LinkedIn PDF parser, GitHub enricher with language+topic inference, LLM fallback chain Gemini→Groq→Cerebras). **Seven are absent** from `backend/src/`, confirmed by direct grep. The three highest-impact absent items — **ESCO taxonomy**, **strict JSON-schema LLM extraction**, **GitHub dependency-file parsing** — account for ~80% of report-predicted engine-quality gain and can be built in any order relative to each other.

**Recommended execution order:** four batches (1.1 → 1.2 → 1.3 → 1.4), each shippable on its own, with two parallel lanes possible inside Batch 1.2.

---

## §1 — What's Already Shipped (evidence)

### 1.1 Multi-provider LLM fallback chain — SHIPPED

Pillar 1 report item #6 ("Local LLM fallback for graceful degradation") partially satisfied by a **cloud fallback chain**:

- `backend/src/services/profile/llm_provider.py:22-47` — `llm_extract()` tries Gemini → Groq → Cerebras in priority order, accumulates errors, raises `RuntimeError` only if all three fail or no key is set.
- `backend/src/services/profile/llm_provider.py:52-86` — `llm_extract_fast()` reverses priority (Cerebras-first) for latency-sensitive paths. Currently unused in profile parsing (CV uses `llm_extract`), reserved for scoring.
- `backend/src/services/profile/llm_provider.py:89-103` — `_call_gemini` uses `gemini-2.0-flash` + `response_mime_type="application/json"` + `temperature=0.1`.
- `backend/src/services/profile/llm_provider.py:106-122` — `_call_groq` uses `llama-3.3-70b-versatile` + `response_format={"type": "json_object"}`.
- `backend/src/services/profile/llm_provider.py:125-144` — `_call_cerebras` uses `llama3.1-8b` + `response_format={"type": "json_object"}`.

**Gap vs report:** no **local** fallback (Qwen3-0.6B or similar). Still Pillar 1 report item #6.

### 1.2 LinkedIn PDF parser — SHIPPED (pivoted from ZIP/CSV path)

Pillar 1 report item #10 ("LinkedIn parsers — expanded field coverage") is **architecturally different** from what shipped. The report assumed the old Voyager/ZIP/CSV flow (parsing 5–12 CSV files). Job360 replaced that with a **PDF "Save to PDF"** flow:

- `backend/src/services/profile/linkedin_parser.py:1-14` — module docstring states: *"Replaces the older LinkedIn Data Export (ZIP of CSVs) flow. Produces the exact same output dict schema so downstream code is unchanged."*
- `backend/src/services/profile/linkedin_parser.py:34-55` — `_SECTION_HEADINGS` covers 18 LinkedIn profile sections (Contact, Summary, Experience, Education, Skills, Top Skills, Certifications, Licenses & Certifications, Languages, Honors-Awards, Publications, Volunteer Experience, Projects, Recommendations, Interests, Courses, Organizations, Patents, Test Scores).
- `backend/src/services/profile/linkedin_parser.py:84-110` — `is_linkedin_pdf()` heuristic (2-of-3 markers: `linkedin.com/in/` URL + 3+ section headings + `Page N of M` footer).
- `backend/src/services/profile/linkedin_parser.py:115-129` — deterministic section split.
- `backend/src/services/profile/linkedin_parser.py:134-149` — deterministic header extraction (name, headline, industry).
- `backend/src/services/profile/linkedin_parser.py:152-166` — deterministic skills extraction (one-per-line, dedup, `(N)` endorsement-count strip).
- `backend/src/services/profile/linkedin_parser.py:178-215` — three LLM prompts for prose sections (Experience, Education, Certifications), called in parallel via `asyncio.gather` at `:338`.
- `backend/src/services/profile/linkedin_parser.py:304-350` — `parse_linkedin_pdf_async` returns canonical dict `{positions, skills, education, certifications, summary, industry, headline}`.
- `backend/src/services/profile/linkedin_parser.py:369-412` — `enrich_cv_from_linkedin` merges into `CVData`, deduplicating by `.lower()` on skills/titles/education/certs.

**Report gap vs reality:** The report's "defensive CSV parsing" recommendation is moot — there are no CSVs. The report's "parse 12 CSV files instead of 5" claim does not apply. What's **still missing** for LinkedIn: the report's broader theme of "parse more fields" — specifically `Courses`, `Languages`, `Projects`, `Volunteer Experience`, `Publications`, `Honors-Awards`, `Patents`, `Test Scores`, `Recommendations`. Headings are detected at `:34-55` but bodies of sections outside {Experience, Education, Skills, Certifications, Summary, header} are **discarded**. See `:316-327` — only 6 section keys are read.

### 1.3 GitHub enricher — SHIPPED (language + topic only, no dependency parsing)

Pillar 1 report item #11 ("GitHub analyzers — dependency parsing is the biggest gap"):

- `backend/src/services/profile/github_enricher.py:20` — `MAX_REPOS = 30` (matches report's "top 30 repos" recommendation).
- `backend/src/services/profile/github_enricher.py:23-55` — `LANGUAGE_TO_SKILL`: **32 mappings** (Python, JavaScript, …, HTML).
- `backend/src/services/profile/github_enricher.py:58-102` — `TOPIC_TO_SKILL`: **45 mappings** (react, django, fastapi, pytorch, machine-learning, devops, …).
- `backend/src/services/profile/github_enricher.py:132-194` — `fetch_github_profile` pulls `/users/{username}/repos?per_page=30&sort=pushed` then fetches per-repo `/languages` for the top 20 repos.
- `backend/src/services/profile/github_enricher.py:197-216` — `_infer_skills` ranks by code bytes (languages), then appends topics.
- `backend/src/services/profile/github_enricher.py:219-232` — `enrich_cv_from_github` merges into `CVData.github_*` fields.

**Gaps vs report item #11:**
- No **dependency-file parsing** (`requirements.txt`, `package.json`, `pyproject.toml`, `Cargo.toml`, `Gemfile`, `go.mod`, `composer.json`). Zero live references in the file. Report claims this is "the biggest gap" — confirmed.
- No **temporal weighting** (repos pushed in last 12 months ≠ 3× weight). Current ranking is code-bytes only, ignoring `pushed_at`.
- Mapping count is 32+45 = 77 (report said 82; close enough — both are "~static tables").

### 1.4 Defensive LLM response coercion — SHIPPED

Not called out separately in the report, but worth noting as existing infrastructure:

- `backend/src/services/profile/cv_parser.py:176-177` — imports `_coerce_str` and `_coerce_str_list` from `_llm_utils.py`.
- `backend/src/services/profile/cv_parser.py:180-256` — `_llm_result_to_cvdata` type-guards every field; weak LLMs (Cerebras llama3.1-8b, Groq llama-3.3-70b) deviating from schema don't crash the parser.

This is a **partial substitute** for Pillar 1 report item #2 (Pydantic validation). It catches type errors but cannot catch semantic errors (empty required fields, wrong enums, hallucinated keys) — no retry loop with validation feedback.

### 1.5 Data model: `CVData`, `UserProfile`, `SearchConfig` — SHIPPED

- `backend/src/services/profile/models.py:9-48` — `CVData` with separate scoring-semantic fields (`skills`, `job_titles`, `companies`, `education`, `certifications`) and display-only fields (`name`, `headline`, `location`, `achievements`). LinkedIn-sourced fields (`linkedin_positions`, `linkedin_skills`, `linkedin_industry`) and GitHub-sourced fields (`github_languages`, `github_topics`, `github_skills_inferred`) are **per-source**, which means the raw data is preserved — but there is no `source` or `confidence` attribute on individual extracted items.
- `backend/src/services/profile/models.py:52-64` — `UserPreferences` (`target_job_titles`, `additional_skills`, `excluded_skills`, `preferred_locations`, `industries`, `salary_min/max`, `work_arrangement`, `experience_level`, `negative_keywords`, `github_username`, `about_me`).
- `backend/src/services/profile/models.py:67-79` — `UserProfile` = `CVData` + `UserPreferences` composition.
- `backend/src/services/profile/models.py:82-117` — `SearchConfig` (11 fields including tiered skill lists).
- `backend/src/services/profile/storage.py:42-84` — per-user DB storage via `user_profiles` table (Batch 3.5.2). Upserts entire dataclass as JSON blobs (`cv_data`, `preferences`).

### 1.6 Keyword generator — SHIPPED, but with the naive tiering the report targets

- `backend/src/services/profile/keyword_generator.py:27-140` — `generate_search_config(profile)` converts `UserProfile` → `SearchConfig`.
- `backend/src/services/profile/keyword_generator.py:67-75` — **the naive position-based thirds split the Pillar 1 report explicitly targets**:
  ```python
  t1 = max(n // 3, 1)
  t2 = max(2 * n // 3, t1 + 1) if n > 1 else t1
  primary = all_skills[:t1]
  secondary = all_skills[t1:t2]
  tertiary = all_skills[t2:]
  ```
  Ordering reflects (1) user-declared `additional_skills`, then (2) CV LLM-extracted skills, then (3) LinkedIn skills, then (4) GitHub-inferred skills. There is no frequency, recency, or importance signal feeding the split.
- `backend/src/services/profile/keyword_generator.py:119-126` — search queries are top-8 titles × top-2 locations = up to 16 queries. Not archetype-aware, not domain-aware.

### 1.7 Ecosystem-absent evidence (grep-confirmed)

Quoting `backend/src` grep results (re-verified for this plan):
- `sentence_transformers` → 0 hits
- `esco` / `ESCO` → 0 hits in `src/`; only hit is `backend/src/core/companies.py` (coincidental word `Escorts` in ATS slug list) — **no taxonomy data, no loader, no embeddings**.
- `onet` / `O\*NET` → 0 hits.
- `skillner` / `SkillNer` / `TechWolf` / `ConTeXT` → 0 hits.
- `pydantic.*BaseModel.*CV` / `json_schema.*strict` → 0 hits.
- `cv_explicit` / `linkedin_sourced` / `provenance` / `confidence.*extract` → 0 hits in `services/profile/`.
- `backend/data/esco*` → no files exist.
- `CurrentStatus.md:424` confirms: *"Absent: sentence-transformers · chromadb · pgvector · ESCO lib · Prometheus client (in pyproject — but exporter lives at `backend/ops/`)"*.
- `CurrentStatus_diff.md:240` lists *"ESCO taxonomy absent. Pillar 1 prerequisite — not yet present."* in the headline-gaps table.

---

## §2 — What's Still in the Report but Not in the Codebase

Mapping the 10 ranked improvements in `pillar_1_report.md` lines 231–349 to current code state.

| # | Report name | Status | Evidence of absence |
|---|---|---|---|
| 1 | ESCO-based skill normalization + tiering (HIGH) | **NOT SHIPPED** | No `sentence-transformers` dep; no ESCO CSV under `backend/data/`; naive thirds at `keyword_generator.py:67-75` |
| 2 | Strict JSON-schema LLM extraction + Pydantic validation (HIGH) | **NOT SHIPPED** | `response_format={"type": "json_object"}` at `llm_provider.py:120,142` — NOT `{"type": "json_schema", "strict": true}`; no Pydantic model for CV output; no retry-with-error-feedback loop |
| 3 | GitHub dependency-file parsing (HIGH) | **NOT SHIPPED** | Grep `requirements.txt\|package.json\|pyproject.toml\|Cargo.toml` → 0 hits in `github_enricher.py`; only `repo['name']`, `language`, `topics` are used (`:166`, `:204`) |
| 4 | NER pre-filtering before LLM extraction (MEDIUM-HIGH) | **NOT SHIPPED** | No `spacy`, `skillner`, or `TechWolf/ConTeXT` dep in `pyproject.toml`; CV text goes directly to LLM at `cv_parser.py:152` |
| 5 | Expanded LinkedIn parsing with defensive patterns (MEDIUM) | **PARTIAL** | PDF path covers Experience/Education/Skills/Certifications/Summary/header only (`linkedin_parser.py:316-327`); 13 other detected sections discarded. Defensive patterns (case-insensitive column matching, fallback names) are **N/A for PDF path** — original report context was CSV |
| 6 | Local LLM fallback for graceful degradation (MEDIUM) | **NOT SHIPPED** | No local model deployment; fallback chain is cloud-only (`llm_provider.py:22-47`) |
| 7 | JSON Resume canonical profile schema with versioning (MEDIUM) | **NOT SHIPPED** | `models.py` uses custom dataclasses, not JSON Resume schema; storage at `user_profiles.cv_data` JSON column is a single-row upsert — no versioned snapshots (`storage.py:42-60`) |
| 8 | Provenance-tracked multi-source conflict resolution (MEDIUM) | **NOT SHIPPED** | `CVData` separates source fields (`linkedin_*`, `github_*`) but individual `skills[]` entries have no `source` / `confidence`; merge functions at `linkedin_parser.py:369`, `github_enricher.py:219` dedup by `.lower()` — no confidence-weighted merge, no conflict resolution |
| 9 | Layout-aware PDF preprocessing (LOWER) | **NOT SHIPPED** | `cv_parser.py:92-95` uses `page.extract_text()` — flat text only; no `extract_words(extra_attrs=["fontname","size"])` call anywhere in `services/profile/` |
| 10 | Archetype classification for contextual matching (LOWER) | **NOT SHIPPED** | No `archetype` field on `CVData`/`UserProfile`; `keyword_generator.py:119-126` generates search queries without archetype branching |

**Bonus (report §"Key data downloads"):** ESCO v1.2.1 CSV, O\*NET database, `sentence-transformers`, `ojd-daps-skills`, `esco-skill-extractor`, `skillNer`, TechWolf ConTeXT HF model, `resume-ner-bert-v2` HF model, JSON Resume schema, Lightcast Open Skills API — **none** are present as deps or data files.

---

## §3 — Dependency Graph Between Remaining Items

Ranked by feeds-into edges rather than by report priority. Each arrow = "A unlocks B; B cannot ship cleanly before A."

```
                       ┌───────────────────────────────┐
                       │ #2 Strict JSON schema +       │
                       │    Pydantic CV model          │
                       │    (HIGH — foundational)      │
                       └────────────┬──────────────────┘
                                    │ unlocks typed output
                                    ├───────────────────────────────┐
                                    │                               │
                                    ▼                               ▼
              ┌──────────────────────────────┐   ┌──────────────────────────────┐
              │ #8 Provenance + confidence   │   │ #10 Archetype classification │
              │    (needs typed CVData)      │   │     (16 enums from #2)       │
              └────────────┬─────────────────┘   └────────────┬─────────────────┘
                           │ feeds confidence signal          │ feeds weight adjustment
                           │                                  │
                           └───────────────┬──────────────────┘
                                           │
         ┌─────────────────────────────────┼──────────────────────────────────┐
         │                                 │                                  │
         ▼                                 ▼                                  ▼
  ┌──────────────┐            ┌────────────────────────┐          ┌──────────────────────┐
  │ #1 ESCO      │◀──────┐    │ #3 GitHub dep-file     │          │ #5 Expanded LinkedIn │
  │ taxonomy +   │       │    │    parsing             │          │    sections          │
  │ tiering      │       │    │    (independent)       │          │    (independent)     │
  │ (HIGH)       │       │    └───────────┬────────────┘          └──────────┬───────────┘
  └──────┬───────┘       │                │ produces more skills             │ produces more
         │               │                │                                  │ skills
         │ feeds skill   │                ▼                                  ▼
         │ normalization │        ┌──────────────────────────────────────────────┐
         │               └────────│ All extracted skills run through ESCO map    │
         │                        └───────────────────┬──────────────────────────┘
         ▼                                            │
  ┌──────────────────────┐                           │
  │ #4 NER pre-filter    │                           │
  │    (needs ESCO to    │                           │
  │    map spans)        │                           │
  └──────────────────────┘                           ▼
                                     ┌──────────────────────────────┐
                                     │ #7 JSON Resume canonical +   │
                                     │    versioned snapshots       │
                                     │    (needs stable schema)     │
                                     └──────────────────────────────┘

  ┌──────────────────────────────┐     ┌──────────────────────────────┐
  │ #9 Layout-aware PDF          │     │ #6 Local LLM fallback        │
  │    (independent, pre-LLM)    │     │    (independent, post-cloud) │
  └──────────────────────────────┘     └──────────────────────────────┘
```

### Dependency rules read plain-English

- **#2 (Strict JSON schema + Pydantic) is foundational.** Everything downstream wants a typed `CVData`. Ship first.
- **#8 (Provenance) requires #2** because it adds `source`/`confidence` fields to the schema. Cheap once #2 is in.
- **#10 (Archetype) requires #2** because the 16 HiringCafe category enums are the classification target; the report specifies them as a schema field.
- **#1 (ESCO) is independent of #2 but benefits from it.** ESCO maps raw skill strings → canonical URIs. If strings come pre-validated (Pydantic), fewer garbage inputs reach the embedding step.
- **#3 (GitHub dep-file parsing) is fully independent** — adds new skills upstream of ESCO mapping. Can ship before, during, or after #1.
- **#4 (NER pre-filter) depends on #1** because NER produces spans that must map to ESCO to replace LLM calls.
- **#5 (Expanded LinkedIn sections) is independent** — new LLM prompts for additional section types.
- **#7 (JSON Resume schema + versioning) requires #2** to produce a stable typed schema before renaming fields to JSON Resume canon. Also depends on a DB migration for snapshot versioning.
- **#9 (Layout-aware PDF) is fully independent** — pre-processing step before LLM extraction, agnostic to downstream.
- **#6 (Local LLM) is fully independent** — infrastructure choice, orthogonal to pipeline shape.

### Critical path

**#2 → #1 → #4** is the longest dependency chain (three hops, all medium-high complexity). This defines the minimum end-to-end delivery timeline if the critical items are sequenced.

---

## §4 — Batch Breakdown (Small, Shippable Units)

Each batch produces a deployable behaviour improvement on its own, with its own tests.

### Batch 1.1 — Strict schema + Pydantic validation + retry loop

**Covers:** Report #2 + part of #8 (source attribution groundwork)
**Touches:**
- `backend/src/services/profile/llm_provider.py` — swap `response_format` to strict JSON schema where supported (Gemini: `response_schema`; Groq/Cerebras: keep `json_object` + Pydantic post-validation).
- `backend/src/services/profile/cv_parser.py` — replace `_llm_result_to_cvdata` manual coercion with Pydantic `.model_validate_json(...)`. Add 16-enum `career_domain` field. Add nullable field definitions.
- **New:** `backend/src/services/profile/schemas.py` — Pydantic models mirroring `CVData` with nullable optional fields.
- Retry-on-validation-failure loop in `llm_extract`: on `ValidationError`, feed error text back to the LLM for correction (max 2 retries).
- `backend/pyproject.toml` — bump `pydantic` floor to a version supporting `model_validate_json` (≥2.0); already present transitively via FastAPI.

**Out of scope:** ESCO, NER, dep-file parsing.
**Test surface:** `tests/test_llm_provider.py` (8 tests already exist), `tests/test_profile.py` (CV parsing fixtures), new `tests/test_cv_schema.py`.
**Effort:** **S–M** (3–5 engineer-days). Low risk, mostly schema wiring.

### Batch 1.2 — GitHub dependency-file parsing + temporal weighting

**Covers:** Report #3.
**Touches:**
- `backend/src/services/profile/github_enricher.py` — add `_fetch_dependency_files(username, repo_name)` that pulls `package.json`, `requirements.txt`, `pyproject.toml`, `Cargo.toml`, `Gemfile`, `go.mod`, `composer.json` via `GET /repos/{owner}/{repo}/contents/{path}`. Add a **dependency → skill** mapping (≥200 entries).
- `backend/src/services/profile/github_enricher.py:197-216` — extend `_infer_skills` with temporal weighting: if `pushed_at` within 12 months → multiply byte weight ×3 before ranking.
- `backend/src/services/profile/models.py` — add `github_frameworks: list[str]` to `CVData` (distinct from `github_skills_inferred` to preserve audit trail).
- **New:** `backend/src/services/profile/dependency_map.py` — curated mapping module.

**Out of scope:** ESCO mapping of the new skills (that's Batch 1.3).
**Test surface:** `tests/test_linkedin_github.py` already has 46 tests; add ≥15 new tests covering each manifest format, missing-file fallback, rate-limit handling, and temporal weighting edge cases.
**Effort:** **M** (5–7 engineer-days). GitHub API work is well-trodden; the dependency→skill mapping is the bulk of the curation effort.

### Batch 1.3 — ESCO taxonomy + semantic skill normalization + evidence-based tiering

**Covers:** Report #1 + `esco_uri` field for #8.
**Touches:**
- **New:** `backend/data/esco/` — ESCO v1.2.1 CSV dataset download + precomputed embeddings (`all-MiniLM-L6-v2`, ~13,900 skills × 384 dims ≈ 21 MB). Script: `backend/scripts/build_esco_index.py` (one-shot generator).
- **New:** `backend/src/services/profile/skill_normalizer.py` — `normalize_skill(raw: str) → ESCOMatch | None` using cosine similarity over precomputed embeddings. Includes alias-label fallback from ESCO's alternative-labels column.
- **New:** `backend/src/services/profile/skill_tiering.py` — replaces `keyword_generator.py:67-75` thirds split. Inputs: list of `(skill, source, last_mentioned_date, frequency)`; output: primary/secondary/tertiary using (a) ESCO essential/optional label for target occupation, (b) frequency across sections, (c) recency weight, (d) O\*NET importance (if mapped).
- `backend/src/services/profile/keyword_generator.py:67-75` — delete naive thirds split; delegate to `skill_tiering.tier_skills(...)`.
- `backend/src/services/profile/models.py` — add `esco_uri: Optional[str]` to each skill (requires a skill sub-object; easiest via a `SkillEntry` dataclass, migrated from the bare `list[str]`).
- `backend/pyproject.toml` — add `sentence-transformers>=2.2`, `numpy>=1.24` (numpy comes in transitively but pin for sentence-transformers), `scikit-learn>=1.3` for cosine similarity (optional — can hand-roll dot product to skip the dep).

**Out of scope:** O\*NET integration (treat as stretch; can be a sub-batch 1.3b if we hit 5-day budget).
**Risk:** First-boot cost — precomputing 13,900 embeddings on `all-MiniLM-L6-v2` takes ~30s on CPU. Ship as a build-time script output (check into the repo as `backend/data/esco/embeddings.npy` + `labels.json`), NOT computed at runtime.
**Test surface:** new `tests/test_skill_normalizer.py` (cosine similarity sanity, alias-fallback, cache hits), new `tests/test_skill_tiering.py`.
**Effort:** **M–L** (7–12 engineer-days). The embedding-build pipeline plus tiering algorithm design plus `list[str]` → `list[SkillEntry]` migration is the bulk. Schema migration ripples into `keyword_generator.py`, `JobScorer.score()`, `storage.py` JSON serialization, and `frontend/src/lib/types.ts`.

### Batch 1.4 — Provenance + confidence-weighted merge

**Covers:** Report #8 fully.
**Touches:**
- `backend/src/services/profile/models.py` — upgrade `list[str]` skills fields to `list[SkillEntry]` where `SkillEntry = {name, source, confidence, esco_uri, last_seen}`. If Batch 1.3 already migrated to `SkillEntry`, this is additive (add `source` + `confidence` fields).
- `backend/src/services/profile/linkedin_parser.py:369-412` — `enrich_cv_from_linkedin` writes `source="linkedin"` + `confidence=0.9` per entry.
- `backend/src/services/profile/github_enricher.py:219-232` — `enrich_cv_from_github` writes `source="github_dep" | "github_lang" | "github_topic"` + `confidence ∈ {0.7, 0.5, 0.4}`.
- `backend/src/services/profile/cv_parser.py:180-256` — CV extraction writes `source="cv_explicit"` + `confidence=0.85`.
- **New:** `backend/src/services/profile/merge.py` — `merge_profile_sources(entries: list[SkillEntry]) → list[SkillEntry]`. Deduplicate by `esco_uri` when available, else by normalized name. Conflict resolution: highest-confidence wins, tie-break by most-recent.

**Out of scope:** UI surfacing of provenance (that's a frontend task — separate plan).
**Test surface:** new `tests/test_profile_merge.py`.
**Effort:** **S–M** (3–5 engineer-days). Mostly bookkeeping once the schema is in place from 1.3.

### Batch 1.5 — Expanded LinkedIn PDF sections

**Covers:** Report #5 (adjusted — PDF not CSV).
**Touches:**
- `backend/src/services/profile/linkedin_parser.py:178-215` — add 4 new LLM prompts for `Languages`, `Projects`, `Volunteer Experience`, `Courses`. Skip the rare ones (`Patents`, `Test Scores`, `Honors-Awards`, `Recommendations`) — judgement call, revisit if user data shows usage.
- `backend/src/services/profile/linkedin_parser.py:304-350` — add 4 new keys to the canonical dict. Run all prompts in parallel via `asyncio.gather`.
- `backend/src/services/profile/models.py` — add `linkedin_projects`, `linkedin_volunteer`, `linkedin_languages`, `linkedin_courses` to `CVData`.
- `backend/src/services/profile/linkedin_parser.py:369-412` — extend `enrich_cv_from_linkedin` to merge the new fields.

**Out of scope:** `Recommendations`, `Patents`, `Test Scores`, `Honors-Awards` (low signal-to-noise).
**Test surface:** `tests/test_linkedin_github.py` — add ≥8 new fixtures.
**Effort:** **S** (2–3 engineer-days). Parallel LLM prompt additions with similar structure to the existing three.

### Batch 1.6 — NER pre-filter (optional — efficiency, not correctness)

**Covers:** Report #4.
**Touches:**
- `backend/pyproject.toml` — add `transformers>=4.36`, `torch>=2.1` (CPU-only wheel). **Significant dep bloat** (~500 MB). Gate behind an optional extra: `[project.optional-dependencies] ner = ["transformers", "torch"]`.
- **New:** `backend/src/services/profile/skill_ner.py` — lazy-load `TechWolf/ConTeXT-Skill-Extraction-base`. `extract_skill_spans(text) → list[str]`. Only runs if `ner` extra is installed; otherwise path is a no-op.
- `backend/src/services/profile/cv_parser.py:137-157` — modify `parse_cv_async` to pre-filter skill spans via NER, pass remaining text + pre-extracted skills to LLM (prompt instructs LLM "skills already extracted: [...], do not re-extract; focus on experience + education").

**Out of scope:** Fine-tuning the NER model. Training data preparation.
**Test surface:** skip entirely in default CI (model download is ~400 MB); add a `@pytest.mark.slow` suite gated behind `RUN_NER_TESTS=1`.
**Effort:** **M** (5–7 engineer-days). Most of the time is on the optional-extra wiring and the model download / cache management. The algorithm is straightforward.

### Batch 1.7 — Layout-aware PDF preprocessing (optional — parse quality uplift)

**Covers:** Report #9.
**Touches:**
- `backend/src/services/profile/cv_parser.py:82-100` — replace `page.extract_text()` with `page.extract_words(extra_attrs=["fontname","size"])`. Cluster by font size (headers ≈ body+2pt), emit section boundaries.
- **New:** `backend/src/services/profile/layout.py` — `segment_sections(words: list[dict]) → dict[str, str]`. Heuristics: font size 2pt+ above median → header; line gap > 1.4× median → subsection.
- `backend/src/services/profile/cv_parser.py:149` — change the LLM prompt template to accept pre-segmented sections (reduces token usage, improves accuracy per OpenResume pattern).

**Out of scope:** YOLO layout detection (over-engineered for CVs).
**Test surface:** new `tests/test_cv_layout.py` with 2–3 sample PDFs exercising section detection.
**Effort:** **S–M** (3–5 engineer-days). `pdfplumber.extract_words` is well-documented; the clustering heuristic is the main design work.

### Batch 1.8 — JSON Resume canonical schema + versioned snapshots

**Covers:** Report #7.
**Touches:**
- `backend/src/services/profile/models.py` — **rewrite** `CVData` / `UserProfile` to JSON Resume canonical field names (`basics`, `work`, `education`, `skills`, `languages`, `projects`, `certificates`, `awards`, `interests`, `references`, `meta`). Preserve custom fields (`source`, `confidence`, `esco_uri`, `career_domain`) via `meta` or per-field extensions.
- **New migration:** `backend/migrations/0007_user_profile_versions.up.sql` — adds `user_profile_versions` table: `(id, user_id, created_at, snapshot_json, source_action)` where `source_action ∈ {"cv_upload", "linkedin_upload", "github_refresh", "user_edit"}`.
- `backend/src/services/profile/storage.py:42-60` — on every `save_profile`, **append** a row to `user_profile_versions`. Current `user_profiles` row becomes the tip (mutable); versions give history.
- Downstream ripple: `frontend/src/lib/types.ts` rename, `keyword_generator.py` field access updates, `cli.py:setup-profile` output format.

**Out of scope:** History UI in frontend (separate plan).
**Test surface:** `tests/test_profile_storage.py` already has 12 tests; add ≥6 new covering version insert, rollback, latest-fetch.
**Effort:** **L** (10–15 engineer-days). Largest ripple surface — touches storage, models, serialization, CLI, frontend types. Ship last.

### Batch 1.9 — Local LLM fallback (deferred — not pre-launch)

**Covers:** Report #6.
**Recommendation:** **Do not ship in Pillar 1.** Cloud fallback chain (Gemini → Groq → Cerebras) already provides graceful degradation. Local model adds training-data annotation cost, fine-tuning infra, deployment complexity, and gguf caching — all for a marginal availability improvement. Park until: (a) cloud quota becomes a binding constraint, (b) privacy regs force on-prem inference, or (c) latency requirements rule out cloud.
**Effort if undertaken:** **XL** (15–25 engineer-days including training data annotation).

### Batch 1.10 — Archetype classification (deferred — Pillar 2 territory)

**Covers:** Report #10.
**Recommendation:** **Defer to Pillar 2.** Archetype-aware scoring weights only pay off if the scoring engine can use them — that's Pillar 2's concern (`JobScorer` refactor). The 16-enum `career_domain` field lands in Batch 1.1 as a schema field, which is sufficient prep; the actual per-archetype weight table and `SearchConfig.query_generator` branching belong in Pillar 2.
**Effort if undertaken:** **M** (5–8 engineer-days).

---

## §5 — Parallelism: Which Batches Run Together

**Critical serial chain (must be sequential):** `1.1 → 1.3 → 1.4`

- 1.1 defines the Pydantic schema.
- 1.3 adds `esco_uri` to the schema → migrates `list[str]` skills → `list[SkillEntry]`.
- 1.4 adds `source`/`confidence` to `SkillEntry` (additive).

Running 1.3 and 1.4 concurrently risks two competing migrations of the same `list[str]` field. Same with running 1.1 and 1.3 concurrently — Pydantic field names must stabilize before ESCO fields are added.

**Parallel lanes (independent once 1.1 is in):**

```
                 ┌─── Batch 1.1 (Strict schema / Pydantic — FOUNDATIONAL) ───┐
                 └───────────────────────────┬────────────────────────────────┘
                                             │
              ┌──────────────────────────────┼──────────────────────────────────┐
              │                              │                                   │
              ▼                              ▼                                   ▼
      ┌───────────────┐            ┌────────────────┐                  ┌────────────────┐
      │ Batch 1.2     │            │ Batch 1.3      │                  │ Batch 1.5      │
      │ GitHub dep-   │ ─────┐     │ ESCO + tiering │    parallel      │ Expanded       │
      │ file parsing  │      │     └───────┬────────┘  ◀──────────────▶│ LinkedIn       │
      └───────┬───────┘      │             │                           └────────────────┘
              │              │             ▼
              │              │     ┌────────────────┐
              │              │     │ Batch 1.4      │
              │              └────▶│ Provenance     │ (needs 1.3's SkillEntry)
              │                    │ + confidence   │
              │                    └────────────────┘
              │
              ▼ (new github skills also flow through 1.3's normalizer)
      ┌────────────────┐
      │ Batch 1.6 NER  │ (needs 1.3's ESCO index)
      │ (optional)     │
      └────────────────┘

      ┌────────────────┐   ┌────────────────┐   ┌────────────────┐
      │ Batch 1.7 PDF  │   │ Batch 1.8 JSON │   │ Batch 1.9 Local│
      │ layout (indep) │   │ Resume + vers. │   │ LLM (deferred) │
      └────────────────┘   └────────────────┘   └────────────────┘
```

- **1.2 || 1.3 || 1.5 || 1.7** — four independent parallel lanes after 1.1 lands.
- **1.4** waits on 1.3 (uses `SkillEntry`).
- **1.6** waits on 1.3 (uses ESCO index).
- **1.8** benefits from 1.1 (stable schema) and 1.4 (final field set) — safest to land last.

### Headcount calibration

- **1 engineer:** strict serial run 1.1 → 1.2 → 1.3 → 1.4 → 1.5 → 1.7 → 1.8. ~6–9 calendar weeks end-to-end. Skip 1.6 unless NER efficiency becomes necessary.
- **2 engineers:** after 1.1, split into dep-file lane (1.2) and ESCO lane (1.3 → 1.4). Then parallel 1.5 & 1.7 & 1.8. ~4–6 calendar weeks end-to-end.
- **3+ engineers:** diminishing returns — all three parallel lanes (1.2, 1.3, 1.5) can run simultaneously, but 1.1's schema decisions are the bottleneck all three depend on. Ship 1.1 fast.

---

## §6 — Effort Estimates (Summary Table)

Effort bands: S = 2–3 eng-days, M = 5–7 eng-days, L = 10–15 eng-days, XL = 15–25 eng-days. These are coding + test + review + bug-fix; not calendar time.

| Batch | Report # | Effort | Value | Ship priority |
|---|---|---|---|---|
| 1.1 Strict schema + Pydantic | #2 | **S–M** (3–5 d) | HIGH — unlocks all downstream | **1** |
| 1.2 GitHub dep-file parsing | #3 | **M** (5–7 d) | HIGH — closes the "biggest gap" per report | **2** (parallel with 1.3) |
| 1.3 ESCO + evidence-based tiering | #1 | **M–L** (7–12 d) | HIGH — replaces the naive thirds split | **3** (critical path) |
| 1.4 Provenance + confidence | #8 | **S–M** (3–5 d) | MEDIUM — quality-of-life for conflicts | **4** |
| 1.5 Expanded LinkedIn sections | #5 | **S** (2–3 d) | MEDIUM — more data, same pipeline | **5** (parallel) |
| 1.6 NER pre-filter | #4 | **M** (5–7 d) | MEDIUM (efficiency only) | **6** (optional) |
| 1.7 Layout-aware PDF | #9 | **S–M** (3–5 d) | LOW–MEDIUM — parse quality uplift | **7** (parallel, optional) |
| 1.8 JSON Resume + versioning | #7 | **L** (10–15 d) | MEDIUM — interop, history | **8** (land last) |
| 1.9 Local LLM fallback | #6 | XL (15–25 d) | LOW today | **DEFER** |
| 1.10 Archetype classification | #10 | M (5–8 d) | LOW until Pillar 2 exists | **DEFER** |

**Total Pillar 1 budget (excluding deferred):** ~38–59 engineer-days.

---

## §7 — Recommended Order

Assuming **one engineer, serial execution, aggressive ship-small cadence**:

1. **Batch 1.1** — Strict JSON schema + Pydantic + retry loop. **Everything downstream improves on day one.** Report explicitly calls this the lowest-complexity high-impact change.
2. **Batch 1.2** — GitHub dependency-file parsing. **Independent, ships value immediately without touching the schema migration path.** Report calls this "the biggest gap." Low-risk.
3. **Batch 1.3** — ESCO taxonomy + evidence-based tiering. **The critical path item.** Do it third because (a) Pydantic schema is stable, (b) GitHub has already introduced more skills that benefit from normalization, (c) the embedding-build pipeline and `SkillEntry` migration are the riskiest work in Pillar 1 — deserve focused attention.
4. **Batch 1.4** — Provenance + confidence. **Cheap addition** once `SkillEntry` exists.
5. **Batch 1.5** — Expanded LinkedIn sections. **Small, contained win** — more profile data for users who export from LinkedIn.
6. **Batch 1.7** — Layout-aware PDF. **Quality uplift** on CV parsing that doesn't depend on the semantic layer.
7. **Batch 1.8** — JSON Resume + versioned snapshots. **Ship last** because it touches the widest surface (models + storage + frontend types + CLI output) and is safest when the skill schema has stopped moving.
8. **Batch 1.6** — NER pre-filter. **Optional.** Only pursue if LLM quota/latency becomes the bottleneck. Otherwise the ~500MB dep bloat isn't worth the token savings.
9. **Batch 1.9 / 1.10** — **Deferred.** See §4.9 and §4.10.

### What NOT to do first

- **Do NOT start with ESCO.** It's the highest-impact item but has the biggest schema-migration ripple. Without Pydantic (1.1) first, the `list[str] → list[SkillEntry]` migration happens mid-field; downstream callers break without type checking.
- **Do NOT start with JSON Resume schema.** It's the biggest surface, the least differentiating change, and its value depends on ecosystem interop that isn't urgent.
- **Do NOT bundle 1.3 + 1.4 as one batch.** Provenance is cheap once `SkillEntry` exists; bundling doubles the review surface and the blast radius of a rollback.

---

## §8 — Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| ESCO dataset licensing (CC BY 4.0 — requires attribution) | Low — attribution in `LICENSE` / `README` | Add attribution line at ESCO import time |
| `sentence-transformers` + `numpy` adds ~300 MB to Docker image | Medium — slows cold start | Consider ONNX Runtime alternative or prune to `all-MiniLM-L6-v2` only; ship CPU-only wheels |
| Embedding-build script takes ~30s; must NOT run in request path | High if accidental | Commit the index into the repo; runtime loads numpy array only |
| Pydantic strict schema breaks Groq/Cerebras (neither supports OpenAI-style `json_schema` mode) | Medium | Keep `json_object` mode + Pydantic post-validation for non-Gemini providers; use strict mode only on Gemini |
| `SkillEntry` migration forces `storage.py` + frontend `types.ts` sync | High on first deploy | Write a one-shot migration in `load_profile` that coerces legacy `list[str]` into `list[SkillEntry]` with `source="legacy"`, `confidence=0.5` |
| GitHub API rate limits on dep-file fetches (30 repos × up to 7 manifests = 210 API calls) | Medium | Respect `Authorization: token $GITHUB_TOKEN` (already present `github_enricher.py:111-112`); cache dep-file results per-repo per `pushed_at` |
| LinkedIn PDF LLM prompts × 4 new sections = 4× more LLM calls per parse | Low–Medium (quota, latency) | Already use `asyncio.gather` at `linkedin_parser.py:338`; widening the gather list is transparent |
| Versioned snapshots (Batch 1.8) balloon DB size | Low (SQLite, one row per profile action, JSON blobs ≲5 KB) | Add retention policy: keep last 10 versions per user, delete older |

---

## §9 — Out of Scope for Pillar 1

Explicitly flagged so future plans don't creep:

- **Scoring engine changes** (`skill_matcher.py`). That's Pillar 2.
- **Semantic job-to-profile matching** (embedding jobs, reranking, BM25+RRF). Pillar 2.
- **Ghost-job detection via LLM** (`main.py:144-187` ghost pass is syntactic; report item #3 in career-ops analysis). Pillar 2.
- **Frontend visualisation of skill tiers + provenance.** Separate frontend plan.
- **Postgres migration** (currently SQLite). Needed eventually for pgvector but not blocking Pillar 1.
- **Lightcast Open Skills API.** Commercial-tier taxonomy alternative to ESCO. ESCO is free and sufficient.

---

## §10 — Acceptance Signals

What "Pillar 1 done" looks like, per batch:

- **1.1 done when:** `pytest tests/test_llm_provider.py tests/test_profile.py` passes with strict-schema mode on Gemini and Pydantic validation on all three providers. Retry loop verified to correct one common error class (missing required field).
- **1.2 done when:** GitHub enricher extracts ≥200 distinct framework skills across a test corpus of 10 sample profiles. Temporal weighting verified with a deterministic fixture (recent repo's language out-ranks an older repo with higher byte count).
- **1.3 done when:** 500-skill test fixture maps to ESCO with ≥85% accuracy. Tiering produces evidence-based primary/secondary/tertiary splits that agree with ESCO essential/optional for at least 3 target occupations (Software Developer, Nurse Practitioner, Financial Analyst).
- **1.4 done when:** A user with CV + LinkedIn + GitHub produces a merged skill list where each entry has `source`, `confidence`, and conflicts are resolved by confidence-then-recency. Audit table preserved.
- **1.5 done when:** Sample LinkedIn PDF with `Languages`, `Projects`, `Volunteer Experience`, `Courses` sections produces non-empty fields for each.
- **1.6 done when (optional):** NER pre-filter reduces median LLM input token count by ≥50% on a 10-CV benchmark.
- **1.7 done when (optional):** 3-column CV layout previously mis-parsed (skills bleeding into experience) now parses with correct section boundaries.
- **1.8 done when:** Saving a profile writes a snapshot row; loading latest returns the tip; rolling back to version N restores prior state.

---

## §11 — Self-review

Checked against the report (`pillar_1_report.md`):

- **All 10 ranked improvements covered?** Yes — items #1–#10 map to batches 1.1–1.10.
- **All claims anchored?** Yes — every "shipped" claim cites `file:line`, every "not shipped" claim cites a grep null-result.
- **Placeholder scan?** No TBD/TODO/FIXME. All file paths are exact. Effort estimates are ranges (S/M/L/XL) with day counts, not vague.
- **Type consistency?** `SkillEntry` referenced in 1.3, 1.4, 1.8 — defined first in 1.3. `career_domain` referenced in 1.1 and 1.10 — defined first in 1.1.
- **Dependency ordering valid?** `1.1 → 1.3 → 1.4` chain verified; `1.2/1.5/1.7` independent lanes verified. `1.6` gated on 1.3 (ESCO index).

One known weakness: §6 effort estimates are upper-bound on a fresh codebase. Job360 has 600 passing tests + tight conventions (`CLAUDE.md` rules, `CurrentStatus.md` anchor practice) — real-world delivery is likely faster than the stated bands. The bands stay conservative to accommodate unknown-unknowns in the ESCO and schema-migration work.

*End of plan.*

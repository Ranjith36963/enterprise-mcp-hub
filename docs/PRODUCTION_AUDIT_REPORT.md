# Job360 Production Readiness Audit

*Generated: 2026-04-06 | Baseline SHA: `4a7ba0a` | Branch: `worktree-reviewer` | Total findings: **41***

> **This report replaces `PRODUCTION_HARDENING_PLAN.md` and `CODEX_VERIFICATION_REPORT.md`.** Every claim from those documents has been re-verified and is reconciled in Section 5. The originals are backed up in `audit-out/job360/20260405-1800/final/replaced_originals/`.

---

## 0. Executive Summary

**Readiness verdict: YELLOW** — The codebase has a strong foundation (clean architecture, 387 tests, zero CVEs, zero eval/exec/pickle) but contains **9 Critical + 1 High + 22 Important** findings that must be resolved before production deployment. The most dangerous issues are scoring bugs that silently misrank jobs for users with profiles, a semaphore leak that can permanently degrade throughput, and a `javascript:` XSS vector in the dashboard.

### Severity Counts

| Severity | Count | Description |
|----------|-------|-------------|
| Critical | 9 | Scoring bugs, async safety, test integrity |
| High | 1 | XSS via javascript: URI |
| Important | 22 | Race conditions, observability, data integrity, test quality |
| Medium | 4 | Config, upload validation, hardcoded key |
| Low/Info | 5 | Dead code, unused deps, consistency |
| **Total** | **41** | |

### Top 10 Blockers

| # | ID | Severity | File:Line | Summary |
|---|------|----------|-----------|---------|
| 1 | F-001 | Critical | `skill_matcher.py:232,295` | `check_visa_flag()` substring match — "No sponsorship" flags as sponsoring |
| 2 | F-002 | Critical | `skill_matcher.py:279` | `JobScorer._negative_penalty()` substring — "Syntax Engineer" penalized for "tax" |
| 3 | F-003 | Critical | `rate_limiter.py:10-11` | Semaphore leak on cancellation — permanently degrades throughput |
| 4 | F-010 | High | `dashboard.py:285,317` | XSS via `javascript:` URI in apply_url href — no scheme allowlist |
| 5 | F-004 | Critical | `main.py:283` | `asyncio.gather` without `return_exceptions=True` |
| 6 | F-005 | Critical | `main.py:320` | Source health check silently swallowed at DEBUG level |
| 7 | F-015 | Important | `models.py:54` vs `deduplicator.py:18` | Normalization divergence leaks cross-run duplicates into DB |
| 8 | F-012 | Important | `main.py:358-361` | Race condition overcounts new jobs in stats/notifications |
| 9 | F-041 | Important | 25 source files | 25 of 47 sources skip `_is_uk_or_remote()` location filter |
| 10 | F-014 | Important | `dashboard.py:342-343` | Module-level DB queries crash on missing database |

---

## 1. If You Only Do 10 Things

1. **F-002: Fix `JobScorer._negative_penalty`** — Replace `if kw in title_lower:` with `if _text_contains(job_title, kw):` at `skill_matcher.py:279`. The `_text_contains` helper already exists at line 90. **Why now:** Every user with a profile gets silently wrong scores today.

2. **F-001: Fix `check_visa_flag` negation** — Add negation check before keyword match at `skill_matcher.py:232,295`. "No sponsorship available" must NOT flag as visa-sponsoring. **Why now:** Users filtering `--visa-only` see irrelevant results.

3. **F-003: Fix semaphore leak in `rate_limiter.py:10`** — Wrap `asyncio.sleep` in `try/except BaseException: self._semaphore.release(); raise`. **Why now:** A single Ctrl-C or timeout permanently halves throughput; two deadlock all requests.

4. **F-010: Add URL scheme allowlist in `dashboard.py:285`** — Only allow `http://` and `https://` in `apply_url` href. Add `rel="noopener noreferrer"`. **Why now:** A malicious `javascript:` URL from any job source executes in the user's browser.

5. **F-004: Add `return_exceptions=True` to `asyncio.gather`** at `main.py:283`. **Why now:** Any `BaseException` from a source kills all sibling fetches.

6. **F-015: Unify normalization** — Move deduplicator's extra stripping (seniority, job codes, parentheticals) into `Job.normalized_key()`. **Why now:** Cross-run dedup is broken; same role appears as "new" on each run.

7. **F-012: Fix overcount race** — Check `cursor.rowcount == 1` after `INSERT OR IGNORE` instead of using `is_job_seen`. **Why now:** Notifications report jobs that weren't actually inserted.

8. **F-041: Add `_is_uk_or_remote()` to 25 missing sources** — The filter already exists in `base.py`; 25 sources just don't call it. **Why now:** Foreign jobs pollute UK-only results.

9. **F-005: Upgrade health check log to WARNING** — Change `logger.debug` to `logger.warning` at `main.py:320`. **Why now:** Silent source failures are invisible at default log level.

10. **F-014: Move dashboard.py:342-343 into lazy-loaded function** — Wrap `all_jobs = load_jobs_7day()` inside the render path, not at module scope. **Why now:** Dashboard crashes on first run (no DB yet) and breaks import-time testing.

---

## 2. Audit Methodology

### Layers Executed

| Layer | Duration | Tools / Agents | Findings |
|-------|----------|---------------|----------|
| L0: Pre-flight | ~5 min | pip install (bandit, pip-audit, radon, vulture, freezegun, pre-commit) | Baseline captured |
| L1: Scanners | ~15 min | ruff, mypy, pytest-cov, gitleaks, bandit, pip-audit, radon cc/mi, vulture (15 parallel) | 3,030 ruff + 199 mypy + 9 bandit + 2 gitleaks + 4 vulture + 98 CC>=8 |
| L2: LLM Lenses | ~20 min | 7 parallel agents (security, async, errors, data, dead code, tests, docs) | 45+ findings, 5 dispute resolutions |
| L3: Cross-model | running | Codex (GPT-5) adversarial verification | Pending integration |
| L4: Claim re-verify | ~10 min | Manual synthesis from L2 mandatory items | 30+ claims reconciled |
| L5: Coverage | ~5 min | Coverage matrix (75 files) | 0 untouched, 0 scanner-only |

### Baseline Metrics

| Metric | Value |
|--------|-------|
| Source LOC | 8,426 across 83 `.py` files |
| Test LOC | 5,600 across 20 files |
| Test count | 387 collected (307 passed, 3 skipped, 77 excluded: live-network) |
| Coverage | 46% (4,455 stmts, excl test_main.py + test_sources.py) |
| Mypy --strict errors | 199 |
| Ruff violations | 3,030 (top: S101=739, ANN201=411, E501=352, D103=213) |
| Bandit findings | 9 (all B314 XML parsing) |
| Gitleaks | 2 (Algolia search key — known) |
| pip-audit CVEs | **0** |
| Radon CC outliers (>=10) | 98 functions (worst: CC=37 `generate_search_config`) |

### Scanner Versions

ruff 0.15.9, mypy 1.20.0, bandit 1.9.4, pip-audit 2.10.0, gitleaks 8.30.1, radon 6.0.1, vulture 2.16, pytest 9.0.2, pytest-cov 7.1.0

---

## 3. Findings by Severity

### 3.1 Critical (9 findings)

---

#### F-001: `check_visa_flag()` substring match flags "No sponsorship" as sponsoring

- **Category:** Scoring bug
- **File:** `src/filters/skill_matcher.py`
- **Lines:** 232-234 (module-level), 295-297 (JobScorer)
- **Evidence:**
  ```python
  text = f"{job.title} {job.description}".lower()
  return any(kw.lower() in text for kw in VISA_KEYWORDS)
  ```
  `VISA_KEYWORDS` includes `"sponsorship"` and `"sponsored"`. Text `"No sponsorship available"` matches because `"sponsorship" in "no sponsorship available"` is `True`.
- **Impact:** Jobs explicitly stating "no sponsorship" are incorrectly flagged as visa-sponsoring. Users filtering `--visa-only` see irrelevant results.
- **Root cause:** Naive `in` substring check with no negation detection.
- **Recommended fix:**
  ```python
  def check_visa_flag(job: Job) -> bool:
      text = f"{job.title} {job.description}".lower()
      if any(neg in text for neg in ("no sponsorship", "not sponsor", "cannot sponsor", "unable to sponsor")):
          return False
      return any(_text_contains(text, kw) for kw in VISA_KEYWORDS)
  ```
  Apply same fix to `JobScorer.check_visa_flag` at line 295.
- **Verification:** `assert check_visa_flag(Job(description="No sponsorship available", ...)) is False`
- **Test to add:** `test_visa_flag_negation_not_flagged`, `test_visa_flag_false_positive_sponsored_benefits`
- **Confidence:** High
- **Sources:** L2-2 (confirmed), L2-6 (missing test), original plan P1.1 (confirmed), Codex (confirmed)

---

#### F-002: `JobScorer._negative_penalty()` uses substring instead of word-boundary

- **Category:** Scoring bug
- **File:** `src/filters/skill_matcher.py`
- **Lines:** 277-281 (JobScorer) vs 176-181 (module-level)
- **Evidence:**
  ```python
  # Module-level (CORRECT — uses word boundary):
  def _negative_penalty(job_title: str) -> int:
      for kw in NEGATIVE_TITLE_KEYWORDS:
          if _text_contains(job_title, kw.strip()):  # word-boundary regex
              return 30

  # JobScorer (BUG — uses raw substring):
  def _negative_penalty(self, job_title: str) -> int:
      title_lower = job_title.lower()
      for kw in self._config.negative_title_keywords:
          if kw in title_lower:  # no word boundary!
              return 30
  ```
- **Impact:** With a user profile loaded, "Syntax Engineer" gets -30 for "tax", "Wholesale Analyst" gets -30 for "sales". Jobs silently drop below MIN_MATCH_SCORE (30) and are filtered out. Only affects the profile path — the primary production path for real users.
- **Root cause:** Copy-paste divergence between module-level and instance method.
- **Recommended fix:** Replace `if kw in title_lower:` with `if _text_contains(job_title, kw.strip()):` at line 279.
- **Verification:** `assert JobScorer(config)._negative_penalty("Syntax Engineer") == 0`
- **Confidence:** 100%
- **Sources:** L2-2 (confirmed), L2-6 (missing test), original plan P1.2 (confirmed), Codex (confirmed)

---

#### F-003: Semaphore leak in `rate_limiter.py` on cancellation

- **Category:** Async resource leak
- **File:** `src/utils/rate_limiter.py`
- **Lines:** 10-11
- **Evidence:**
  ```python
  async def acquire(self):
      await self._semaphore.acquire()   # slot taken
      await asyncio.sleep(self._delay)  # CancelledError HERE = slot lost forever
  ```
- **Impact:** If cancellation (Ctrl-C, timeout) arrives between `acquire()` and `sleep()`, the semaphore slot is grabbed but never released. With default `concurrent=2`, one cancellation permanently halves throughput; two deadlock all requests from that source forever. Triggered by normal operations (Ctrl-C, asyncio timeout).
- **Root cause:** No `try/finally` guarding the sleep after acquire.
- **Recommended fix:**
  ```python
  async def acquire(self):
      await self._semaphore.acquire()
      try:
          await asyncio.sleep(self._delay)
      except BaseException:
          self._semaphore.release()
          raise
  ```
- **Verification:** Cancel a task during `acquire()`, verify semaphore count is restored.
- **Confidence:** 92%
- **Sources:** L2-2 (NEW — not in either prior MD file)

---

#### F-004: `asyncio.gather` without `return_exceptions=True`

- **Category:** Async safety
- **File:** `src/main.py`
- **Line:** 283
- **Evidence:**
  ```python
  results = await asyncio.gather(*[_fetch_source(s) for s in sources])
  ```
- **Impact:** Any `BaseException` (e.g., `KeyboardInterrupt`, uncaught `CancelledError` from a source's internal task) cancels all sibling source fetches. `_fetch_source` catches `Exception` but not `BaseException`.
- **Recommended fix:** `asyncio.gather(..., return_exceptions=True)` + check `isinstance(result, BaseException)` in results loop.
- **Confidence:** 95%
- **Sources:** L2-2, original plan (confirmed)

---

#### F-005: Source health check silently swallowed at DEBUG level

- **Category:** Observability
- **File:** `src/main.py`
- **Lines:** 308-321
- **Evidence:**
  ```python
  except Exception as e:
      logger.debug(f"Source health check skipped: {e}")
  ```
- **Impact:** The only mechanism that detects silent source failures is itself swallowed at DEBUG level. At default INFO level, operators never see it. A corrupt `run_log.per_source` JSON row silently disables health monitoring.
- **Recommended fix:** Change `logger.debug` to `logger.warning`.
- **Confidence:** 88%
- **Sources:** L2-3 (NEW)

---

#### F-006: SMTP credential leak risk in tracebacks

- **Category:** Data exposure
- **File:** `src/notifications/email_notify.py`
- **Lines:** 58-62
- **Evidence:** `_send_sync` has no try/except. `SMTP_PASSWORD` is in scope as a module-level import. If `server.login()` raises, Python's traceback includes local variables in the frame.
- **Impact:** Password potentially readable in `data/logs/job360.log` after auth failure. Note: `smtplib` doesn't echo the password in the exception *message*, but the full traceback (if captured by a debugger or `logging.exception()`) could expose it.
- **Recommended fix:** Wrap in try/except, re-raise as `RuntimeError("SMTP auth failed — check credentials")` without the original exception details.
- **Confidence:** 85%
- **Sources:** L2-3, original plan P2.7

---

#### F-007: Multiple tests hit live network (not just test_main.py:299)

- **Category:** Test integrity
- **File:** `tests/test_main.py:108,299` + `tests/test_sources.py:99`
- **Evidence:** `test_run_search_completes_without_keys` creates real `aiohttp.ClientSession`, calls `run_search()` which invokes python-jobspy hitting `apis.indeed.com`. `test_reed_parses_response` also hangs. `test_source_instance_count_matches_build_sources` creates live session without `aioresponses`.
- **Impact:** Tests time out after 30-60s (or 32 minutes without timeout), violate CLAUDE.md "Always mock HTTP" rule, and cause CI failures on offline environments.
- **Recommended fix:** Wrap all `ClientSession` creation in `aioresponses()` context, or mock `python-jobspy` calls.
- **Confidence:** 95%
- **Sources:** L1 (timeout during coverage run), L2-6, memory (known 32-min issue)

---

#### F-008: No test for visa substring false-positive

- **Category:** Missing regression test
- **File:** `tests/test_scorer.py:68-80`
- **Evidence:** `VISA_KEYWORDS` contains `"sponsored"`. "Company-sponsored benefits" matches. No test covers this case.
- **Recommended fix:** Add `test_visa_flag_false_positive_sponsored_benefits`
- **Confidence:** 95%
- **Sources:** L2-6

---

#### F-009: No test for JobScorer negative penalty divergence

- **Category:** Missing regression test
- **File:** `tests/test_scorer.py:247-284`
- **Evidence:** Tests only cover module-level `_negative_penalty`. `JobScorer._negative_penalty` (the profile path) has no tests. The word-boundary divergence is undetectable by the current suite.
- **Recommended fix:** Add `test_jobscorer_negative_penalty_no_false_substring`
- **Confidence:** 97%
- **Sources:** L2-6

---

### 3.2 High (1 finding)

---

#### F-010: XSS via `javascript:` URI in dashboard apply_url href

- **Category:** XSS
- **File:** `src/dashboard.py`
- **Lines:** 285, 317
- **Evidence:**
  ```python
  url = html.escape(job.get("apply_url", "#"))
  # ... rendered as:
  f'<a href="{url}" target="_blank">{title}</a>'
  # inside st.markdown(..., unsafe_allow_html=True)
  ```
  `html.escape()` does not block `javascript:` URIs. A `apply_url = "javascript:alert(document.cookie)"` from a malicious job source executes when clicked. No `rel="noopener noreferrer"` present.
- **Impact:** Stored XSS — a compromised job source can execute arbitrary JavaScript in the user's browser context.
- **Recommended fix:**
  ```python
  def _safe_url(raw: str) -> str:
      parsed = urllib.parse.urlparse(raw.strip())
      if parsed.scheme not in ("http", "https", ""):
          return "#"
      return raw.strip()
  url = html.escape(_safe_url(job.get("apply_url", "#")))
  ```
  Add `rel="noopener noreferrer"` to all `target="_blank"` anchors.
- **Confidence:** High
- **Sources:** L2-1, Codex (originally flagged as missed by plan)

---

### 3.3 Important (22 findings)

#### F-011: Blocking `write_text` in async function
- **File:** `src/main.py:387`
- **Fix:** `await asyncio.to_thread(md_path.write_text, md_report, encoding="utf-8")`

#### F-012: Race condition overcounts new jobs
- **File:** `src/main.py:358-361`
- **Fix:** Use `cursor.rowcount == 1` after `INSERT OR IGNORE` instead of `is_job_seen` pre-check.

#### F-013: No TCPConnector limit configured
- **File:** `src/main.py:263`
- **Fix:** `aiohttp.TCPConnector(limit=200, limit_per_host=10)`

#### F-014: Dashboard module-level DB queries crash without database
- **File:** `src/dashboard.py:342-343`
- **Fix:** Move `all_jobs = load_jobs_7day()` and `df_runs = load_run_logs()` into the render path behind a function call, not at module scope.

#### F-015: Normalization divergence between models.py and deduplicator.py
- **File:** `src/models.py:54-58` vs `src/filters/deduplicator.py:18-24`
- **Fix:** Move seniority/job-code/parenthetical stripping from deduplicator into `Job.normalized_key()`. CLAUDE.md Rule 1 applies.

#### F-016: Per-row commits in insert loop
- **File:** `src/storage/database.py:105`
- **Fix:** Batch all inserts in a single `BEGIN...COMMIT` transaction.

#### F-017: Non-atomic CSV export
- **File:** `src/storage/csv_export.py:21-37`
- **Fix:** Write to temp file + `os.replace()`.

#### F-018: run_log unbounded growth
- **File:** `src/storage/database.py`
- **Fix:** Add `purge_old_run_logs(days=90)` + `LIMIT` clause on `get_run_logs()`.

#### F-019: ALTER TABLE f-string latent SQL injection
- **File:** `src/storage/database.py:67`
- **Fix:** Add regex validation on `col_name` and type whitelist on `col_def` before executing.

#### F-020: Algolia API key hardcoded
- **File:** `src/sources/eightykhours.py:12-13`
- **Fix:** Move to `settings.py` via `os.getenv()` with current value as default. Rotate the key.

#### F-021: No server-side upload validation
- **File:** `src/dashboard.py:352,375`
- **Fix:** Check `uploaded_file.size > MAX_UPLOAD_MB * 1024 * 1024` and validate file extension server-side.

#### F-022: GitHub username not validated before URL interpolation
- **File:** `src/profile/github_enricher.py:139,165`
- **Fix:** Add `_GITHUB_USERNAME_RE = re.compile(r'^[a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,37}[a-zA-Z0-9])?$')` validation.

#### F-023: Retry backoff IndexError risk
- **File:** `src/sources/base.py:118,130,139`
- **Fix:** `backoff = RETRY_BACKOFF[min(attempt, len(RETRY_BACKOFF) - 1)]`

#### F-024: Missing `exc_info=True` in source failure logging
- **File:** `src/main.py:284`
- **Fix:** `logger.error(f"Source {source.name} failed: {e}", exc_info=True)`

#### F-025: Corrupt profile silently falls back to defaults
- **File:** `src/profile/storage.py:31-42`
- **Fix:** In `main.py`, distinguish "no profile" from "corrupt profile" in the log message.

#### F-026: "No API key" logged at INFO instead of WARNING
- **Files:** `src/sources/reed.py:27`, `jsearch.py:39`, `jooble.py:27`, + 4 other keyed sources
- **Fix:** Change all `logger.info("...no API key, skipping")` to `logger.warning(...)`.

#### F-027: No structured logging or run correlation ID
- **File:** `src/utils/logger.py:18-21`
- **Fix:** Add JSON formatter option + UUID per `run_search()` call.

#### F-028: 112 f-strings in logging calls (G004)
- **Files:** 56 files across `src/`
- **Fix:** Replace with `%s`-style lazy formatting: `logger.warning("msg %s", var)`.

#### F-029: No test for London,Ontario false location match
- **Fix:** Add `test_foreign_penalty_london_ontario` and `test_location_score_london_ontario`.

#### F-030: No round-trip normalization test
- **Fix:** Add test that inserts a job and verifies DB columns match `normalized_key()`.

#### F-031: Mixed async test patterns
- **Files:** test_database.py, test_notifications.py, test_main.py, test_sources.py
- **Fix:** Standardize on `@pytest.mark.asyncio` with `asyncio_mode = "auto"` in pyproject.toml.

#### F-032: Time-dependent tests without freezegun
- **Files:** test_scorer.py, conftest.py
- **Fix:** Use `@freeze_time("2026-04-05")` or `unittest.mock.patch("datetime.now")`.

#### F-033: 5 tautology test assertions
- **File:** `tests/test_sources.py:1563-1795`
- **Fix:** Replace `assert isinstance(jobs, list)` + `if jobs else True` with concrete assertions matching mock data.

#### F-034: conftest.py fixture gaps
- **Fix:** Add `sample_non_uk_job`, `sample_empty_description_job`. Standardize `_make_job()` defaults.

#### F-035: Dashboard at 0% test coverage
- **Fix:** Extract data-loading logic from `dashboard.py` into `dashboard_data.py`, test those functions.

---

### 3.4 Medium (4 findings)

#### F-036: London,Ontario treated as UK (scoring bug)
- **File:** `src/filters/skill_matcher.py:184-193`
- **Fix:** Check FOREIGN_INDICATORS before UK_TERMS. Already confirmed by plan P1.3.

#### F-037: weworkremotely.py missing `_sanitize_xml()`
- **File:** `src/sources/weworkremotely.py:30`
- **Fix:** Add `from src.sources.base import _sanitize_xml` and apply to XML input.

#### F-038: Bandit B314 XML consistency (9 files)
- **Note:** Python's `xml.etree.ElementTree` does NOT resolve external entities. B314 is a false positive for XXE. But `defusedxml` is best practice. The 9 files are consistent except weworkremotely.py (F-037).

#### F-041: 25 of 47 sources skip `_is_uk_or_remote()` location filter
- **Files:** adzuna, arbeitnow, bcs_jobs, careerjet, climatebase, devitjobs, findajob, google_jobs, himalayas, indeed, jobicy, jobs_ac_uk, jobtensor, jooble, landingjobs, linkedin, nhs_jobs, nomis, pinpoint, reed, remoteok, remotive, smartrecruiters, uni_jobs, workable
- **Fix:** Call `self._filter_uk_or_remote(jobs)` at the end of `fetch_jobs()` in each file. The helper exists in `base.py`.

---

### 3.5 Low / Info (3 findings)

#### F-039: Unused import `field` in models.py:3
#### F-040: Unused import `Text` in cli_view.py:14
#### F-042: fpdf2 unused in requirements-dev.txt:5

---

## 4. Findings by Category

### 4.1 Security (F-001, F-006, F-010, F-019, F-020, F-021, F-022, F-037, F-038)
### 4.2 Async/Concurrency (F-003, F-004, F-011, F-013)
### 4.3 Error Handling & Observability (F-005, F-006, F-023, F-024, F-025, F-026, F-027, F-028)
### 4.4 Data Integrity (F-012, F-015, F-016, F-017, F-018, F-019, F-036, F-041)
### 4.5 Scoring Bugs (F-001, F-002, F-036)
### 4.6 Dead Code & Deps (F-039, F-040, F-042)
### 4.7 Test Quality (F-007, F-008, F-009, F-029, F-030, F-031, F-032, F-033, F-034, F-035)
### 4.8 Documentation Parity (see Section 5 + F-041 source filter count)

---

## 5. Original Claim Reconciliation

Every claim from the replaced `PRODUCTION_HARDENING_PLAN.md` and `CODEX_VERIFICATION_REPORT.md`, with final verdict.

| ID | Claim | Plan Said | Codex Said | Fresh Verdict | Superseded By |
|----|-------|-----------|------------|---------------|---------------|
| P1.1 | Visa substring match | CRITICAL | CONFIRMED | **CONFIRMED** | F-001 |
| P1.2 | Negative penalty substring | CRITICAL | CONFIRMED | **CONFIRMED** | F-002 |
| P1.3 | London,Ontario as UK | HIGH | CONFIRMED | **CONFIRMED** | F-036 |
| P1.4 | Normalization divergence | HIGH | CONFIRMED | **CONFIRMED** | F-015 |
| P1.5 | "21 sources skip filter" | HIGH (21) | REFUTED (25) | **25/47 (Codex was right)** | F-041 |
| P2.1 | Algolia key hardcoded | MEDIUM | CONFIRMED | **CONFIRMED** | F-020 |
| P2.2 | ALTER TABLE f-string | HIGH | PARTIALLY TRUE | **LATENT (migrations=[])** | F-019 |
| P2.3 | LinkedIn zip-slip | MEDIUM | **REFUTED** | **NOT A VULNERABILITY** (no disk extraction) | Dropped |
| P2.4 | No upload validation | MEDIUM | CONFIRMED | **CONFIRMED** | F-021 |
| P2.5 | GitHub username no validation | MEDIUM | PARTIALLY TRUE | **CONFIRMED (input validation + log injection)** | F-022 |
| P2.6 | 4x unsafe_allow_html XSS | MEDIUM | PARTIALLY TRUE | **ONLY apply_url href is exploitable** | F-010 |
| P2.7 | SMTP credential leak | MEDIUM | CONFIRMED | **NUANCED** (smtplib doesn't echo pw in msg) | F-006 |
| P2.8 | .gitleaks.toml absent | LOW | CONFIRMED | **CONFIRMED** | Infra task |
| PA | Race condition | Under-report | **Overcount** | **OVERCOUNT (Codex was right)** | F-012 |
| PB | Blocking write_text | HIGH | CONFIRMED | **CONFIRMED** | F-011 |
| PC | No lockfile/pyproject.toml | MEDIUM | CONFIRMED | **CONFIRMED** | Infra task |
| PD | Sources missing filter + count | HIGH (21) | PARTIALLY TRUE (25) | **25/47 (Codex was right)** | F-041 |
| PE | Upload + XSS conflated | MEDIUM | PARTIALLY TRUE | **SEPARATED into F-021 + F-010** | F-010, F-021 |
| PF | No CI/pre-commit | MEDIUM | CONFIRMED | **CONFIRMED** | Infra task |
| P3.1c | Climatebase swallows silently | Claimed | **REFUTED** | **FALSE — it DOES log warnings** | Dropped |
| P7.1a | dashboard.py:27 dead import | Claimed | **REFUTED** | **FALSE — import IS used at line 385** | Dropped |
| P7.1b | fpdf2 unused | LOW | CONFIRMED | **CONFIRMED** | F-042 |
| P3.10a | 376 tests / 17 files | Claimed | 387 / 18 | **387 / 18 (Codex was right)** | Docs fix |
| P3.10b | TARGET_SALARY_* missing from .env.example | MEDIUM | CONFIRMED | **CONFIRMED** | Docs fix |

**Codex missed (Codex's original report):**
| Finding | Codex's verdict | Fresh verdict |
|---------|----------------|---------------|
| C.1: Dynamic JobScorer.check_visa_flag | "Plan missed it" | **CONFIRMED** — both paths use substring | F-001 |
| C.2: Dashboard href scheme allowlist | "Plan missed it" | **CONFIRMED** — javascript: URI exploitable | F-010 |

**This audit found but NEITHER prior document caught:**
| Finding | Why it was missed |
|---------|-------------------|
| F-003: Semaphore leak | Requires async reasoning about cancellation timing |
| F-005: Health check at DEBUG | Requires reading the exception handler in context |
| F-014: Module-level side effects in dashboard | Only manifests when DB doesn't exist |
| F-023: Retry backoff IndexError risk | Only triggers if MAX_RETRIES is increased |
| F-033: 5 tautology test assertions | Requires reading test assertion patterns closely |
| F-028: 112 f-string logging calls | Ruff G004 catches mechanically; neither prior review ran ruff |

---

## 6. Scanner Baseline (for regression tracking)

| Scanner | Count | Breakdown |
|---------|-------|-----------|
| ruff | 3,030 | S101:739, ANN201:411, E501:352, D103:213, D102:163, PLR2004:132, G004:114, ANN202:111, ANN001:91, F401:54, BLE001:24 |
| mypy --strict | 199 | Mostly missing return types + generic type args |
| bandit -ll | 9 | ALL B314 (XML parsing) in 9 source files |
| gitleaks | 2 | Algolia key in eightykhours.py + PRODUCTION_HARDENING_PLAN.md |
| pip-audit | **0** | No CVEs |
| vulture | 4 | 1 real (cli_view.py:14), 3 false-positive (__aexit__ params) |
| radon CC>=10 | 98 | generate_search_config:37, NoFluffJobsSource:33, run_search:32 |
| radon MI<50 | 20 | dashboard.py:31.6, skill_matcher.py:36.5, main.py:40.5 |
| pytest | 387 collected | 307 passed, 3 skipped, 77 excluded (live-network) |
| coverage | 46% | 4,455 stmts total, 2,412 missing |

---

## 7. File Coverage Matrix

75 source files reviewed. **0 untouched. 0 scanner-only.**

| Status | Count |
|--------|-------|
| covered_with_findings | 16 |
| covered_clean | 59 |
| scanner_only | 0 |
| untouched | 0 |

Top files by finding density: `dashboard.py` (6), `main.py` (8), `skill_matcher.py` (4), `database.py` (4).

Full matrix in `audit-out/job360/20260405-1800/layer5/coverage_matrix.csv`.

---

## 8. Dependencies Inventory

| Package | Version Pin | CVEs | Status |
|---------|------------|------|--------|
| aiohttp | >=3.9.0 | 0 | OK |
| aiosqlite | >=0.19.0 | 0 | OK |
| python-dotenv | >=1.0.0 | 0 | OK |
| jinja2 | >=3.1.0 | 0 | OK |
| click | >=8.1.0 | 0 | OK |
| streamlit | >=1.30.0 | 0 | OK |
| pandas | >=2.0.0 | 0 | OK |
| plotly | >=5.18.0 | 0 | OK |
| pdfplumber | >=0.10.0 | 0 | OK |
| python-docx | >=1.1.0 | 0 | OK |
| rich | >=13.0.0 | 0 | OK |
| humanize | >=4.9.0 | 0 | OK |

**Dev deps:**
| Package | Status |
|---------|--------|
| pytest | OK |
| pytest-asyncio | OK |
| aioresponses | OK |
| **fpdf2** | **UNUSED — remove** (F-042) |

**Unused in production:** None detected (all 12 packages imported somewhere in `src/`).

**Missing infrastructure:**
- No `pyproject.toml` (PEP 517)
- No lockfile (`requirements.lock`)
- No `.pre-commit-config.yaml`
- Loose `>=X.Y.Z` pinning allows breaking upgrades

---

## 9. Fix Agent Playbook

Recommended execution order, grouped into logical PRs:

### PR 1: Scoring Bugs (Critical — user-facing today)
- F-001: Fix `check_visa_flag` negation
- F-002: Fix `JobScorer._negative_penalty` word boundary
- F-036: Fix London,Ontario location scoring
- F-008: Add visa false-positive regression test
- F-009: Add negative penalty regression test
- F-029: Add London,Ontario regression test
- **Blast radius:** `src/filters/skill_matcher.py` + 3 new tests
- **Run after:** `python -m pytest tests/test_scorer.py tests/test_profile.py -v`

### PR 2: Async Safety (Critical — data loss risk)
- F-003: Fix semaphore leak in rate_limiter
- F-004: Add `return_exceptions=True` to gather
- F-011: Wrap `write_text` in `asyncio.to_thread`
- F-013: Configure `TCPConnector`
- **Blast radius:** `src/main.py`, `src/utils/rate_limiter.py`
- **Run after:** `python -m pytest tests/test_main.py tests/test_rate_limiter.py -v`

### PR 3: Data Integrity (Important — correctness)
- F-012: Fix overcount race (use `cursor.rowcount`)
- F-015: Unify normalization (move to `normalized_key`)
- F-016: Batch insert transaction
- F-017: Atomic CSV export
- F-018: Add run_log retention
- F-030: Add normalization round-trip test
- **Blast radius:** `src/main.py`, `src/storage/database.py`, `src/storage/csv_export.py`, `src/models.py`, `src/filters/deduplicator.py`
- **Run after:** `python -m pytest tests/test_database.py tests/test_deduplicator.py tests/test_models.py tests/test_csv_export.py -v`

### PR 4: Security Hardening (High + Medium)
- F-010: URL scheme allowlist + `rel="noopener noreferrer"`
- F-019: Migration column validation
- F-020: Algolia key to env var
- F-021: Upload size/type validation
- F-022: GitHub username validation
- **Blast radius:** `src/dashboard.py`, `src/storage/database.py`, `src/sources/eightykhours.py`, `src/config/settings.py`, `src/profile/github_enricher.py`

### PR 5: Observability (Important)
- F-005: Health check log to WARNING
- F-006: SMTP exception wrapping
- F-024: Add `exc_info=True` to source failure
- F-025: Distinguish corrupt profile from missing
- F-026: API key skip to WARNING
- F-027: Structured logging + run ID (optional)
- **Blast radius:** `src/main.py`, `src/notifications/email_notify.py`, `src/profile/storage.py`, `src/sources/reed.py` + 6 other keyed sources, `src/utils/logger.py`

### PR 6: Source Layer (Important)
- F-041: Add location filter to 25 sources
- F-037: Add `_sanitize_xml` to weworkremotely.py
- **Blast radius:** 25 source files under `src/sources/`
- **Run after:** `python -m pytest tests/test_sources.py -v` (must fix F-007 first)

### PR 7: Test Suite Hardening
- F-007: Mock all live-network tests
- F-031: Standardize async test pattern
- F-032: Add freezegun to time-dependent tests
- F-033: Fix 5 tautology assertions
- F-034: Add conftest fixtures
- F-035: Extract + test dashboard data functions
- **Blast radius:** All `tests/` files

### PR 8: Cleanup
- F-028: Convert 112 f-string logging calls to %s-style
- F-039: Remove unused `field` import
- F-040: Remove unused `Text` import
- F-042: Remove fpdf2 from requirements-dev.txt
- F-014: Move dashboard module-level queries to lazy load
- **Blast radius:** 56 files (f-string fix) + dashboard.py + models.py + cli_view.py + requirements-dev.txt

### PR 9: Infrastructure
- Add `pyproject.toml` with `[tool.pytest]`, `[tool.ruff]`, `[tool.mypy]` sections
- Add `requirements.lock` via `pip-compile`
- Add `.pre-commit-config.yaml` (gitleaks, ruff, ruff-format)
- Port `.gitleaks.toml` from `origin/main`
- Add `.github/workflows/ci.yml` (lint + test + security)
- Add `TARGET_SALARY_MIN/MAX` to `.env.example`
- Sync CLAUDE.md test counts (387 / 18)

---

## 10. Appendix A: Raw Artifact Locations

```
C:\Users\Ranjith\audit-out\job360\20260405-1800\
├── layer0\baseline.sha, baseline.status
├── layer1\ruff.json, mypy.txt, bandit.json, gitleaks.json, pip_audit.json,
│         radon_cc.json, radon_mi.json, vulture.txt, pytest_full.txt,
│         coverage.json, SUMMARY.md
├── layer2\01_security.md through 07_docs_parity.md + CONSOLIDATED_FINDINGS.md
├── layer3\codex_verdict.md (pending), codex_session_id.txt
├── layer4\canonical_claims.md
├── layer5\coverage_matrix.csv
└── final\replaced_originals\{PRODUCTION_HARDENING_PLAN.md, CODEX_VERIFICATION_REPORT.md}
```

---

## 11. Appendix B: Audit Session Provenance

- **Claude model:** claude-opus-4-6[1m] (1M context)
- **Codex session ID (prior):** `019d5e90-3788-7740-8136-3fb8d2e415ba`
- **Codex session ID (Layer 3):** pending
- **Git SHA audited:** `4a7ba0a68f5a746e51f0ac625e1530a821c993a3`
- **Baseline branch:** `worktree-reviewer`
- **Audit start:** 2026-04-05 ~20:10 UTC
- **Layer 1 complete:** 2026-04-05 ~20:25 UTC
- **Layer 2 complete:** 2026-04-06 ~18:20 UTC
- **Report generated:** 2026-04-06

### Ground Truth Counts (authoritative, AST/grep verified)

| Metric | Value | Method |
|--------|-------|--------|
| KNOWN_SKILLS | 392 | `ast.parse()` set element count |
| KNOWN_TITLE_PATTERNS | 107 | `ast.parse()` set element count |
| Sources WITH `_is_uk_or_remote` | 22 / 47 files | `grep -rl` |
| Sources WITHOUT | 25 / 47 files | `grep -rl` inverse |
| SOURCE_REGISTRY entries | 48 | manual count |
| RATE_LIMITS entries | 48 | manual count |
| ATS companies | 104 | manual sum |
| Test functions | 387 | `pytest --collect-only` |
| Test files | 18 | `ls tests/test_*.py` |

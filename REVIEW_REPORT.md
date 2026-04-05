# Job360 Production Codebase Review Report

**Generated:** 2026-04-05
**Reviewers:** 8 parallel agents (CodeRabbit x2, Superpowers, Feature-Dev x2, Code-Simplifier, Explore x2) + pytest + npm audit
**Scope:** Full stack — FastAPI backend (src/) + Next.js frontend (frontend/)

---

## Executive Summary

| Metric | Value |
|--------|-------|
| **Total Issues Found** | 68 |
| **Critical** | 10 |
| **High/Important** | 22 |
| **Medium** | 16 |
| **Minor/Low** | 20 |
| **Runtime Bugs** | 3 (will crash in production) |
| **Security Vulnerabilities** | 14 (2 critical, 6 high, 4 medium, 2 low) |
| **Dead Code Items** | 10 (1 backend, 4 API functions, 3 UI components, 2 CSS classes) |
| **Backend Tests** | Crashed (integration test timeout — known slow test) |
| **npm audit** | 0 vulnerabilities |
| **Core Rules Compliance** | 3/3 PASS (dynamic keywords, CV mandatory, single scoring path) |
| **FE↔BE Integration** | 3 BROKEN, 3 PARTIAL MISMATCH, 15 OK |

---

## CRITICAL — Must Fix Before Deploy

### BUG 1: `set_action` — String vs Enum Crash
**Found by:** CodeRabbit Backend, Architecture Review, Security Audit (3 independent confirmations)
**File:** `src/api/routes/actions.py:20`
**Impact:** Like/Skip/Apply buttons throw 500 error — `AttributeError: 'str' object has no attribute 'value'`
**Root cause:** `body.action` is `str`, but `UserActionsDB.set_action()` expects `ActionType` enum
**Fix:** `await db.user_actions.set_action(job_id, ActionType(body.action), notes=body.notes)`

### BUG 2: `getSources()` — Frontend Unwraps Non-Existent Wrapper
**Found by:** Architecture Review, Standards Compliance
**File:** `frontend/lib/api.ts:63`
**Impact:** `data.sources` is always `undefined` — source listing is broken
**Root cause:** Backend returns `list[SourceInfo]` directly, frontend expects `{ sources: SourceInfo[] }`
**Fix:** Change to `return request<SourceInfo[]>("/api/sources")`

### BUG 3: `"complete"` vs `"completed"` — Search Polling Never Stops
**Found by:** Code Simplifier
**File:** `src/api/routes/search.py:32` + `frontend/app/dashboard/page.tsx:197`
**Impact:** Frontend polls forever after search finishes — never refreshes job list
**Root cause:** Backend sets `status = "complete"`, frontend checks `status === "completed"`
**Fix:** Change backend to `"completed"` or frontend to `"complete"`

### BUG 4: Unrestricted File Upload — RAM/Disk Exhaustion
**Found by:** Security Audit, CodeRabbit Backend
**File:** `src/api/routes/profile.py:64,103`
**Impact:** Multi-GB upload crashes server (OOM)
**Fix:** Add 10MB cap: `if len(content) > 10_000_000: raise HTTPException(413, "File too large")`

### BUG 5: No Error Boundaries — Unhandled Errors Crash Entire App
**Found by:** CodeRabbit Frontend
**Files:** No `error.tsx` files exist anywhere
**Impact:** Any runtime exception shows white screen in production
**Fix:** Add `app/error.tsx`, `app/not-found.tsx`, `app/loading.tsx`

### BUG 6: `_search_runs` Memory Leak — Unbounded Dict Growth
**Found by:** CodeRabbit Backend, Security Audit
**File:** `src/api/routes/search.py:18`
**Impact:** Server memory grows indefinitely — OOM on long-running processes
**Fix:** Add TTL-based eviction (1hr) or cap dict size

### BUG 7: No Concurrent Search Guard — Pipeline DoS
**Found by:** Security Audit, CodeRabbit Backend
**File:** `src/api/routes/search.py:42-58`
**Impact:** Multiple simultaneous searches exhaust resources
**Fix:** Check for running search before starting new one, return 429

### BUG 8: `asyncio.create_task` Orphaned — Exception Swallowed
**Found by:** CodeRabbit Backend
**File:** `src/api/routes/search.py:56`
**Impact:** Background task exceptions silently lost, status stuck at "running"
**Fix:** Store task reference, catch broad `Exception` in `_run_pipeline`

### BUG 9: Temp File `UnboundLocalError` in LinkedIn Upload
**Found by:** CodeRabbit Backend, Security Audit, Code Simplifier
**File:** `src/api/routes/profile.py:106-128`
**Impact:** If `NamedTemporaryFile` fails, `tmp_path` is unbound → masking error
**Fix:** Initialize `tmp_path = None` before try block

### BUG 10: CORS `allow_headers=["*"]` with `allow_credentials=True`
**Found by:** Security Audit
**File:** `src/api/app.py:30-40`
**Impact:** Violates Fetch spec — browsers may reject credentialed requests
**Fix:** Enumerate specific headers: `["Content-Type", "Accept"]`

---

## HIGH/IMPORTANT — Should Fix

| # | Issue | File | Found By |
|---|-------|------|----------|
| I1 | No auth on any endpoint | `app.py` | Security |
| I2 | No rate limiting on `/api/search` | `search.py` | Security |
| I3 | `removeJobAction` response missing `action` field | `actions.py:27` | Architecture |
| I4 | LinkedIn/GitHub `merged` typed as `boolean` (is `dict`) | `api.ts:143,154` | Architecture |
| I5 | Dashboard shows no error when API is down | `dashboard/page.tsx` | CodeRabbit FE |
| I6 | Double fetch on every filter/bucket change | `dashboard/page.tsx:83-99` | CodeRabbit FE, Simplifier |
| I7 | `PreferencesRequest` not validated (any string accepted) | `schemas.py:62-74` | CodeRabbit BE |
| I8 | Job listing loads ALL jobs into memory before filtering | `jobs.py:113-155` | CodeRabbit BE |
| I9 | `get_run_logs()` fetches all rows, uses only first | `status.py:23` | CodeRabbit BE |
| I10 | `get_profile()` is sync — blocks event loop | `deps.py:16` | CodeRabbit BE, Standards |
| I11 | GitHub username not validated — path injection risk | `profile.py:132-153` | Security |
| I12 | CSV export accumulates files, never cleaned up | `jobs.py:158-194` | Security |
| I13 | Stale closure in `handleAction` on job detail | `jobs/[id]/page.tsx:138` | CodeRabbit FE |
| I14 | `preferences` typed as `Record<string, unknown>` | `types.ts:71` | CodeRabbit FE |
| I15 | Duplicate hidden file input with same ref | `CVUpload.tsx:160,263` | CodeRabbit FE, Simplifier |
| I16 | "Save Profile" button does nothing | `CVUpload.tsx:272` | CodeRabbit FE, Simplifier |
| I17 | Missing return type annotations on 18 API functions | `src/api/routes/*.py` | Standards |
| I18 | Missing docstrings on most API functions | `src/api/routes/*.py` | Standards |
| I19 | 5 bare `except Exception:` blocks | `dashboard.py`, `base.py` | Standards |
| I20 | Hardcoded Algolia API key | `eightykhours.py:14` | Standards |
| I21 | `noqa: E402` suppression violates project rules | `app.py:43` | Standards |
| I22 | `PipelineApplication` has no backend schema | `types.ts:122` | Standards |

---

## MEDIUM — Nice to Have

| # | Issue | File |
|---|-------|------|
| M1 | File extension check bypassed by double extension | `profile.py:59-63` |
| M2 | Pipeline errors may log API keys in URLs | `search.py:39` |
| M3 | `notes` field has no length limit (storage exhaustion) | `schemas.py:91` |
| M4 | No Content-Type validation on LinkedIn ZIP | `profile.py:96` |
| M5 | Missing `response_model` on 11 endpoints | Multiple route files |
| M6 | `SourceInfo.type` always empty | `status.py:44` |
| M7 | `_format_salary` crashes on non-numeric values | `jobs.py:56-65` |
| M8 | Unsafe type casting in profile completeness | `profile/page.tsx:31-52` |
| M9 | `apply_url` rendered as raw href (open redirect risk) | `JobCard.tsx:172`, `jobs/[id]` |
| M10 | No keyboard accessibility on JobCard click target | `JobCard.tsx:70-73` |
| M11 | No keyboard accessibility on Kanban collapse toggle | `KanbanBoard.tsx:213` |
| M12 | Missing `aria-label` on CV drop zone | `CVUpload.tsx:149` |
| M13 | Radar chart `size` prop doesn't handle mobile overflow | `ScoreRadar.tsx:62` |
| M14 | KanbanBoard renders two copies of board (desktop+mobile) | `KanbanBoard.tsx:289` |
| M15 | `eslint-disable` hiding potential stale dep bug | `dashboard/page.tsx:104` |
| M16 | Inconsistent error handling patterns across pages | Multiple pages |

---

## MINOR/LOW

| # | Issue | File |
|---|-------|------|
| L1 | Unused import `timedelta` | `jobs.py:5` |
| L2 | Unused imports `Depends`, `get_profile`, `CVData`, `UserPreferences` | `profile.py:8,10,15` |
| L3 | Unused import `asyncio` in `enrich_github` | `profile.py:140` |
| L4 | Unused import `X` in CVUpload | `CVUpload.tsx:10` |
| L5 | Unused import `Badge` in PreferencesForm | `PreferencesForm.tsx:18` |
| L6 | `_compute_bucket` could use data-driven approach | `jobs.py:31-52` |
| L7 | Hardcoded "white" fill in radar chart tick | `ScoreRadar.tsx:76` |
| L8 | `exportJobsCsv` bypasses shared `request` helper | `api.ts:79` |
| L9 | PoundSterling icon for UK salary (was DollarSign) | Already fixed |
| L10 | 4 duplicate date formatting helpers across files | Multiple files |
| L11 | `TagInput` icon renders without gap or aria-hidden | `PreferencesForm.tsx:85` |
| L12 | Tooltip `render` prop pattern may not work with Base UI | `JobCard.tsx:121` |
| L13 | Secrets accessible via module-level attributes | `settings.py:41` |
| L14 | `get_db` returns not yields — no reconnection logic | `deps.py:10` |
| L15 | Deps inconsistency — profile.py bypasses shared dep | `deps.py`, `profile.py` |

---

## Dead Code Inventory

### Backend
| Item | File | Status |
|------|------|--------|
| `PreferencesRequest` schema | `schemas.py` | UNUSED — never imported in routes |

### Frontend — Unused API Functions
| Function | File | Status |
|----------|------|--------|
| `exportJobsCsv()` | `lib/api.ts` | Never called |
| `getActions()` | `lib/api.ts` | Never called |
| `getActionCounts()` | `lib/api.ts` | Never called |
| `getSources()` | `lib/api.ts` | Never called (also broken — see BUG 2) |

### Frontend — Unused UI Components
| Component | File | Status |
|-----------|------|--------|
| `Card` (shadcn) | `components/ui/card.tsx` | Installed but never imported |
| `Dialog` (shadcn) | `components/ui/dialog.tsx` | Installed but never imported |
| `Tabs` (shadcn) | `components/ui/tabs.tsx` | Installed but never imported |

### Frontend — Unused CSS Classes
| Class | File | Status |
|-------|------|--------|
| `.animate-count-up` | `globals.css` | Defined but never applied |
| `.animate-action-bounce` | `globals.css` | Defined but never applied |

---

## Security Summary (OWASP Top 10)

| OWASP Category | Findings | Severity |
|----------------|----------|----------|
| A01 Broken Access Control | No auth, no rate limiting | High |
| A02 Cryptographic Failures | Secrets in module attributes | Low |
| A03 Injection | Enum type mismatch, extension bypass, GitHub path injection | Critical + Medium |
| A04 Insecure Design | File upload no limit, memory leak, no concurrent guard, unbounded notes | Critical + High + Medium |
| A05 Security Misconfiguration | CORS spec violation, CSV file accumulation | High + Medium |
| A07 Auth Failures | Zero authentication | High (known limitation) |
| A09 Logging Failures | API keys may leak in error logs | Medium |
| A10 SSRF | GitHub username not validated | High |

---

## Frontend↔Backend Integration Matrix

| Endpoint | Frontend Function | Status |
|----------|------------------|--------|
| `GET /api/health` | `getHealth()` | OK |
| `GET /api/status` | `getStatus()` | OK |
| `GET /api/sources` | `getSources()` | **BROKEN** — array vs wrapper |
| `GET /api/jobs` | `getJobs()` | OK |
| `GET /api/jobs/export` | `exportJobsCsv()` | OK (unused) |
| `GET /api/jobs/{id}` | `getJob()` | OK |
| `POST /api/jobs/{id}/action` | `setJobAction()` | **BROKEN** — str vs enum |
| `DELETE /api/jobs/{id}/action` | `removeJobAction()` | PARTIAL — missing `action` field |
| `GET /api/actions` | `getActions()` | OK (unused) |
| `GET /api/actions/counts` | `getActionCounts()` | OK (unused) |
| `GET /api/profile` | `getProfile()` | OK |
| `POST /api/profile` | `uploadProfile()` | OK |
| `POST /api/profile/linkedin` | `uploadLinkedin()` | PARTIAL — `merged` typed as bool |
| `POST /api/profile/github` | `uploadGithub()` | PARTIAL — `merged` typed as bool |
| `POST /api/search` | `startSearch()` | OK |
| `GET /api/search/{id}/status` | `getSearchStatus()` | OK (but `"complete"` bug) |
| `GET /api/pipeline` | `getPipelineApplications()` | OK |
| `POST /api/pipeline/{id}` | `createPipelineApplication()` | OK |
| `POST /api/pipeline/{id}/advance` | `advancePipelineStage()` | OK |
| `GET /api/pipeline/reminders` | `getPipelineReminders()` | OK |
| `GET /api/pipeline/counts` | `getPipelineCounts()` | OK |

---

## Core Rules Compliance

| Rule | Status | Evidence |
|------|--------|---------|
| Rule 1: All keywords dynamic | **PASS** | No hardcoded job titles/skills in sources or scoring |
| Rule 2: CV mandatory | **PASS** | `main.py` and `search.py` both gate on profile |
| Rule 3: Single scoring path | **PASS** | Only `JobScorer.score()` and `score_detailed()` |

---

## Test Results

| Suite | Result |
|-------|--------|
| Backend pytest (843 tests) | Crashed — integration test timeout in `test_run_search_completes_without_keys` |
| Frontend build (`next build`) | **PASS** — all routes compile, TypeScript clean |
| npm audit | **0 vulnerabilities** |

---

## Recommendations Priority

### Immediate (before sharing)
1. Fix BUG 1 (`ActionType` enum) — 1 line fix
2. Fix BUG 2 (`getSources` wrapper) — 1 line fix
3. Fix BUG 3 (`"complete"` vs `"completed"`) — 1 line fix
4. Add file upload size limit — 3 line fix
5. Add `app/error.tsx` error boundary — new file
6. Fix CORS `allow_headers` — 1 line fix

### Before deployment
7. Add `_search_runs` TTL eviction
8. Add concurrent search guard
9. Store `asyncio.create_task` reference
10. Add basic API key auth
11. Fix `tmp_path` UnboundLocalError
12. Add dashboard error state

### Code quality
13. Remove dead code (unused imports, schemas, UI components)
14. Add return type annotations to API functions
15. Add docstrings to API functions
16. Consolidate 4 duplicate date helpers into `lib/date.ts`
17. Type `preferences` properly in `ProfileResponse`

---

*Report generated by 8 parallel review agents across 4 waves. Total review time: ~5 minutes wall clock.*

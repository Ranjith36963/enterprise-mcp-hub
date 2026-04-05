# TESTING.md — Test Patterns Reference

843 tests across 43 test files + 15 E2E tests. All HTTP calls mocked with `aioresponses`. All tests use explicit `SearchConfig` — no defaults exist.

---

## Running Tests

```bash
# All tests
python -m pytest tests/ -v

# Single file
python -m pytest tests/test_scorer.py -v

# Single test
python -m pytest tests/test_scorer.py::test_name -v

# Module groups
python -m pytest tests/test_scorer.py tests/test_description_matcher.py -v   # scoring
python -m pytest tests/test_sources.py -v                                     # sources
python -m pytest tests/test_profile.py tests/test_skill_graph.py -v           # profile
python -m pytest tests/test_pipeline.py tests/test_user_actions.py -v         # pipeline
python -m pytest tests/test_cli.py tests/test_main.py -v                      # integration

# Quick smoke test (CLI + registry count)
python -m pytest tests/test_cli.py -v --tb=short
```

---

## Key Test Patterns

### `_TEST_CONFIG` SearchConfig (from `tests/test_sources.py`)

All source tests use this shared config. Copy it exactly when writing new source tests:

```python
from src.profile.models import SearchConfig

_TEST_CONFIG = SearchConfig(
    job_titles=["AI Engineer", "ML Engineer", "Data Scientist", "Software Engineer"],
    primary_skills=["Python", "PyTorch", "TensorFlow"],
    secondary_skills=["AWS", "Docker"],
    tertiary_skills=["Git"],
    relevance_keywords=["ai", "ml", "python", "engineer", "data", "software",
                        "developer", "remote", "devops", "cloud", "health",
                        "climate", "science", "tech", "job", "work"],
    negative_title_keywords=[],
    locations=["London", "UK", "Remote"],
    visa_keywords=["visa sponsorship", "sponsorship"],
    core_domain_words={"ai", "ml", "data", "software"},
    supporting_role_words={"engineer", "scientist", "developer"},
    search_queries=["AI Engineer UK", "ML Engineer London"],
)
```

### `_mock_profile()` + `_patch_profile()` (from `tests/test_main.py`)

Integration tests that run `run_search()` must patch the profile (CV is mandatory):

```python
from unittest.mock import patch
from src.profile.models import CVData, UserPreferences, UserProfile

def _mock_profile():
    """Return a mock profile so run_search proceeds (CV is mandatory)."""
    return UserProfile(
        cv_data=CVData(
            raw_text="Experienced AI Engineer with Python and PyTorch",
            skills=["Python", "PyTorch", "TensorFlow", "LangChain", "RAG",
                    "LLM", "NLP", "Deep Learning", "AWS", "Docker"],
            job_titles=["AI Engineer"],
        ),
        preferences=UserPreferences(
            target_job_titles=["AI Engineer", "ML Engineer"],
            preferred_locations=["London", "UK"],
        ),
    )

def _patch_profile():
    """Patch load_profile to return a valid profile."""
    return patch("src.main.load_profile", return_value=_mock_profile())
```

### `_run(coro)` Async Helper

Used in both `test_sources.py` and `test_main.py` for running async tests without `pytest-asyncio` markers:

```python
import asyncio

def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)
```

### `aioresponses` Mocking Pattern

All HTTP calls are mocked. Use `re.compile()` for URL patterns and `repeat=True` for sources that make multiple requests:

```python
import re
from aioresponses import aioresponses

def test_my_source():
    async def _test():
        with aioresponses() as m:
            # JSON API response
            m.get(re.compile(r"https://api\.example\.com/.*"),
                  payload={"jobs": [{"title": "Engineer", ...}]},
                  repeat=True)

            # XML/HTML response
            m.get(re.compile(r"https://example\.com/feed"),
                  body="<rss><channel>...</channel></rss>",
                  repeat=True)

            async with aiohttp.ClientSession() as session:
                source = MySource(session, search_config=_TEST_CONFIG)
                jobs = await source.fetch_jobs()
                assert len(jobs) >= 1
    _run(_test())
```

### `_mock_free_sources(m)` (from `tests/test_main.py`)

Mocks ALL 50 sources for integration tests. Groups:
- **Group A:** Keyed APIs (Reed, Adzuna, JSearch, Jooble, SerpApi, Findwork) — `payload={"results": []}` etc.
- **Group B:** Free APIs (Arbeitnow, RemoteOK, Jobicy, Himalayas, Remotive, etc.) — empty payloads
- **Group C:** ATS boards (Greenhouse, Lever, Workable, Ashby, etc.) — empty payloads
- **Group D:** HTML scrapers (LinkedIn, JobTensor, Climatebase, etc.) — `body="<html></html>"`
- **Group E:** RSS/XML feeds (jobs.ac.uk, NHS, WWR, etc.) — `body="<rss><channel></channel></rss>"`
- **Group F:** Other APIs (HN Firebase, Algolia, YC, NoFluffJobs, Nomis, Careerjet)

When adding a new source, add its mock URL pattern to the appropriate group in `_mock_free_sources()`.

### Shared Fixtures (from `tests/conftest.py`)

Available to all test files via pytest:

```python
@pytest.fixture
def sample_ai_job():        # AI Engineer at DeepMind, London, with visa sponsorship
def sample_unrelated_job():  # Marketing Manager at Acme Corp, New York
def sample_duplicate_jobs():  # Two ML Engineer jobs at Revolut from different sources
def sample_visa_job():        # Data Scientist at Faculty AI with visa sponsorship
```

### Registry Count Assertion (from `tests/test_cli.py`)

**Must update when adding or removing sources:**

```python
def test_source_registry_count():
    assert len(SOURCE_REGISTRY) == 50  # Update this number
```

---

## Automation Test Files (WP1)

| Test File | Tests | What It Covers |
|-----------|:-----:|----------------|
| `tests/test_circuit_breaker.py` | 10 | Persistent circuit breaker: safe_fetch tripping, reset, exponential backoff (1hr/6hr/24hr), load_source_health, DB persistence |
| `tests/test_robots_checker.py` | 5 | robots.txt compliance: allowed/blocked URLs, fail-open, domain caching, network errors |
| `tests/test_evidence.py` | 7 | Evidence tagging: *_reason fields in ScoreBreakdown — role, skill, seniority, experience, penalty |
| `tests/test_deal_breakers.py` | 5 | Deal-breakers: negative title cap at 15, excluded company zero-out, normalization, no false positives |
| `tests/test_safe_mode.py` | 5 | --safe mode: excludes scrapers, keeps APIs/ATS/RSS |
| `tests/test_rate_limiter.py` | 5 | Rate limiter: concurrent limit, delay, context manager |
| `tests/test_cv_parser.py` | 6 | CV parser entry points: parse_cv, parse_cv_from_bytes, section detection |
| `tests/test_dashboard_data.py` | 6 | Dashboard data layer: get_recent_jobs, user actions, get_job_by_id |

### Circuit Breaker Test Pattern

```python
from src.sources.base import _circuit_breaker, _source_health, load_source_health

@pytest.fixture(autouse=True)
def _clear_circuit_breaker():
    _circuit_breaker.clear()
    _source_health.clear()
    yield
    _circuit_breaker.clear()
    _source_health.clear()
```

Create a `_DummySource(BaseJobSource)` with `fetch_jobs = AsyncMock(...)` for testing.

### Deal-Breaker Test Pattern

```python
config = SearchConfig(negative_title_keywords=["intern"], excluded_companies=["BadCorp"])
scorer = JobScorer(config)
bd = scorer.score_detailed(job)
assert bd.total <= 15  # negative title cap
assert bd.total == 0   # excluded company zero-out
```

---

## E2E Browser Tests (Playwright)

Located in `tests/e2e/`. **Excluded from default test runs** via `addopts = "--ignore=tests/e2e"` in pyproject.toml.

```bash
# Run E2E tests (requires dashboard to be running, or uses conftest auto-launch)
python -m pytest tests/e2e/ --no-header -v

# Run with headed browser for debugging
python -m pytest tests/e2e/ --headed --slowmo 500
```

| Test File | Tests | What It Covers |
|-----------|:-----:|----------------|
| `tests/e2e/test_profile_setup.py` | 4 | Dashboard loads, sidebar visible, CV uploader present, save button |
| `tests/e2e/test_search_flow.py` | 3 | Search button, filter controls, no-profile handling |
| `tests/e2e/test_job_browsing.py` | 3 | Main content renders, sort options, no errors on load |
| `tests/e2e/test_job_actions.py` | 3 | Export CSV/Markdown buttons, clear DB button |
| `tests/e2e/test_export.py` | 2 | Export section present, responsive viewport |

---

## QA Runner Enhancements

```bash
# Run QA with all enhancements (PDF validation, SearchConfig, domain detection, regression tracking)
python tests/qa_runner.py                    # All CVs, 3 pillars
python tests/qa_runner.py nurse              # Single CV
python tests/qa_runner.py --pillar 1         # Only parsing
```

New features:
- **PDF Parsing Validation**: Compares PDF vs TXT parsing for CVs that have both formats
- **SearchConfig Quality**: Validates generated config (skills, queries, domains, duplicates, locations)
- **Domain Detection**: Checks detected_domains matches ground truth
- **Per-Source Regression**: Tracks per-source fetch counts across runs, flags >50% drops
- **Benchmark Comparison**: Compares current vs previous results, flags regressions >5%

---

## Common Failure Patterns

| Symptom | Cause | Fix |
|---------|-------|-----|
| `ConnectionError` in source test | Missing mock URL | Add `m.get(re.compile(...))` for the source's URL |
| `TypeError: score()` | SearchConfig not provided | Pass `_TEST_CONFIG` or explicit SearchConfig |
| `AssertionError: 50 != 51` | Added source without updating test | Update count in `tests/test_cli.py` |
| `ModuleNotFoundError` | Missing import in `src/main.py` | Add import and registry entry |
| Async test hangs | Missing `_run()` wrapper | Wrap with `_run(_test())` |
| `AttributeError: 'NoneType'` in source | `search_config=None` not handled | Use `self.relevance_keywords` property (returns `[]`) |

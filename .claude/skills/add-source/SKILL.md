---
name: add-source
description: Scaffold a new job source with all required file changes (9-step checklist)
---

# /add-source — New Source Scaffold

Triggered by: `/add-source <name> <type>` where type is one of: `free`, `keyed`, `ats`, `rss`, `scraper`

You are adding a new job source to Job360. This touches 5-7 files. Follow the 9-step checklist from SOURCES.md exactly. Do NOT skip steps.

---

## Step 1: Gather Info

Determine from the user's request:
- **Source name** (snake_case, e.g., `my_source`)
- **Class name** (PascalCase + Source, e.g., `MySourceSource`)
- **Type**: free API, keyed API, ATS board, RSS/XML, or HTML scraper
- **API URL / endpoint** — if the user hasn't provided one, ask
- **Response format** — JSON, XML, or HTML

Read `SOURCES.md` for the matching template (Template 1-5). Read an existing source of the same type for reference patterns.

---

## Step 2: Create Source File

Create `src/sources/<name>.py` using the matching template from SOURCES.md:
- **Free API** → Template 1 (based on arbeitnow.py)
- **Keyed API** → Template 2 (based on reed.py)
- **ATS board** → Template 3 (based on greenhouse.py)
- **RSS/XML** → Template 4 (based on nhs_jobs.py)
- **Scraper** → Template 5 (based on jobtensor.py)

Must include: `name = "<name>"`, `fetch_jobs()`, relevance filtering via `self.relevance_keywords`, proper logging.

---

## Step 3: Wire into main.py (3 changes)

Read `src/main.py` and make exactly 3 additions:

1. **Import** at the top with the other source imports:
   ```python
   from src.sources.<name> import <Name>Source
   ```

2. **SOURCE_REGISTRY** entry (alphabetical within its group):
   ```python
   "<name>": <Name>Source,
   ```

3. **_build_sources()** entry in `all_sources` list:
   ```python
   <Name>Source(session, search_config=sc),  # or with api_key for keyed
   ```

If it's an HTML scraper, also add the name to `_SCRAPER_SOURCES` frozenset.

---

## Step 4: Add Rate Limits

Read `src/config/settings.py` and add to `RATE_LIMITS`:
```python
"<name>": {"concurrent": 2, "delay": 1.0},  # Free API
# or {"concurrent": 1, "delay": 2.0} for keyed
# or {"concurrent": 1, "delay": 3.0} for scraper
```

If keyed: also add the env var (e.g., `<NAME>_API_KEY = os.getenv("<NAME>_API_KEY", "")`).

---

## Step 5: Add Test

Read `tests/test_sources.py` and add a test following the existing pattern:
```python
def test_<name>_source():
    async def _test():
        with aioresponses() as m:
            m.get(re.compile(r"https://..."), payload=[...], repeat=True)
            async with aiohttp.ClientSession() as session:
                source = <Name>Source(session, search_config=_TEST_CONFIG)
                jobs = await source.fetch_jobs()
                assert isinstance(jobs, list)
    _run(_test())
```

---

## Step 6: Add Mock to Integration Tests

Read `tests/test_main.py` and add the mock URL pattern to `_mock_free_sources()` in the appropriate group (A-F).

---

## Step 7: Update Count Assertion

Read `tests/test_cli.py` and increment the count in `test_source_registry_count()`:
```python
assert len(SOURCE_REGISTRY) == <current + 1>
```

Also update the `expected` set in `test_source_registry_keys()` to include `"<name>"`.

---

## Step 8: Run Tests

```bash
python -m pytest tests/test_sources.py::test_<name>_source -v
python -m pytest tests/test_cli.py -v
python -m pytest tests/test_main.py -v --tb=short
```

All must pass before proceeding.

---

## Step 9: Update Docs

Run `/sync` to update all MD files with the new source count and categories.

---

## Checklist Summary

| Step | File | Change |
|------|------|--------|
| 2 | `src/sources/<name>.py` | Create source class |
| 3a | `src/main.py` | Import |
| 3b | `src/main.py` | SOURCE_REGISTRY entry |
| 3c | `src/main.py` | _build_sources() entry |
| 4 | `src/config/settings.py` | RATE_LIMITS + env var (if keyed) |
| 5 | `tests/test_sources.py` | Unit test |
| 6 | `tests/test_main.py` | Mock URL in _mock_free_sources() |
| 7 | `tests/test_cli.py` | Registry count + keys |
| 8 | — | Run tests |
| 9 | All MD files | /sync |

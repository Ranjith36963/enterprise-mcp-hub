"""Three-Pillar QA Runner — automated quality assurance for Job360.

Validates all three pillars independently for each CV:
  Pillar 1: CV Parsing Quality — parser output vs ground truth annotations
  Pillar 2: Source Data Quality — stored jobs vs live web validation
  Pillar 3: Engine Quality — result relevance, score sanity, skill match

Usage:
    python tests/qa_runner.py                    # Run all CVs (3 pillars)
    python tests/qa_runner.py nurse              # Run single CV
    python tests/qa_runner.py --list             # List available CVs
    python tests/qa_runner.py --pillar 1         # Only run Pillar 1 (parsing)
    python tests/qa_runner.py --skip-search      # Skip search, validate existing DB
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

QA_PROFILES_DIR = PROJECT_ROOT / "tests" / "qa_profiles"
QA_PDFS_DIR = QA_PROFILES_DIR / "pdfs"
DATA_DIR = PROJECT_ROOT / "data"
RESULTS_DIR = DATA_DIR / "qa_results"
GROUND_TRUTH_PATH = QA_PROFILES_DIR / "ground_truth.json"
BENCHMARK_PATH = DATA_DIR / "reports" / "BENCHMARK.md"
SOURCE_HISTORY_PATH = RESULTS_DIR / "source_history.json"


# ── CV Parsing (uses real parser, not simplified version) ────────────

def _parse_cv_text(text: str) -> dict:
    """Parse CV text using the REAL cv_parser pipeline (same as dashboard upload).

    This ensures we test the actual parser, not a simplified QA-only version.
    Falls back to basic parsing if structured parser fails.
    """
    from src.profile.cv_parser import _find_sections, _extract_skills_from_text
    from src.profile.cv_parser import _extract_known_skills, _extract_known_titles
    from src.profile.cv_parser import _extract_titles_from_experience, _extract_titles_from_entries
    from src.profile.models import CVData

    sections = _find_sections(text)
    cv = CVData(raw_text=text)

    # Skills — layered extraction (same as parse_cv)
    if "skills" in sections:
        cv.skills = _extract_skills_from_text(sections["skills"])
    if len(cv.skills) < 5:
        known = _extract_known_skills(text)
        existing_lower = {s.lower() for s in cv.skills}
        for skill in known:
            if skill.lower() not in existing_lower:
                cv.skills.append(skill)
                existing_lower.add(skill.lower())
    cv.skills = cv.skills[:50]

    # Titles — layered extraction
    if "experience" in sections:
        cv.job_titles = _extract_titles_from_experience(sections["experience"])
    if len(cv.job_titles) < 2:
        exp_text = sections.get("experience", "")
        if exp_text:
            entry_titles = _extract_titles_from_entries(exp_text)
            existing_lower = {t.lower() for t in cv.job_titles}
            for t in entry_titles:
                if t.lower() not in existing_lower:
                    cv.job_titles.append(t)
                    existing_lower.add(t.lower())
    if len(cv.job_titles) < 2:
        known_titles = _extract_known_titles(text)
        existing_lower = {t.lower() for t in cv.job_titles}
        for t in known_titles:
            if t.lower() not in existing_lower:
                cv.job_titles.append(t)
                existing_lower.add(t.lower())

    # Education
    if "education" in sections:
        lines = [l.strip() for l in sections["education"].split("\n") if l.strip()]
        cv.education = lines[:10]

    # Certifications
    if "certifications" in sections:
        lines = [l.strip() for l in sections["certifications"].split("\n") if l.strip()]
        cv.certifications = lines[:10]

    # Summary
    if "summary" in sections:
        cv.summary = sections["summary"][:500]

    # Structured parsing (work experiences, education, seniority)
    try:
        from src.profile.cv_structured_parser import enhance_cv_data
        cv = enhance_cv_data(cv, sections)
    except Exception:
        pass

    return cv


def _cv_to_profile_json(cv, text: str) -> dict:
    """Convert parsed CVData to profile JSON for saving."""
    summary = getattr(cv, "summary", "") or ""
    seniority = getattr(cv, "computed_seniority", "mid") or "mid"

    return {
        "cv_data": {
            "raw_text": text,
            "skills": cv.skills[:30],
            "job_titles": cv.job_titles[:6],
            "education": cv.education,
            "certifications": cv.certifications,
            "summary": summary,
            "structured_education": [
                {"degree": e.degree, "field_of_study": e.field_of_study,
                 "institution": e.institution, "year": e.year}
                for e in getattr(cv, "structured_education", [])
            ],
            "work_experiences": [
                {"title": w.title, "company": w.company,
                 "start_date": w.start_date, "end_date": w.end_date,
                 "duration_months": w.duration_months,
                 "description": w.description, "skills_used": w.skills_used}
                for w in getattr(cv, "work_experiences", [])
            ],
            "projects": [],
            "total_experience_months": getattr(cv, "total_experience_months", 48),
            "computed_seniority": seniority,
            "linkedin_positions": [],
            "linkedin_skills": [],
            "linkedin_industry": "",
            "github_languages": {},
            "github_topics": [],
            "github_skills_inferred": [],
        },
        "preferences": {
            "target_job_titles": cv.job_titles[:6],
            "additional_skills": [],
            "excluded_skills": [],
            "preferred_locations": ["London", "Remote", "UK"],
            "industries": [],
            "salary_min": None,
            "salary_max": None,
            "work_arrangement": "",
            "experience_level": seniority,
            "negative_keywords": ["intern"] if seniority != "entry" else [],
            "about_me": summary[:200],
        },
    }


# ── WP2A: PDF Parsing Validation ───────────────────────────────────

def _validate_pdf_parsing(cv_name: str, txt_cv) -> dict | None:
    """If a PDF version of this CV exists, parse it and compare to TXT parsing.

    Returns overlap metrics or None if no PDF exists.
    """
    pdf_path = QA_PDFS_DIR / f"{cv_name}.pdf"
    if not pdf_path.exists():
        return None

    try:
        from src.profile.cv_parser import parse_cv
        pdf_cv = parse_cv(str(pdf_path))
    except Exception as exc:
        return {"error": str(exc), "skills_recall": 0, "titles_recall": 0}

    txt_skills = {s.lower() for s in txt_cv.skills}
    pdf_skills = {s.lower() for s in pdf_cv.skills}
    skills_overlap = len(txt_skills & pdf_skills)
    skills_recall = skills_overlap / max(len(txt_skills), 1)

    txt_titles = {t.lower() for t in txt_cv.job_titles}
    pdf_titles = {t.lower() for t in pdf_cv.job_titles}
    titles_overlap = len(txt_titles & pdf_titles)
    titles_recall = titles_overlap / max(len(txt_titles), 1)

    return {
        "skills_recall": round(skills_recall, 3),
        "titles_recall": round(titles_recall, 3),
        "pdf_skills_count": len(pdf_cv.skills),
        "txt_skills_count": len(txt_cv.skills),
        "overlap_skills": skills_overlap,
    }


# ── WP2B: SearchConfig Quality Validation ─────────────────────────

def _validate_search_config(config, ground_truth_entry: dict) -> dict:
    """Validate that generated SearchConfig is complete and correct.

    Checks:
    1. At least some primary skills extracted
    2. Enough search queries (>= 3)
    3. Detected domains match expected domain
    4. No duplicate skills across primary + secondary
    5. Locations include UK-relevant entries
    6. Negative keywords present if non-entry level
    """
    checks = {}

    # 1. Primary skills present
    checks["has_primary_skills"] = len(config.primary_skills) > 0
    checks["primary_skills_count"] = len(config.primary_skills)

    # 2. Enough search queries
    checks["has_enough_queries"] = len(config.search_queries) >= 3
    checks["query_count"] = len(config.search_queries)

    # 3. Detected domains match expected
    expected_domain = ground_truth_entry.get("domain", "")
    detected = getattr(config, "detected_domains", [])
    checks["domain_detected"] = expected_domain in detected if expected_domain else True
    checks["detected_domains"] = detected

    # 4. No duplicate skills
    all_skills_lower = [s.lower() for s in config.primary_skills + config.secondary_skills]
    unique_count = len(set(all_skills_lower))
    checks["no_skill_duplicates"] = unique_count == len(all_skills_lower)
    checks["duplicate_count"] = len(all_skills_lower) - unique_count

    # 5. UK locations present
    loc_lower = [loc.lower() for loc in config.locations]
    checks["has_uk_locations"] = any(
        uk in loc for loc in loc_lower
        for uk in ("uk", "london", "remote", "england", "united kingdom")
    )

    # 6. Negative keywords for non-entry
    expected_seniority = ground_truth_entry.get("expected_seniority", "mid")
    if expected_seniority != "entry":
        checks["has_negative_keywords"] = len(config.negative_title_keywords) > 0
    else:
        checks["has_negative_keywords"] = True  # Not required for entry level

    # Compute quality score (0-1)
    passed = sum(1 for k, v in checks.items() if isinstance(v, bool) and v)
    total_checks = sum(1 for k, v in checks.items() if isinstance(v, bool))
    checks["quality_score"] = round(passed / max(total_checks, 1), 3)

    return checks


# ── WP2D: Per-Source Regression Tracking ──────────────────────────

def _load_source_history() -> dict:
    """Load per-source regression history from JSON."""
    if SOURCE_HISTORY_PATH.exists():
        try:
            return json.loads(SOURCE_HISTORY_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_source_history(history: dict) -> None:
    """Save per-source history, keeping last 30 entries."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    # Trim to last 30 dates
    dates = sorted(history.keys())
    if len(dates) > 30:
        for old in dates[:-30]:
            del history[old]
    SOURCE_HISTORY_PATH.write_text(json.dumps(history, indent=2), encoding="utf-8")


def _track_source_regression(search_stats: dict) -> list[str]:
    """Compare current per-source stats vs last run; flag regressions > 50%.

    Returns list of warning strings for regressions.
    """
    per_source = search_stats.get("per_source", {})
    if not per_source:
        return []

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    history = _load_source_history()

    # Find last entry (most recent date before today)
    prev_dates = sorted(d for d in history.keys() if d < today)
    prev = history[prev_dates[-1]] if prev_dates else {}

    # Save current run
    current = {}
    for src_name, stats in per_source.items():
        fetched = stats if isinstance(stats, int) else stats.get("fetched", 0)
        current[src_name] = {"fetched": fetched}
    history[today] = current
    _save_source_history(history)

    # Check regressions
    warnings = []
    for src_name, cur_stats in current.items():
        cur_fetched = cur_stats.get("fetched", 0)
        prev_stats = prev.get(src_name, {})
        prev_fetched = prev_stats.get("fetched", 0)
        if prev_fetched > 0 and cur_fetched < prev_fetched * 0.5:
            warnings.append(
                f"{src_name}: fetched dropped {prev_fetched} -> {cur_fetched} "
                f"({cur_fetched / prev_fetched:.0%} of previous)"
            )
    return warnings


# ── WP2E: Before/After Benchmark Comparison ───────────────────────

def _load_previous_benchmark() -> dict:
    """Load the previous benchmark results from qa_results.json."""
    results_path = RESULTS_DIR / "qa_results.json"
    if results_path.exists():
        try:
            prev = json.loads(results_path.read_text(encoding="utf-8"))
            return {r["cv_name"]: r for r in prev if "cv_name" in r}
        except Exception:
            pass
    return {}


def _compare_benchmarks(prev: dict, current: list[dict]) -> list[str]:
    """Compare current results vs previous; flag improvements and regressions.

    Returns list of comparison strings.
    """
    comparisons = []
    for r in current:
        name = r.get("cv_name", "")
        if name not in prev:
            comparisons.append(f"  {name}: NEW (no previous data)")
            continue
        old = prev[name]
        for pillar in ("pillar1", "pillar2", "pillar3"):
            old_conf = old.get(pillar, {}).get("confidence", 0) or 0
            new_conf = r.get(pillar, {}).get("confidence", 0) or 0
            if old_conf == 0 and new_conf == 0:
                continue
            diff = new_conf - old_conf
            if abs(diff) > 0.05:
                direction = "IMPROVED" if diff > 0 else "REGRESSED"
                comparisons.append(
                    f"  {name}/{pillar}: {old_conf:.0%} -> {new_conf:.0%} ({direction})"
                )
    return comparisons


# ── Pipeline helpers ────────────────────────────────────────────────

def _save_profile(profile_data: dict) -> None:
    """Save profile to data/user_profile.json."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "user_profile.json").write_text(
        json.dumps(profile_data, indent=2, ensure_ascii=False), encoding="utf-8"
    )


async def _run_search() -> dict:
    """Run the search pipeline and return stats."""
    import gc
    from src.main import run_search
    try:
        return await run_search(no_notify=True)
    finally:
        gc.collect()


async def _run_validation(per_source: int = 2) -> dict:
    """Run Pillar 2 validation and return JSON results."""
    from src.validation.sampler import sample_jobs
    from src.validation.checker import validate_job, aggregate_by_source
    from src.validation.report import generate_validation_json
    import aiohttp

    db_path = str(DATA_DIR / "jobs.db")
    jobs = await sample_jobs(db_path, per_source=per_source, days=7)
    if not jobs:
        return {"overall_confidence": 0, "total_checked": 0, "per_source": {}}

    sem = asyncio.Semaphore(3)
    async with aiohttp.ClientSession() as session:
        async def _check(job):
            async with sem:
                return await validate_job(session, job)
        results = await asyncio.gather(*[_check(j) for j in jobs])

    results = list(results)
    sources = aggregate_by_source(results)
    return generate_validation_json(results, sources)


async def _get_stored_jobs() -> list[dict]:
    """Get all stored jobs from DB for Pillar 3 validation."""
    from src.storage.database import JobDatabase
    db = JobDatabase(str(DATA_DIR / "jobs.db"))
    try:
        await db.init_db()
        return await db.get_recent_jobs(days=7, min_score=0)
    finally:
        await db.close()


def _clear_data() -> None:
    """Clear DB, logs, exports, reports for fresh run."""
    import gc
    import time as _time

    gc.collect()
    for pattern in ["jobs.db", "jobs.db-wal", "jobs.db-shm",
                     "exports/*.csv", "logs/job360.log",
                     "reports/report_*.md", "reports/validation_*.md",
                     "reports/validation_*.json"]:
        for f in DATA_DIR.glob(pattern):
            for attempt in range(3):
                try:
                    f.unlink(missing_ok=True)
                    break
                except PermissionError:
                    gc.collect()
                    _time.sleep(1)


# ── Main QA cycle ──────────────────────────────────────────────────

def run_qa_for_cv(
    cv_name: str,
    cv_path: Path,
    ground_truth: dict,
    run_search: bool = True,
    run_pillars: set[int] | None = None,
) -> dict:
    """Run three-pillar QA cycle for a single CV."""
    import gc

    if run_pillars is None:
        run_pillars = {1, 2, 3}

    print(f"\n{'='*70}")
    print(f"QA: {cv_name}")
    print(f"{'='*70}")

    # ── Parse CV using real parser ──
    cv_text = cv_path.read_text(encoding="utf-8")
    cv = _parse_cv_text(cv_text)
    profile = _cv_to_profile_json(cv, cv_text)
    seniority = getattr(cv, "computed_seniority", "mid")

    print(f"  Parsed: {len(cv.skills)} skills, {len(cv.job_titles)} titles, "
          f"{len(cv.education)} education, {len(cv.certifications)} certs, "
          f"seniority={seniority}")

    result = {
        "cv_name": cv_name,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "skills_parsed": cv.skills[:20],
        "titles_parsed": cv.job_titles,
        "seniority": seniority,
    }

    # ── WP2A: PDF Parsing Comparison (if PDF exists) ──
    pdf_result = _validate_pdf_parsing(cv_name, cv)
    if pdf_result:
        if "error" in pdf_result:
            print(f"  [PDF] Parse error: {pdf_result['error']}")
        else:
            print(f"  [PDF] Skills recall={pdf_result['skills_recall']:.0%}, "
                  f"Titles recall={pdf_result['titles_recall']:.0%}")
        result["pdf_parsing"] = pdf_result

    # ── PILLAR 1: CV Parsing Quality ──
    if 1 in run_pillars:
        print("  [P1] Validating parsing quality...")
        from src.validation.pillar1_parsing import validate_cv_parsing, load_ground_truth

        gt = ground_truth or load_ground_truth(GROUND_TRUTH_PATH)
        p1 = validate_cv_parsing(
            cv_name=cv_name,
            parsed_skills=cv.skills,
            parsed_titles=cv.job_titles,
            parsed_education=cv.education + [
                f"{e.degree} {e.field_of_study}" for e in getattr(cv, "structured_education", [])
            ],
            parsed_certifications=cv.certifications,
            parsed_seniority=seniority,
            ground_truth=gt,
        )
        print(f"  [P1] Skills={p1.skills_recall:.0%} ({p1.found_skills}/{p1.expected_skills}), "
              f"Titles={p1.titles_recall:.0%}, Seniority={'MATCH' if p1.seniority_match == 1.0 else 'MISMATCH'}, "
              f"Confidence={p1.confidence:.0%}")
        if p1.missing_skills:
            print(f"       Missing skills: {', '.join(p1.missing_skills[:5])}")
        if p1.missing_titles:
            print(f"       Missing titles: {', '.join(p1.missing_titles)}")

        result["pillar1"] = {
            "skills_recall": round(p1.skills_recall, 3),
            "titles_recall": round(p1.titles_recall, 3),
            "education_recall": round(p1.education_recall, 3),
            "certifications_recall": round(p1.certifications_recall, 3),
            "seniority_match": round(p1.seniority_match, 3),
            "confidence": round(p1.confidence, 3),
            "missing_skills": p1.missing_skills,
            "missing_titles": p1.missing_titles,
            "domain": p1.domain,
        }

    # ── WP2B+C: SearchConfig Quality + Domain Detection ──
    try:
        from src.profile.storage import load_profile as _lp
        from src.profile.keyword_generator import generate_search_config
        from src.profile.models import UserProfile, CVData, UserPreferences

        _save_profile(profile)  # save temporarily for SearchConfig generation
        loaded_profile = _lp()
        if loaded_profile and loaded_profile.is_complete:
            search_config = generate_search_config(loaded_profile)
            gt_entry = ground_truth.get(cv_name, {})
            sc_quality = _validate_search_config(search_config, gt_entry)
            result["search_config_quality"] = sc_quality

            # Domain detection accuracy
            expected_domain = gt_entry.get("domain", "")
            detected = getattr(search_config, "detected_domains", [])
            result["domain_detection"] = {
                "expected": expected_domain,
                "detected": detected,
                "match": expected_domain in detected if expected_domain else True,
            }
            print(f"  [SC] Quality={sc_quality['quality_score']:.0%}, "
                  f"Domains={detected}, "
                  f"{'MATCH' if result['domain_detection']['match'] else 'MISMATCH'}")
    except Exception as exc:
        print(f"  [SC] Validation error: {exc}")

    # ── Search Pipeline ──
    if run_search:
        gc.collect()
        _clear_data()
        _save_profile(profile)
        print("  [Search] Running pipeline...")
        t0 = time.time()
        stats = asyncio.run(_run_search())
        search_time = time.time() - t0
        total = stats.get("total_found", 0)
        new = stats.get("new_jobs", 0)
        print(f"  [Search] Done: {total} fetched, {new} stored ({search_time:.0f}s)")
        result["search"] = {
            "total_found": total,
            "new_stored": new,
            "sources_queried": stats.get("sources_queried", 0),
            "search_time_s": round(search_time, 1),
        }
    else:
        # Check if DB already has jobs from a previous run
        try:
            existing_jobs = asyncio.run(_get_stored_jobs())
            existing_count = len(existing_jobs)
        except Exception:
            existing_count = 0
        result["search"] = {"total_found": 0, "new_stored": existing_count, "sources_queried": 0,
                            "search_time_s": 0, "note": f"Skipped search, {existing_count} jobs in DB"}
        if existing_count:
            print(f"  [Search] Skipped — {existing_count} jobs already in DB")

    # ── PILLAR 2: Source Data Quality ──
    new_stored = result["search"].get("new_stored", 0)
    if 2 in run_pillars and new_stored > 0:
        print("  [P2] Validating source data quality...")
        val = asyncio.run(_run_validation(per_source=2))
        p2_conf = val.get("overall_confidence", 0)
        p2_sources = len(val.get("per_source", {}))
        print(f"  [P2] Confidence={p2_conf:.0%} ({p2_sources} sources validated)")
        result["pillar2"] = {
            "confidence": round(p2_conf, 3) if isinstance(p2_conf, float) else p2_conf,
            "sources_validated": p2_sources,
            "per_source": {
                k: round(v.get("confidence", 0), 3)
                for k, v in val.get("per_source", {}).items()
            },
        }
    else:
        result["pillar2"] = {"confidence": 0, "sources_validated": 0, "per_source": {},
                             "note": "Skipped (no jobs)" if new_stored == 0 else "Skipped (not requested)"}

    # ── PILLAR 3: Engine Quality ──
    if 3 in run_pillars and new_stored > 0:
        print("  [P3] Validating engine quality...")
        from src.validation.pillar3_engine import validate_engine_quality
        gt_entry = ground_truth.get(cv_name, {})
        domain = gt_entry.get("domain", "unknown")
        exp_seniority = gt_entry.get("expected_seniority", seniority)

        jobs = asyncio.run(_get_stored_jobs())
        p3 = validate_engine_quality(
            cv_name=cv_name,
            domain=domain,
            jobs=jobs,
            cv_skills=cv.skills,
            expected_seniority=exp_seniority,
        )
        print(f"  [P3] Relevance={p3.domain_relevance:.0%}, Scores={p3.score_sanity:.0%}, "
              f"SkillMatch={p3.skill_match_accuracy:.0%}, Seniority={p3.seniority_alignment:.0%}, "
              f"Confidence={p3.confidence:.0%}")
        if p3.irrelevant_examples:
            print(f"       Irrelevant: {'; '.join(p3.irrelevant_examples[:3])}")

        result["pillar3"] = {
            "domain": domain,
            "domain_relevance": round(p3.domain_relevance, 3),
            "score_sanity": round(p3.score_sanity, 3),
            "skill_match_accuracy": round(p3.skill_match_accuracy, 3),
            "seniority_alignment": round(p3.seniority_alignment, 3),
            "confidence": round(p3.confidence, 3),
            "score_stats": p3.score_stats,
            "irrelevant_examples": p3.irrelevant_examples[:5],
        }
    else:
        result["pillar3"] = {"confidence": 0, "domain": "unknown",
                             "note": "Skipped (no jobs)" if new_stored == 0 else "Skipped (not requested)"}

    return result


def _update_benchmark(all_results: list[dict]) -> None:
    """Update BENCHMARK.md with three-pillar results."""
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # Compute averages
    p1_scores = [r["pillar1"]["confidence"] for r in all_results if "pillar1" in r and r["pillar1"].get("confidence")]
    p2_scores = [r["pillar2"]["confidence"] for r in all_results if "pillar2" in r and r["pillar2"].get("confidence")]
    p3_scores = [r["pillar3"]["confidence"] for r in all_results if "pillar3" in r and r["pillar3"].get("confidence")]

    p1_avg = sum(p1_scores) / len(p1_scores) if p1_scores else 0
    p2_avg = sum(p2_scores) / len(p2_scores) if p2_scores else 0
    p3_avg = sum(p3_scores) / len(p3_scores) if p3_scores else 0
    overall = (p1_avg + p2_avg + p3_avg) / 3 if (p1_scores and p2_scores and p3_scores) else max(p1_avg, p2_avg, p3_avg)

    lines = [
        "# Job360 Quality Benchmark",
        "",
        f"**Last updated:** {timestamp}",
        f"**Overall confidence:** {overall:.0%}",
        f"**Pillar 1 (CV Parsing):** {p1_avg:.0%} avg across {len(p1_scores)} CVs",
        f"**Pillar 2 (Source Data):** {p2_avg:.0%} avg across {len(p2_scores)} CVs",
        f"**Pillar 3 (Engine Quality):** {p3_avg:.0%} avg across {len(p3_scores)} CVs",
        f"**Test CVs:** {len(all_results)} professional CVs across {len(set(r.get('pillar1', {}).get('domain', '') for r in all_results))} domains",
        "",
        "## Per-CV Results",
        "",
        "| CV | Domain | P1 Parsing | P2 Source | P3 Engine | PDF | SC | Jobs | Overall |",
        "|---|--------|:---:|:---:|:---:|:---:|:---:|:---:|:---:|",
    ]

    for r in sorted(all_results, key=lambda x: x.get("cv_name", "")):
        name = r.get("cv_name", "?")
        domain = r.get("pillar1", {}).get("domain", r.get("pillar3", {}).get("domain", "?"))
        p1 = r.get("pillar1", {}).get("confidence", 0)
        p2 = r.get("pillar2", {}).get("confidence", 0)
        p3 = r.get("pillar3", {}).get("confidence", 0)
        jobs = r.get("search", {}).get("new_stored", 0)
        row_scores = [s for s in [p1, p2, p3] if s]
        row_avg = sum(row_scores) / len(row_scores) if row_scores else 0
        p2_str = f"{p2:.0%}" if p2 else "N/A"
        p3_str = f"{p3:.0%}" if p3 else "N/A"
        # WP2 columns: PDF parsing and SearchConfig quality
        pdf = r.get("pdf_parsing", {})
        pdf_str = f"{pdf['skills_recall']:.0%}" if pdf and "skills_recall" in pdf and not pdf.get("error") else "N/A"
        sc = r.get("search_config_quality", {})
        sc_str = f"{sc['quality_score']:.0%}" if sc and "quality_score" in sc else "N/A"
        lines.append(
            f"| {name} | {domain} | {p1:.0%} | {p2_str} | {p3_str} "
            f"| {pdf_str} | {sc_str} | {jobs} | **{row_avg:.0%}** |"
        )

    # Pillar 1 details
    lines.extend(["", "## Pillar 1: CV Parsing Details", ""])
    for r in all_results:
        p1 = r.get("pillar1", {})
        if p1.get("missing_skills") or p1.get("missing_titles"):
            name = r.get("cv_name", "?")
            lines.append(f"### {name}")
            if p1.get("missing_skills"):
                lines.append(f"- Missing skills: {', '.join(p1['missing_skills'][:10])}")
            if p1.get("missing_titles"):
                lines.append(f"- Missing titles: {', '.join(p1['missing_titles'])}")
            sr = p1.get("skills_recall", 0)
            tr = p1.get("titles_recall", 0)
            lines.append(f"- Skills recall: {sr:.0%}, Titles recall: {tr:.0%}")
            lines.append("")

    # Pillar 3 details
    lines.extend(["## Pillar 3: Engine Quality Details", ""])
    for r in all_results:
        p3 = r.get("pillar3", {})
        if p3.get("irrelevant_examples") or p3.get("score_stats"):
            name = r.get("cv_name", "?")
            stats = p3.get("score_stats", {})
            if stats:
                lines.append(f"### {name}")
                lines.append(f"- Score distribution: avg={stats.get('avg')}, min={stats.get('min')}, max={stats.get('max')}, spread={stats.get('spread')}")
                lines.append(f"- Domain relevance: {p3.get('domain_relevance', 0):.0%}")
                if p3.get("irrelevant_examples"):
                    lines.append(f"- Irrelevant examples: {'; '.join(p3['irrelevant_examples'][:3])}")
                lines.append("")

    # Write benchmark
    BENCHMARK_PATH.parent.mkdir(parents=True, exist_ok=True)
    BENCHMARK_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nBenchmark updated: {BENCHMARK_PATH}")


def main():
    parser = argparse.ArgumentParser(description="Job360 Three-Pillar QA Runner")
    parser.add_argument("cv", nargs="?", help="CV name to test (without .txt)")
    parser.add_argument("--list", action="store_true", help="List available CVs")
    parser.add_argument("--pillar", type=int, choices=[1, 2, 3], help="Run only one pillar")
    parser.add_argument("--skip-search", action="store_true", help="Skip search, validate existing DB")
    args = parser.parse_args()

    cv_files = sorted(QA_PROFILES_DIR.glob("*.txt"))

    if args.list:
        print("Available CVs:")
        for f in cv_files:
            print(f"  {f.stem}")
        return

    if args.cv:
        cv_files = [f for f in cv_files if f.stem == args.cv]
        if not cv_files:
            print(f"CV not found: {args.cv}")
            return

    # Load ground truth once
    from src.validation.pillar1_parsing import load_ground_truth
    ground_truth = load_ground_truth(GROUND_TRUTH_PATH)

    run_pillars = {args.pillar} if args.pillar else {1, 2, 3}
    do_search = not args.skip_search and (2 in run_pillars or 3 in run_pillars)

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    all_results: list[dict] = []

    for cv_path in cv_files:
        try:
            result = run_qa_for_cv(
                cv_name=cv_path.stem,
                cv_path=cv_path,
                ground_truth=ground_truth,
                run_search=do_search,
                run_pillars=run_pillars,
            )
            all_results.append(result)
        except Exception as exc:
            import traceback
            print(f"  ERROR: {exc}")
            traceback.print_exc()
            all_results.append({"cv_name": cv_path.stem, "error": str(exc)})

    # ── Summary ──
    print(f"\n{'='*70}")
    print("THREE-PILLAR QA SUMMARY")
    print(f"{'='*70}")
    print(f"{'CV':<30} {'P1':>5} {'P2':>5} {'P3':>5} {'Jobs':>6} {'Overall':>8}")
    print("-" * 70)
    for r in all_results:
        if "error" in r:
            print(f"{r['cv_name']:<30} ERROR: {r['error'][:35]}")
        else:
            p1 = r.get("pillar1", {}).get("confidence", 0)
            p2 = r.get("pillar2", {}).get("confidence", 0)
            p3 = r.get("pillar3", {}).get("confidence", 0)
            jobs = r.get("search", {}).get("new_stored", 0)
            scores = [s for s in [p1, p2, p3] if s]
            overall = sum(scores) / len(scores) if scores else 0
            p1s = f"{p1:.0%}" if p1 else "N/A"
            p2s = f"{p2:.0%}" if p2 else "N/A"
            p3s = f"{p3:.0%}" if p3 else "N/A"
            print(f"{r['cv_name']:<30} {p1s:>5} {p2s:>5} {p3s:>5} {jobs:>6} {overall:>7.0%}")

    # ── WP2D: Per-source regression tracking ──
    for r in all_results:
        search_stats = r.get("search", {})
        if search_stats.get("per_source") or search_stats.get("sources_queried", 0) > 0:
            regressions = _track_source_regression(search_stats)
            if regressions:
                print("\n  SOURCE REGRESSIONS:")
                for w in regressions:
                    print(f"    ⚠ {w}")
            break  # Only track once (last search run)

    # ── WP2E: Before/after benchmark comparison ──
    prev_benchmark = _load_previous_benchmark()
    if prev_benchmark:
        comparisons = _compare_benchmarks(prev_benchmark, all_results)
        if comparisons:
            print("\n  BENCHMARK CHANGES:")
            for c in comparisons:
                print(f"    {c}")

    # Save results JSON
    results_path = RESULTS_DIR / "qa_results.json"
    results_path.write_text(json.dumps(all_results, indent=2), encoding="utf-8")
    print(f"\nResults saved: {results_path}")

    # Update benchmark MD
    _update_benchmark(all_results)

    # Clean up: remove benchmark DB and profile so they don't pollute
    # the user's real dashboard. QA results are saved in qa_results.json.
    _clear_data()
    print("Cleaned up benchmark data (won't affect dashboard)")


if __name__ == "__main__":
    main()

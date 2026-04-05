"""Pillar 3: Search & Match Engine Quality Validator.

Given that CV parsing (Pillar 1) and source data (Pillar 2) are good,
validates whether the engine produces relevant results:

- Domain relevance: Do results match the CV's professional domain?
- Score distribution: Are scores reasonable (not compressed, not inflated)?
- Skill overlap: Do high-scoring jobs actually mention the seeker's skills?
- Seniority alignment: Are job seniority levels appropriate?
- Negative filtering: Are excluded/irrelevant jobs properly filtered?

Metrics per CV:
- Domain relevance score (0-1): % of stored jobs matching the CV's domain
- Score sanity (0-1): score distribution health (spread, not all bunched)
- Skill match accuracy (0-1): avg skill overlap for top-10 scored jobs
- Overall Pillar 3 confidence: weighted average
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger("job360.validation.pillar3")


# ── LLM-based validation helpers ────────────────────────────────────

def _llm_classify_domain(jobs: list[dict], domain: str) -> list[bool]:
    """Use LLM to classify whether each job belongs to the given domain.

    Falls back to keyword matching if LLM is unavailable.
    """
    try:
        from src.llm.client import llm_complete, is_configured, parse_json_response
        if not is_configured():
            return []
    except ImportError:
        return []

    # Batch jobs into chunks of 10 for efficient LLM calls
    results: list[bool] = []
    for i in range(0, len(jobs), 10):
        batch = jobs[i:i + 10]
        job_list = "\n".join(
            f'{idx + 1}. "{j.get("title", "")} at {j.get("company", "")}"'
            for idx, j in enumerate(batch)
        )
        prompt = (
            f"You are classifying job listings by professional domain.\n"
            f"Domain: {domain}\n\n"
            f"For each job below, answer YES if it belongs to the {domain} domain, NO if not.\n"
            f"Return ONLY a JSON array of booleans, e.g. [true, false, true, ...]\n\n"
            f"Jobs:\n{job_list}"
        )
        try:
            raw = llm_complete(prompt, max_tokens=200)
            if raw:
                parsed = parse_json_response(raw)
                if isinstance(parsed, list) and len(parsed) == len(batch):
                    results.extend(bool(v) for v in parsed)
                    continue
        except (RuntimeError, ValueError, OSError) as exc:
            logger.debug(f"LLM domain classification failed: {exc}")
        # Fallback: mark all as unknown (empty list triggers keyword fallback)
        return []

    return results


def _llm_check_skill_overlap(jobs: list[dict], cv_skills: list[str]) -> list[float]:
    """Use LLM to assess what % of CV skills are relevant to each job.

    Returns a list of overlap scores (0.0-1.0) per job.
    Falls back to keyword matching if LLM is unavailable.
    """
    try:
        from src.llm.client import llm_complete, is_configured, parse_json_response
        if not is_configured():
            return []
    except ImportError:
        return []

    skills_str = ", ".join(cv_skills[:20])  # Cap to avoid prompt bloat
    results: list[float] = []

    for job in jobs:
        title = job.get("title", "")
        desc = (job.get("description") or "")[:800]
        prompt = (
            f"A job seeker has these skills: {skills_str}\n\n"
            f"Job: {title}\n"
            f"Description: {desc}\n\n"
            f"What percentage (0-100) of the seeker's skills are relevant to this job?\n"
            f"Consider synonyms, related skills, and transferable skills.\n"
            f"Return ONLY a single integer number (0-100)."
        )
        try:
            raw = llm_complete(prompt, max_tokens=20)
            if raw:
                # Extract number from response
                nums = re.findall(r'\d+', raw.strip())
                if nums:
                    pct = min(int(nums[0]), 100) / 100.0
                    results.append(pct)
                    continue
        except (RuntimeError, ValueError, OSError) as exc:
            logger.debug(f"LLM skill overlap failed: {exc}")
        results.append(-1.0)  # -1 = LLM failed for this job

    # If too many failures, return empty to trigger keyword fallback
    failures = sum(1 for r in results if r < 0)
    if failures > len(results) * 0.5:
        return []
    return [max(0.0, r) for r in results]


@dataclass
class EngineResult:
    """Result of engine quality check for one CV's search results."""
    cv_name: str
    domain: str
    total_jobs_stored: int = 0
    # Scores (0.0 - 1.0)
    domain_relevance: float = 0.0
    score_sanity: float = 0.0
    skill_match_accuracy: float = 0.0
    seniority_alignment: float = 0.0
    # Details
    relevant_jobs: int = 0
    irrelevant_examples: list[str] = field(default_factory=list)
    score_stats: dict = field(default_factory=dict)
    top_jobs_skill_overlap: list[dict] = field(default_factory=list)
    notes: str = ""
    # Overall
    confidence: float = 0.0

    def compute_confidence(self) -> float:
        """Weighted: domain_relevance(0.35) + score_sanity(0.25) + skill_match(0.25) + seniority(0.15)."""
        self.confidence = (
            self.domain_relevance * 0.35
            + self.score_sanity * 0.25
            + self.skill_match_accuracy * 0.25
            + self.seniority_alignment * 0.15
        )
        return self.confidence


def _check_domain_relevance(jobs: list[dict], domain: str) -> tuple[float, int, list[str]]:
    """Check what % of stored jobs match the CV's domain.

    Uses LLM classification first (understands context, not just keywords).
    Falls back to keyword matching if LLM is unavailable.
    """
    if not jobs:
        return 0.0, 0, []

    # Try LLM-based classification first
    llm_results = _llm_classify_domain(jobs, domain)

    relevant = 0
    irrelevant_examples = []

    if llm_results and len(llm_results) == len(jobs):
        # LLM classification available
        for i, job in enumerate(jobs):
            if llm_results[i]:
                relevant += 1
            elif len(irrelevant_examples) < 5:
                irrelevant_examples.append(
                    f"{job.get('title', 'Unknown')} @ {job.get('company', 'Unknown')}"
                )
        logger.info(f"P3 domain relevance: LLM classified {relevant}/{len(jobs)} as {domain}")
    else:
        # Fallback: keyword matching (less accurate but always available)
        from src.filters.description_matcher import text_contains_with_synonyms
        # Use domain detector's signal words instead of hardcoded list
        try:
            from src.profile.domain_detector import _DOMAIN_SIGNALS
            title_kws, skill_kws = _DOMAIN_SIGNALS.get(domain, (set(), set()))
            keywords = list(title_kws | skill_kws)
        except ImportError:
            keywords = []

        if not keywords:
            return 0.5, 0, []  # Unknown domain, neutral score

        for job in jobs:
            title = (job.get("title") or "").lower()
            desc = (job.get("description") or "").lower()[:500]
            combined = f"{title} {desc}"

            is_relevant = any(kw in combined for kw in keywords)
            if is_relevant:
                relevant += 1
            elif len(irrelevant_examples) < 5:
                irrelevant_examples.append(
                    f"{job.get('title', 'Unknown')} @ {job.get('company', 'Unknown')}"
                )

    score = relevant / len(jobs) if jobs else 0.0
    return score, relevant, irrelevant_examples


def _check_score_sanity(jobs: list[dict]) -> tuple[float, dict]:
    """Check if score distribution is healthy (not compressed, has spread)."""
    scores = [j.get("match_score", 0) for j in jobs if j.get("match_score")]
    if not scores:
        return 0.0, {}

    avg = sum(scores) / len(scores)
    min_s = min(scores)
    max_s = max(scores)
    spread = max_s - min_s
    # Score above 30 jobs (should be most since MIN_MATCH_SCORE=30)
    above_30 = sum(1 for s in scores if s >= 30)
    above_50 = sum(1 for s in scores if s >= 50)
    above_70 = sum(1 for s in scores if s >= 70)

    stats = {
        "count": len(scores),
        "avg": round(avg, 1),
        "min": min_s,
        "max": max_s,
        "spread": spread,
        "above_50": above_50,
        "above_70": above_70,
    }

    # Sanity checks:
    score = 1.0
    # 1. Spread should be > 15 (not all same score)
    if spread < 15:
        score -= 0.3
    # 2. Average should be between 35 and 80 (not too low, not inflated)
    if avg < 35:
        score -= 0.2
    elif avg > 80:
        score -= 0.2  # inflated scores
    # 3. Should have some high-quality matches (at least 1 above 60)
    if max_s < 60:
        score -= 0.2
    # 4. Should have diversity — not all bunched at one level
    if len(scores) > 5 and above_70 / len(scores) > 0.8:
        score -= 0.2  # too many high scores = probably inflated

    return max(0.0, score), stats


def _check_skill_match(jobs: list[dict], cv_skills: list[str]) -> tuple[float, list[dict]]:
    """Check skill overlap between top-scored jobs and CV skills.

    Uses LLM for semantic skill matching (understands synonyms, related
    skills, transferable skills). Falls back to keyword+synonym matching.
    """
    if not jobs or not cv_skills:
        return 0.0, []

    # Sort by score, take top 10
    sorted_jobs = sorted(jobs, key=lambda j: j.get("match_score", 0), reverse=True)[:10]

    # Try LLM-based skill overlap first
    llm_overlaps = _llm_check_skill_overlap(sorted_jobs, cv_skills)

    overlaps = []
    total_overlap = 0.0

    if llm_overlaps and len(llm_overlaps) == len(sorted_jobs):
        # LLM results available
        for i, job in enumerate(sorted_jobs):
            pct = llm_overlaps[i]
            total_overlap += pct
            overlaps.append({
                "title": job.get("title", "Unknown"),
                "score": job.get("match_score", 0),
                "overlap_pct": round(pct, 2),
                "method": "llm",
            })
        logger.info(f"P3 skill match: LLM avg overlap={total_overlap / len(sorted_jobs):.0%}")
    else:
        # Fallback: keyword + synonym matching
        try:
            from src.filters.description_matcher import text_contains_with_synonyms
            use_synonyms = True
        except ImportError:
            use_synonyms = False

        cv_skills_lower = {s.lower() for s in cv_skills}

        for job in sorted_jobs:
            desc = (job.get("description") or "").lower()
            title = (job.get("title") or "").lower()
            combined = f"{title} {desc}"

            matched = []
            for skill in cv_skills_lower:
                if use_synonyms:
                    if text_contains_with_synonyms(combined, skill):
                        matched.append(skill)
                elif skill in combined:
                    matched.append(skill)

            overlap_pct = len(matched) / len(cv_skills_lower) if cv_skills_lower else 0.0
            total_overlap += overlap_pct
            overlaps.append({
                "title": job.get("title", "Unknown"),
                "score": job.get("match_score", 0),
                "skills_found": len(matched),
                "skills_total": len(cv_skills_lower),
                "overlap_pct": round(overlap_pct, 2),
                "method": "synonym",
            })

    avg_overlap = total_overlap / len(sorted_jobs) if sorted_jobs else 0.0
    # Scale: 15%+ overlap for top jobs = 1.0 (many jobs won't list all CV skills)
    score = min(1.0, avg_overlap / 0.15)
    return score, overlaps


def _check_seniority_alignment(jobs: list[dict], expected_seniority: str) -> float:
    """Check if job seniority levels match what the CV seeker should get."""
    if not jobs or not expected_seniority:
        return 0.5  # neutral if we can't check

    seniority_keywords = {
        "entry": ["junior", "graduate", "entry", "trainee", "intern", "apprentice"],
        "mid": ["mid", "intermediate"],
        "senior": ["senior", "sr", "experienced", "staff", "principal"],
        "lead": ["lead", "principal", "head", "manager", "director", "staff"],
        "executive": ["director", "vp", "chief", "head of", "executive", "cto", "cfo"],
    }

    target_words = seniority_keywords.get(expected_seniority, [])
    # Also accept adjacent levels
    levels = ["entry", "mid", "senior", "lead", "executive"]
    try:
        idx = levels.index(expected_seniority)
        adjacent = []
        if idx > 0:
            adjacent.extend(seniority_keywords.get(levels[idx - 1], []))
        if idx < len(levels) - 1:
            adjacent.extend(seniority_keywords.get(levels[idx + 1], []))
    except ValueError:
        adjacent = []

    exact = 0
    close = 0
    neutral = 0
    total_checked = 0

    for job in jobs[:20]:  # Check top 20
        title = (job.get("title") or "").lower()
        desc = (job.get("description") or "").lower()[:300]
        if not title:
            continue
        total_checked += 1

        if any(w in title for w in target_words):
            exact += 1
        elif any(w in title for w in adjacent):
            close += 1
        elif any(w in desc for w in target_words):
            # Seniority signal in description but not title — weaker signal
            close += 1
        else:
            # No seniority keyword anywhere — neutral (most JDs don't state level)
            neutral += 1

    if total_checked == 0:
        return 0.5

    # Exact=1.0, close=0.7, no keyword=0.5 (neutral, not penalty)
    alignment = (exact * 1.0 + close * 0.7 + neutral * 0.5) / total_checked
    return min(1.0, alignment)


def validate_engine_quality(
    cv_name: str,
    domain: str,
    jobs: list[dict],
    cv_skills: list[str],
    expected_seniority: str = "",
) -> EngineResult:
    """Run all engine quality checks for one CV's search results."""
    result = EngineResult(
        cv_name=cv_name,
        domain=domain,
        total_jobs_stored=len(jobs),
    )

    if not jobs:
        result.notes = "No jobs found — cannot validate engine quality"
        return result

    # Domain relevance
    result.domain_relevance, result.relevant_jobs, result.irrelevant_examples = (
        _check_domain_relevance(jobs, domain)
    )

    # Score distribution sanity
    result.score_sanity, result.score_stats = _check_score_sanity(jobs)

    # Skill match accuracy for top jobs
    result.skill_match_accuracy, result.top_jobs_skill_overlap = (
        _check_skill_match(jobs, cv_skills)
    )

    # Seniority alignment
    result.seniority_alignment = _check_seniority_alignment(jobs, expected_seniority)

    result.compute_confidence()
    return result


def format_pillar3_report(results: list[EngineResult]) -> str:
    """Format Pillar 3 results as markdown table."""
    lines = [
        "## Pillar 3: Search & Match Engine Quality",
        "",
        "| CV | Domain | Jobs | Relevance | Score Sanity | Skill Match | Seniority | Confidence |",
        "|---|--------|:---:|:---:|:---:|:---:|:---:|:---:|",
    ]

    for r in sorted(results, key=lambda x: x.confidence, reverse=True):
        lines.append(
            f"| {r.cv_name} | {r.domain} "
            f"| {r.total_jobs_stored} "
            f"| {r.domain_relevance:.0%} ({r.relevant_jobs}/{r.total_jobs_stored}) "
            f"| {r.score_sanity:.0%} "
            f"| {r.skill_match_accuracy:.0%} "
            f"| {r.seniority_alignment:.0%} "
            f"| **{r.confidence:.0%}** |"
        )

    # Overall average (excluding CVs with 0 jobs)
    valid_results = [r for r in results if r.total_jobs_stored > 0]
    if valid_results:
        avg = sum(r.confidence for r in valid_results) / len(valid_results)
        lines.append(f"\n**Overall Pillar 3 Confidence: {avg:.0%}** ({len(valid_results)} CVs with results)")

    # Issues
    issues = []
    for r in results:
        if r.total_jobs_stored == 0:
            issues.append(f"- **{r.cv_name}** ({r.domain}): Zero jobs found — sources may not cover this domain")
        elif r.domain_relevance < 0.5:
            issues.append(f"- **{r.cv_name}**: Low domain relevance ({r.domain_relevance:.0%}) — engine returning off-domain jobs")
        if r.score_sanity < 0.5 and r.total_jobs_stored > 0:
            stats = r.score_stats
            issues.append(f"- **{r.cv_name}**: Score distribution issue — avg={stats.get('avg')}, spread={stats.get('spread')}")
        if r.irrelevant_examples:
            examples = "; ".join(r.irrelevant_examples[:3])
            issues.append(f"  Irrelevant examples: {examples}")

    if issues:
        lines.append("\n### Engine Issues Found")
        lines.extend(issues[:20])

    return "\n".join(lines)

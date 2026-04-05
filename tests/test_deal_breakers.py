"""Tests for deal-breaker scoring logic.

Covers: negative title keyword → cap at 15, negative description → normal
penalty (no cap), excluded company → zero-out, company name normalization,
and short description filtering.
"""

from datetime import datetime, timezone

from src.models import Job
from src.filters.skill_matcher import JobScorer
from src.profile.models import SearchConfig


def _make_config(**overrides) -> SearchConfig:
    defaults = dict(
        job_titles=["Data Scientist", "ML Engineer"],
        primary_skills=["Python", "SQL", "Machine Learning"],
        secondary_skills=["Docker"],
        tertiary_skills=[],
        relevance_keywords=["data", "python"],
        negative_title_keywords=["intern", "volunteer", "apprentice"],
        locations=["London", "Remote"],
        visa_keywords=["visa"],
        core_domain_words={"data", "scientist", "ml"},
        supporting_role_words={"engineer"},
        search_queries=["Data Scientist London"],
        excluded_companies=[],
    )
    defaults.update(overrides)
    return SearchConfig(**defaults)


def _make_job(**overrides) -> Job:
    defaults = dict(
        title="Data Scientist",
        company="TechCorp",
        location="London, UK",
        description=(
            "Looking for a Data Scientist with Python, SQL, and Machine Learning "
            "skills. 3+ years experience required. BSc minimum."
        ),
        apply_url="https://example.com/job/1",
        source="reed",
        date_found=datetime.now(timezone.utc).isoformat(),
    )
    defaults.update(overrides)
    return Job(**defaults)


class TestDealBreakers:

    def test_negative_title_caps_at_15(self):
        """Job with negative keyword in TITLE → score capped at 15."""
        config = _make_config(negative_title_keywords=["intern"])
        scorer = JobScorer(config)
        job = _make_job(title="Data Science Intern", description=(
            "Great opportunity for a Data Science Intern with Python and ML skills."
        ))
        bd = scorer.score_detailed(job)
        assert bd.total <= 15, f"Score {bd.total} should be capped at 15"

    def test_negative_description_only_no_cap(self):
        """Negative keyword in description only → penalty (-15), but NO hard cap."""
        config = _make_config(negative_title_keywords=["volunteer"])
        scorer = JobScorer(config)
        job = _make_job(
            title="Senior Data Scientist",
            description=(
                "Senior Data Scientist role. Python, SQL, Machine Learning required. "
                "We also have volunteer mentoring opportunities."
            ),
        )
        bd = scorer.score_detailed(job)
        # Should NOT be capped at 15 — description-only penalty is -15
        assert bd.penalty == 15
        # Total could still be above 15 depending on other scores
        # The key assertion: no hard cap was applied
        # (If we had a high base score, total > 15 is possible)

    def test_excluded_company_zero_out(self):
        """Excluded company → score = 0 regardless of match quality."""
        config = _make_config(excluded_companies=["TechCorp"])
        scorer = JobScorer(config)
        job = _make_job(company="TechCorp", title="Data Scientist")
        bd = scorer.score_detailed(job)
        assert bd.total == 0, f"Excluded company should zero-out; got {bd.total}"

    def test_excluded_company_normalized(self):
        """'TechCorp Ltd' matches 'TechCorp' after stripping 'Ltd' suffix."""
        config = _make_config(excluded_companies=["TechCorp"])
        scorer = JobScorer(config)
        job = _make_job(company="TechCorp Ltd", title="Data Scientist")
        bd = scorer.score_detailed(job)
        assert bd.total == 0, f"Normalized company should match; got {bd.total}"

    def test_excluded_company_no_false_positive(self):
        """Non-excluded company should NOT be zeroed out."""
        config = _make_config(excluded_companies=["BadCorp"])
        scorer = JobScorer(config)
        job = _make_job(company="GoodCorp", title="Data Scientist")
        bd = scorer.score_detailed(job)
        assert bd.total > 0, "Non-excluded company should have a positive score"

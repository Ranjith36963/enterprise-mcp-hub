"""Tests for evidence tagging in score_detailed().

Verifies that each of the 8 dimensions produces a non-empty *_reason
string explaining WHY it scored what it did.
"""

from datetime import datetime, timezone

from src.models import Job
from src.filters.skill_matcher import JobScorer, ScoreBreakdown
from src.filters.jd_parser import parse_jd, ParsedJD
from src.profile.models import SearchConfig, CVData


def _make_config(**overrides) -> SearchConfig:
    defaults = dict(
        job_titles=["Data Scientist", "ML Engineer"],
        primary_skills=["Python", "SQL", "Machine Learning", "TensorFlow"],
        secondary_skills=["Docker", "AWS"],
        tertiary_skills=[],
        relevance_keywords=["data", "machine learning", "python"],
        negative_title_keywords=["intern", "volunteer"],
        locations=["London", "Remote"],
        visa_keywords=["visa", "sponsorship"],
        core_domain_words={"data", "scientist", "ml", "machine", "learning"},
        supporting_role_words={"engineer", "analyst"},
        search_queries=["Data Scientist London"],
        target_experience_level="mid",
    )
    defaults.update(overrides)
    return SearchConfig(**defaults)


def _make_job(**overrides) -> Job:
    defaults = dict(
        title="Senior Data Scientist",
        company="DeepMind",
        location="London, UK",
        description=(
            "We need a Senior Data Scientist with 5+ years experience in "
            "Python, SQL, TensorFlow, and Machine Learning. "
            "PhD or MSc preferred. Experience with Docker and AWS a plus."
        ),
        apply_url="https://example.com/job/1",
        source="greenhouse",
        date_found=datetime.now(timezone.utc).isoformat(),
    )
    defaults.update(overrides)
    return Job(**defaults)


def _make_cv_data(**overrides) -> CVData:
    defaults = dict(
        raw_text="Experienced data scientist with Python and ML expertise.",
        skills=["Python", "SQL", "Machine Learning", "TensorFlow"],
        job_titles=["Data Scientist"],
        education=["MSc Computer Science"],
        certifications=["AWS Certified"],
        total_experience_months=60,
        computed_seniority="mid",
    )
    defaults.update(overrides)
    return CVData(**defaults)


class TestEvidenceTagging:

    def test_role_reason_contains_title(self):
        """role_reason mentions the job title being scored."""
        config = _make_config()
        scorer = JobScorer(config)
        job = _make_job(title="Data Scientist")
        bd = scorer.score_detailed(job)
        assert "Data Scientist" in bd.role_reason

    def test_skill_reason_shows_counts(self):
        """skill_reason shows matched and missing counts."""
        config = _make_config()
        scorer = JobScorer(config)
        job = _make_job()
        parsed_jd = parse_jd(job.description, list(config.primary_skills))
        bd = scorer.score_detailed(job, parsed_jd=parsed_jd)
        # Should contain a number for matched count
        assert "matched" in bd.skill_reason
        assert "missing" in bd.skill_reason

    def test_seniority_reason_shows_levels(self):
        """seniority_reason shows JD and user levels."""
        config = _make_config(target_experience_level="mid")
        scorer = JobScorer(config)
        job = _make_job(title="Senior Data Scientist")
        bd = scorer.score_detailed(job)
        assert "JD=" in bd.seniority_reason
        assert "You=" in bd.seniority_reason

    def test_experience_reason_shows_years(self):
        """experience_reason shows JD required years and user's years."""
        config = _make_config()
        scorer = JobScorer(config)
        job = _make_job()
        parsed_jd = parse_jd(job.description)
        cv_data = _make_cv_data(total_experience_months=84)
        bd = scorer.score_detailed(job, parsed_jd=parsed_jd, cv_data=cv_data)
        assert "yr" in bd.experience_reason
        assert "JD needs" in bd.experience_reason

    def test_penalty_reason_explains_negative(self):
        """penalty_reason explains why penalty was applied."""
        config = _make_config(negative_title_keywords=["intern"])
        scorer = JobScorer(config)
        job = _make_job(title="Data Science Intern")
        bd = scorer.score_detailed(job)
        assert "negative keyword" in bd.penalty_reason

    def test_all_reasons_non_empty(self):
        """ALL *_reason fields are non-empty after scoring a job."""
        config = _make_config()
        scorer = JobScorer(config)
        job = _make_job()
        parsed_jd = parse_jd(job.description, list(config.primary_skills))
        cv_data = _make_cv_data()
        bd = scorer.score_detailed(job, parsed_jd=parsed_jd, cv_data=cv_data)

        reason_fields = [
            "role_reason", "skill_reason", "seniority_reason",
            "experience_reason", "credentials_reason", "location_reason",
            "recency_reason", "semantic_reason",
        ]
        for field_name in reason_fields:
            value = getattr(bd, field_name)
            assert value, f"{field_name} is empty"

    def test_evidence_fields_in_breakdown(self):
        """ScoreBreakdown has all expected *_reason + score fields."""
        config = _make_config()
        scorer = JobScorer(config)
        job = _make_job()
        bd = scorer.score_detailed(job)

        # Score dimensions
        assert isinstance(bd.role, int)
        assert isinstance(bd.skill, int)
        assert isinstance(bd.seniority, int)
        assert isinstance(bd.experience, int)
        assert isinstance(bd.credentials, int)
        assert isinstance(bd.location, int)
        assert isinstance(bd.recency, int)
        assert isinstance(bd.semantic, int)
        assert isinstance(bd.penalty, int)
        assert isinstance(bd.total, int)

        # Reason strings exist
        assert hasattr(bd, "role_reason")
        assert hasattr(bd, "skill_reason")
        assert hasattr(bd, "seniority_reason")
        assert hasattr(bd, "experience_reason")
        assert hasattr(bd, "credentials_reason")
        assert hasattr(bd, "location_reason")
        assert hasattr(bd, "recency_reason")
        assert hasattr(bd, "semantic_reason")
        assert hasattr(bd, "penalty_reason")

        # Match lists
        assert isinstance(bd.matched_skills, list)
        assert isinstance(bd.missing_required, list)
        assert isinstance(bd.missing_preferred, list)
        assert isinstance(bd.transferable_skills, list)

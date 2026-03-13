"""Tests for user preferences and profile merging.

Validates that:
- Preferences save/load correctly
- CV + preferences merge properly (preferences widen the net)
- LinkedIn data integrates into the merged profile
- Preference skills become secondary (not primary)
- Profile merging deduplicates correctly
"""

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.preferences import load_preferences, save_preferences, get_empty_preferences
from src.cv_parser import extract_profile, save_profile, load_profile
from src.filters.skill_matcher import (
    reload_profile,
    _load_active_profile,
    _merge_profile_and_preferences,
    score_job,
    get_search_queries,
    get_search_locations,
    get_relevance_keywords,
)
from src.models import Job


@pytest.fixture(autouse=True)
def _isolate_scorer():
    reload_profile()
    yield
    reload_profile()


# ---------------------------------------------------------------------------
# Preferences save / load
# ---------------------------------------------------------------------------

class TestPreferencesStorage:

    def test_save_and_load(self, tmp_path):
        path = tmp_path / "prefs.json"
        prefs = {
            "job_titles": ["AI Platform Engineer", "Cloud ML Engineer"],
            "skills": ["Azure", "GCP", "Terraform"],
            "locations": ["Berlin", "Remote"],
            "about_me": "Passionate about cloud-native ML",
            "projects": ["Built ML pipeline on Azure"],
            "certifications": ["AWS Solutions Architect"],
        }
        save_preferences(prefs, path)
        loaded = load_preferences(path)
        assert loaded is not None
        assert loaded["job_titles"] == ["AI Platform Engineer", "Cloud ML Engineer"]
        assert loaded["skills"] == ["Azure", "GCP", "Terraform"]
        assert "updated_at" in loaded

    def test_load_nonexistent_returns_none(self, tmp_path):
        assert load_preferences(tmp_path / "nope.json") is None

    def test_empty_preferences(self):
        empty = get_empty_preferences()
        assert empty["job_titles"] == []
        assert empty["skills"] == []
        assert empty["about_me"] == ""

    def test_overwrite_preferences(self, tmp_path):
        path = tmp_path / "prefs.json"
        save_preferences({"job_titles": ["Engineer"], "skills": []}, path)
        save_preferences({"job_titles": ["Manager"], "skills": ["SQL"]}, path)
        loaded = load_preferences(path)
        assert loaded["job_titles"] == ["Manager"]
        assert loaded["skills"] == ["SQL"]


# ---------------------------------------------------------------------------
# Profile merging (CV + preferences)
# ---------------------------------------------------------------------------

class TestProfileMerging:

    def test_cv_only(self):
        cv = {
            "job_titles": ["AI Engineer"],
            "primary_skills": ["Python", "PyTorch"],
            "secondary_skills": ["Docker"],
            "tertiary_skills": ["Git"],
            "locations": ["London"],
        }
        merged = _merge_profile_and_preferences(cv, None)
        assert merged["job_titles"] == ["AI Engineer"]
        assert "Python" in merged["primary_skills"]
        assert "Docker" in merged["secondary_skills"]

    def test_preferences_only(self):
        prefs = {
            "job_titles": ["Cloud Engineer"],
            "skills": ["Azure", "Terraform"],
            "locations": ["Berlin"],
            "about_me": "",
            "projects": [],
            "certifications": [],
        }
        merged = _merge_profile_and_preferences(None, prefs)
        assert "Cloud Engineer" in merged["job_titles"]
        assert "Azure" in merged["secondary_skills"]
        assert "Terraform" in merged["secondary_skills"]
        assert "Berlin" in merged["locations"]

    def test_cv_plus_preferences_merges(self):
        cv = {
            "job_titles": ["AI Engineer"],
            "primary_skills": ["Python", "PyTorch"],
            "secondary_skills": ["Docker"],
            "tertiary_skills": ["Git"],
            "locations": ["London"],
        }
        prefs = {
            "job_titles": ["AI Platform Engineer", "Cloud ML Engineer"],
            "skills": ["Azure", "GCP"],
            "locations": ["Remote", "Berlin"],
            "about_me": "",
            "projects": [],
            "certifications": [],
        }
        merged = _merge_profile_and_preferences(cv, prefs)
        # CV titles come first, then preference titles
        assert merged["job_titles"][0] == "AI Engineer"
        assert "AI Platform Engineer" in merged["job_titles"]
        assert "Cloud ML Engineer" in merged["job_titles"]
        # CV primary skills stay primary
        assert "Python" in merged["primary_skills"]
        assert "PyTorch" in merged["primary_skills"]
        # Preference skills become secondary
        assert "Azure" in merged["secondary_skills"]
        assert "GCP" in merged["secondary_skills"]
        # Locations merged
        assert "London" in merged["locations"]
        assert "Remote" in merged["locations"]
        assert "Berlin" in merged["locations"]

    def test_preference_skills_not_promoted_to_primary(self):
        cv = {
            "job_titles": ["Developer"],
            "primary_skills": ["Python"],
            "secondary_skills": [],
            "tertiary_skills": [],
            "locations": [],
        }
        prefs = {
            "job_titles": [],
            "skills": ["React", "TypeScript"],
            "locations": [],
            "about_me": "",
            "projects": [],
            "certifications": [],
        }
        merged = _merge_profile_and_preferences(cv, prefs)
        # Preference skills should NOT appear in primary
        assert "React" not in merged["primary_skills"]
        assert "TypeScript" not in merged["primary_skills"]
        # They should be secondary
        assert "React" in merged["secondary_skills"]
        assert "TypeScript" in merged["secondary_skills"]

    def test_deduplication(self):
        cv = {
            "job_titles": ["AI Engineer"],
            "primary_skills": ["Python"],
            "secondary_skills": ["Docker"],
            "tertiary_skills": [],
            "locations": ["London"],
        }
        prefs = {
            "job_titles": ["AI Engineer"],  # duplicate
            "skills": ["Python", "Docker", "Azure"],  # Python/Docker are dupes
            "locations": ["London", "Remote"],  # London is dupe
            "about_me": "",
            "projects": [],
            "certifications": [],
        }
        merged = _merge_profile_and_preferences(cv, prefs)
        # No duplicate titles
        assert merged["job_titles"].count("AI Engineer") == 1
        # Python stays primary, not also secondary
        assert "Python" in merged["primary_skills"]
        assert "Python" not in merged["secondary_skills"]
        # Docker stays secondary (from CV), not duplicated
        secondary_lower = [s.lower() for s in merged["secondary_skills"]]
        assert secondary_lower.count("docker") == 1
        # Azure added as new secondary
        assert "Azure" in merged["secondary_skills"]
        # London not duplicated
        assert merged["locations"].count("London") == 1

    def test_certifications_mined_for_skills(self):
        prefs = {
            "job_titles": [],
            "skills": [],
            "locations": [],
            "about_me": "",
            "projects": [],
            "certifications": ["AWS Solutions Architect Professional"],
        }
        merged = _merge_profile_and_preferences(None, prefs)
        # "AWS" should be extracted from the certification text
        all_skills = merged["primary_skills"] + merged["secondary_skills"] + merged["tertiary_skills"]
        assert "AWS" in all_skills

    def test_projects_mined_for_skills(self):
        prefs = {
            "job_titles": [],
            "skills": [],
            "locations": [],
            "about_me": "",
            "projects": ["Built a React dashboard with TypeScript and PostgreSQL"],
            "certifications": [],
        }
        merged = _merge_profile_and_preferences(None, prefs)
        all_skills = merged["primary_skills"] + merged["secondary_skills"] + merged["tertiary_skills"]
        assert "React" in all_skills
        assert "TypeScript" in all_skills
        assert "PostgreSQL" in all_skills


# ---------------------------------------------------------------------------
# LinkedIn data in preferences
# ---------------------------------------------------------------------------

class TestLinkedInMerge:

    def test_linkedin_titles_added(self):
        cv = {
            "job_titles": ["AI Engineer"],
            "primary_skills": ["Python"],
            "secondary_skills": [],
            "tertiary_skills": [],
            "locations": ["London"],
        }
        prefs = {
            "job_titles": [],
            "skills": [],
            "locations": [],
            "about_me": "",
            "projects": [],
            "certifications": [],
            "linkedin": {
                "job_titles": ["Machine Learning Engineer", "Data Scientist"],
                "skills": ["Scikit-learn", "Pandas"],
                "locations": ["San Francisco"],
                "certifications": [],
                "projects": [],
                "companies": ["Google", "Meta"],
            },
        }
        merged = _merge_profile_and_preferences(cv, prefs)
        assert "Machine Learning Engineer" in merged["job_titles"]
        assert "Data Scientist" in merged["job_titles"]
        assert "Scikit-learn" in merged["secondary_skills"]
        assert "Pandas" in merged["secondary_skills"]
        assert "San Francisco" in merged["locations"]

    def test_linkedin_skills_are_secondary(self):
        prefs = {
            "job_titles": [],
            "skills": [],
            "locations": [],
            "about_me": "",
            "projects": [],
            "certifications": [],
            "linkedin": {
                "job_titles": [],
                "skills": ["Spark", "Hadoop", "Kafka"],
                "locations": [],
                "certifications": [],
                "projects": [],
            },
        }
        merged = _merge_profile_and_preferences(None, prefs)
        # LinkedIn skills should be secondary, not primary
        assert "Spark" in merged["secondary_skills"]
        assert "Hadoop" in merged["secondary_skills"]
        assert "Kafka" in merged["secondary_skills"]
        assert "Spark" not in merged["primary_skills"]


# ---------------------------------------------------------------------------
# Scoring with merged profile
# ---------------------------------------------------------------------------

class TestScoringWithPreferences:

    def test_preferences_widen_search(self, tmp_path, monkeypatch):
        """User's CV says AWS, preferences add Azure — Azure job should score higher."""
        import src.cv_parser as cv_mod
        import src.preferences as pref_mod
        import src.filters.skill_matcher as sm

        cv_path = tmp_path / "cv_profile.json"
        pref_path = tmp_path / "user_preferences.json"
        monkeypatch.setattr(cv_mod, "CV_PROFILE_PATH", cv_path)
        monkeypatch.setattr(pref_mod, "USER_PREFERENCES_PATH", pref_path)

        # CV: only AWS
        cv = extract_profile("AI Engineer with Python and AWS experience. London based.")
        cv["source_file"] = "test.pdf"
        save_profile(cv, cv_path)

        sm.reload_profile()
        profile_without_prefs = sm._load_active_profile()

        # Now add preferences: Azure, GCP
        prefs = {
            "job_titles": ["Cloud AI Engineer"],
            "skills": ["Azure", "GCP"],
            "locations": ["Remote"],
            "about_me": "",
            "projects": [],
            "certifications": [],
        }
        save_preferences(prefs, pref_path)
        sm.reload_profile()
        profile_with_prefs = sm._load_active_profile()

        # Azure job
        azure_job = Job(
            title="Cloud AI Engineer",
            company="Test",
            apply_url="https://example.com",
            source="test",
            date_found=datetime.now(timezone.utc).isoformat(),
            location="Remote",
            description="Looking for Azure cloud AI engineer with GCP experience",
        )

        score_without = score_job(azure_job, profile=profile_without_prefs)
        score_with = score_job(azure_job, profile=profile_with_prefs)
        # With preferences, the Azure/GCP job should score higher
        assert score_with > score_without

    def test_relevance_keywords_include_preference_skills(self, tmp_path, monkeypatch):
        import src.cv_parser as cv_mod
        import src.preferences as pref_mod
        import src.filters.skill_matcher as sm

        cv_path = tmp_path / "cv_profile.json"
        pref_path = tmp_path / "user_preferences.json"
        monkeypatch.setattr(cv_mod, "CV_PROFILE_PATH", cv_path)
        monkeypatch.setattr(pref_mod, "USER_PREFERENCES_PATH", pref_path)

        cv = extract_profile("Python developer in London.")
        save_profile(cv, cv_path)

        prefs = {
            "job_titles": ["Platform Engineer"],
            "skills": ["Terraform", "Pulumi"],
            "locations": [],
            "about_me": "",
            "projects": [],
            "certifications": [],
        }
        save_preferences(prefs, pref_path)
        sm.reload_profile()

        keywords = sm.get_relevance_keywords()
        assert "terraform" in keywords
        assert "pulumi" in keywords
        assert "platform" in keywords  # from job title

    def test_search_queries_include_preference_titles(self, tmp_path, monkeypatch):
        import src.cv_parser as cv_mod
        import src.preferences as pref_mod
        import src.filters.skill_matcher as sm

        cv_path = tmp_path / "cv_profile.json"
        pref_path = tmp_path / "user_preferences.json"
        monkeypatch.setattr(cv_mod, "CV_PROFILE_PATH", cv_path)
        monkeypatch.setattr(pref_mod, "USER_PREFERENCES_PATH", pref_path)

        cv = extract_profile("AI Engineer at a startup in London.")
        save_profile(cv, cv_path)

        prefs = {
            "job_titles": ["ML Platform Engineer", "Cloud AI Engineer"],
            "skills": [],
            "locations": [],
            "about_me": "",
            "projects": [],
            "certifications": [],
        }
        save_preferences(prefs, pref_path)
        sm.reload_profile()

        queries = sm.get_search_queries(limit=10)
        assert "AI Engineer" in queries
        assert "ML Platform Engineer" in queries
        assert "Cloud AI Engineer" in queries

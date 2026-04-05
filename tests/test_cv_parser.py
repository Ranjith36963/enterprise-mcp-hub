"""Tests for CV parser entry-point functions.

Covers: parse_cv() for PDF/DOCX files, parse_cv_from_bytes() for
dashboard uploads, text extraction, and section detection.
"""

import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from src.profile.cv_parser import (
    parse_cv,
    parse_cv_from_bytes,
    extract_text,
    _find_sections,
    _extract_known_skills,
    _extract_known_titles,
)
from src.profile.models import CVData


# ── Helpers ──

SAMPLE_CV_TEXT = """
JOHN DOE
Senior Software Engineer

SUMMARY
Experienced software engineer with 8 years of Python, Java, and cloud expertise.

SKILLS
Python, Java, TypeScript, React, Docker, Kubernetes, AWS, PostgreSQL, Redis

EXPERIENCE
Senior Software Engineer at TechCorp (2020-Present)
- Led backend team building microservices in Python and Java
- Deployed services on AWS using Docker and Kubernetes

Software Engineer at StartupCo (2016-2020)
- Developed REST APIs using FastAPI and PostgreSQL
- Implemented CI/CD pipelines with Jenkins and GitHub Actions

EDUCATION
MSc Computer Science — Imperial College London, 2016
BSc Mathematics — University of Manchester, 2014

CERTIFICATIONS
AWS Solutions Architect
Certified Kubernetes Administrator
"""


class TestParseCv:

    def test_parse_cv_from_text_file(self, tmp_path):
        """parse_cv reads a .txt file and extracts skills/titles."""
        cv_file = tmp_path / "test_cv.txt"
        cv_file.write_text(SAMPLE_CV_TEXT, encoding="utf-8")

        # patch extract_text to return our sample text (avoids PDF/DOCX deps)
        with patch("src.profile.cv_parser.extract_text", return_value=SAMPLE_CV_TEXT):
            cv = parse_cv(str(cv_file))

        assert isinstance(cv, CVData)
        assert cv.raw_text == SAMPLE_CV_TEXT
        assert len(cv.skills) > 0, "Should extract at least some skills"

    def test_parse_cv_empty_file_returns_empty(self, tmp_path):
        """parse_cv on empty file returns empty CVData."""
        cv_file = tmp_path / "empty.txt"
        cv_file.write_text("", encoding="utf-8")

        with patch("src.profile.cv_parser.extract_text", return_value=""):
            cv = parse_cv(str(cv_file))

        assert cv.raw_text == ""
        assert cv.skills == []

    def test_parse_cv_from_bytes(self):
        """parse_cv_from_bytes creates temp file, parses, then cleans up."""
        content = SAMPLE_CV_TEXT.encode("utf-8")
        # Mock extract_text to avoid needing actual PDF/DOCX parsing
        with patch("src.profile.cv_parser.extract_text", return_value=SAMPLE_CV_TEXT):
            cv = parse_cv_from_bytes(content, "resume.pdf")

        assert isinstance(cv, CVData)
        assert len(cv.skills) > 0

    def test_extract_known_skills(self):
        """_extract_known_skills finds known tech terms in text."""
        skills = _extract_known_skills(SAMPLE_CV_TEXT)
        skills_lower = [s.lower() for s in skills]
        assert "python" in skills_lower
        assert "docker" in skills_lower
        assert "aws" in skills_lower

    def test_extract_known_titles(self):
        """_extract_known_titles finds job title patterns."""
        titles = _extract_known_titles(SAMPLE_CV_TEXT)
        titles_lower = [t.lower() for t in titles]
        assert any("software engineer" in t for t in titles_lower)

    def test_find_sections_detects_headings(self):
        """_find_sections identifies CV sections like SKILLS, EXPERIENCE, EDUCATION."""
        sections = _find_sections(SAMPLE_CV_TEXT)
        # Should detect at least some sections
        found = set(sections.keys())
        assert len(found) >= 2, f"Expected ≥2 sections, found: {found}"

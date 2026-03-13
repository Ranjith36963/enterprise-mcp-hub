"""Tests for LinkedIn data export import."""

import csv
import io
import zipfile
from pathlib import Path

import pytest

from src.linkedin_import import parse_linkedin_zip


@pytest.fixture
def linkedin_zip(tmp_path) -> Path:
    """Create a mock LinkedIn data export ZIP."""
    zip_path = tmp_path / "linkedin_export.zip"

    with zipfile.ZipFile(zip_path, "w") as zf:
        # Profile.csv
        profile_csv = io.StringIO()
        writer = csv.DictWriter(profile_csv, fieldnames=["First Name", "Last Name", "Headline", "Summary", "Geo Location"])
        writer.writeheader()
        writer.writerow({
            "First Name": "Jane",
            "Last Name": "Doe",
            "Headline": "Senior AI Engineer",
            "Summary": "Passionate ML engineer with 8 years in NLP and computer vision.",
            "Geo Location": "London, United Kingdom",
        })
        zf.writestr("Profile.csv", profile_csv.getvalue())

        # Positions.csv
        pos_csv = io.StringIO()
        writer = csv.DictWriter(pos_csv, fieldnames=["Company Name", "Title", "Description", "Started On", "Finished On"])
        writer.writeheader()
        writer.writerow({
            "Company Name": "DeepMind",
            "Title": "Research Engineer",
            "Description": "Worked on NLP models",
            "Started On": "Jan 2020",
            "Finished On": "",
        })
        writer.writerow({
            "Company Name": "Google",
            "Title": "Software Engineer",
            "Description": "Backend systems",
            "Started On": "Mar 2017",
            "Finished On": "Dec 2019",
        })
        zf.writestr("Positions.csv", pos_csv.getvalue())

        # Skills.csv
        skills_csv = io.StringIO()
        writer = csv.DictWriter(skills_csv, fieldnames=["Name"])
        writer.writeheader()
        for skill in ["Python", "PyTorch", "TensorFlow", "Kubernetes", "NLP"]:
            writer.writerow({"Name": skill})
        zf.writestr("Skills.csv", skills_csv.getvalue())

        # Certifications.csv
        certs_csv = io.StringIO()
        writer = csv.DictWriter(certs_csv, fieldnames=["Name", "Authority", "License Number"])
        writer.writeheader()
        writer.writerow({
            "Name": "AWS Machine Learning Specialty",
            "Authority": "Amazon Web Services",
            "License Number": "ABC123",
        })
        zf.writestr("Certifications.csv", certs_csv.getvalue())

        # Education.csv
        edu_csv = io.StringIO()
        writer = csv.DictWriter(edu_csv, fieldnames=["School Name", "Degree Name", "Notes"])
        writer.writeheader()
        writer.writerow({
            "School Name": "Imperial College London",
            "Degree Name": "MSc Machine Learning",
            "Notes": "",
        })
        zf.writestr("Education.csv", edu_csv.getvalue())

        # Projects.csv
        proj_csv = io.StringIO()
        writer = csv.DictWriter(proj_csv, fieldnames=["Title", "Description"])
        writer.writeheader()
        writer.writerow({
            "Title": "NLP Pipeline",
            "Description": "Built an end-to-end NLP pipeline using spaCy and Hugging Face",
        })
        zf.writestr("Projects.csv", proj_csv.getvalue())

    return zip_path


class TestLinkedInImport:

    def test_extracts_job_titles(self, linkedin_zip):
        data = parse_linkedin_zip(linkedin_zip)
        assert "Senior AI Engineer" in data["job_titles"]  # from headline
        assert "Research Engineer" in data["job_titles"]
        assert "Software Engineer" in data["job_titles"]

    def test_extracts_skills(self, linkedin_zip):
        data = parse_linkedin_zip(linkedin_zip)
        assert "Python" in data["skills"]
        assert "PyTorch" in data["skills"]
        assert "TensorFlow" in data["skills"]
        assert "Kubernetes" in data["skills"]
        assert "NLP" in data["skills"]

    def test_extracts_locations(self, linkedin_zip):
        data = parse_linkedin_zip(linkedin_zip)
        assert "London, United Kingdom" in data["locations"]

    def test_extracts_certifications(self, linkedin_zip):
        data = parse_linkedin_zip(linkedin_zip)
        assert len(data["certifications"]) == 1
        assert "AWS Machine Learning Specialty" in data["certifications"][0]
        assert "Amazon Web Services" in data["certifications"][0]

    def test_extracts_companies(self, linkedin_zip):
        data = parse_linkedin_zip(linkedin_zip)
        assert "DeepMind" in data["companies"]
        assert "Google" in data["companies"]

    def test_extracts_education(self, linkedin_zip):
        data = parse_linkedin_zip(linkedin_zip)
        assert len(data["education"]) == 1
        assert "Imperial College London" in data["education"][0]
        assert "MSc Machine Learning" in data["education"][0]

    def test_extracts_projects(self, linkedin_zip):
        data = parse_linkedin_zip(linkedin_zip)
        assert len(data["projects"]) == 1
        assert "NLP Pipeline" in data["projects"][0]

    def test_extracts_about_me(self, linkedin_zip):
        data = parse_linkedin_zip(linkedin_zip)
        assert "ML engineer" in data["about_me"]

    def test_deduplicates_titles(self, tmp_path):
        """Same title in multiple positions should appear only once."""
        zip_path = tmp_path / "test.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            pos_csv = io.StringIO()
            writer = csv.DictWriter(pos_csv, fieldnames=["Company Name", "Title"])
            writer.writeheader()
            writer.writerow({"Company Name": "A", "Title": "Software Engineer"})
            writer.writerow({"Company Name": "B", "Title": "Software Engineer"})
            zf.writestr("Positions.csv", pos_csv.getvalue())
        data = parse_linkedin_zip(zip_path)
        assert data["job_titles"].count("Software Engineer") == 1

    def test_invalid_zip_raises(self, tmp_path):
        bad = tmp_path / "bad.zip"
        bad.write_text("not a zip")
        with pytest.raises(ValueError, match="Not a valid ZIP"):
            parse_linkedin_zip(bad)

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            parse_linkedin_zip(tmp_path / "nope.zip")

    def test_empty_zip(self, tmp_path):
        zip_path = tmp_path / "empty.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            pass  # empty ZIP
        data = parse_linkedin_zip(zip_path)
        assert data["job_titles"] == []
        assert data["skills"] == []

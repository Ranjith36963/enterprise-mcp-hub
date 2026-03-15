"""LinkedIn Data Import — the third input layer.

LinkedIn allows users to download their data as a ZIP archive via:
Settings > Data Privacy > Get a copy of your data.

The ZIP contains CSV files with structured professional data:
- Profile.csv — headline, summary, location
- Positions.csv — work history (title, company, description)
- Skills.csv — endorsed skills
- Certifications.csv — certifications with issuing org
- Education.csv — degrees and institutions
- Projects.csv — project names and descriptions

This module parses the ZIP and extracts structured data that supplements
the CV profile and user preferences.
"""

import csv
import io
import logging
import re
import zipfile
from collections import Counter
from pathlib import Path

from src.config.keywords import KNOWN_SKILLS, KNOWN_TITLE_PATTERNS, KNOWN_LOCATIONS

logger = logging.getLogger("job360.linkedin_import")


def _read_csv_from_zip(zf: zipfile.ZipFile, filename: str) -> list[dict]:
    """Read a CSV file from the ZIP, trying common path variations."""
    candidates = [
        filename,
        f"Basic_LinkedInDataExport_03-13-2026/{filename}",
    ]
    # Also try any path ending with the filename
    for name in zf.namelist():
        if name.endswith(filename) or name.endswith(f"/{filename}"):
            candidates.insert(0, name)

    for candidate in candidates:
        if candidate in zf.namelist():
            with zf.open(candidate) as f:
                text = f.read().decode("utf-8", errors="replace")
                reader = csv.DictReader(io.StringIO(text))
                return list(reader)
    return []


def parse_linkedin_zip(zip_path: str | Path) -> dict:
    """Parse a LinkedIn data export ZIP and return structured profile data.

    Returns a dict with:
        job_titles: list[str]   — from Positions.csv + Profile.csv headline
        skills: list[str]       — from Skills.csv
        locations: list[str]    — from Profile.csv
        certifications: list[str] — from Certifications.csv
        projects: list[str]     — from Projects.csv
        about_me: str           — from Profile.csv summary
        companies: list[str]    — from Positions.csv
        education: list[str]    — from Education.csv
    """
    path = Path(zip_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {zip_path}")
    if not zipfile.is_zipfile(path):
        raise ValueError(f"Not a valid ZIP file: {zip_path}")

    result = {
        "job_titles": [],
        "skills": [],
        "locations": [],
        "certifications": [],
        "projects": [],
        "about_me": "",
        "companies": [],
        "education": [],
        "source": "linkedin_export",
    }

    with zipfile.ZipFile(path, "r") as zf:
        # --- Profile ---
        profiles = _read_csv_from_zip(zf, "Profile.csv")
        for row in profiles:
            headline = row.get("Headline", "").strip()
            if headline:
                result["job_titles"].append(headline)
            summary = row.get("Summary", "").strip()
            if summary:
                result["about_me"] = summary
            geo = row.get("Geo Location", "").strip()
            if geo:
                result["locations"].append(geo)

        # --- Positions (work history) ---
        positions = _read_csv_from_zip(zf, "Positions.csv")
        seen_titles = set()
        for row in positions:
            title = row.get("Title", "").strip()
            if title and title.lower() not in seen_titles:
                seen_titles.add(title.lower())
                result["job_titles"].append(title)
            company = row.get("Company Name", "").strip()
            if company and company not in result["companies"]:
                result["companies"].append(company)

        # --- Skills ---
        skills = _read_csv_from_zip(zf, "Skills.csv")
        for row in skills:
            skill = row.get("Name", "").strip()
            if skill:
                result["skills"].append(skill)

        # --- Certifications ---
        certs = _read_csv_from_zip(zf, "Certifications.csv")
        for row in certs:
            name = row.get("Name", "").strip()
            org = row.get("Authority", "").strip()
            if name:
                cert_str = f"{name} ({org})" if org else name
                result["certifications"].append(cert_str)

        # --- Education ---
        education = _read_csv_from_zip(zf, "Education.csv")
        for row in education:
            school = row.get("School Name", "").strip()
            degree = row.get("Degree Name", "").strip()
            field = row.get("Notes", "").strip()
            if school:
                edu_str = f"{degree} — {school}" if degree else school
                if field:
                    edu_str += f" ({field})"
                result["education"].append(edu_str)

        # --- Projects ---
        projects = _read_csv_from_zip(zf, "Projects.csv")
        for row in projects:
            title = row.get("Title", "").strip()
            desc = row.get("Description", "").strip()
            if title:
                proj_str = f"{title}: {desc}" if desc else title
                result["projects"].append(proj_str)

    total = sum(len(v) if isinstance(v, list) else (1 if v else 0) for v in result.values())
    logger.info(
        "LinkedIn import: %d titles, %d skills, %d certs, %d projects, %d companies",
        len(result["job_titles"]),
        len(result["skills"]),
        len(result["certifications"]),
        len(result["projects"]),
        len(result["companies"]),
    )
    return result

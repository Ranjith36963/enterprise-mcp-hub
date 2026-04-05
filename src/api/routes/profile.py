"""Profile management endpoints — CV upload, preferences, LinkedIn, GitHub."""

import json
import logging
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from src.api.deps import get_profile
from src.api.schemas import ProfileResponse, ProfileSummary
from src.profile.cv_parser import parse_cv, parse_cv_from_bytes
from src.profile.preferences import validate_preferences, merge_cv_and_preferences
from src.profile.storage import save_profile, load_profile
from src.profile.models import CVData, UserPreferences, UserProfile

logger = logging.getLogger("job360.api.profile")

router = APIRouter()


def _build_summary(profile: UserProfile) -> ProfileSummary:
    """Build a profile summary from a UserProfile."""
    cv = profile.cv_data
    return ProfileSummary(
        is_complete=profile.is_complete,
        job_titles=cv.job_titles or [],
        skills_count=len(cv.skills or []),
        cv_length=len(cv.raw_text or ""),
        has_linkedin=bool(cv.linkedin_skills),
        has_github=bool(cv.github_languages),
        education=cv.education or [],
        experience_level=cv.computed_seniority or "",
    )


@router.get("/api/profile", response_model=ProfileResponse)
async def get_profile_endpoint():
    profile = load_profile()
    if not profile:
        raise HTTPException(404, "No profile found. Upload a CV first.")
    return ProfileResponse(
        summary=_build_summary(profile),
        preferences=profile.preferences.__dict__ if profile.preferences else {},
    )


@router.post("/api/profile", response_model=ProfileResponse)
async def update_profile(
    cv: UploadFile | None = File(None),
    preferences: str = Form("{}"),
):
    """Upload CV and/or update preferences. CV accepts PDF or DOCX."""
    # Load existing profile or start fresh
    profile = load_profile() or UserProfile()

    # Parse CV if uploaded
    if cv:
        if not cv.filename:
            raise HTTPException(400, "No filename provided")
        ext = Path(cv.filename).suffix.lower()
        if ext not in (".pdf", ".docx"):
            raise HTTPException(400, f"Unsupported file type: {ext}. Use PDF or DOCX.")
        content = await cv.read()
        try:
            cv_data = parse_cv_from_bytes(content, cv.filename)
            profile.cv_data = cv_data
            logger.info(f"CV parsed: {len(cv_data.skills)} skills, {len(cv_data.job_titles)} titles")
        except (ValueError, OSError) as e:
            raise HTTPException(400, f"CV parsing failed: {e}")

    # Parse preferences if provided
    try:
        prefs_dict = json.loads(preferences)
    except json.JSONDecodeError:
        raise HTTPException(400, "Invalid preferences JSON")

    if prefs_dict:
        prefs = validate_preferences(prefs_dict)
        if profile.cv_data.skills or profile.cv_data.job_titles:
            prefs = merge_cv_and_preferences(
                profile.cv_data.skills, profile.cv_data.job_titles, prefs
            )
        profile.preferences = prefs

    # Save
    save_profile(profile)
    logger.info("Profile saved")

    return ProfileResponse(
        summary=_build_summary(profile),
        preferences=profile.preferences.__dict__,
    )


@router.post("/api/profile/linkedin")
async def upload_linkedin(file: UploadFile = File(...)):
    """Upload LinkedIn data export ZIP to enrich profile."""
    profile = load_profile()
    if not profile:
        raise HTTPException(400, "Upload a CV first before adding LinkedIn data")

    content = await file.read()
    try:
        # Write to temp file for ZIP parsing
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
            tmp.write(content)
            tmp_path = tmp.name

        from src.profile.linkedin_parser import parse_linkedin_zip
        linkedin_data = parse_linkedin_zip(tmp_path)

        # Merge into existing CV data
        if linkedin_data.get("skills"):
            existing = set(profile.cv_data.linkedin_skills or [])
            existing.update(linkedin_data["skills"])
            profile.cv_data.linkedin_skills = sorted(existing)
        if linkedin_data.get("positions"):
            profile.cv_data.linkedin_positions = linkedin_data["positions"]
        if linkedin_data.get("industry"):
            profile.cv_data.linkedin_industry = linkedin_data["industry"]

        save_profile(profile)
        return {"ok": True, "merged": {k: len(v) if isinstance(v, list) else v for k, v in linkedin_data.items()}}
    except (ValueError, KeyError, OSError) as e:
        raise HTTPException(400, f"LinkedIn ZIP parsing failed: {e}")
    finally:
        Path(tmp_path).unlink(missing_ok=True)


@router.post("/api/profile/github")
async def enrich_github(username: str = Form(...)):
    """Enrich profile with GitHub public repo data."""
    profile = load_profile()
    if not profile:
        raise HTTPException(400, "Upload a CV first before adding GitHub data")

    try:
        from src.profile.github_enricher import enrich_from_github
        import asyncio
        github_data = await enrich_from_github(username)

        if github_data.get("languages"):
            profile.cv_data.github_languages = github_data["languages"]
        if github_data.get("topics"):
            profile.cv_data.github_topics = github_data["topics"]
        if github_data.get("skills_inferred"):
            profile.cv_data.github_skills_inferred = github_data["skills_inferred"]

        save_profile(profile)
        return {"ok": True, "merged": {k: len(v) if isinstance(v, list) else v for k, v in github_data.items()}}
    except (ValueError, KeyError, OSError) as e:
        raise HTTPException(400, f"GitHub enrichment failed: {e}")

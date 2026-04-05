"""Pydantic request/response models for Job360 API."""

from __future__ import annotations

from pydantic import BaseModel


class JobResponse(BaseModel):
    id: int
    title: str
    company: str
    location: str
    salary: str | None = None
    match_score: int
    source: str
    date_found: str
    apply_url: str
    visa_flag: bool = False
    job_type: str = ""
    experience_level: str = ""
    # 8D score breakdown
    role: int = 0
    skill: int = 0
    seniority: int = 0
    experience: int = 0
    credentials: int = 0
    location_score: int = 0
    recency: int = 0
    semantic: int = 0
    penalty: int = 0
    # Skill analysis
    matched_skills: list[str] = []
    missing_required: list[str] = []
    transferable_skills: list[str] = []
    # User action
    action: str | None = None
    bucket: str = ""


class JobListResponse(BaseModel):
    jobs: list[JobResponse]
    total: int
    filters_applied: dict = {}


class ProfileSummary(BaseModel):
    is_complete: bool
    job_titles: list[str] = []
    skills_count: int = 0
    cv_length: int = 0
    has_linkedin: bool = False
    has_github: bool = False
    education: list[str] = []
    experience_level: str = ""


class ProfileResponse(BaseModel):
    summary: ProfileSummary
    preferences: dict = {}


class PreferencesRequest(BaseModel):
    target_job_titles: list[str] = []
    additional_skills: list[str] = []
    excluded_skills: list[str] = []
    preferred_locations: list[str] = []
    industries: list[str] = []
    salary_min: float | None = None
    salary_max: float | None = None
    work_arrangement: str = ""
    experience_level: str = ""
    negative_keywords: list[str] = []
    about_me: str = ""
    excluded_companies: list[str] = []


class SearchStartResponse(BaseModel):
    run_id: str
    status: str = "running"


class SearchStatusResponse(BaseModel):
    run_id: str
    status: str
    progress: str = ""
    result: dict | None = None


class ActionRequest(BaseModel):
    action: str  # "liked", "applied", "not_interested"
    notes: str = ""


class PipelineAdvanceRequest(BaseModel):
    stage: str  # PipelineStage value


class StatusResponse(BaseModel):
    jobs_total: int
    last_run: dict | None = None
    sources_active: int = 0
    sources_total: int = 0
    profile_exists: bool = False


class SourceInfo(BaseModel):
    name: str
    type: str = ""
    health: dict = {}


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = ""

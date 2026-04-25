"""Pydantic models for Job360 FastAPI backend."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    version: str


class SourceInfo(BaseModel):
    name: str
    type: str
    health: dict


class SourcesResponse(BaseModel):
    sources: list[SourceInfo]


class StatusResponse(BaseModel):
    jobs_total: int
    last_run: Optional[dict]
    sources_active: int
    sources_total: int
    profile_exists: bool


class JobResponse(BaseModel):
    id: int
    title: str
    company: str
    location: str
    salary: Optional[str]
    match_score: int
    source: str
    date_found: str
    apply_url: str
    visa_flag: bool
    job_type: str = ""
    experience_level: str = ""
    # Score-dim breakdown (Pillar 2 Batch 2.9). Step-1.5 S1.1 wired the
    # 9 columns end-to-end (migration 0011 → Job dataclass → main.py
    # capture → insert_job → _row_to_job_response). `role`/`skill`/
    # `location_score`/`recency`/`seniority_score` carry their respective
    # ScoreBreakdown component each run; the remaining four
    # (experience/credentials/semantic/penalty) persist as 0 until the
    # engine starts producing those signals — see CLAUDE.md rule #21.
    role: int = 0
    skill: int = 0
    seniority_score: int = 0
    experience: int = 0
    credentials: int = 0
    location_score: int = 0
    recency: int = 0
    semantic: int = 0
    penalty: int = 0
    matched_skills: list[str] = []
    missing_required: list[str] = []
    transferable_skills: list[str] = []
    action: Optional[str] = None
    bucket: str = ""
    # Step-1 B6 — date-model fields (Pillar 3 Batch 1). Persisted on the
    # `jobs` table; `posted_at` is None when no trustworthy source field
    # was found, `staleness_state` flips to 'stale' / 'expired' as the
    # ghost detector runs. Frontend lib/types.ts must mirror these.
    posted_at: Optional[str] = None
    first_seen_at: Optional[str] = None
    last_seen_at: Optional[str] = None
    date_confidence: Optional[str] = None
    staleness_state: Optional[str] = None
    # Step-1 B6 — enrichment fields (Pillar 2 Batch 2.5 subset). Sourced
    # from the `job_enrichment` row via a LEFT JOIN — None when no row
    # exists. Mirrors a 13-of-18 user-facing slice of `JobEnrichment`.
    title_canonical: Optional[str] = None
    seniority: Optional[str] = None
    employment_type: Optional[str] = None
    workplace_type: Optional[str] = None
    visa_sponsorship: Optional[bool] = None
    salary_min_gbp: Optional[int] = None
    salary_max_gbp: Optional[int] = None
    salary_period: Optional[str] = None
    salary_currency_original: Optional[str] = None
    required_skills: Optional[list[str]] = None
    nice_to_have_skills: Optional[list[str]] = None
    industry: Optional[str] = None
    years_experience_min: Optional[int] = None


class JobListResponse(BaseModel):
    jobs: list[JobResponse]
    total: int
    filters_applied: dict


class ActionRequest(BaseModel):
    action: str
    notes: str = ""


class ActionResponse(BaseModel):
    ok: bool
    job_id: int
    action: str


class ActionsListResponse(BaseModel):
    actions: list[ActionResponse]


class ProfileSummary(BaseModel):
    is_complete: bool
    job_titles: list[str]
    skills_count: int
    cv_length: int
    has_linkedin: bool
    has_github: bool
    education: list[str]
    experience_level: str


class CVDetail(BaseModel):
    """Full extracted CV data for transparent display."""

    raw_text: str = ""
    skills: list[str] = []
    job_titles: list[str] = []
    companies: list[str] = []
    education: list[str] = []
    certifications: list[str] = []
    summary_text: str = ""
    experience_text: str = ""
    # Display-only fields (NOT used in scoring)
    name: str = ""
    headline: str = ""
    location: str = ""
    achievements: list[str] = []
    # Aggregated highlights for the CV viewer — merges skills + titles +
    # companies + achievements + name/headline/location for in-text highlighting
    highlights: list[str] = []


class ProfileResponse(BaseModel):
    summary: ProfileSummary
    preferences: dict
    cv_detail: CVDetail | None = None
    # Step-1.5 S1.5-F — evidence-based skill tiering surfaced via
    # ``services.profile.skill_tiering.tier_skills_by_evidence``. Maps
    # tier name → ordered list of skill names. Empty dict when no profile
    # is loaded (or the profile has no skills yet).
    skill_tiers: dict[str, list[str]] = {}
    # Step-1.5 S1.5-D/E — ESCO concept URIs per skill (canonical_label →
    # esco_uri). Mirrors `CVData.cv_skills_esco`. Empty when SEMANTIC is
    # off or the index is missing — gracefully degrades.
    skill_esco: dict[str, str] = {}


class LinkedInResponse(BaseModel):
    ok: bool
    merged: bool


class GitHubResponse(BaseModel):
    ok: bool
    merged: bool


class SearchStartResponse(BaseModel):
    run_id: str
    status: str


class SearchStatusResponse(BaseModel):
    run_id: str
    status: str
    progress: str
    result: Optional[dict] = None


class PipelineApplication(BaseModel):
    job_id: int
    stage: str
    created_at: str
    updated_at: str
    notes: str = ""
    title: str = ""
    company: str = ""


class PipelineListResponse(BaseModel):
    applications: list[PipelineApplication]


class PipelineAdvanceRequest(BaseModel):
    stage: str


class PipelineRemindersResponse(BaseModel):
    reminders: list[PipelineApplication]

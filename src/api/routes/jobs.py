"""Job listing and detail endpoints."""

import json
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse

from src.api.deps import get_db
from src.api.schemas import JobResponse, JobListResponse
from src.storage.database import JobDatabase
from src.config.settings import DB_PATH, MIN_MATCH_SCORE

logger = logging.getLogger("job360.api.jobs")

router = APIRouter()


def _parse_match_data(match_data_str: str) -> dict:
    """Parse match_data JSON string into dict."""
    if not match_data_str:
        return {}
    try:
        return json.loads(match_data_str)
    except (json.JSONDecodeError, TypeError):
        return {}


def _compute_bucket(date_found: str) -> str:
    """Compute time bucket for a job's date_found."""
    if not date_found:
        return "7d+"
    try:
        posted = datetime.fromisoformat(date_found)
        if posted.tzinfo is None:
            posted = posted.replace(tzinfo=timezone.utc)
        hours = (datetime.now(timezone.utc) - posted).total_seconds() / 3600
        if hours <= 24:
            return "24h"
        if hours <= 48:
            return "48h"
        if hours <= 72:
            return "3d"
        if hours <= 120:
            return "5d"
        if hours <= 168:
            return "7d"
        return "7d+"
    except (ValueError, TypeError):
        return "7d+"


def _format_salary(job: dict) -> str | None:
    """Format salary range."""
    s_min = job.get("salary_min")
    s_max = job.get("salary_max")
    if s_min and s_max:
        return f"{int(s_min):,}-{int(s_max):,}"
    if s_min:
        return f"{int(s_min):,}+"
    if s_max:
        return f"up to {int(s_max):,}"
    return None


def _job_to_response(job: dict, action: str | None = None) -> JobResponse:
    """Convert a DB job dict to a JobResponse."""
    md = _parse_match_data(job.get("match_data", ""))
    return JobResponse(
        id=job["id"],
        title=job.get("title", ""),
        company=job.get("company", ""),
        location=job.get("location", ""),
        salary=_format_salary(job),
        match_score=job.get("match_score", 0),
        source=job.get("source", ""),
        date_found=job.get("date_found", ""),
        apply_url=job.get("apply_url", ""),
        visa_flag=bool(job.get("visa_flag")),
        job_type=job.get("job_type", ""),
        experience_level=job.get("experience_level", ""),
        role=md.get("role", 0),
        skill=md.get("skill", 0),
        seniority=md.get("seniority", 0),
        experience=md.get("experience", 0),
        credentials=md.get("credentials", 0),
        location_score=md.get("location", 0),
        recency=md.get("recency", 0),
        semantic=md.get("semantic", 0),
        penalty=md.get("penalty", 0),
        matched_skills=md.get("matched", []),
        missing_required=md.get("missing_required", []),
        transferable_skills=md.get("transferable", []),
        action=action,
        bucket=_compute_bucket(job.get("date_found", "")),
    )


@router.get("/api/jobs", response_model=JobListResponse)
async def list_jobs(
    hours: int = Query(168, description="Jobs from last N hours"),
    min_score: int = Query(MIN_MATCH_SCORE, description="Minimum match score"),
    source: str | None = Query(None, description="Filter by source"),
    bucket: str | None = Query(None, description="Filter by time bucket"),
    action: str | None = Query(None, description="Filter by user action"),
    visa_only: bool = Query(False, description="Only visa-sponsoring jobs"),
    limit: int = Query(200, le=500),
    offset: int = Query(0, ge=0),
    db: JobDatabase = Depends(get_db),
):
    days = max(1, hours // 24) if hours > 0 else 7
    all_jobs = await db.get_recent_jobs(days=days, min_score=min_score)

    # Load user actions
    all_actions = await db.user_actions.get_all_actions()
    action_map = {a["job_id"]: a["action"] for a in all_actions}

    # Convert and filter
    results = []
    for job in all_jobs:
        job_action = action_map.get(job["id"])
        resp = _job_to_response(job, action=job_action)

        # Apply filters
        if source and resp.source != source:
            continue
        if bucket and resp.bucket != bucket:
            continue
        if action and resp.action != action:
            continue
        if visa_only and not resp.visa_flag:
            continue

        results.append(resp)

    # Sort by score descending
    results.sort(key=lambda j: j.match_score, reverse=True)

    total = len(results)
    page = results[offset:offset + limit]

    return JobListResponse(
        jobs=page,
        total=total,
        filters_applied={
            "hours": hours,
            "min_score": min_score,
            "source": source,
            "bucket": bucket,
            "action": action,
            "visa_only": visa_only,
        },
    )


@router.get("/api/jobs/export")
async def export_csv(db: JobDatabase = Depends(get_db)):
    """Export recent jobs as CSV file."""
    from src.storage.csv_export import export_to_csv, HEADERS
    from src.models import Job

    jobs_data = await db.get_recent_jobs(days=7, min_score=MIN_MATCH_SCORE)
    if not jobs_data:
        raise HTTPException(404, "No jobs to export")

    # Convert dicts to Job objects for the CSV exporter
    job_objects = []
    for j in jobs_data:
        job_objects.append(Job(
            title=j.get("title", ""),
            company=j.get("company", ""),
            location=j.get("location", ""),
            description=j.get("description", ""),
            apply_url=j.get("apply_url", ""),
            source=j.get("source", ""),
            date_found=j.get("date_found", ""),
            match_score=j.get("match_score", 0),
            visa_flag=bool(j.get("visa_flag")),
            salary_min=j.get("salary_min"),
            salary_max=j.get("salary_max"),
            experience_level=j.get("experience_level", ""),
            job_type=j.get("job_type", ""),
            match_data=j.get("match_data", ""),
        ))

    export_dir = Path(str(DB_PATH)).parent / "exports"
    export_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = str(export_dir / f"jobs_{ts}.csv")
    export_to_csv(job_objects, filepath)

    return FileResponse(filepath, media_type="text/csv", filename=f"job360_export_{ts}.csv")


@router.get("/api/jobs/{job_id}")
async def get_job(job_id: int, db: JobDatabase = Depends(get_db)):
    job = await db.get_job_by_id(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    action_record = await db.user_actions.get_action(job_id)
    action = action_record["action"] if action_record else None
    return _job_to_response(job, action=action)

"""Application tracking pipeline endpoints."""

from fastapi import APIRouter, Depends, HTTPException

from src.api.deps import get_db
from src.api.schemas import PipelineAdvanceRequest
from src.storage.database import JobDatabase
from src.pipeline.tracker import PipelineStage

router = APIRouter()


@router.get("/api/pipeline")
async def get_applications(
    stage: str | None = None,
    db: JobDatabase = Depends(get_db),
):
    if stage:
        try:
            ps = PipelineStage(stage)
        except ValueError:
            raise HTTPException(400, f"Invalid stage: {stage}")
        apps = await db.applications.get_applications_by_stage(ps)
    else:
        apps = await db.applications.get_all_applications()
    return {"applications": apps}


@router.post("/api/pipeline/{job_id}")
async def create_application(job_id: int, db: JobDatabase = Depends(get_db)):
    job = await db.get_job_by_id(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    app = await db.applications.create_application(job_id)
    return app


@router.post("/api/pipeline/{job_id}/advance")
async def advance_stage(
    job_id: int,
    body: PipelineAdvanceRequest,
    db: JobDatabase = Depends(get_db),
):
    try:
        new_stage = PipelineStage(body.stage)
    except ValueError:
        stages = [s.value for s in PipelineStage]
        raise HTTPException(400, f"Invalid stage. Must be one of: {stages}")
    result = await db.applications.advance_stage(job_id, new_stage)
    if not result:
        raise HTTPException(404, "Application not found")
    return result


@router.get("/api/pipeline/reminders")
async def get_reminders(db: JobDatabase = Depends(get_db)):
    reminders = await db.applications.get_due_reminders()
    return {"reminders": reminders}


@router.get("/api/pipeline/counts")
async def pipeline_counts(db: JobDatabase = Depends(get_db)):
    counts = await db.applications.count_by_stage()
    return counts

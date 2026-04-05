"""User action endpoints — like, apply, not interested."""

from fastapi import APIRouter, Depends, HTTPException

from src.api.deps import get_db
from src.api.schemas import ActionRequest
from src.storage.database import JobDatabase

router = APIRouter()


@router.post("/api/jobs/{job_id}/action")
async def set_action(job_id: int, body: ActionRequest, db: JobDatabase = Depends(get_db)):
    valid_actions = {"liked", "applied", "not_interested"}
    if body.action not in valid_actions:
        raise HTTPException(400, f"Invalid action. Must be one of: {valid_actions}")
    job = await db.get_job_by_id(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    await db.user_actions.set_action(job_id, body.action, notes=body.notes)
    return {"ok": True, "job_id": job_id, "action": body.action}


@router.delete("/api/jobs/{job_id}/action")
async def remove_action(job_id: int, db: JobDatabase = Depends(get_db)):
    await db.user_actions.remove_action(job_id)
    return {"ok": True, "job_id": job_id}


@router.get("/api/actions")
async def get_all_actions(db: JobDatabase = Depends(get_db)):
    actions = await db.user_actions.get_all_actions()
    return {"actions": actions}


@router.get("/api/actions/counts")
async def action_counts(db: JobDatabase = Depends(get_db)):
    counts = await db.user_actions.count_by_action()
    return counts

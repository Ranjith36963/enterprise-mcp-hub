"""Search pipeline endpoints — trigger and poll."""

import asyncio
import logging
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException

from src.api.deps import get_db, get_profile
from src.api.schemas import SearchStartResponse, SearchStatusResponse
from src.storage.database import JobDatabase

logger = logging.getLogger("job360.api.search")

router = APIRouter()

# In-memory search run tracking (single-server MVP)
_search_runs: dict[str, dict] = {}


async def _run_pipeline(run_id: str, source_filter: str | None = None, safe_mode: bool = False):
    """Execute the search pipeline in background."""
    try:
        _search_runs[run_id]["progress"] = "loading profile"
        from src.main import run_search
        _search_runs[run_id]["progress"] = "searching"
        result = await run_search(
            source_filter=source_filter,
            no_notify=True,
            safe_mode=safe_mode,
        )
        _search_runs[run_id]["status"] = "complete"
        _search_runs[run_id]["progress"] = "done"
        _search_runs[run_id]["result"] = result
        logger.info(f"Search {run_id} complete: {result.get('new_jobs', 0)} new jobs")
    except (RuntimeError, ValueError, OSError) as e:
        _search_runs[run_id]["status"] = "failed"
        _search_runs[run_id]["progress"] = str(e)
        logger.error(f"Search {run_id} failed: {e}")


@router.post("/api/search", response_model=SearchStartResponse)
async def start_search(
    source: str | None = None,
    safe: bool = False,
):
    """Trigger a pipeline search run. Returns run_id to poll for status."""
    profile = get_profile()
    if not profile or not profile.is_complete:
        raise HTTPException(400, "No profile found. Upload a CV first.")

    run_id = uuid4().hex[:12]
    _search_runs[run_id] = {"status": "running", "progress": "starting", "result": None}

    # Run in background — don't block the response
    asyncio.create_task(_run_pipeline(run_id, source_filter=source, safe_mode=safe))

    return SearchStartResponse(run_id=run_id, status="running")


@router.get("/api/search/{run_id}/status", response_model=SearchStatusResponse)
async def search_status(run_id: str):
    """Poll the status of a running search."""
    if run_id not in _search_runs:
        raise HTTPException(404, "Search run not found")
    run = _search_runs[run_id]
    return SearchStatusResponse(
        run_id=run_id,
        status=run["status"],
        progress=run["progress"],
        result=run["result"],
    )

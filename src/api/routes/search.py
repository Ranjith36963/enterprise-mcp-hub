"""Search routes for Job360 FastAPI backend."""
from __future__ import annotations

import asyncio
import uuid
from typing import Optional

from fastapi import APIRouter, Query

from src.api.models import SearchStartResponse, SearchStatusResponse
from src.main import run_search

router = APIRouter(tags=["search"])

_runs: dict[str, dict] = {}


@router.post("/search", response_model=SearchStartResponse)
async def start_search(source: Optional[str] = Query(None)):
    """Start an async job search run. Returns a run_id to poll for status."""
    run_id = uuid.uuid4().hex[:12]
    _runs[run_id] = {"status": "running", "progress": "Starting...", "result": None}

    async def _run():
        try:
            _runs[run_id]["progress"] = "Fetching from sources..."
            result = await run_search(source_filter=source, no_notify=True)
            _runs[run_id].update(status="completed", progress="Done", result=result)
        except Exception as e:
            _runs[run_id].update(status="failed", progress=str(e))

    asyncio.create_task(_run())
    return SearchStartResponse(run_id=run_id, status="running")


@router.get("/search/{run_id}/status", response_model=SearchStatusResponse)
async def search_status(run_id: str):
    """Poll the status of a running or completed search."""
    run = _runs.get(run_id)
    if not run:
        return SearchStatusResponse(
            run_id=run_id,
            status="not_found",
            progress="Unknown run ID",
        )
    return SearchStatusResponse(run_id=run_id, **run)

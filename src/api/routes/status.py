"""Status and health endpoints."""

from fastapi import APIRouter, Depends

from src.api.deps import get_db, get_profile
from src.api.schemas import StatusResponse, SourceInfo, HealthResponse
from src.storage.database import JobDatabase
from src.__version__ import __version__
from src.main import SOURCE_REGISTRY

router = APIRouter()


@router.get("/api/health", response_model=HealthResponse)
async def health():
    return HealthResponse(status="ok", version=__version__)


@router.get("/api/status", response_model=StatusResponse)
async def status(db: JobDatabase = Depends(get_db)):
    jobs_total = await db.count_jobs()
    run_logs = await db.get_run_logs()
    last_run = run_logs[0] if run_logs else None
    source_health = await db.get_source_health()
    active = sum(
        1 for h in source_health.values()
        if not h.get("skip_until")
    )
    profile = get_profile()
    return StatusResponse(
        jobs_total=jobs_total,
        last_run=last_run,
        sources_active=active or len(SOURCE_REGISTRY),
        sources_total=len(SOURCE_REGISTRY),
        profile_exists=profile is not None and profile.is_complete,
    )


@router.get("/api/sources", response_model=list[SourceInfo])
async def list_sources(db: JobDatabase = Depends(get_db)):
    health = await db.get_source_health()
    sources = []
    for name in sorted(SOURCE_REGISTRY.keys()):
        sources.append(SourceInfo(
            name=name,
            health=health.get(name, {}),
        ))
    return sources

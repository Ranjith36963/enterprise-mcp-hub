"""Job360 FastAPI application."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.storage.database import JobDatabase
from src.config.settings import DB_PATH
from src.__version__ import __version__


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: init DB. Shutdown: close DB."""
    db = JobDatabase(str(DB_PATH))
    await db.init_db()
    app.state.db = db
    yield
    await db.close()


app = FastAPI(
    title="Job360 API",
    description="UK job search aggregator — 50 sources, 8D scoring, CV-based matching",
    version=__version__,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:3001",
        "https://job360.app",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routes
from src.api.routes import status, profile, jobs, actions, pipeline, search  # noqa: E402

app.include_router(status.router, tags=["Status"])
app.include_router(profile.router, tags=["Profile"])
app.include_router(jobs.router, tags=["Jobs"])
app.include_router(actions.router, tags=["Actions"])
app.include_router(pipeline.router, tags=["Pipeline"])
app.include_router(search.router, tags=["Search"])

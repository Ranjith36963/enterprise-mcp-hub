"""Shared FastAPI dependencies for Job360 API."""

from fastapi import Request

from src.storage.database import JobDatabase
from src.profile.storage import load_profile
from src.profile.models import UserProfile


async def get_db(request: Request) -> JobDatabase:
    """Get the shared database instance from app state."""
    return request.app.state.db


def get_profile() -> UserProfile | None:
    """Load the current user profile (None if not set up)."""
    return load_profile()

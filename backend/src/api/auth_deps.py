"""FastAPI auth dependencies — cookie-based session resolution.

Usage::

    @router.get("/me")
    async def me(user: CurrentUser = Depends(require_user)):
        return {"id": user.id, "email": user.email}

When the session cookie is missing / tampered / expired, raises HTTP 401.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

import aiosqlite
from fastapi import Cookie, HTTPException, status

from src.core.settings import DB_PATH
from src.services.auth import sessions as auth_sessions

SESSION_COOKIE_NAME = "job360_session"


def _secret() -> str:
    """Return the HMAC secret for session cookies.

    Fail-closed: raises if ``SESSION_SECRET`` is unset. A committed default
    would silently sign production cookies with a value visible in git log,
    so we refuse to serve traffic without an explicit key. Tests must set
    the env var (the fixtures in ``test_auth_routes.py`` /
    ``test_channels_routes.py`` do this via ``monkeypatch.setenv``;
    ``test_auth_sessions.py`` passes ``secret=`` explicitly).
    """
    secret = os.environ.get("SESSION_SECRET")
    if not secret:
        raise RuntimeError(
            "SESSION_SECRET env var is required. Generate with: "
            "python -c 'import secrets; print(secrets.token_urlsafe(64))'"
        )
    return secret


@dataclass(frozen=True)
class CurrentUser:
    id: str
    email: str


async def _current_user_from_cookie(
    cookie: Optional[str],
) -> Optional[CurrentUser]:
    if not cookie:
        return None
    user_id = await auth_sessions.resolve_session(
        str(DB_PATH), cookie, secret=_secret()
    )
    if user_id is None:
        return None
    async with aiosqlite.connect(str(DB_PATH)) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT id, email FROM users WHERE id = ? AND deleted_at IS NULL",
            (user_id,),
        )
        row = await cur.fetchone()
    return CurrentUser(id=row["id"], email=row["email"]) if row else None


async def require_user(
    job360_session: Optional[str] = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> CurrentUser:
    user = await _current_user_from_cookie(job360_session)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="authentication required",
        )
    return user


async def optional_user(
    job360_session: Optional[str] = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> Optional[CurrentUser]:
    return await _current_user_from_cookie(job360_session)

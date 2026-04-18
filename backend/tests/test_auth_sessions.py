"""Tests for signed-cookie session management."""
import asyncio
import os
import tempfile
from datetime import datetime, timedelta, timezone

import aiosqlite
import pytest

from migrations import runner
from src.services.auth import sessions as auth_sessions


SESSION_SECRET = "test-secret-" + "x" * 32


@pytest.fixture
async def session_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    # Apply migrations up through 0001_auth (Phase 1).
    await runner.up(path)
    async with aiosqlite.connect(path) as db:
        # Insert a placeholder user matching the sessions FK.
        await db.execute(
            "INSERT INTO users(id, email, password_hash) VALUES(?, ?, ?)",
            ("user-1", "u@example.test", "!"),
        )
        await db.commit()
    yield path
    try:
        os.unlink(path)
    except OSError:
        pass


@pytest.mark.asyncio
async def test_session_create_and_resolve(session_db):
    cookie = await auth_sessions.create_session(
        session_db, user_id="user-1", secret=SESSION_SECRET
    )
    assert isinstance(cookie, str) and "." in cookie
    resolved = await auth_sessions.resolve_session(
        session_db, cookie, secret=SESSION_SECRET
    )
    assert resolved == "user-1"


@pytest.mark.asyncio
async def test_session_revoke(session_db):
    cookie = await auth_sessions.create_session(
        session_db, user_id="user-1", secret=SESSION_SECRET
    )
    await auth_sessions.revoke_session(session_db, cookie, secret=SESSION_SECRET)
    assert await auth_sessions.resolve_session(
        session_db, cookie, secret=SESSION_SECRET
    ) is None


@pytest.mark.asyncio
async def test_cookie_tampering_rejected(session_db):
    cookie = await auth_sessions.create_session(
        session_db, user_id="user-1", secret=SESSION_SECRET
    )
    # Flip last char of signature
    tampered = cookie[:-1] + ("a" if cookie[-1] != "a" else "b")
    assert await auth_sessions.resolve_session(
        session_db, tampered, secret=SESSION_SECRET
    ) is None


@pytest.mark.asyncio
async def test_expired_session_returns_none(session_db):
    # Create a session that is already past expiry by manipulating expires_at.
    cookie = await auth_sessions.create_session(
        session_db, user_id="user-1", secret=SESSION_SECRET
    )
    async with aiosqlite.connect(session_db) as db:
        past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        await db.execute("UPDATE sessions SET expires_at = ?", (past,))
        await db.commit()
    assert await auth_sessions.resolve_session(
        session_db, cookie, secret=SESSION_SECRET
    ) is None


@pytest.mark.asyncio
async def test_wrong_secret_rejected(session_db):
    cookie = await auth_sessions.create_session(
        session_db, user_id="user-1", secret=SESSION_SECRET
    )
    assert await auth_sessions.resolve_session(
        session_db, cookie, secret="a-different-secret-that-is-long-enough"
    ) is None

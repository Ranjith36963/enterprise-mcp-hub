"""Auth primitives: argon2id passwords + signed-cookie sessions.

Surface::

    from src.services.auth import passwords, sessions
    passwords.hash_password("pw") -> str
    passwords.verify_password(h, "pw") -> bool
    await sessions.create_session(db_path, user_id, secret) -> cookie
    await sessions.resolve_session(db_path, cookie, secret) -> user_id | None
    await sessions.revoke_session(db_path, cookie, secret) -> None
"""

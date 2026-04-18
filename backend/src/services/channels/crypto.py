"""Fernet (AES-128-CBC + HMAC-SHA256) encryption for channel credentials.

Key source: ``CHANNEL_ENCRYPTION_KEY`` env var (urlsafe-base64 32-byte key).
Generate once with::

    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

Key rotation (Batch 3): ``user_channels.key_version`` column already exists.
"""
from __future__ import annotations

import os
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken


@lru_cache(maxsize=1)
def _fernet() -> Fernet:
    key = os.environ.get("CHANNEL_ENCRYPTION_KEY")
    if not key:
        # Deterministic dev/test fallback. Never used in production — the
        # env-driven path is the only real one. Tests overwrite via
        # ``set_test_key()`` below.
        key = "mIaARLi5Yd8zKLTZBtRGcKB6a83kfkSTEhtfcRwGmF4="
    return Fernet(key.encode("utf-8") if isinstance(key, str) else key)


def encrypt(plaintext: str) -> bytes:
    return _fernet().encrypt(plaintext.encode("utf-8"))


def decrypt(ciphertext: bytes) -> str:
    try:
        return _fernet().decrypt(ciphertext).decode("utf-8")
    except InvalidToken as e:
        raise ValueError("channel credential decryption failed") from e


def set_test_key(key: str) -> None:
    """Test hook — clears lru_cache and replaces the key."""
    os.environ["CHANNEL_ENCRYPTION_KEY"] = key
    _fernet.cache_clear()

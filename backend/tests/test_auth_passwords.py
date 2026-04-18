"""Tests for argon2id password hashing."""
from src.services.auth.passwords import hash_password, verify_password


def test_password_roundtrip():
    h = hash_password("correct horse battery staple")
    assert verify_password(h, "correct horse battery staple") is True
    assert verify_password(h, "incorrect") is False


def test_password_hash_is_argon2id():
    h = hash_password("x")
    assert h.startswith("$argon2id$"), f"unexpected hash format: {h[:20]}..."


def test_distinct_salts_per_hash():
    a = hash_password("same")
    b = hash_password("same")
    assert a != b, "each hash must include a fresh salt"


def test_verify_rejects_malformed_hash():
    assert verify_password("not-a-hash", "anything") is False

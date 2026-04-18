"""Fernet credential encryption tests."""
import pytest
from cryptography.fernet import Fernet

from src.services.channels import crypto


@pytest.fixture(autouse=True)
def _fernet_key(monkeypatch):
    key = Fernet.generate_key().decode("ascii")
    crypto.set_test_key(key)
    yield
    # No teardown — a fresh key is set per test.


def test_fernet_roundtrip():
    plaintext = "slack://a/b/c"
    ct = crypto.encrypt(plaintext)
    assert isinstance(ct, bytes)
    assert crypto.decrypt(ct) == plaintext


def test_different_plaintexts_produce_different_ciphertexts():
    a = crypto.encrypt("slack://a/b/c")
    b = crypto.encrypt("slack://x/y/z")
    assert a != b


def test_decrypt_rejects_tampered_ciphertext():
    ct = crypto.encrypt("slack://a/b/c")
    tampered = ct[:-1] + b"X"
    with pytest.raises(ValueError):
        crypto.decrypt(tampered)


def test_decrypt_with_wrong_key_fails():
    ct = crypto.encrypt("slack://a/b/c")
    # Rotate the key — previous ciphertext must NOT decrypt.
    crypto.set_test_key(Fernet.generate_key().decode("ascii"))
    with pytest.raises(ValueError):
        crypto.decrypt(ct)

"""Tests for src.security.jwt — JWT token management."""

import pytest

from src.security.jwt import create_access_token, decode_access_token

SECRET = "test-secret-key-for-jwt-testing-32chars!"


def test_create_access_token_returns_string():
    token = create_access_token("user-123", SECRET)
    assert isinstance(token, str)
    assert len(token) > 0


def test_decode_access_token_round_trip():
    token = create_access_token("user-456", SECRET)
    payload = decode_access_token(token, SECRET)
    assert payload["sub"] == "user-456"


def test_decode_access_token_has_exp_claim():
    token = create_access_token("user-789", SECRET)
    payload = decode_access_token(token, SECRET)
    assert "exp" in payload


def test_decode_access_token_expired_raises():
    token = create_access_token("user-exp", SECRET, expire_days=-1)
    with pytest.raises(Exception):
        decode_access_token(token, SECRET)


def test_decode_access_token_invalid_token_raises():
    with pytest.raises(Exception):
        decode_access_token("not.a.valid.token", SECRET)


def test_decode_access_token_wrong_secret_raises():
    token = create_access_token("user-sec", SECRET)
    with pytest.raises(Exception):
        decode_access_token(token, "wrong-secret-key-that-is-different!")


def test_jwt_contains_jti():
    """JWT should include a unique jti claim for future revocation support."""
    token = create_access_token("user-jti", SECRET)
    payload = decode_access_token(token, SECRET)
    assert "jti" in payload
    assert len(payload["jti"]) > 10

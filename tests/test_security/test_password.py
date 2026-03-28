"""Tests for src.security.password — bcrypt hashing."""

from src.security.password import hash_password, verify_password


def test_hash_password_returns_bcrypt_string():
    hashed = hash_password("mysecret")
    assert hashed.startswith("$2b$")


def test_hash_password_is_not_plaintext():
    hashed = hash_password("mysecret")
    assert hashed != "mysecret"


def test_hash_password_different_inputs_different_hashes():
    h1 = hash_password("password1")
    h2 = hash_password("password2")
    assert h1 != h2


def test_verify_password_correct_returns_true():
    hashed = hash_password("correct")
    assert verify_password("correct", hashed) is True


def test_verify_password_wrong_returns_false():
    hashed = hash_password("correct")
    assert verify_password("wrong", hashed) is False


def test_verify_password_empty_returns_false():
    hashed = hash_password("notempty")
    assert verify_password("", hashed) is False

"""Tests for src.security.encryption — Fernet KeyVault."""

import pytest
from cryptography.fernet import Fernet

from src.security.encryption import KeyVault


@pytest.fixture
def key() -> str:
    return Fernet.generate_key().decode()


@pytest.fixture
def vault(key: str) -> KeyVault:
    return KeyVault(key)


def test_encrypt_returns_string(vault: KeyVault):
    result = vault.encrypt("my-api-key")
    assert isinstance(result, str)


def test_encrypt_decrypt_round_trip(vault: KeyVault):
    plaintext = "sk-openrouter-abc123"
    encrypted = vault.encrypt(plaintext)
    assert vault.decrypt(encrypted) == plaintext


def test_encrypted_text_is_not_plaintext(vault: KeyVault):
    plaintext = "sk-openrouter-abc123"
    encrypted = vault.encrypt(plaintext)
    assert encrypted != plaintext


def test_decrypt_wrong_key_raises(vault: KeyVault):
    encrypted = vault.encrypt("secret")
    other_key = Fernet.generate_key().decode()
    other_vault = KeyVault(other_key)
    with pytest.raises(Exception):
        other_vault.decrypt(encrypted)


def test_encrypt_different_inputs_different_ciphertext(vault: KeyVault):
    e1 = vault.encrypt("key-one")
    e2 = vault.encrypt("key-two")
    assert e1 != e2

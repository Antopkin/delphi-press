"""Fernet encryption for user API keys.

Спека: docs/08-api-backend.md (§12).

Контракт:
    KeyVault.encrypt(plaintext) → ciphertext string
    KeyVault.decrypt(ciphertext) → plaintext string
"""

from __future__ import annotations

from cryptography.fernet import Fernet


class KeyVault:
    """Symmetric encryption/decryption of user API keys via Fernet."""

    def __init__(self, encryption_key: str) -> None:
        self._fernet = Fernet(encryption_key.encode())

    def encrypt(self, plaintext: str) -> str:
        """Encrypt a plaintext string and return base64-encoded ciphertext."""
        return self._fernet.encrypt(plaintext.encode()).decode()

    def decrypt(self, ciphertext: str) -> str:
        """Decrypt a base64-encoded ciphertext and return plaintext."""
        return self._fernet.decrypt(ciphertext.encode()).decode()

"""Bcrypt password hashing utilities.

Спека: docs/08-api-backend.md (§12).

Контракт:
    hash_password(str) → bcrypt hash string
    verify_password(str, str) → bool
"""

from __future__ import annotations

import bcrypt


def hash_password(password: str) -> str:
    """Hash a plaintext password with bcrypt."""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    """Verify a plaintext password against a bcrypt hash."""
    return bcrypt.checkpw(password.encode(), hashed.encode())

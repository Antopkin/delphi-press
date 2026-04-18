"""JWT token creation and verification.

Спека: docs-site/docs/infrastructure/security.md.

Контракт:
    create_access_token(user_id, secret_key, expire_days) → JWT string
    decode_access_token(token, secret_key) → payload dict
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import jwt


def create_access_token(
    user_id: str,
    secret_key: str,
    expire_days: int = 7,
) -> str:
    """Create a signed JWT access token."""
    now = datetime.now(UTC)
    payload = {
        "sub": user_id,
        "jti": str(uuid.uuid4()),
        "iat": now,
        "exp": now + timedelta(days=expire_days),
    }
    return jwt.encode(payload, secret_key, algorithm="HS256")


def decode_access_token(token: str, secret_key: str) -> dict:
    """Decode and verify a JWT access token.

    Raises:
        jwt.ExpiredSignatureError: Token has expired.
        jwt.InvalidTokenError: Token is invalid.
    """
    return jwt.decode(token, secret_key, algorithms=["HS256"])

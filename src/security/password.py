"""Bcrypt password hashing utilities.

Спека: docs-site/docs/infrastructure/security.md.

Контракт:
    hash_password(str) → bcrypt hash string
    verify_password(str, str) → bool
    hash_password_async(str) → bcrypt hash string  (non-blocking)
    verify_password_async(str, str) → bool          (non-blocking)

bcrypt.hashpw / checkpw are CPU-intensive (100-300 ms).
Async wrappers delegate to a thread pool via asyncio.to_thread
so the event loop stays responsive in FastAPI handlers.
"""

from __future__ import annotations

import asyncio

import bcrypt


def hash_password(password: str) -> str:
    """Hash a plaintext password with bcrypt."""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    """Verify a plaintext password against a bcrypt hash."""
    return bcrypt.checkpw(password.encode(), hashed.encode())


async def hash_password_async(password: str) -> str:
    """Non-blocking wrapper around hash_password.

    Offloads CPU-bound bcrypt hashing to the default thread-pool executor
    so the asyncio event loop is not blocked.
    """
    return await asyncio.to_thread(hash_password, password)


async def verify_password_async(password: str, hashed: str) -> bool:
    """Non-blocking wrapper around verify_password.

    Offloads CPU-bound bcrypt verification to the default thread-pool executor
    so the asyncio event loop is not blocked.
    """
    return await asyncio.to_thread(verify_password, password, hashed)

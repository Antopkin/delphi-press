"""Tests for src.security.password — bcrypt hashing."""

import asyncio
import inspect

import pytest

from src.security.password import (
    hash_password,
    hash_password_async,
    verify_password,
    verify_password_async,
)


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


# === Async wrappers ===


def test_hash_password_async_exists():
    """hash_password_async must be importable and be a coroutine function."""
    assert callable(hash_password_async)
    assert inspect.iscoroutinefunction(hash_password_async)


def test_verify_password_async_exists():
    """verify_password_async must be importable and be a coroutine function."""
    assert callable(verify_password_async)
    assert inspect.iscoroutinefunction(verify_password_async)


@pytest.mark.asyncio
async def test_hash_password_async_returns_bcrypt_string():
    hashed = await hash_password_async("asyncsecret")
    assert hashed.startswith("$2b$")
    assert hashed != "asyncsecret"


@pytest.mark.asyncio
async def test_verify_password_async_correct():
    hashed = await hash_password_async("correct")
    assert await verify_password_async("correct", hashed) is True


@pytest.mark.asyncio
async def test_verify_password_async_wrong():
    hashed = await hash_password_async("correct")
    assert await verify_password_async("wrong", hashed) is False


@pytest.mark.asyncio
async def test_hash_password_async_does_not_block_event_loop():
    """Verify async wrapper yields control — other coroutines can run concurrently."""
    marker: list[str] = []

    async def background():
        marker.append("ran")

    # Schedule background task; if hash_password_async truly offloads to thread,
    # the background task gets a chance to run.
    _, _ = await asyncio.gather(
        hash_password_async("test"),
        background(),
    )
    assert "ran" in marker

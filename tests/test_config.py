"""Tests for src.config — expanded Settings class."""

from __future__ import annotations

import pytest
from pydantic import ValidationError


# ── Backward compatibility ──────────────────────────────────────────


def test_settings_inherits_llm_config():
    """Settings must still expose all LLMConfig fields."""
    from src.config import Settings

    s = Settings()
    assert hasattr(s, "openrouter_api_key")
    assert hasattr(s, "default_model_cheap")
    assert hasattr(s, "max_budget_usd")


def test_settings_new_fields_have_defaults():
    """All new fields must have defaults — no env vars required."""
    from src.config import Settings

    s = Settings()
    assert s.app_name == "Delphi Press"
    assert s.debug is False


# ── New fields ──────────────────────────────────────────────────────


def test_settings_secret_key_has_dev_default():
    from src.config import Settings

    s = Settings()
    assert len(s.secret_key) >= 32


def test_settings_database_url_default():
    from src.config import Settings

    s = Settings()
    assert s.database_url.startswith("sqlite+aiosqlite")


def test_settings_redis_url_default():
    from src.config import Settings

    s = Settings()
    assert "redis" in s.redis_url


def test_settings_app_version():
    from src.config import Settings

    s = Settings()
    assert s.app_version == "0.1.0"


def test_settings_pipeline_tuning_fields():
    from src.config import Settings

    s = Settings()
    assert s.delphi_rounds == 2
    assert s.delphi_agents == 5
    assert s.max_event_threads == 20
    assert s.max_headlines_per_prediction == 7
    assert s.quality_gate_min_score == 3


def test_settings_server_fields():
    from src.config import Settings

    s = Settings()
    assert s.host == "0.0.0.0"
    assert s.port == 8000
    assert s.workers == 1


def test_settings_arq_fields():
    from src.config import Settings

    s = Settings()
    assert s.arq_max_jobs == 10
    assert s.arq_job_timeout == 1800
    assert s.arq_concurrency == 2


def test_settings_cors_origins():
    from src.config import Settings

    s = Settings()
    assert s.cors_origins == ["*"]


# ── Validators ──────────────────────────────────────────────────────


def test_settings_log_level_uppercases():
    from src.config import Settings

    s = Settings(log_level="info")
    assert s.log_level == "INFO"


def test_settings_log_level_rejects_invalid():
    from src.config import Settings

    with pytest.raises(ValidationError, match="log_level"):
        Settings(log_level="TRACE")


def test_settings_database_url_rejects_invalid():
    from src.config import Settings

    with pytest.raises(ValidationError, match="database_url"):
        Settings(database_url="mysql://localhost/db")


# ── Singleton ───────────────────────────────────────────────────────


def test_get_settings_returns_singleton():
    from src.config import get_settings

    get_settings.cache_clear()
    s1 = get_settings()
    s2 = get_settings()
    assert s1 is s2
    get_settings.cache_clear()

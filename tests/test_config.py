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
    assert s.app_version == "0.9.4"


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
    assert s.cors_origins == ["http://localhost:8000"]


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


# ── Security fields ─────────────────────────────────────────────────


def test_settings_jwt_expire_days_default():
    from src.config import Settings

    s = Settings()
    assert s.jwt_expire_days == 7


def test_settings_fernet_key_has_dev_default():
    from src.config import Settings

    s = Settings()
    assert len(s.fernet_key) > 0


def test_settings_fernet_key_is_valid_fernet():
    from cryptography.fernet import Fernet

    from src.config import Settings

    s = Settings()
    Fernet(s.fernet_key.encode())


# ── Singleton ───────────────────────────────────────────────────────


def test_get_settings_returns_singleton():
    from src.config import get_settings

    get_settings.cache_clear()
    s1 = get_settings()
    s2 = get_settings()
    assert s1 is s2
    get_settings.cache_clear()


# ── Presets ────────────────────────────────────────────────────────


def test_presets_are_defined():
    from src.config import PRESETS

    assert "light" in PRESETS
    assert "standard" in PRESETS
    assert "full" in PRESETS
    assert len(PRESETS) == 3


def test_preset_config_fields():
    from src.config import PRESETS

    for name, preset in PRESETS.items():
        assert preset.name == name
        assert preset.label
        assert preset.description
        assert preset.estimated_cost_usd > 0
        assert preset.model
        assert preset.max_event_threads > 0
        assert preset.delphi_rounds >= 1
        assert preset.max_headlines > 0
        assert preset.quality_gate_min_score >= 1


def test_get_preset_valid():
    from src.config import get_preset

    preset = get_preset("light")
    assert preset.name == "light"
    assert preset.model == "google/gemini-2.5-flash"
    assert preset.delphi_rounds == 1


def test_get_preset_invalid_raises():
    from src.config import get_preset

    with pytest.raises(ValueError, match="Unknown preset"):
        get_preset("custom")


def test_preset_config_is_frozen():
    from src.config import get_preset

    preset = get_preset("full")
    with pytest.raises(AttributeError):
        preset.model = "changed"

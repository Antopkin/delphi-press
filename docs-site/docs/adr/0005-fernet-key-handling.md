# ADR-0005: Fernet/JWT key handling (CWE-798 fix)

**Status:** Accepted · **Date:** 2026-04-13 · **Deciders:** @Antopkin

## Context

В апреле 2026 CI flagged `src/config.py` как содержащий **hardcoded cryptographic keys**:

- `SECRET_KEY` — HS256 подпись JWT
- `FERNET_KEY` — шифрование API-ключей пользователей в БД

Оба ключа были рабочими значениями, видимыми в публичном git репо. Классификация: **CWE-798: Use of Hard-coded Credentials**, severity Medium.

Production на VPS уже использовал реальные ключи из `.env` — hardcoded были только **дефолты для dev**. Но любой, кто клонировал репо, имел рабочие prod-ключи в git history.

## Decision

**Трёхслойная схема:**

1. **Dev/test**: `field_validator(mode="before")` автогенерирует эфемерные ключи через `secrets.token_urlsafe(48)` (JWT) и `Fernet.generate_key()` (Fernet). Warning в лог: «ключи не переживут рестарт».

2. **Production** (`DELPHI_PRODUCTION=1`): ключи **обязательны из `.env`**. Автогенерация запрещена — `ValueError` с инструкцией по генерации.

3. **Blocklist сожжённых ключей**: `_BURNED_SECRETS = frozenset({...})` — старые публичные значения. Отвергаются **в любом окружении** (dev, test, prod). Защита от stale `.env` с копией из git history.

Дополнительно:
- Whitespace-only значения → обрабатываются как отсутствующие
- Невалидный Fernet формат → rejection на уровне config (fail-fast)
- Warnings не логируют сами значения ключей (защита от CWE-532)

## Consequences

**Плюсы:**
- Public repo больше не содержит рабочих ключей
- Production требует явного задания — невозможно случайно задеплоить с дефолтом
- Dev workflow не сломан — эфемерные ключи автогенерятся
- +12 тестов (1413 → 1425) покрывают все edge cases

**Минусы:**
- Dev-сессии теряют JWT и зашифрованные API-keys при рестарте (ожидаемо)
- Deploy checklist расширен: сгенерировать и задать оба ключа до первого старта
- Старые локальные `.env` с сожжёнными ключами требуют ротации

## Alternatives considered

1. **Удалить дефолты, ошибка при отсутствии** — ломает dev-workflow (каждый разработчик должен генерировать локально)
2. **Хранить ключи в vault (HashiCorp/AWS Secrets Manager)** — overkill для single-VPS проекта; добавляет deploy dependency
3. **Commit `.env.example` с пустыми ключами** — сделано, но само по себе не решает проблему — разработчик мог забыть перезаписать

## References

- CHANGELOG v0.9.9 — полный разбор
- `src/config.py` — `_BURNED_SECRETS`, `field_validator` для `secret_key` и `fernet_key`
- `tests/test_config.py` — 12 regression тестов
- Commits: `067a1e5`…`358aceb` (9 TDD циклов)
- [infrastructure/security.md](../infrastructure/security.md) — общая threat model

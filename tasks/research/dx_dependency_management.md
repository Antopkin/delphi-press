# Dependency Management Strategy для Delphi Press

> Research date: 2026-04-05

## Источники

1. [uv — Managing dependencies](https://docs.astral.sh/uv/concepts/projects/dependencies/)
2. [Using uv with Renovate](https://docs.astral.sh/uv/guides/integration/renovate/)
3. [Dependabot Now Supports uv](https://pydevtools.com/blog/dependabot-uv-support/)
4. [Dependabot updates uv.lock but not pyproject.toml · #12788](https://github.com/dependabot/dependabot-core/issues/12788)
5. [Renovate PEP 621 manager](https://docs.renovatebot.com/modules/manager/pep621/)
6. [uv audit — Issue #9189 (COMPLETED)](https://github.com/astral-sh/uv/issues/9189)
7. [pip-audit · GitHub (pypa)](https://github.com/pypa/pip-audit)
8. [Should You Use Upper Bound Version Constraints?](https://iscinumpy.dev/post/bound-version-constraints/)
9. [LiteLLM TeamPCP Supply Chain Attack](https://www.wiz.io/blog/threes-a-crowd-teampcp-trojanizes-litellm-in-continuation-of-campaign)
10. [Docker Base Image Pinning 2026](https://oneuptime.com/blog/post/2026-02-08-how-to-pin-package-versions-in-dockerfiles-for-reproducible-builds/view)

---

## Текущее состояние (аудит)

### Что работает хорошо

| Аспект | Оценка |
|--------|--------|
| `uv.lock` закоммичен | ✅ Гарантирует воспроизводимость |
| `uv sync --locked` в Dockerfile | ✅ Точные версии |
| Lower bounds без upper caps | ✅ Правильно для application |
| `pydantic<3.0` upper bound | ✅ Оправдан |
| Non-root Docker, multi-stage | ✅ Безопасность |

### Риски

| Риск | Серьёзность |
|------|-------------|
| Нет автообновления зависимостей | Высокая |
| Нет сканирования уязвимостей | Высокая (litellm март 2026) |
| `python:3.12-slim` без digest | Средняя |
| Нет Dependabot/Renovate | Средняя |
| `pip install` без версий в docs-builder | Низкая |

---

## Dependabot vs Renovate

| Критерий | Dependabot | Renovate |
|----------|-----------|---------|
| Обновляет `pyproject.toml` | Нет (баг #12788) | Да — оба файла атомарно |
| Cooldown для новых пакетов | Нет | `minimumReleaseAge` |
| Docker digest pinning | Да | Да |
| Зрелость uv-поддержки | Alpha | Стабильная |

### Рекомендация: Renovate

Renovate обновляет оба файла атомарно. `minimumReleaseAge: "3 days"` защищает от supply chain. Поддерживает Docker digest pinning.

---

## Security scanning

| Инструмент | База CVE | Нативная работа с uv.lock |
|-----------|---------|--------------------------|
| `uv audit` | OSV (Google) | Да (с uv 0.10.10) |
| pip-audit | OSV + PyPI Advisory | Через export |
| uv-secure | PyPI JSON API | Да (alpha) |

**Primary:** `uv audit`. **Secondary:** `pip-audit` в CI.
**Важно:** uv в Dockerfile `0.8` — нужно обновить до `>=0.11`.

---

## Version pinning strategy

Lower bounds + lockfile = правильный подход для application. Upper bounds (`pydantic<3.0`) только при доказанном breaking change. Остальное — через lockfile.

---

## Docker image pinning

Текущее: `python:3.12-slim` (мутабельный тег).
Рекомендация: digest pinning через Renovate (`pinDigests: true`).

---

## Готовые конфиги

### renovate.json

```json
{
  "$schema": "https://docs.renovatebot.com/renovate-schema.json",
  "extends": ["config:recommended"],
  "timezone": "Europe/Moscow",
  "schedule": ["before 9am on Monday"],
  "lockFileMaintenance": {
    "enabled": true,
    "schedule": ["before 9am on Monday"]
  },
  "packageRules": [
    {
      "matchDatasources": ["pypi"],
      "minimumReleaseAge": "3 days",
      "automerge": false,
      "groupName": "Python dependencies"
    },
    {
      "matchDatasources": ["docker"],
      "pinDigests": true,
      "automerge": false,
      "groupName": "Docker base images"
    }
  ],
  "vulnerabilityAlerts": {
    "enabled": true,
    "schedule": ["at any time"]
  }
}
```

### .github/workflows/security.yml

```yaml
name: Security Scan
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]
  schedule:
    - cron: "0 6 * * 1"

jobs:
  audit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
        with:
          version: ">=0.11"
      - run: uv sync --locked --all-extras
      - name: uv audit
        run: uv audit
      - name: pip-audit
        uses: pypa/gh-action-pip-audit@v1.1.0
        with:
          virtual-environment: .venv
```

---

## План внедрения

| Шаг | Действие | Effort | Impact | Приоритет |
|-----|----------|--------|--------|-----------|
| 1 | `security.yml` с `uv audit` | 1 ч | Критический | P0 |
| 2 | Обновить uv `0.8` → `0.11` в Dockerfile | 30 мин | Открывает uv audit | P0 |
| 3 | Renovate GitHub App + `renovate.json` | 1 ч | Авто PR | P1 |
| 4 | `.pre-commit-config.yaml` с `uv-lock` | 30 мин | Lockfile guard | P1 |
| 5 | Docker digest pinning | 2 ч | Иммутабельные сборки | P2 |
| 6 | Поднять `cryptography>=44.0` | 30 мин | Убрать CVE | P2 |
| 7 | SBOM через CycloneDX | 1 ч | Incident response | P3 |

**Итого P0+P1:** ~3 часа.

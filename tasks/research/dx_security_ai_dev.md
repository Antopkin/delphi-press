# Security в AI-assisted разработке

> Дата исследовани��: 2026-04-05
> Версия проекта: Delphi Press v0.9.5

## Источники

1. [Claude Code Security — Anthropic](https://code.claude.com/docs/en/security)
2. [Claude Code Security Best Practices — Backslash](https://www.backslash.security/blog/claude-code-security-best-practices)
3. [Claude Code Hardening Cheat Sheet](https://github.com/okdt/claude-code-hardening-cheatsheet)
4. [deny permissions not enforced — #6699](https://github.com/anthropics/claude-code/issues/6699)
5. [OWASP Top 10 for LLM Applications](https://owasp.org/www-project-top-10-for-large-language-model-applications/)
6. [OWASP Top 10 for Agentic Applications 2026](https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/)
7. [AI-Generated Code: 2.74x more vulnerabilities](https://www.softwareseni.com/ai-generated-code-security-risks-why-vulnerabilities-increase-2-74x-and-how-to-prevent-them/)
8. [Prompt Injection on Agentic Coding Assistants — arXiv](https://arxiv.org/html/2601.17548v1)
9. [LiteLLM Supply Chain Attack March 2026](https://futuresearch.ai/blog/litellm-pypi-supply-chain-attack/)
10. [Secret Scanning with Gitleaks](https://oneuptime.com/blog/post/2026-01-25-secret-scanning-gitleaks/view)

---

## Текущие защиты (аудит)

| Категория | Мера | Статус | Оценка |
|-----------|------|--------|--------|
| Claude Code permissions | Deny: Read/Edit `.env`, `.env.local`, `.env.production` | Частичный | WARN: не покрывает `**/.env`, `*.pem`, `*.key` |
| Hooks / Pre-tool | Блокировка `rm -rf`, `git push --force`, `sudo` | Есть | GOOD |
| Auth | JWT (PyJWT) + bcrypt, API-ключи Fernet | Есть | GOOD |
| Production validation | `_reject_insecure_defaults_in_production` | Есть | GOOD |
| CSRF | Middleware на POST endpoints | Есть | GOOD |
| CSP | `script-src 'self' 'unsafe-inline' cdn.jsdelivr.net` | Есть | WARN: `unsafe-inline` ослабляет CSP |
| Nginx rate limiting | auth: 5r/m, predictions: 2r/m, general: 10r/s | Есть | GOOD |
| TLS | TLSv1.2/1.3, Let's Encrypt, HSTS | Есть | GOOD |
| Docker | Non-root UID 1001, tini init, multi-stage | Есть | GOOD |
| Network isolation | backend internal, frontend для nginx | Есть | GOOD |
| Secret scanning | Нет pre-commit / CI scanning | **Отсутствует** | GAP |
| SAST | Нет автопроверки AI-generated кода | **Отсутствует** | GAP |
| Supply chain | uv.lock pinned, но нет SCA в CI | Частичный | GAP |

---

## AI-специфичные риски

### 1. Prompt injection через внешний контент

Delphi Press парсит RSS и веб-страницы СМИ. Если в тексте инъекция (`<!-- SYSTEM: ignore previous instructions -->`), LLM может обработать как команду. Прецедент: CVE-2025-53773 (Copilot, CVSS 9.6).

**Атакуемые стадии:** Stage 1 (RSS), Stage 2 (event threads), Stage 3 (persona prompts).
**Mitigation:** Санитизация входящего текста, structural prompt separation, мониторинг аномалий.

### 2. Secret leakage через AI-контекст

До патча 1.0.93 deny-rules в settings.json полностью игнорировались ([The Register, Jan 2026](https://www.theregister.com/2026/01/28/claude_code_ai_secrets_files/)). Текущие deny-rules покрывают только `.env*` в корне — не `**/.env*`, `*.pem`, `*.key`.

### 3. Slopsquatting — галлюцинированные пакеты

~20% AI-рекомендаций содержат несуществующие pip/npm пакеты. Атакующие регистрируют эти имена с вредоносным кодом. Инцидент: litellm 1.82.7 (март 2026, TeamPCP).
**Mitigation:** `pip-audit` в CI, `uv lock --locked` в Dockerfile (уже есть).

### 4. AI-generated code — 2.74x больше уязвимостей

48% AI-предложений кода содержат уязвимости. 80% разработчиков ошибочно считают AI-код более безопасным.
**Mitigation:** SAST (Semgrep/Bandit) на каждый PR.

### 5. Claude Code CVE: ANTHROPIC_BASE_URL redirect

CVE-2026-21852: перенаправление API-трафика через контролируемый URL → утечка API-ключа.
**Mitigation:** Обновлять Claude Code, secrets через GitHub Actions secrets (не env vars).

---

## Gaps и рекомендации

| # | Gap | Risk | Рекомендация | Effort |
|---|-----|------|--------------|--------|
| G1 | Нет secret scanning | HIGH | gitleaks pre-commit + CI | 2 ч |
| G2 | Deny-rules неполные | HIGH | Расширить до `**/*.pem`, `**/*.key`, `**/.env*` | 30 мин |
| G3 | Нет SAST в CI | HIGH | Semgrep/Bandit в GitHub Actions | 3 ч |
| G4 | CSP `unsafe-inline` | MEDIUM | Nonce-based CSP (FastAPI middleware) | 1 день |
| G5 | Нет SCA | MEDIUM | `uv pip audit` в CI | 2 ч |
| G6 | JWT без refresh rotation | MEDIUM | Access=15мин, refresh=7дн, single-use | 2 дня |
| G7 | Нет prompt injection sanitization | MEDIUM | `strip_prompt_injection()` в src/utils/ | 4 ч |
| G8 | Secrets через env_file | LOW | Docker secrets (tmpfs) для prod | 1 день |
| G9 | Security audit устарел | LOW | Semgrep + Bandit scan на src/ | 4 ч |

---

## Quick wins (P0)

**P0-1: Расширить deny-rules** (30 мин)

```json
{
  "permissions": {
    "deny": [
      "Read(.env)", "Read(.env.*)", "Read(**/.env)", "Read(**/.env.*)",
      "Read(**/*.pem)", "Read(**/*.key)", "Read(**/*.p12)",
      "Edit(.env)", "Edit(.env.*)", "Edit(**/.env)", "Edit(**/.env.*)"
    ]
  }
}
```

**P0-2: gitleaks pre-commit** (2 ч)

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/gitleaks/gitleaks
    rev: v8.21.0
    hooks:
      - id: gitleaks
        args: ["--staged"]
```

**P0-3: pip-audit в CI** (2 ч)

```bash
uv run pip-audit --requirement <(uv export --format requirements-txt)
```

---

## Strategic improvements (P1)

**P1-1: Semgrep в GitHub Actions**

```yaml
- name: Semgrep scan
  uses: semgrep/semgrep-action@v1
  with:
    config: "p/python p/secrets p/owasp-top-ten p/jwt"
```

**P1-2: Nonce-based CSP** — генерировать nonce в FastAPI middleware, убрать `unsafe-inline`.

**P1-3: Refresh token rotation** — access=15мин, refresh=7дн, single-use, SHA-256 hash в БД.

**P1-4: Prompt injection sanitization** — regex-фильтр `system:`, `assistant:`, `ignore previous` в RSS-парсере.

**P1-5: Повторный security audit** — Semgrep + Bandit на весь src/ после v0.7.1→v0.9.5 изменений.

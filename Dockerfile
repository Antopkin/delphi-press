# syntax=docker/dockerfile:1

# ── Stage 0: CSS Builder (Tailwind CSS) ──────────────────────────────────────
FROM node:20-alpine AS css-builder

WORKDIR /build
COPY package.json package-lock.json ./
RUN npm ci --ignore-scripts
COPY postcss.config.mjs ./
COPY src/web/static/css/input.css ./src/web/static/css/
COPY src/web/templates/ ./src/web/templates/
RUN npx postcss src/web/static/css/input.css -o src/web/static/css/tailwind.css


# ── Stage 1: Builder ─────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /uvx /bin/

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

# Layer 1: dependencies (cached unless pyproject.toml/uv.lock change)
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-install-project --no-dev
# Layer 2: application code
COPY src/ ./src/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable

# ── Stage 2: Docs Builder (MkDocs) ───────────────────────────────────────────
FROM python:3.12-slim AS docs-builder

WORKDIR /build
COPY docs-site/ docs-site/
RUN pip install --no-cache-dir \
      mkdocs-material pymdown-extensions \
      mkdocs-llmstxt mkdocs-include-markdown-plugin mkdocs-copy-to-llm \
    && cd docs-site && mkdocs build

# ── Stage 3: Runtime ─────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

RUN apt-get update && \
    apt-get install -y --no-install-recommends curl tini && \
    rm -rf /var/lib/apt/lists/*

# Non-root user
RUN groupadd -g 1001 appgroup && \
    useradd -u 1001 -g appgroup -m -d /home/appuser -s /bin/false appuser

# Copy virtualenv and source
COPY --from=builder --chown=appuser:appgroup /app/.venv /app/.venv
COPY --from=builder --chown=appuser:appgroup /app/src /app/src
# Copy compiled CSS from node builder (overwrite with fresh build)
COPY --from=css-builder --chown=appuser:appgroup /build/src/web/static/css/tailwind.css /app/src/web/static/css/tailwind.css

# Download script (for auto-download in entrypoint)
COPY --chown=appuser:appgroup scripts/download_profiles.py /app/scripts/download_profiles.py

# Entrypoint (downloads profiles if missing)
COPY --chown=appuser:appgroup docker-entrypoint.sh /app/docker-entrypoint.sh
RUN chmod +x /app/docker-entrypoint.sh

# Copy built MkDocs site
COPY --from=docs-builder /build/docs-site/site /app/docs-site/site

# Data directories (SQLite + inverse profiles)
RUN mkdir -p /app/data /app/data/inverse && chown -R appuser:appgroup /app/data

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH="/app"

WORKDIR /app
USER appuser

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/health || exit 1

ENTRYPOINT ["tini", "--", "/app/docker-entrypoint.sh"]
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--proxy-headers", "--forwarded-allow-ips", "*"]

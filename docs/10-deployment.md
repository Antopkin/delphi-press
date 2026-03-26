# 10 -- Деплой и инфраструктура

> Реализуемые файлы: `Dockerfile`, `docker-compose.yml`, `nginx/nginx.conf`, `.env.example`

---

## Обзор

Деплой Foresighting News -- 4 контейнера на одном VPS через Docker Compose:
- **app** -- FastAPI/Uvicorn (веб + API + SSE)
- **worker** -- ARQ worker (пайплайн прогнозирования)
- **redis** -- брокер задач + pub/sub для SSE
- **nginx** -- reverse proxy + SSL termination

Данные хранятся на хосте через Docker volumes: SQLite-файл, кэш, Let's Encrypt сертификаты.

Ключевые принципы:
- **Минимальный overhead**: один VPS, без Kubernetes, без managed services
- **Воспроизводимость**: `docker compose up -d` -- единственная команда для запуска
- **Безопасность**: non-root user, SSL обязателен, `.env` вне контейнера
- **Backup**: один файл `foresighting.db` -- достаточно `cp` для бэкапа

---

## 1. Dockerfile (multi-stage build)

```dockerfile
# ==============================================================
# Foresighting News -- Multi-stage Dockerfile
# ==============================================================
# Stage 1: builder -- установка зависимостей через uv
# Stage 2: runtime -- минимальный образ с приложением
# ==============================================================

# ---- Stage 1: Builder ----
FROM python:3.12-slim AS builder

# Установка uv (fast Python package manager)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /build

# Копирование файлов зависимостей
COPY pyproject.toml uv.lock* ./

# Установка зависимостей в виртуальное окружение
# --no-dev: без dev-зависимостей (pytest, ruff)
# --frozen: строгое соответствие lockfile
RUN uv sync --no-dev --frozen --no-editable 2>/dev/null || \
    uv sync --no-dev --no-editable

# Копирование исходного кода
COPY src/ ./src/
COPY alembic.ini* ./
COPY alembic/ ./alembic/ 2>/dev/null || true


# ---- Stage 2: Runtime ----
FROM python:3.12-slim AS runtime

# Системные зависимости для Playwright и общие
RUN apt-get update && apt-get install -y --no-install-recommends \
        # Playwright browser dependencies
        libnss3 \
        libnspr4 \
        libdbus-1-3 \
        libatk1.0-0 \
        libatk-bridge2.0-0 \
        libcups2 \
        libdrm2 \
        libxkbcommon0 \
        libxcomposite1 \
        libxdamage1 \
        libxfixes3 \
        libxrandr2 \
        libgbm1 \
        libpango-1.0-0 \
        libcairo2 \
        libasound2 \
        libatspi2.0-0 \
        # Fonts for page rendering
        fonts-liberation \
        fonts-noto-cjk \
        # Utilities
        curl \
        tini \
    && rm -rf /var/lib/apt/lists/*

# Создание non-root пользователя
RUN groupadd --gid 1000 appuser && \
    useradd --uid 1000 --gid appuser --shell /bin/bash --create-home appuser

WORKDIR /app

# Копирование виртуального окружения из builder
COPY --from=builder /build/.venv /app/.venv

# Копирование исходного кода
COPY --from=builder /build/src /app/src
COPY --from=builder /build/alembic.ini /app/alembic.ini 2>/dev/null || true
COPY --from=builder /build/alembic /app/alembic 2>/dev/null || true

# Установка Playwright browsers (только Chromium)
ENV PATH="/app/.venv/bin:$PATH"
RUN playwright install chromium 2>/dev/null || true

# Создание директории данных
RUN mkdir -p /app/data && chown -R appuser:appuser /app

# Переключение на non-root
USER appuser

# Environment
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app"

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/health || exit 1

# По умолчанию -- запуск FastAPI (переопределяется для worker)
EXPOSE 8000

# tini как PID 1 для корректной обработки сигналов
ENTRYPOINT ["tini", "--"]

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
```

### Пояснения к Dockerfile

| Решение | Обоснование |
|---|---|
| `python:3.12-slim` | Минимальный Debian-based образ, ~150 MB. Alpine ломает Playwright |
| `uv` вместо `pip` | 10-50x быстрее install, поддержка lockfile |
| Multi-stage build | Builder ~800 MB, runtime ~500 MB (с Playwright browsers) |
| `tini` as PID 1 | Корректная обработка SIGTERM для graceful shutdown |
| Non-root `appuser` | Безопасность: даже при RCE -- нет root-доступа |
| Playwright Chromium only | Не ставим Firefox/WebKit -- не нужны, экономия ~200 MB |
| `HEALTHCHECK` | Docker отслеживает состояние контейнера |

---

## 2. docker-compose.yml

```yaml
# ==============================================================
# Foresighting News -- Docker Compose
# ==============================================================
# 4 сервиса: app, worker, redis, nginx
# ==============================================================

version: "3.9"

services:
  # ---- FastAPI Application ----
  app:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: foresighting-app
    restart: unless-stopped
    env_file: .env
    environment:
      - DATABASE_URL=sqlite+aiosqlite:///data/foresighting.db
      - REDIS_URL=redis://redis:6379
    volumes:
      - app-data:/app/data
    networks:
      - internal
    depends_on:
      redis:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/api/v1/health"]
      interval: 30s
      timeout: 10s
      start_period: 15s
      retries: 3
    # Не экспонируем порт наружу -- только через nginx
    expose:
      - "8000"
    deploy:
      resources:
        limits:
          memory: 1G
          cpus: "1.0"

  # ---- ARQ Worker ----
  worker:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: foresighting-worker
    restart: unless-stopped
    env_file: .env
    environment:
      - DATABASE_URL=sqlite+aiosqlite:///data/foresighting.db
      - REDIS_URL=redis://redis:6379
    # Переопределение CMD для запуска воркера вместо FastAPI
    command: ["arq", "src.worker.WorkerSettings"]
    volumes:
      - app-data:/app/data
    networks:
      - internal
    depends_on:
      redis:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "arq", "--check", "src.worker.WorkerSettings"]
      interval: 60s
      timeout: 10s
      start_period: 10s
      retries: 3
    deploy:
      resources:
        limits:
          memory: 2G
          cpus: "1.5"

  # ---- Redis ----
  redis:
    image: redis:7-alpine
    container_name: foresighting-redis
    restart: unless-stopped
    # Конфигурация Redis
    command: >
      redis-server
        --maxmemory 256mb
        --maxmemory-policy allkeys-lru
        --save 60 1000
        --save 300 100
        --appendonly yes
        --appendfsync everysec
    volumes:
      - redis-data:/data
    networks:
      - internal
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      start_period: 5s
      retries: 5
    # Не экспонируем наружу
    expose:
      - "6379"
    deploy:
      resources:
        limits:
          memory: 512M
          cpus: "0.5"

  # ---- Nginx Reverse Proxy ----
  nginx:
    image: nginx:alpine
    container_name: foresighting-nginx
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/nginx.conf:ro
      - certbot-etc:/etc/letsencrypt:ro
      - certbot-var:/var/lib/letsencrypt
      - certbot-webroot:/var/www/certbot:ro
    networks:
      - internal
    depends_on:
      app:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "wget", "--spider", "-q", "http://localhost/api/v1/health"]
      interval: 30s
      timeout: 10s
      retries: 3

  # ---- Certbot (SSL certificate management) ----
  certbot:
    image: certbot/certbot:latest
    container_name: foresighting-certbot
    volumes:
      - certbot-etc:/etc/letsencrypt
      - certbot-var:/var/lib/letsencrypt
      - certbot-webroot:/var/www/certbot
    # Автообновление: запускается по расписанию (см. cron ниже)
    # При первом запуске -- вручную (см. секцию "SSL Setup")
    entrypoint: "/bin/sh -c 'trap exit TERM; while :; do certbot renew --webroot -w /var/www/certbot --quiet; sleep 12h & wait $${!}; done;'"
    depends_on:
      - nginx


# ---- Volumes ----
volumes:
  app-data:
    driver: local
    driver_opts:
      type: none
      o: bind
      device: ./data
  redis-data:
    driver: local
  certbot-etc:
    driver: local
  certbot-var:
    driver: local
  certbot-webroot:
    driver: local


# ---- Networks ----
networks:
  internal:
    driver: bridge
```

### Описание сервисов

| Сервис | Образ | RAM лимит | CPU лимит | Порты | Назначение |
|---|---|---|---|---|---|
| `app` | custom (Dockerfile) | 1 GB | 1.0 | 8000 (internal) | FastAPI + SSE |
| `worker` | custom (Dockerfile) | 2 GB | 1.5 | -- | ARQ пайплайн |
| `redis` | redis:7-alpine | 512 MB | 0.5 | 6379 (internal) | Queue + pub/sub |
| `nginx` | nginx:alpine | -- | -- | 80, 443 | Reverse proxy + SSL |
| `certbot` | certbot/certbot | -- | -- | -- | SSL auto-renewal |

### Описание volumes

| Volume | Mount | Назначение |
|---|---|---|
| `app-data` | `/app/data` (bind mount to `./data`) | SQLite DB, кэш скрейпера |
| `redis-data` | `/data` | Redis RDB + AOF snapshots |
| `certbot-etc` | `/etc/letsencrypt` | SSL-сертификаты |
| `certbot-var` | `/var/lib/letsencrypt` | Certbot state |
| `certbot-webroot` | `/var/www/certbot` | ACME challenge files |

### Порядок запуска

```
redis (healthy) -> app (healthy) -> nginx -> certbot
                -> worker
```

Worker и app запускаются параллельно после ready Redis. Nginx ждёт healthy app. Certbot ждёт nginx.

---

## 3. Nginx конфигурация (`nginx/nginx.conf`)

```nginx
# ==============================================================
# Foresighting News -- Nginx Configuration
# ==============================================================
# Reverse proxy + SSL termination + rate limiting
# ==============================================================

worker_processes auto;
error_log /var/log/nginx/error.log warn;
pid /var/run/nginx.pid;

events {
    worker_connections 1024;
}

http {
    include       /etc/nginx/mime.types;
    default_type  application/octet-stream;

    # --- Logging ---
    log_format main '$remote_addr - $remote_user [$time_local] '
                    '"$request" $status $body_bytes_sent '
                    '"$http_referer" "$http_user_agent" '
                    'rt=$request_time';
    access_log /var/log/nginx/access.log main;

    # --- Performance ---
    sendfile on;
    tcp_nopush on;
    tcp_nodelay on;
    keepalive_timeout 65;
    types_hash_max_size 2048;

    # --- Gzip ---
    gzip on;
    gzip_vary on;
    gzip_proxied any;
    gzip_comp_level 6;
    gzip_types
        text/plain
        text/css
        text/xml
        text/javascript
        application/json
        application/javascript
        application/xml
        application/rss+xml
        image/svg+xml;

    # --- Rate Limiting ---
    # Зона для общих запросов: 10 req/s per IP
    limit_req_zone $binary_remote_addr zone=general:10m rate=10r/s;

    # Зона для API создания прогнозов: 2 req/min per IP (дорогая операция)
    limit_req_zone $binary_remote_addr zone=predictions:10m rate=2r/m;

    # Зона для SSE: 5 соединений per IP
    limit_conn_zone $binary_remote_addr zone=sse_conn:10m;

    # --- Upstream ---
    upstream app {
        server app:8000;
    }

    # --- HTTP -> HTTPS redirect ---
    server {
        listen 80;
        server_name _;

        # Let's Encrypt ACME challenge
        location /.well-known/acme-challenge/ {
            root /var/www/certbot;
        }

        # Redirect all other HTTP to HTTPS
        location / {
            return 301 https://$host$request_uri;
        }
    }

    # --- HTTPS Server ---
    server {
        listen 443 ssl http2;
        server_name _;  # Заменить на реальный домен

        # --- SSL Configuration ---
        ssl_certificate     /etc/letsencrypt/live/your-domain.com/fullchain.pem;
        ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;

        # Modern SSL settings
        ssl_protocols TLSv1.2 TLSv1.3;
        ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384;
        ssl_prefer_server_ciphers off;
        ssl_session_cache shared:SSL:10m;
        ssl_session_timeout 1d;
        ssl_session_tickets off;

        # HSTS
        add_header Strict-Transport-Security "max-age=63072000" always;

        # --- Security Headers ---
        add_header X-Frame-Options "SAMEORIGIN" always;
        add_header X-Content-Type-Options "nosniff" always;
        add_header X-XSS-Protection "1; mode=block" always;
        add_header Referrer-Policy "strict-origin-when-cross-origin" always;

        # --- Request size limit ---
        client_max_body_size 1m;

        # --- Static files (served by nginx directly) ---
        location /static/ {
            alias /app/src/web/static/;
            expires 30d;
            add_header Cache-Control "public, immutable";
            access_log off;
        }

        # --- SSE endpoint (special proxy settings) ---
        location /api/v1/predictions/ {
            # Rate limit for POST (create prediction)
            limit_req zone=predictions burst=3 nodelay;

            # SSE-specific headers for streaming endpoints
            proxy_pass http://app;
            proxy_http_version 1.1;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_set_header Connection "";

            # SSE: disable buffering, long timeouts
            proxy_buffering off;
            proxy_cache off;
            proxy_read_timeout 180s;
            proxy_send_timeout 180s;

            # SSE keepalive
            chunked_transfer_encoding on;
        }

        # --- SSE stream endpoint (explicit) ---
        location ~ /api/v1/predictions/.+/stream$ {
            limit_conn sse_conn 5;

            proxy_pass http://app;
            proxy_http_version 1.1;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_set_header Connection "";

            # Critical for SSE: no buffering
            proxy_buffering off;
            proxy_cache off;
            proxy_read_timeout 600s;
            proxy_send_timeout 600s;

            # No content type sniffing
            add_header X-Accel-Buffering no;

            chunked_transfer_encoding on;
        }

        # --- API endpoints ---
        location /api/ {
            limit_req zone=general burst=20 nodelay;

            proxy_pass http://app;
            proxy_http_version 1.1;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }

        # --- Web pages (HTML) ---
        location / {
            limit_req zone=general burst=20 nodelay;

            proxy_pass http://app;
            proxy_http_version 1.1;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }

        # --- Error pages ---
        error_page 502 503 504 /50x.html;
        location = /50x.html {
            root /usr/share/nginx/html;
        }
    }
}
```

### Rate limiting сводка

| Зона | Rate | Burst | Эндпоинты | Обоснование |
|---|---|---|---|---|
| `general` | 10 req/s per IP | 20 | `/api/*`, `/` | Защита от DoS |
| `predictions` | 2 req/min per IP | 3 | `POST /api/v1/predictions` | Один прогноз ~$30, защита от спама |
| `sse_conn` | 5 connections per IP | -- | `*/stream` | Ограничение SSE-соединений |

### SSE proxy -- критические настройки

| Директива | Значение | Зачем |
|---|---|---|
| `proxy_buffering off` | Отключает буферизацию | SSE-события доставляются мгновенно |
| `proxy_cache off` | Отключает кэш | Каждый event уникален |
| `proxy_read_timeout 600s` | 10 минут | Пайплайн может работать до 20 мин |
| `proxy_http_version 1.1` | HTTP/1.1 | Keepalive для SSE |
| `Connection ""` | Пустая строка | Не передавать `Connection: close` |
| `X-Accel-Buffering no` | Отключает nginx buffering | Дополнительная гарантия для SSE |
| `chunked_transfer_encoding on` | Chunked | Потоковая передача без Content-Length |

---

## 4. VPS Setup Guide

### Рекомендуемые характеристики VPS

| Параметр | Минимум | Рекомендуется | Обоснование |
|---|---|---|---|
| RAM | 2 GB | 4 GB | Worker держит в памяти PipelineContext (~200 MB) |
| vCPU | 1 | 2 | Параллельные LLM-вызовы (async, но DNS/SSL -- CPU) |
| Диск | 20 GB SSD | 40 GB SSD | SQLite + Playwright browser cache + Docker images |
| Трафик | 1 TB | 2 TB | LLM API -- исходящий, скрейпинг -- входящий |
| ОС | Ubuntu 22.04+ | Ubuntu 24.04 LTS | Стабильность, Docker support |

### Рекомендуемые провайдеры

| Провайдер | Конфигурация | Цена/мес | Примечание |
|---|---|---|---|
| **Hetzner Cloud** | CPX21 (3 vCPU, 4 GB, 80 GB) | ~5 EUR | Лучшее соотношение цена/производительность |
| **DigitalOcean** | Basic (2 vCPU, 4 GB, 80 GB) | ~24 USD | Простой UI, хорошая документация |
| **Vultr** | High Frequency (2 vCPU, 4 GB) | ~24 USD | NVMe SSD, много локаций |

Hetzner -- рекомендуемый вариант: серверы в Европе, минимальная цена, отличная производительность.

### Пошаговая настройка VPS

#### Шаг 1: Базовая настройка сервера

```bash
# Подключение к VPS
ssh root@YOUR_VPS_IP

# Обновление системы
apt update && apt upgrade -y

# Создание пользователя
adduser deploy
usermod -aG sudo deploy

# Настройка SSH (отключение root login)
sed -i 's/PermitRootLogin yes/PermitRootLogin no/' /etc/ssh/sshd_config
systemctl restart sshd

# Firewall
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw enable

# Переключение на пользователя deploy
su - deploy
```

#### Шаг 2: Установка Docker

```bash
# Docker Engine (официальный способ)
curl -fsSL https://get.docker.com | sh

# Добавление пользователя в группу docker
sudo usermod -aG docker deploy

# Перелогин для применения группы
exit
ssh deploy@YOUR_VPS_IP

# Проверка
docker --version
docker compose version
```

#### Шаг 3: Клонирование проекта

```bash
# Создание директории
mkdir -p ~/apps
cd ~/apps

# Клонирование
git clone https://github.com/YOUR_USER/foresighting_news.git
cd foresighting_news

# Создание директории данных
mkdir -p data
```

#### Шаг 4: Конфигурация

```bash
# Копирование шаблона
cp .env.example .env

# Редактирование (обязательные поля)
nano .env

# Минимально необходимые изменения:
# SECRET_KEY=<случайная строка 64 символа>
# OPENROUTER_API_KEY=sk-or-<ваш ключ>
```

Генерация SECRET_KEY:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
```

#### Шаг 5: Настройка домена

1. Купить домен (например, через Namecheap, Cloudflare)
2. Создать A-запись: `foresighting.yourdomain.com` -> `YOUR_VPS_IP`
3. Дождаться пропагации DNS (~5-30 минут)
4. Обновить `nginx/nginx.conf`: заменить `your-domain.com` на реальный домен

#### Шаг 6: Получение SSL-сертификата

```bash
# Первый запуск без SSL (для ACME challenge)
# Временно закомментировать HTTPS server block в nginx.conf
# или использовать HTTP-only конфиг

# Запуск только nginx и certbot
docker compose up -d nginx

# Получение сертификата
docker compose run --rm certbot certonly \
    --webroot \
    --webroot-path=/var/www/certbot \
    --email your-email@example.com \
    --agree-tos \
    --no-eff-email \
    -d foresighting.yourdomain.com

# После получения -- раскомментировать HTTPS block
# и обновить пути к сертификатам в nginx.conf
```

#### Шаг 7: Запуск всех сервисов

```bash
# Сборка образов
docker compose build

# Запуск в фоне
docker compose up -d

# Проверка состояния
docker compose ps

# Проверка логов
docker compose logs -f --tail=50

# Проверка health
curl -s http://localhost/api/v1/health | python3 -m json.tool
```

#### Шаг 8: Заполнение каталога СМИ

```bash
# Запуск seed-скрипта внутри контейнера app
docker compose exec app python scripts/seed_outlets.py
```

---

## 5. SSL Setup (Let's Encrypt)

### Первоначальное получение сертификата

Перед получением SSL-сертификата нужен рабочий nginx на порту 80. Стратегия -- двухэтапный запуск:

**Этап 1: HTTP-only nginx** (временный конфиг без SSL)

Создать временный `nginx/nginx-initial.conf`:

```nginx
# Временный конфиг только для получения SSL-сертификата
worker_processes auto;
events { worker_connections 1024; }

http {
    server {
        listen 80;
        server_name foresighting.yourdomain.com;

        location /.well-known/acme-challenge/ {
            root /var/www/certbot;
        }

        location / {
            return 200 'Waiting for SSL setup...';
            add_header Content-Type text/plain;
        }
    }
}
```

```bash
# Запуск с временным конфигом
docker compose run --rm -v ./nginx/nginx-initial.conf:/etc/nginx/nginx.conf:ro nginx

# Или просто запустить nginx
docker compose up -d nginx

# Получение сертификата
docker compose run --rm certbot certonly \
    --webroot \
    --webroot-path=/var/www/certbot \
    --email admin@yourdomain.com \
    --agree-tos \
    --no-eff-email \
    -d foresighting.yourdomain.com
```

**Этап 2: Переключение на полный конфиг**

```bash
# Обновить nginx.conf -- заменить пути к сертификатам:
# ssl_certificate     /etc/letsencrypt/live/foresighting.yourdomain.com/fullchain.pem;
# ssl_certificate_key /etc/letsencrypt/live/foresighting.yourdomain.com/privkey.pem;

# Перезапуск nginx
docker compose restart nginx
```

### Автообновление сертификатов

Certbot-контейнер в `docker-compose.yml` уже настроен на автообновление (цикл `certbot renew` каждые 12 часов). Nginx нужно перезагружать после обновления сертификата.

Cron job на хосте для reload nginx после renewal:

```bash
# Добавить в crontab (sudo crontab -e)
0 3 * * * cd /home/deploy/apps/foresighting_news && docker compose exec -T nginx nginx -s reload > /dev/null 2>&1
```

Альтернативно -- deploy hook в certbot:

```bash
docker compose run --rm certbot renew \
    --deploy-hook "docker compose exec -T nginx nginx -s reload"
```

### Проверка SSL

```bash
# Проверка сертификата
curl -vI https://foresighting.yourdomain.com 2>&1 | grep -E "(subject|expire|issuer)"

# SSL Labs тест
# Открыть: https://www.ssllabs.com/ssltest/analyze.html?d=foresighting.yourdomain.com
```

---

## 6. Мониторинг

### Health check endpoint

Основной инструмент мониторинга -- `GET /api/v1/health` (описан в `08-api-backend.md`).

```bash
# Простая проверка (добавить в cron каждые 5 минут)
curl -sf https://foresighting.yourdomain.com/api/v1/health || \
    echo "ALERT: Foresighting News is down" | mail -s "Health Check Failed" admin@yourdomain.com
```

### Docker-логи

```bash
# Все сервисы в реальном времени
docker compose logs -f --tail=100

# Только worker (для отладки пайплайна)
docker compose logs -f worker --tail=200

# Только ошибки
docker compose logs --since 1h | grep -i error

# Экспорт логов в файл
docker compose logs --no-color > /tmp/foresighting-logs.txt
```

### Мониторинг ресурсов

```bash
# Потребление ресурсов контейнерами
docker stats --no-stream

# Размер SQLite базы
ls -lh data/foresighting.db

# Размер Docker volumes
docker system df -v

# Свободное место на диске
df -h /
```

### Мониторинг SQLite

```bash
# Размер БД
docker compose exec app python -c "
import os
size = os.path.getsize('data/foresighting.db')
print(f'DB size: {size / 1024 / 1024:.1f} MB')
"

# Количество записей
docker compose exec app python -c "
import sqlite3
conn = sqlite3.connect('data/foresighting.db')
for table in ['predictions', 'headlines', 'pipeline_steps', 'outlets']:
    count = conn.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
    print(f'{table}: {count} rows')
conn.close()
"
```

### Бэкап

SQLite -- один файл. Бэкап тривиален:

```bash
# Простой бэкап (при остановленном воркере)
cp data/foresighting.db data/backup-$(date +%Y%m%d).db

# Безопасный бэкап (без остановки -- через SQLite backup API)
docker compose exec app python -c "
import sqlite3
src = sqlite3.connect('data/foresighting.db')
dst = sqlite3.connect('data/backup-safe.db')
src.backup(dst)
dst.close()
src.close()
print('Backup completed')
"

# Cron для ежедневного бэкапа (добавить в crontab)
0 4 * * * cd /home/deploy/apps/foresighting_news && \
    docker compose exec -T app python -c "import sqlite3; src=sqlite3.connect('data/foresighting.db'); dst=sqlite3.connect('data/backup-\$(date +\%Y\%m\%d).db'); src.backup(dst); dst.close(); src.close()" && \
    find data/ -name 'backup-*.db' -mtime +7 -delete
```

### Алерты (простой вариант)

Cron-based мониторинг (без дополнительных сервисов):

```bash
#!/bin/bash
# /home/deploy/apps/foresighting_news/scripts/monitor.sh

set -e

DOMAIN="foresighting.yourdomain.com"
ALERT_EMAIL="admin@yourdomain.com"

# 1. Health check
if ! curl -sf "https://${DOMAIN}/api/v1/health" > /dev/null 2>&1; then
    echo "Health check failed" | mail -s "[ALERT] Foresighting Down" "$ALERT_EMAIL"
fi

# 2. Disk space (<10% free)
FREE_PCT=$(df / --output=pcent | tail -1 | tr -dc '0-9')
if [ "$FREE_PCT" -gt 90 ]; then
    echo "Disk usage: ${FREE_PCT}%" | mail -s "[ALERT] Low Disk Space" "$ALERT_EMAIL"
fi

# 3. SQLite size (>1 GB)
DB_SIZE=$(stat -c%s data/foresighting.db 2>/dev/null || echo 0)
if [ "$DB_SIZE" -gt 1073741824 ]; then
    SIZE_MB=$((DB_SIZE / 1024 / 1024))
    echo "DB size: ${SIZE_MB} MB" | mail -s "[ALERT] Large Database" "$ALERT_EMAIL"
fi

# 4. Docker containers running
RUNNING=$(docker compose ps --format json | python3 -c "import sys,json; data=[json.loads(l) for l in sys.stdin]; print(sum(1 for d in data if d.get('State')=='running'))")
if [ "$RUNNING" -lt 4 ]; then
    echo "Only $RUNNING containers running" | mail -s "[ALERT] Container Down" "$ALERT_EMAIL"
fi
```

```bash
# Добавить в crontab (каждые 5 минут)
*/5 * * * * /home/deploy/apps/foresighting_news/scripts/monitor.sh > /dev/null 2>&1
```

---

## 7. Обновление приложения

```bash
# 1. Получить обновления
cd /home/deploy/apps/foresighting_news
git pull origin main

# 2. Пересобрать образы
docker compose build

# 3. Перезапуск с zero-downtime (app + worker)
docker compose up -d --no-deps --build app worker

# 4. Проверка
docker compose ps
curl -s https://foresighting.yourdomain.com/api/v1/health
```

### Откат

```bash
# Посмотреть предыдущие образы
docker images | grep foresighting

# Откат кода
git log --oneline -5
git checkout <previous-commit-hash>

# Пересборка
docker compose build
docker compose up -d --no-deps --build app worker
```

---

## 8. Типичные проблемы и решения

| Проблема | Диагностика | Решение |
|---|---|---|
| `502 Bad Gateway` | `docker compose logs app` | App не стартовал. Проверить `.env`, зависимости |
| SSE не работает через nginx | `curl -N http://app:8000/api/v1/predictions/ID/stream` | Проверить `proxy_buffering off` в nginx |
| SQLite `database is locked` | Два процесса пишут одновременно | `workers=1` в конфиге, один воркер |
| Redis `Connection refused` | `docker compose logs redis` | Redis не стартовал или OOM |
| SSL certificate expired | `openssl s_client -connect domain:443` | `docker compose run --rm certbot renew` |
| Disk full | `df -h /` | Очистить старые бэкапы, `docker system prune` |
| Worker OOM killed | `dmesg | grep -i oom` | Увеличить `memory` limit в compose |
| Playwright browser not found | `docker compose exec app playwright install chromium` | Пересобрать образ |

---

## 9. Полная последовательность первого деплоя

```
1.  Заказать VPS (Hetzner CPX21, Ubuntu 24.04)
2.  Настроить SSH + firewall
3.  Установить Docker + Docker Compose
4.  Привязать домен (A record -> VPS IP)
5.  git clone проекта
6.  cp .env.example .env && nano .env
7.  mkdir -p data
8.  Получить SSL-сертификат (certbot)
9.  Обновить nginx.conf (пути к сертификатам, имя домена)
10. docker compose build
11. docker compose up -d
12. docker compose exec app python scripts/seed_outlets.py
13. Проверить: curl https://domain/api/v1/health
14. Настроить cron (бэкап + мониторинг + certbot reload)
```

Ожидаемое время настройки: 30-60 минут (при наличии домена и API-ключей).

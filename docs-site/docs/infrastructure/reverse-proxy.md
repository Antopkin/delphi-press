# Reverse proxy (multi-tenant nginx)

Сервис `delphi-press-nginx-1` на VPS выполняет функцию не только реверс-прокси для самого delphi-press, но и **общего reverse-proxy хаба** для нескольких независимых проектов на одном сервере. Эта страница описывает текущую архитектуру, причины её выбора и паттерн добавления новых доменов.

## Обзор

```
                     Internet (HTTPS 443)
                            │
                            ▼
           ┌────────────────────────────────────┐
           │     delphi-press-nginx-1           │
           │     (nginx:1.27-alpine)            │
           │     0.0.0.0:80, 0.0.0.0:443        │
           └─┬──────────────┬──────────────┬────┘
             │              │              │
     delphi_frontend    faun_net      outline-net
     (internal)        (external)    (external)
             │              │              │
             ▼              ▼              ▼
      ┌──────────┐   ┌─────────────┐   ┌───────────────┐
      │   app    │   │ faun-cloud-1│   │ outline-moskino│
      │ :8000    │   │   :8000     │   │    :3000      │
      └──────────┘   └─────────────┘   └───────────────┘
```

**Три server blocks**, три отдельных сертификата Let's Encrypt:

| Домен                              | Upstream                   | Docker network | Комментарий                               |
|------------------------------------|----------------------------|----------------|-------------------------------------------|
| `delphi.antopkin.ru`               | `app:8000`                 | `delphi_frontend` (internal) | Основной сервис delphi-press.        |
| `faun.antopkin.ru`                 | `faun-cloud-1:8000`        | `faun_net` (external)        | Отдельный docker-compose проект.     |
| `moskino-workshops.antopkin.ru` *  | `outline-moskino:3000`     | `outline-net` (external)     | Outline CMS для команды Москино.     |

\* планируется / добавляется.

!!! note "Почему один nginx, а не отдельный reverse-proxy"
    Порты 80 и 443 на хосте может занять только один процесс. Альтернативы — Caddy/Traefik как отдельный хост-процесс + перенос `delphi-press-nginx-1` на `127.0.0.1:8080` — означали бы правку production-nginx-конфига, включая критичные SSE-настройки. Выбрано минимально инвазивное расширение существующего nginx.

## Подключение внешних Docker-сетей

По умолчанию `delphi-press-nginx-1` находится только в своей собственной сети `delphi_frontend`. Чтобы он мог обращаться к контейнерам из других docker-compose проектов по имени, эти сети подключаются **как внешние**:

```yaml
# docker-compose.yml (фрагмент сервиса nginx)
services:
  nginx:
    networks:
      - frontend
      - faun_net      # external, owned by faun/docker-compose.yml
      # - outline-net  # planned: external, owned by moskino_site/docker-compose.yml
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/nginx.conf:ro
      - ./nginx/security-headers.conf:/etc/nginx/conf.d/security-headers.conf:ro
      - ./nginx/faun-security-headers.conf:/etc/nginx/conf.d/faun-security-headers.conf:ro
      - /etc/letsencrypt:/etc/letsencrypt:ro
      - ./src/web/static:/var/www/static:ro
      - docs_data:/var/www/docs:ro

networks:
  frontend:
    driver: bridge
  faun_net:
    external: true
  # outline-net:
  #   external: true
```

!!! warning "external: true"
    `external: true` означает, что сеть **уже должна существовать** — `docker compose` не создаёт и не удаляет её. Владелец сети — тот проект, который её заводит (например `faun`'s own docker-compose.yml). Это обеспечивает, что `docker compose down` в delphi-press не снесёт сеть и не уронит чужие контейнеры.

## Runtime DNS resolution для upstream'ов

**Проблема:** `proxy_pass http://faun-cloud-1:8000;` с голым hostname вызывает **resolution в момент парсинга конфига**. На холодном старте `delphi-press-nginx-1` Docker embedded DNS ещё не успевает зарегистрировать контейнер в `faun_net`, и nginx падает с:

```
[emerg] host not found in upstream "faun-cloud-1" in /etc/nginx/nginx.conf
```

и уходит в restart-loop до ручного `docker compose restart nginx`.

**Решение:** runtime DNS resolution через Docker-овский embedded resolver + переменная в `proxy_pass`:

```nginx
http {
    # Docker bridge-network embedded DNS. Hardcoded в демоне Docker.
    # valid=30s переопределяет дефолтный TTL=600s от Docker DNS.
    # ipv6=off потому что Docker DNS не возвращает AAAA для bridge-сетей.
    resolver 127.0.0.11 valid=30s ipv6=off;

    # ...

    server {
        listen 443 ssl;
        server_name faun.antopkin.ru;

        location / {
            set $faun_upstream "faun-cloud-1:8000";
            proxy_pass http://$faun_upstream;
            # ... остальные proxy_set_header
        }
    }
}
```

Когда `proxy_pass` содержит **переменную**, nginx откладывает resolution до момента запроса и использует `resolver`. Если upstream недоступен на первом запросе — вернёт 502, но не умрёт. При последующем появлении контейнера в DNS запросы пройдут нормально.

!!! note "Почему delphi's `upstream app` не переписан"
    Блок `upstream app { server app:8000; }` для самого delphi оставлен как есть. `app` находится в том же docker-compose, что и nginx, и запускается через `depends_on: app: { condition: service_healthy }` — то есть DNS для него гарантированно стабилен к моменту старта nginx. Parse-time resolution здесь не проблема, и `upstream` с `keepalive 16` даёт пул постоянных соединений.

## Как добавить новый домен

Пошаговая процедура для ещё одного проекта, живущего в своём docker-compose (например, Outline для новой команды):

1. **В своём docker-compose.yml** объявить внешнюю сеть и контейнер в ней, не публикуя порты на хост:
   ```yaml
   services:
     <my-app>:
       container_name: <my-app>
       networks:
         - my-app-net
   networks:
     my-app-net:
       name: my-app-net
   ```
   Сеть **создаёт сам этот проект** (`docker compose up -d` или явным `docker network create`).

2. **В delphi-press docker-compose.yml** добавить сеть в `networks` у сервиса `nginx` и в верхнеуровневый `networks` как `external: true`. Никаких `depends_on` — nginx не должен ждать чужой контейнер, эту задачу закрывает runtime DNS (см. выше).

3. **В delphi-press nginx/nginx.conf** добавить два server-блока (HTTP redirect + HTTPS) по паттерну faun. Обязательно: `set $var "..."; proxy_pass http://$var;` вместо голого hostname. Если нужен отдельный CSP, создать `nginx/<project>-security-headers.conf` и смонтировать в `/etc/nginx/conf.d/`.

4. **Выпустить TLS-сертификат** через `certbot certonly --standalone` с pre/post-hook останова и запуска nginx (см. [деплой-скрипты](scripts.md)). Текущая схема сертификатов живёт в `/etc/letsencrypt/renewal/*.conf` с `authenticator = standalone`.

5. **Открыть PR** в `Antopkin/delphi-press`, дождаться зелёного CI, merge. Deploy-workflow сделает `git pull --ff-only && docker compose down && build && up -d`, выполнит health-check через `https://delphi.antopkin.ru/api/v1/health` и завершится успехом. Ожидаемый downtime всех обслуживаемых доменов — ~30 секунд.

## Что проверить после deploy

```bash
# Основной сервис работает
curl -sI https://delphi.antopkin.ru/
curl -s https://delphi.antopkin.ru/api/v1/health

# SSE-стрим не буферизуется (проверка что новые server blocks не задели существующий)
curl -N https://delphi.antopkin.ru/api/v1/predictions/<id>/stream

# Другие домены отвечают
curl -sI https://faun.antopkin.ru/
# curl -sI https://moskino-workshops.antopkin.ru/  # когда добавится

# nginx не в crash loop
ssh antopkin-vps 'docker inspect delphi-press-nginx-1 --format "{{.State.Status}} RestartCount={{.RestartCount}}"'
# Ожидаемо: running RestartCount=0

# nginx подключён ко всем нужным сетям
ssh antopkin-vps 'docker inspect delphi-press-nginx-1 --format "{{range \$k, \$v := .NetworkSettings.Networks}}{{\$k}} {{end}}"'
# Ожидаемо: delphi-press_frontend faun_net [outline-net]
```

## Известные ограничения

- **Certbot standalone mode** — выпуск нового сертификата требует короткого останова `delphi-press-nginx-1` (pre-hook → renew → post-hook). Это означает ~30 секунд downtime всех доменов, обслуживаемых этим nginx, во время каждого выпуска. Плановое обновление существующих сертификатов идёт автоматически через `certbot.timer` раз в сутки; замена нужна только при добавлении новых доменов.
- **Нет централизованного rate-limit zone** для кросс-проектных доменов — faun и будущий moskino делят `zone=general` 10r/s, объявленный в `http {}` блоке. Если какому-то домену понадобится свой лимит, завести отдельный `limit_req_zone`.
- **Один `resolver 127.0.0.11`** работает для всех external networks, но требует чтобы все эти сети были **bridge-типа** (overlay-сети Docker Swarm не поддерживаются этим паттерном).

## Источники правды

- **Конфиг:** `nginx/nginx.conf` — фактическое состояние.
- **History:** PR [#10](https://github.com/Antopkin/delphi-press/pull/10) (sync faun state), [#11](https://github.com/Antopkin/delphi-press/pull/11) (runtime DNS resolver), [#12](https://github.com/Antopkin/delphi-press/pull/12) (CI deploy fail-fast).
- **Логи nginx:** `docker logs delphi-press-nginx-1` — access и error пишутся в Docker logging driver (json-file с ротацией 10m×3).

# Безопасность

Delphi Press использует многоуровневый подход к защите: аутентификация на уровне приложения (JWT), шифрование чувствительных данных, защита от CSRF, rate limiting на уровне сервера и TLS для транспортного уровня.

## Обзор уровней защиты

```
┌─────────────────────────────────────────────────────┐
│ TLS/HTTPS (nginx + Let's Encrypt)                   │
├─────────────────────────────────────────────────────┤
│ Rate Limiting (nginx: 10 req/s общее, 5 req/min auth)
├─────────────────────────────────────────────────────┤
│ Security Headers (HSTS, CSP, X-Frame-Options)       │
├─────────────────────────────────────────────────────┤
│ CSRF Protection (Double Submit Cookie)              │
├─────────────────────────────────────────────────────┤
│ JWT Authentication (PyJWT + HS256)                  │
├─────────────────────────────────────────────────────┤
│ Bcrypt Password Hashing (async)                     │
├─────────────────────────────────────────────────────┤
│ Fernet Encryption (user API keys)                   │
└─────────────────────────────────────────────────────┘
```

---

## JWT Аутентификация

### Поток аутентификации

Delphi Press использует **JSON Web Token (JWT)** стандарт (RFC 7519) для stateless аутентификации.

#### Регистрация

```bash
POST /api/v1/auth/register
Content-Type: application/json

{
  "email": "user@example.com",
  "password": "MySecurePassword123"
}
```

**Процесс:**

1. Валидация email (RFC 5322) и пароля (мин. 8 символов)
2. Хеширование пароля с bcrypt (см. ниже)
3. Сохранение пользователя в БД с уникальным UUID
4. Генерация JWT access token с сроком 7 дней
5. Возврат токена клиенту

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer"
}
```

#### Вход в систему

```bash
POST /api/v1/auth/login
Content-Type: application/json

{
  "email": "user@example.com",
  "password": "MySecurePassword123"
}
```

**Процесс:**

1. Поиск пользователя по email (case-sensitive)
2. Проверка пароля через bcrypt
3. Если совпадает — генерация нового JWT токена
4. Если не совпадает — возврат `401 Unauthorized`

!!! warning "Timing attacks"
    Проверка пароля выполняется с защитой от timing attacks благодаря bcrypt, который имеет фиксированное время выполнения независимо от того, где произошла ошибка.

### Структура JWT

Token содержит следующие claims:

```json
{
  "sub": "550e8400-e29b-41d4-a716-446655440000",  // user_id (subject)
  "jti": "a7c5b9e1-2f3d-4a5f-8c9d-0e1f2a3b4c5d",  // JWT ID (уникален)
  "iat": 1701432000,                               // Issued At (timestamp)
  "exp": 1702036800                                // Expiration (7 дней)
}
```

#### JWT ID (jti) — уникальный идентификатор токена

**Назначение:** Каждый токен получает уникальный идентификатор для возможной отозванности (future feature).

```python
# src/security/jwt.py
def create_access_token(user_id: str, secret_key: str, expire_days: int = 7) -> str:
    """Создаёт подписанный JWT с HS256."""
    now = datetime.now(UTC)
    payload = {
        "sub": user_id,
        "jti": str(uuid.uuid4()),  # UUID v4 — 128 бит энтропии
        "iat": now,
        "exp": now + timedelta(days=expire_days),
    }
    return jwt.encode(payload, secret_key, algorithm="HS256")
```

**Генерация:** `uuid.uuid4()` — криптографически случайный UUID (128 бит).

**Использование:**

- Настоящее: идентификация каждого токена (логирование, отладка)
- Будущее: создание реестра отозванных токенов (token blacklist) при logout или смене пароля

**Хранение:** На данный момент `jti` не хранится в БД, но может быть добавлено в таблицу `revoked_tokens` для реализации logout-функции.

### Параметры токена

```python
# src/security/jwt.py
def create_access_token(
    user_id: str,
    secret_key: str,
    expire_days: int = 7,  # TTL: 7 дней
) -> str:
    """Создаёт подписанный JWT с HS256."""
```

**Алгоритм подписи:** HS256 (HMAC-SHA256)

**Срок действия:** 7 дней (настраивается через переменную окружения `JWT_EXPIRE_DAYS`)

**Secret key:** Хранится в переменной окружения `SECRET_KEY` (мин. 32 символа)

!!! danger "SECRET_KEY"
    Никогда не коммитьте `SECRET_KEY` в репозиторий. Используйте `.env.local` или системные переменные окружения.
    
    На продакшене ключ генерируется при развёртывании и хранится в защищённом хранилище.

### Проверка токена

При каждом запросе к защищённому эндпоинту:

```python
# src/api/dependencies.py
async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> User | None:
    """Опциональная авторизация — None если без токена."""
    # 1. Извлечь токен из Bearer header или cookie
    token = credentials.credentials if credentials else request.cookies.get("access_token")
    
    if token is None:
        return None
    
    # 2. Декодировать JWT
    try:
        payload = decode_access_token(token, settings.secret_key)
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return None
    
    # 3. Загрузить пользователя из БД
    user_id = payload.get("sub")
    user = await UserRepository.get_by_id(user_id)
    
    if user is None or not user.is_active:
        return None
    
    return user
```

**Исключения:**

- `jwt.ExpiredSignatureError` — токен истёк
- `jwt.InvalidTokenError` — неверная подпись или формат

### Использование токена

Клиент отправляет токен в заголовке `Authorization`:

```bash
GET /api/v1/predictions
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

---

## Хеширование паролей (bcrypt)

### Алгоритм

Пароли хешируются с помощью **bcrypt** (адаптивная функция вывода ключа):

```python
# src/security/password.py
def hash_password(password: str) -> str:
    """Хеширование пароля с bcrypt."""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
```

**Параметры bcrypt:**

- **Работа:** 12 раундов (по умолчанию в `bcrypt.gensalt()`)
- **Соль:** Автоматически генерируется (128-бит random)
- **Выход:** Base64-кодированная строка (60 символов)

### Пример

```python
# Пароль: "MySecurePassword123"
# Хеш:    "$2b$12$1234567890abcdefghij.1234567890abcdefghij1234567890a"
```

Каждое хеширование даёт разный результат благодаря уникальной соли:

```python
hash1 = hash_password("password")  # $2b$12$...abc123...
hash2 = hash_password("password")  # $2b$12$...xyz789...
# hash1 != hash2, но оба проходят проверку
```

### Асинхронное хеширование

!!! note "Асинхронность"
    Bcrypt использует CPU на 100-300 мс. Для не блокирования FastAPI event loop, хеширование выполняется в отдельном потоке:

```python
# src/security/password.py
async def hash_password_async(password: str) -> str:
    """Неблокирующая обёртка bcrypt."""
    return await asyncio.to_thread(hash_password, password)
```

**Где используется:**

- Во время регистрации: `await hash_password_async(body.password)`
- Во время входа: `await verify_password_async(body.password, user.hashed_password)`

---

## Шифрование API-ключей (Fernet)

### Проблема

Пользователи вводят свои OpenRouter API-ключи в веб-интерфейс. Эти ключи **не должны** храниться в plain text в БД.

### Решение: Fernet

Используется **Fernet** из библиотеки `cryptography` (симметричное шифрование):

```python
# src/security/encryption.py
class KeyVault:
    """Симметричное шифрование/дешифрование пользовательских API-ключей."""
    
    def __init__(self, encryption_key: str) -> None:
        self._fernet = Fernet(encryption_key.encode())
    
    def encrypt(self, plaintext: str) -> str:
        """Зашифровать и вернуть base64-кодированный ciphertext."""
        return self._fernet.encrypt(plaintext.encode()).decode()
    
    def decrypt(self, ciphertext: str) -> str:
        """Расшифровать base64-кодированный ciphertext."""
        return self._fernet.decrypt(ciphertext.encode()).decode()
```

### Поток

**При добавлении ключа:**

```bash
POST /api/v1/keys
Authorization: Bearer <jwt_token>
Content-Type: application/json

{
  "provider": "openrouter",
  "api_key": "sk-or-v1-abc123...",
  "label": "Мой OpenRouter ключ"
}
```

1. Клиент отправляет plain text API-ключ
2. KeyVault шифрует его: `ciphertext = Fernet.encrypt(api_key)`
3. Ciphertext сохраняется в БД (не plain text)
4. Plain text сразу забывается

**При использовании ключа (валидация):**

```bash
POST /api/v1/keys/{key_id}/validate
Authorization: Bearer <jwt_token>
```

1. Извлечь ciphertext из БД
2. KeyVault дешифрует: `plaintext = Fernet.decrypt(ciphertext)`
3. Отправить plain text на OpenRouter (только через HTTPS)
4. Plain text забыть

### Параметры Fernet

```python
# src/main.py (lifespan)
from src.security.encryption import KeyVault

key_vault = KeyVault(settings.fernet_key)  # 32-byte base64-encoded key
```

**Где находится ключ:**

- Переменная окружения: `FERNET_KEY`
- Генерируется при инициализации: `from cryptography.fernet import Fernet; Fernet.generate_key()`
- На продакшене хранится в защищённом хранилище (env vars в Docker)

!!! danger "FERNET_KEY"
    Если `FERNET_KEY` потеряется, все зашифрованные ключи станут неразборчивыми (невозможно восстановить). На продакшене нужны резервные копии.

### Проверка целостности

Если ciphertext повреждён (например, при сбое БД), API вернёт ошибку:

```python
# src/api/keys.py
try:
    key_vault.decrypt(k.encrypted_key)
except Exception:
    health = "corrupted"  # Отметить ключ как поражённый
```

Пользователь может удалить и заново добавить такой ключ.

---

## CSRF Защита

### Уязвимость

Cross-Site Request Forgery (CSRF) — атака, при которой вредоносный сайт заставляет браузер пользователя отправить запрос на Delphi Press с его учётными данными.

**Пример:**

```html
<!-- evil.com -->
<form action="https://delphi.antopkin.ru/api/v1/keys" method="POST">
  <input type="hidden" name="api_key" value="attacker-key">
  <input type="submit" value="Click me">
</form>
```

Если пользователь кликнет, он добавит ключ атакующего в свой аккаунт.

### Защита: Double Submit Cookie

Delphi Press использует паттерн **Double Submit Cookie**:

```python
# src/security/csrf.py
class CSRFMiddleware(BaseHTTPMiddleware):
    """Double Submit Cookie CSRF protection для HTML forms."""
    
    async def dispatch(self, request: Request, ...) -> Response:
        # 1. Извлечь или создать CSRF токен
        token = request.cookies.get("csrf_token") or secrets.token_urlsafe(32)
        request.state.csrf_token = token
        
        # 2. Для безопасных методов (GET, HEAD) — просто установить cookie
        if request.method in {"GET", "HEAD", "OPTIONS"}:
            response = await call_next(request)
            response.set_cookie("csrf_token", token, httponly=False, samesite="lax", path="/")
            return response
        
        # 3. JSON API запросы защищены CORS + SameSite (exempt)
        if "application/json" in request.headers.get("content-type", ""):
            return await call_next(request)
        
        # 4. Form data: проверить токен из cookie и body
        cookie_token = request.cookies.get("csrf_token")
        form_token = form_data.get("csrf_token")
        
        if not secrets.compare_digest(cookie_token, form_token):
            return JSONResponse(status_code=403, content={"detail": "CSRF token mismatch."})
        
        return await call_next(request)
```

#### Генерация токена

**Место:** `src/security/csrf.py`, строка 27

```python
token = request.cookies.get("csrf_token") or secrets.token_urlsafe(32)
```

- `secrets.token_urlsafe(32)` — криптографически случайная строка (256 бит, base64-кодирована в ~43 символа)
- Генерируется один раз при первом GET-запросе к странице
- Устанавливается в HttpOnly=False cookie (требуется для чтения в JavaScript и отправки в форме)

#### Поток валидации

**На странице (Jinja2 шаблон):**

```html
<form method="POST" action="/api/v1/keys">
  <!-- CSRF токен передается как скрытое поле -->
  <input type="hidden" name="csrf_token" value="{{ csrf_token }}">
  
  <!-- Остальные поля -->
  <input type="text" name="api_key" placeholder="sk-or-v1-...">
  <button type="submit">Добавить ключ</button>
</form>
```

**При отправке формы (form data, не JSON):**

1. Browser прочитывает CSRF токен из cookie: `csrf_token_from_cookie`
2. Browser отправляет токен в теле формы: `csrf_token_from_form`
3. Middleware перехватывает запрос
4. Middleware сравнивает `secrets.compare_digest(csrf_token_from_cookie, csrf_token_from_form)`
5. Если совпадает → запрос пропускается дальше
6. Если не совпадает → `403 Forbidden` с сообщением "CSRF token mismatch."

**Защита от timing attacks:** `secrets.compare_digest()` выполняет constant-time сравнение (не выходит рано при первой ошибке).

#### Защищённые эндпоинты

**Требует CSRF токена (form data):**

- `POST /api/v1/keys` — добавление API-ключей
- `DELETE /api/v1/keys/{id}` — удаление API-ключей
- `POST /api/v1/auth/logout` — logout из веб-UI

**Защищены автоматически (CORS + SameSite):**

- `POST /api/v1/predictions` (JSON API)
- `POST /api/v1/auth/login` (JSON API)
- `POST /api/v1/auth/register` (JSON API)

### JSON API запросы

JSON API запросы **защищены автоматически** через CORS и SameSite cookie:

```bash
# JavaScript (same-origin)
fetch('/api/v1/keys', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ api_key: '...' })
})
```

- CSRF токен не требуется (защита через CORS)
- SameSite=Lax cookie не отправляется cross-site
- Вредоносный сайт не может прочитать JWT токен (HttpOnly невозможно из-за архитектуры)

!!! note "HttpOnly Cookie"
    JWT токены хранятся в HttpOnly cookie (`_set_auth_cookie` в `src/web/router.py`). Web UI использует cookie (не `Authorization` заголовок). Это защищает токен от XSS-атак — JavaScript не имеет доступа к cookie.

---

## SSRF Защита

### Уязвимость

Server-Side Request Forgery (SSRF) — когда приложение делает HTTP запросы на адреса, контролируемые пользователем, что позволяет атакующему получить доступ к приватным сетям или metadata endpoints.

**Примеры опасных адресов:**

- `http://127.0.0.1:6379` — локальный Redis (drain учётные данные)
- `http://169.254.169.254/latest/meta-data/` — AWS metadata endpoint (IAM credentials)
- `http://10.0.0.1:8080` — приватная сеть (внутренние сервисы)
- `http://[::1]/admin` — IPv6 loopback

### Решение: URL валидация

Delphi Press валидирует все user-provided URLs перед server-side запросами:

```python
# src/utils/url_validator.py
def validate_url_safe(url: str) -> None:
    """Validate that a URL is safe for server-side requests."""
    parsed = urlparse(url)
    
    # 1. Проверить scheme
    if parsed.scheme not in {"http", "https"}:
        raise SSRFBlockedError(url, f"scheme '{parsed.scheme}' not allowed")
    
    # 2. Проверить hostname не пустой
    if not parsed.hostname:
        raise SSRFBlockedError(url, "no hostname")
    
    # 3. Если hostname — IP литерал, проверить на private ranges
    try:
        addr = ipaddress.ip_address(parsed.hostname)
        if _is_blocked(addr):
            raise SSRFBlockedError(url, f"private IP {addr}")
        return
    except ValueError:
        pass  # Not an IP literal, proceed to DNS resolution
    
    # 4. Если hostname — доменное имя, resolve и проверить IPs
    try:
        results = socket.getaddrinfo(parsed.hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
    except socket.gaierror:
        return  # DNS failure — let the HTTP client handle it
    
    for family, _type, _proto, _canonname, sockaddr in results:
        ip_str = sockaddr[0]
        addr = ipaddress.ip_address(ip_str)
        if _is_blocked(addr):
            raise SSRFBlockedError(url, f"resolves to private IP {addr}")
```

#### Блокированные сети (IPv4 и IPv6)

```python
# src/utils/url_validator.py
_BLOCKED_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),        # Loopback
    ipaddress.ip_network("10.0.0.0/8"),         # Private class A
    ipaddress.ip_network("172.16.0.0/12"),      # Private class B
    ipaddress.ip_network("192.168.0.0/16"),     # Private class C
    ipaddress.ip_network("169.254.0.0/16"),     # Link-local (APIPA)
    ipaddress.ip_network("::1/128"),            # IPv6 loopback
    ipaddress.ip_network("fc00::/7"),           # IPv6 unique local (private)
    ipaddress.ip_network("fe80::/10"),          # IPv6 link-local
]
```

**Покрывает:**

- **127.0.0.0/8** — localhost (127.0.0.1)
- **10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16** — RFC 1918 private ranges
- **169.254.0.0/16** — APIPA (кроме AWS metadata через DNS rebinding в некоторых случаях)
- **IPv6 эквиваленты** — fc00::/7, fe80::/10

#### Использование

```python
# src/data_sources/feed_discovery.py
from src.utils.url_validator import validate_url_safe

async def discover_feeds(outlet_domain: str):
    """Discover RSS feeds for a news outlet."""
    # SSRF protection
    await validate_url_safe_async(f"https://{outlet_domain}")
    
    # Now safe to make HTTP request
    async with httpx.AsyncClient() as client:
        response = await client.get(f"https://{outlet_domain}")
```

**Raises:**

- `SSRFBlockedError(url, reason)` — если URL pointing to blocked network

### Async DNS (не блокирующее разрешение)

#### Проблема

В FastAPI async app, использование `socket.getaddrinfo()` (блокирующий вызов DNS) может заблокировать весь event loop:

```python
# BAD: блокирует весь event loop
results = socket.getaddrinfo("example.com", 80)  # ~50ms DNS query
```

Пока один корутин ждёт DNS разрешения, другие корутины не могут выполняться.

#### Решение: asyncio.to_thread()

```python
# src/utils/url_validator.py
async def validate_url_safe_async(url: str) -> None:
    """Async version — runs DNS resolution in a thread pool."""
    import asyncio
    
    await asyncio.to_thread(validate_url_safe, url)
```

**Как работает:**

1. `asyncio.to_thread(func, args)` запускает `func` в отдельном потоке из `ThreadPoolExecutor`
2. Event loop продолжает обрабатывать другие корутины
3. Когда DNS разрешение завершается, корутин возобновляется с результатом

**Где используется:**

- `await validate_url_safe_async(feed_url)` перед HTTP запросами на внешние сайты

!!! warning "DNS Rebinding"
    Даже с SSRF защитой есть атака **DNS Rebinding**: атакующий контролирует DNS сервер и возвращает разные IPs при повторных запросах (сначала публичный, потом приватный). Mitigation: либо повторная валидация перед HTTP запросом, либо использование DNS-over-HTTPS (DoH).

---

## Fail-fast на секреты

### Проблема

Hardcoded dev секреты в production могут привести к критическим уязвимостям:

- `SECRET_KEY = "dev-insecure-key-change-in-production-32ch"` → все токены подделываются
- `FERNET_KEY = "3FsRWU3nhSsWfUlLDxtlREMWWZvO0a8PPlZi85leT-o="` → все API-ключи расшифровываются

### Решение: Pydantic validators

Delphi Press использует **model validators** (Pydantic v2) для fail-fast при старте в production:

```python
# src/config.py
class Settings(LLMConfig):
    """Центральная конфигурация приложения."""
    
    secret_key: str = Field(
        default="dev-insecure-key-change-in-production-32ch",
        description="Секретный ключ для подписи сессий и CSRF-токенов.",
        min_length=32,
    )
    
    fernet_key: str = Field(
        default="3FsRWU3nhSsWfUlLDxtlREMWWZvO0a8PPlZi85leT-o=",
        description="Fernet encryption key for user API keys (base64, 32 bytes).",
    )
    
    cors_origins: list[str] = Field(
        default=["http://localhost:8000"],
        description="Allowed CORS origins. Set explicitly in production.",
    )
    
    _INSECURE_SECRET_KEY = "dev-insecure-key-change-in-production-32ch"
    _INSECURE_FERNET_KEY = "3FsRWU3nhSsWfUlLDxtlREMWWZvO0a8PPlZi85leT-o="
    
    @model_validator(mode="after")
    def _reject_insecure_defaults_in_production(self) -> Settings:
        """Fail-fast if production runs with hardcoded dev secrets."""
        
        # Only enforce when DEBUG=False AND DELPHI_PRODUCTION=1
        if self.debug or not os.environ.get("DELPHI_PRODUCTION"):
            return self  # Allow in dev/test
        
        # Check SECRET_KEY
        if self.secret_key == self._INSECURE_SECRET_KEY:
            raise ValueError(
                "SECRET_KEY is set to the insecure dev default. "
                "Set a strong SECRET_KEY in .env for production (min 32 chars)."
            )
        
        # Check FERNET_KEY
        if self.fernet_key == self._INSECURE_FERNET_KEY:
            raise ValueError(
                "FERNET_KEY is set to the insecure dev default. "
                "Generate a new key: python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'"
            )
        
        # Check CORS_ORIGINS
        if self.cors_origins == ["*"]:
            raise ValueError(
                "CORS_ORIGINS=['*'] is not allowed in production. "
                "Set explicit origins: CORS_ORIGINS='[\"https://yourdomain.com\"]'"
            )
        
        return self
```

#### Поток

**Development (DEBUG=True или DELPHI_PRODUCTION не установлен):**

```bash
$ python -m src.main
# ✓ Works fine with dev defaults
```

**Production с забытыми секретами:**

```bash
$ docker run -e DELPHI_PRODUCTION=1 -e DEBUG=False <image>
# ValueError: SECRET_KEY is set to the insecure dev default.
# Application REFUSES TO START
```

**Production с правильными секретами:**

```bash
$ docker run \
  -e DELPHI_PRODUCTION=1 \
  -e DEBUG=False \
  -e SECRET_KEY="$(openssl rand -base64 32)" \
  -e FERNET_KEY="$(python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')" \
  <image>
# ✓ Application starts normally
```

#### Где проверяется

- `src/config.py` → `Settings._reject_insecure_defaults_in_production()` (model_validator)
- Вызывается при создании Settings: `get_settings()` → `Settings()` (Pydantic validation)
- Запускается **перед** созданием app, worker'а, DB connection — app не запустится

!!! danger "DELPHI_PRODUCTION флаг"
    В Docker Compose (production) обязательно установить:
    
    ```yaml
    environment:
      DELPHI_PRODUCTION: "1"
      DEBUG: "false"
      SECRET_KEY: "${SECRET_KEY}"
      FERNET_KEY: "${FERNET_KEY}"
    ```
    
    Без флага валидация пропускается (для локальной разработки).

---

## Rate Limiting

### Конфигурация (nginx)

Rate limiting реализован на уровне nginx и включает несколько зон:

```nginx
# nginx/nginx.conf

# Общий лимит: 10 запросов в секунду
limit_req_zone $binary_remote_addr zone=general:10m rate=10r/s;

# Predictions (дорогой эндпоинт): 2 запроса в минуту
limit_req_zone $binary_remote_addr zone=predictions:10m rate=2r/m;

# Auth endpoints (защита от brute-force): 5 запросов в минуту
limit_req_zone $binary_remote_addr zone=auth:10m rate=5r/m;

# SSE подключения: максимум 5 одновременных
limit_conn_zone $binary_remote_addr zone=sse_conn:10m;
```

### Применение по эндпоинтам

| Эндпоинт | Лимит | Burst | Причина |
|----------|-------|-------|---------|
| `POST /api/v1/predictions` | 2 req/min | 3 | Дорогой: 30 LLM-вызовов/запрос |
| `POST /api/v1/auth/login` | 5 req/min | 3 | Защита от brute-force |
| `POST /api/v1/auth/register` | 5 req/min | 3 | Защита от spam |
| `GET /api/v1/predictions/*/stream` | 5 одновременных | — | Limit connections, не requests |
| Остальное (`/api/*`) | 10 req/s | 20 | Общий лимит |

### Механизм

```nginx
location = /api/v1/predictions {
    limit_req zone=predictions burst=3 nodelay;  # 2 req/min, allow burst of 3
    # ...
}

location ~ ^/(api/v1/auth/(login\|register)\|login\|register)$ {
    limit_req zone=auth burst=3 nodelay;  # 5 req/min, allow burst of 3
    # ...
}
```

**Параметры:**

- `zone=predictions` — использовать зону `predictions`
- `burst=3` — разрешить всплеск до 3 дополнительных запросов
- `nodelay` — сразу отклонить лишние запросы (вместо очереди)

### Ответ при превышении

```http
HTTP/1.1 429 Too Many Requests
Content-Type: application/json

{
  "detail": "Rate limit exceeded"
}
```

---

## Security Headers

### Конфигурация

Все security headers отправляются в каждом ответе (nginx):

```nginx
# nginx/security-headers.conf

add_header Strict-Transport-Security "max-age=63072000; includeSubDomains; preload" always;
add_header X-Frame-Options "SAMEORIGIN" always;
add_header X-Content-Type-Options "nosniff" always;
add_header X-XSS-Protection "0" always;
add_header Referrer-Policy "strict-origin-when-cross-origin" always;
add_header Content-Security-Policy "default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdn.jsdelivr.net; font-src 'self' https://fonts.gstatic.com https://cdn.jsdelivr.net; img-src 'self' data:; connect-src 'self'" always;
```

### Каждый заголовок

#### Strict-Transport-Security (HSTS)

```
Strict-Transport-Security: max-age=63072000; includeSubDomains; preload
```

- **max-age=63072000** — 2 года: браузер **всегда** использует HTTPS
- **includeSubDomains** — распространяется на все поддомены
- **preload** — браузеры добавляют delphi.antopkin.ru в встроенный список HSTS

!!! warning "HSTS preload"
    После добавления в HSTS preload лист, удалить невозможно (несколько месяцев). Убедитесь, что HTTPS работает **идеально**, прежде чем добавлять `preload`.

#### X-Frame-Options

```
X-Frame-Options: SAMEORIGIN
```

Предотвращает clickjacking: страницы Delphi Press могут быть встроены только в `<iframe>` на `delphi.antopkin.ru`.

#### X-Content-Type-Options

```
X-Content-Type-Options: nosniff
```

Браузер **не должен** угадывать MIME-тип. Используется только Content-Type заголовок.

#### X-XSS-Protection

```
X-XSS-Protection: 0
```

Отключает встроенный XSS фильтр браузера (современные браузеры используют CSP вместо него).

#### Referrer-Policy

```
Referrer-Policy: strict-origin-when-cross-origin
```

Когда пользователь кликает на внешнюю ссылку, `Referer` заголовок содержит только origin (без пути):

- `https://delphi.antopkin.ru/predictions/123?key=456` → `Referer: https://delphi.antopkin.ru`

#### Content-Security-Policy (CSP)

```
Content-Security-Policy: 
  default-src 'self';
  script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net;
  style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdn.jsdelivr.net;
  font-src 'self' https://fonts.gstatic.com https://cdn.jsdelivr.net;
  img-src 'self' data:;
  connect-src 'self'
```

**Правила:**

- `default-src 'self'` — по умолчанию загружать ресурсы только с собственного origin
- `script-src` — скрипты из собственного origin, inline скрипты (Tailwind), CDN
- `style-src` — стили из собственного origin, inline (Tailwind), Google Fonts, CDN
- `font-src` — шрифты из собственного origin, Google Fonts, CDN
- `img-src` — изображения из собственного origin и data URLs
- `connect-src` — XHR/WebSocket/EventSource только на собственный origin (без cross-origin API)

---

## TLS/HTTPS

### Сертификаты (Let's Encrypt)

Delphi Press использует **Let's Encrypt** для бесплатных автоматических сертификатов.

```nginx
# nginx/nginx.conf

server {
    listen 443 ssl;
    server_name delphi.antopkin.ru;
    
    ssl_certificate     /etc/letsencrypt/live/delphi.antopkin.ru/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/delphi.antopkin.ru/privkey.pem;
}
```

### Конфигурация TLS

```nginx
ssl_protocols TLSv1.2 TLSv1.3;      # Только современные протоколы
ssl_ciphers HIGH:!aNULL:!MD5;       # Сильные шифры, исключить слабые
ssl_prefer_server_ciphers off;      # Использовать предпочтения клиента (TLS 1.3)
ssl_session_cache shared:SSL:10m;   # Кеш сессий для возобновления
ssl_session_timeout 1d;             # Время жизни кеша: 1 день
```

### HTTP → HTTPS редирект

```nginx
server {
    listen 80;
    server_name delphi.antopkin.ru;
    
    # ACME challenge для Let's Encrypt
    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }
    
    # Всё остальное → HTTPS
    location / {
        return 301 https://$host$request_uri;
    }
}
```

### Обновление сертификатов

Let's Encrypt сертификаты действуют 90 дней. Обновление автоматизировано через `certbot`:

```bash
# In docker-compose.yml
certbot:
  image: certbot/certbot:latest
  volumes:
    - /etc/letsencrypt:/etc/letsencrypt
    - /var/www/certbot:/var/www/certbot
  entrypoint: "/bin/sh -c 'trap exit TERM; while :; do certbot renew --webroot -w /var/www/certbot; sleep 12h & wait $!; done'"
```

Certbot проверяет наличие сертификатов раз в 12 часов и автоматически обновляет их при необходимости.

---

## Логирование и мониторинг

### Логирование аутентификации

Все события аутентификации логируются (с маскированием PII):

```python
# src/api/auth.py

# При регистрации:
masked = body.email[0] + "***@" + body.email.split("@")[-1]
logger.info("Registered user %s (%s)", user_id, masked)

# Попытка входа с неверным паролем:
# logger.warning("Failed login attempt: %s", masked)  # опционально
```

### Логирование ошибок

```python
# src/main.py

@application.exception_handler(500)
async def internal_error_handler(request: Request, exc: Exception):
    logger.exception("Internal server error: %s", exc)
    return JSONResponse(status_code=500, ...)
```

### Access log (nginx)

```nginx
log_format main '$remote_addr - $remote_user [$time_local] "$request" '
                '$status $body_bytes_sent "$http_referer" '
                '"$http_user_agent" "$http_x_forwarded_for"';
access_log /var/log/nginx/access.log main;
```

---

## Чек-лист безопасности

!!! info "Production Hardening"
    Перед развёртыванием убедитесь, что:

- [ ] `SECRET_KEY` установлен на 32+ символа (используйте `os.urandom(32).hex()`)
- [ ] `FERNET_KEY` сгенерирован и сохранён `cryptography.fernet.Fernet.generate_key()`
- [ ] `.env` файлы в `.gitignore` (никогда не коммитьте secrets)
- [ ] `DELPHI_PRODUCTION=1` установлен в Docker (включает fail-fast валидацию)
- [ ] CORS настроен правильно (`allow_origins` не `["*"]`)
- [ ] Rate limiting включен в nginx
- [ ] HTTPS работает (сертификаты Let's Encrypt действительны)
- [ ] HSTS header отправляется (проверить в DevTools)
- [ ] CSP политика не имеет `unsafe-eval`
- [ ] API ключи пользователей хранятся зашифрованными (никогда plain text)
- [ ] Пароли хешируются bcrypt, не MD5
- [ ] Логирование включено (access log + error log)
- [ ] Резервные копии БД выполняются регулярно
- [ ] Резервные копии `FERNET_KEY` хранятся отдельно
- [ ] SSRF валидация включена для всех user-provided URLs

---

## Классические уязвимости (OWASP Top 10)

| Уязвимость | Защита в Delphi Press |
|-----------|----------------------|
| A01:2021 – Broken Access Control | JWT + role-based checks |
| A02:2021 – Cryptographic Failures | Fernet (AES-128-CBC), bcrypt |
| A03:2021 – Injection | Pydantic validation, parameterized queries (SQLAlchemy) |
| A04:2021 – Insecure Design | Security headers, rate limiting, CSRF protection, SSRF validation |
| A05:2021 – Security Misconfiguration | TLS 1.2+, disabled debug в production, fail-fast на secrets, secure defaults |
| A06:2021 – Vulnerable Components | Зависимости обновляются, используются modern versions |
| A07:2021 – Authentication Failures | bcrypt + async hashing, JWT с HS256, timing attack protection |
| A08:2021 – Data Integrity Failures | CSRF token validation, HTTPS everywhere |
| A09:2021 – Logging/Monitoring Failures | Логирование auth events, exception handlers |
| A10:2021 – SSRF | SSRF валидация для всех user-provided URLs, async DNS |

---

## Дополнительные ресурсы

- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [JWT Best Practices](https://tools.ietf.org/html/rfc7519)
- [bcrypt](https://github.com/pyca/bcrypt)
- [cryptography.fernet](https://cryptography.io/en/latest/fernet/)
- [Mozilla Security Headers](https://infosec.mozilla.org/guidelines/web_security)
- [HSTS Preload List](https://hstspreload.org/)
- [OWASP SSRF Prevention](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html)

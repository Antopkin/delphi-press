> **Архивная спека.** Этот документ — предреализационное техническое задание. Написан до кода.
> Актуальная документация: [`docs-site/docs/`](../docs-site/docs/). Код — источник правды для схем и сигнатур.

# 01 -- Слой сбора данных (`src/data_sources/`)

## Назначение

Модуль `data_sources` -- низкоуровневый слой доступа к внешним источникам информации. Он не содержит бизнес-логики прогнозирования; его задача -- получить сырые данные и привести их к унифицированным Pydantic-схемам, которые потребляют агенты-сборщики (`src/agents/collectors/`).

**Потребители**: `NewsScout`, `EventCalendar`, `OutletHistorian` (Stage 1 пайплайна).

**Принцип**: каждый подмодуль работает автономно, не знает о пайплайне, принимает примитивные параметры и возвращает типизированные данные.

---

## Структура файлов

```
src/data_sources/
    __init__.py          # Реэкспорт публичного API
    rss.py               # Async RSS fetcher/parser
    web_search.py         # Exa + Jina search обёртки
    scraper.py           # Playwright-based async scraper
    outlets_catalog.py   # Каталог СМИ с метаданными
```

---

## 1. Pydantic-схемы

Все схемы объявлены в `src/schemas/events.py` (shared), но для удобства чтения спеки приведены здесь. Модуль `data_sources` импортирует их оттуда.

### 1.1 SignalRecord

Минимальная единица информации -- один сигнал (новость, анонс, пост). Используется как вход для Stage 2 (кластеризация событий).

```python
from datetime import datetime
from enum import StrEnum
from pydantic import BaseModel, Field, HttpUrl


class SignalSource(StrEnum):
    """Откуда получен сигнал."""
    RSS = "rss"
    WEB_SEARCH = "web_search"
    SCRAPER = "scraper"
    TELEGRAM = "telegram"      # будущее расширение
    MANUAL = "manual"


class SignalRecord(BaseModel):
    """Единичный информационный сигнал из внешнего источника."""

    title: str = Field(..., min_length=5, max_length=500,
                       description="Заголовок / headline")
    summary: str = Field(default="", max_length=2000,
                         description="Краткое содержание / первый абзац")
    url: HttpUrl = Field(..., description="Ссылка на первоисточник")
    published_at: datetime | None = Field(
        default=None,
        description="Дата публикации (UTC). None если не удалось распарсить."
    )
    source_name: str = Field(..., min_length=1, max_length=200,
                             description="Название источника: 'ТАСС', 'Reuters'")
    source_type: SignalSource = Field(...,
                                     description="Тип источника")
    language: str = Field(default="und", max_length=3,
                          description="ISO 639-1 код языка ('ru', 'en', 'und')")
    raw_categories: list[str] = Field(default_factory=list,
                                      description="Теги/категории из RSS или scraper")

    class Config:
        frozen = True

    def dedup_key(self) -> str:
        """Ключ дедупликации: нормализованный URL."""
        return str(self.url).rstrip("/").lower()
```

### 1.2 SearchResult

Результат web search (Exa / Jina). Отличается от SignalRecord наличием поискового скора и сниппета.

```python
class SearchResult(BaseModel):
    """Результат поискового запроса через Exa или Jina."""

    title: str = Field(..., max_length=500)
    url: HttpUrl
    snippet: str = Field(default="", max_length=1000,
                         description="Текстовый сниппет из поисковика")
    published_at: datetime | None = None
    score: float = Field(default=0.0, ge=0.0, le=1.0,
                         description="Relevance score от поисковика (0..1)")
    provider: str = Field(..., description="'exa' | 'jina'")
    raw_data: dict = Field(default_factory=dict,
                           description="Сырой ответ для отладки")

    def to_signal(self, source_name: str = "web_search") -> SignalRecord:
        """Конвертация в SignalRecord для унификации."""
        return SignalRecord(
            title=self.title,
            summary=self.snippet,
            url=self.url,
            published_at=self.published_at,
            source_name=source_name,
            source_type=SignalSource.WEB_SEARCH,
        )
```

### 1.3 ScrapedArticle

Результат скрейпинга одной страницы. Содержит больше контекста, чем RSS.

```python
class ScrapedArticle(BaseModel):
    """Статья, извлечённая скрейпером со страницы СМИ."""

    headline: str = Field(..., min_length=3, max_length=500)
    first_paragraph: str = Field(default="", max_length=3000)
    url: HttpUrl
    published_at: datetime | None = None
    author: str | None = None
    categories: list[str] = Field(default_factory=list)
    outlet_name: str = Field(..., description="Название СМИ")

    def to_signal(self) -> SignalRecord:
        return SignalRecord(
            title=self.headline,
            summary=self.first_paragraph,
            url=self.url,
            published_at=self.published_at,
            source_name=self.outlet_name,
            source_type=SignalSource.SCRAPER,
            raw_categories=self.categories,
        )
```

### 1.4 OutletInfo

Метаданные одного СМИ из каталога. Используется повсюду в пайплайне.

```python
class PoliticalLeaning(StrEnum):
    """Политическая позиция СМИ (упрощённая шкала)."""
    STATE = "state"              # государственное / провластное
    PRO_GOVERNMENT = "pro_gov"   # лояльное
    CENTRIST = "centrist"        # центристское
    LIBERAL = "liberal"          # либеральное
    OPPOSITION = "opposition"    # оппозиционное
    INDEPENDENT = "independent"  # независимое
    UNKNOWN = "unknown"


class OutletInfo(BaseModel):
    """Метаданные одного СМИ из каталога."""

    slug: str = Field(..., pattern=r"^[a-z0-9_-]+$",
                      description="Уникальный идентификатор: 'tass', 'bbc_russian'")
    name: str = Field(..., description="Отображаемое имя: 'ТАСС'")
    name_en: str = Field(default="", description="Английское название для API-запросов")
    country: str = Field(..., max_length=2,
                         description="ISO 3166-1 alpha-2: 'RU', 'GB', 'US'")
    language: str = Field(..., max_length=3,
                          description="Основной язык контента: 'ru', 'en', 'ar'")
    website_url: HttpUrl
    rss_feeds: list[HttpUrl] = Field(default_factory=list,
                                     description="Список RSS/Atom фидов")
    political_leaning: PoliticalLeaning = PoliticalLeaning.UNKNOWN
    description: str = Field(default="",
                             description="Краткое описание для контекста LLM")
    is_telegram: bool = Field(default=False,
                              description="Телеграм-канал (без RSS, только scraper)")
    scrape_url: HttpUrl | None = Field(
        default=None,
        description="URL архивной страницы для скрейпинга (если RSS недоступен)"
    )
    aliases: list[str] = Field(default_factory=list,
                               description="Альтернативные названия для fuzzy match")

    class Config:
        frozen = True
```

---

## 2. RSS-модуль (`rss.py`)

### 2.1 Назначение

Асинхронное получение и парсинг RSS/Atom-фидов из каталога СМИ. Модуль является основным источником сигналов для `NewsScout`.

### 2.2 Архитектурные решения

- **Конкурентность**: все фиды загружаются параллельно через `asyncio.gather` с семафором (не больше 20 одновременных HTTP-запросов).
- **Кеширование**: in-memory кеш на базе `dict[url, (timestamp, entries)]`. Если фид запрашивался менее `ttl` секунд назад, возвращается кешированная версия. TTL по умолчанию = 300 секунд (5 минут). Кеш не персистится -- при перезапуске worker-а очищается.
- **Timeout**: 15 секунд на один фид. Если фид не ответил -- пропускается с логированием warning.
- **feedparser**: вызывается синхронно (CPU-bound), но парсинг XML быстрый (~5ms на фид). Оборачивается в `asyncio.to_thread` для крупных фидов.
- **HTTP-клиент**: `httpx.AsyncClient` с переиспользуемым connection pool. Создаётся один раз на lifetime worker-процесса.
- **User-Agent**: `ForesightingNews/1.0 (RSS fetcher; +https://github.com/...)` -- идентификация для вежливого скрейпинга.
- **Conditional GET**: используются заголовки `If-Modified-Since` и `If-None-Match` (ETag), чтобы не перекачивать неизменённые фиды.

### 2.3 API

```python
import asyncio
from datetime import datetime, timedelta

import feedparser
import httpx

from src.schemas.events import SignalRecord, SignalSource


class RSSFetcher:
    """Асинхронный сборщик RSS-фидов с кешированием и concurrency control."""

    def __init__(
        self,
        *,
        max_concurrent: int = 20,
        timeout_seconds: float = 15.0,
        cache_ttl_seconds: int = 300,
        user_agent: str = "ForesightingNews/1.0 (RSS fetcher)",
    ) -> None:
        """
        Args:
            max_concurrent: Максимальное число параллельных HTTP-запросов.
            timeout_seconds: Timeout на один фид.
            cache_ttl_seconds: Время жизни кеша в секундах (0 = без кеша).
            user_agent: HTTP User-Agent header.
        """
        ...

    async def fetch_feeds(
        self,
        feed_urls: list[str],
        *,
        since: datetime | None = None,
    ) -> list[SignalRecord]:
        """
        Загрузить и распарсить несколько RSS-фидов параллельно.

        Args:
            feed_urls: Список URL RSS/Atom-фидов.
            since: Если указано, возвращает только записи новее этой даты.
                   По умолчанию = 7 дней назад.

        Returns:
            Список SignalRecord, отсортированный по published_at (новые первыми).
            Дубликаты по URL удалены.

        Raises:
            Никаких исключений -- ошибки отдельных фидов логируются и пропускаются.
        """
        ...

    async def fetch_single_feed(
        self,
        feed_url: str,
        *,
        since: datetime | None = None,
    ) -> list[SignalRecord]:
        """
        Загрузить и распарсить один RSS-фид.

        Args:
            feed_url: URL RSS/Atom-фида.
            since: Фильтр по дате публикации.

        Returns:
            Список SignalRecord из этого фида.
        """
        ...

    def _parse_feed_entries(
        self,
        parsed: feedparser.FeedParserDict,
        feed_url: str,
        since: datetime | None,
    ) -> list[SignalRecord]:
        """
        Преобразовать записи feedparser в SignalRecord.

        Внутренний метод. Обрабатывает:
        - Извлечение title, summary, link, published
        - Парсинг даты (feedparser.struct_time -> datetime)
        - Фильтрацию по since
        - Извлечение source_name из feed.title
        """
        ...

    async def close(self) -> None:
        """Закрыть HTTP-клиент. Вызывается при shutdown worker-а."""
        ...
```

### 2.4 Внутренний кеш

```python
# Структура кеша (приватный атрибут RSSFetcher)
_cache: dict[str, _CacheEntry]

@dataclass
class _CacheEntry:
    fetched_at: float          # time.monotonic()
    etag: str | None           # ETag из HTTP-ответа
    last_modified: str | None  # Last-Modified из HTTP-ответа
    records: list[SignalRecord]
```

Логика кеширования в `fetch_single_feed`:
1. Проверить `_cache[url]` -- если `fetched_at + ttl > now`, вернуть `records`.
2. Если запись есть, но TTL истёк -- отправить запрос с `If-None-Match` / `If-Modified-Since`.
3. Если сервер вернул `304 Not Modified` -- обновить `fetched_at`, вернуть кешированные `records`.
4. Если сервер вернул `200` -- распарсить, обновить кеш.

### 2.5 Обработка ошибок

| Ситуация | Действие |
|---|---|
| HTTP timeout | `logger.warning(...)`, вернуть `[]` |
| HTTP 4xx/5xx | `logger.warning(...)`, вернуть `[]` |
| Невалидный XML | `logger.warning(...)`, вернуть `[]` |
| Отсутствует title у entry | Пропустить entry |
| Не парсится дата | Установить `published_at = None` |
| Дубликат URL в batch | Оставить первый (по дате) |

---

## 3. Web Search модуль (`web_search.py`)

### 3.1 Назначение

Поиск свежей информации по текстовому запросу через поисковые API. Используется агентами `NewsScout` (поиск новостей) и `EventCalendar` (поиск запланированных событий).

### 3.2 Поддерживаемые провайдеры

| Провайдер | API | Бесплатный лимит | Особенности |
|---|---|---|---|
| **Exa** | `https://api.exa.ai/search` | 1000 req/мес | Semantic search, свежие результаты, text content |
| **Jina** | `https://s.jina.ai/` | 1000 req/мес (Reader) | LLM-optimized results, Markdown output |

### 3.3 Архитектурные решения

- **Единый интерфейс**: оба провайдера реализуют общий протокол `SearchProvider`.
- **Fallback**: если primary провайдер вернул ошибку или 0 результатов, автоматически пробуется secondary.
- **Rate limiting**: `asyncio.Semaphore` + per-provider `TokenBucket` (не более N запросов в минуту).
- **Дедупликация**: результаты объединяются и дедуплицируются по нормализованному URL.
- **Кеширование**: in-memory кеш по `(provider, query, num_results)` с TTL=600 сек.

### 3.4 API

```python
from abc import ABC, abstractmethod
from datetime import datetime

from src.schemas.events import SearchResult


class SearchProvider(ABC):
    """Абстрактный интерфейс поискового провайдера."""

    @abstractmethod
    async def search(
        self,
        query: str,
        *,
        num_results: int = 10,
        days_back: int = 7,
        language: str | None = None,
    ) -> list[SearchResult]:
        """
        Выполнить поисковый запрос.

        Args:
            query: Текстовый запрос (на любом языке).
            num_results: Максимальное число результатов (1..50).
            days_back: Искать за последние N дней.
            language: Фильтр по языку ('ru', 'en', None = любой).

        Returns:
            Список SearchResult, отсортированный по score (убывание).
        """
        ...


class ExaSearchProvider(SearchProvider):
    """Обёртка над Exa Search API (https://docs.exa.ai)."""

    def __init__(
        self,
        api_key: str,
        *,
        max_requests_per_minute: int = 20,
        timeout_seconds: float = 30.0,
    ) -> None:
        """
        Args:
            api_key: Exa API ключ (env: EXA_API_KEY).
            max_requests_per_minute: Rate limit.
            timeout_seconds: Timeout на один запрос.
        """
        ...

    async def search(
        self,
        query: str,
        *,
        num_results: int = 10,
        days_back: int = 7,
        language: str | None = None,
    ) -> list[SearchResult]:
        """
        Exa search с type='neural' для семантического поиска.

        Использует Exa API параметры:
        - type: "neural" (по умолчанию) или "keyword"
        - numResults: num_results
        - startPublishedDate: datetime.now() - timedelta(days=days_back)
        - contents.text: true (получить текст страницы)
        """
        ...


class JinaSearchProvider(SearchProvider):
    """Обёртка над Jina Search API (https://jina.ai/search)."""

    def __init__(
        self,
        api_key: str,
        *,
        max_requests_per_minute: int = 15,
        timeout_seconds: float = 30.0,
    ) -> None:
        """
        Args:
            api_key: Jina API ключ (env: JINA_API_KEY).
            max_requests_per_minute: Rate limit.
            timeout_seconds: Timeout на один запрос.
        """
        ...

    async def search(
        self,
        query: str,
        *,
        num_results: int = 10,
        days_back: int = 7,
        language: str | None = None,
    ) -> list[SearchResult]:
        """
        Jina search через GET https://s.jina.ai/{query}.

        Headers:
        - Authorization: Bearer {api_key}
        - X-Return-Format: json
        - Accept: application/json
        """
        ...


class WebSearchService:
    """
    Фасад поисковых провайдеров с fallback, дедупликацией и кешированием.
    Это основной класс, который используют агенты.
    """

    def __init__(
        self,
        providers: list[SearchProvider],
        *,
        cache_ttl_seconds: int = 600,
    ) -> None:
        """
        Args:
            providers: Список провайдеров в порядке приоритета.
                       Первый -- primary, остальные -- fallback.
            cache_ttl_seconds: TTL кеша результатов.
        """
        ...

    async def search(
        self,
        query: str,
        *,
        num_results: int = 10,
        days_back: int = 7,
        language: str | None = None,
    ) -> list[SearchResult]:
        """
        Поиск с fallback-логикой.

        Алгоритм:
        1. Проверить кеш.
        2. Запросить primary провайдер.
        3. Если primary вернул 0 результатов или ошибку -- попробовать secondary.
        4. Объединить результаты (если оба вернули данные).
        5. Дедуплицировать по URL.
        6. Отсортировать по score.
        7. Обрезать до num_results.
        8. Сохранить в кеш.

        Returns:
            Список SearchResult (макс. num_results).
        """
        ...

    async def multi_search(
        self,
        queries: list[str],
        *,
        num_results_per_query: int = 10,
        days_back: int = 7,
        language: str | None = None,
    ) -> list[SearchResult]:
        """
        Параллельный поиск по нескольким запросам с общей дедупликацией.

        Использует asyncio.gather с семафором (макс. 5 параллельных запросов).

        Args:
            queries: Список текстовых запросов.
            num_results_per_query: Результатов на один запрос.

        Returns:
            Объединённый и дедуплицированный список SearchResult.
        """
        ...

    async def close(self) -> None:
        """Закрыть HTTP-клиенты всех провайдеров."""
        ...
```

### 3.5 Rate Limiting

```python
class TokenBucket:
    """
    Простая реализация token bucket для rate limiting.
    Не персистится -- сбрасывается при перезапуске.
    """

    def __init__(self, rate: float, capacity: int) -> None:
        """
        Args:
            rate: Токенов в секунду (например, 20/60 = 0.333).
            capacity: Максимальный burst.
        """
        ...

    async def acquire(self) -> None:
        """Подождать, пока не появится свободный токен."""
        ...
```

Каждый `SearchProvider` создаёт свой `TokenBucket` в `__init__` и вызывает `await self._bucket.acquire()` перед каждым HTTP-запросом.

### 3.6 Обработка ошибок

| Ситуация | Действие |
|---|---|
| API key не задан | `logger.error(...)`, провайдер помечается unavailable |
| HTTP 429 (rate limited) | Retry через `Retry-After` header или 60 сек |
| HTTP 5xx | Retry 1 раз с backoff 2 сек, затем fallback |
| Пустые результаты | Попробовать fallback провайдер |
| Невалидный JSON ответ | `logger.error(...)`, fallback |

---

## 4. Scraper модуль (`scraper.py`)

### 4.1 Назначение

Извлечение статей из веб-архивов СМИ, когда RSS недоступен или не содержит нужной глубины (например, Телеграм-каналы через веб-зеркала, или архивные страницы за 30 дней). Используется агентом `OutletHistorian`.

### 4.2 Архитектурные решения

- **Playwright async API**: headless Chromium для рендеринга JavaScript-heavy страниц.
- **Один browser instance**: создаётся при старте worker-а, переиспользуется. Каждый запрос открывает новый `BrowserContext` (изолированные куки, storage).
- **Вежливый скрейпинг**: задержка между запросами (1-3 сек), уважение robots.txt, User-Agent идентификация.
- **Пагинация**: поддержка «Load more» кнопок и infinite scroll через прокрутку + ожидание.
- **Timeout**: 30 секунд на загрузку страницы, 60 секунд на весь scrape одного outlet.
- **Fallback на httpx**: если Playwright недоступен (CI, лёгкий деплой), использовать `httpx` + `selectolux` / `lxml` для статических страниц.

### 4.3 API

```python
from datetime import datetime

from src.schemas.events import ScrapedArticle, OutletInfo


class OutletScraper:
    """
    Playwright-based async scraper для архивных страниц СМИ.
    Один экземпляр на lifetime worker-процесса.
    """

    def __init__(
        self,
        *,
        headless: bool = True,
        delay_between_requests: tuple[float, float] = (1.0, 3.0),
        page_timeout_ms: int = 30_000,
        max_pages: int = 5,
        user_agent: str = "ForesightingNews/1.0 (research scraper)",
    ) -> None:
        """
        Args:
            headless: Запускать Chromium без GUI.
            delay_between_requests: Случайная задержка (min, max) между запросами.
            page_timeout_ms: Timeout загрузки одной страницы.
            max_pages: Максимум страниц пагинации на один outlet.
            user_agent: HTTP User-Agent.
        """
        ...

    async def start(self) -> None:
        """Запустить Playwright browser. Вызывается один раз при старте worker-а."""
        ...

    async def stop(self) -> None:
        """Закрыть browser. Вызывается при shutdown."""
        ...

    async def scrape_outlet(
        self,
        outlet: OutletInfo,
        *,
        since: datetime | None = None,
        max_articles: int = 50,
    ) -> list[ScrapedArticle]:
        """
        Извлечь статьи из архивной страницы СМИ.

        Args:
            outlet: Метаданные СМИ (нужен scrape_url или website_url).
            since: Не извлекать статьи старше этой даты.
                   По умолчанию = 30 дней назад.
            max_articles: Максимальное число статей.

        Returns:
            Список ScrapedArticle, отсортированный по published_at (новые первыми).

        Raises:
            ScraperError: Если скрейпинг полностью провалился.
        """
        ...

    async def scrape_url(
        self,
        url: str,
        *,
        outlet_name: str = "unknown",
    ) -> list[ScrapedArticle]:
        """
        Извлечь статьи с произвольной страницы.

        Args:
            url: URL страницы для скрейпинга.
            outlet_name: Имя СМИ для заполнения ScrapedArticle.outlet_name.

        Returns:
            Список ScrapedArticle, найденных на странице.
        """
        ...

    async def _extract_articles_from_page(
        self,
        page: "playwright.async_api.Page",
        outlet_name: str,
    ) -> list[ScrapedArticle]:
        """
        Извлечь статьи из загруженной страницы.

        Стратегия извлечения (в порядке приоритета):
        1. JSON-LD (schema.org/NewsArticle) -- самый надёжный
        2. OpenGraph meta-теги (og:title, og:description)
        3. Семантические HTML-теги (<article>, <h2>, <time>)
        4. CSS-эвристики (типичные классы: .article, .news-item, .post)

        Returns:
            Список ScrapedArticle.
        """
        ...

    async def _handle_pagination(
        self,
        page: "playwright.async_api.Page",
    ) -> bool:
        """
        Попробовать перейти на следующую страницу.

        Стратегии:
        1. Клик по кнопке «Ещё» / «Load more» / «Next»
        2. Scroll to bottom для infinite scroll
        3. Переход по ссылке ?page=N

        Returns:
            True если удалось загрузить следующую страницу, False если конец.
        """
        ...


class ScraperError(Exception):
    """Ошибка скрейпинга."""
    pass
```

### 4.4 Robots.txt

```python
async def _check_robots_txt(self, url: str) -> bool:
    """
    Проверить, разрешён ли скрейпинг URL по robots.txt.

    Использует urllib.robotparser.RobotFileParser.
    Кеширует robots.txt по домену (TTL=3600 сек).

    Returns:
        True если скрейпинг разрешён.
    """
    ...
```

Если `robots.txt` запрещает URL -- пропускаем с `logger.info("Skipped {url}: robots.txt disallow")`.

### 4.5 Обработка ошибок

| Ситуация | Действие |
|---|---|
| Playwright не установлен | Fallback на httpx + lxml (статические страницы) |
| Timeout загрузки страницы | `logger.warning(...)`, пропустить страницу |
| Captcha / Cloudflare | `logger.warning(...)`, прервать scrape, вернуть собранное |
| Нет статей на странице | Вернуть `[]` |
| robots.txt запрещает | Пропустить URL |
| Некорректная дата | `published_at = None` |

---

## 5. Каталог СМИ (`outlets_catalog.py`)

### 5.1 Назначение

Предопределённый список СМИ с метаданными, RSS-фидами и характеристиками. Используется:
- **Веб-интерфейсом**: autocomplete при вводе названия СМИ.
- **Агентами**: получение RSS-фидов и scrape_url для сбора данных.
- **LLM-промптами**: контекст о политической позиции, стране, языке.

### 5.2 Каталог СМИ

#### Российские СМИ

| slug | name | country | lang | RSS | political_leaning |
|---|---|---|---|---|---|
| `tass` | ТАСС | RU | ru | `https://tass.ru/rss/v2.xml` | state |
| `ria` | РИА Новости | RU | ru | `https://ria.ru/export/rss2/archive/index.xml` | state |
| `interfax` | Интерфакс | RU | ru | `https://www.interfax.ru/rss.asp` | pro_gov |
| `rbc` | РБК | RU | ru | `https://rssexport.rbc.ru/rbcnews/news/30/full.rss` | centrist |
| `vedomosti` | Ведомости | RU | ru | `https://www.vedomosti.ru/rss/news` | centrist |
| `kommersant` | Коммерсантъ | RU | ru | `https://www.kommersant.ru/RSS/news.xml` | centrist |
| `rtvi` | RTVI | RU | ru | -- (scrape) | independent |
| `nezыgar` | Незыгарь | RU | ru | -- (telegram/scrape) | pro_gov |
| `meduza` | Медуза | LV | ru | `https://meduza.io/rss2/all` | opposition |
| `novaya_gazeta` | Новая газета Европа | NL | ru | -- (scrape) | opposition |
| `lenta` | Лента.ру | RU | ru | `https://lenta.ru/rss` | pro_gov |
| `iz` | Известия | RU | ru | `https://iz.ru/xml/rss/all.xml` | state |

#### Международные СМИ (англоязычные)

| slug | name | country | lang | RSS | political_leaning |
|---|---|---|---|---|---|
| `bbc` | BBC News | GB | en | `https://feeds.bbci.co.uk/news/rss.xml` | centrist |
| `bbc_russian` | BBC Russian | GB | ru | `https://feeds.bbci.co.uk/russian/rss.xml` | centrist |
| `reuters` | Reuters | US | en | `https://www.reutersagency.com/feed/` | centrist |
| `ap` | AP News | US | en | -- (scrape) | centrist |
| `cnn` | CNN | US | en | `http://rss.cnn.com/rss/edition.rss` | liberal |
| `guardian` | The Guardian | GB | en | `https://www.theguardian.com/world/rss` | liberal |
| `nyt` | The New York Times | US | en | `https://rss.nytimes.com/services/xml/rss/nyt/World.xml` | liberal |
| `fox_news` | Fox News | US | en | `https://moxie.foxnews.com/google-publisher/world.xml` | pro_gov |
| `wsj` | The Wall Street Journal | US | en | -- (scrape) | centrist |

#### Международные СМИ (прочие)

| slug | name | country | lang | RSS | political_leaning |
|---|---|---|---|---|---|
| `al_jazeera` | Al Jazeera | QA | en | `https://www.aljazeera.com/xml/rss/all.xml` | independent |
| `dw` | Deutsche Welle | DE | en | `https://rss.dw.com/rdf/rss-en-all` | centrist |
| `dw_russian` | DW Russian | DE | ru | `https://rss.dw.com/rdf/rss-ru-all` | centrist |
| `france24` | France 24 | FR | en | `https://www.france24.com/en/rss` | centrist |
| `scmp` | South China Morning Post | HK | en | `https://www.scmp.com/rss/91/feed` | centrist |
| `globaltimes` | Global Times | CN | en | -- (scrape) | state |
| `nhk` | NHK World | JP | en | `https://www3.nhk.or.jp/rss/news/cat0.xml` | centrist |

**Итого**: 28 изданий.

> **Примечание**: URL RSS-фидов необходимо верифицировать при реализации -- фиды могут менять адреса. В коде хранить как конфигурацию, а не хардкод, чтобы можно было обновлять без деплоя.

### 5.3 API

```python
from src.schemas.events import OutletInfo


# Каталог хранится как константа -- список OutletInfo.
# При необходимости можно вынести в JSON/YAML файл.
OUTLETS: list[OutletInfo] = [
    OutletInfo(
        slug="tass",
        name="ТАСС",
        name_en="TASS",
        country="RU",
        language="ru",
        website_url="https://tass.ru",
        rss_feeds=["https://tass.ru/rss/v2.xml"],
        political_leaning=PoliticalLeaning.STATE,
        description="Государственное информационное агентство России. "
                    "Основной источник официальной позиции. "
                    "Стиль: формальный, безэмоциональный, протокольный.",
        aliases=["ИТАР-ТАСС", "tass.ru"],
    ),
    # ... остальные 27 изданий
]


def get_all_outlets() -> list[OutletInfo]:
    """Получить полный каталог СМИ."""
    return OUTLETS


def get_outlet_by_slug(slug: str) -> OutletInfo | None:
    """
    Найти СМИ по slug.

    Args:
        slug: Уникальный идентификатор ('tass', 'bbc_russian').

    Returns:
        OutletInfo или None.
    """
    ...


def search_outlets(
    query: str,
    *,
    limit: int = 5,
) -> list[OutletInfo]:
    """
    Fuzzy-поиск СМИ по названию для autocomplete.

    Алгоритм:
    1. Точное совпадение slug -- вернуть сразу.
    2. Prefix match по name, name_en, aliases (case-insensitive).
    3. Fuzzy match (Levenshtein distance <= 2) по name, aliases.
    4. Отсортировать: точные совпадения первыми, затем prefix, затем fuzzy.

    Args:
        query: Строка поиска ('тасс', 'bbc', 'ком').
        limit: Максимальное число результатов.

    Returns:
        Список OutletInfo, отсортированный по релевантности.
    """
    ...


def get_outlets_by_language(language: str) -> list[OutletInfo]:
    """
    Получить все СМИ, пишущие на указанном языке.

    Args:
        language: ISO 639-1 код ('ru', 'en').

    Returns:
        Список OutletInfo.
    """
    ...


def get_outlets_with_rss() -> list[OutletInfo]:
    """Получить все СМИ, у которых есть хотя бы один RSS-фид."""
    ...
```

### 5.4 Fuzzy Match

Для autocomplete используется простой алгоритм без тяжёлых зависимостей:

```python
def _normalize(text: str) -> str:
    """Lowercase, strip, удаление пунктуации для сравнения."""
    ...

def _levenshtein_distance(s1: str, s2: str) -> int:
    """Расстояние Левенштейна (стандартная реализация O(nm))."""
    ...
```

Если в будущем понадобится более продвинутый fuzzy match, можно подключить `rapidfuzz`.

---

## 6. Интеграция модулей

### 6.1 Фабрика сервисов

Все сервисы создаются в `src/main.py` (lifespan) или `src/worker.py` (при старте worker-а) и передаются агентам через dependency injection (реестр агентов).

```python
# src/data_sources/__init__.py

from src.data_sources.rss import RSSFetcher
from src.data_sources.web_search import (
    ExaSearchProvider,
    JinaSearchProvider,
    WebSearchService,
)
from src.data_sources.scraper import OutletScraper
from src.data_sources.outlets_catalog import (
    get_all_outlets,
    get_outlet_by_slug,
    search_outlets,
    OUTLETS,
)

__all__ = [
    "RSSFetcher",
    "ExaSearchProvider",
    "JinaSearchProvider",
    "WebSearchService",
    "OutletScraper",
    "get_all_outlets",
    "get_outlet_by_slug",
    "search_outlets",
    "OUTLETS",
]
```

### 6.2 Lifecycle

```
Worker startup:
  1. RSSFetcher() -- создать, инициализировать httpx.AsyncClient
  2. WebSearchService([ExaSearchProvider(...), JinaSearchProvider(...)]) -- создать
  3. OutletScraper() -> await scraper.start() -- запустить Playwright

Worker shutdown:
  1. await rss_fetcher.close()
  2. await web_search_service.close()
  3. await scraper.stop()
```

### 6.3 Как агенты используют data_sources

```python
# Пример: NewsScout (src/agents/collectors/news_scout.py)

class NewsScout(BaseAgent):
    def __init__(
        self,
        rss_fetcher: RSSFetcher,
        web_search: WebSearchService,
        ...
    ):
        self._rss = rss_fetcher
        self._search = web_search

    async def execute(self, context: PipelineContext) -> AgentResult:
        outlet = context.outlet  # OutletInfo

        # 1. RSS-сигналы
        rss_signals = await self._rss.fetch_feeds(
            [str(url) for url in outlet.rss_feeds],
            since=context.window_start,
        )

        # 2. Web search сигналы
        queries = self._build_search_queries(outlet, context.target_date)
        search_results = await self._search.multi_search(
            queries, days_back=7, language=outlet.language,
        )
        search_signals = [r.to_signal() for r in search_results]

        # 3. Объединение и дедупликация
        all_signals = self._deduplicate(rss_signals + search_signals)

        return AgentResult(
            agent_name="news_scout",
            data={"signals": [s.model_dump() for s in all_signals]},
            ...
        )
```

---

## 7. Зависимости

Все pip-пакеты, необходимые для `src/data_sources/`:

```toml
# В pyproject.toml [project.dependencies]

# RSS
feedparser = ">=6.0"

# HTTP client (async)
httpx = ">=0.27"

# Web scraping
playwright = ">=1.44"

# HTML parsing (fallback для scraper без Playwright)
lxml = ">=5.0"
selectolax = ">=0.3"  # быстрый CSS selector parser

# Pydantic (shared)
pydantic = ">=2.0"

# Для fuzzy match в каталоге (опционально, можно без неё)
# rapidfuzz = ">=3.0"
```

Playwright требует отдельной установки браузеров:

```bash
# После pip install playwright:
playwright install chromium
```

В Dockerfile это выглядит так:

```dockerfile
RUN pip install playwright && playwright install --with-deps chromium
```

---

## 8. Конфигурация

Все настраиваемые параметры вынесены в `src/config.py` (pydantic-settings):

```python
from pydantic_settings import BaseSettings


class DataSourcesConfig(BaseSettings):
    """Настройки слоя сбора данных."""

    # RSS
    rss_max_concurrent: int = 20
    rss_timeout_seconds: float = 15.0
    rss_cache_ttl_seconds: int = 300

    # Web Search
    exa_api_key: str = ""
    jina_api_key: str = ""
    search_cache_ttl_seconds: int = 600
    exa_max_rpm: int = 20
    jina_max_rpm: int = 15

    # Scraper
    scraper_headless: bool = True
    scraper_delay_min: float = 1.0
    scraper_delay_max: float = 3.0
    scraper_page_timeout_ms: int = 30_000
    scraper_max_pages: int = 5

    class Config:
        env_prefix = "DS_"
```

---

## 9. Тестирование

### 9.1 Unit-тесты

Файл: `tests/test_data_sources/`

| Тест | Что проверяет |
|---|---|
| `test_rss_parse_entries` | Парсинг feedparser output в SignalRecord |
| `test_rss_cache_hit` | Повторный запрос возвращает кеш |
| `test_rss_conditional_get` | 304 Not Modified обновляет TTL |
| `test_rss_timeout` | Timeout возвращает `[]`, не бросает исключение |
| `test_search_dedup` | Дедупликация результатов по URL |
| `test_search_fallback` | Exa fail -> Jina fallback |
| `test_search_rate_limit` | TokenBucket блокирует при превышении |
| `test_scraper_extract` | Извлечение статей из HTML-фикстуры |
| `test_outlet_search_exact` | `search_outlets("ТАСС")` -> ТАСС первый |
| `test_outlet_search_fuzzy` | `search_outlets("тас")` -> ТАСС в результатах |
| `test_outlet_search_english` | `search_outlets("bbc")` -> BBC, BBC Russian |
| `test_signal_dedup_key` | `dedup_key()` нормализует URL |

### 9.2 Интеграционные тесты

Помечены `@pytest.mark.integration`, не запускаются в CI по умолчанию (требуют API-ключи и сеть).

| Тест | Что проверяет |
|---|---|
| `test_rss_fetch_real_feed` | Реальный запрос к ТАСС RSS |
| `test_exa_search_real` | Реальный запрос к Exa API |
| `test_jina_search_real` | Реальный запрос к Jina API |
| `test_scraper_real_outlet` | Скрейпинг реального сайта СМИ |

### 9.3 Фикстуры

```
tests/fixtures/
    rss_tass_sample.xml       # Пример RSS-ответа ТАСС
    rss_bbc_sample.xml        # Пример RSS-ответа BBC
    exa_response.json         # Пример ответа Exa API
    jina_response.json        # Пример ответа Jina API
    outlet_page_sample.html   # HTML-страница для тестов scraper
```

---

## 10. Ограничения и будущие расширения

### Текущие ограничения

- **Телеграм-каналы**: не поддерживаются напрямую. Используется веб-зеркало (t.me/s/{channel}) через scraper. Потери: нет доступа к постам старше ~50.
- **Платные СМИ**: paywall не обходится. Скрейпер извлекает только то, что доступно без авторизации.
- **Языковая детекция**: не реализована автоматически. Язык берётся из каталога (`OutletInfo.language`).

### Расширения v2

- **Telegram Bot API**: прямой доступ к каналам через `telethon` или `pyrogram`.
- **Social media**: Twitter/X API, VK API для мониторинга трендов.
- **Языковая детекция**: `langdetect` или `fasttext` для автоматического определения.
- **Персистентный кеш**: Redis-кеш вместо in-memory для переживания рестартов.
- **Каталог в БД**: перенос каталога СМИ из Python-кода в SQLite для динамического редактирования через UI.

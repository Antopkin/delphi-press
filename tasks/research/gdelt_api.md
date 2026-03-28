# GDELT API Integration Research — Delphi Press

*Ресёрч: 2026-03-28*

## Executive Summary

GDELT offers two access paths relevant to Delphi Press. The **DOC 2.0 API** (`api.gdeltproject.org/api/v2/doc/doc`) provides a no-auth, no-cost REST endpoint returning up to 250 news articles per query with JSON output, covering the past 3 months at 15-minute resolution — directly mappable to `SignalRecord`. The **Events/GKG CSV feed** (updated every 15 minutes at `data.gdeltproject.org/gdeltv2/`) provides structured event data with CAMEO codes, tone scores, and geo context — mappable to `ScheduledEvent` with LLM post-processing. BigQuery access to GKG is powerful but incurs cost at scale (GKG table = 2.65 TB/year; 1 TB free/month). The recommended implementation path is: DOC 2.0 API for `NewsScout` signals → 15-minute CSV feed polling for `EventCalendar` → BigQuery deferred until historical backfill is needed. No API keys required for either the DOC API or CSV downloads.

---

## Key Findings

### Finding 1: GDELT DOC 2.0 API requires no authentication and delivers structured article data

**Evidence:** The DOC 2.0 API base endpoint is `https://api.gdeltproject.org/api/v2/doc/doc`. No API key, no registration. Confirmed by official GDELT blog post ([GDELT DOC 2.0 API Debuts](https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/)) and third-party Python client ([alex9smith/gdelt-doc-api](https://github.com/alex9smith/gdelt-doc-api)). HTTPS is supported. The JSON ArtList response contains these fields per article: `url`, `url_mobile`, `title`, `seendate` (format `YYYYMMDDTHHMMSSZ`), `socialimage`, `domain`, `language` (3-char ISO), `sourcecountry` (2-char FIPS).

**Implication:** Zero infrastructure cost for integration. Can be called directly from `NewsScout` as a supplementary data source alongside RSS and Exa. The `seendate` field maps directly to `SignalRecord.published_at`; `domain` maps to `source_name`; `language` maps to `language` after ISO code normalization.

### Finding 2: Rate limits exist but are undocumented — conservative throttling is necessary

**Evidence:** The GDELT team confirmed rate limiting is active: "Our APIs are rate limited to protect the underlying ElasticSearch clusters, given the enormous volume of requests we receive during peak events." ([Ukraine, API Rate Limiting & Web NGrams 3.0](https://blog.gdeltproject.org/ukraine-api-rate-limiting-web-ngrams-3-0/)). No public numeric threshold. Community reports suggest ~1 req/sec is safe; 429 responses appear at sustained higher rates.

**Implication:** The client must implement a token bucket at ~1 req/s with exponential backoff on 429. Caching is mandatory — the same query with `timespan=24h` should not be re-fetched within 15 minutes (GDELT updates every 15 min, so re-fetching more often is wasted quota).

### Finding 3: GKG themes enable precision topical filtering that reduces noise significantly

**Evidence:** The `theme:` operator filters by GDELT Global Knowledge Graph categories. A lookup of themes used in 100+ articles/2 years is at `http://data.gdeltproject.org/api/v2/guides/LOOKUP-GKGTHEMES.TXT`. Key themes for Delphi Press include: `ECON_CENTRAL_BANK`, `MILITARY_CONFLICT`, `GOV_ELECTIONS`, `NATURAL_DISASTER`, `ENV_CLIMATECHANGE`, `WB_628` (United Nations), `DIPLOMATIC_RELATIONS`. Combining with `sourcelang:` and `sourcecountry:` operators allows per-outlet relevance tuning.

**Implication:** Instead of generic keyword queries, `NewsScout`'s GDELT calls should use `theme:` operators to pre-filter by topic cluster. This reduces the 250-article pool to ~30-50 high-relevance items, cutting downstream LLM classification cost.

### Finding 4: The 15-minute CSV feed is the cleanest path to structured event data

**Evidence:** GDELT 2.0 publishes three CSV files every 15 minutes: Events, Mentions, and GKG. The master file list is at `http://data.gdeltproject.org/gdeltv2/masterfilelist.txt` (updated every 15 min). Each Events CSV row contains 61 fields including: `EventCode` (CAMEO, 4-digit), `Actor1Name`, `Actor2Name`, `GoldsteinScale` (-10 to +10), `NumMentions`, `AvgTone` (-100 to +100), `ActionGeo_CountryCode`, `SOURCEURL`. Files are tab-separated, zipped.

**Implication:** Polling `masterfilelist.txt`, downloading the latest Events CSV, and filtering by `NumMentions > 5` and `GoldsteinScale < -3` (conflict events) provides a structured stream of breaking events for `EventCalendar`. This is more structured than DOC API article search for event detection, but requires CSV parsing infrastructure.

### Finding 5: CAMEO codes map cleanly to the existing `EventType` enum

**Evidence:** CAMEO event taxonomy organizes 310 event codes under 4 QuadClasses: 1=Verbal Cooperation, 2=Material Cooperation, 3=Verbal Conflict, 4=Material Conflict. Root codes: 01-02 (MAKE PUBLIC STATEMENT), 03-04 (CONSULT), 05-06 (ENGAGE IN DIPLOMATIC COOPERATION), 07-08 (PROVIDE AID), 09-10 (INVESTIGATE), 11-12 (DEMAND), 13-14 (THREATEN), 15-16 (EXHIBIT FORCE POSTURE), 17-18 (PROTEST), 19-20 (ASSAULT/COERCE). Full codebook: [GDELT-Event_Codebook-V2.0.pdf](http://data.gdeltproject.org/documentation/GDELT-Event_Codebook-V2.0.pdf).

**Implication:** A static lookup table maps CAMEO root codes to `EventType`: codes 01-06 → `diplomatic`, 07-08 → `political`, 11-14 → `political`/`military`, 17-18 → `social`, 19-20 → `military`. This avoids LLM calls for event classification when using the CSV feed.

### Finding 6: BigQuery is powerful but expensive at GKG scale — use CSV polling instead

**Evidence:** The GDELT GKG table in BigQuery (`gdelt-bq:gdeltv2.gkg`) spans 2.65 TB for the past year. Google BigQuery free tier: 1 TB/month. A single unoptimized GKG query can process 311 GB and cost ~$1.50. With 7-day table decorators (`@-604800000-`), the same query processes 6.28 GB and costs ~$0.03. Events table is smaller (hundreds of GB). Source: [Using BigQuery Table Decorators To Lower Query Cost](https://blog.gdeltproject.org/using-bigquery-table-decorators-to-lower-query-cost/).

**Implication:** BigQuery is viable for retrospective pipeline testing (batch historical queries) but unsuitable for real-time production use without careful cost management. The 15-minute CSV download approach has zero cost beyond bandwidth (~2-5 MB per 15-min batch compressed).

### Finding 7: Context 2.0 API provides sentence-level snippets — useful for signal summarization

**Evidence:** The Context API endpoint is `https://api.gdeltproject.org/api/v2/context/context`. Unlike DOC API (article-level), it returns the specific sentence where a query term appears. Supports `ISQUOTE=1` to return only direct quotes. Coverage: last 72 hours only. Max 200 records. Source: [Announcing The GDELT Context 2.0 API](https://blog.gdeltproject.org/announcing-the-gdelt-context-2-0-api/).

**Implication:** The Context API can enrich `SignalRecord.summary` with the actual quoted sentence around a topic rather than relying on article descriptions. Most useful for political quotes and statements (e.g., `query="sanctions" ISQUOTE=1` returns actual quotes from officials).

---

## GDELT DOC 2.0 API — Full Reference

### Endpoint

```
GET https://api.gdeltproject.org/api/v2/doc/doc
```

No authentication. No API key. HTTPS supported.

### Core Parameters

| Parameter | Values | Notes |
|-----------|--------|-------|
| `query` | String | Supports `"phrase"`, `OR`, `-negation`, operators |
| `mode` | `artlist`, `timelinevol`, `timelinevolraw`, `timelinetone`, `timelinelang`, `timelinesourcecountry` | Case-insensitive |
| `format` | `json`, `csv`, `rss`, `jsonfeed` | Default: HTML |
| `maxrecords` | 1–250 | Default: 75 |
| `timespan` | `15min`, `1h`, `24h`, `7d`, `1m`, `3m` | Default: 3 months |
| `startdatetime` | `YYYYMMDDHHMMSS` | Overrides timespan |
| `enddatetime` | `YYYYMMDDHHMMSS` | Paired with startdatetime |
| `sort` | `datedesc`, `dateasc`, `tonedesc`, `toneDesc`, `hybridrel` | Default: datedesc |

### Advanced Query Operators

```
theme:ECON_CENTRAL_BANK        # GKG theme filter
sourcelang:russian             # Article language (65 supported)
sourcecountry:RS               # Source outlet country (FIPS 2-char)
domain:reuters.com             # Specific domain coverage
domainis:reuters.com           # Exact domain match
tone<-5                        # Sentiment below -5
toneabs>10                     # High emotion intensity
near10:"interest rate hike"    # Terms within 10 words
repeat3:"sanctions"            # Word appears 3+ times
```

### JSON ArtList Response Structure

```json
{
  "articles": [
    {
      "url": "https://example.com/article",
      "url_mobile": "https://m.example.com/article",
      "title": "Article headline text",
      "seendate": "20260328T143000Z",
      "socialimage": "https://example.com/image.jpg",
      "domain": "example.com",
      "language": "English",
      "sourcecountry": "US"
    }
  ]
}
```

Note: `language` is the human-readable English name (e.g., "Russian", "English"), not ISO code. `sourcecountry` is 2-char FIPS (not ISO 3166). Mapping table needed.

### Timeline Response Structure (timelinevol mode)

```json
{
  "timeline": [
    {
      "date": "20260321",
      "value": 0.0023
    }
  ]
}
```

`value` = fraction of all monitored articles covering this topic at that timestamp.

---

## GDELT Event Database — Full Reference

### CSV Feed Architecture

Three parallel files per 15-min interval:
1. **Events** — one row per unique event (deduped by GDELT)
2. **Mentions** — one row per article mentioning an event (many-to-one)
3. **GKG** — Global Knowledge Graph (themes, persons, orgs, tone per article)

Master file list: `http://data.gdeltproject.org/gdeltv2/masterfilelist.txt`
Latest 15-min file: last line of master list

File naming pattern: `YYYYMMDDHHMMSS.export.CSV.zip` (Events), `YYYYMMDDHHMMSS.mentions.CSV.zip` (Mentions), `YYYYMMDDHHMMSS.gkg.csv.zip` (GKG).

### Events CSV Key Fields (61 total)

| Field | Type | Description |
|-------|------|-------------|
| `GlobalEventID` | int | Primary key |
| `Day` | int | YYYYMMDD |
| `Actor1Name` | str | Primary actor (e.g., "RUSSIA", "PUTIN") |
| `Actor2Name` | str | Secondary actor |
| `Actor1CountryCode` | str | CAMEO 3-char country |
| `Actor2CountryCode` | str | CAMEO 3-char country |
| `EventCode` | str | CAMEO event code (e.g., "0411") |
| `EventBaseCode` | str | 3-digit base (e.g., "041") |
| `EventRootCode` | str | 2-digit root (e.g., "04") |
| `QuadClass` | int | 1=VerbalCoop, 2=MatCoop, 3=VerbalConflict, 4=MatConflict |
| `GoldsteinScale` | float | -10 to +10 stability impact |
| `NumMentions` | int | Article mentions in 15-min window |
| `NumSources` | int | Unique sources |
| `NumArticles` | int | Unique articles |
| `AvgTone` | float | -100 to +100 sentiment |
| `ActionGeo_CountryCode` | str | Where event occurred |
| `ActionGeo_Long/Lat` | float | Coordinates |
| `DATEADDED` | int | Ingest timestamp (YYYYMMDDHHMMSS) |
| `SOURCEURL` | str | Original article URL |

### CAMEO → EventType Mapping

```python
CAMEO_TO_EVENT_TYPE = {
    "01": "political",    # Make Public Statement
    "02": "political",    # Appeal
    "03": "diplomatic",   # Express Intent to Cooperate
    "04": "diplomatic",   # Consult
    "05": "diplomatic",   # Engage in Diplomatic Cooperation
    "06": "diplomatic",   # Engage in Material Cooperation
    "07": "political",    # Provide Aid
    "08": "political",    # Yield
    "09": "judicial",     # Investigate
    "10": "judicial",     # Demand
    "11": "political",    # Disapprove
    "12": "political",    # Reject
    "13": "military",     # Threaten
    "14": "military",     # Protest
    "15": "military",     # Exhibit Military Posture
    "16": "military",     # Reduce Relations
    "17": "social",       # Coerce
    "18": "military",     # Assault
    "19": "military",     # Fight
    "20": "military",     # Use Unconventional Mass Violence
}
```

### GKG Key Fields

| Field | Description | Use |
|-------|-------------|-----|
| `V2Themes` | Semicolon-separated GKG themes | Topic classification |
| `V2Persons` | Named persons mentioned | `entities` list |
| `V2Organizations` | Organizations mentioned | `participants` list |
| `V2Tone` | 6 tone dimensions: tone, positive, negative, polarity, activity, self/group | `AvgTone` equivalent |
| `V2Locations` | Locations with geo context | `location` field |
| `GKGRECORDID` | Primary key, format: `YYYYMMDDHHMMSS-N` | Dedup |

---

## Schema Mapping

### DOC 2.0 API → SignalRecord

```python
from datetime import datetime, timezone

def gdelt_article_to_signal(article: dict) -> SignalRecord:
    """Map GDELT DOC 2.0 ArtList article to SignalRecord."""
    
    # Parse seendate: "20260328T143000Z"
    seen_raw = article.get("seendate", "")
    published_at: datetime | None = None
    if seen_raw:
        try:
            published_at = datetime.strptime(seen_raw, "%Y%m%dT%H%M%SZ").replace(
                tzinfo=timezone.utc
            )
        except ValueError:
            pass
    
    # Language: GDELT uses English name ("Russian") → normalize to ISO 639-1
    lang_raw = article.get("language", "").lower()
    LANG_MAP = {
        "english": "en", "russian": "ru", "german": "de",
        "french": "fr", "spanish": "es", "chinese": "zh",
        "arabic": "ar", "japanese": "ja", "ukrainian": "uk",
    }
    language = LANG_MAP.get(lang_raw, lang_raw[:2] if lang_raw else "en")
    
    domain = article.get("domain", "")
    url = article.get("url", "")
    title = article.get("title", "")
    
    return SignalRecord(
        id=f"gdelt_{hashlib.sha256((url + title).encode()).hexdigest()[:12]}",
        title=title,
        summary="",  # DOC API does not return summary text
        url=url,
        source_name=domain,
        source_type=SignalSource.WEB_SEARCH,  # closest existing enum value
        published_at=published_at,
        language=language,
        categories=[],    # enriched via GKG themes if needed
        entities=[],
        relevance_score=0.6,  # base score for GDELT-sourced signals
    )
```

**Gap:** DOC API returns only URL + title, no article body or summary. `SignalRecord.summary` will be empty unless supplemented by a scraper call (optional — only for top-ranked signals).

### Events CSV → ScheduledEvent

```python
import csv
from datetime import date

def gdelt_event_to_scheduled(row: dict) -> ScheduledEvent | None:
    """Map GDELT Events CSV row to ScheduledEvent. Returns None if not newsworthy."""
    
    num_mentions = int(row.get("NumMentions", 0))
    goldstein = float(row.get("GoldsteinScale", 0))
    avg_tone = float(row.get("AvgTone", 0))
    
    # Filter: only events with significant coverage
    if num_mentions < 5:
        return None
    
    event_root = row.get("EventRootCode", "01")
    event_type = CAMEO_TO_EVENT_TYPE.get(event_root, "other")
    
    # Newsworthiness: normalize mentions + abs(goldstein) + abs(tone)
    # NumMentions upper bound: 500 articles = very high
    mention_score = min(num_mentions / 500, 1.0)
    conflict_score = abs(goldstein) / 10.0
    tone_score = abs(avg_tone) / 100.0
    newsworthiness = (mention_score * 0.5 + conflict_score * 0.3 + tone_score * 0.2)
    
    actor1 = row.get("Actor1Name", "")
    actor2 = row.get("Actor2Name", "")
    participants = [a for a in [actor1, actor2] if a]
    
    # Parse date
    day_str = str(row.get("Day", ""))
    event_date: date | None = None
    if len(day_str) == 8:
        try:
            event_date = date(int(day_str[:4]), int(day_str[4:6]), int(day_str[6:8]))
        except ValueError:
            event_date = date.today()
    
    country = row.get("ActionGeo_CountryCode", "")
    source_url = row.get("SOURCEURL", "")
    
    # Certainty based on QuadClass
    quad = int(row.get("QuadClass", 1))
    certainty = EventCertainty.CONFIRMED if quad >= 3 else EventCertainty.LIKELY
    
    title = f"{' vs '.join(participants)}: CAMEO {row.get('EventCode', '?')}"
    
    return ScheduledEvent(
        id=f"evt_{row.get('GlobalEventID', '')}",
        title=title[:300],
        description=f"GoldsteinScale={goldstein}, AvgTone={avg_tone:.1f}, Mentions={num_mentions}",
        event_date=event_date or date.today(),
        event_type=EventType(event_type),
        certainty=certainty,
        location=country,
        participants=participants,
        potential_impact="",  # requires LLM enrichment
        source_url=source_url,
        newsworthiness=round(newsworthiness, 3),
    )
```

**Note:** The `title` field from raw CAMEO data is machine-coded, not human-readable. An LLM enrichment step is needed to convert `"RUSSIA vs UKRAINE: CAMEO 1900"` into `"Russia intensifies military operations in eastern Ukraine"`. This can be batched (10-20 events → 1 LLM call).

---

## Example Queries for Delphi Press Use Cases

### 1. Trending events in the past 24 hours (global)

```
GET https://api.gdeltproject.org/api/v2/doc/doc
  ?query=*
  &mode=timelinevolraw
  &format=json
  &timespan=24h
```

Use `timelinevolraw` to find topic volume spikes — high `value` at recent timestamps = trending.

### 2. Top articles for a target outlet language (Russian, past 6 hours)

```
GET https://api.gdeltproject.org/api/v2/doc/doc
  ?query=*
  &sourcelang=russian
  &mode=artlist
  &format=json
  &maxrecords=50
  &timespan=6h
  &sort=hybridrel
```

### 3. Geopolitical conflict events (for conflict signal enrichment)

```
GET https://api.gdeltproject.org/api/v2/doc/doc
  ?query=theme:MILITARY_CONFLICT+OR+theme:TERROR+OR+theme:GOV_COLLAPSE
  &mode=artlist
  &format=json
  &maxrecords=100
  &timespan=24h
  &sort=datedesc
```

### 4. Economic events for a specific country (Russia)

```
GET https://api.gdeltproject.org/api/v2/doc/doc
  ?query=theme:ECON_CENTRAL_BANK+OR+theme:ECON_TRADE+sourcecountry:RS
  &mode=artlist
  &format=json
  &maxrecords=50
  &timespan=48h
```

### 5. High-tone (emotionally charged) articles (breaking news signal)

```
GET https://api.gdeltproject.org/api/v2/doc/doc
  ?query=toneabs>15
  &mode=artlist
  &format=json
  &maxrecords=100
  &timespan=6h
  &sort=hybridrel
```

### 6. Sentiment timeline for a topic (trend detection)

```
GET https://api.gdeltproject.org/api/v2/doc/doc
  ?query="NATO expansion"
  &mode=timelinetone
  &format=json
  &timespan=7d
```

### 7. Context API — extract quotes from officials (past 24h)

```
GET https://api.gdeltproject.org/api/v2/context/context
  ?query=sanctions
  &ISQUOTE=1
  &format=json
  &timespan=24h
  &maxrecords=50
```

### 8. CSV Events feed — latest 15-min batch

```python
# 1. Fetch master list last line
masterlist_url = "http://data.gdeltproject.org/gdeltv2/masterfilelist.txt"
# Last entry: "size hash http://data.gdeltproject.org/gdeltv2/YYYYMMDDHHMMSS.export.CSV.zip"

# 2. Download + unzip Events CSV
# 3. Parse tab-separated, filter NumMentions > 5
# 4. Map to ScheduledEvent via CAMEO lookup
```

---

## Implementation Plan: Python Async GDELT Client

### Module location

`src/data_sources/gdelt.py`

### Architecture

```python
"""GDELT data source — DOC 2.0 API + Events CSV feed.

Stage 1 data source for NewsScout (SignalRecord) and EventCalendar (ScheduledEvent).
Spec: docs/01-data-sources.md
No authentication required.
"""

from __future__ import annotations

import asyncio
import csv
import gzip
import hashlib
import io
import logging
import time
from datetime import UTC, date, datetime
from typing import Any

import httpx

from src.schemas.events import (
    EventCertainty, EventType, ScheduledEvent, SignalRecord, SignalSource
)

logger = logging.getLogger(__name__)

DOC_API_BASE = "https://api.gdeltproject.org/api/v2/doc/doc"
CONTEXT_API_BASE = "https://api.gdeltproject.org/api/v2/context/context"
MASTERLIST_URL = "http://data.gdeltproject.org/gdeltv2/masterfilelist.txt"

CACHE_TTL_SECONDS = 900  # 15 min — matches GDELT update cycle


class _TokenBucket:
    """Rate limiter: 1 req/sec for GDELT APIs."""
    # (reuse existing _TokenBucket from web_search.py)
    ...


class GdeltDocClient:
    """Async client for GDELT DOC 2.0 API → SignalRecord[]."""

    def __init__(self, *, timeout: float = 30.0) -> None:
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout),
            headers={"User-Agent": "DelphiPress/1.0 (+https://delphi.antopkin.ru/about)"},
        )
        self._bucket = _TokenBucket(rate=1.0, capacity=3)
        self._cache: dict[str, tuple[float, list[SignalRecord]]] = {}

    async def search_articles(
        self,
        query: str,
        *,
        timespan: str = "24h",
        max_records: int = 100,
        sourcelang: str | None = None,
        sourcecountry: str | None = None,
        themes: list[str] | None = None,
        sort: str = "hybridrel",
    ) -> list[SignalRecord]:
        """Fetch articles from DOC 2.0 ArtList mode → SignalRecord[]."""
        
        full_query = query
        if themes:
            theme_filter = " OR ".join(f"theme:{t}" for t in themes)
            full_query = f"({full_query}) ({theme_filter})"
        if sourcelang:
            full_query += f" sourcelang:{sourcelang}"
        if sourcecountry:
            full_query += f" sourcecountry:{sourcecountry}"
        
        cache_key = f"{full_query}:{timespan}:{max_records}"
        cached = self._cache.get(cache_key)
        if cached and (time.monotonic() - cached[0]) < CACHE_TTL_SECONDS:
            return cached[1]
        
        await self._bucket.acquire()
        
        params = {
            "query": full_query,
            "mode": "artlist",
            "format": "json",
            "maxrecords": str(min(max_records, 250)),
            "timespan": timespan,
            "sort": sort,
        }
        
        try:
            resp = await self._client.get(DOC_API_BASE, params=params)
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 429:
                await asyncio.sleep(60)
                logger.warning("GDELT rate limited, backing off 60s")
            logger.error("GDELT DOC API error: %s", exc)
            return []
        except httpx.RequestError as exc:
            logger.warning("GDELT DOC API request failed: %s", exc)
            return []
        
        data = resp.json()
        signals = [
            _article_to_signal(a)
            for a in data.get("articles", [])
            if a.get("url") and a.get("title")
        ]
        self._cache[cache_key] = (time.monotonic(), signals)
        return signals

    async def close(self) -> None:
        await self._client.aclose()


class GdeltEventsFeedClient:
    """Async client for GDELT 2.0 Events CSV feed → ScheduledEvent[]."""

    def __init__(self, *, timeout: float = 60.0) -> None:
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout),
            headers={"User-Agent": "DelphiPress/1.0 (+https://delphi.antopkin.ru/about)"},
        )
        self._last_fetched_url: str | None = None
        self._cache: list[ScheduledEvent] = []
        self._cache_time: float = 0.0

    async def get_latest_events(
        self,
        *,
        min_mentions: int = 5,
        min_abs_goldstein: float = 2.0,
        target_date: date | None = None,
    ) -> list[ScheduledEvent]:
        """Fetch and parse latest 15-min Events CSV."""
        
        if (time.monotonic() - self._cache_time) < CACHE_TTL_SECONDS:
            return self._cache
        
        # Step 1: Get latest CSV URL from master list
        try:
            resp = await self._client.get(MASTERLIST_URL)
            resp.raise_for_status()
        except httpx.RequestError as exc:
            logger.warning("GDELT masterlist fetch failed: %s", exc)
            return []
        
        # Parse: each line = "size hash url"
        # Find last .export.CSV.zip line
        latest_url = None
        for line in resp.text.splitlines():
            parts = line.strip().split()
            if len(parts) == 3 and parts[2].endswith(".export.CSV.zip"):
                latest_url = parts[2]
        
        if not latest_url or latest_url == self._last_fetched_url:
            return self._cache
        
        # Step 2: Download + decompress
        try:
            csv_resp = await self._client.get(latest_url)
            csv_resp.raise_for_status()
        except httpx.RequestError as exc:
            logger.warning("GDELT Events CSV download failed: %s", exc)
            return []
        
        # Decompress zip → CSV bytes
        import zipfile
        zf = zipfile.ZipFile(io.BytesIO(csv_resp.content))
        csv_content = zf.read(zf.namelist()[0]).decode("utf-8", errors="replace")
        
        # Step 3: Parse CSV
        reader = csv.DictReader(
            io.StringIO(csv_content),
            fieldnames=GDELT_EVENTS_COLUMNS,  # see constant below
            delimiter="\t",
        )
        
        events: list[ScheduledEvent] = []
        for row in reader:
            try:
                num_mentions = int(row.get("NumMentions", 0) or 0)
                goldstein = float(row.get("GoldsteinScale", 0) or 0)
                if num_mentions < min_mentions:
                    continue
                if abs(goldstein) < min_abs_goldstein:
                    continue
                evt = _gdelt_row_to_event(row)
                if evt:
                    events.append(evt)
            except (ValueError, TypeError):
                continue
        
        # Sort by newsworthiness desc
        events.sort(key=lambda e: e.newsworthiness, reverse=True)
        
        self._last_fetched_url = latest_url
        self._cache = events[:50]  # keep top 50
        self._cache_time = time.monotonic()
        return self._cache

    async def close(self) -> None:
        await self._client.aclose()
```

### Key constants (add to module)

```python
GDELT_EVENTS_COLUMNS = [
    "GlobalEventID", "Day", "MonthYear", "Year", "FractionDate",
    "Actor1Code", "Actor1Name", "Actor1CountryCode", "Actor1KnownGroupCode",
    "Actor1EthnicCode", "Actor1Religion1Code", "Actor1Religion2Code",
    "Actor1Type1Code", "Actor1Type2Code", "Actor1Type3Code",
    "Actor2Code", "Actor2Name", "Actor2CountryCode", "Actor2KnownGroupCode",
    "Actor2EthnicCode", "Actor2Religion1Code", "Actor2Religion2Code",
    "Actor2Type1Code", "Actor2Type2Code", "Actor2Type3Code",
    "IsRootEvent", "EventCode", "EventBaseCode", "EventRootCode", "QuadClass",
    "GoldsteinScale", "NumMentions", "NumSources", "NumArticles", "AvgTone",
    "Actor1Geo_Type", "Actor1Geo_FullName", "Actor1Geo_CountryCode",
    "Actor1Geo_ADM1Code", "Actor1Geo_Lat", "Actor1Geo_Long", "Actor1Geo_FeatureID",
    "Actor2Geo_Type", "Actor2Geo_FullName", "Actor2Geo_CountryCode",
    "Actor2Geo_ADM1Code", "Actor2Geo_Lat", "Actor2Geo_Long", "Actor2Geo_FeatureID",
    "ActionGeo_Type", "ActionGeo_FullName", "ActionGeo_CountryCode",
    "ActionGeo_ADM1Code", "ActionGeo_Lat", "ActionGeo_Long", "ActionGeo_FeatureID",
    "DATEADDED", "SOURCEURL",
]
```

---

## Rate Limits and Caching Strategy

| Dimension | DOC 2.0 API | Events CSV Feed | BigQuery |
|-----------|-------------|-----------------|----------|
| Auth | None | None | Google account |
| Rate limit | ~1 req/s (undocumented) | Bandwidth only | $5/TB |
| Update freq | 15 min | 15 min | 15 min |
| Latency | 1-3s | 3-10s (download) | 3-15s |
| Max results | 250 articles/query | Full batch (~500-2000 events) | Unlimited |
| Historical depth | 3 months (DOC API) | Full archive (CSV download) | Full archive |

**Caching rules:**
1. DOC API responses: cache by `(query, timespan, maxrecords)` → TTL 15 min
2. Events CSV: cache by `latest_url` — skip if same URL as last fetch
3. Masterlist.txt: fetch every 15 min via ARQ cron (not on-demand)
4. GKG themes lookup: load once at startup, no expiry (changes monthly)

**ARQ integration:**

```python
# In WorkerSettings.cron_jobs:
cron(fetch_gdelt_events, minute={0, 15, 30, 45}),    # 15-min batch
cron(fetch_gdelt_trending, minute={5, 20, 35, 50}),  # DOC API trending scan
```

---

## DOC API vs BigQuery Comparison

| Criterion | DOC 2.0 API | BigQuery |
|-----------|-------------|----------|
| Cost | Free | Free up to 1 TB/mo, then $5/TB |
| Auth | None | Google Cloud account + credentials |
| Setup complexity | `httpx.get()` | google-cloud-bigquery SDK, service account |
| Query language | Custom operators | Standard SQL |
| Max results | 250 per query | Unlimited |
| Historical depth | 3 months | 2015–present |
| GKG themes | Via `theme:` operator | Full V2Themes column |
| Latency | 1-3s | 3-15s (depends on table size scanned) |
| Data freshness | 15 min | 15 min |
| Suitable for | Real-time signal collection | Retrospective testing, historical analysis |
| GKG cost risk | None | HIGH (2.65 TB table; 1 unoptimized query = ~$1.50) |

**Recommendation:** Use DOC 2.0 API for production pipeline. Use BigQuery only for retrospective pipeline testing (the `tasks/todo.md` mentions historical testing as a future task). When BigQuery is needed, always use 7-day table decorators (`@-604800000-`) to limit scan to 6.28 GB instead of full table.

---

## Gotchas and Known Issues

1. **`language` field is English name, not ISO code.** `"Russian"` not `"ru"`. Requires mapping table. The lookup file is at `http://data.gdeltproject.org/api/v2/guides/LOOKUP-LANGUAGES.TXT`.

2. **`sourcecountry` uses FIPS codes, not ISO 3166.** Russia = `RS` (FIPS) not `RU` (ISO). The lookup file is at `http://data.gdeltproject.org/api/v2/guides/LOOKUP-COUNTRIES.TXT`.

3. **No article body in DOC API.** `title` only. If `SignalRecord.summary` is needed, a separate scraper call is required. Recommended: only scrape top-10 signals by relevance, not all 250.

4. **`seendate` is discovery time, not publication time.** GDELT indexes articles when it first sees them. There can be a lag of minutes to hours. Use with awareness that `published_at` may be approximate.

5. **`timespan` minimum is 15 minutes.** Querying more frequently than every 15 minutes returns the same data.

6. **Events CSV is tab-separated despite `.csv` extension.** Use `delimiter="\t"` in csv.DictReader.

7. **Events CSV has no header row.** Must supply column names manually (see `GDELT_EVENTS_COLUMNS` constant above).

8. **CAMEO codes are left-padded strings, not integers.** `"0131"` not `131`. String comparison required.

9. **BigQuery GKG table size.** Do NOT run `SELECT *` on `gdelt-bq:gdeltv2.gkg` without time filter. Use table decorators or `WHERE DATE(_PARTITIONTIME) >= DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY)`.

10. **Rate limit 429 behavior.** GDELT does not return `Retry-After` header. Use fixed 60-second backoff on first 429, then exponential.

---

## Limitations

- GDELT DOC API coverage starts January 1, 2017. Earlier dates require direct CSV download.
- Non-English content is machine-translated by GDELT before indexing; query quality on non-English topics via English keywords is generally adequate but may miss nuance.
- Events CSV does not include full article text — only URLs. The `SignalRecord.summary` gap is a known limitation.
- GDELT's event extraction from articles is automated and has known false positive rates, particularly for historical events re-mentioned in current articles (GDELT may date them as new events).
- The Context 2.0 API is limited to 72 hours — not suitable for longer trend analysis.
- BigQuery queries on the full GKG table without time decorators will exhaust the free 1 TB tier in ~3-4 queries, incurring cost.

---

## Sources

1. [GDELT DOC 2.0 API Debuts — The GDELT Project](https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/)
2. [alex9smith/gdelt-doc-api Python client README](https://github.com/alex9smith/gdelt-doc-api/blob/main/README.md)
3. [Announcing The GDELT Context 2.0 API](https://blog.gdeltproject.org/announcing-the-gdelt-context-2-0-api/)
4. [Ukraine, API Rate Limiting & Web NGrams 3.0](https://blog.gdeltproject.org/ukraine-api-rate-limiting-web-ngrams-3-0/)
5. [GDELT Event Database Data Format Codebook V2.0](http://data.gdeltproject.org/documentation/GDELT-Event_Codebook-V2.0.pdf)
6. [GDELT Global Knowledge Graph Codebook V2.1](http://data.gdeltproject.org/documentation/GDELT-Global_Knowledge_Graph_Codebook-V2.1.pdf)
7. [Using BigQuery Table Decorators To Lower Query Cost](https://blog.gdeltproject.org/using-bigquery-table-decorators-to-lower-query-cost/)
8. [GDELT Data Access Page](https://www.gdeltproject.org/data.html)
9. [Digging into the GDELT Event Schema](https://arpieb.com/2018/06/20/digging-into-the-gdelt-event-schema/)
10. [MissionSquad/mcp-gdelt — MCP Server for GDELT](https://github.com/MissionSquad/mcp-gdelt)
11. [CAMEO Conflict and Mediation Event Observations Codebook](http://data.gdeltproject.org/documentation/CAMEO.Manual.1.1b3.pdf)
12. [Google BigQuery Pricing](https://cloud.google.com/bigquery/pricing)

---
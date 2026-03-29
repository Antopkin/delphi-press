"""Wikidata SPARQL client for media outlet resolution.

Спека: docs/03-collectors.md (outlet catalog enrichment).
Контракт: name → WikidataResult(name, website_url, language, country) | None.
"""

from __future__ import annotations

import logging

import httpx
from pydantic import BaseModel

logger = logging.getLogger(__name__)

WIKIDATA_SPARQL_URL = "https://query.wikidata.org/sparql"
_TIMEOUT_SECONDS = 10

SPARQL_TEMPLATE = """
SELECT DISTINCT ?itemLabel ?website ?langLabel ?countryLabel WHERE {{
  VALUES ?mediaTypes {{ wd:Q11032 wd:Q1193236 wd:Q1145276 wd:Q15265344 }}
  ?item wdt:P31/wdt:P279* ?mediaTypes .
  ?item rdfs:label ?label .
  FILTER(CONTAINS(LCASE(STR(?label)), LCASE("{query}")))
  OPTIONAL {{ ?item wdt:P856 ?website . }}
  OPTIONAL {{ ?item wdt:P407 ?lang . }}
  OPTIONAL {{ ?item wdt:P17 ?country . }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "ru,en". }}
}} LIMIT 5
"""


class WikidataResult(BaseModel, frozen=True):
    """Structured result from Wikidata SPARQL lookup."""

    name: str
    website_url: str = ""
    language: str = ""
    country: str = ""


async def wikidata_lookup(name: str) -> WikidataResult | None:
    """Look up a media outlet by name via Wikidata SPARQL.

    Returns the first matching result or None if not found / error.
    """
    query = SPARQL_TEMPLATE.format(query=name.replace('"', '\\"'))
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
            response = await client.get(
                WIKIDATA_SPARQL_URL,
                params={"query": query, "format": "json"},
                headers={"User-Agent": "DelphiPress/1.0"},
            )
            response.raise_for_status()
            data = response.json()
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        logger.warning("Wikidata lookup failed for %r: %s", name, exc)
        return None

    bindings = data.get("results", {}).get("bindings", [])
    if not bindings:
        return None

    first = bindings[0]
    return WikidataResult(
        name=first.get("itemLabel", {}).get("value", name),
        website_url=first.get("website", {}).get("value", ""),
        language=first.get("langLabel", {}).get("value", ""),
        country=first.get("countryLabel", {}).get("value", ""),
    )

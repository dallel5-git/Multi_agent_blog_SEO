"""Adapter de recherche Tavily (free tier, 1000 requêtes/mois) — repli optionnel.

Activé uniquement si `TAVILY_API_KEY` est présente dans `.env`. Appel REST brut,
pas de SDK.
"""

from __future__ import annotations

import logging

import requests

from ...domain.ports.search import SearchPort, SearchResult
from ...shared.retry import retry

logger = logging.getLogger(__name__)

_ENDPOINT = "https://api.tavily.com/search"


class TavilySearch(SearchPort):
    """Recherche web via Tavily free tier."""

    name = "tavily"

    def __init__(self, api_key: str, *, timeout_s: int = 30, session: requests.Session | None = None) -> None:
        self.api_key = api_key
        self.timeout_s = timeout_s
        self._session = session or requests.Session()

    def is_available(self) -> bool:
        return bool(self.api_key)

    def search(self, query: str, *, max_results: int = 8, region: str = "") -> list[SearchResult]:
        return self._run(query, max_results, topic="general")

    def search_news(self, query: str, *, max_results: int = 8, region: str = "") -> list[SearchResult]:
        return self._run(query, max_results, topic="news")

    @retry(attempts=2, base_delay=2.0)
    def _run(self, query: str, max_results: int, topic: str) -> list[SearchResult]:
        if not self.api_key:
            return []
        payload = {
            "api_key": self.api_key,
            "query": query,
            "max_results": max_results,
            "search_depth": "basic",  # « basic » consomme 1 crédit, « advanced » en consomme 2
            "topic": topic,
            "include_answer": False,
        }
        try:
            response = self._session.post(_ENDPOINT, json=payload, timeout=self.timeout_s)
            if response.status_code >= 400:
                logger.warning("Tavily HTTP %s : %s", response.status_code, response.text[:200])
                return []
            data = response.json()
        except (requests.RequestException, ValueError) as exc:
            logger.warning("Tavily a échoué pour « %s » : %s", query, exc)
            return []

        results = [
            SearchResult(
                title=(item.get("title") or "").strip(),
                url=(item.get("url") or "").strip(),
                snippet=(item.get("content") or "").strip(),
                source=self.name,
            )
            for item in data.get("results", [])
        ]
        logger.info("[tavily/%s] « %s » → %s résultat(s)", topic, query, len(results))
        return [r for r in results if r.url and r.title]

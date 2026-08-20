"""Adapter de recherche DuckDuckGo — source principale, aucune clé d'API.

La librairie s'est appelée successivement `duckduckgo-search` (classe `DDGS`)
puis `ddgs`. On tente les deux imports pour ne pas casser à la prochaine
migration de nom de paquet.
"""

from __future__ import annotations

import logging
import time

from ...domain.ports.search import SearchPort, SearchResult
from ...shared.retry import retry

logger = logging.getLogger(__name__)


def _import_ddgs():
    """Importe la classe DDGS quel que soit le nom du paquet installé."""
    try:
        from ddgs import DDGS  # type: ignore[import-not-found]

        return DDGS
    except ImportError:
        pass
    try:
        from duckduckgo_search import DDGS  # type: ignore[import-not-found]

        return DDGS
    except ImportError:
        return None


class DuckDuckGoSearch(SearchPort):
    """Recherche web gratuite, sans clé et sans quota déclaré."""

    name = "duckduckgo"

    def __init__(self, *, delay_s: float = 2.0, default_region: str = "wt-wt") -> None:
        self.delay_s = delay_s
        self.default_region = default_region
        self._ddgs_cls = _import_ddgs()
        self._last_call = 0.0
        if self._ddgs_cls is None:
            logger.warning(
                "duckduckgo-search / ddgs non installé : la recherche web sera désactivée. "
                "Installez-le avec `pip install ddgs`."
            )

    def is_available(self) -> bool:
        return self._ddgs_cls is not None

    def _throttle(self) -> None:
        """DuckDuckGo bannit temporairement les appels trop rapprochés."""
        elapsed = time.monotonic() - self._last_call
        if elapsed < self.delay_s:
            time.sleep(self.delay_s - elapsed)
        self._last_call = time.monotonic()

    # ------------------------------------------------------------------ #
    def search(self, query: str, *, max_results: int = 8, region: str = "") -> list[SearchResult]:
        return self._run("text", query, max_results, region)

    def search_news(self, query: str, *, max_results: int = 8, region: str = "") -> list[SearchResult]:
        results = self._run("news", query, max_results, region)
        return results or self._run("text", query, max_results, region)

    @retry(attempts=2, base_delay=3.0)
    def _run(self, mode: str, query: str, max_results: int, region: str) -> list[SearchResult]:
        if self._ddgs_cls is None:
            return []

        self._throttle()
        region = region or self.default_region
        try:
            with self._ddgs_cls() as ddgs:
                method = getattr(ddgs, mode)
                raw = list(method(query, region=region, safesearch="moderate", max_results=max_results))
        except Exception as exc:  # noqa: BLE001 - dégradation gracieuse
            logger.warning("DuckDuckGo (%s) a échoué pour « %s » : %s", mode, query, exc)
            return []

        results = [
            SearchResult(
                title=(item.get("title") or "").strip(),
                url=(item.get("href") or item.get("url") or "").strip(),
                snippet=(item.get("body") or item.get("excerpt") or "").strip(),
                source=item.get("source") or self.name,
            )
            for item in raw
        ]
        results = [r for r in results if r.url and r.title]
        logger.info("[duckduckgo/%s] « %s » → %s résultat(s)", mode, query, len(results))
        return results

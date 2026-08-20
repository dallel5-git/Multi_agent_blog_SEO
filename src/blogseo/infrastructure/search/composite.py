"""Recherche composite : DuckDuckGo d'abord, Tavily en secours.

Même logique que la chaîne LLM : le premier moteur disponible qui renvoie des
résultats gagne. Si aucun ne répond, on renvoie une liste vide plutôt que de
lever — une veille incomplète ne doit pas faire tomber le pipeline.
"""

from __future__ import annotations

import logging

from ...domain.ports.search import SearchPort, SearchResult

logger = logging.getLogger(__name__)


class CompositeSearch(SearchPort):
    """Compose plusieurs `SearchPort` en cascade."""

    name = "composite-search"

    def __init__(self, engines: list[SearchPort]) -> None:
        self.engines = [e for e in engines if e is not None]

    def is_available(self) -> bool:
        return any(engine.is_available() for engine in self.engines)

    def search(self, query: str, *, max_results: int = 8, region: str = "") -> list[SearchResult]:
        return self._cascade("search", query, max_results, region)

    def search_news(self, query: str, *, max_results: int = 8, region: str = "") -> list[SearchResult]:
        return self._cascade("search_news", query, max_results, region)

    def _cascade(self, method: str, query: str, max_results: int, region: str) -> list[SearchResult]:
        for engine in self.engines:
            if not engine.is_available():
                continue
            results = getattr(engine, method)(query, max_results=max_results, region=region)
            if results:
                return results
            logger.debug("[%s] aucun résultat pour « %s », essai du moteur suivant", engine.name, query)
        logger.warning("Aucun moteur de recherche n'a renvoyé de résultat pour « %s »", query)
        return []

    def search_many(self, queries: list[str], *, max_results: int = 5, region: str = "") -> list[SearchResult]:
        """Exécute plusieurs requêtes et dédoublonne par URL."""
        seen: set[str] = set()
        merged: list[SearchResult] = []
        for query in queries:
            for result in self.search(query, max_results=max_results, region=region):
                if result.url not in seen:
                    seen.add(result.url)
                    merged.append(result)
        return merged

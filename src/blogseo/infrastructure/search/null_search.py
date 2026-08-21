"""Adapter neutre de `SearchPort`, utilisé en mode `--offline`.

Renvoie toujours une liste vide, sans aucun appel réseau — c'est le pendant du
`FakeLLM` et du `NullNotifier` pour la recherche web.
"""

from __future__ import annotations

from ...domain.ports.search import SearchPort, SearchResult


class NullSearch(SearchPort):
    """Aucune recherche : utilisé quand le pipeline tourne hors ligne."""

    name = "null-search"

    def search(self, query: str, *, max_results: int = 8, region: str = "fr-fr") -> list[SearchResult]:
        return []

    def is_available(self) -> bool:
        return False
